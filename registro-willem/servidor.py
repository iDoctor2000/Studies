#!/usr/bin/env python3
"""
Registro WILLEM · Hospital Clínico Universitario Virgen de la Arrixaca
Servidor web LOCAL. Solo usa la biblioteca estándar de Python (no hay que instalar nada).

    python servidor.py              -> abre en este ordenador  (http://127.0.0.1:8765)
    python servidor.py --red        -> accesible desde otros PCs de la red del hospital
    python servidor.py --demo       -> base de DEMOSTRACIÓN con pacientes inventados
    python servidor.py --puerto 9000
    python servidor.py --llave E:\\llave\\llave.sqlite   (libro llave en un USB cifrado, p. ej.)

Ningún dato sale de este ordenador: no hay conexión a internet ni a servicios externos.
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import math
import mimetypes
import os
import re
import secrets
import sqlite3
import ssl
import sys
import threading
import time
import webbrowser
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASE, "web")
DICCIONARIO = os.path.join(BASE, "diccionario", "diccionario_maestro.xlsx")
SITE_ID = "HCUVA"
MARCAS = ("NC", "DUDA")  # Desconocido / Duda: en el Excel final van vacíos
SESION_HORAS = 12

# Windows a veces asigna tipos MIME erróneos a .js/.css (los módulos no cargarían)
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

# Perfiles: dm = data manager (todo) · rev = cardiólogo revisor (revisa, corrige y valida casos; auditoría y pistas
# de la IA; no importa, no exporta, no borra y no gestiona usuarios) · intro = introducción de datos
ROLES = ("dm", "rev", "intro")
REVISAN = ("dm", "rev")
CFG = {"db": None, "llave": None, "demo": False, "nas": False, "2fa": False, "https": False}
LOCK = threading.Lock()


# ===========================================================================
#  Lectura del diccionario (xlsx) sin librerías externas
# ===========================================================================
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col_idx(ref):
    letras = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def leer_xlsx(ruta):
    """Devuelve {nombre_hoja: [[celdas...], ...]}."""
    hojas = {}
    with zipfile.ZipFile(ruta) as z:
        compartidas = []
        if "xl/sharedStrings.xml" in z.namelist():
            raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in raiz.findall("m:si", NS):
                compartidas.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        destino = {r.get("Id"): r.get("Target") for r in rels}
        for hoja in wb.find("m:sheets", NS):
            rid = hoja.get(f"{{{NS['r']}}}id")
            tgt = destino[rid].lstrip("/")
            tgt = tgt if tgt.startswith("xl/") else "xl/" + tgt
            raiz = ET.fromstring(z.read(tgt))
            filas = []
            for row in raiz.iter(f"{{{NS['m']}}}row"):
                fila = []
                for c in row.findall("m:c", NS):
                    i = _col_idx(c.get("r"))
                    while len(fila) <= i:
                        fila.append(None)
                    t = c.get("t")
                    v = c.find("m:v", NS)
                    if t == "s" and v is not None:
                        val = compartidas[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                    elif v is not None:
                        val = v.text
                        try:
                            f = float(val)
                            val = int(f) if f.is_integer() else f
                        except (TypeError, ValueError):
                            pass
                    else:
                        val = None
                    fila[i] = val
                filas.append(fila)
            hojas[hoja.get("name")] = filas
    return hojas


_DIC_CACHE = {"mtime": None, "data": None}


def diccionario():
    mtime = os.path.getmtime(DICCIONARIO)
    if _DIC_CACHE["mtime"] != mtime:
        hojas = leer_xlsx(DICCIONARIO)

        def a_dicts(filas):
            if not filas:
                return []
            cab = [str(c or "").strip() for c in filas[0]]
            out = []
            for f in filas[1:]:
                d = {cab[i]: (f[i] if i < len(f) else None) for i in range(len(cab)) if cab[i]}
                if d.get("codigo_variable"):
                    out.append(d)
            return out

        campos = a_dicts(hojas.get("Diccionario", []))
        locales = [d for d in a_dicts(hojas.get("Variables_locales", []))
                   if not str(d["codigo_variable"]).startswith("local_ejemplo")]
        for d in locales:
            d["exportar_al_registro"] = d.get("exportar_al_registro") or "Solo local"
            d["pestaña"] = "Datos locales"
            d["local"] = True
        _DIC_CACHE.update(mtime=mtime, data={"campos": campos, "locales": locales,
                                             "cargado": dt.datetime.fromtimestamp(mtime).isoformat(timespec="minutes")})
    return _DIC_CACHE["data"]


def columnas_exportacion(solo_local=False):
    """Columnas del Excel final, SIEMPRE en el orden del CRF original (orden_registro)."""
    dic = diccionario()
    cols = []
    def orden(d):
        try:
            return float(d.get("orden_registro") or 1e6)
        except (TypeError, ValueError):
            return 1e6
    for d in sorted(dic["campos"] + dic["locales"], key=orden):
        exp = str(d.get("exportar_al_registro") or "")
        es_local = exp.lower().startswith("solo local")
        if exp.lower() == "no" or es_local != solo_local:
            continue
        spec = str(d.get("columnas_en_exportacion") or d["codigo_variable"])
        if spec.startswith("("):
            continue
        cols += [c.strip() for c in spec.split(";") if c.strip()]
    return cols


# ===========================================================================
#  Base de datos
# ===========================================================================
@contextmanager
def db():
    """Conexión con commit automático y cierre garantizado."""
    con = sqlite3.connect(CFG["db"], timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def es_ruta_de_red(ruta):
    """True si la ruta está en una carpeta compartida (NAS, unidad de red)."""
    ruta = os.path.abspath(ruta)
    if ruta.startswith("\\\\") or ruta.startswith("//"):
        return True
    if os.name == "nt":
        try:
            import ctypes
            unidad = os.path.splitdrive(ruta)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(unidad) == 4  # DRIVE_REMOTE
        except Exception:
            return False
    return False


def iniciar_db():
    os.makedirs(os.path.dirname(CFG["db"]), exist_ok=True)
    # El modo WAL de SQLite no es seguro en carpetas de red: allí se usa el modo clásico.
    modo = "DELETE" if CFG.get("red_fs") else "WAL"
    with db() as con:
        con.execute(f"PRAGMA journal_mode={modo}")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios(
            id INTEGER PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL,
            rol TEXT NOT NULL CHECK(rol IN ('dm','intro','rev')), hash TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1, creado TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sesiones(
            token TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
            expira TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS casos(
            numero INTEGER PRIMARY KEY, principal TEXT NOT NULL, secundarias TEXT NOT NULL DEFAULT '[]',
            valores TEXT NOT NULL DEFAULT '{}', estado TEXT NOT NULL DEFAULT 'borrador',
            creado TEXT NOT NULL, creado_por TEXT NOT NULL,
            modificado TEXT NOT NULL, modificado_por TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS auditoria(
            id INTEGER PRIMARY KEY, numero INTEGER, usuario TEXT, fecha TEXT,
            campo TEXT, antes TEXT, despues TEXT, origen TEXT);
        CREATE INDEX IF NOT EXISTS idx_aud_num ON auditoria(numero);
        """)
        # Pistas clínicas para la IA escritas por el equipo (sustituyen a las del diccionario)
        con.execute("CREATE TABLE IF NOT EXISTS pistas_ia(codigo TEXT PRIMARY KEY, texto TEXT NOT NULL, autor TEXT, fecha TEXT)")
        # Papelera: los casos eliminados se guardan enteros para que un data manager pueda recuperarlos
        con.execute("""CREATE TABLE IF NOT EXISTS casos_borrados(
            id INTEGER PRIMARY KEY, numero INTEGER NOT NULL, datos TEXT NOT NULL, borrado_por TEXT NOT NULL, fecha TEXT NOT NULL)""")
        # Fase 2 (IA local): propuestas de la IA y textos anonimizados de los informes
        cols = [r[1] for r in con.execute("PRAGMA table_info(casos)")]
        if "ia" not in cols:
            con.execute("ALTER TABLE casos ADD COLUMN ia TEXT NOT NULL DEFAULT '{}'")
        if "informes" not in cols:
            con.execute("ALTER TABLE casos ADD COLUMN informes TEXT NOT NULL DEFAULT '[]'")
        # Doble factor (TOTP) y bloqueo por intentos fallidos
        cols_u = [r[1] for r in con.execute("PRAGMA table_info(usuarios)")]
        for col, tipo in (("totp", "TEXT"), ("totp_ultimo", "INTEGER"), ("recuperacion", "TEXT"),
                          ("fallos", "INTEGER NOT NULL DEFAULT 0"), ("bloqueado_hasta", "TEXT")):
            if col not in cols_u:
                con.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {tipo}")
    migrar_roles()


def migrar_roles():
    """Bases anteriores al perfil «cardiólogo revisor»: se rehace la tabla de usuarios para admitirlo (sin perder nada)."""
    con = sqlite3.connect(CFG["db"], timeout=30, isolation_level=None)
    try:
        sql = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()[0]
        if "'rev'" in sql:
            return
        nuevo = re.sub(r"CREATE TABLE\s+\"?usuarios\"?\s*\(", "CREATE TABLE usuarios_nueva(", sql, count=1)
        nuevo = re.sub(r"IN\s*\(\s*'dm'\s*,\s*'intro'\s*\)", "IN ('dm','intro','rev')", nuevo)
        if nuevo == sql or "'rev'" not in nuevo or "usuarios_nueva" not in nuevo:
            raise RuntimeError("No se ha podido actualizar la tabla de usuarios")
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute(nuevo)
            con.execute("INSERT INTO usuarios_nueva SELECT * FROM usuarios")
            con.execute("DROP TABLE usuarios")
            con.execute("ALTER TABLE usuarios_nueva RENAME TO usuarios")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def copia_de_seguridad(carpeta, conservar=14):
    """Copia coherente de la base (API de copia de SQLite, válida con el registro en uso). Guarda las últimas `conservar`."""
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"registro_{dt.date.today().isoformat()}.sqlite")
    origen = sqlite3.connect(CFG["db"], timeout=30)
    copia = sqlite3.connect(destino + ".tmp")
    try:
        with copia:
            origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    os.replace(destino + ".tmp", destino)
    copias = sorted(f for f in os.listdir(carpeta) if re.fullmatch(r"registro_\d{4}-\d{2}-\d{2}\.sqlite", f))
    for viejo in copias[:-conservar]:
        os.remove(os.path.join(carpeta, viejo))
    return destino


def copias_diarias(carpeta):
    while True:
        try:
            print(f"  Copia de seguridad: {copia_de_seguridad(carpeta)}")
        except Exception as e:  # nunca debe tumbar el servidor
            print(f"  AVISO: no se pudo hacer la copia de seguridad ({e})")
        time.sleep(24 * 3600)


def llave_db():
    if CFG["nas"]:
        return None  # en el NAS no hay libro llave: solo existe en el Mac
    ruta = CFG["llave"]
    carpeta = os.path.dirname(ruta)
    if not os.path.isdir(carpeta):
        return None
    con = sqlite3.connect(ruta, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS llave(
        numero INTEGER PRIMARY KEY, cip TEXT, carm TEXT, nhc TEXT, notas TEXT,
        creado TEXT, creado_por TEXT)""")
    return con


def ahora():
    return dt.datetime.now().isoformat(timespec="seconds")


def hash_pw(pw, sal=None):
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(sal), 240_000).hex()
    return f"{sal}${h}"


def comprobar_pw(pw, guardado):
    sal, _ = guardado.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, sal), guardado)


# ===========================================================================
#  Doble factor (TOTP, RFC 6238: Google Authenticator, Microsoft Authenticator...)
# ===========================================================================
EMISOR_2FA = "WILLEM Arrixaca"
DESAFIOS = {}  # token -> {usuario_id, tipo: "codigo"|"alta", secreto, expira}
INTENTOS_IP = {}  # ip -> [instantes de fallos]
MAX_FALLOS_USUARIO, MAX_FALLOS_IP, MINUTOS_BLOQUEO = 5, 20, 15


def nuevo_secreto_totp():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp(secreto, paso=None, digitos=6, periodo=30):
    clave = base64.b32decode(secreto.upper() + "=" * (-len(secreto) % 8))
    n = int(time.time() // periodo) if paso is None else paso
    h = hmac.new(clave, n.to_bytes(8, "big"), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((int.from_bytes(h[o:o + 4], "big") & 0x7FFFFFFF) % 10 ** digitos).zfill(digitos)


def comprobar_totp(secreto, codigo, ultimo=None):
    """Devuelve el paso de tiempo válido (admite ±30 s de desfase) o None. Un código no se puede reutilizar."""
    codigo = re.sub(r"\s", "", codigo or "")
    if not re.fullmatch(r"\d{6}", codigo):
        return None
    ahora_paso = int(time.time() // 30)
    for paso in (ahora_paso - 1, ahora_paso, ahora_paso + 1):
        if hmac.compare_digest(totp(secreto, paso), codigo):
            return paso if (ultimo is None or paso > ultimo) else -1  # -1: código correcto pero ya usado
    return None


def uri_totp(usuario, secreto):
    return (f"otpauth://totp/{quote(EMISOR_2FA)}:{quote(usuario)}?secret={secreto}&issuer={quote(EMISOR_2FA)}"
            "&algorithm=SHA1&digits=6&period=30")


def codigos_recuperacion(n=8):
    letras = "abcdefghjkmnpqrstuvwxyz23456789"
    return ["".join(secrets.choice(letras) for _ in range(4)) + "-" + "".join(secrets.choice(letras) for _ in range(4)) for _ in range(n)]


def hash_recuperacion(codigo, usuario_id):
    return hashlib.sha256(f"{usuario_id}:{codigo.strip().lower()}".encode()).hexdigest()


def nuevo_desafio(usuario_id, tipo, secreto=None):
    tok = secrets.token_urlsafe(24)
    with LOCK:
        for k in [k for k, d in DESAFIOS.items() if d["expira"] < time.time()]:
            DESAFIOS.pop(k, None)
        DESAFIOS[tok] = {"usuario_id": usuario_id, "tipo": tipo, "secreto": secreto, "expira": time.time() + 300}
    return tok


def caso_a_dict(r, con_valores=True, con_informes=False):
    d = {"numero": r["numero"], "principal": r["principal"],
         "secundarias": json.loads(r["secundarias"]), "estado": r["estado"],
         "creado": r["creado"], "creado_por": r["creado_por"],
         "modificado": r["modificado"], "modificado_por": r["modificado_por"],
         "ia": json.loads(r["ia"] or "{}")}
    if con_valores:
        d["valores"] = json.loads(r["valores"])
    if con_informes:
        d["informes"] = json.loads(r["informes"] or "[]")
    return d


# ===========================================================================
#  Propuestas de la IA local (misma lógica que web/js/ia.js)
# ===========================================================================
def eventos_posteriores(valores):
    """Fechas de eventos del seguimiento posteriores a la fecha del último seguimiento (no debería haber ninguna)."""
    fu = str(valores.get("follow_up_date") or "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}", fu):
        return []
    claves = [k for k in valores if k in ("death_date", "rehospitalization_hf_date", "rehospitalization_no_hf_date")
              or (k.startswith("mace_") and k.endswith("_date"))]
    return sorted(k for k in claves if re.match(r"^\d{4}-\d{2}-\d{2}", str(valores[k])) and str(valores[k])[:10] > fu[:10])


def _tiene_valor(x):
    return x is not None and x != ""


def ia_pendientes(ia, valores):
    return [k for k, m in ia.items() if not m.get("revisado")
            and (k == "_diagnosticos" or any(_tiene_valor(valores.get(c)) for c in m.get("codigos", [])))]


def marcar_por_campos(ia, campos):
    campos, out = set(campos), []
    for k, m in ia.items():
        if not m.get("revisado") and campos & set(m.get("codigos", [])):
            m["revisado"] = True
            out.append(k)
    return out


def aplicar_propuesta(con, p, usuario):
    """Aplica una propuesta de la IA (crea el caso si no existe). Nunca pisa lo escrito por una persona."""
    if not isinstance(p, dict) or p.get("formato") != "willem-propuesta-ia/1":
        return {"accion": "omitido", "motivo": "No es un archivo de propuestas de la IA"}
    num = int(p.get("numero_caso") or 0)
    if num <= 0:
        return {"accion": "omitido", "motivo": "Número de caso no válido"}
    r = con.execute("SELECT * FROM casos WHERE numero=?", (num,)).fetchone()
    if r and r["estado"] == "validado":
        return {"numero": num, "accion": "omitido", "motivo": "El caso ya está validado"}
    if r and not json.loads(r["ia"] or "{}"):
        # Un caso creado a mano con el mismo número podría ser OTRO paciente: nunca se mezcla
        return {"numero": num, "accion": "omitido", "motivo": "Ya existe un caso con ese número creado a mano. Compruebe que la "
                "numeración del libro llave del Mac continúa la del registro (Estación → Ajustes → primer número)"}
    t = ahora()
    auditoria = []
    if r:
        accion, valores = "actualizado", json.loads(r["valores"])
        principal, sec = r["principal"], json.loads(r["secundarias"])
        ia, informes = json.loads(r["ia"] or "{}"), json.loads(r["informes"] or "[]")
    else:
        accion = "creado"
        diags = [d.get("codigo") for d in p.get("diagnosticos") or [] if d.get("codigo") in GRUPOS_PRINCIPALES]
        principal, sec = (diags[0] if diags else "OTRO"), diags[1:]
        valores = {"site_id": SITE_ID, "patient_id": num, "authored_at": t}
        valores.update(diagnosticos(principal, sec))
        if "OTRO" in [principal, *sec]:
            otro = next((d for d in p.get("diagnosticos") or [] if d.get("codigo") == "OTRO"), {})
            valores["other_disease"] = (otro.get("texto") or "").strip() or "Pendiente de revisar (propuesto por la IA)"
        avisos = ([] if diags else ["La IA no ha identificado ningún diagnóstico del estudio"]) + \
            [d.get("aviso") for d in p.get("diagnosticos") or [] if d.get("aviso")]
        ia = {"_diagnosticos": {"valor_texto": ", ".join(diags or ["OTRO"]), "origen": "ia", "revisado": False,
                                "cita": "\n".join(f"{d.get('codigo')}: {d.get('cita')}" for d in p.get("diagnosticos") or []),
                                "aviso": "; ".join(avisos), "codigos": ["_diagnosticos"]}}
        informes = []
        auditoria.append(("(caso creado)", None, principal))
    de_ia = {c for m in ia.values() if not m.get("revisado") for c in m.get("codigos", [])}
    aplicados = omitidos = 0
    for k, meta in (p.get("ia") or {}).items():
        cods = [c for c in meta.get("codigos") or [] if re.fullmatch(r"[a-z0-9_]{1,80}", str(c))
                and c not in ("site_id", "patient_id", "authored_at")]
        if not cods:
            continue
        nuevos = {c: (p.get("valores") or {}).get(c) for c in cods}
        previo = ia.get(k)
        if previo and previo.get("revisado") and previo.get("valores_ia") == nuevos:
            omitidos += 1  # una persona ya revisó (confirmó, corrigió o quitó) esta misma propuesta: no se repite
            continue
        if any(_tiene_valor(valores.get(c)) and c not in de_ia for c in cods):
            omitidos += 1
            continue
        for c in cods:
            nuevo = (p.get("valores") or {}).get(c)
            if valores.get(c) != nuevo:
                auditoria.append((c, valores.get(c), nuevo))
            if nuevo is None:
                valores.pop(c, None)
            else:
                valores[c] = nuevo
        ia[k] = {"valor_texto": str(meta.get("valor_texto") or ""), "cita": str(meta.get("cita") or ""),
                 "aviso": str(meta.get("aviso") or ""), "origen": meta.get("origen") or "ia", "codigos": cods, "revisado": False,
                 "valores_ia": nuevos}  # lo que propuso la IA, para la auditoría (compararlo con lo que quede al final)
        aplicados += 1
    for inf in p.get("informes") or []:
        limpio = {k: inf.get(k) for k in ("fecha_ingreso", "fecha_alta", "servicio", "titulo")}
        limpio.update(texto=str(inf.get("texto") or ""), indice=bool(inf.get("indice")))
        informes = [x for x in informes if x.get("fecha_ingreso") != limpio["fecha_ingreso"]] + [limpio]
    informes.sort(key=lambda x: str(x.get("fecha_ingreso")))
    if r:
        con.execute("UPDATE casos SET valores=?, ia=?, informes=?, modificado=?, modificado_por=? WHERE numero=?",
                    (json.dumps(valores), json.dumps(ia), json.dumps(informes), t, usuario, num))
    else:
        con.execute("""INSERT INTO casos(numero,principal,secundarias,valores,creado,creado_por,modificado,modificado_por,ia,informes)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", (num, principal, json.dumps(sec), json.dumps(valores), t, usuario, t, usuario,
                                                          json.dumps(ia), json.dumps(informes)))
    con.executemany("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                    [(num, usuario, t, c, None if a is None else str(a), None if d is None else str(d), "ia") for c, a, d in auditoria])
    return {"numero": num, "accion": accion, "aplicados": aplicados, "omitidos": omitidos}


# ===========================================================================
#  Exportación a Excel (xlsx mínimo, sin librerías)
# ===========================================================================
def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col_letra(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _hoja_xml(filas):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
           '<sheetData>']
    for ri, fila in enumerate(filas, 1):
        out.append(f'<row r="{ri}">')
        for ci, v in enumerate(fila):
            ref = f"{_col_letra(ci)}{ri}"
            estilo = ' s="1"' if ri == 1 else ""
            if v is None or v == "":
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append(f'<c r="{ref}"{estilo}><v>{v}</v></c>')
            else:
                out.append(f'<c r="{ref}" t="inlineStr"{estilo}><is><t xml:space="preserve">{_esc(v)}</t></is></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def crear_xlsx(hojas):
    """hojas: [(nombre, filas)] -> bytes"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ov = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                     for i in range(1, len(hojas) + 1))
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + ov + '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        sheets = "".join(f'<sheet name="{_esc(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(hojas, 1))
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f'<sheets>{sheets}</sheets></workbook>')
        rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                       for i in range(1, len(hojas) + 1))
        rels += f'<Relationship Id="rId{len(hojas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                   '</styleSheet>')
        for i, (_, filas) in enumerate(hojas, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _hoja_xml(filas))
    return buf.getvalue()


FECHA_DESCONOCIDA = "0000-00-00"


def filas_exportacion(solo_local=False, solo_validados=False, desconocido="blanco"):
    """desconocido: "blanco" (por defecto) o "-1" (Desconocido = -1; en fechas, 0000-00-00). La Duda va siempre en blanco."""
    cols = columnas_exportacion(solo_local)
    menos1 = desconocido == "-1"

    def es_fecha(c):
        f = campo.get(c) or {}
        return c.endswith("_date") or str(f.get("tipo_formulario") or f.get("tipo") or "").startswith("date")
    if not solo_local:
        cab = cols  # exactamente las columnas del CRF original, en su orden
    else:
        cab = ["patient_id"] + cols
    filas = [cab]
    copias = copias_calculadas()
    conjunto = set(cols)
    campo = campo_por_columna()
    with db() as con:
        q = "SELECT * FROM casos" + (" WHERE estado='validado'" if solo_validados else "") + " ORDER BY numero"
        for r in con.execute(q):
          base = json.loads(r["valores"])
          diags = [r["principal"]] + json.loads(r["secundarias"])
          # Una fila por diagnóstico (en la hoja local, una por caso)
          for g in ([None] if solo_local else diags):
            v = dict(base)
            if g:
                for G, cod in DIAG.items():
                    v[cod] = 1 if G == g else 0
                if g != "OTRO":
                    v.pop("other_disease", None)
                preparar_valores(v, {"diagnosticos": diags, "creado": r["creado"]})
            fila = [r["numero"]] if solo_local else []
            v.setdefault("site_id", SITE_ID)
            v["site_id"], v["patient_id"] = SITE_ID, r["numero"]
            v.setdefault("authored_at", r["creado"])
            for c in cols:
                if g and not aplica_a(campo.get(c), g):
                    fila.append("")
                    continue
                x = v.get(copias.get(c, c))
                if menos1 and x == "NC":
                    fila.append(FECHA_DESCONOCIDA if es_fecha(c) else -1)
                    continue
                if not solo_local and c.endswith("_date") and c[:-5] in conjunto:
                    # Fecha de un Sí/No: la fecha si la hay; 0 si está contestado; vacío si Desconocido/Duda/sin contestar
                    if x not in (None, "") and x not in MARCAS:
                        fila.append(x)
                    else:
                        b = v.get(copias.get(c[:-5], c[:-5]))
                        fila.append(0 if b in (0, 1) else "")
                    continue
                fila.append("" if x is None or x in MARCAS else x)
            filas.append(fila)
    return filas


_OPS = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b, ">": lambda a, b: a > b, "=": lambda a, b: a == b}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def _vacio(x):
    return x is None or x == ""


def _es_numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _redondear1(x):
    """Redondeo a 1 decimal como Math.round de JavaScript (los .5 hacia arriba), para que web y servidor den lo mismo."""
    return math.floor(x * 10 + 0.5) / 10


def edad_en(nacimiento, fecha):
    """Años cumplidos entre dos fechas AAAA-MM-DD."""
    a = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(nacimiento or ""))
    b = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(fecha or ""))
    if not a or not b:
        return None
    e = int(b.group(1)) - int(a.group(1))
    if b.group(2) + b.group(3) < a.group(2) + a.group(3):
        e -= 1
    return e if 0 <= e < 130 else None


def _fn_mdrd(v, ctx):
    """Filtrado glomerular MDRD-4 (IDMS): 175 × Cr^-1,154 × edad^-0,203 × 0,742 si mujer. Edad en la fecha de la analítica."""
    cr = v.get("creatinine")
    sexo = 0.742 if v.get("biological_sex_female") == 1 else (1 if v.get("biological_sex_male") == 1 else None)
    if not _es_numero(cr) or cr <= 0 or sexo is None:
        return None
    diag = sorted(str(v[k]) for k in v if k.endswith("_diagnosis_date") and re.match(r"^\d{4}-", str(v[k])))
    ref = next((f for f in (v.get("laboratory_biomarkers_test"), diag[0] if diag else None, ctx.get("creado"))
                if re.match(r"^\d{4}-\d{2}-\d{2}", str(f or ""))), None)
    edad = edad_en(v.get("dob"), ref)
    if not edad:
        return None
    x = _redondear1(175 * cr ** -1.154 * edad ** -0.203 * sexo)
    return int(x) if x == int(x) else x


def _fn_sindrome_cardiorrenal(v, ctx):
    """IC (diagnóstico del estudio o ingreso previo por IC) + (ERC o MDRD < 60)."""
    previo = v.get("prior_heart_failure_hospitalization")
    ic = 1 if ("IC" in (ctx.get("diagnosticos") or []) or previo == 1) else (0 if previo == 0 else ("NC" if previo == "NC" else "DUDA"))
    # el filtrado se calcula aquí mismo: en el diccionario va después y aún no estaría hecho
    erc, fg = v.get("chronic_kidney_disease"), _fn_mdrd(v, ctx)
    if fg is None:
        fg = v.get("glomerular_filtration_rate_mdrd")
    renal = 1 if (erc == 1 or (_es_numero(fg) and fg < 60)) else (0 if erc == 0 else ("NC" if erc == "NC" else "DUDA"))
    if ic == 1 and renal == 1:
        return 1
    if ic == 0 or renal == 0:
        return 0
    return "DUDA" if "DUDA" in (ic, renal) else "NC"


FUNCIONES = {"mdrd": _fn_mdrd, "sindrome_cardiorrenal": _fn_sindrome_cardiorrenal}


def cumple_condicion(texto, v):
    """¿Se cumple "a = 1 O b = 1 Y c != 0"? (misma gramática que mostrar_solo_si)"""
    c = str(texto or "").strip()
    if not c:
        return True

    def igual(a, b):
        if a is None:
            return False
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return str(a) == str(b)

    for parte in re.split(r"\s+O\s+", c, flags=re.I):
        ok = True
        for at in re.split(r"\s+Y\s+", parte, flags=re.I):
            m = re.search(r"([a-z0-9_]+)\s*(=|!=)\s*(\S+)", at, re.I)
            if not m:
                continue
            if igual(v.get(m.group(1)), m.group(3)) != (m.group(2) == "="):
                ok = False
                break
        if ok:
            return True
    return False


def _valor_regla(x):
    try:
        f = float(x)
        return int(f) if f == int(f) else f
    except ValueError:
        return x


def aplicar_defectos(v):
    """Valores por defecto al exportar (columna valor_por_defecto): mismas reglas que registro.js."""
    for f in diccionario()["campos"]:
        d = str(f.get("valor_por_defecto") if f.get("valor_por_defecto") is not None else "").strip()
        if not d:
            continue
        cod = str(f["codigo_variable"])
        if "->" in d:
            if not _vacio(v.get(cod)) and cumple_condicion(f.get("mostrar_solo_si"), v):
                continue
            for regla in d.split(";"):
                m = re.search(r"([a-z0-9_]+)\s*=\s*(\S+)\s*->\s*(\S+)", regla, re.I)
                if not m:
                    continue
                x = v.get(m.group(1))
                txt = str(int(x)) if isinstance(x, float) and x == int(x) else str(x)
                if x is not None and txt == m.group(2):
                    v[cod] = _valor_regla(m.group(3))
                    break
        elif _vacio(v.get(cod)) and re.match(r"^s[ií]$", str(f.get("oculto") or "").strip(), re.I):
            v[cod] = _valor_regla(d)
    return v


def preparar_valores(v, ctx):
    """Valores listos para exportar: por defecto + calculados. ctx = {"diagnosticos": [...], "creado": iso}"""
    aplicar_defectos(v)
    return aplicar_calculos(v, ctx)


def aplicar_calculos(v, ctx=None):
    """Campos calculados (columna 'calcular'): mismas reglas que web/js/registro.js."""
    ctx = ctx or {}
    for f in diccionario()["campos"]:
        spec = str(f.get("calcular") or "").strip()
        if not spec:
            continue
        fn = re.match(r"^funcion:\s*([a-z0-9_]+)", spec, re.I)
        if fn:
            res = FUNCIONES[fn.group(1)](v, ctx) if fn.group(1) in FUNCIONES else None
            if res is not None:
                v[str(f["codigo_variable"])] = res
            continue
        reglas, _, extra = spec.partition("|")
        m_fecha = re.search(r"fecha:\s*([a-z0-9_]+)", extra, re.I)
        res = None
        for regla in reglas.split(";"):
            if "->" not in regla:
                continue
            cond, valor = [x.strip() for x in regla.split("->", 1)]
            cumple = True
            for at in re.split(r"\s+y\s+", cond, flags=re.I):
                m = re.match(r"^([a-z0-9_]+)\s*(<=|>=|!=|<|>|=)\s*(\S+)$", at.strip(), re.I)
                x = v.get(m.group(1)) if m else None
                if not m or x in (None, "") or x in MARCAS:
                    cumple = False
                    break
                a, b = _num(x), _num(m.group(3))
                try:
                    ok = _OPS[m.group(2)](a, b)
                except TypeError:
                    ok = False
                if not ok:
                    cumple = False
                    break
            if cumple:
                res = int(valor) if re.fullmatch(r"-?\d+", valor) else (float(valor) if re.fullmatch(r"-?\d+\.\d+", valor) else v.get(valor))
                break
        cod = str(f["codigo_variable"])
        if res in (None, ""):
            v.pop(cod, None)
            v.pop(cod + "_date", None)
            continue
        v[cod] = res
        if m_fecha:
            if res == 1 and v.get(m_fecha.group(1)):
                v[cod + "_date"] = v[m_fecha.group(1)]
            else:
                v.pop(cod + "_date", None)
    return v


def campo_por_columna():
    m = {}
    dic = diccionario()
    for f in dic["campos"] + dic["locales"]:
        spec = str(f.get("columnas_en_exportacion") or f["codigo_variable"])
        if spec.startswith("("):
            continue
        for c in spec.split(";"):
            if c.strip():
                m[c.strip()] = f
    return m


def aplica_a(f, g):
    """¿La columna corresponde a la fila del diagnóstico g?"""
    if not f:
        return True
    grupos = re.split(r"[\s,;]+", str(f.get("patologias") or "COMUN").upper())
    if "COMUN" not in grupos and g not in grupos:
        return False
    cond = str(f.get("mostrar_solo_si") or "")
    return not any(G != g and re.search(rf"\b{cod}\b", cond) for G, cod in DIAG.items())


def copias_calculadas():
    """Campos cuyo valor se copia de otro (columna copiar_de del diccionario)."""
    return {str(d["codigo_variable"]): str(d["copiar_de"]).strip() for d in diccionario()["campos"] if str(d.get("copiar_de") or "").strip()}


def filas_marcas(solo_validados=False):
    """Hoja interna: qué campos quedaron como Desconocido o Duda (no se envía)."""
    filas = [["patient_id", "variable", "estado", "nota_duda"]]
    with db() as con:
        q = "SELECT * FROM casos" + (" WHERE estado='validado'" if solo_validados else "") + " ORDER BY numero"
        for r in con.execute(q):
            v = json.loads(r["valores"])
            for k, x in sorted(v.items()):
                if x in MARCAS:
                    filas.append([r["numero"], k, "Desconocido" if x == "NC" else "Duda", v.get(k + "_duda_nota", "")])
    return filas


# ===========================================================================
#  Servidor HTTP
# ===========================================================================
class Error(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


class Manejador(BaseHTTPRequestHandler):
    server_version = "WILLEM/1.0"

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            sys.stderr.write("  %s  %s\n" % (dt.datetime.now().strftime("%H:%M:%S"), args[0]))

    # ---- utilidades -------------------------------------------------------
    def end_headers(self):
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if CFG["https"] or CFG["nas"]:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        super().end_headers()

    def _json(self, obj, code=200, headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _cuerpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise Error(415, "Se esperaba JSON")
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _usuario(self, obligatorio=True, rol=None):
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"willem_sid=([A-Za-z0-9_\-]+)", cookie)
        u = None
        if m:
            with db() as con:
                u = con.execute("""SELECT u.* FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id
                                   WHERE s.token=? AND s.expira>? AND u.activo=1""", (m.group(1), ahora())).fetchone()
        if obligatorio and not u:
            raise Error(401, "Sesión no iniciada o caducada")
        if rol and u["rol"] not in ((rol,) if isinstance(rol, str) else rol):
            raise Error(403, "Solo los data managers pueden hacer esto" if rol == "dm" else "Su perfil no permite hacer esto")
        return u

    def _estatico(self, ruta):
        if ruta in ("", "/"):
            ruta = "/index.html"
        f = os.path.normpath(os.path.join(WEB, ruta.lstrip("/")))
        if not f.startswith(WEB) or not os.path.isfile(f):
            f = os.path.join(WEB, "index.html")
        with open(f, "rb") as fh:
            data = fh.read()
        tipo = mimetypes.guess_type(f)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo.endswith("javascript"):
            tipo += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _descarga(self, data, nombre, tipo):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- enrutado -----------------------------------------------------------
    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def do_PUT(self):
        self._despachar("PUT")

    def do_DELETE(self):
        self._despachar("DELETE")

    def _desde_el_proxy(self, url):
        """En el NAS solo se atiende lo que llega por el proxy inverso HTTPS de DSM, que añade la
        cabecera X-Willem-Proxy con la clave de <datos>/clave_proxy.txt. Así, aunque el puerto 8765
        se alcance por otra vía (p. ej. el Tailscale de Synology reenvía la red privada a localhost),
        sin la clave no se puede usar. La comprobación de salud del propio contenedor queda exenta."""
        if not CFG.get("clave_proxy"):
            return True
        if self.client_address[0] == "127.0.0.1" and url.path == "/api/estado":
            return True
        recibida = (self.headers.get("X-Willem-Proxy") or "").strip().encode()
        return hmac.compare_digest(recibida, CFG["clave_proxy"].encode())

    def _despachar(self, metodo):
        url = urlparse(self.path)
        if not self._desde_el_proxy(url):
            data = "Acceso solo a través del proxy HTTPS del NAS.\n".encode()
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        try:
            if not url.path.startswith("/api/"):
                if metodo != "GET":
                    raise Error(405, "Método no permitido")
                return self._estatico(url.path)
            partes = url.path[5:].strip("/").split("/")
            fn = getattr(self, f"api_{metodo.lower()}_{partes[0].replace('-', '_')}", None)
            if not fn:
                raise Error(404, "No encontrado")
            return fn(partes[1:], parse_qs(url.query))
        except Error as e:
            self._json({"error": e.msg}, e.code)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self._json({"error": f"Petición no válida: {e}"}, 400)
        except Exception as e:  # noqa
            import traceback
            traceback.print_exc()
            self._json({"error": f"Error interno: {e}"}, 500)

    # ---- configuración inicial / sesión ------------------------------------
    def api_get_estado(self, p, q):
        with db() as con:
            n = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        u = self._usuario(obligatorio=False)
        self._json({"necesita_configuracion": n == 0, "demo": CFG["demo"], "centro": SITE_ID, "nas": CFG["nas"],
                    "doble_factor": CFG["2fa"],
                    "usuario": dict(id=u["id"], usuario=u["usuario"], nombre=u["nombre"], rol=u["rol"]) if u else None})

    def api_post_configurar(self, p, q):
        b = self._cuerpo()
        with LOCK, db() as con:
            if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
                raise Error(403, "Ya está configurado")
            self._validar_usuario(b)
            con.execute("INSERT INTO usuarios(usuario,nombre,rol,hash,creado) VALUES(?,?,?,?,?)",
                        (b["usuario"].strip().lower(), b["nombre"].strip(), "dm", hash_pw(b["clave"]), ahora()))
        self._json({"ok": True})

    def _validar_usuario(self, b, clave_obligatoria=True):
        if not re.fullmatch(r"[a-zA-Z0-9._-]{3,30}", (b.get("usuario") or "").strip()):
            raise Error(400, "Usuario: 3-30 letras, números, punto o guion")
        if not (b.get("nombre") or "").strip():
            raise Error(400, "Falta el nombre")
        if clave_obligatoria or b.get("clave"):
            if len(b.get("clave") or "") < 8:
                raise Error(400, "La contraseña debe tener al menos 8 caracteres")

    # -- protección frente a intentos repetidos
    def _ip(self):
        if CFG["nas"]:  # detrás del proxy inverso del NAS
            xff = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if xff:
                return xff
        return self.client_address[0]

    def _comprobar_ip(self):
        ip, t = self._ip(), time.time()
        with LOCK:
            fallos = [x for x in INTENTOS_IP.get(ip, []) if x > t - MINUTOS_BLOQUEO * 60]
            INTENTOS_IP[ip] = fallos
        if len(fallos) >= MAX_FALLOS_IP:
            raise Error(429, f"Demasiados intentos desde este equipo: espere {MINUTOS_BLOQUEO} minutos")

    def _fallo(self, con, u=None):
        with LOCK:
            INTENTOS_IP.setdefault(self._ip(), []).append(time.time())
        if u is not None:
            n = (u["fallos"] or 0) + 1
            hasta = (dt.datetime.now() + dt.timedelta(minutes=MINUTOS_BLOQUEO)).isoformat(timespec="seconds") if n >= MAX_FALLOS_USUARIO else None
            con.execute("UPDATE usuarios SET fallos=?, bloqueado_hasta=? WHERE id=?", (0 if hasta else n, hasta, u["id"]))
            con.commit()

    def _bloqueado(self, u):
        if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora():
            raise Error(429, f"Usuario bloqueado por demasiados intentos: espere {MINUTOS_BLOQUEO} minutos o pida a un data manager que lo revise")

    def _abrir_sesion(self, con, u, extra=None):
        tok = secrets.token_urlsafe(32)
        exp = (dt.datetime.now() + dt.timedelta(hours=SESION_HORAS)).isoformat(timespec="seconds")
        con.execute("DELETE FROM sesiones WHERE expira<?", (ahora(),))
        con.execute("INSERT INTO sesiones VALUES(?,?,?)", (tok, u["id"], exp))
        con.execute("UPDATE usuarios SET fallos=0, bloqueado_hasta=NULL WHERE id=?", (u["id"],))
        con.commit()  # antes de responder: la siguiente petición ya debe encontrar la sesión
        segura = "; Secure" if (CFG["https"] or CFG["nas"]) else ""
        self._json({"ok": True, **(extra or {})},
                   headers={"Set-Cookie": f"willem_sid={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESION_HORAS * 3600}{segura}"})

    def api_post_login(self, p, q):
        """Paso 1: usuario y contraseña. Paso 2 (/login/codigo): código del doble factor.
        Alta del doble factor (/login/activar): primer código de la aplicación del móvil."""
        self._comprobar_ip()
        b = self._cuerpo()
        paso = p[0] if p else ""
        with db() as con:
            if paso in ("codigo", "activar"):
                d = DESAFIOS.get(b.get("desafio") or "")
                if not d or d["expira"] < time.time() or d["tipo"] != {"codigo": "codigo", "activar": "alta"}[paso]:
                    raise Error(401, "La verificación ha caducado: vuelva a escribir su usuario y contraseña")
                u = con.execute("SELECT * FROM usuarios WHERE id=? AND activo=1", (d["usuario_id"],)).fetchone()
                if not u:
                    raise Error(401, "Usuario no válido")
                self._bloqueado(u)
                codigo = (b.get("codigo") or "").strip()
                if paso == "activar":
                    pasos = comprobar_totp(d["secreto"], codigo)
                    if pasos is None or pasos < 0:
                        self._fallo(con, u)
                        raise Error(401, "El código no es correcto. Compruebe la hora del móvil y escriba el código que aparece ahora")
                    rec = codigos_recuperacion()
                    con.execute("UPDATE usuarios SET totp=?, totp_ultimo=?, recuperacion=? WHERE id=?",
                                (d["secreto"], pasos, json.dumps([hash_recuperacion(c, u["id"]) for c in rec]), u["id"]))
                    DESAFIOS.pop(b.get("desafio"), None)
                    con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                                (None, u["usuario"], ahora(), "(doble factor activado)", None, None, "formulario"))
                    return self._abrir_sesion(con, u, {"recuperacion": rec})
                pasos = comprobar_totp(u["totp"], codigo, u["totp_ultimo"])
                if pasos == -1:
                    raise Error(401, "Ese código ya se ha usado: espere a que la aplicación muestre el siguiente (cambia cada 30 segundos)")
                if pasos is not None:
                    con.execute("UPDATE usuarios SET totp_ultimo=? WHERE id=?", (pasos, u["id"]))
                else:
                    lista = json.loads(u["recuperacion"] or "[]")
                    h = hash_recuperacion(codigo, u["id"])
                    if h not in lista:
                        self._fallo(con, u)
                        raise Error(401, "Código incorrecto")
                    lista.remove(h)  # cada código de recuperación sirve una sola vez
                    con.execute("UPDATE usuarios SET recuperacion=? WHERE id=?", (json.dumps(lista), u["id"]))
                DESAFIOS.pop(b.get("desafio"), None)
                return self._abrir_sesion(con, u)
            u = con.execute("SELECT * FROM usuarios WHERE usuario=? AND activo=1",
                            ((b.get("usuario") or "").strip().lower(),)).fetchone()
            if u:
                self._bloqueado(u)
            if not u or not comprobar_pw(b.get("clave") or "", u["hash"]):
                self._fallo(con, u)
                raise Error(401, "Usuario o contraseña incorrectos")
            if u["totp"]:
                return self._json({"paso": "codigo", "desafio": nuevo_desafio(u["id"], "codigo")})
            if CFG["2fa"]:
                sec = nuevo_secreto_totp()
                return self._json({"paso": "configurar_2fa", "desafio": nuevo_desafio(u["id"], "alta", sec),
                                   "secreto": sec, "uri": uri_totp(u["usuario"], sec), "usuario": u["usuario"]})
            return self._abrir_sesion(con, u)

    def api_post_logout(self, p, q):
        cookie = self.headers.get("Cookie") or ""
        m = re.search(r"willem_sid=([A-Za-z0-9_\-]+)", cookie)
        if m:
            with db() as con:
                con.execute("DELETE FROM sesiones WHERE token=?", (m.group(1),))
        self._json({"ok": True}, headers={"Set-Cookie": "willem_sid=; Path=/; Max-Age=0"})

    # ---- diccionario -------------------------------------------------------
    def api_post_clave(self, p, q):
        """Cada persona cambia su propia contraseña (hay que saber la actual)."""
        u = self._usuario()
        b = self._cuerpo()
        nueva = b.get("nueva") or ""
        m = re.search(r"willem_sid=([A-Za-z0-9_\-]+)", self.headers.get("Cookie") or "")
        self._comprobar_ip()
        self._bloqueado(u)
        if not comprobar_pw(b.get("actual") or "", u["hash"]):
            with db() as con:
                self._fallo(con, u)
            raise Error(403, "La contraseña actual no es correcta")
        with LOCK, db() as con:
            if len(nueva) < 8:
                raise Error(400, "La contraseña nueva debe tener al menos 8 caracteres")
            if nueva == b.get("actual"):
                raise Error(400, "La contraseña nueva debe ser distinta de la actual")
            con.execute("UPDATE usuarios SET hash=?, fallos=0 WHERE id=?", (hash_pw(nueva), u["id"]))
            # se cierran sus otras sesiones abiertas (otros navegadores o equipos)
            con.execute("DELETE FROM sesiones WHERE usuario_id=? AND token<>?", (u["id"], m.group(1) if m else ""))
            con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(NULL,?,?,?,NULL,NULL,?)",
                        (u["usuario"], ahora(), "(contraseña cambiada por el propio usuario)", "cuenta"))
        self._json({"ok": True})

    def api_get_diccionario(self, p, q):
        self._usuario()
        self._json(diccionario())

    # ---- usuarios ----------------------------------------------------------
    def api_get_usuarios(self, p, q):
        self._usuario(rol="dm")
        with db() as con:
            rows = con.execute("""SELECT id,usuario,nombre,rol,activo,creado, totp IS NOT NULL AS doble_factor,
                                  CASE WHEN bloqueado_hasta > ? THEN bloqueado_hasta END AS bloqueado_hasta
                                  FROM usuarios ORDER BY rol,nombre""", (ahora(),)).fetchall()
        self._json([dict(r) for r in rows])

    def api_post_usuarios(self, p, q):
        self._usuario(rol="dm")
        b = self._cuerpo()
        self._validar_usuario(b)
        if b.get("rol") not in ROLES:
            raise Error(400, "Rol no válido")
        try:
            with LOCK, db() as con:
                con.execute("INSERT INTO usuarios(usuario,nombre,rol,hash,creado) VALUES(?,?,?,?,?)",
                            (b["usuario"].strip().lower(), b["nombre"].strip(), b["rol"], hash_pw(b["clave"]), ahora()))
        except sqlite3.IntegrityError:
            raise Error(409, "Ese nombre de usuario ya existe")
        self._json({"ok": True})

    def api_put_usuarios(self, p, q):
        yo = self._usuario(rol="dm")
        uid = int(p[0])
        b = self._cuerpo()
        with LOCK, db() as con:
            u = con.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
            if not u:
                raise Error(404, "Usuario no encontrado")
            if "activo" in b:
                if uid == yo["id"] and not b["activo"]:
                    raise Error(400, "No puede desactivarse a sí mismo")
                con.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if b["activo"] else 0, uid))
                if not b["activo"]:
                    con.execute("DELETE FROM sesiones WHERE usuario_id=?", (uid,))
            if b.get("clave"):
                if len(b["clave"]) < 8:
                    raise Error(400, "La contraseña debe tener al menos 8 caracteres")
                con.execute("UPDATE usuarios SET hash=? WHERE id=?", (hash_pw(b["clave"]), uid))
            if b.get("rol") in ROLES and uid != yo["id"]:
                con.execute("UPDATE usuarios SET rol=? WHERE id=?", (b["rol"], uid))
            if b.get("reiniciar_2fa"):
                # Móvil perdido o cambiado: la próxima vez que entre volverá a configurar el doble factor
                con.execute("UPDATE usuarios SET totp=NULL, totp_ultimo=NULL, recuperacion=NULL WHERE id=?", (uid,))
                con.execute("DELETE FROM sesiones WHERE usuario_id=?", (uid,))
            if b.get("desbloquear"):
                con.execute("UPDATE usuarios SET fallos=0, bloqueado_hasta=NULL WHERE id=?", (uid,))
        self._json({"ok": True})

    # ---- casos -------------------------------------------------------------
    def api_get_casos(self, p, q):
        self._usuario()
        with db() as con:
            if p:
                r = con.execute("SELECT * FROM casos WHERE numero=?", (int(p[0]),)).fetchone()
                if not r:
                    raise Error(404, "Caso no encontrado")
                return self._json(caso_a_dict(r, con_informes=True))
            rows = con.execute("SELECT * FROM casos ORDER BY modificado DESC").fetchall()
        self._json([caso_a_dict(r) for r in rows])

    def api_get_siguiente(self, p, q):
        self._usuario()
        self._json({"numero": siguiente_numero()})

    def api_post_casos(self, p, q):
        u = self._usuario()
        b = self._cuerpo()
        num = int(b.get("numero") or 0)
        if num <= 0:
            raise Error(400, "Número de caso no válido")
        if b.get("principal") not in GRUPOS_PRINCIPALES:
            raise Error(400, "Elija al menos un diagnóstico")
        sec = [s for s in b.get("secundarias", []) if s in GRUPOS_TODOS and s != b["principal"]]
        valores = {"site_id": SITE_ID, "patient_id": num, "authored_at": ahora()}
        valores.update(diagnosticos(b["principal"], sec))
        try:
            with LOCK, db() as con:
                con.execute("""INSERT INTO casos(numero,principal,secundarias,valores,creado,creado_por,modificado,modificado_por)
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (num, b["principal"], json.dumps(sec), json.dumps(valores), ahora(), u["usuario"], ahora(), u["usuario"]))
                con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                            (num, u["usuario"], ahora(), "(caso creado)", None, b["principal"], "formulario"))
        except sqlite3.IntegrityError:
            raise Error(409, f"El caso {num:04d} ya existe")
        self._json({"ok": True, "numero": num})

    def api_put_casos(self, p, q):
        u = self._usuario()
        num = int(p[0])
        b = self._cuerpo()
        origen = b.get("origen") if b.get("origen") in ("formulario", "importacion", "relleno_no", "ia_revision", "deshacer") else "formulario"
        with LOCK, db() as con:
            r = con.execute("SELECT * FROM casos WHERE numero=?", (num,)).fetchone()
            if not r:
                raise Error(404, "Caso no encontrado")
            if r["estado"] == "validado" and u["rol"] not in REVISAN:
                raise Error(403, "Caso validado: solo un data manager o un cardiólogo revisor puede modificarlo")
            valores = json.loads(r["valores"])
            ia = json.loads(r["ia"] or "{}")
            principal, sec, estado = r["principal"], json.loads(r["secundarias"]), r["estado"]
            cambios = []
            if "principal" in b or "secundarias" in b:
                np_ = b.get("principal", principal)
                ns = [s for s in b.get("secundarias", sec) if s in GRUPOS_TODOS and s != np_]
                if np_ not in GRUPOS_PRINCIPALES:
                    raise Error(400, "Enfermedad principal no válida")
                if np_ != principal:
                    cambios.append(("(enfermedad principal)", principal, np_))
                if ns != sec:
                    cambios.append(("(diagnósticos secundarios)", ",".join(sec), ",".join(ns)))
                principal, sec = np_, ns
                b.setdefault("valores", {}).update(diagnosticos(principal, sec))
            for k, v in (b.get("valores") or {}).items():
                if k in ("site_id", "patient_id", "authored_at"):
                    continue
                if not re.fullmatch(r"[a-z0-9_]{1,80}", k):
                    raise Error(400, f"Campo no válido: {k}")
                if v == "":
                    v = None
                if valores.get(k) != v:
                    cambios.append((k, valores.get(k), v))
                    if v is None:
                        valores.pop(k, None)
                    else:
                        valores[k] = v
            # Lo que una persona cambia deja de estar "pendiente de revisar" de la IA
            revisados = marcar_por_campos(ia, [c for c, _, _ in cambios if not c.startswith("(")])
            if any(c.startswith("(diagn") or c.startswith("(enfermedad") for c, _, _ in cambios) and "_diagnosticos" in ia \
                    and not ia["_diagnosticos"].get("revisado"):
                ia["_diagnosticos"]["revisado"] = True
                revisados.append("_diagnosticos")
            pedir = b.get("ia_revisar") or []
            for k in (list(ia) if pedir == "*" else pedir):
                if k in ia and not ia[k].get("revisado"):
                    ia[k]["revisado"] = True
                    revisados.append(k)
            cambios += [("(IA revisado)", None, k) for k in revisados]
            # Deshacer una confirmación en bloque: esos datos de la IA vuelven a estar pendientes
            for k in b.get("ia_desrevisar") or []:
                if k in ia and ia[k].get("revisado") and k not in revisados:
                    ia[k]["revisado"] = False
                    cambios.append(("(IA: revisión deshecha)", None, k))
            if b.get("estado") in ("borrador", "completo", "validado") and b["estado"] != estado:
                if (b["estado"] == "validado" or estado == "validado") and u["rol"] not in REVISAN:
                    raise Error(403, "Solo un data manager o un cardiólogo revisor puede validar")
                if b["estado"] == "validado" and "DUDA" in valores.values():
                    raise Error(409, "No se puede validar: el caso tiene dudas sin resolver")
                if b["estado"] == "validado" and ia_pendientes(ia, valores):
                    raise Error(409, f"No se puede validar: quedan {len(ia_pendientes(ia, valores))} datos de la IA sin revisar")
                if b["estado"] == "validado" and eventos_posteriores(valores):
                    raise Error(409, "No se puede validar: hay eventos con fecha posterior a la del último seguimiento")
                cambios.append(("(estado)", estado, b["estado"]))
                estado = b["estado"]
            if cambios:
                t = ahora()
                con.execute("""UPDATE casos SET principal=?, secundarias=?, valores=?, estado=?, ia=?, modificado=?, modificado_por=?
                               WHERE numero=?""", (principal, json.dumps(sec), json.dumps(valores), estado, json.dumps(ia), t, u["usuario"], num))
                con.executemany("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                                [(num, u["usuario"], t, c, None if a is None else str(a), None if d is None else str(d), origen)
                                 for c, a, d in cambios])
            r = con.execute("SELECT * FROM casos WHERE numero=?", (num,)).fetchone()
        self._json(caso_a_dict(r))

    def api_post_ia(self, p, q):
        """Importa propuestas de la IA local (solo data managers)."""
        u = self._usuario(rol="dm")
        if not p or p[0] != "importar":
            raise Error(404, "No encontrado")
        props = self._cuerpo().get("propuestas") or []
        if not isinstance(props, list) or len(props) > 1000:
            raise Error(400, "Envíe una lista de propuestas (máximo 1000)")
        with LOCK, db() as con:
            res = [aplicar_propuesta(con, x, u["usuario"]) for x in props]
        self._json({"resultados": res})

    # ---- pistas clínicas para la IA ---------------------------------------------
    def api_get_pistas(self, p, q):
        self._usuario()
        with db() as con:
            filas = [dict(r) for r in con.execute("SELECT * FROM pistas_ia ORDER BY codigo")]
        self._json({"pistas": {f["codigo"]: f["texto"] for f in filas}, "detalle": filas})

    def api_put_pistas(self, p, q):
        u = self._usuario(rol=REVISAN)
        codigo = p[0] if p else ""
        if not re.fullmatch(r"[a-z0-9_]{1,80}", codigo):
            raise Error(400, "Variable no válida")
        b = self._cuerpo()
        texto = str(b.get("texto") or "").strip()[:1500]
        with LOCK, db() as con:
            antes = con.execute("SELECT texto FROM pistas_ia WHERE codigo=?", (codigo,)).fetchone()
            if b.get("restaurar"):
                con.execute("DELETE FROM pistas_ia WHERE codigo=?", (codigo,))
                texto = None
            else:
                con.execute("INSERT OR REPLACE INTO pistas_ia VALUES(?,?,?,?)", (codigo, texto, u["usuario"], ahora()))
            con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                        (None, u["usuario"], ahora(), f"(pista IA) {codigo}", antes["texto"] if antes else None, texto, "formulario"))
        self._json({"ok": True})

    def api_delete_casos(self, p, q):
        """Elimina un caso. Cualquier usuario puede eliminar un caso NO validado; uno validado, solo un data manager.
        El caso se guarda entero en la papelera, de donde un data manager puede recuperarlo."""
        u = self._usuario()
        num = int(p[0])
        with LOCK, db() as con:
            r = con.execute("SELECT * FROM casos WHERE numero=?", (num,)).fetchone()
            if not r:
                raise Error(404, "Caso no encontrado")
            if r["estado"] == "validado" and u["rol"] != "dm":
                raise Error(403, "Caso validado: solo un data manager puede eliminarlo")
            con.execute("INSERT INTO casos_borrados(numero,datos,borrado_por,fecha) VALUES(?,?,?,?)",
                        (num, json.dumps(dict(r)), u["usuario"], ahora()))
            con.execute("DELETE FROM casos WHERE numero=?", (num,))
            con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                        (num, u["usuario"], ahora(), "(caso eliminado)", r["estado"], None, "formulario"))
        self._json({"ok": True})

    def api_get_papelera(self, p, q):
        self._usuario(rol="dm")
        with db() as con:
            filas = con.execute("SELECT id, numero, datos, borrado_por, fecha FROM casos_borrados ORDER BY fecha DESC").fetchall()
        out = []
        for f in filas:
            d = json.loads(f["datos"])
            out.append({"id": f["id"], "numero": f["numero"], "principal": d.get("principal"), "secundarias": json.loads(d.get("secundarias") or "[]"),
                        "estado": d.get("estado"), "borrado_por": f["borrado_por"], "fecha": f["fecha"]})
        self._json(out)

    def api_post_papelera(self, p, q):
        """Recupera un caso de la papelera (solo data managers)."""
        u = self._usuario(rol="dm")
        b = self._cuerpo()
        with LOCK, db() as con:
            f = con.execute("SELECT * FROM casos_borrados WHERE id=?", (int(b.get("id") or 0),)).fetchone()
            if not f:
                raise Error(404, "Ese caso ya no está en la papelera")
            if con.execute("SELECT 1 FROM casos WHERE numero=?", (f["numero"],)).fetchone():
                raise Error(409, f"Ya existe otro caso con el número {f['numero']:04d}: no se puede recuperar encima")
            d = json.loads(f["datos"])
            cols = [c[1] for c in con.execute("PRAGMA table_info(casos)")]
            d = {k: d[k] for k in cols if k in d}
            con.execute(f"INSERT INTO casos({','.join(d)}) VALUES({','.join('?' * len(d))})", list(d.values()))
            con.execute("DELETE FROM casos_borrados WHERE id=?", (f["id"],))
            con.execute("INSERT INTO auditoria(numero,usuario,fecha,campo,antes,despues,origen) VALUES(?,?,?,?,?,?,?)",
                        (f["numero"], u["usuario"], ahora(), "(caso recuperado de la papelera)", None, None, "formulario"))
        self._json({"ok": True, "numero": f["numero"]})

    # ---- auditoría -----------------------------------------------------------
    def api_get_auditoria(self, p, q):
        self._usuario()
        lim = min(int((q.get("limite") or ["200"])[0]), 1000)
        with db() as con:
            if q.get("caso"):
                rows = con.execute("SELECT * FROM auditoria WHERE numero=? ORDER BY id DESC LIMIT ?",
                                   (int(q["caso"][0]), lim)).fetchall()
            else:
                rows = con.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (lim,)).fetchall()
        self._json([dict(r) for r in rows])

    # ---- exportación -------------------------------------------------------
    def api_get_exportar(self, p, q):
        self._usuario(rol="dm")
        fmt = p[0] if p else "xlsx"
        solo_val = (q.get("validados") or ["0"])[0] == "1"
        desc = "-1" if (q.get("desconocido") or [""])[0] == "-1" else "blanco"
        reg = filas_exportacion(False, solo_val, desc)
        loc = filas_exportacion(True, solo_val)
        sello = dt.datetime.now().strftime("%Y%m%d_%H%M")
        if fmt == "csv":
            s = io.StringIO()
            csv.writer(s, delimiter=";").writerows(reg)
            return self._descarga(("\ufeff" + s.getvalue()).encode("utf-8"), f"WILLEM_{SITE_ID}_{sello}.csv", "text/csv; charset=utf-8")
        hojas = [("WILLEM_registro", reg)]
        if len(loc[0]) > 1:
            hojas.append(("Solo_local_NO_ENVIAR", loc))
        marcas = filas_marcas(solo_val)
        if len(marcas) > 1:
            hojas.append(("Desconocido_Duda_NO_ENVIAR", marcas))
        with db() as con:
            notas = [[r["numero"], json.loads(r["valores"]).get("nota_revision")] for r in con.execute("SELECT numero, valores FROM casos ORDER BY numero")]
        notas = [n for n in notas if str(n[1] or "").strip()]
        if notas:
            hojas.append(("Notas_revision_NO_ENVIAR", [["patient_id", "nota_revision"]] + notas))
        data = crear_xlsx(hojas)
        self._descarga(data, f"WILLEM_{SITE_ID}_{sello}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def api_get_columnas(self, p, q):
        self._usuario()
        self._json({"registro": columnas_exportacion(False), "local": columnas_exportacion(True)})

    # ---- libro llave -------------------------------------------------------
    def api_get_llave(self, p, q):
        if CFG["nas"]:
            self._usuario(rol="dm")
            return self._json({"disponible": False, "nas": True, "filas": []})
        self._usuario(rol="dm")
        con = llave_db()
        if con is None:
            return self._json({"disponible": False, "ruta": CFG["llave"], "filas": []})
        with con:
            texto = (q.get("q") or [""])[0].strip()
            if texto:
                like = f"%{texto}%"
                rows = con.execute("""SELECT * FROM llave WHERE cip LIKE ? OR carm LIKE ? OR nhc LIKE ?
                                      OR CAST(numero AS TEXT) LIKE ? ORDER BY numero DESC LIMIT 50""",
                                   (like, like, like, like)).fetchall()
            else:
                rows = con.execute("SELECT * FROM llave ORDER BY numero DESC LIMIT 50").fetchall()
            total = con.execute("SELECT COUNT(*) FROM llave").fetchone()[0]
        self._json({"disponible": True, "ruta": CFG["llave"], "total": total, "filas": [dict(r) for r in rows]})

    def api_post_llave(self, p, q):
        u = self._usuario(rol="dm")
        b = self._cuerpo()
        cip, carm, nhc = [(b.get(k) or "").strip().upper() for k in ("cip", "carm", "nhc")]
        if not (cip or carm or nhc):
            raise Error(400, "Introduzca al menos CIP, CARM o NHC")
        con = llave_db()
        if con is None:
            raise Error(503, "El libro llave no está disponible (¿USB conectado?)")
        with LOCK, con:
            for campo, val in (("cip", cip), ("carm", carm), ("nhc", nhc)):
                if val:
                    ya = con.execute(f"SELECT numero FROM llave WHERE {campo}=?", (val,)).fetchone()
                    if ya:
                        raise Error(409, f"Este paciente ya tiene el caso nº {ya['numero']:04d}")
            num = siguiente_numero(con)
            con.execute("INSERT INTO llave VALUES(?,?,?,?,?,?,?)",
                        (num, cip or None, carm or None, nhc or None, (b.get("notas") or "").strip(), ahora(), u["usuario"]))
        self._json({"ok": True, "numero": num})


# ---------------------------------------------------------------------------
GRUPOS_PRINCIPALES = ["ISQ", "IC", "EAO", "MCH", "QTL", "ATTR", "IAM", "HTA", "OTRO"]  # diagnósticos del estudio
GRUPOS_TODOS = GRUPOS_PRINCIPALES
DIAG = {"ISQ": "ischemic_cardiomyopathy", "IC": "heart_failure", "EAO": "aortic_stenosis",
        "MCH": "hypertrophic_cardiomyopathy", "QTL": "long_qt_syndrome", "ATTR": "amyloidosis_attr",
        "IAM": "myocardial_infarction", "HTA": "hypertensive_disease"}  # "OTRO" va en other_disease (texto)


def diagnosticos(principal, sec):
    act = {principal, *sec}
    return {codigo: (1 if g in act else 0) for g, codigo in DIAG.items()}


def siguiente_numero(con_llave=None):
    with db() as con:
        m = con.execute("SELECT COALESCE(MAX(numero),0) FROM casos").fetchone()[0]
    try:
        cl = con_llave or llave_db()
        if cl is not None:
            m = max(m, cl.execute("SELECT COALESCE(MAX(numero),0) FROM llave").fetchone()[0])
    except sqlite3.Error:
        pass
    return m + 1


def clave_proxy(carpeta):
    """Clave que el proxy inverso de DSM debe enviar en la cabecera X-Willem-Proxy.
    Se crea sola la primera vez en <datos>/clave_proxy.txt (o se toma de WILLEM_CLAVE_PROXY)."""
    clave = (os.environ.get("WILLEM_CLAVE_PROXY") or "").strip()
    if clave:
        return clave
    ruta = os.path.join(carpeta, "clave_proxy.txt")
    try:
        with open(ruta, encoding="utf-8") as f:
            clave = f.read().strip()
    except FileNotFoundError:
        pass
    if not clave:
        clave = secrets.token_urlsafe(32)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(clave + "\n")
        os.chmod(ruta, 0o600)
    return clave


# ===========================================================================
def ip_local():
    """Dirección de este equipo en la red local (no envía nada: solo pregunta por dónde saldría)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = None
    finally:
        s.close()
    return ip if ip and not ip.startswith("127.") else None


def main():
    ap = argparse.ArgumentParser(description="Registro WILLEM – servidor local")
    ap.add_argument("--red", action="store_true", help="Permitir acceso desde otros PCs de la red local")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--demo", action="store_true", help="Usar base de demostración con pacientes inventados")
    ap.add_argument("--datos", default=os.path.join(BASE, "datos"), help="Carpeta de la base de datos")
    ap.add_argument("--llave", default=os.path.join(BASE, "llave", "llave.sqlite"), help="Ruta del libro llave (offline)")
    ap.add_argument("--no-navegador", action="store_true")
    ap.add_argument("--nas", action="store_true",
                    help="Servidor central en el NAS: sin libro llave, doble factor obligatorio, solo tras HTTPS")
    ap.add_argument("--doble-factor", action="store_true", help="Exigir doble factor (código del móvil) también fuera del NAS")
    ap.add_argument("--certificado", help="Servir por HTTPS con este certificado (PEM)")
    ap.add_argument("--clave-certificado", help="Clave privada del certificado (PEM)")
    a = ap.parse_args()

    CFG["demo"] = a.demo
    CFG["nas"] = a.nas
    CFG["2fa"] = a.nas or a.doble_factor
    CFG["https"] = bool(a.certificado)
    if a.nas:
        a.red = True  # dentro del contenedor; desde fuera solo se llega por el proxy HTTPS del NAS
    CFG["db"] = os.path.join(a.datos, "demo.sqlite" if a.demo else "registro.sqlite")
    CFG["llave"] = os.path.join(a.datos, "llave_demo", "llave.sqlite") if a.demo else os.path.abspath(a.llave)
    CFG["red_fs"] = es_ruta_de_red(a.datos)
    iniciar_db()
    if a.demo:
        os.makedirs(os.path.dirname(CFG["llave"]), exist_ok=True)
        import demo
        demo.poblar(CFG["db"], CFG["llave"], hash_pw, diagnosticos)
    diccionario()

    if a.nas:
        CFG["clave_proxy"] = clave_proxy(a.datos)
    if a.nas and not a.demo:
        # Copia diaria en <datos>/copias (las copias de seguridad del NAS deben incluir esa carpeta)
        threading.Thread(target=copias_diarias, args=(os.path.join(a.datos, "copias"),), daemon=True).start()
    host = "0.0.0.0" if a.red else "127.0.0.1"
    srv = ThreadingHTTPServer((host, a.puerto), Manejador)
    if a.certificado:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(a.certificado, a.clave_certificado)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    url = f"{'https' if a.certificado else 'http'}://127.0.0.1:{a.puerto}"
    print("\n  ╔══════════════════════════════════════════════════════╗")
    print("  ║   Registro WILLEM · H.C.U. Virgen de la Arrixaca      ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print(f"  Abierto en: {url}" + ("   (MODO DEMOSTRACIÓN)" if a.demo else ""))
    if a.nas:
        print("  Acceso: a través del proxy inverso HTTPS del NAS (este puerto no debe publicarse fuera del NAS)")
    elif a.red:
        ip = ip_local()
        if ip:
            print(f"  Desde otros equipos de la misma red (PC, iPad, móvil): {'https' if a.certificado else 'http'}://{ip}:{a.puerto}")
        else:
            print("  No se ha podido averiguar la dirección de este equipo en la red (¿está conectado a la wifi?).")
        if not a.certificado:
            print("  AVISO: sin HTTPS, lo que se escribe viaja sin cifrar por la red local. Úselo solo en una red de confianza.")
    print(f"  Base de datos: {CFG['db']}" + ("   (carpeta de red)" if CFG["red_fs"] else ""))
    if CFG["red_fs"]:
        print("  AVISO: con la base en una carpeta de red, abra el servidor en UN SOLO ordenador a la vez.")
    print(f"  Libro llave:   {'(no hay: en el NAS solo se guardan casos con número)' if CFG['nas'] else CFG['llave']}")
    if CFG["2fa"]:
        print("  Doble factor:  obligatorio (código de 6 cifras del móvil)")
    print("  Para cerrar: Ctrl+C o cierre esta ventana.\n")
    if not a.no_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Servidor detenido.")


if __name__ == "__main__":
    main()
