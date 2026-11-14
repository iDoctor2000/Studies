"""
Revisión de los informes con AVISOS (posibles nombres), con botones en lugar de editar archivos.

Cada informe "para revisar" está en ~/WILLEM_privado/pendientes_de_revisar/ con:
  caso_XXXX_ingreso_FECHA.json / .txt   texto anonimizado (salvo lo dudoso)
  caso_XXXX_ingreso_FECHA.avisos.json   avisos con su contexto (privado)

Decisiones posibles para cada aviso:
  - "ocultar":     es un nombre → se sustituye por [PERSONA] en este informe y se añade a
                   ocultar_tambien.txt para los informes siguientes
  - "no_es":       no es un nombre → se añade a no_son_nombres.txt (deja de avisar)
  - "visto":       revisado, no hay dato personal (sin añadir nada a las listas)
Además se puede ocultar a mano cualquier palabra del informe ("ocultar_texto").
Cuando no queda ningún aviso pendiente, el informe pasa solo a ~/WILLEM_anonimizado/listos/.
"""
import glob
import json
import os
import re
import shutil

from anonimizar import LETRA, patron_texto, separar_secciones
from llave import Llave
from procesar_informes import AYUDA_NO_SON, AYUDA_OCULTAR, leer_lista

PALABRA = re.compile(rf"[{LETRA}]{{3,}}")
NO_PALABRAS = {"DEL", "LOS", "LAS", "POR", "CON", "UNA", "QUE", "HIJA", "HIJO", "HIJAS", "HIJOS", "ESPOSA", "ESPOSO", "MARIDO",
               "MUJER", "HERMANA", "HERMANO", "COMENTADO", "COMENTADA", "HABLADO", "HABLADA", "VALORADO", "VALORADA", "VISTO",
               "VISTA", "RESIDENTE", "ADJUNTO", "ADJUNTA", "ENFERMERA", "ENFERMERO", "FAMILIAR", "VECINA", "VECINO", "NIETA",
               "NIETO", "SOBRINA", "SOBRINO", "CUIDADORA", "CUIDADOR", "LLAMADA", "LLAMADO", "CONSULTADO", "CONSULTADA",
               "EXPLORADO", "EXPLORADA", "INTERVENIDO", "INTERVENIDA", "OPERADO", "OPERADA", "REALIZADO", "REALIZADA",
               "INFORMADO", "INFORMADA", "NUERA", "YERNO"}


def palabras_dudosas(fragmento):
    """'(Arce /Gañan)' -> ['Arce', 'Gañan']; 'Hija Lucinda' -> ['Lucinda']."""
    out = []
    for w in PALABRA.findall(fragmento or ""):
        if w.upper() in NO_PALABRAS or w.upper() in {x.upper() for x in out}:
            continue
        if w[0].isupper():
            out.append(w)
    if not out:  # una sola palabra en minúscula (p. ej. coincide con un apellido del paciente)
        ws = [w for w in PALABRA.findall(fragmento or "") if w.upper() not in NO_PALABRAS]
        if len(ws) == 1:
            out = ws
    return out


def _rutas(privado, base):
    d = os.path.join(privado, "pendientes_de_revisar")
    return {e: os.path.join(d, base + e) for e in (".json", ".txt", ".avisos.json")}


def listar(privado):
    out = []
    for ruta in sorted(glob.glob(os.path.join(privado, "pendientes_de_revisar", "*.avisos.json"))):
        base = os.path.basename(ruta)[:-len(".avisos.json")]
        with open(ruta, encoding="utf-8") as f:
            a = json.load(f)
        texto = ""
        r = _rutas(privado, base)
        if os.path.exists(r[".json"]):
            with open(r[".json"], encoding="utf-8") as f:
                texto = json.load(f).get("texto", "")
        for x in a["avisos"]:
            x["palabras"] = palabras_dudosas(x.get("fragmento"))
        out.append({"base": base, "archivo": a.get("archivo"), "numero": a.get("numero"), "fecha_ingreso": a.get("fecha_ingreso"),
                    "avisos": a["avisos"], "pendientes": sum(1 for x in a["avisos"] if not x.get("resuelto")), "texto": texto})
    return out


def _anadir(ruta, ayuda, palabras):
    actuales = leer_lista(ruta, ayuda)
    nuevas = [p for p in palabras if p.strip() and p.strip().lower() not in {x.lower() for x in actuales}]
    if nuevas:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\n".join(nuevas) + "\n")
    return nuevas


def _ocultar_en_texto(texto, palabras):
    n = 0
    for w in sorted(palabras, key=len, reverse=True):
        p = patron_texto(w)
        if not p:
            continue
        texto, k = re.subn(p, "[PERSONA]", texto)
        n += k
    return texto, n


def _guardar(privado, salida, base, datos, avisos):
    r = _rutas(privado, base)
    datos["secciones"] = separar_secciones(datos["texto"])
    pendientes = [x for x in avisos["avisos"] if not x.get("resuelto")]
    datos["control"] = {"estado": "revisar" if pendientes else "listo", "avisos": len(pendientes), "revisado_a_mano": True}
    cab = ""
    if os.path.exists(r[".txt"]):
        with open(r[".txt"], encoding="utf-8") as f:
            cab = "".join(f.readlines()[:3])
    with open(r[".json"], "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    with open(r[".txt"], "w", encoding="utf-8") as f:
        f.write(cab + datos["texto"] + "\n")
    with open(r[".avisos.json"], "w", encoding="utf-8") as f:
        json.dump(avisos, f, ensure_ascii=False, indent=1)
    if pendientes:
        return "revisar"
    # Todo resuelto: pasa a la carpeta compartible
    os.makedirs(os.path.join(salida, "listos"), exist_ok=True)
    for e in (".json", ".txt"):
        shutil.move(r[e], os.path.join(salida, "listos", base + e))
    os.remove(r[".avisos.json"])
    try:
        llave = Llave(os.path.join(privado, "llave_willem.sqlite"))
        llave.con.execute("UPDATE informes SET estado='listo' WHERE salida=?", (base,))
        llave.con.commit()
    except Exception:
        pass
    return "listo"


def resolver(privado, salida, base, aviso_id=None, decision="visto", texto_libre=""):
    """Aplica una decisión. Devuelve {"estado": "revisar"|"listo", "ocultadas": n, "anadidas": [...]}."""
    if not re.fullmatch(r"caso_\d{4}_ingreso_[0-9a-z_-]+", base or ""):
        raise ValueError("Informe no válido")
    r = _rutas(privado, base)
    if not os.path.exists(r[".avisos.json"]):
        raise ValueError("Ese informe ya no está pendiente de revisar")
    with open(r[".json"], encoding="utf-8") as f:
        datos = json.load(f)
    with open(r[".avisos.json"], encoding="utf-8") as f:
        avisos = json.load(f)
    aviso = next((x for x in avisos["avisos"] if x["id"] == aviso_id), None)
    anadidas, ocultadas = [], 0
    if decision == "ocultar_texto":
        palabras = [w.strip() for w in re.split(r"[,;\n]+", texto_libre or "") if len(w.strip()) >= 2]
        if not palabras:
            raise ValueError("Escriba la palabra o el nombre que quiere ocultar")
        datos["texto"], ocultadas = _ocultar_en_texto(datos["texto"], palabras)
        anadidas = _anadir(os.path.join(privado, "ocultar_tambien.txt"), AYUDA_OCULTAR, palabras)
    else:
        if not aviso:
            raise ValueError("Aviso no encontrado")
        palabras = palabras_dudosas(aviso.get("fragmento"))
        if decision == "ocultar":
            if not palabras:
                raise ValueError("No hay ninguna palabra que ocultar en este aviso: use «Ocultar otra palabra»")
            datos["texto"], ocultadas = _ocultar_en_texto(datos["texto"], palabras)
            anadidas = _anadir(os.path.join(privado, "ocultar_tambien.txt"), AYUDA_OCULTAR, palabras)
        elif decision == "no_es":
            anadidas = _anadir(os.path.join(privado, "no_son_nombres.txt"), AYUDA_NO_SON, palabras)
        elif decision != "visto":
            raise ValueError("Decisión no válida")
        aviso["resuelto"] = decision
    # Otros avisos cuyas palabras ya no están en el texto (se han ocultado): resueltos
    for x in avisos["avisos"]:
        if not x.get("resuelto"):
            ws = palabras_dudosas(x.get("fragmento"))
            if ws and not any(re.search(patron_texto(w), datos["texto"]) for w in ws):
                x["resuelto"] = "ocultar"
    estado = _guardar(privado, salida, base, datos, avisos)
    return {"estado": estado, "ocultadas": ocultadas, "anadidas": anadidas}


def descartar(privado, base):
    """El informe no se usa (p. ej. demasiados datos personales en el texto): se borra de pendientes."""
    if not re.fullmatch(r"caso_\d{4}_ingreso_[0-9a-z_-]+", base or ""):
        raise ValueError("Informe no válido")
    for ruta in _rutas(privado, base).values():
        if os.path.exists(ruta):
            os.remove(ruta)
    try:
        llave = Llave(os.path.join(privado, "llave_willem.sqlite"))
        llave.con.execute("UPDATE informes SET estado='descartado' WHERE salida=?", (base,))
        llave.con.commit()
    except Exception:
        pass
