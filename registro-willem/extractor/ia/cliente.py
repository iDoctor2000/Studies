"""
Cliente del modelo de IA LOCAL (Ollama o LM Studio) — solo biblioteca estándar.

Por seguridad, solo se permite hablar con un servidor de ESTE ordenador (localhost):
los textos, aunque estén anonimizados, nunca salen del Mac.

Cada respuesta tiene TOPE de longitud y de tiempo: si el modelo entra en bucle (escribe sin
parar, repite o rellena con espacios) se corta, y quien llama puede repetir la pregunta
partida en trozos más pequeños. La respuesta se lee en directo (streaming) para poder
mostrar un «latido» y cancelar a mitad.
"""
import http.client
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

LOCALES = {"localhost", "127.0.0.1", "::1"}


class ErrorIA(Exception):
    """Fallo al usar la IA."""


class ErrorConexion(ErrorIA):
    """La IA no está en marcha o no responde: no tiene sentido reintentar."""


class RespuestaCortada(ErrorIA):
    """La respuesta se cortó (bucle, tope de longitud o de tiempo) o no es un JSON válido."""

    def __init__(self, motivo, texto=""):
        super().__init__(motivo)
        self.texto = texto


class Cancelado(ErrorIA):
    """La persona ha pulsado «Cancelar»."""


class ClienteIA:
    def __init__(self, url="http://127.0.0.1:11434", modelo="qwen3:30b", proveedor="ollama",
                 contexto=16384, tiempo_max=240, pensar=False):
        host = urllib.parse.urlparse(url).hostname
        if host not in LOCALES:
            raise ErrorIA(f"La IA debe estar en este ordenador (localhost). Dirección no permitida: {host}")
        if "cloud" in (modelo or "").lower():
            raise ErrorIA(f"El modelo «{modelo}» se ejecuta en la nube: use un modelo local.")
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.proveedor = proveedor
        self.contexto = contexto
        self.tiempo_max = tiempo_max      # segundos como máximo por respuesta
        self.espera_inicio = 300          # la primera respuesta espera a que el modelo se cargue en memoria
        self.pensar = pensar
        self.llamadas = 0
        self.segundos = 0.0
        self.ultima = {}                  # datos de la última llamada (para el registro)
        self.latido = None                # función(tokens, segundos) mientras genera
        self.cancelar = None              # threading.Event para cancelar

    def _abrir(self, ruta, cuerpo, espera):
        req = urllib.request.Request(self.url + ruta, data=json.dumps(cuerpo).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            return urllib.request.urlopen(req, timeout=espera)
        except urllib.error.HTTPError as e:
            raise ErrorIA(f"La IA respondió con error {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")
        except (socket.timeout, TimeoutError):
            raise RespuestaCortada("La IA no ha empezado a contestar a tiempo")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise RespuestaCortada("La IA no ha empezado a contestar a tiempo")
            raise ErrorConexion(f"No se puede conectar con la IA en {self.url} ({e.reason}). ¿Está abierto Ollama / LM Studio?")
        except (http.client.HTTPException, OSError) as e:
            raise RespuestaCortada(f"La conexión con la IA se interrumpió ({type(e).__name__})")

    def modelos(self):
        """Lista de modelos instalados (sirve también para comprobar que la IA está en marcha)."""
        ruta = "/api/tags" if self.proveedor == "ollama" else "/v1/models"
        try:
            with urllib.request.urlopen(self.url + ruta, timeout=10) as r:
                d = json.loads(r.read())
        except Exception as e:
            raise ErrorConexion(f"No se puede conectar con la IA en {self.url}: ¿está abierto {'Ollama' if self.proveedor == 'ollama' else 'LM Studio'}? ({e})")
        if self.proveedor == "ollama":
            return [m.get("name") for m in d.get("models", [])]
        return [m.get("id") for m in d.get("data", [])]

    # ------------------------------------------------------------------
    def _ollama(self, cuerpo, t0):
        """Lee la respuesta en directo. Devuelve (texto, motivo_fin)."""
        r = self._abrir("/api/chat", cuerpo, self.espera_inicio)
        trozos, n, fin = [], 0, None
        cola = ""
        try:
            for linea in r:
                if self.cancelar is not None and self.cancelar.is_set():
                    raise Cancelado("Cancelado")
                if not linea.strip():
                    continue
                d = json.loads(linea)
                if d.get("error"):
                    raise ErrorIA(f"La IA respondió con un error: {d['error']}")
                t = (d.get("message") or {}).get("content", "")
                if t:
                    trozos.append(t)
                    n += 1
                    cola = (cola + t)[-600:]
                    if self.latido and n % 20 == 0:
                        self.latido(n, time.time() - t0)
                if d.get("done"):
                    fin = d.get("done_reason") or "stop"
                    self.ultima.update(tokens=d.get("eval_count", n), tokens_entrada=d.get("prompt_eval_count"))
                    break
                # Bucles típicos: relleno de espacios o la misma frase repetida sin fin
                if len(cola) >= 400 and not cola[-400:].strip():
                    fin = "bucle (relleno de espacios)"
                    break
                if len(cola) == 600 and len(set(cola[i:i + 60] for i in range(0, 600, 60))) == 1:
                    fin = "bucle (texto repetido)"
                    break
                if time.time() - t0 > self.tiempo_max:
                    fin = f"tiempo máximo ({self.tiempo_max} s)"
                    break
        except (socket.timeout, TimeoutError):
            fin = "la IA dejó de contestar"
        except (http.client.HTTPException, OSError, json.JSONDecodeError) as e:
            fin = f"la conexión con la IA se interrumpió ({type(e).__name__})"
        finally:
            r.close()  # al cerrar la conexión, Ollama deja de generar
        self.ultima.setdefault("tokens", n)
        return "".join(trozos), fin or "conexión cerrada"

    def preguntar(self, sistema, usuario, esquema, max_tokens=2048):
        """Devuelve el objeto JSON que contesta la IA (forzado a seguir el esquema)."""
        t0 = time.time()
        self.ultima = {"max_tokens": max_tokens}
        if self.cancelar is not None and self.cancelar.is_set():
            raise Cancelado("Cancelado")
        try:
            if self.proveedor == "ollama":
                cuerpo = {"model": self.modelo, "stream": True, "format": esquema, "keep_alive": "30m",
                          "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                          "options": {"temperature": 0, "seed": 7, "num_ctx": self.contexto, "num_predict": max_tokens}}
                if self.pensar is not None:
                    cuerpo["think"] = self.pensar
                try:
                    texto, fin = self._ollama(cuerpo, t0)
                except ErrorIA as e:
                    if "think" in str(e).lower() and "think" in cuerpo and not isinstance(e, (Cancelado, ErrorConexion)):
                        cuerpo.pop("think")  # modelos que no admiten la opción
                        texto, fin = self._ollama(cuerpo, t0)
                    else:
                        raise
            else:  # LM Studio u otro servidor local compatible con OpenAI
                r = self._abrir("/v1/chat/completions", {
                    "model": self.modelo, "temperature": 0, "stream": False, "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                    "response_format": {"type": "json_schema", "json_schema": {"name": "respuesta", "strict": True, "schema": esquema}}},
                    self.tiempo_max + self.espera_inicio)
                try:
                    d = json.loads(r.read())
                except (socket.timeout, TimeoutError):
                    raise RespuestaCortada(f"tiempo máximo ({self.tiempo_max} s)")
                finally:
                    r.close()
                texto = d["choices"][0]["message"]["content"]
                fin = {"length": "length"}.get(d["choices"][0].get("finish_reason"), "stop")
                self.ultima.update(tokens=(d.get("usage") or {}).get("completion_tokens"))
        finally:
            self.llamadas += 1
            self.segundos += time.time() - t0
            self.ultima.update(segundos=round(time.time() - t0, 1))
        self.ultima.update(fin=fin)
        texto = re.sub(r"(?s)^\s*<think>.*?</think>", "", texto or "").strip()
        if fin != "stop":
            motivo = "llegó al tope de longitud" if fin == "length" else fin
            raise RespuestaCortada(f"Respuesta cortada: {motivo}", texto)
        m = re.search(r"(?s)\{.*\}", texto)
        try:
            return json.loads(m.group(0) if m else texto)
        except (json.JSONDecodeError, AttributeError):
            raise RespuestaCortada("La IA no devolvió un JSON válido", texto)
