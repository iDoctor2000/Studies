"""
Cliente del modelo de IA LOCAL (Ollama o LM Studio) — solo biblioteca estándar.

Por seguridad, solo se permite hablar con un servidor de ESTE ordenador (localhost):
los textos, aunque estén anonimizados, nunca salen del Mac.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

LOCALES = {"localhost", "127.0.0.1", "::1"}


class ErrorIA(Exception):
    pass


class ClienteIA:
    def __init__(self, url="http://127.0.0.1:11434", modelo="qwen3:30b", proveedor="ollama",
                 contexto=16384, tiempo_max=900, pensar=False):
        host = urllib.parse.urlparse(url).hostname
        if host not in LOCALES:
            raise ErrorIA(f"La IA debe estar en este ordenador (localhost). Dirección no permitida: {host}")
        if "cloud" in (modelo or "").lower():
            raise ErrorIA(f"El modelo «{modelo}» se ejecuta en la nube: use un modelo local.")
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.proveedor = proveedor
        self.contexto = contexto
        self.tiempo_max = tiempo_max
        self.pensar = pensar
        self.llamadas = 0
        self.segundos = 0.0

    def _post(self, ruta, cuerpo):
        req = urllib.request.Request(self.url + ruta, data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.tiempo_max) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise ErrorIA(f"La IA respondió con error {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except urllib.error.URLError as e:
            raise ErrorIA(f"No se puede conectar con la IA en {self.url} ({e.reason}). ¿Está abierto Ollama / LM Studio?")

    def modelos(self):
        """Lista de modelos instalados (sirve también para comprobar que la IA está en marcha)."""
        ruta = "/api/tags" if self.proveedor == "ollama" else "/v1/models"
        try:
            with urllib.request.urlopen(self.url + ruta, timeout=10) as r:
                d = json.loads(r.read())
        except Exception as e:
            raise ErrorIA(f"No se puede conectar con la IA en {self.url}: ¿está abierto {'Ollama' if self.proveedor == 'ollama' else 'LM Studio'}? ({e})")
        if self.proveedor == "ollama":
            return [m.get("name") for m in d.get("models", [])]
        return [m.get("id") for m in d.get("data", [])]

    def preguntar(self, sistema, usuario, esquema):
        """Devuelve el objeto JSON que contesta la IA (forzado a seguir el esquema)."""
        t0 = time.time()
        if self.proveedor == "ollama":
            cuerpo = {"model": self.modelo, "stream": False, "format": esquema, "keep_alive": "30m",
                      "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                      "options": {"temperature": 0, "seed": 7, "num_ctx": self.contexto}}
            if self.pensar is not None:
                cuerpo["think"] = self.pensar
            try:
                d = self._post("/api/chat", cuerpo)
            except ErrorIA as e:
                if "think" in str(e).lower() and "think" in cuerpo:  # modelos que no admiten la opción
                    cuerpo.pop("think")
                    d = self._post("/api/chat", cuerpo)
                else:
                    raise
            texto = (d.get("message") or {}).get("content", "")
        else:  # LM Studio u otro servidor local compatible con OpenAI
            d = self._post("/v1/chat/completions", {
                "model": self.modelo, "temperature": 0, "stream": False,
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "respuesta", "strict": True, "schema": esquema}}})
            texto = d["choices"][0]["message"]["content"]
        self.llamadas += 1
        self.segundos += time.time() - t0
        texto = re.sub(r"(?s)^\s*<think>.*?</think>", "", texto or "").strip()
        m = re.search(r"(?s)\{.*\}", texto)
        try:
            return json.loads(m.group(0) if m else texto)
        except (json.JSONDecodeError, AttributeError):
            raise ErrorIA("La IA no devolvió un JSON válido.")
