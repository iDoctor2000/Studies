"""
IA SIMULADA para las pruebas: imita la API de Ollama (/api/tags y /api/chat) y contesta
con reglas sencillas. Incluye errores a propósito (una cita inventada, un número fuera de
rango, datos de una prueba no marcada) para comprobar que el extractor los detecta.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _frag(texto, m, ancho=50):
    return texto[max(0, m.start() - 5):min(len(texto), m.end() + ancho)].split("\n")[0].strip()


def contestar(usuario, esquema):
    partes = usuario.split("-----")
    texto = partes[1] if len(partes) > 2 else usuario
    props = esquema.get("properties", {})
    if "diagnosticos" in props:
        out = []
        for g, rx in (("IC", r"insuficiencia cardiaca"), ("ISQ", r"cardiopat[ií]a isqu[eé]mica"), ("EAO", r"estenosis a[oó]rtica"),
                      ("ATTR", r"amiloidosis")):
            m = re.search(rx, texto, re.I)
            if m:
                out.append({"codigo": g, "texto": None, "cita": _frag(texto, m)})
        return {"diagnosticos": out, "principal": "IC" if any(d["codigo"] == "IC" for d in out) else None}
    if "por_insuficiencia_cardiaca" in props:
        m = re.search(r"insuficiencia cardiaca", texto, re.I)
        return {"por_insuficiencia_cardiaca": 1 if m else 0, "fallecimiento": 1 if re.search(r"exitus", texto, re.I) else 0,
                "cita": _frag(texto, m) if m else texto.strip().split("\n")[0][:80]}
    r = {}
    for cod, p in props.items():
        res = {"valor": None, "cita": None}
        if "fecha" in p["properties"]:
            res["fecha"] = None
        if cod == "echocardiography_lvef":
            m = re.search(r"FEVI[^\d\n]{0,10}(\d+)\s*%", texto)
            if m:
                res = {"valor": int(m.group(1)), "cita": _frag(texto, m, 10)}
        elif cod == "echocardiography_procedure":
            m = re.search(r"Ecocardiograma \((\d\d)/(\d\d)/(\d{4})\)", texto)
            if m:
                res = {"valor": f"{m.group(3)}-{m.group(2)}-{m.group(1)}", "cita": m.group(0)}
        elif cod == "hypertension":
            m = re.search(r"\b(No HTA|HTA)\b", texto)
            if m:
                res = {"valor": 0 if m.group(1).startswith("No") else 1, "cita": m.group(0)}
        elif cod == "diabetes":
            m = re.search(r"\bDM2\b", texto)
            if m:
                res = {"valor": "diabetes_mellitus_type_2", "cita": _frag(texto, m, 20)}
        elif cod == "nyha_functional_class":
            m = re.search(r"NYHA\s*(I{1,3}V?|IV)", texto)
            if m:
                res = {"valor": "nyha_class_" + m.group(1).lower(), "cita": m.group(0)}
        elif cod == "dyslipidaemia":  # cita INVENTADA a propósito
            res = {"valor": 1, "cita": "Dislipemia familiar grave en tratamiento con tres fármacos"}
        elif cod == "resting_heart_rate":  # número fuera de rango y que no está en la cita
            m = re.search(r"FC:\s*\d+\s*lpm", texto)
            if m:
                res = {"valor": 400, "cita": m.group(0)}
        elif cod == "natriuretic_peptide_nt_probnp":
            m = re.search(r"NT-proBNP:?\s*([\d.]+)", texto)
            if m:
                res = {"valor": float(m.group(1)), "cita": m.group(0)}
        elif cod == "prior_atrial_fibrillation":  # su pregunta llave (arritmias previas) no se contesta
            m = re.search(r"fibrilaci[oó]n auricular", texto, re.I)
            if m:
                res = {"valor": 1, "cita": _frag(texto, m, 20)}
                if "fecha" in p["properties"]:
                    res["fecha"] = None
        elif cod == "timi_coronary_grade_flow":  # resultado de una prueba que nadie ha marcado como hecha
            m = re.search(r"TIMI\s*([0-3])", texto)
            if m:
                res = {"valor": "timi_coronary_grade_flow_" + m.group(1), "cita": m.group(0)}
        if "fecha" in p["properties"] and "fecha" not in res:
            res["fecha"] = None
        r[cod] = res
    return r


class _Manejador(BaseHTTPRequestHandler):
    llamadas = []

    def log_message(self, *a):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "simulada:1"}]})
        self.send_error(404)

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Manejador.llamadas.append(b)
        usuario = b["messages"][-1]["content"]
        self._json({"message": {"role": "assistant", "content": json.dumps(contestar(usuario, b["format"]), ensure_ascii=False)}})


def arrancar(puerto=0):
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}", _Manejador.llamadas


if __name__ == "__main__":
    srv, url, _ = arrancar(11435)
    print("IA simulada en", url)
    threading.Event().wait()
