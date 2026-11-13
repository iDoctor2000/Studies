"""
Prepara la versión "solo navegador" del registro WILLEM.

    python3 herramientas/construir_web.py

Genera:
  web/datos/diccionario.json   diccionario para la web (GitHub Pages / cualquier servidor estático)
  web/datos/demo.json          pacientes INVENTADOS para el modo demostración
  dist/WILLEM.html             ¡TODO en un único archivo! Doble clic y funciona, sin Python ni internet.

Vuelva a ejecutarlo cada vez que cambie el diccionario maestro o el código de web/.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import servidor  # noqa: E402
import demo  # noqa: E402

WEB = os.path.join(RAIZ, "web")
MODULOS = ["xlsx", "registro", "iconos", "modelo", "importador", "local", "envio", "acceso", "app"]  # orden de dependencias


def diccionario_json():
    d = servidor.diccionario()
    os.makedirs(os.path.join(WEB, "datos"), exist_ok=True)
    with open(os.path.join(WEB, "datos", "diccionario.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    return d


def demo_json():
    with tempfile.TemporaryDirectory() as tmp:
        servidor.CFG["db"] = os.path.join(tmp, "demo.sqlite")
        servidor.CFG["red_fs"] = False
        servidor.iniciar_db()
        llave = os.path.join(tmp, "llave.sqlite")
        demo.poblar(servidor.CFG["db"], llave, servidor.hash_pw, servidor.diagnosticos)
        con = sqlite3.connect(servidor.CFG["db"])
        con.row_factory = sqlite3.Row
        casos = [servidor.caso_a_dict(r) for r in con.execute("SELECT * FROM casos ORDER BY numero")]
        aud = [dict(r) for r in con.execute("SELECT * FROM auditoria ORDER BY id")]
        con.close()
        cl = sqlite3.connect(llave)
        cl.row_factory = sqlite3.Row
        ll = [dict(r) for r in cl.execute("SELECT * FROM llave ORDER BY numero")]
        cl.close()
    d = {"casos": casos, "auditoria": aud, "llave": ll}
    with open(os.path.join(WEB, "datos", "demo.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    return d


def modulo_como_iife(nombre, codigo):
    """Convierte un módulo ES en una función autoejecutable, para poder ir en un solo archivo."""
    imports = []

    def imp(m):
        cosas, origen = " ".join(m.group(1).split()), m.group(2)
        mod = "__m_" + os.path.splitext(os.path.basename(origen))[0]
        if cosas.startswith("* as "):
            imports.append(f"const {cosas[5:].strip()} = {mod};")
        else:
            imports.append(f"const {cosas} = {mod};")
        return ""

    codigo = re.sub(r'^import\s+([^;]+?)\s+from\s+"(.+?)";[ \t]*$', imp, codigo, flags=re.M)  # admite varias líneas
    if re.search(r"^import\s", codigo, flags=re.M):
        raise SystemExit(f"{nombre}.js: hay un import que no se ha podido convertir")
    exportados = re.findall(r"^export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)", codigo, flags=re.M)
    for grupo in re.findall(r"^export\s*\{([^}]*)\};?\s*$", codigo, flags=re.M):
        exportados += [x.strip() for x in grupo.split(",") if x.strip()]
    codigo = re.sub(r"^export\s*\{[^}]*\};?\s*$", "", codigo, flags=re.M)
    codigo = re.sub(r"^export\s+", "", codigo, flags=re.M)
    return (f"const __m_{nombre} = (() => {{\n{chr(10).join(imports)}\n{codigo}\n"
            f"return {{ {', '.join(dict.fromkeys(exportados))} }};\n}})();\n")


def html_unico(dic, dem):
    with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(WEB, "css", "app.css"), encoding="utf-8") as f:
        css = f.read()
    js = []
    for m in MODULOS:
        with open(os.path.join(WEB, "js", m + ".js"), encoding="utf-8") as f:
            js.append(modulo_como_iife(m, f.read()))
    seguro = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    datos = (f"window.WILLEM_MODO='navegador';\nwindow.WILLEM_DIC={seguro(dic)};\nwindow.WILLEM_DEMO={seguro(dem)};\n")
    codigo = "\n".join(js)
    if "</script" in codigo.lower():
        raise SystemExit("El código contiene '</script': no se puede incrustar")
    html = html.replace('<link rel="stylesheet" href="css/app.css">', f"<style>\n{css}\n</style>")
    # El archivo único se abre con doble clic: ahí no hay inicio de sesión de Microsoft (envío solo desde la web)
    html = html.replace('  <script src="vendor/msal-browser.min.js"></script>\n', "")
    html = html.replace('<script type="module" src="js/app.js"></script>',
                        f"<script>\n{datos}</script>\n<script>\n\"use strict\";\n{codigo}\n</script>")
    os.makedirs(os.path.join(RAIZ, "dist"), exist_ok=True)
    destino = os.path.join(RAIZ, "dist", "WILLEM.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(html)
    return destino


if __name__ == "__main__":
    d = diccionario_json()
    dm = demo_json()
    destino = html_unico(d, dm)
    print(f"OK  diccionario: {len(d['campos'])} campos · demo: {len(dm['casos'])} casos")
    print(f"OK  {os.path.relpath(destino, RAIZ)}  ({os.path.getsize(destino) // 1024} KB)")
