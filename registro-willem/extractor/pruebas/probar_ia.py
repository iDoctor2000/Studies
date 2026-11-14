#!/usr/bin/env python3
"""
Prueba de la FASE 2 (IA local) con una IA SIMULADA e informes INVENTADOS.

    python3 extractor/pruebas/probar_ia.py [carpeta_donde_dejar_las_propuestas]

Comprueba que las respuestas de la IA se convierten bien en valores del formulario,
que se detectan citas inventadas, números fuera de rango y fechas imposibles, que se
respetan las condiciones del formulario, que los reingresos rellenan el seguimiento y
que la IA solo se usa en este ordenador.
"""
import json
import os
import shutil
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "ia"))

import ia_simulada  # noqa: E402
import informes_sinteticos as S  # noqa: E402
from cliente import Cancelado, ClienteIA, ErrorIA, RespuestaCortada  # noqa: E402
from extraer_ia import Extraccion, cita_en_informe, convertir, ejecutar, fecha_iso  # noqa: E402
from preguntas import cargar_preguntas  # noqa: E402
from procesar_informes import buscar_pdfs, procesar  # noqa: E402

FALLOS = []


def ok(c, msg):
    print(("  ✓ " if c else "  ✗ ") + msg)
    if not c:
        FALLOS.append(msg)


CUERPO = [
    "MOTIVO DE INGRESO:", "Disnea de esfuerzo progresiva.", "",
    "ANTECEDENTES:", "FRCV: HTA. DM2. Dislipemia.", "Cardiopatía isquémica crónica. Fibrilación auricular paroxística.",
    "Situación basal: independiente. NYHA II.", "",
    "EXPLORACIÓN FÍSICA:", "TA: 130/80 mmHg; FC: 72 lpm.", "",
    "RESUMEN PRUEBAS COMPLEMENTARIAS:", "Ecocardiograma (05/01/2025): FEVI 38 %.", "NT-proBNP: 3500 pg/mL.",
    "Coronariografía urgente: oclusión de DA media con flujo TIMI 0, se implanta stent.", "",
    "DIAGNÓSTICO PRINCIPAL:", "Insuficiencia cardiaca con FEVI reducida.", "", "MOTIVO DE ALTA:", "Mejoría",
]


def main():
    tmp = tempfile.mkdtemp(prefix="willem_ia_")
    usb, priv, sal = (os.path.join(tmp, x) for x in ("usb", "privado", "anonimizado"))
    os.makedirs(usb)
    firma = ["Fdo: Dr./Dra. Ejemplo Inventado, Rosendo", "Col. Nº.: 30999999", "Fecha: 15/01/2025"]
    S.informe(os.path.join(usb, "a.pdf"), S.paciente(), CUERPO, firma)
    S.informe(os.path.join(usb, "b.pdf"), S.paciente(ingreso="03/06/2025 09:00", alta="09/06/2025 13:00", acto="25-1000099"),
              ["MOTIVO DE INGRESO:", "Insuficiencia cardiaca descompensada.", "", "MOTIVO DE ALTA:", "Mejoría"], firma)
    S.informe(os.path.join(usb, "c.pdf"), S.paciente(ingreso="10/10/2025 09:00", alta="12/10/2025 13:00", acto="25-1000100"),
              ["MOTIVO DE INGRESO:", "Neumonía.", "", "MOTIVO DE ALTA:", "Exitus"], firma)
    S.informe(os.path.join(usb, "d.pdf"), S.paciente(nhc="200002", carm="CARM200000000002", dni="22222222J", nombre="LUISA", sexo="Mujer",
                                                     nac="03/03/1960 (64 Años)", cip_sns="AAAAAAAAAA200002"),
              ["MOTIVO DE INGRESO:", "Dolor torácico.", "", "ANTECEDENTES:", "No HTA. Estenosis aórtica severa.", "", "MOTIVO DE ALTA:", "Mejoría"], firma)
    print("\n0) Fase 1 sobre los informes inventados")
    res, _ = procesar(buscar_pdfs([usb]), priv, sal)
    ok(all(r["estado"] == "listo" for r in res), "4 informes listos (2 pacientes)")

    print("\n1) Seguridad")
    try:
        ClienteIA("http://192.168.1.50:11434")
        ok(False, "rechaza una IA fuera de este ordenador")
    except ErrorIA:
        ok(True, "rechaza una IA fuera de este ordenador (solo localhost)")
    try:
        ClienteIA("http://127.0.0.1:11434", "gpt-oss:120b-cloud")
        ok(False, "rechaza modelos en la nube")
    except ErrorIA:
        ok(True, "rechaza los modelos «cloud» de Ollama (solo modelos locales)")
    try:
        ClienteIA("http://127.0.0.1:9", "x").modelos()
        ok(False, "avisa si la IA no está abierta")
    except ErrorIA as e:
        ok("Ollama" in str(e), "si la IA no está abierta, lo dice claramente")

    print("\n2) Comprobaciones de cada respuesta")
    items = {it["codigo"]: it for it in cargar_preguntas()}
    inf = {"texto": "Ecocardiograma (05/01/2025): FEVI 38 %.\nNYHA II.", "fecha_alta": "2025-01-15"}
    ok(cita_en_informe("Ecocardiograma (05/01/2025):  FEVI 38 %", inf["texto"]), "cita encontrada aunque cambien espacios")
    ok(not cita_en_informe("FEVI 45 %", inf["texto"]), "cita inventada detectada")
    c = convertir(items["echocardiography_lvef"], {"valor": 38, "cita": "FEVI 38 %"}, inf)
    ok(c[0] == {"echocardiography_lvef": 38} and not c[2], "FEVI 38 % → 38, sin avisos")
    c = convertir(items["echocardiography_lvef"], {"valor": 83, "cita": "FEVI 38 %"}, inf)
    ok(any("no aparece en la cita" in a for a in c[2]), "número que no está en la cita → aviso")
    ok(fecha_iso("2026-01-01", "2025-01-15")[0] is None, "fecha posterior al alta → se descarta")
    ok(fecha_iso("2019-03", "2025-01-15") == ("2019-03-01", "En el informe solo constan mes y año: se ha puesto el día 1"), "fecha incompleta → día 1 y aviso")
    c = convertir(items["nyha_functional_class"], {"valor": "nyha_class_ii", "cita": "NYHA II"}, inf)
    ok(c[0] == {"nyha_class_i": 0, "nyha_class_ii": 1, "nyha_class_iii": 0, "nyha_class_iv": 0}, "selección única → una opción a 1 y las demás a 0")
    ok(convertir(items["hypertension"], {"valor": None, "cita": None}, inf) is None, "sin respuesta → nada (no se pone «No»)")

    print("\n3) Extracción completa con la IA simulada")
    srv, url, llamadas = ia_simulada.arrancar()
    ia = ClienteIA(url, "simulada:1")
    ok(ia.modelos() == ["simulada:1"], "conecta con la IA local")
    import glob
    por_caso = {}
    for r in sorted(glob.glob(os.path.join(sal, "listos", "*.json"))):
        d = json.load(open(r, encoding="utf-8"))
        por_caso.setdefault(d["numero_caso"], []).append(d)
    ext = Extraccion(ia, cargar_preguntas())
    p1 = ext.caso(1, por_caso[1], progreso=lambda *_: None)
    v, meta = p1["valores"], p1["ia"]
    ok([d["codigo"] for d in p1["diagnosticos"]] == ["IC", "ISQ"], f"diagnósticos propuestos: IC (principal) e ISQ ({[d['codigo'] for d in p1['diagnosticos']]})")
    ok(v.get("echocardiography_lvef") == 38 and not meta["echocardiography_lvef"]["aviso"], "FEVI 38")
    ok(v.get("echocardiography_procedure") == "2025-01-05", "fecha del ecocardiograma")
    ok(v.get("natriuretic_peptide_nt_probnp") == 3500, "NT-proBNP 3500")
    ok(v.get("hypertension") == 1 and v.get("diabetes_mellitus_type_2") == 1, "HTA sí y diabetes tipo 2")
    ok(v.get("nyha_class_ii") == 1, "NYHA II")
    ok(v.get("dob") == "1950-02-02" and v.get("biological_sex_male") == 1 and meta["dob"]["origen"] == "cabecera", "fecha de nacimiento y sexo desde la cabecera")
    ok("no aparece literalmente" in meta["dyslipidaemia"]["aviso"], "la cita inventada (dislipemia) queda marcada")
    ok("Fuera del rango" in meta["resting_heart_rate"]["aviso"], "FC 400 → aviso de rango")
    ok(v.get("prior_arrhythmias") == 1 and meta["prior_arrhythmias"]["origen"] == "deducido", "arritmia previa deducida al haber FA (pregunta llave)")
    ok(v.get("timi_coronary_grade_flow_0") == 1 and v.get("coronary_angiography_done") == 1, "TIMI 0 → se marca la coronariografía como realizada")
    ok(v.get("rehospitalization") == 1 and v.get("rehospitalizations_number") == 2, "2 reingresos")
    ok(v.get("rehospitalization_hf") == 1 and v.get("rehospitalization_hf_date") == "2025-06-03", "reingreso por IC con su fecha")
    ok(v.get("rehospitalization_no_hf") == 1 and v.get("rehospitalization_no_hf_date") == "2025-10-10", "reingreso no IC con su fecha")
    ok(v.get("death") == 1 and v.get("death_date") == "2025-10-12", "fallecimiento (alta por exitus)")
    ok(len(p1["informes"]) == 3 and p1["informes"][0]["indice"], "los 3 informes van en la propuesta; el primero es el índice")
    ok(all(set(m["codigos"]) <= set(v) for m in meta.values()), "cada dato propuesto sabe qué campos rellena")
    p2 = ext.caso(2, por_caso[2], progreso=lambda *_: None)
    ok([d["codigo"] for d in p2["diagnosticos"]] == ["EAO"], "paciente 2: estenosis aórtica")
    ok(p2["valores"].get("hypertension") == 0, "«No HTA» → 0")
    ok("timi_coronary_grade_flow_0" not in p2["valores"], "sin datos de coronariografía no se inventa nada")
    ok(p2["valores"].get("biological_sex_female") == 1, "sexo mujer")
    ok("prior_atrial_fibrillation" not in p2["valores"], "nada de FA en quien no la tiene")
    # Lo que se envía a la IA está anonimizado
    enviado = json.dumps(llamadas, ensure_ascii=False)
    ok(all(x not in enviado for x in ("ANTONIO", "FICTICIO", "100001", "CARM100000000001", "611223344", "Rosendo")),
       "a la IA solo le llega el texto anonimizado")
    ok(all(c["options"]["num_ctx"] >= 16384 and c["options"]["temperature"] == 0 for c in llamadas), "contexto amplio y temperatura 0")
    ok(all(c["options"].get("num_predict", 0) > 0 and c["stream"] for c in llamadas), "cada respuesta tiene tope de longitud y se lee en directo")

    print("\n4) Si la IA se atasca, el programa se recupera solo")
    import threading
    import time as _t
    lineas = []
    # a) bucle de relleno en la tanda que contiene la FEVI: se corta y se repite por mitades
    ia_simulada.AVERIAS.update(bucle="echocardiography_lvef")
    t0 = _t.time()
    pb = Extraccion(ia, cargar_preguntas()).caso(1, por_caso[1], progreso=lineas.append)
    ok(_t.time() - t0 < 30, f"un bucle sin fin se detecta y se corta en segundos ({_t.time() - t0:.1f} s)")
    ok(pb["valores"].get("echocardiography_lvef") == 38 and pb["valores"].get("natriuretic_peptide_nt_probnp") == 3500,
       "tras repetir la tanda en mitades, los datos se recuperan (FEVI 38, NT-proBNP 3500)")
    ok(pb["incidencias"] >= 1 and any("se repite en dos mitades" in x for x in lineas), f"las repeticiones quedan anotadas ({pb['incidencias']})")
    ok({k: v for k, v in pb["valores"].items()} == {k: v for k, v in p1["valores"].items()}, "el resultado es idéntico al de una IA sin averías")
    ia_simulada.AVERIAS.update(bucle=None)
    # b) respuesta cortada por tope de longitud (JSON a medias)
    ia_simulada.AVERIAS.update(cortada="hypertension")
    pc = Extraccion(ia, cargar_preguntas()).caso(1, por_caso[1], progreso=lambda *_: None)
    ok(pc["valores"].get("hypertension") == 1 and pc["incidencias"] >= 1, "respuesta cortada a medias: se repite y se recupera")
    ia_simulada.AVERIAS.update(cortada=None)
    # d) registro en archivo y cancelación
    ruta_log = os.path.join(tmp, "registro_ia.log")
    ia_simulada.AVERIAS.update(bucle="echocardiography_lvef")
    filas, _, estado = ejecutar(ia, sal, [(1, por_caso[1])], progreso=lambda *_: None, ruta_log=ruta_log)
    ia_simulada.AVERIAS.update(bucle=None)
    log = open(ruta_log, encoding="utf-8").read()
    ok(estado == "ok" and filas[0]["incidencias"] >= 1, "ejecutar: caso terminado con incidencias contadas")
    ok("FALLO: Respuesta cortada: bucle" in log and "tanda 6/7" in log and "caso terminado" in log and "tokens" in log,
       "el registro dice en qué tanda falló, por qué, cuánto tardó y cuántos tokens")
    ok(all(x not in log for x in ("ANTONIO", "FICTICIO", "CARM100000000001")), "el registro no lleva datos identificativos")
    ia.cancelar = threading.Event()
    ia_simulada.AVERIAS.update(lenta=0.05)
    threading.Timer(0.6, ia.cancelar.set).start()
    t0 = _t.time()
    filas, _, estado = ejecutar(ia, sal, [(1, por_caso[1]), (2, por_caso[2])], progreso=lambda *_: None, ruta_log=ruta_log)
    ia_simulada.AVERIAS.update(lenta=0)
    ok(estado == "cancelado" and _t.time() - t0 < 5, f"«Cancelar» detiene la IA enseguida ({_t.time() - t0:.1f} s)")
    ia.cancelar = None
    try:
        lento = ClienteIA(url, "simulada:1", tiempo_max=1)
        ia_simulada.AVERIAS.update(lenta=0.7)
        lento.preguntar("s", "INFORME:\n-----\nFEVI 38 %\n-----\n", {"type": "object", "properties": {"echocardiography_lvef": {"type": "object", "properties": {}}, "hypertension": {"type": "object", "properties": {}}}})
        ok(False, "tope de tiempo por respuesta")
    except RespuestaCortada as e:
        ok("tiempo máximo" in str(e), "tope de tiempo por respuesta: se corta y avisa")
    ia_simulada.AVERIAS.update(lenta=0)

    destino = sys.argv[1] if len(sys.argv) > 1 else None
    if destino:
        os.makedirs(destino, exist_ok=True)
        for p in (p1, p2):
            with open(os.path.join(destino, f"caso_{p['numero_caso']:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False, indent=1)
    srv.shutdown()
    shutil.rmtree(tmp)
    print(f"\n{'TODO CORRECTO' if not FALLOS else 'FALLOS: ' + str(len(FALLOS))}")
    sys.exit(1 if FALLOS else 0)


if __name__ == "__main__":
    main()
