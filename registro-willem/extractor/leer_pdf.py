"""
Lectura de un informe de alta del Servicio Murciano de Salud (PDF de texto).

Separa el informe en sus partes:
  - cabecera  (se repite en cada página: NHC, nombre, CIP, domicilio...)
  - cuerpo    (el texto clínico, de "MOTIVO DE INGRESO" a "MOTIVO DE ALTA")
  - firma     ("Fdo: Dr./Dra. ...", nº de colegiado y fecha)
  - pie       (centro de salud, enfermera y médico de Atención Primaria)

No usa inteligencia artificial: la cabecera tiene siempre las mismas casillas y se lee
por su posición. Solo usa la biblioteca estándar y pypdf (incluido en extractor/vendor).
"""
import datetime as dt
import logging
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if os.path.join(AQUI, "vendor") not in sys.path:
    sys.path.insert(0, os.path.join(AQUI, "vendor"))
import pypdf  # noqa: E402

# pypdf avisa de "texto girado" (el código lateral del SMS): no nos interesa verlo
logging.getLogger("pypdf").setLevel(logging.ERROR)


class InformeNoValido(Exception):
    """El PDF no se puede procesar con seguridad (se bloquea y se explica por qué)."""


# Casillas de la cabecera. Columna izquierda y derecha.
ETIQ_IZQ = [("N.H.C.", "nhc"), ("Nombre", "nombre"), ("1ªApellido", "apellido1"),
            ("2º Apellido", "apellido2"), ("Sexo", "sexo"), ("F.Nacim(Edad)", "nacimiento"),
            ("Teléfono", "telefono"), ("Domicilio", "domicilio"), ("C.I.P.SNS", "cip_sns"),
            ("Financiación", "financiacion")]
ETIQ_DER = [("DNI/NIE/PPTE", "dni"), ("Servicio", "servicio"), ("Nº Cama", "cama"),
            ("F. Ingreso", "ingreso"), ("F. Alta", "alta"), ("Nº Acto", "acto"),
            ("N.S.S.", "nss"), ("Población", "poblacion"), ("C.I.P.A.", "cip_carm"),
            ("Patología", "patologia")]
# Casillas cuyo valor puede ocupar más de una línea
VARIAS_IZQ = {"nombre", "apellido1", "apellido2", "telefono", "domicilio"}
VARIAS_DER = {"servicio", "poblacion", "patologia"}

# Membrete del hospital (a la derecha de la cabecera): no es dato del paciente
MEMBRETE = [r"Hospital\s+Cl[ií]nico", r"Universitario\s+Virgen", r"de\s+la\s+Arrixaca",
            r"Ctra\.\s*Madrid\s*[–-]\s*Cartagena", r"30120\s+El\s+Palmar\s*\(Murcia\)",
            r"Telf\.\s*968\s*36\s*95\s*00"]
RE_MEMBRETE = re.compile("|".join(MEMBRETE))
RE_PAGINA = re.compile(r"P[áa]g\s*\d+\s*de\s*\d+")
RE_HUELLA = re.compile(r"\[[0-9a-fA-F]{32,}\]")


def _patron_etiqueta(etiq):
    # tolerante a espacios: "1ªApellido" = "1ª Apellido"
    return re.compile(r"\s*".join(re.escape(c) for c in etiq.replace(" ", "")))


P_IZQ = [(_patron_etiqueta(e), k) for e, k in ETIQ_IZQ]
P_DER = [(_patron_etiqueta(e), k) for e, k in ETIQ_DER]


def _tapar(linea, patron):
    """Sustituye por espacios lo que coincide (conserva las columnas)."""
    return patron.sub(lambda m: " " * len(m.group(0)), linea)


def _quitar_etiqueta(texto, patrones):
    t = texto.strip()
    for p, k in patrones:
        m = p.match(t)
        if m:
            return k, t[m.end():].strip()
    return None, t


def texto_de_paginas(ruta):
    try:
        lector = pypdf.PdfReader(ruta)
        # Los informes del SMS vienen "protegidos" solo contra edición (sin contraseña de apertura)
        if lector.is_encrypted and not lector.decrypt(""):
            raise InformeNoValido("El PDF está protegido con contraseña de apertura.")
        return [p.extract_text(extraction_mode="layout") or "" for p in lector.pages]
    except InformeNoValido:
        raise
    except Exception as e:  # PDF dañado o que no es un PDF
        raise InformeNoValido(f"No se ha podido abrir el PDF ({type(e).__name__}).")


def _leer_cabecera(lineas):
    """lineas: las de la cabecera de una página. Devuelve ({campo: texto}, [todos los valores])."""
    col2 = None
    for ln in lineas:
        m = P_DER[0][0].search(ln)  # DNI/NIE/PPTE marca dónde empieza la columna derecha
        if m:
            col2 = m.start()
            break
    if col2 is None:
        raise InformeNoValido("No se reconoce la cabecera del informe (falta la casilla DNI/NIE).")
    filas = []  # (indice, etiqueta_izq, valor_izq, etiqueta_der, valor_der)
    for i, ln in enumerate(lineas):
        ln = _tapar(_tapar(_tapar(ln, RE_MEMBRETE), RE_PAGINA), RE_HUELLA)
        ki, vi = _quitar_etiqueta(ln[:max(col2 - 1, 0)], P_IZQ)
        kd, vd = _quitar_etiqueta(ln[max(col2 - 1, 0):], P_DER)
        filas.append((i, ki, vi, kd, vd))

    campos = {}

    def repartir(lado_etq, lado_val, multiples):
        con_etiqueta = [(f[0], f[lado_etq]) for f in filas if f[lado_etq]]
        partes = {k: [] for _, k in con_etiqueta}
        for f in filas:
            idx, etq, val = f[0], f[lado_etq], f[lado_val]
            if etq:
                if val:
                    partes[etq].append((idx, val))
                continue
            if not val:
                continue
            # Línea de continuación: ¿a qué casilla pertenece?
            if lado_etq == 1 and re.fullmatch(r"[\d\s/.-]+", val) and "telefono" in partes:
                partes["telefono"].append((idx, val))
                continue
            candidatas = [(abs(i - idx), -i, k) for i, k in con_etiqueta if k in multiples]
            if candidatas:
                _, _, k = min(candidatas)  # la más cercana; si empatan, la de abajo
                partes[k].append((idx, val))
            else:
                partes.setdefault("_sin_casilla", []).append((idx, val))
        for k, trozos in partes.items():
            campos[k] = " ".join(v for _, v in sorted(trozos)).strip()

    repartir(1, 2, VARIAS_IZQ)
    repartir(3, 4, VARIAS_DER)
    valores = [v for f in filas for v in (f[2], f[4]) if v]
    return campos, valores


def _fecha(txt):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", txt or "")
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def interpretar_cabecera(c):
    """Pasa los textos de las casillas a datos limpios."""
    out = {k: (c.get(k) or "").strip() for _, k in ETIQ_IZQ + ETIQ_DER}
    out["dni"] = out["dni"].strip(" /").upper()
    out["nss"] = out["nss"].strip()
    out["telefonos"] = sorted(set(re.findall(r"\d{9}", re.sub(r"(?<=\d)[ .-](?=\d)", "", out["telefono"]))
                                  + re.findall(r"\d{9}", out["telefono"])))
    out["fecha_nacimiento"] = _fecha(out["nacimiento"])
    m = re.search(r"\((\d+)\s*A", out["nacimiento"])
    out["edad"] = int(m.group(1)) if m else None
    out["fecha_ingreso"] = _fecha(out["ingreso"])
    out["fecha_alta"] = _fecha(out["alta"])
    m = re.search(r"CARM\s*\d+", out["cip_carm"].upper())
    out["cip_carm"] = m.group(0).replace(" ", "") if m else out["cip_carm"].replace(" ", "").upper()
    out["cip_sns"] = out["cip_sns"].replace(" ", "").upper()
    m = re.match(r"\s*(\d{5})?\s*(.*)$", out["poblacion"])
    resto = (m.group(2) if m else out["poblacion"]).strip().rstrip(",")
    out["cp"] = (m.group(1) if m else "") or ""
    # "Sangonera La Seca, Murcia" -> localidad "Sangonera La Seca", provincia "Murcia"
    if "," in resto:
        loc, prov = resto.rsplit(",", 1)
        if "(" in prov and ")" not in loc:  # "Garres (Los), Murcia" ya va bien; caso raro
            loc, prov = resto, ""
        out["localidad"], out["provincia"] = loc.strip(), prov.strip()
    else:
        out["localidad"], out["provincia"] = resto, ""
    out["sexo"] = out["sexo"].capitalize()
    return out


def _leer_pie(lineas, i):
    """lineas[i] es la de 'Centro de Salud: Enfermera...: Médico...:'."""
    cab = lineas[i]
    val = ""
    for ln in lineas[i + 1:]:
        if ln.strip():
            val = ln
            break
    c_enf = cab.find("Enfermera")
    c_med = cab.find("Médico") if "Médico" in cab else cab.find("Medico")
    trozos = re.split(r"\s{2,}", val.strip())
    if len(trozos) == 3:
        centro, enf, med = trozos
    elif c_enf > 0 and c_med > c_enf:
        centro, enf, med = val[:c_enf - 1], val[c_enf - 1:c_med - 1], val[c_med - 1:]
    else:
        centro, enf, med = val, "", ""
    resto = [ln.strip() for ln in lineas[i + 1:] if ln.strip()][1:]
    return {"centro": centro.strip(), "enfermera": enf.strip(), "medico": med.strip(), "extra": resto}


RE_FDO = re.compile(r"^\s*Fdo\s*[:.]", re.I)


def _separar_firma(cuerpo):
    """Quita el bloque de firma del cuerpo. Devuelve (cuerpo, firma)."""
    firma = {"lineas": [], "nombres": [], "colegiados": []}
    for i, ln in enumerate(cuerpo):
        if not RE_FDO.match(ln):
            continue
        j = i + 1
        bloque = [ln]
        while j < len(cuerpo):
            s = cuerpo[j].strip()
            if (not s or s.startswith("/") or re.match(r"Col\.?\s*N", s, re.I) or re.match(r"Fecha\s*:", s, re.I)
                    or re.fullmatch(r"[\d/.\- ]{6,12}", s)):
                bloque.append(cuerpo[j])
                j += 1
                continue
            break
        texto = " ".join(x.strip() for x in bloque)
        m = re.search(r"Fdo\s*[:.]\s*(?:Dr\.?\s*/?\s*Dra\.?|Dra?\.?)?\s*(.*?)(?:Col\.?\s*N|Fecha\s*:|$)", texto, re.I)
        nombres = [n.strip(" ,/") for n in re.split(r"\s/\s*|^/", m.group(1) if m else "") if n.strip(" ,/")]
        firma["nombres"] += nombres
        firma["colegiados"] += re.findall(r"\d{6,}", re.sub(r".*?Col\.?\s*N[º°o]?\.?\s*:?", "", texto, count=1, flags=re.I)
                                          if re.search(r"Col\.?\s*N", texto, re.I) else "")
        firma["lineas"] += [x.strip() for x in bloque if x.strip()]
        return cuerpo[:i] + cuerpo[j:], firma
    return cuerpo, firma


def leer_informe(ruta):
    paginas = texto_de_paginas(ruta)
    if not paginas or not any(p.strip() for p in paginas):
        raise InformeNoValido("El PDF no contiene texto (¿es un escaneo o una foto?).")
    cabeceras, valores, cuerpo, pies = [], [], [], []
    titulo = ""
    for n, txt in enumerate(paginas):
        lineas = txt.split("\n")
        fin = next((i for i, ln in enumerate(lineas) if P_IZQ[-1][0].search(ln)), None)  # Financiación
        if fin is None:
            if n == 0:
                raise InformeNoValido("No se reconoce la cabecera del informe (¿es un informe de alta del SMS?).")
            fin = -1  # página sin cabecera: todo es cuerpo
        else:
            c, v = _leer_cabecera(lineas[:fin + 1])
            cabeceras.append(c)
            valores += v
        resto = lineas[fin + 1:]
        # pie: la última línea "Centro de Salud:" de la página
        i_pie = max((i for i, ln in enumerate(resto) if re.match(r"\s*Centro de Salud\s*:", ln)), default=None)
        if i_pie is not None:
            pies.append(_leer_pie(resto, i_pie))
            resto = resto[:i_pie]
        if n == 0:
            for i, ln in enumerate(resto):
                if ln.strip():
                    if "INFORME" in ln.upper():
                        titulo = re.sub(r"\s+", " ", ln.strip())
                        resto = resto[i + 1:]
                    break
        cuerpo += [_tapar(ln, RE_HUELLA).rstrip() for ln in resto]
    # Todas las páginas deben ser del mismo paciente
    claves = {(c.get("nhc", "").strip(), c.get("cip_carm", "").strip()) for c in cabeceras}
    if len(claves) > 1:
        raise InformeNoValido("El PDF contiene páginas de más de un paciente (cabeceras distintas).")
    cab = interpretar_cabecera(cabeceras[0])
    cuerpo, firma = _separar_firma(cuerpo)
    # limpia espacios y líneas vacías repetidas
    limpio = []
    for ln in cuerpo:
        s = re.sub(r"[ \t ]{2,}", " ", ln.strip())
        if s or (limpio and limpio[-1]):
            limpio.append(s)
    while limpio and not limpio[-1]:
        limpio.pop()
    pie = pies[0] if pies else {"centro": "", "enfermera": "", "medico": "", "extra": []}
    for p in pies[1:]:
        pie["extra"] = sorted(set(pie["extra"] + [p["centro"], p["enfermera"], p["medico"]] + p["extra"]) - {pie["centro"], pie["enfermera"], pie["medico"], ""})
    return {
        "paginas": len(paginas),
        "titulo": titulo,
        "cabecera": cab,
        "valores_cabecera": sorted(set(valores)),
        "cuerpo": limpio,
        "firma": firma,
        "pie": pie,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(leer_informe(sys.argv[1]), ensure_ascii=False, indent=1))
