"""
Cambia la contraseña de acceso a la versión web (modo navegador / GitHub Pages).

    python3 herramientas/cambiar_clave.py

Pide la contraseña nueva (no se muestra al escribirla) y reescribe web/js/acceso.js.
En el repositorio solo se guarda una huella cifrada (PBKDF2-SHA256), nunca la contraseña.
Después: python3 herramientas/construir_web.py y subir los cambios.
"""
import getpass
import hashlib
import os
import secrets
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "web", "js", "acceso.js")
ITERACIONES = 310_000

PLANTILLA = '''// Contraseña de acceso a la versión web. Generado por herramientas/cambiar_clave.py: NO editar a mano.
// Solo se guarda una huella cifrada (PBKDF2-SHA256), nunca la contraseña.
// Es una barrera ligera: los datos de pacientes nunca están en esta página.
export const ACCESO = {{ sal: "{sal}", iteraciones: {it}, huella: "{huella}" }};

const CLAVE_LOCAL = "willem_acceso";
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

async function derivar(clave) {{
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(clave), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({{ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(ACCESO.sal), iterations: ACCESO.iteraciones }}, k, 256);
  return hex(bits);
}}

export async function comprobarClave(clave) {{
  return (await derivar(clave)) === ACCESO.huella;
}}

export function accesoConcedido() {{
  try {{ return localStorage.getItem(CLAVE_LOCAL) === ACCESO.huella || sessionStorage.getItem(CLAVE_LOCAL) === ACCESO.huella; }} catch {{ return false; }}
}}

export function recordarAcceso(enEsteDispositivo) {{
  try {{ (enEsteDispositivo ? localStorage : sessionStorage).setItem(CLAVE_LOCAL, ACCESO.huella); }} catch {{ /* sin almacenamiento */ }}
}}

export function olvidarAcceso() {{
  try {{ localStorage.removeItem(CLAVE_LOCAL); sessionStorage.removeItem(CLAVE_LOCAL); }} catch {{ /* nada */ }}
}}
'''


def main():
    clave = os.environ.get("WILLEM_CLAVE") or getpass.getpass("Contraseña nueva: ")
    if not os.environ.get("WILLEM_CLAVE") and getpass.getpass("Repítala: ") != clave:
        sys.exit("No coinciden.")
    if not clave:
        sys.exit("La contraseña no puede estar vacía.")
    sal = secrets.token_hex(16)
    huella = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), ITERACIONES).hex()
    with open(DESTINO, "w", encoding="utf-8") as f:
        f.write(PLANTILLA.format(sal=sal, it=ITERACIONES, huella=huella))
    print(f"OK: contraseña cambiada en {os.path.relpath(DESTINO, RAIZ)}. Todos tendrán que escribirla de nuevo.")


if __name__ == "__main__":
    main()
