"""
Preguntas para la IA a partir del diccionario del formulario (web/datos/diccionario.json).

Sigue las mismas reglas que la interfaz (web/js/modelo.js): campos ocultos fuera, preguntas
con opciones (selección única o múltiple), Sí/No con fecha, números con rango, condiciones
"mostrar_solo_si"... Así lo que propone la IA cae exactamente en los campos del formulario.
"""
import json
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
DICCIONARIO = os.path.join(AQUI, "..", "..", "web", "datos", "diccionario.json")

DIAG = {"ISQ": "ischemic_cardiomyopathy", "IC": "heart_failure", "EAO": "aortic_stenosis",
        "MCH": "hypertrophic_cardiomyopathy", "QTL": "long_qt_syndrome", "ATTR": "amyloidosis_attr",
        "IAM": "myocardial_infarction", "HTA": "hypertensive_disease"}
NOMBRE_DIAG = {"ISQ": "Cardiopatía isquémica", "IC": "Insuficiencia cardiaca", "EAO": "Estenosis aórtica",
               "MCH": "Miocardiopatía hipertrófica", "QTL": "Síndrome de QT largo", "ATTR": "Amiloidosis cardiaca por transtiretina (ATTR)",
               "IAM": "Infarto agudo de miocardio", "HTA": "Cardiopatía hipertensiva", "OTRO": "Otra cardiopatía"}
# Campos que no pregunta la IA: se rellenan solos o salen de la cabecera del informe
NO_PREGUNTAR = {"authored_at", "patient_id", "site_id", "other_disease", "dob", "biological_sex"} | set(DIAG.values())


def _t(v):
    return "" if v is None else str(v).strip()


def _num(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def compilar_condicion(c):
    """'a = 1 O b = 1 Y c != 0' -> función(valores) (misma lógica que modelo.js)."""
    c = _t(c)
    if not c:
        return lambda v: True, []
    refs, ors = [], []
    for parte in re.split(r"\s+O\s+", c, flags=re.I):
        ands = []
        for t in re.split(r"\s+Y\s+", parte, flags=re.I):
            m = re.search(r"([a-z0-9_]+)\s*(=|!=)\s*(\S+)", t, re.I)
            if not m:
                continue
            refs.append(m.group(1))
            ands.append((m.group(1), m.group(2), m.group(3)))
        ors.append(ands)

    def igual(a, b):
        if a is None:
            return False
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return str(a) == str(b)

    def fn(v):
        return any(all(igual(v.get(k), val) if op == "=" else not igual(v.get(k), val) for k, op, val in ands) for ands in ors)
    return fn, refs


def unidad(r):
    f = _t(r.get("formato_unidades_notas")).split(";")[0].strip()
    if not f or re.search(r"YYYY|code|dropdown|ICD|free text|follow", f, re.I) or len(f) > 22:
        return ""
    return f.replace("standard drinks/week", "UBE/sem").replace("hours/week", "h/sem").replace("beats/min", "lpm")


def cargar_preguntas(ruta=DICCIONARIO):
    with open(ruta, encoding="utf-8") as f:
        dic = json.load(f)
    filas = dic["campos"] + dic.get("locales", [])
    items, grupo, oculto_padre = [], None, False
    for r in filas:
        codigo = _t(r.get("codigo_variable"))
        if re.match(r"^s[ií]$", _t(r.get("oculto")), re.I):
            grupo = None
            oculto_padre = bool(_t(r.get("tipo_seleccion")))
            continue
        hijo = bool(_t(r.get("pertenece_a_pregunta")))
        if hijo and oculto_padre:
            continue  # opción de una pregunta oculta
        if not hijo:
            oculto_padre = False
        tipo = _t(r.get("tipo_formulario")) or _t(r.get("tipo"))
        ctrl = _t(r.get("control_en_pantalla"))
        cond, refs = compilar_condicion(r.get("mostrar_solo_si"))
        base = {
            "codigo": codigo, "texto": _t(r.get("texto_ES")) or codigo, "ayuda": _t(r.get("ayuda_ES")),
            "grupos": [g for g in re.split(r"[\s,;]+", _t(r.get("patologias") or "COMUN").upper()) if g],
            "condicion": _t(r.get("mostrar_solo_si")), "cond": cond, "refs": refs,
            "pestana": re.sub(r"^\d+\.\s*", "", _t(r.get("pestaña"))), "bloque": _t(r.get("bloque")),
            "min": _num(r.get("valor_min")), "max": _num(r.get("valor_max")), "unidad": unidad(r),
            "calculado": bool(_t(r.get("calcular"))) or bool(_t(r.get("copiar_de"))),
        }
        if _t(r.get("tipo_seleccion")):
            # en las preguntas con opciones, "copiar_de" se refiere a su fecha, no a la respuesta
            grupo = dict(base, calculado=bool(_t(r.get("calcular"))), tipo="multi" if _t(r["tipo_seleccion"]).startswith("m") else "single",
                         con_fecha=bool(re.search("fecha", ctrl, re.I)), opciones=[])
            items.append(grupo)
            continue
        if hijo and grupo:
            grupo["opciones"].append({"codigo": codigo, "texto": base["texto"], "con_fecha": "date" in tipo})
            continue
        grupo = None
        if codigo in ("authored_at", "patient_id") or _t(r.get("valor_fijo")) or re.search("Fijo", ctrl, re.I):
            t = "fijo"
        elif tipo == "boolean, date":
            t = "sinofecha"
        elif tipo == "boolean":
            t = "sino"
        elif tipo in ("date", "datetime"):
            t = "fecha"
        elif tipo == "float":
            t = "entero" if re.search("entero", ctrl, re.I) else "numero"
        else:
            t = "texto"
        items.append(dict(base, tipo=t))
    return items


def preguntables(items):
    return [it for it in items if it["tipo"] != "fijo" and it["codigo"] not in NO_PREGUNTAR and not it["calculado"]]


def lotes(items, maximo=22):
    """Agrupa las preguntas por pestaña (y bloques seguidos) en tandas de tamaño razonable."""
    out, actual, pest = [], [], None
    peso = lambda it: 1 + len(it.get("opciones", [])) // 4  # noqa: E731
    for it in items:
        if actual and (it["pestana"] != pest or sum(map(peso, actual)) + peso(it) > maximo):
            out.append(actual)
            actual = []
        actual.append(it)
        pest = it["pestana"]
    if actual:
        out.append(actual)
    return out


# ---------------------------------------------------------------------------
#  Texto de cada pregunta y esquema JSON de la respuesta
# ---------------------------------------------------------------------------
def describir(it):
    t = it["tipo"]
    txt = it["texto"]
    if t == "sino":
        q = f"{txt} [1 = sí, 0 = no]"
    elif t == "sinofecha":
        q = f"{txt} [1 = sí, 0 = no; si es 1, «fecha» = fecha del diagnóstico o del evento]"
    elif t == "fecha":
        q = f"{txt} [fecha AAAA-MM-DD]"
    elif t in ("numero", "entero"):
        rango = f", valores esperados {it['min']:g}–{it['max']:g}" if it["min"] is not None and it["max"] is not None else ""
        q = f"{txt} [{'número entero' if t == 'entero' else 'número'}{(' en ' + it['unidad']) if it['unidad'] else ''}{rango}]"
    elif t == "single":
        q = f"{txt} [UNA opción: " + " | ".join(f"{o['codigo']} = {o['texto']}" for o in it["opciones"]) + "]"
    elif t == "multi":
        q = f"{txt} [lista con TODAS las opciones que apliquen: " + " | ".join(f"{o['codigo']} = {o['texto']}" for o in it["opciones"]) + "]"
        if any(o["con_fecha"] for o in it["opciones"]):
            q += " (si hay fecha de la opción, ponla en «fecha»)"
    else:
        q = f"{txt} [texto breve]"
    if it["ayuda"]:
        q += f" — {it['ayuda']}"
    return f"- {it['codigo']}: {q}"


def esquema_valor(it):
    t = it["tipo"]
    if t in ("sino", "sinofecha"):
        return {"type": ["integer", "null"], "enum": [0, 1, None]}
    if t in ("numero", "entero"):
        return {"type": ["number", "null"]}
    if t == "single":
        return {"type": ["string", "null"], "enum": [o["codigo"] for o in it["opciones"]] + [None]}
    if t == "multi":
        return {"type": ["array", "null"], "items": {"type": "string", "enum": [o["codigo"] for o in it["opciones"]]}}
    return {"type": ["string", "null"]}


def esquema_lote(lote):
    props = {}
    for it in lote:
        p = {"valor": esquema_valor(it), "cita": {"type": ["string", "null"]}}
        req = ["valor", "cita"]
        if it["tipo"] == "sinofecha" or (it["tipo"] == "multi" and any(o["con_fecha"] for o in it["opciones"])):
            p["fecha"] = {"type": ["string", "null"]}
            req.append("fecha")
        props[it["codigo"]] = {"type": "object", "properties": p, "required": req, "additionalProperties": False}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


ESQUEMA_DIAGNOSTICOS = {
    "type": "object",
    "properties": {
        "diagnosticos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "codigo": {"type": "string", "enum": list(NOMBRE_DIAG)},
                    "texto": {"type": ["string", "null"]},
                    "cita": {"type": "string"},
                },
                "required": ["codigo", "texto", "cita"],
                "additionalProperties": False,
            },
        },
        "principal": {"type": ["string", "null"], "enum": list(NOMBRE_DIAG) + [None]},
    },
    "required": ["diagnosticos", "principal"],
    "additionalProperties": False,
}

ESQUEMA_REINGRESO = {
    "type": "object",
    "properties": {
        "por_insuficiencia_cardiaca": {"type": "integer", "enum": [0, 1]},
        "fallecimiento": {"type": "integer", "enum": [0, 1]},
        "cita": {"type": "string"},
    },
    "required": ["por_insuficiencia_cardiaca", "fallecimiento", "cita"],
    "additionalProperties": False,
}
