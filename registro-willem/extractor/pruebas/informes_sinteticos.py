"""
Genera informes de alta INVENTADOS en PDF con la misma maqueta que los del SMS
(cabecera con casillas, cuerpo, firma y pie), para probar el extractor sin datos reales.
Escritor de PDF mínimo: solo biblioteca estándar.
"""
import os

HOSPITAL = ["Hospital Clínico", "Universitario Virgen", "de la Arrixaca", "Ctra. Madrid – Cartagena",
            "30120 El Palmar (Murcia)", "Telf. 968 36 95 00"]


def _esc(t):
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _texto(x, y, t, tam=8, girado=False):
    m = "0 1 -1 0" if girado else "1 0 0 1"
    return f"BT /F1 {tam} Tf {m} {x:.1f} {y:.1f} Tm ({_esc(t)}) Tj ET\n"


def escribir_pdf(ruta, paginas):
    """paginas: lista de listas de (x, y, texto[, tam[, girado]])."""
    objetos = []

    def nuevo(contenido):
        objetos.append(contenido)
        return len(objetos)

    fuente = nuevo(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    raiz_pags = len(objetos) + 1
    objetos.append(None)  # se rellena al final
    hijos = []
    for elems in paginas:
        flujo = "".join(_texto(*e) for e in elems).encode("cp1252")
        c = nuevo(b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream")
        p = nuevo(f"<< /Type /Page /Parent {raiz_pags} 0 R /MediaBox [0 0 595.28 841.88] "
                  f"/Resources << /Font << /F1 {fuente} 0 R >> >> /Contents {c} 0 R >>".encode())
        hijos.append(p)
    objetos[raiz_pags - 1] = f"<< /Type /Pages /Kids [{' '.join(f'{h} 0 R' for h in hijos)}] /Count {len(hijos)} >>".encode()
    catalogo = nuevo(f"<< /Type /Catalog /Pages {raiz_pags} 0 R >>".encode())
    out = bytearray(b"%PDF-1.4\n")
    pos = []
    for i, o in enumerate(objetos, 1):
        pos.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{p:010d} 00000 n \n" for p in pos).encode()
    out += f"trailer\n<< /Size {len(objetos) + 1} /Root {catalogo} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(ruta, "wb") as f:
        f.write(out)


def cabecera(p, pag, total):
    """Elementos de la cabecera con la disposición de los informes del SMS."""
    e = []
    filas = [("N.H.C.", p["nhc"], "DNI/NIE/PPTE", p["dni"] + "/"),
             ("Nombre", p["nombre"], "Servicio", p["servicio"]),
             ("1ªApellido", p["ap1"], "Nº Cama", p["cama"]),
             ("2º Apellido", p["ap2"], "F. Ingreso", p["ingreso"]),
             ("Sexo", p["sexo"], "F. Alta", p["alta"]),
             ("F.Nacim(Edad)", p["nac"], "Nº Acto", p["acto"])]
    y = 799.2
    for li, vi, ld, vd in filas:
        e += [(132.9, y, li), (192.6, y, vi), (296.8, y, ld), (356.5, y, vd)]
        y -= 16.5
    # teléfonos (dos líneas), domicilio y población (dos líneas)
    tels = p["telefonos"]
    e += [(192.6, 700.3, " ".join(tels[:2])), (132.9, 695.4, "Teléfono"), (296.8, 695.4, "N.S.S."), (356.5, 695.4, p["nss"])]
    if len(tels) > 2:
        e.append((192.6, 690.5, " ".join(tels[2:])))
    e.append((68.1, 685.6, f"Pág {pag} de {total}"))
    d1, d2 = p["domicilio"]
    o1, o2 = p["poblacion"]
    e += [(192.6, 674.0, d1), (132.9, 669.1, "Domicilio"), (192.6, 664.2, d2),
          (296.8, 669.1, "Población"), (356.5, 674.0, o1), (356.5, 664.2, o2),
          (132.9, 647.7, "C.I.P.SNS"), (192.6, 647.7, p["cip_sns"]), (296.8, 647.7, "C.I.P.A."), (356.5, 647.7, p["carm"]),
          (132.9, 631.2, "Financiación"), (192.6, 631.2, "_Seguridad Social"), (296.8, 631.2, "Patología")]
    y = 715.8
    for h in HOSPITAL:
        e.append((470.0, y, h))
        y -= 11.8
    e.append((20.0, 300.0, "[" + p["huella"] + "]", 6, True))  # código lateral girado
    return e


def pie(p):
    return [(47.2, 56.6, "Centro de Salud:"), (173.0, 56.6, "Enfermera de A. Primaria:"), (347.2, 56.6, "Médico de A. Primaria:"),
            (47.2, 43.7, p["centro"]), (173.0, 43.7, p["enfermera"]), (347.2, 43.7, p["medico"])]


def informe(ruta, p, cuerpo, firma, lineas_por_pagina=40):
    """cuerpo: lista de líneas; firma: lista de líneas (alineadas a la derecha)."""
    trozos = [cuerpo[i:i + lineas_por_pagina] for i in range(0, max(len(cuerpo), 1), lineas_por_pagina)]
    total = len(trozos)
    paginas = []
    for n, trozo in enumerate(trozos, 1):
        e = cabecera(p, n, total)
        y = 564.3
        if n == 1:
            e.append((157.2, 598.6, "INFORME CLÍNICO DE ALTA"))
        else:
            y = 615.0
        for ln in trozo:
            if ln:
                e.append((45.3, y, ln))
            y -= 12.3
        if n == total:
            y -= 12
            for ln in firma:
                e.append((380.0, y, ln))
                y -= 11
        e += pie(p)
        paginas.append(e)
    escribir_pdf(ruta, paginas)


def paciente(**k):
    base = dict(nhc="100001", dni="12345678Z", nombre="ANTONIO", ap1="PRUEBAS", ap2="FICTICIO", servicio="Cardiología",
                cama="HG-101-1", ingreso="10/01/2025 10:00", alta="15/01/2025 12:00", sexo="Hombre",
                nac="02/02/1950 (74 Años)", acto="25-1000001", telefonos=["611223344", "968000111"],
                nss="30/1234567890", domicilio=("Calle ALAMEDA DE LOS", "INVENTADOS, 12"),
                poblacion=("30999 Villaprueba del", "Monte, Murcia"), cip_sns="AAAAAAAAAA100001",
                carm="CARM100000000001", huella="ab" * 32, centro="Villaprueba, Cons.",
                enfermera="LUCRECIA ZARZALEJO OYAMBRE", medico="TEODORO QUINTANAR ALBORNOZ")
    base.update(k)
    return base


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(d, exist_ok=True)
    informe(os.path.join(d, "ejemplo.pdf"), paciente(), ["MOTIVO DE INGRESO:", "Disnea", "", "MOTIVO DE ALTA:", "Mejoría"],
            ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo", "Col. Nº.: 30999999", "Fecha: 15/01/2025"])
    print("ok")
