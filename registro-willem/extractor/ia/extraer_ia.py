#!/usr/bin/env python3
"""
Registro WILLEM · FASE 2: la IA local rellena el formulario a partir de los informes anonimizados.

Lee  ~/WILLEM_anonimizado/listos/caso_XXXX_ingreso_FECHA.json   (salida de la fase 1)
Deja ~/WILLEM_anonimizado/propuestas_ia/caso_XXXX.json          (se importa en la web: "Importar de la IA")

Para cada caso:
  1. El informe más antiguo es el ingreso índice: de él salen los datos basales.
  2. La IA propone los diagnósticos del estudio y responde, por tandas, a todas las preguntas
     del formulario. Cada respuesta lleva la FRASE LITERAL del informe en la que se basa.
  3. Comprobaciones automáticas: la frase existe en el informe, los números aparecen en ella,
     rangos, fechas posibles, condiciones del formulario. Lo dudoso se marca con un aviso.
  4. Los informes posteriores (reingresos) rellenan el seguimiento.
Nada se da por bueno: en la web, cada dato de la IA queda marcado hasta que una persona lo revisa.

Uso:  python3 extractor/ia/extraer_ia.py [--modelo qwen3:30b] [--casos 1,2] [--rehacer] [--abrir]
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import platform
import re
import subprocess
import sys
import time
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from cliente import ClienteIA, ErrorIA  # noqa: E402
from preguntas import (DIAG, ESQUEMA_DIAGNOSTICOS, ESQUEMA_REINGRESO, NOMBRE_DIAG, cargar_preguntas,  # noqa: E402
                       describir, esquema_lote, lotes, preguntables)

VERSION = "1.0"
SALIDA_DEF = os.path.join(os.path.expanduser("~"), "WILLEM_anonimizado")

SISTEMA = """Eres un asistente que extrae datos de informes de alta hospitalaria de cardiología para un registro de investigación.
Reglas obligatorias:
1. Usa SOLO lo que está escrito en el informe. No inventes ni supongas nada. Si un dato no consta, pon null.
2. Preguntas de sí/no: 1 si el informe lo afirma; 0 SOLO si el informe lo niega expresamente (por ejemplo "No HTA", "niega", "sin"); si no se menciona, null.
3. Números: el valor tal y como aparece, en las unidades pedidas, con punto decimal.
4. Fechas en formato AAAA-MM-DD. Si solo consta el mes y el año, AAAA-MM; si solo el año, AAAA. No calcules fechas a partir de expresiones como "hace 10 años": deja la fecha en null.
5. En "cita" copia LITERALMENTE el fragmento del informe que justifica la respuesta (máximo 200 caracteres), sin cambiar ninguna letra. Si la respuesta es null, la cita también es null.
6. El texto está anonimizado: las marcas entre corchetes como [PACIENTE] o [PROFESIONAL] son datos ocultos; ignóralas.
7. Responde únicamente con el objeto JSON pedido."""


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def compacto(s):
    return re.sub(r"\s+", "", sin_tildes(s).lower())


def cita_en_informe(cita, texto):
    if not cita or not cita.strip():
        return False
    t = compacto(texto)
    partes = [p for p in re.split(r"\.\.\.|…|\[\.\.\.\]", cita) if len(compacto(p)) >= 4]
    return bool(partes) and all(compacto(p) in t for p in partes)


def _num_en_cita(v, cita):
    c = compacto(cita).replace(",", ".")
    v = abs(float(v))
    variantes = {f"{v:g}", f"{v:.1f}", f"{v:.2f}"}
    if v == int(v):
        variantes.add(str(int(v)))
    return any(re.search(r"(?<![\d.])" + re.escape(x) + r"(?![\d])", c) for x in variantes)


def fecha_iso(valor, alta=None):
    """'2024-03' -> ('2024-03-01', aviso). Devuelve (None, motivo) si no es válida."""
    if not valor:
        return None, None
    m = re.fullmatch(r"\s*(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?\s*", str(valor))
    if not m:
        m2 = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", str(valor))
        if not m2:
            return None, f"Fecha con formato no reconocido ({valor})"
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}")
    a, me, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        f = dt.date(a, me, d)
    except ValueError:
        return None, f"Fecha imposible ({valor})"
    if a < 1900:
        return None, f"Fecha imposible ({valor})"
    if alta and f.isoformat() > alta:
        return None, f"Fecha posterior al alta del informe ({valor})"
    aviso = None
    if not m.group(2):
        aviso = "En el informe solo consta el año: se ha puesto el 1 de enero"
    elif not m.group(3):
        aviso = "En el informe solo constan mes y año: se ha puesto el día 1"
    return f.isoformat(), aviso


def _fecha_en_cita(iso, cita):
    a, m, d = iso.split("-")
    c = sin_tildes(cita or "").lower()
    return a in c or re.search(rf"\b0?{int(d)}[/.-]0?{int(m)}[/.-](?:{a}|{a[2:]})\b", c) is not None


# ---------------------------------------------------------------------------
#  Respuesta de la IA -> valores del formulario
# ---------------------------------------------------------------------------
def convertir(it, r, informe):
    """Devuelve (cambios, valor_texto, avisos) o None si no hay respuesta útil."""
    if not isinstance(r, dict):
        return None
    v, cita = r.get("valor"), (r.get("cita") or "").strip()
    if v is None or v == [] or v == "":
        return None
    avisos, cambios, t = [], {}, it["tipo"]
    alta = informe.get("fecha_alta")
    if t in ("sino", "sinofecha"):
        if v not in (0, 1):
            return None
        cambios[it["codigo"]] = v
        txt = "Sí" if v == 1 else "No"
        if t == "sinofecha" and v == 1 and r.get("fecha"):
            f, av = fecha_iso(r["fecha"], alta)
            if f:
                cambios[it["codigo"] + "_date"] = f
                txt += " · " + "/".join(reversed(f.split("-")))
                if not _fecha_en_cita(f, cita):
                    avisos.append("La fecha no aparece escrita en la cita")
            if av:
                avisos.append(av)
    elif t == "fecha":
        f, av = fecha_iso(v, alta)
        if not f:
            return ({}, "", [av]) if av else None
        cambios[it["codigo"]] = f
        txt = "/".join(reversed(f.split("-")))
        if av:
            avisos.append(av)
        if not _fecha_en_cita(f, cita):
            avisos.append("La fecha no aparece escrita en la cita")
    elif t in ("numero", "entero"):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        if t == "entero":
            x = round(x)
        x = int(x) if x == int(x) else round(x, 3)
        cambios[it["codigo"]] = x
        txt = f"{x:g}".replace(".", ",") + (f" {it['unidad']}" if it["unidad"] else "")
        if it["min"] is not None and it["max"] is not None and not (it["min"] <= x <= it["max"]):
            avisos.append(f"Fuera del rango esperado ({it['min']:g}–{it['max']:g})")
        if cita and not _num_en_cita(x, cita):
            avisos.append("El número no aparece en la cita")
    elif t == "single":
        ops = {o["codigo"]: o for o in it["opciones"]}
        if v not in ops:
            return None
        cambios.update({o: (1 if o == v else 0) for o in ops})
        txt = ops[v]["texto"]
    elif t == "multi":
        ops = {o["codigo"]: o for o in it["opciones"]}
        elegidas = [x for x in (v if isinstance(v, list) else [v]) if x in ops]
        if not elegidas:
            return None
        for o in elegidas:
            cambios[o] = 1
        txt = ", ".join(ops[o]["texto"] for o in elegidas)
        if r.get("fecha"):
            con_f = [o for o in elegidas if ops[o]["con_fecha"]]
            f, av = fecha_iso(r["fecha"], alta)
            if f and len(con_f) == 1:
                cambios[con_f[0] + "_date"] = f
                txt += " · " + "/".join(reversed(f.split("-")))
            if av:
                avisos.append(av)
    else:
        cambios[it["codigo"]] = str(v)[:300]
        txt = str(v)[:80]
    if not cita:
        avisos.append("La IA no ha indicado de dónde lo saca")
    elif not cita_en_informe(cita, informe["texto"]):
        avisos.append("La cita no aparece literalmente en el informe: compruébelo con especial cuidado")
    return cambios, txt, avisos


def aplica(it, diags):
    return "COMUN" in it["grupos"] or any(g in it["grupos"] for g in diags) or any(DIAG.get(g) in it["refs"] for g in diags)


def informe_para_ia(inf):
    p = inf.get("paciente") or {}
    cab = (f"Informe de alta. Fecha de ingreso: {inf.get('fecha_ingreso')}. Fecha de alta: {inf.get('fecha_alta')}. "
           f"Servicio: {inf.get('servicio') or '?'}. Sexo: {p.get('sexo') or '?'}. Edad: {p.get('edad') or '?'} años.")
    return f"{cab}\n\n{inf['texto']}"


class Extraccion:
    def __init__(self, cliente, items):
        self.ia = cliente
        self.items = items
        self.por_codigo = {it["codigo"]: it for it in items}

    def _preguntar(self, informe, preguntas, esquema):
        usuario = (f"INFORME (anonimizado):\n-----\n{informe_para_ia(informe)}\n-----\n\n"
                   f"PREGUNTAS. Devuelve un objeto JSON con una clave por cada código:\n{preguntas}")
        return self.ia.preguntar(SISTEMA, usuario, esquema)

    def diagnosticos(self, informe):
        lista = "\n".join(f"- {k}: {v}" for k, v in NOMBRE_DIAG.items())
        r = self._preguntar(informe, "¿Cuáles de estas cardiopatías tiene diagnosticadas el paciente según el informe "
                            "(como diagnóstico del ingreso o como antecedente)? Incluye solo las que estén escritas. "
                            "Para OTRO, indica en «texto» cuál es. En «principal», la que motivó este ingreso "
                            f"(si es una de la lista):\n{lista}", ESQUEMA_DIAGNOSTICOS)
        out, vistos = [], set()
        for d in r.get("diagnosticos") or []:
            g = d.get("codigo")
            if g not in NOMBRE_DIAG or g in vistos:
                continue
            vistos.add(g)
            av = [] if cita_en_informe(d.get("cita"), informe["texto"]) else ["La cita no aparece literalmente en el informe"]
            out.append({"codigo": g, "texto": (d.get("texto") or "").strip() if g == "OTRO" else "", "cita": d.get("cita") or "",
                        "aviso": "; ".join(av)})
        principal = r.get("principal") if r.get("principal") in vistos else (out[0]["codigo"] if out else None)
        out.sort(key=lambda d: d["codigo"] != principal)
        return out

    def caso(self, numero, informes, progreso=print):
        informes = sorted(informes, key=lambda i: i.get("fecha_ingreso") or "")
        indice, reingresos = informes[0], informes[1:]
        t0 = time.time()
        progreso(f"    diagnósticos…")
        diags = self.diagnosticos(indice)
        codigos_diag = [d["codigo"] for d in diags]
        propuestas, descartadas = {}, []
        # Datos de la cabecera (no los pregunta la IA)
        pac = indice.get("paciente") or {}
        if pac.get("fecha_nacimiento"):
            propuestas["dob"] = {"cambios": {"dob": pac["fecha_nacimiento"]}, "valor_texto": "/".join(reversed(pac["fecha_nacimiento"].split("-"))),
                                 "cita": "Cabecera del informe", "avisos": [], "origen": "cabecera"}
        sexo = (pac.get("sexo") or "").lower()
        if sexo in ("hombre", "mujer"):
            propuestas["biological_sex"] = {"cambios": {"biological_sex_male": int(sexo == "hombre"), "biological_sex_female": int(sexo == "mujer")},
                                            "valor_texto": "Varón" if sexo == "hombre" else "Mujer", "cita": "Cabecera del informe",
                                            "avisos": [], "origen": "cabecera"}
        basales = [it for it in preguntables(self.items) if it["pestana"] != "Seguimiento"]
        tandas = lotes(basales)
        for i, lote in enumerate(tandas, 1):
            progreso(f"    tanda {i}/{len(tandas)} · {lote[0]['pestana']} ({len(lote)} preguntas)…")
            try:
                r = self._preguntar(indice, "\n".join(describir(it) for it in lote), esquema_lote(lote))
            except ErrorIA as e:
                descartadas.append({"codigo": "(tanda)", "motivo": str(e)})
                continue
            for it in lote:
                conv = convertir(it, r.get(it["codigo"]), indice)
                if not conv:
                    continue
                cambios, txt, avisos = conv
                if not cambios:
                    descartadas.append({"codigo": it["codigo"], "motivo": "; ".join(avisos)})
                    continue
                if not aplica(it, codigos_diag):
                    descartadas.append({"codigo": it["codigo"], "motivo": "No corresponde a los diagnósticos propuestos"})
                    continue
                propuestas[it["codigo"]] = {"cambios": cambios, "valor_texto": txt, "cita": (r[it["codigo"]].get("cita") or "")[:300],
                                            "avisos": avisos, "origen": "ia"}
        if reingresos:
            progreso(f"    seguimiento: {len(reingresos)} reingreso(s)…")
            self.seguimiento(reingresos, propuestas)
        self.condiciones(propuestas, descartadas)
        valores = {}
        for p in propuestas.values():
            valores.update(p["cambios"])
        return {
            "formato": "willem-propuesta-ia/1",
            "version": VERSION,
            "numero_caso": numero,
            "generado": dt.datetime.now().replace(microsecond=0).isoformat(),
            "modelo": {"proveedor": self.ia.proveedor, "nombre": self.ia.modelo},
            "segundos": round(time.time() - t0, 1),
            "diagnosticos": diags,
            "informes": [{"fecha_ingreso": i.get("fecha_ingreso"), "fecha_alta": i.get("fecha_alta"), "servicio": i.get("servicio"),
                          "titulo": i.get("titulo"), "texto": i["texto"], "indice": n == 0} for n, i in enumerate(informes)],
            "valores": valores,
            "ia": {k: {"valor_texto": p["valor_texto"], "cita": p["cita"], "aviso": "; ".join(p["avisos"]), "origen": p["origen"],
                       "codigos": sorted(p["cambios"])} for k, p in propuestas.items()},
            "descartadas": descartadas,
        }

    def seguimiento(self, reingresos, propuestas):
        hf, no_hf, muerte = [], [], None
        for inf in reingresos:
            try:
                r = self._preguntar(inf, "- por_insuficiencia_cardiaca: ¿el motivo principal de ESTE ingreso es la insuficiencia cardiaca? [1/0]\n"
                                    "- fallecimiento: ¿el paciente falleció durante este ingreso (alta por exitus)? [1/0]\n"
                                    "- cita: frase literal del informe que lo justifica", ESQUEMA_REINGRESO)
            except ErrorIA:
                continue
            (hf if r.get("por_insuficiencia_cardiaca") == 1 else no_hf).append((inf, r.get("cita") or ""))
            if r.get("fallecimiento") == 1:
                muerte = (inf, r.get("cita") or "")
        aviso = "Deducido de los informes de reingreso: compruébelo"
        n = len(reingresos)
        propuestas["rehospitalization"] = {"cambios": {"rehospitalization": 1}, "valor_texto": "Sí", "cita": f"{n} informe(s) de reingreso",
                                           "avisos": [], "origen": "calculado"}
        propuestas["rehospitalizations_number"] = {"cambios": {"rehospitalizations_number": n}, "valor_texto": str(n),
                                                   "cita": f"{n} informe(s) de reingreso", "avisos": [], "origen": "calculado"}
        for cod, lista in (("rehospitalization_hf", hf), ("rehospitalization_no_hf", no_hf)):
            c = {cod: 1 if lista else 0}
            if lista:
                c[cod + "_date"] = lista[0][0].get("fecha_ingreso")
            propuestas[cod] = {"cambios": c, "valor_texto": ("Sí · " + "/".join(reversed(lista[0][0]["fecha_ingreso"].split("-")))) if lista else "No",
                               "cita": lista[0][1] if lista else "", "avisos": [aviso], "origen": "calculado"}
        ultimo = reingresos[-1]
        propuestas["follow_up_date"] = {"cambios": {"follow_up_date": ultimo.get("fecha_alta")}, "valor_texto": "/".join(reversed((ultimo.get("fecha_alta") or "").split("-"))),
                                        "cita": "Fecha de alta del último informe", "avisos": [aviso], "origen": "calculado"}
        if muerte:
            propuestas["mace"] = {"cambios": {"death": 1, "death_date": muerte[0].get("fecha_alta")}, "valor_texto": "Fallecimiento",
                                  "cita": muerte[1], "avisos": [aviso], "origen": "calculado"}

    def condiciones(self, propuestas, descartadas):
        """Quita lo que el formulario no mostraría (p. ej. datos de una prueba marcada como no realizada)."""
        for _ in range(6):
            valores = {}
            for p in propuestas.values():
                valores.update(p["cambios"])
            quitar = []
            for k, p in propuestas.items():
                it = self.por_codigo.get(k)
                if not it or it["cond"](valores):
                    continue
                # Si la condición es "prueba = 1" y nadie la ha contestado, pero hay resultados: se marca la prueba
                m = re.fullmatch(r"\s*([a-z0-9_]+)\s*=\s*1\s*", it["condicion"])
                llave = self.por_codigo.get(m.group(1)) if m else None
                if llave and llave["tipo"] in ("sino", "sinofecha") and valores.get(llave["codigo"]) is None:
                    propuestas[llave["codigo"]] = {"cambios": {llave["codigo"]: 1}, "valor_texto": "Sí", "cita": p["cita"],
                                                   "avisos": ["Se marca porque el informe da resultados de esta prueba"], "origen": "deducido"}
                    break
                quitar.append(k)
            else:
                for k in quitar:
                    descartadas.append({"codigo": k, "motivo": "El formulario no lo mostraría (condición: " + self.por_codigo[k]["condicion"] + ")"})
                    propuestas.pop(k)
                if not quitar:
                    return


# ---------------------------------------------------------------------------
def resumen_html(filas, carpeta):
    trs = "".join(
        f"<tr><td><b>{f['numero']}</b></td><td>{f['informes']}</td><td>{html.escape(', '.join(f['diags']) or '—')}</td>"
        f"<td>{f['campos']}</td><td class='{'av' if f['avisos'] else ''}'>{f['avisos']}</td><td>{f['segundos']:.0f} s</td>"
        f"<td>{html.escape(f.get('error') or '')}</td></tr>" for f in filas)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WILLEM · propuestas de la IA</title><style>
:root{{--fondo:#f4f6fb;--papel:#fff;--tinta:#1d2433;--suave:#5b6478;--borde:#dfe4ee;--ambar:#c77700}}
@media (prefers-color-scheme:dark){{:root{{--fondo:#11151d;--papel:#1a202b;--tinta:#e6e9f0;--suave:#9aa3b5;--borde:#2c3443}}}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px}} h1{{font-size:22px;margin:0 0 4px}} p{{color:var(--suave)}}
.tabla{{overflow-x:auto;background:var(--papel);border:1px solid var(--borde);border-radius:12px}}
table{{border-collapse:collapse;width:100%}} th,td{{padding:8px 10px;border-bottom:1px solid var(--borde);text-align:left;font-size:14px}}
th{{color:var(--suave);font-weight:600}} td.av{{color:var(--ambar);font-weight:700}} code{{font-size:12px}}
</style></head><body><main><h1>Propuestas de la IA</h1>
<p>{dt.datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(filas)} caso(s). Importe la carpeta <code>{html.escape(carpeta)}</code> en la web
(menú «Importar de la IA»). Ningún dato se da por bueno hasta que una persona lo revisa.</p>
<div class="tabla"><table><tr><th>Caso</th><th>Informes</th><th>Diagnósticos propuestos</th><th>Campos propuestos</th><th>Con aviso</th><th>Tiempo</th><th>Error</th></tr>{trs}</table></div>
</main></body></html>"""


def casos_a_procesar(salida, elegidos=None, rehacer=False):
    """Casos con informes listos que aún no tienen propuesta (o todos con rehacer). -> [(numero, [informes])]"""
    por_caso = {}
    for ruta in sorted(glob.glob(os.path.join(salida, "listos", "caso_*.json"))):
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
        por_caso.setdefault(d["numero_caso"], []).append((ruta, d))
    out = []
    for numero in sorted(por_caso):
        if elegidos and numero not in elegidos:
            continue
        prop = os.path.join(salida, "propuestas_ia", f"caso_{numero:04d}.json")
        mas_nuevo = max(os.path.getmtime(r) for r, _ in por_caso[numero])
        if os.path.exists(prop) and not rehacer and os.path.getmtime(prop) >= mas_nuevo:
            continue
        out.append((numero, [d for _, d in por_caso[numero]]))
    return out


def pasos(casos, n_tandas):
    """Número de pasos (llamadas a la IA) previstos, para la barra de progreso."""
    return sum(1 + n_tandas + (1 if len(infs) > 1 else 0) for _, infs in casos)


def ejecutar(ia, salida, casos, progreso=print, al_caso=None):
    """Extrae los casos indicados y guarda las propuestas. Devuelve (filas, ruta_resumen)."""
    ext = Extraccion(ia, cargar_preguntas())
    destino = os.path.join(salida, "propuestas_ia")
    os.makedirs(destino, exist_ok=True)
    filas = []
    for numero, informes in casos:
        progreso(f"  Caso {numero} ({len(informes)} informe(s))")
        fila = {"numero": numero, "informes": len(informes), "diags": [], "campos": 0, "avisos": 0, "segundos": 0}
        try:
            prop = ext.caso(numero, informes, progreso=progreso)
            with open(os.path.join(destino, f"caso_{numero:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(prop, f, ensure_ascii=False, indent=1)
            fila.update(diags=[d["codigo"] for d in prop["diagnosticos"]], campos=len(prop["ia"]),
                        avisos=sum(1 for x in prop["ia"].values() if x["aviso"]), segundos=prop["segundos"])
            progreso(f"    → {fila['campos']} campos propuestos ({fila['avisos']} con aviso) en {fila['segundos']:.0f} s")
        except ErrorIA as e:
            fila["error"] = str(e)
            progreso(f"    ✗ {e}")
        filas.append(fila)
        if al_caso:
            al_caso(fila)
    ruta_html = None
    if filas:
        ruta_html = os.path.join(destino, f"resumen_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        with open(ruta_html, "w", encoding="utf-8") as f:
            f.write(resumen_html(filas, destino))
    return filas, ruta_html


def comprobar_modelo(ia):
    """Lanza ErrorIA si la IA no está en marcha o el modelo no está instalado."""
    instalados = ia.modelos()
    if ia.proveedor == "ollama" and instalados and ia.modelo not in instalados and ia.modelo + ":latest" not in instalados:
        raise ErrorIA(f"El modelo «{ia.modelo}» no está instalado en Ollama. Instalados: {', '.join(instalados)}. "
                      f"Instálelo con:  ollama pull {ia.modelo}")
    return instalados


def main():
    ap = argparse.ArgumentParser(description="La IA local rellena el formulario a partir de los informes anonimizados.")
    ap.add_argument("--salida", default=SALIDA_DEF, help="carpeta WILLEM_anonimizado")
    ap.add_argument("--modelo", default=os.environ.get("WILLEM_MODELO", "qwen3:30b"))
    ap.add_argument("--url", default=os.environ.get("WILLEM_IA_URL", "http://127.0.0.1:11434"))
    ap.add_argument("--proveedor", choices=["ollama", "openai"], default=os.environ.get("WILLEM_IA_PROVEEDOR", "ollama"),
                    help="ollama (por defecto) u openai (LM Studio y similares)")
    ap.add_argument("--contexto", type=int, default=16384, help="tamaño de contexto del modelo (tokens)")
    ap.add_argument("--casos", help="solo estos casos, p. ej. 1,2,7")
    ap.add_argument("--rehacer", action="store_true", help="volver a extraer aunque ya haya propuesta")
    ap.add_argument("--abrir", action="store_true")
    a = ap.parse_args()
    try:
        ia = ClienteIA(a.url, a.modelo, a.proveedor, a.contexto)
        comprobar_modelo(ia)
    except ErrorIA as e:
        sys.exit(f"\n{e}\n")
    elegidos = {int(x) for x in a.casos.split(",")} if a.casos else None
    casos = casos_a_procesar(a.salida, elegidos, a.rehacer)
    print(f"\nRegistro WILLEM · extracción con IA local ({a.modelo})\n")
    if not casos:
        print("  No hay casos nuevos que procesar (use --rehacer para repetir los que ya tienen propuesta).")
        return
    filas, ruta_html = ejecutar(ia, a.salida, casos)
    print(f"\nPropuestas en: {os.path.join(a.salida, 'propuestas_ia')}\nResumen: {ruta_html}")
    if a.abrir and platform.system() == "Darwin":
        subprocess.run(["open", ruta_html])


if __name__ == "__main__":
    main()
