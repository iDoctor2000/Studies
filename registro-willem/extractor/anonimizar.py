"""
Anonimización del texto clínico de un informe de alta + DOBLE CONTROL.

1) Todo lo que viene en la cabecera, el pie y la firma se elimina sin más.
2) En el texto clínico se sustituye:
     - lo que ya sabemos que identifica a ESTE paciente (nombre, apellidos, teléfonos, NHC,
       DNI, CIP, nº de Seguridad Social, nº de episodio, cama, domicilio, localidad)
     - los profesionales del informe (firmantes, enfermera y médico de primaria) y los del
       "directorio de profesionales" que se va formando con todos los informes procesados
     - patrones generales: DNI/NIE, teléfonos, correos, CIP, "Dr./Dra. Apellido", direcciones...
     - las palabras de la lista "ocultar_tambien.txt"
3) DOBLE CONTROL: se vuelve a buscar en el resultado cada identificador conocido, normalizado
   (sin tildes, sin mayúsculas, sin espacios ni puntos). Si aparece alguno -> BLOQUEADO.
4) AVISOS: posibles nombres que no se pueden confirmar automáticamente (p. ej. "(Arce /Gañan)").
   Un informe con avisos no pasa a la carpeta compartida hasta que una persona lo revise.

Las fechas clínicas se conservan (son datos del estudio). Solo biblioteca estándar.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
LETRA = r"A-Za-zÁÉÍÓÚÜÑáéíóúüñÀÈÌÒÙàèìòùÇç"
SIN_LETRA_ANTES = rf"(?<![{LETRA}0-9])"
SIN_LETRA_DESPUES = rf"(?![{LETRA}0-9])"
RE_ETIQUETA = re.compile(r"\[[A-ZÁÉÍÓÚÑº ]{2,}\]")

# Partículas que no se buscan solas
PARTICULAS = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "I", "E", "SAN", "SANTA", "MC", "VON", "VAN", "DA", "DO", "DOS"}

# Nombres y apellidos que también son palabras corrientes (o médicas): solos no se sustituyen
# (sí cuando van junto a otro nombre o detrás de Dr./Dra./Sr./Sra.). Solo generan aviso.
PALABRAS_CORRIENTES = {
    "DOLORES", "ROSARIO", "ANGELES", "PILAR", "LUZ", "PAZ", "CONSUELO", "REMEDIOS", "ROSA", "MAR", "SOL",
    "ESPERANZA", "SOCORRO", "AMPARO", "ASUNCION", "CONCEPCION", "ENCARNACION", "PURIFICACION", "VICTORIA",
    "GLORIA", "FE", "CARIDAD", "MERCEDES", "CRUZ", "NIEVES", "SALUD", "AURORA", "ALEGRIA", "PIEDAD", "REYES",
    "BLANCO", "MORENO", "CALVO", "VIVO", "BAÑOS", "MAYOR", "LEAL", "PRIETO", "CANO", "SOLA", "ROMERO",
    "PALACIOS", "FUENTES", "PARRA", "SANTOS", "RUBIO", "DELGADO", "LARGO", "ALEGRE", "BUENO", "BRAVO",
    "CAMPOS", "CASTILLO", "CORDERO", "CUESTA", "FLORES", "GALLEGO", "GRANDE", "HUERTA", "IGLESIAS",
    "LOBO", "MOLINA", "MONTES", "NAVARRO", "PASCUAL", "PEÑA", "PRADO", "RAMOS", "RIOS", "ROJO", "SERRANO",
    "TORRES", "VALLE", "VEGA", "VIDAL", "ALBA", "ARROYO", "BARRANCO", "CABALLERO", "CAMPO", "CARMEN",
    "CORRAL", "ESPINOSA", "GARRIDO", "HERRERO", "LUNA", "MEDINA", "MIRANDA", "MOYA", "OLIVA", "PALOMO",
    "PASTOR", "PINO", "PUERTO", "REY", "RICO", "ROCA", "SANZ", "SOLER", "TORO", "VERA", "VICENTE", "ESTRELLA",
    "MILAGROS", "VIRTUDES", "CONSOLACION", "SOLEDAD", "PRESENTACION", "MAYO", "ABRIL", "MARZO",
}


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    """Para comparar: mayúsculas, sin tildes, espacios simples."""
    return re.sub(r"\s+", " ", sin_tildes(s or "").upper()).strip()


def compacto(s):
    """Sin tildes, mayúsculas, sin espacios, puntos, guiones ni barras."""
    return re.sub(r"[\s.\-/_,:;()]", "", sin_tildes(s or "").upper())


_VARIANTES = {"A": "AÁÀ", "E": "EÉÈ", "I": "IÍÌ", "O": "OÓÒ", "U": "UÚÜÙ", "N": "NÑ", "C": "CÇ"}


def patron_texto(t):
    """Patrón tolerante a tildes, mayúsculas, espacios y signos entre palabras."""
    trozos = []
    for palabra in re.split(r"[\s,]+", sin_tildes(t).strip()):
        if not palabra:
            continue
        p = ""
        for ch in palabra:
            v = _VARIANTES.get(ch.upper())
            if v:
                p += "[" + v + v.lower() + "]"
            elif ch.isalpha():
                p += "[" + ch.upper() + ch.lower() + "]"
            else:
                p += re.escape(ch)
        trozos.append(p)
    if not trozos:
        return None
    return SIN_LETRA_ANTES + r"[\s,.\-]{1,3}".join(trozos) + SIN_LETRA_DESPUES


def patron_digitos(d, separadores=True):
    """Patrón para un número: admite espacios/puntos/guiones entre las cifras si separadores."""
    d = re.sub(r"\s", "", d)
    sep = r"[\s.\-/]?" if separadores else ""
    return r"(?<![0-9A-Za-z])" + sep.join(re.escape(c) for c in d) + r"(?![0-9A-Za-z])"


class Anonimizador:
    def __init__(self, informe, directorio=(), ocultar=(), no_son_nombres=()):
        self.inf = informe
        self.c = informe["cabecera"]
        self.directorio = [x for x in directorio if x and x.strip()]
        self.ocultar = [x for x in ocultar if x and x.strip()]
        self.no_son = {norm(x) for x in no_son_nombres if x and x.strip()}
        self.cuenta = {}
        self.avisos = []
        self.bloqueos = []

    # ------------------------------------------------------------------
    # Qué identifica a este informe
    # ------------------------------------------------------------------
    def nombres_paciente(self):
        c = self.c
        partes = []
        for k in ("nombre", "apellido1", "apellido2"):
            partes += [p for p in re.split(r"[\s\-]+", c.get(k) or "") if p]
        frases = []
        n, a1, a2 = c.get("nombre", ""), c.get("apellido1", ""), c.get("apellido2", "")
        for f in (f"{n} {a1} {a2}", f"{a1} {a2} {n}", f"{a1} {a2}", f"{n} {a1}", f"{a1}, {n}", f"{a1} {a2}, {n}"):
            if len(f.replace(",", "").split()) >= 2:
                frases.append(f)
        sueltas = [p for p in partes if len(p) >= 3 and norm(p) not in PARTICULAS]
        return frases, sueltas

    def profesionales(self):
        """Nombres de profesionales de este informe + directorio + lista manual."""
        nombres = list(self.inf["firma"]["nombres"])
        pie = self.inf["pie"]
        nombres += [pie.get("enfermera", ""), pie.get("medico", "")]
        return [n for n in nombres if n and n.strip()]

    @staticmethod
    def variantes_nombre(nombre):
        """'Apellido1 Apellido2, Nombre' -> frases a buscar + apellidos sueltos."""
        nombre = re.sub(r"\s+", " ", nombre.strip(" ,/"))
        frases = {nombre}
        if "," in nombre:  # "Apellidos, Nombre"
            ap, no = [x.strip() for x in nombre.split(",", 1)]
            frases |= {f"{no} {ap}", ap}
            palabras = ap.split() + no.split()
        else:  # el orden no es fiable ("NOMBRE APELLIDOS" o "Apellidos Nombre")
            palabras = nombre.split()
        # todas las parejas de palabras seguidas
        for f in list(frases):
            p = f.split()
            frases |= {" ".join(p[i:i + 2]) for i in range(len(p) - 1)}
        frases = {f for f in frases if len(f.split()) >= 2 and not all(norm(w) in PARTICULAS for w in f.split())}
        sueltos = [a for a in palabras if len(a) >= 4 and norm(a) not in PARTICULAS]
        return sorted(frases, key=len, reverse=True), sueltos

    def identificadores_numericos(self):
        c = self.c
        ids = {}
        for k, etq in (("nhc", "NHC"), ("dni", "DNI"), ("cip_sns", "CIP"), ("cip_carm", "CIP"),
                       ("nss", "Nº SS"), ("acto", "Nº EPISODIO"), ("cama", "CAMA")):
            v = (c.get(k) or "").strip(" /")
            if v:
                ids[v] = etq
        for t in c.get("telefonos", []):
            ids[t] = "TELÉFONO"
        if c.get("dni"):
            num = re.sub(r"[^0-9]", "", c["dni"])
            if len(num) >= 7:
                ids[num] = "DNI"
        if c.get("nss"):
            num = re.sub(r"[^0-9]", "", c["nss"])
            ids[num] = "Nº SS"
            if len(num) > 10:
                ids[num[2:]] = "Nº SS"
        for col in self.inf["firma"]["colegiados"]:
            ids[col] = "Nº COLEGIADO"
        return ids

    def lugares(self):
        c = self.c
        dom = (c.get("domicilio") or "").strip()
        frases = []
        if dom:
            frases.append((dom, "DOMICILIO"))
            calle = re.sub(r"^(C/|Calle|Cl\.?|Avda\.?|Avenida|Plaza|Pza\.?|Paseo|Camino|Carril|Ctra\.?|Carretera|Urb\.?|Urbanizaci[oó]n|Barrio|Bº)\s+", "", dom, flags=re.I)
            calle = re.split(r",|\s\d", calle)[0].strip()
            if len(calle.split()) >= 2 or (len(calle) >= 6 and norm(calle) not in PALABRAS_CORRIENTES):
                frases.append((calle, "DOMICILIO"))
        loc = (c.get("localidad") or "").strip()
        if loc:
            frases.append((loc, "LOCALIDAD"))
            m = re.match(r"(.+?)\s*\((L[ao]s?|El|La)\)$", loc, re.I)  # "Garres (Los)" -> "Los Garres"
            if m:
                frases += [(f"{m.group(2)} {m.group(1)}", "LOCALIDAD"), (m.group(1), "LOCALIDAD")]
        centro = (self.inf["pie"].get("centro") or "").strip()
        if centro:
            frases.append((centro, "CENTRO DE SALUD"))
            base = re.split(r",", centro)[0].strip()
            if base and base != centro:
                frases.append((base, "CENTRO DE SALUD"))
        return frases

    # ------------------------------------------------------------------
    # Sustitución (nunca toca lo que ya es una [ETIQUETA])
    # ------------------------------------------------------------------
    def _sub(self, texto, patron, etiqueta, filtro=None, flags=0, grupo=0):
        rx = re.compile(patron, flags) if isinstance(patron, str) else patron
        trozos = RE_ETIQUETA.split(texto)
        etiquetas = RE_ETIQUETA.findall(texto)

        def rep(m):
            if filtro and not filtro(m):
                return m.group(0)
            self.cuenta[etiqueta] = self.cuenta.get(etiqueta, 0) + 1
            if grupo:
                return m.group(0)[:m.start(grupo) - m.start(0)] + f"[{etiqueta}]" + m.group(0)[m.end(grupo) - m.start(0):]
            return f"[{etiqueta}]"

        out = []
        for i, t in enumerate(trozos):
            out.append(rx.sub(rep, t))
            if i < len(etiquetas):
                out.append(etiquetas[i])
        return "".join(out)

    @staticmethod
    def _con_mayuscula(m):
        s = m.group(0).strip()
        return bool(s) and s[0].isupper() and not en_titulo_seccion(m)

    def anonimizar(self, texto):
        t = RE_HUELLA_GLOBAL.sub("", texto)
        # 0. Correos electrónicos (antes que los nombres, que podrían ir dentro)
        t = self._sub(t, RE_CORREO, "CORREO")
        # 1. Identificadores numéricos de este paciente (también con espacios/puntos en medio)
        for v, etq in sorted(self.identificadores_numericos().items(), key=lambda x: -len(x[0])):
            cifras = re.sub(r"[^0-9A-Za-z]", "", v)
            separadores = len(re.sub(r"\D", "", cifras)) >= 8
            t = self._sub(t, patron_digitos(cifras, separadores), etq)
            if v != cifras:
                t = self._sub(t, re.escape(v), etq)
        # 2. Nombre del paciente: frases completas (cualquier forma) y partes con mayúscula
        frases, sueltas = self.nombres_paciente()
        for f in sorted(frases, key=len, reverse=True):
            p = patron_texto(f)
            if p:
                t = self._sub(t, p, "PACIENTE")
        for s in sorted(sueltas, key=len, reverse=True):
            if norm(s) in PALABRAS_CORRIENTES:
                continue
            t = self._sub(t, patron_texto(s), "PACIENTE", filtro=self._con_mayuscula)
        # 3. Domicilio, localidad y centro de salud
        for f, etq in sorted(self.lugares(), key=lambda x: -len(x[0])):
            p = patron_texto(f)
            if p:
                t = self._sub(t, p, etq, filtro=None if len(f.split()) >= 2 else self._con_mayuscula)
        # 4. Profesionales (de este informe, del directorio y de la lista manual)
        nombres = self.profesionales() + self.directorio
        sueltos_prof = set()
        frases_prof = set()
        for n in nombres:
            fr, su = self.variantes_nombre(n)
            frases_prof |= set(fr)
            sueltos_prof |= set(su)
        for f in sorted(frases_prof, key=len, reverse=True):
            t = self._sub(t, patron_texto(f), "PROFESIONAL")
        for s in sorted(sueltos_prof, key=len, reverse=True):
            if norm(s) in PALABRAS_CORRIENTES or norm(s) in self.no_son:
                continue
            t = self._sub(t, patron_texto(s), "PROFESIONAL", filtro=self._con_mayuscula)
        # 5. Lista manual "ocultar_tambien.txt"
        for f in sorted(self.ocultar, key=len, reverse=True):
            p = patron_texto(f)
            if p:
                t = self._sub(t, p, "PERSONA", filtro=None if len(f.split()) >= 2 else self._con_mayuscula)
        # 6. Patrones generales
        for rx, etq, grupo in PATRONES_GENERALES:
            t = self._sub(t, rx, etq, grupo=grupo)
        return t

    # ------------------------------------------------------------------
    # Doble control y avisos
    # ------------------------------------------------------------------
    def controlar(self, texto):
        bloqueos, avisos = [], []
        comp = compacto(texto)
        normal = norm(texto)
        # a) Ningún identificador numérico, ni siquiera con separadores
        for v, etq in self.identificadores_numericos().items():
            cv = compacto(v)
            if len(cv) >= 8:
                if cv in comp:
                    bloqueos.append(f"Sigue apareciendo un identificador ({etq}).")
            elif re.search(r"(?<![0-9A-Z])" + re.escape(cv) + r"(?![0-9A-Z])", re.sub(r"[.\-/]", "", normal)):
                bloqueos.append(f"Sigue apareciendo un identificador ({etq}).")
        # b) Nombre completo y apellidos del paciente
        frases, sueltas = self.nombres_paciente()
        for f in frases:
            if re.search(patron_texto(f), texto):
                bloqueos.append("Sigue apareciendo el nombre del paciente.")
        for s in sueltas:
            for m in re.finditer(patron_texto(s), texto):
                if en_titulo_seccion(m):
                    continue
                if norm(s) in PALABRAS_CORRIENTES or not m.group(0)[0].isupper():
                    avisos.append(("Palabra que coincide con un nombre o apellido del paciente", _contexto(texto, m)))
                else:
                    bloqueos.append("Sigue apareciendo un nombre o apellido del paciente.")
            # partido entre dos líneas ("GAR-\nCIA" o "GAR\nCIA")
            if len(s) >= 5:
                unido = compacto(re.sub(r"-?\n\s*", "", texto))
                n_unido = unido.count(compacto(s))
                n_normal = len(re.findall(patron_texto(s), texto))
                if n_unido > n_normal and compacto(s) not in compacto(" ".join(PALABRAS_CORRIENTES)):
                    avisos.append(("Posible apellido del paciente partido entre dos líneas", s[:2] + "…"))
        # c) Domicilio y profesionales de este informe
        for f, etq in self.lugares():
            if len(f.split()) >= 2 and re.search(patron_texto(f), texto):
                bloqueos.append(f"Sigue apareciendo un dato de {etq.lower()}.")
        for n in self.profesionales():
            fr, _ = self.variantes_nombre(n)
            if any(re.search(patron_texto(f), texto) for f in fr):
                bloqueos.append("Sigue apareciendo el nombre de un profesional.")
        # d) Restos de cabecera, pie o código del documento
        if RE_HUELLA_GLOBAL.search(texto):
            bloqueos.append("Sigue apareciendo el código del documento.")
        for patron, motivo in RESTOS_CABECERA:
            if re.search(patron, texto):
                bloqueos.append(motivo)
        # e) Posibles nombres que nadie ha confirmado
        for rx, motivo in PATRONES_AVISO:
            for m in rx.finditer(texto):
                palabras = [w for w in re.findall(rf"[{LETRA}]+", m.group(1) if m.groups() else m.group(0))]
                if not palabras or all(norm(w) in self.no_son or _es_vocabulario(w) for w in palabras):
                    continue
                avisos.append((motivo, _contexto(texto, m)))
        self.bloqueos = sorted(set(bloqueos))
        vistos, self.avisos = set(), []
        for a in avisos:
            if a not in vistos:
                vistos.add(a)
                self.avisos.append(a)
        return self.bloqueos, self.avisos


def en_titulo_seccion(m):
    """¿La coincidencia está dentro de un título de sección ("RESUMEN PRUEBAS COMPLEMENTARIAS:")?"""
    ini = m.string.rfind("\n", 0, m.start()) + 1
    fin = m.string.find("\n", m.end())
    linea = m.string[ini:fin if fin >= 0 else len(m.string)]
    t = re.match(r"^\s*([^:]+?)\s*:", linea)
    return bool(t) and norm(t.group(1)) in SECCIONES and m.end() <= ini + t.end()


def _contexto(texto, m, ancho=45):
    a, b = max(0, m.start() - ancho), min(len(texto), m.end() + ancho)
    return (("…" if a else "") + texto[a:m.start()] + "⟦" + texto[m.start():m.end()] + "⟧" + texto[m.end():b]
            + ("…" if b < len(texto) else "")).replace("\n", " ")


RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_HUELLA_GLOBAL = re.compile(r"\[\s*[0-9a-fA-F]{32,}\s*\]")

# (patrón, etiqueta, grupo que se sustituye; 0 = todo)
PATRONES_GENERALES = [
    (re.compile(r"(?<![0-9A-Za-z])[XYZxyz][\s.\-]?\d{7}[\s.\-]?[A-Za-z](?![0-9A-Za-z])"), "DNI", 0),
    (re.compile(r"(?<![0-9A-Za-z])\d{8}[\s.\-]?[A-HJ-NP-TV-Za-hj-np-tv-z](?![0-9A-Za-z])"), "DNI", 0),
    (re.compile(r"(?<![0-9A-Za-z])CARM\s*\d{6,}", re.I), "CIP", 0),
    (re.compile(r"(?<![0-9A-Za-z])[A-Z]{4}\d{12}(?![0-9A-Za-z])"), "CIP", 0),
    (re.compile(r"(?<![0-9A-Za-z])[A-Z]{10}\d{6}(?![0-9A-Za-z])"), "CIP", 0),
    (re.compile(r"(?<![\d.,/])(?:\+34[\s.]?)?[6789]\d{2}(?:[\s.]?\d{2}){3}(?![\d.,/])"), "TELÉFONO", 0),
    (re.compile(r"(?<![\d.,/])(?:\+34[\s.]?)?[6789]\d{2}[\s.]?\d{3}[\s.]?\d{3}(?![\d.,/])"), "TELÉFONO", 0),
    (re.compile(r"(?:N\.?\s?H\.?\s?C\.?|historia\s+cl[ií]nica|n[ºo°]\s*de\s*historia)\s*(?:n[ºo°]\.?)?\s*:?\s*(\d{4,})", re.I), "NHC", 1),
    (re.compile(r"(?:N\.?\s?S\.?\s?S\.?|Seguridad\s+Social)\s*:?\s*(\d{2}/?\d{8,10})", re.I), "Nº SS", 1),
    (re.compile(r"Col(?:egiado)?\.?\s*N[º°o]?\.?\s*:?\s*(\d{5,}(?:\s*/\s*\d{5,})*)", re.I), "Nº COLEGIADO", 1),
    # "Dr. García", "Dra. Pérez López", "Dr./Dra. Ruiz", "Sra. Martínez"
    (re.compile(r"\b(?:Dr|Dra|Dres|Doctor|Doctora|Prof|Profa)\.?(?:\s*/\s*Dra\.?)?\s+"
                rf"((?:[A-ZÁÉÍÓÚÑ][{LETRA}]+)(?:[\s,]+(?:de\s+la|de\s+los|del|de|la|y|[A-ZÁÉÍÓÚÑ][{LETRA}]+)){{0,3}})"), "PROFESIONAL", 1),
    (re.compile(r"\b(?:Sr|Sra|Srta|D[ªa]|Dña|Don|Doña)\.?\s+"
                rf"((?:[A-ZÁÉÍÓÚÑ][{LETRA}]+)(?:[\s,]+(?:de\s+la|de\s+los|del|de|la|y|[A-ZÁÉÍÓÚÑ][{LETRA}]+)){{0,3}})"), "PERSONA", 1),
    # Direcciones: "C/ Mayor 12", "Calle Salvador de Madariaga, 7", "Avda. Juan Carlos I nº 3"
    (re.compile(r"\b(?:C/|Calle|Avda\.?|Avenida|Plaza|Pza\.?|Paseo|Camino|Carril|Urb\.|Urbanizaci[oó]n)\s+"
                rf"(?:[A-ZÁÉÍÓÚÑ0-9][{LETRA}0-9ºª]*\.?\s*(?:de\s+la\s+|de\s+los\s+|del\s+|de\s+|la\s+|y\s+)?){{1,6}}"
                r"(?:,?\s*(?:n[ºo°]\.?\s*)?\d+[\w\sºª,/-]{0,12})?"), "DIRECCIÓN", 0),
]

# Restos de la cabecera o el pie que nunca deben quedar
RESTOS_CABECERA = [
    (r"(?i)\bDNI\s*/\s*NIE", "Ha quedado parte de la cabecera (DNI/NIE)."),
    (r"(?i)C\.I\.P\.\s*(?:SNS|A\.)", "Ha quedado parte de la cabecera (C.I.P.)."),
    (r"(?i)Enfermera\s+de\s+A\.\s*Primaria", "Ha quedado parte del pie de página."),
    (r"(?i)\bFdo\s*[:.]\s*Dr", "Ha quedado parte de la firma."),
]

# Posibles nombres que no se pueden confirmar automáticamente -> AVISO para una persona
PATRONES_AVISO = [
    (re.compile(r"\(([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+\s*/\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:\s*/\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)*)\)"),
     "Posibles apellidos entre paréntesis"),
    (re.compile(r"\b(?i:comentad[oa]|hablad[oa]|valorad[oa]|consultad[oa]|vist[oa]|explorad[oa]|intervenid[oa]|operad[oa]|realizad[oa]|informad[oa])\s+"
                r"(?i:con|por)\s+(?i:el\s+|la\s+)?(?:Dr\.?\s+|Dra\.?\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)?)"),
     "Posible nombre de un profesional"),
    (re.compile(r"\b(?i:hij[oa]s?|espos[oa]|marido|mujer|herman[oa]s?|sobrin[oa]s?|niet[oa]s?|nuera|yerno|cuidador[a]?|familiar|vecin[oa])"
                r"(?:\s+\([^)]*\))?[\s,:]+(?:llamad[oa]\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)"),
     "Posible nombre de un familiar"),
    (re.compile(r"\b(?:(?i:residente|adjunt[oa]|enfermer[oa])|R[1-5])\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)"),
     "Posible nombre de un profesional"),
]

# Palabras con mayúscula que son vocabulario clínico/administrativo (no generan aviso)
VOCABULARIO = {norm(x) for x in """
Cardiología Cardiologia Neurología Nefrología Geriatría Urgencias Medicina Interna Cirugía UCI UCIC Hematología Oncología
Digestivo Neumología Endocrino Endocrinología Reumatología Urología Traumatología Dermatología Psiquiatría Rehabilitación
Paliativos Anestesia Radiología Microbiología Infecciosas Nutrición Ginecología Oftalmología ORL Hemodinámica
Electrofisiología Arritmias Trasplante Atención Primaria MAP MI CEX Consultas Enfermería Trabajo Social Unidad Planta
Servicio Equipo Guardia Hospital Centro Salud Domicilio Insuficiencia Cardiaca IC HTA DM FA ECG ETT ETE TAC RMN
Furosemida Seguril Sintrom Eliquis Xarelto Pradaxa Lixiana Entresto Jardiance Forxiga Bisoprolol Carvedilol Digoxina
Amiodarona Trangorex Espironolactona Eplerenona Torasemida Hidroclorotiazida Enalapril Ramipril Losartan Valsartan
Atorvastatina Rosuvastatina Simvastatina Ezetimiba Clopidogrel Ticagrelor Prasugrel Adiro AAS Omeprazol Pantoprazol
Metformina Insulina Lantus Novorapid Sinemet Acovil Cardyl Omnic Hidroferol Paracetamol Nolotil Tramadol Pulmicort
Spiriva Ventolin Symbicort Ultibro Trelegy Dexketoprofeno Enantyum Augmentine Ceftriaxona Levofloxacino Meropenem
Hombre Mujer Paciente Familia Cuidadora Cuidador Geriatra Cardiólogo Cardiologo Nefrólogo Internista Médico Medico
""".split()}


def _es_vocabulario(w):
    n = norm(w)
    return n in VOCABULARIO or n.endswith("LOGIA") or n.endswith("LOGO") or n.endswith("LOGA") or len(n) <= 2


def anonimizar_informe(informe, directorio=(), ocultar=(), no_son_nombres=()):
    """Devuelve dict con texto anonimizado, cuenta de sustituciones, bloqueos y avisos."""
    a = Anonimizador(informe, directorio, ocultar, no_son_nombres)
    texto = "\n".join(informe["cuerpo"])
    anon = a.anonimizar(texto)
    bloqueos, avisos = a.controlar(anon)
    return {"texto": anon, "sustituciones": dict(sorted(a.cuenta.items())), "bloqueos": bloqueos, "avisos": avisos}


# Encabezados de sección del informe de alta (para separar el texto en apartados)
SECCIONES = ["MOTIVO DE INGRESO", "TIPO DE INGRESO", "ANTECEDENTES", "ANTECEDENTES PERSONALES", "HISTORIA ACTUAL",
             "ENFERMEDAD ACTUAL", "ANAMNESIS", "EXPLORACION FISICA", "RESUMEN PRUEBAS COMPLEMENTARIAS",
             "PRUEBAS COMPLEMENTARIAS", "EXPLORACIONES EN PLANTA", "EXPLORACIONES COMPLEMENTARIAS", "MICROBIOLOGIA",
             "EVOLUCION Y COMENTARIOS", "EVOLUCION", "JUICIO CLINICO", "DIAGNOSTICO PRINCIPAL", "OTROS DIAGNOSTICOS",
             "DIAGNOSTICOS SECUNDARIOS", "DIAGNOSTICOS", "PROCEDIMIENTOS", "TRATAMIENTO", "TRATAMIENTO AL ALTA",
             "OTRAS RECOMENDACIONES", "RECOMENDACIONES", "MOTIVO DE ALTA"]


def separar_secciones(texto):
    secciones = [{"titulo": "", "texto": []}]
    for ln in texto.split("\n"):
        m = re.match(r"^\s*([A-ZÁÉÍÓÚÑa-záéíóúñ .]+?)\s*:\s*(.*)$", ln)
        if m and norm(m.group(1)) in SECCIONES and m.group(1).strip() == m.group(1).strip().upper():
            secciones.append({"titulo": m.group(1).strip(), "texto": [m.group(2)] if m.group(2).strip() else []})
        else:
            secciones[-1]["texto"].append(ln)
    out = []
    for s in secciones:
        txt = "\n".join(s["texto"]).strip()
        if s["titulo"] or txt:
            out.append({"titulo": s["titulo"] or "(inicio)", "texto": txt})
    return out
