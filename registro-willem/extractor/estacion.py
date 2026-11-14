#!/usr/bin/env python3
"""
Registro WILLEM · ESTACIÓN DE INFORMES (Mac)

Interfaz gráfica para todo el circuito de informes, en una página web LOCAL:
  elegir carpeta/USB → anonimizar → revisar avisos → rellenar con IA → pasar al registro,
  con el estado de Ollama, FileVault y el registro, y acceso al libro llave.

    python3 extractor/estacion.py            (doble clic: WILLEM_Mac.command)

Seguridad: solo escucha en 127.0.0.1 (este Mac), cada sesión tiene una clave aleatoria que
viaja en la dirección de la página y se exige en todas las peticiones, y se comprueba la
cabecera Host. Nada sale del Mac salvo, al pulsar «Pasar al registro», las propuestas
anonimizadas hacia el servidor del registro que usted indique.
"""
import argparse
import datetime as dt
import glob
import http.cookiejar
import json
import mimetypes
import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "ia"))
sys.path.insert(0, RAIZ)

import revision  # noqa: E402
from cliente import ClienteIA, ErrorIA  # noqa: E402
from extraer_ia import casos_a_procesar, comprobar_modelo, ejecutar, pasos  # noqa: E402
from llave import Llave  # noqa: E402
from preguntas import cargar_preguntas, lotes, preguntables  # noqa: E402
from procesar_informes import PRIVADO_DEF, SALIDA_DEF, avisos_del_equipo, buscar_pdfs, informe_html, procesar  # noqa: E402

WEB = os.path.join(AQUI, "estacion_web")
ICONOS = os.path.join(RAIZ, "web", "js", "iconos.js")
ES_MAC = platform.system() == "Darwin"
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

AJUSTES_DEF = {"modelo": "qwen3:30b", "url_ia": "http://127.0.0.1:11434", "proveedor": "ollama",
               "url_registro": "http://127.0.0.1:8765", "usuario_registro": "", "carpeta": ""}


class Estacion:
    def __init__(self, privado, salida):
        self.privado, self.salida = os.path.abspath(privado), os.path.abspath(salida)
        os.makedirs(self.privado, exist_ok=True)
        os.makedirs(os.path.join(self.salida, "listos"), exist_ok=True)
        self.token = secrets.token_urlsafe(24)
        self.puerto = None
        self.lock = threading.Lock()
        self.trabajo = {"tipo": None, "activo": False}
        self._cache = {}
        self.registro_proc = None

    # ---------------- ajustes ----------------
    @property
    def ruta_ajustes(self):
        return os.path.join(self.privado, "estacion.json")

    def ajustes(self):
        a = dict(AJUSTES_DEF)
        try:
            with open(self.ruta_ajustes, encoding="utf-8") as f:
                a.update(json.load(f))
        except (OSError, ValueError):
            pass
        return a

    def guardar_ajustes(self, cambios):
        a = self.ajustes()
        for k in AJUSTES_DEF:
            if k in cambios and isinstance(cambios[k], str):
                a[k] = cambios[k].strip()
        if urllib.parse.urlparse(a["url_ia"]).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("La IA tiene que estar en este Mac (127.0.0.1)")
        if "cloud" in a["modelo"].lower():
            raise ValueError("Use un modelo local (no «cloud»)")
        if not re.match(r"^https?://", a["url_registro"]):
            raise ValueError("La dirección del registro debe empezar por http:// o https://")
        with open(self.ruta_ajustes, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=1)
        self._cache.clear()
        return a

    # ---------------- estado ----------------
    def _cacheado(self, clave, segundos, fn):
        t, v = self._cache.get(clave, (0, None))
        if time.time() - t > segundos:
            v = fn()
            self._cache[clave] = (time.time(), v)
        return v

    def estado_ia(self):
        a = self.ajustes()

        def mirar():
            try:
                ruta = "/api/tags" if a["proveedor"] == "ollama" else "/v1/models"
                with urllib.request.urlopen(a["url_ia"].rstrip("/") + ruta, timeout=2) as r:
                    d = json.loads(r.read())
                mods = [m.get("name") for m in d.get("models", [])] if a["proveedor"] == "ollama" else [m.get("id") for m in d.get("data", [])]
                instalado = a["modelo"] in mods or a["modelo"] + ":latest" in mods
                return {"ok": instalado, "en_marcha": True, "modelos": mods, "modelo": a["modelo"],
                        "texto": f"{a['modelo']}" if instalado else f"falta el modelo {a['modelo']}"}
            except Exception:
                return {"ok": False, "en_marcha": False, "modelos": [], "modelo": a["modelo"], "texto": "Ollama no está abierto"}
        return self._cacheado("ia", 4, mirar)

    def estado_equipo(self):
        def mirar():
            avisos = avisos_del_equipo(self.privado)
            fv = None
            if ES_MAC:
                fv = not any("FileVault" in x for x in avisos)
            return {"filevault": fv, "avisos": avisos, "mac": ES_MAC}
        return self._cacheado("equipo", 60, mirar)

    def estado_registro(self):
        a = self.ajustes()

        def mirar():
            try:
                with urllib.request.urlopen(a["url_registro"].rstrip("/") + "/api/estado", timeout=2) as r:
                    d = json.loads(r.read())
                return {"ok": True, "url": a["url_registro"], "configurar": d.get("necesita_configuracion"), "demo": d.get("demo")}
            except Exception:
                return {"ok": False, "url": a["url_registro"]}
        return self._cacheado("registro", 4, mirar)

    def importadas(self):
        try:
            with open(os.path.join(self.privado, "importadas.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def propuestas(self):
        """[(numero, ruta, mtime, ya_importada)]"""
        imp = self.importadas()
        out = []
        for r in sorted(glob.glob(os.path.join(self.salida, "propuestas_ia", "caso_*.json"))):
            m = re.search(r"caso_(\d+)\.json$", r)
            mt = os.path.getmtime(r)
            out.append((int(m.group(1)), r, mt, imp.get(str(int(m.group(1))), 0) >= mt))
        return out

    def cuentas(self):
        listos = glob.glob(os.path.join(self.salida, "listos", "caso_*.json"))
        casos_listos = {re.search(r"caso_(\d+)_", os.path.basename(x)).group(1) for x in listos}
        props = self.propuestas()
        try:
            n_llave = Llave(os.path.join(self.privado, "llave_willem.sqlite")).con.execute("SELECT COUNT(*) FROM llave").fetchone()[0]
        except Exception:
            n_llave = 0
        try:
            sin_ia = len(casos_a_procesar(self.salida))
        except Exception:
            sin_ia = 0
        return {"llave": n_llave, "listos": len(listos), "casos_listos": len(casos_listos),
                "pendientes": len(glob.glob(os.path.join(self.privado, "pendientes_de_revisar", "*.avisos.json"))),
                "sin_ia": sin_ia, "propuestas": len(props), "sin_pasar": sum(1 for p in props if not p[3])}

    def entrada(self):
        c = self.ajustes()["carpeta"]
        if not c or not os.path.isdir(c):
            return {"carpeta": c, "existe": False, "pdfs": 0}
        return {"carpeta": c, "nombre": os.path.basename(c.rstrip("/")) or c, "existe": True, "pdfs": len(buscar_pdfs([c]))}

    def ultimo(self):
        try:
            with open(os.path.join(self.privado, "ultimo_proceso.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        inf = d.get("informes", [])
        return {"fecha": d.get("fecha"), "total": len(inf), **{k: sum(1 for x in inf if x["estado"] == k) for k in ("listo", "revisar", "bloqueado")},
                "bloqueados": [{"archivo": x["archivo"], "motivo": "; ".join(x.get("bloqueos") or [])} for x in inf if x["estado"] == "bloqueado"]}

    def estado(self):
        return {"ia": self.estado_ia(), "equipo": self.estado_equipo(), "registro": self.estado_registro(),
                "cuentas": self.cuentas(), "entrada": self.entrada(), "ultimo": self.ultimo(), "trabajo": self.ver_trabajo(),
                "ajustes": {k: v for k, v in self.ajustes().items()}, "carpetas": {"privado": self.privado, "salida": self.salida}}

    # ---------------- trabajos en segundo plano ----------------
    def ver_trabajo(self):
        with self.lock:
            t = dict(self.trabajo)
            t["lineas"] = list(t.get("lineas", []))[-300:]
            return t

    def lanzar(self, tipo, titulo, fn):
        with self.lock:
            if self.trabajo.get("activo"):
                raise ValueError("Ya hay un trabajo en marcha: espere a que termine")
            self.trabajo = {"tipo": tipo, "titulo": titulo, "activo": True, "hecho": 0, "total": 0, "mensaje": "Empezando…",
                            "lineas": [], "inicio": time.time(), "fin": None, "error": None, "resultado": None}

        def correr():
            try:
                res = fn()
                with self.lock:
                    self.trabajo.update(resultado=res, mensaje="Terminado")
            except Exception as e:  # el error se enseña en la interfaz
                traceback.print_exc()
                with self.lock:
                    self.trabajo.update(error=str(e), mensaje="Se ha detenido por un error")
            finally:
                with self.lock:
                    self.trabajo.update(activo=False, fin=time.time())
                self._cache.clear()
        threading.Thread(target=correr, daemon=True).start()

    def _avance(self, hecho=None, total=None, mensaje=None, linea=None):
        with self.lock:
            if hecho is not None:
                self.trabajo["hecho"] = hecho
            if total is not None:
                self.trabajo["total"] = total
            if mensaje is not None:
                self.trabajo["mensaje"] = mensaje
            if linea:
                self.trabajo["lineas"].append(linea)

    # 1 · anonimizar
    def anonimizar(self):
        carpeta = self.ajustes()["carpeta"]
        if not carpeta or not os.path.isdir(carpeta):
            raise ValueError("Elija primero la carpeta o el USB con los informes")
        pdfs = buscar_pdfs([carpeta])
        if not pdfs:
            raise ValueError("En esa carpeta no hay ningún PDF")

        def fn():
            self._avance(0, len(pdfs), f"Leyendo {len(pdfs)} informe(s)…")
            nombres = {"listo": "listo", "revisar": "para revisar", "bloqueado": "BLOQUEADO"}

            def prog(i, total, r):
                self._avance(i, total, f"Informe {i} de {total}",
                             f"{r['archivo']}: {nombres[r['estado']]}" + (f" · caso {r['numero']}" if r.get("numero") else "")
                             + (f" — {r['bloqueos'][0]}" if r["bloqueos"] else ""))
            res, _ = procesar(pdfs, self.privado, self.salida, "estacion", progreso=prog)
            carpeta_inf = os.path.join(self.privado, "resumenes_de_proceso")
            os.makedirs(carpeta_inf, exist_ok=True)
            ruta = os.path.join(carpeta_inf, f"proceso_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(informe_html(res, avisos_del_equipo(self.privado), self.privado, self.salida))
            return {"resumen": ruta, **{k: sum(1 for r in res if r["estado"] == k) for k in ("listo", "revisar", "bloqueado")},
                    "nuevos": sum(1 for r in res if r["nuevo"])}
        self.lanzar("anonimizar", "Anonimizar informes", fn)

    # 2 · IA
    def rellenar_ia(self, rehacer=False):
        a = self.ajustes()
        ia = ClienteIA(a["url_ia"], a["modelo"], a["proveedor"])
        comprobar_modelo(ia)
        casos = casos_a_procesar(self.salida, rehacer=rehacer)
        if not casos:
            raise ValueError("No hay casos nuevos para la IA (todos los informes listos ya tienen propuesta)")
        n_tandas = len(lotes([it for it in preguntables(cargar_preguntas()) if it["pestana"] != "Seguimiento"]))
        total = pasos(casos, n_tandas)

        def fn():
            self._avance(0, total, f"La IA va a leer {len(casos)} caso(s)…")
            hecho = [0]

            def prog(texto):
                t = texto.strip()
                if t.startswith("diagnósticos") or t.startswith("tanda") or t.startswith("seguimiento"):
                    hecho[0] += 1
                    self._avance(hecho[0], total, t.rstrip("…"))
                self._avance(linea=t)
            filas, ruta = ejecutar(ia, self.salida, casos, progreso=prog)
            self._avance(total, total)
            return {"resumen": ruta, "casos": len(filas), "campos": sum(f["campos"] for f in filas),
                    "avisos": sum(f["avisos"] for f in filas), "errores": [f"Caso {f['numero']}: {f['error']}" for f in filas if f.get("error")],
                    "segundos": round(sum(f["segundos"] for f in filas))}
        self.lanzar("ia", "Rellenar con la IA", fn)

    # 3 · pasar al registro
    def pasar_al_registro(self, usuario, clave):
        a = self.ajustes()
        url = a["url_registro"].rstrip("/")
        props = [p for p in self.propuestas() if not p[3]]
        if not props:
            raise ValueError("No hay propuestas nuevas que pasar al registro")
        if not usuario or not clave:
            raise ValueError("Escriba su usuario y contraseña del registro")

        def fn():
            self._avance(0, len(props), "Conectando con el registro…")
            abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

            def pedir(ruta, cuerpo):
                req = urllib.request.Request(url + "/api/" + ruta, data=json.dumps(cuerpo).encode(), method="POST",
                                             headers={"Content-Type": "application/json"})
                try:
                    with abridor.open(req, timeout=60) as r:
                        return json.loads(r.read())
                except urllib.error.HTTPError as e:
                    try:
                        msg = json.loads(e.read()).get("error")
                    except Exception:
                        msg = None
                    raise RuntimeError(msg or f"El registro respondió con error {e.code}")
                except urllib.error.URLError:
                    raise RuntimeError(f"No se puede conectar con el registro en {url}. ¿Está abierto?")
            pedir("login", {"usuario": usuario, "clave": clave})
            imp = self.importadas()
            resultados = []
            for i in range(0, len(props), 10):
                tanda = props[i:i + 10]
                datos = []
                for _, ruta, _, _ in tanda:
                    with open(ruta, encoding="utf-8") as f:
                        datos.append(json.load(f))
                r = pedir("ia/importar", {"propuestas": datos})
                for (num, _, mt, _), res in zip(tanda, r.get("resultados", [])):
                    resultados.append(res)
                    if res.get("accion") in ("creado", "actualizado"):
                        imp[str(num)] = mt
                    linea = {"creado": "creado", "actualizado": "completado", "omitido": "no importado"}.get(res.get("accion"), res.get("accion"))
                    self._avance(linea=f"Caso {num}: {linea}" + (f" · {res.get('aplicados')} datos" if res.get("aplicados") else "")
                                 + (f" · {res.get('motivo')}" if res.get("motivo") else ""))
                self._avance(min(i + 10, len(props)), len(props), f"Enviados {min(i + 10, len(props))} de {len(props)}")
                with open(os.path.join(self.privado, "importadas.json"), "w", encoding="utf-8") as f:
                    json.dump(imp, f)
            try:
                pedir("logout", {})
            except Exception:
                pass
            return {k: sum(1 for x in resultados if x.get("accion") == k) for k in ("creado", "actualizado", "omitido")} | {"url": url}
        self.lanzar("registro", "Pasar al registro", fn)

    # ---------------- libro llave ----------------
    def llave(self, q=""):
        ll = Llave(os.path.join(self.privado, "llave_willem.sqlite"))
        filas = ll.con.execute("""SELECT l.numero, l.carm, l.cip, l.nhc, d.dni, l.creado,
                                  (SELECT COUNT(*) FROM informes i WHERE i.numero=l.numero) AS n_inf,
                                  (SELECT MAX(fecha_ingreso) FROM informes i WHERE i.numero=l.numero) AS ultimo
                                  FROM llave l LEFT JOIN llave_dni d ON d.numero=l.numero ORDER BY l.numero DESC""").fetchall()
        q = (q or "").strip().upper()
        out = [dict(r) for r in filas]
        if q:
            out = [r for r in out if any(q in str(r[k] or "").upper() for k in ("carm", "cip", "nhc", "dni")) or q.lstrip("0") == str(r["numero"])]
        return {"filas": out[:500], "total": len(filas), "primer_numero": ll.ajuste("primer_numero", "1")}

    def exportar_llave(self):
        from procesar_informes import exportar_llave
        ll = Llave(os.path.join(self.privado, "llave_willem.sqlite"))
        exportar_llave(ll, self.privado)
        return os.path.join(self.privado, f"LLAVE_WILLEM_NO_COMPARTIR_{dt.date.today().isoformat()}.xlsx")


def abrir_en_finder(ruta, seleccionar=False):
    if ES_MAC and ruta and os.path.exists(ruta):
        subprocess.Popen(["open", "-R", ruta] if seleccionar else ["open", ruta])
        return True
    return False


class Manejador(BaseHTTPRequestHandler):
    E: Estacion = None

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return (self.headers.get("Host") or "") in (f"127.0.0.1:{self.E.puerto}", f"localhost:{self.E.puerto}")

    def do_GET(self):
        if not self._host_ok():
            return self.send_error(403)
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/"):
            return self._api("GET", u)
        nombre = {"/": "index.html"}.get(u.path, u.path.lstrip("/"))
        ruta = ICONOS if nombre == "iconos.js" else os.path.normpath(os.path.join(WEB, nombre))
        if ruta != ICONOS and (not ruta.startswith(WEB) or not os.path.isfile(ruta)):
            return self.send_error(404)
        with open(ruta, "rb") as f:
            data = f.read()
        tipo = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", tipo + ("; charset=utf-8" if tipo.startswith("text") or "javascript" in tipo else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._host_ok():
            return self.send_error(403)
        self._api("POST", urllib.parse.urlparse(self.path))

    def _api(self, metodo, u):
        if not secrets.compare_digest(self.headers.get("X-Token") or "", self.E.token):
            return self._json({"error": "Sesión no válida: cierre esta pestaña y vuelva a abrir WILLEM desde el Mac"}, 403)
        E = self.E
        q = urllib.parse.parse_qs(u.query)
        b = {}
        if metodo == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            b = json.loads(self.rfile.read(n) or b"{}") if n else {}
        ruta = u.path[5:]
        try:
            if metodo == "GET" and ruta == "estado":
                return self._json(E.estado())
            if metodo == "GET" and ruta == "trabajo":
                return self._json(E.ver_trabajo())
            if metodo == "GET" and ruta == "avisos":
                return self._json(revision.listar(E.privado))
            if metodo == "GET" and ruta == "llave":
                return self._json(E.llave((q.get("q") or [""])[0]))
            if metodo == "POST" and ruta == "elegir":
                if not ES_MAC:
                    raise ValueError("Escriba la ruta de la carpeta en Ajustes (el selector solo funciona en el Mac)")
                r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Elija la carpeta o el USB con los informes de alta (PDF)")'],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    return self._json({"cancelado": True})
                E.guardar_ajustes({"carpeta": r.stdout.strip()})
                return self._json(E.entrada())
            if metodo == "POST" and ruta == "ajustes":
                if b.get("carpeta") and not os.path.isdir(os.path.expanduser(b["carpeta"])):
                    raise ValueError("Esa carpeta no existe")
                if b.get("carpeta"):
                    b["carpeta"] = os.path.abspath(os.path.expanduser(b["carpeta"]))
                a = E.guardar_ajustes(b)
                if b.get("primer_numero"):
                    ll = Llave(os.path.join(E.privado, "llave_willem.sqlite"))
                    if ll.con.execute("SELECT COUNT(*) FROM llave").fetchone()[0]:
                        raise ValueError("El libro llave ya tiene casos: el primer número ya no se puede cambiar")
                    ll.poner_ajuste("primer_numero", int(b["primer_numero"]))
                return self._json(a)
            if metodo == "POST" and ruta == "anonimizar":
                E.anonimizar()
                return self._json({"ok": True})
            if metodo == "POST" and ruta == "ia":
                E.rellenar_ia(bool(b.get("rehacer")))
                return self._json({"ok": True})
            if metodo == "POST" and ruta == "registro":
                E.pasar_al_registro((b.get("usuario") or "").strip(), b.get("clave") or "")
                E.guardar_ajustes({"usuario_registro": (b.get("usuario") or "").strip()})
                return self._json({"ok": True})
            if metodo == "POST" and ruta == "avisos":
                return self._json(revision.resolver(E.privado, E.salida, b.get("base"), b.get("id"), b.get("decision", "visto"), b.get("texto", "")))
            if metodo == "POST" and ruta == "descartar":
                revision.descartar(E.privado, b.get("base"))
                return self._json({"ok": True})
            if metodo == "POST" and ruta == "llave/exportar":
                r = E.exportar_llave()
                return self._json({"ruta": r, "abierto": abrir_en_finder(r, True)})
            if metodo == "POST" and ruta == "abrir":
                destinos = {"listos": os.path.join(E.salida, "listos"), "propuestas": os.path.join(E.salida, "propuestas_ia"),
                            "privado": E.privado, "pendientes": os.path.join(E.privado, "pendientes_de_revisar")}
                ruta_a = destinos.get(b.get("que"))
                if b.get("que") == "resumen":
                    ruta_a = (E.ver_trabajo().get("resultado") or {}).get("resumen")
                if not ruta_a:
                    raise ValueError("No hay nada que abrir")
                os.makedirs(ruta_a, exist_ok=True) if b.get("que") != "resumen" else None
                return self._json({"ruta": ruta_a, "abierto": abrir_en_finder(ruta_a)})
            if metodo == "POST" and ruta == "ollama":
                return self._json(arrancar_ollama())
            if metodo == "POST" and ruta == "registro/arrancar":
                return self._json(arrancar_registro(E))
            return self._json({"error": "No encontrado"}, 404)
        except (ValueError, ErrorIA, RuntimeError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"Error interno: {e}"}, 500)


def arrancar_ollama():
    if not ES_MAC:
        return {"ok": False, "mensaje": "Arranque Ollama a mano (ollama serve)"}
    for orden in (["brew", "services", "start", "ollama"], ["/opt/homebrew/bin/brew", "services", "start", "ollama"], ["open", "-a", "Ollama"]):
        try:
            if subprocess.run(orden, capture_output=True, timeout=60).returncode == 0:
                return {"ok": True, "mensaje": "Ollama arrancando… espere unos segundos"}
        except (OSError, subprocess.TimeoutExpired):
            continue
    return {"ok": False, "mensaje": "No se ha podido arrancar Ollama. En el Terminal: brew services start ollama"}


def arrancar_registro(E):
    url = E.ajustes()["url_registro"]
    p = urllib.parse.urlparse(url)
    if p.hostname not in ("127.0.0.1", "localhost"):
        return {"ok": False, "mensaje": "El registro no está en este Mac: no se puede arrancar desde aquí"}
    if E.estado_registro().get("ok"):
        if ES_MAC:
            subprocess.Popen(["open", url])
        return {"ok": True, "mensaje": "El registro ya está abierto"}
    log = open(os.path.join(E.privado, "registro_servidor.log"), "a")
    E.registro_proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, "servidor.py"), "--puerto", str(p.port or 8765), "--no-navegador"],
                                       stdout=log, stderr=log, cwd=RAIZ)
    for _ in range(40):
        time.sleep(0.25)
        E._cache.pop("registro", None)
        if E.estado_registro().get("ok"):
            if ES_MAC:
                subprocess.Popen(["open", url])
            return {"ok": True, "mensaje": "Registro abierto en este Mac"}
    return {"ok": False, "mensaje": "El registro no ha arrancado: mire registro_servidor.log en la carpeta privada"}


def puerto_libre(preferido):
    for p in list(range(preferido, preferido + 10)) + [0]:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("No hay puertos libres")


def main():
    ap = argparse.ArgumentParser(description="WILLEM · Estación de informes (interfaz gráfica local)")
    ap.add_argument("--privado", default=PRIVADO_DEF)
    ap.add_argument("--salida", default=SALIDA_DEF)
    ap.add_argument("--puerto", type=int, default=8790)
    ap.add_argument("--no-navegador", action="store_true")
    ap.add_argument("--token", help=argparse.SUPPRESS)  # solo para las pruebas automáticas
    a = ap.parse_args()
    E = Estacion(a.privado, a.salida)
    if a.token:
        E.token = a.token
    E.puerto = puerto_libre(a.puerto)
    Manejador.E = E
    srv = ThreadingHTTPServer(("127.0.0.1", E.puerto), Manejador)
    url = f"http://127.0.0.1:{E.puerto}/#t={E.token}"
    print("\n  WILLEM · Estación de informes")
    print(f"  Abierta en el navegador: {url}")
    print("  Deje esta ventana abierta mientras trabaja. Para salir, ciérrela (o pulse Ctrl+C).\n")
    if not a.no_navegador:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Estación cerrada.")
    finally:
        if E.registro_proc:
            E.registro_proc.terminate()


if __name__ == "__main__":
    main()
