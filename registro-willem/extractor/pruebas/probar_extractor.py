#!/usr/bin/env python3
"""
Pruebas del extractor (fase 1) con informes INVENTADOS.

    python3 extractor/pruebas/probar_extractor.py

Comprueba: lectura de cabecera, libro llave (mismo paciente = mismo caso), duplicados,
bloqueos, avisos, y sobre todo que NINGÚN identificador llega a la carpeta compartida.
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))

import informes_sinteticos as S  # noqa: E402
from leer_pdf import leer_informe  # noqa: E402
from procesar_informes import buscar_pdfs, procesar  # noqa: E402

FALLOS = []


def ok(c, msg):
    print(("  ✓ " if c else "  ✗ ") + msg)
    if not c:
        FALLOS.append(msg)


def n(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper()


FIRMA2 = ["Fdo: Dr./Dra. Zubizarreta Montesclaros, Eulalia", "/Berenguela Otxoa Casimira", "Col. Nº.: 30111222/3022233", "13-5-25"]
CUERPO1 = [
    "MOTIVO DE INGRESO:", "Disnea de esfuerzo progresiva.", "",
    "ANTECEDENTES:",
    "FRCV: HTA. DM2. Dislipemia. Exfumador.",
    "El paciente Antonio Pruebas Ficticio vive en Calle Alameda de los Inventados, 12 de Villaprueba del Monte.",
    "Teléfono de contacto de su hija: 622 33 44 55. Su DNI 12345678Z consta en la historia.",
    "Otro contacto 699.88.77.66; correo pruebas.ficticio@correo.es. NHC: 100001.",
    "Comentado con Dr. Hermenegildo Valcárcel, que valora el caso. Seguimiento por la Dra. Zubizarreta.",
    "En 2019 se realiza recambio valvular (Arcedo /Gañanez) sin incidencias.",
    "Hija Lucinda acompaña al paciente. Valorado por Cardiología.",
    "Antecedente de ingreso en Villaprueba, Cons. de referencia; CIP CARM100000000001.",
    "", "EXPLORACIÓN FÍSICA:", "TA: 130/80 mmHg; FC: 72 lpm; Sat.O2: 96 %.", "",
    "RESUMEN PRUEBAS COMPLEMENTARIAS:",
    "Ecocardiograma (05/01/2025): FEVI 38 %. DTDVI 58 mm. Septo 11 mm. Pared posterior 10 mm. Strain -12 %.",
    "NT-proBNP: 3500 pg/mL. Plaquetas: 611.2 10e3/uL. Leucocitos: 9.68 10e3/uL.",
    "", "EVOLUCIÓN Y COMENTARIOS:", "Buena evolución con diuréticos. Dolores torácicos atípicos resueltos.", "",
    "DIAGNÓSTICO PRINCIPAL:", "Insuficiencia cardiaca con FEVI reducida.", "",
    "TRATAMIENTO:", "Furosemida 40 mg 1-0-0. Bisoprolol 2,5 mg 1-0-0.", "",
    "MOTIVO DE ALTA:", "Mejoría",
] + ["Línea de relleno clínico sin datos personales."] * 30


def main():
    tmp = tempfile.mkdtemp(prefix="willem_prueba_")
    usb, priv, sal = (os.path.join(tmp, x) for x in ("usb", "privado", "anonimizado"))
    os.makedirs(usb)
    p1 = S.paciente()
    # 1. Paciente con muchas trampas en el texto, 2 páginas, dos firmantes
    S.informe(os.path.join(usb, "01_PRUEBAS_FICTICIO_alta.pdf"), p1, CUERPO1, FIRMA2)
    # 2. Mismo paciente, reingreso (otro episodio, mismo CARM)
    S.informe(os.path.join(usb, "02_reingreso.pdf"), S.paciente(ingreso="03/06/2025 09:00", alta="09/06/2025 13:00", acto="25-1000099", cama="HG-222-1"),
              ["MOTIVO DE INGRESO:", "Insuficiencia cardiaca descompensada.", "", "MOTIVO DE ALTA:", "Mejoría"],
              ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo", "Col. Nº.: 30999999", "Fecha: 09/06/2025"])
    # 3. El mismo PDF copiado con otro nombre
    shutil.copy(os.path.join(usb, "01_PRUEBAS_FICTICIO_alta.pdf"), os.path.join(usb, "03_copia.pdf"))
    # 4. Sin CIP autonómico
    S.informe(os.path.join(usb, "04_sin_carm.pdf"), S.paciente(nhc="100004", carm="", cip_sns="AAAAAAAAAA100004", dni="87654321X"),
              ["MOTIVO DE INGRESO:", "Disnea"], ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo"])
    # 4b. El mismo paciente sin CARM reingresa y ahora sí trae CARM (mismo NHC)
    S.informe(os.path.join(usb, "04b_con_carm.pdf"), S.paciente(nhc="100004", carm="CARM100000000004", cip_sns="AAAAAAAAAA100004", dni="87654321X",
              ingreso="01/09/2025 10:00", alta="05/09/2025 10:00", acto="25-1000044"), ["MOTIVO DE INGRESO:", "Disnea"], ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo"])
    # 4c. Sin ninguna clave (ni CARM, ni CIP, ni NHC, ni DNI)
    S.informe(os.path.join(usb, "04c_sin_claves.pdf"), S.paciente(nhc="", carm="", cip_sns="", dni=""), ["MOTIVO DE INGRESO:", "Disnea"], ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo"])
    # 4d. Mismo NHC que el paciente 1 pero otro CARM: no cuadra -> bloqueado
    S.informe(os.path.join(usb, "04d_conflicto.pdf"), S.paciente(carm="CARM100000000099", cip_sns="AAAAAAAAAA100099", dni="99999999R"),
              ["MOTIVO DE INGRESO:", "Disnea"], ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo"])
    # 5. Páginas de dos pacientes en el mismo PDF
    pa, pb = S.paciente(nhc="100005", carm="CARM100000000005"), S.paciente(nhc="100006", carm="CARM100000000006", nombre="OTRO")
    S.escribir_pdf(os.path.join(usb, "05_mezclado.pdf"), [S.cabecera(pa, 1, 2) + S.pie(pa), S.cabecera(pb, 2, 2) + S.pie(pb)])
    # 6. PDF sin texto (como un escaneo)
    S.escribir_pdf(os.path.join(usb, "06_escaneado.pdf"), [[]])
    # 7. No es un PDF
    with open(os.path.join(usb, "07_roto.pdf"), "wb") as f:
        f.write(b"esto no es un pdf")
    # 8. Resto del Mac en USB (debe ignorarse)
    shutil.copy(os.path.join(usb, "02_reingreso.pdf"), os.path.join(usb, "._02_reingreso.pdf"))
    # 9. Paciente llamada DOLORES, nombre compuesto, apellido partido entre líneas
    p9 = S.paciente(nhc="100009", carm="CARM100000000009", cip_sns="AAAAAAAAAA100009", dni="11223344B", nombre="MARIA DOLORES",
                    ap1="DE LA FUENTEVIEJA", ap2="SOL", sexo="Mujer", telefonos=["677889900"], acto="25-1000009",
                    domicilio=("Avda. LOS ALMENDROS", "PRUEBA, 4"), poblacion=("30998 Otropueblo,", "Murcia"))
    S.informe(os.path.join(usb, "09_dolores.pdf"), p9,
              ["MOTIVO DE INGRESO:", "Dolores torácicos opresivos.", "", "ANTECEDENTES:",
               "La Sra. Fuentevieja refiere dolor. Doña María Dolores vive sola en Otropueblo.",
               "Hermana Fuente", "vieja colabora en los cuidados.", "", "MOTIVO DE ALTA:", "Mejoría"],
              ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo", "Col. Nº.: 30999999", "Fecha: 15/01/2025"])

    print("\n1) Lectura de la cabecera")
    c = leer_informe(os.path.join(usb, "01_PRUEBAS_FICTICIO_alta.pdf"))["cabecera"]
    esperado = {"nhc": "100001", "dni": "12345678Z", "nombre": "ANTONIO", "apellido1": "PRUEBAS", "apellido2": "FICTICIO",
                "cip_carm": "CARM100000000001", "cip_sns": "AAAAAAAAAA100001", "fecha_nacimiento": "1950-02-02", "edad": 74,
                "fecha_ingreso": "2025-01-10", "fecha_alta": "2025-01-15", "telefonos": ["611223344", "968000111"],
                "domicilio": "Calle ALAMEDA DE LOS INVENTADOS, 12", "localidad": "Villaprueba del Monte", "cp": "30999",
                "sexo": "Hombre", "servicio": "Cardiología", "acto": "25-1000001"}
    for k, v in esperado.items():
        ok(c.get(k) == v, f"cabecera · {k} = {v!r}" + ("" if c.get(k) == v else f" (leído {c.get(k)!r})"))
    f9 = leer_informe(os.path.join(usb, "09_dolores.pdf"))
    ok(f9["cabecera"]["nombre"] == "MARIA DOLORES" and f9["cabecera"]["apellido1"] == "DE LA FUENTEVIEJA", "nombre y apellido compuestos")
    f1 = leer_informe(os.path.join(usb, "01_PRUEBAS_FICTICIO_alta.pdf"))
    ok(f1["paginas"] == 2, "informe de 2 páginas leído entero")
    ok(f1["firma"]["nombres"] == ["Zubizarreta Montesclaros, Eulalia", "Berenguela Otxoa Casimira"], "dos firmantes reconocidos")
    ok(f1["firma"]["colegiados"] == ["30111222", "3022233"], "dos números de colegiado")

    print("\n2) Proceso completo")
    pdfs = buscar_pdfs([usb])
    ok(not any(os.path.basename(p).startswith("._") for p in pdfs), "se ignoran los restos '._' del Mac")
    res, llave = procesar(pdfs, priv, sal)
    R = {r["archivo"][:2]: r for r in res if r["archivo"][2] == "_"}
    ok(R["01"]["numero"] == R["02"]["numero"] == R["03"]["numero"] == 1, "mismo paciente (reingreso y copia) = mismo caso")
    ok(R["01"]["nuevo"] and not R["02"]["nuevo"], "el reingreso no crea un caso nuevo")
    ok(R["09"]["numero"] == 3, "paciente distinto = caso nuevo")
    ok(R["03"]["repetido"], "la copia se reconoce como ya procesada")
    R.update({r["archivo"][:3]: r for r in res if r["archivo"][2] in "bcd"})
    ok(R["04"]["estado"] != "bloqueado" and R["04"]["sin_carm"] and R["04"]["numero"] == 2, "sin CARM: se enlaza por NHC/DNI (caso 2)")
    ok(R["04b"]["numero"] == 2 and not R["04b"]["nuevo"], "reingreso del paciente sin CARM, ahora con CARM: mismo caso")
    for k, motivo in (("04c", "ni DNI"), ("04d", "no cuadra"), ("05", "más de un paciente"), ("06", "no contiene texto"), ("07", "No se ha podido abrir")):
        ok(R[k]["estado"] == "bloqueado" and any(motivo in b for b in R[k]["bloqueos"]), f"bloqueado {k}: {motivo}")
    ok(R["02"]["estado"] == "listo", "reingreso sin trampas: listo")
    ok(R["01"]["estado"] == "revisar", "informe con posibles nombres: va a revisar")
    motivos = " | ".join(m + " " + x for m, x in R["01"]["avisos"])
    ok("Arcedo" in motivos, "aviso: apellidos entre paréntesis (Arcedo /Gañanez)")
    ok("Lucinda" in motivos, "aviso: nombre de un familiar (Hija Lucinda)")
    ok(R["09"]["estado"] != "bloqueado", "paciente DOLORES no bloqueado")
    ok(any("partido" in m for m, _ in R["09"]["avisos"]), "aviso: apellido partido entre dos líneas")
    t1 = R["01"]["texto"]
    for frag in ("[PACIENTE]", "[TELÉFONO]", "[DNI]", "[CORREO]", "[NHC]", "[CIP]", "[PROFESIONAL]", "[DOMICILIO]", "[LOCALIDAD]", "[CENTRO DE SALUD]"):
        ok(frag in t1, f"sustituido en el texto: {frag}")
    ok("Dr. [PROFESIONAL]" in t1 and "Dra. [PROFESIONAL]" in t1, "'Dr. Hermenegildo Valcárcel' y 'Dra. Zubizarreta' sustituidos")
    ok("FEVI 38 %" in t1 and "611.2 10e3/uL" in t1 and "05/01/2025" in t1, "se conservan datos clínicos, cifras de laboratorio y fechas")
    t9 = R["09"]["texto"]
    ok("RESUMEN PRUEBAS COMPLEMENTARIAS:" in t1, "los títulos de sección no se tocan aunque coincidan con un apellido (PRUEBAS)")
    ok("Dolores torácicos" in t9, "'Dolores torácicos' no se confunde con el nombre de la paciente")
    ok("Fuentevieja" not in t9 and "Otropueblo" not in t9, "apellido y localidad de la paciente sustituidos")

    print("\n3) Ningún identificador en la carpeta compartida (comprobación independiente)")
    compartido = ""
    for f in glob.glob(os.path.join(sal, "**", "*"), recursive=True):
        if os.path.isfile(f):
            compartido += open(f, encoding="utf-8").read() + "\n" + os.path.basename(f) + "\n"
    T = n(compartido)
    Tc = re.sub(r"[\s.\-/]", "", T)
    prohibido = []
    for p in (p1, p9, S.paciente(nhc="100004", carm="CARM100000000004", cip_sns="AAAAAAAAAA100004", dni="87654321X")):
        prohibido += [p["nhc"], p["dni"], p["cip_sns"], p["carm"], p["nss"], p["acto"], p["cama"], *p["telefonos"]]
        prohibido += [w for w in re.split(r"[\s,]+", " ".join([p["nombre"], p["ap1"], p["ap2"], *p["domicilio"], p["poblacion"][0],
                                                             p["enfermera"], p["medico"]])) if len(w) >= 5 and n(w) not in {"MARIA", "DOLORES", "MURCIA", "CALLE", "AVDA."}]
    prohibido += ["Zubizarreta", "Montesclaros", "Eulalia", "Berenguela", "Casimira", "Hermenegildo", "Valcárcel", "622334455",
                  "699887766", "pruebas.ficticio", "30111222", "Rosendo", "PRUEBAS", "FICTICIO", "01_PRUEBAS", p1["huella"]]
    fugas = []
    for v in prohibido:
        w = n(v)
        if re.search(r"(?<![A-Z0-9])" + re.escape(w) + r"(?![A-Z0-9])", T) or (len(w) >= 8 and re.sub(r"[\s.\-/]", "", w) in Tc):
            fugas.append(v)
    ok(not fugas, "ningún dato identificativo en la carpeta compartida" + (f" — FUGAS: {fugas}" if fugas else ""))
    ok(not [x for x in glob.glob(os.path.join(sal, "**", "*"), recursive=True) if "PRUEBAS" in x or x.endswith(".pdf")], "los nombres de archivo originales no se copian")
    listos = sorted(os.path.basename(x) for x in glob.glob(os.path.join(sal, "listos", "*.json")))
    ok(listos == ["caso_0001_ingreso_2025-06-03.json", "caso_0002_ingreso_2025-01-10.json", "caso_0002_ingreso_2025-09-01.json"],
       f"en 'listos' solo los informes sin avisos: {listos}")

    print("\n4) Revisión: tras marcar los nombres, el informe pasa a 'listos'")
    with open(os.path.join(priv, "ocultar_tambien.txt"), "a", encoding="utf-8") as f:
        f.write("Arcedo\nGañanez\nLucinda\n")
    with open(os.path.join(priv, "no_son_nombres.txt"), "a", encoding="utf-8") as f:
        f.write("Fuente\n")
    res2, _ = procesar([os.path.join(usb, "01_PRUEBAS_FICTICIO_alta.pdf")], priv, sal)
    ok(res2[0]["estado"] == "listo", "informe 01 ahora LISTO")
    ok(os.path.exists(os.path.join(sal, "listos", "caso_0001_ingreso_2025-01-10.json")), "aparece en 'listos'")
    ok(not os.path.exists(os.path.join(priv, "pendientes_de_revisar", "caso_0001_ingreso_2025-01-10.json")), "y desaparece de 'pendientes'")
    d = json.load(open(os.path.join(sal, "listos", "caso_0001_ingreso_2025-01-10.json"), encoding="utf-8"))
    ok("Arcedo" not in d["texto"] and "Lucinda" not in d["texto"], "los nombres marcados ya no aparecen")
    ok(d["paciente"] == {"sexo": "Hombre", "fecha_nacimiento": "1950-02-02", "edad": 74} and d["numero_caso"] == 1, "datos del caso en el JSON")
    ok([s["titulo"] for s in d["secciones"]][:3] == ["MOTIVO DE INGRESO", "ANTECEDENTES", "EXPLORACIÓN FÍSICA"], "texto separado por secciones")

    print("\n5) Libro llave")
    filas = llave.filas_llave()
    ok([f[0] for f in filas] == [1, 2, 3] and filas[0][2] == "CARM100000000001" and filas[0][3] == "100001", "llave: 3 pacientes con CARM y NHC")
    ok(filas[1][2] == "CARM100000000004" and filas[1][7] == "87654321X", "el CARM que faltaba se completa al reingresar; DNI guardado")
    prof = llave.profesionales()
    ok("Zubizarreta Montesclaros, Eulalia" in prof and "LUCRECIA ZARZALEJO OYAMBRE" in prof, "directorio de profesionales")
    from servidor import crear_xlsx, leer_xlsx
    ruta_x = os.path.join(tmp, "llave.xlsx")
    with open(ruta_x, "wb") as f:
        f.write(crear_xlsx([("LLAVE", [["numero", "cip", "carm", "nhc", "notas", "creado", "creado_por"],
                                       [50, "X", "CARM5", "5", "", "", ""]])]))
    h = leer_xlsx(ruta_x)["LLAVE"]
    ok(llave.importar([dict(zip(h[0], r)) for r in h[1:]]) == 1 and llave.siguiente_numero() == 51, "importar llave de la web y seguir numerando")
    shutil.rmtree(tmp)
    print(f"\n{'TODO CORRECTO' if not FALLOS else 'FALLOS: ' + str(len(FALLOS))}")
    sys.exit(1 if FALLOS else 0)


if __name__ == "__main__":
    main()
