#!/usr/bin/env python3
"""
Registro WILLEM · Procesado de informes de alta (FASE 1: sin inteligencia artificial)

Lee los PDF de una carpeta (o de un USB), y para cada informe:
  1. lee la cabecera (NHC, CIP, CARM...) por reglas fijas
  2. busca el paciente en el LIBRO LLAVE: si ya existe, usa su número de caso; si no, le da uno nuevo
  3. anonimiza el texto clínico y hace el DOBLE CONTROL
  4. guarda el resultado:
       - correcto                -> ~/WILLEM_anonimizado/listos/       (se puede compartir)
       - con avisos (posibles nombres) -> ~/WILLEM_privado/pendientes_de_revisar/
       - bloqueado               -> no se guarda nada; el motivo sale en el informe del proceso
  5. abre un informe del proceso (página web local) con el resumen

Uso:
    python3 extractor/procesar_informes.py /Volumes/USB/informes
    python3 extractor/procesar_informes.py CARPETA --primer-numero 101       (solo la primera vez)
    python3 extractor/procesar_informes.py --importar-llave LLAVE_WILLEM.xlsx (números ya usados en la web)
    python3 extractor/procesar_informes.py --exportar-llave

Todo ocurre en este ordenador. No hay conexión a internet.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import platform
import re
import subprocess
import sys
import webbrowser

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))  # para servidor.py (lector/escritor de Excel)

from anonimizar import anonimizar_informe, separar_secciones  # noqa: E402
from leer_pdf import InformeNoValido, leer_informe  # noqa: E402
from llave import ConflictoLlave, Llave  # noqa: E402

VERSION = "1.0"
CASA = os.path.expanduser("~")
PRIVADO_DEF = os.path.join(CASA, "WILLEM_privado")
SALIDA_DEF = os.path.join(CASA, "WILLEM_anonimizado")

AYUDA_OCULTAR = """# Palabras o nombres que hay que OCULTAR SIEMPRE en los informes (uno por línea).
# Ejemplo: apellidos de cirujanos que aparecen en el texto, nombres de familiares...
# Las líneas que empiezan por # no cuentan.
"""
AYUDA_NO_SON = """# Palabras que NO son nombres de personas (uno por línea): dejan de generar avisos.
# Ejemplo: nombres comerciales de fármacos escritos con mayúscula.
# Las líneas que empiezan por # no cuentan.
"""


def leer_lista(ruta, ayuda):
    if not os.path.exists(ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(ayuda)
        return []
    with open(ruta, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]


def huella_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def buscar_pdfs(entradas):
    pdfs = []
    for e in entradas:
        if os.path.isfile(e):
            pdfs.append(e)
            continue
        for raiz, carpetas, archivos in os.walk(e):
            carpetas[:] = sorted(c for c in carpetas if not c.startswith("."))
            for a in sorted(archivos):
                # "._informe.pdf" son restos que crea el Mac en los USB: no son informes
                if a.lower().endswith(".pdf") and not a.startswith("."):
                    pdfs.append(os.path.join(raiz, a))
    return pdfs


def avisos_del_equipo(privado):
    """Comprobaciones de seguridad del ordenador (solo informan, no bloquean)."""
    out = []
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["fdesetup", "status"], capture_output=True, text=True, timeout=10)
            if "On" not in r.stdout:
                out.append("FileVault (cifrado del disco) NO está activado en este Mac. Actívelo en Ajustes del Sistema → "
                           "Privacidad y seguridad → FileVault antes de trabajar con informes reales.")
        except Exception:
            out.append("No se ha podido comprobar si FileVault está activado.")
        p = os.path.abspath(privado)
        if "Mobile Documents" in p or p.startswith(os.path.join(CASA, "Desktop")) or p.startswith(os.path.join(CASA, "Documents")):
            out.append("La carpeta privada está en Escritorio/Documentos/iCloud: si iCloud sincroniza esas carpetas, "
                       "el libro llave se subiría a la nube. Use la carpeta por defecto (~/WILLEM_privado).")
    return out


def nombre_salida(numero, fecha, huella):
    return f"caso_{numero:04d}_ingreso_{fecha or 'sin_fecha_' + huella[:8]}"


def guardar_avisos(destino, r):
    """Avisos de un informe "para revisar", en un archivo privado aparte (para resolverlos con botones)."""
    avisos = []
    for n, (motivo, contexto) in enumerate(r["avisos"], 1):
        m = re.search(r"⟦(.*?)⟧", contexto)
        avisos.append({"id": n, "motivo": motivo, "contexto": contexto, "fragmento": m.group(1) if m else "", "resuelto": None})
    with open(destino + ".avisos.json", "w", encoding="utf-8") as f:
        json.dump({"archivo": r["archivo"], "pdf": r["ruta"], "numero": r["numero"], "fecha_ingreso": r.get("fecha_ingreso"),
                   "avisos": avisos}, f, ensure_ascii=False, indent=1)


def procesar(pdfs, privado, salida, usuario="extractor", progreso=None):
    os.makedirs(privado, exist_ok=True)
    os.makedirs(os.path.join(salida, "listos"), exist_ok=True)
    pendientes = os.path.join(privado, "pendientes_de_revisar")
    os.makedirs(pendientes, exist_ok=True)
    llave = Llave(os.path.join(privado, "llave_willem.sqlite"))
    ocultar = leer_lista(os.path.join(privado, "ocultar_tambien.txt"), AYUDA_OCULTAR)
    no_son = leer_lista(os.path.join(privado, "no_son_nombres.txt"), AYUDA_NO_SON)
    resultados = []
    for i, ruta in enumerate(pdfs, 1):
        r = {"archivo": os.path.basename(ruta), "ruta": ruta, "estado": "bloqueado", "bloqueos": [], "avisos": [],
             "sustituciones": {}, "numero": None, "nuevo": False, "repetido": False, "texto": ""}
        print(f"  [{i}/{len(pdfs)}] {r['archivo']} … ", end="", flush=True)
        try:
            h = huella_archivo(ruta)
            r["repetido"] = llave.informe(h) is not None
            inf = leer_informe(ruta)
            c = inf["cabecera"]
            carm = c["cip_carm"] if c["cip_carm"].startswith("CARM") else ""
            numero, nuevo, clave = llave.caso_para(carm, c["cip_sns"], c["nhc"], c["dni"], usuario)
            r.update(numero=numero, nuevo=nuevo, sin_carm=not carm, clave=clave, fecha_ingreso=c["fecha_ingreso"], fecha_alta=c["fecha_alta"],
                     paginas=inf["paginas"])
            # Los profesionales de este informe se ocultarán también en los siguientes
            llave.anotar_profesionales(inf["firma"]["nombres"] + [inf["pie"]["enfermera"], inf["pie"]["medico"]])
            an = anonimizar_informe(inf, directorio=llave.profesionales(), ocultar=ocultar, no_son_nombres=no_son)
            r.update(texto=an["texto"], sustituciones=an["sustituciones"], bloqueos=an["bloqueos"], avisos=an["avisos"])
            base = nombre_salida(numero, c["fecha_ingreso"], h)
            destino_listo = os.path.join(salida, "listos", base)
            destino_pend = os.path.join(pendientes, base)
            if r["bloqueos"]:
                r["estado"] = "bloqueado"
                destino = None
            else:
                r["estado"] = "revisar" if r["avisos"] else "listo"
                destino = destino_pend if r["avisos"] else destino_listo
                datos = {
                    "formato": "willem-informe-anonimizado/1",
                    "version_extractor": VERSION,
                    "numero_caso": numero,
                    "fecha_ingreso": c["fecha_ingreso"],
                    "fecha_alta": c["fecha_alta"],
                    "servicio": c["servicio"],
                    "paciente": {"sexo": c["sexo"], "fecha_nacimiento": c["fecha_nacimiento"], "edad": c["edad"]},
                    "titulo": inf["titulo"],
                    "paginas": inf["paginas"],
                    "secciones": separar_secciones(an["texto"]),
                    "texto": an["texto"],
                    "sustituciones": an["sustituciones"],
                    "control": {"estado": r["estado"], "avisos": len(an["avisos"])},
                    "procesado": dt.datetime.now().replace(microsecond=0).isoformat(),
                }
                with open(destino + ".json", "w", encoding="utf-8") as f:
                    json.dump(datos, f, ensure_ascii=False, indent=1)
                with open(destino + ".txt", "w", encoding="utf-8") as f:
                    f.write(f"WILLEM · caso {numero} · ingreso {c['fecha_ingreso']} · alta {c['fecha_alta']}\n"
                            f"{c['sexo']} · nacimiento {c['fecha_nacimiento']} · {c['servicio']}\n\n{an['texto']}\n")
                if r["estado"] == "revisar":
                    guardar_avisos(destino, r)
            # Si antes estaba en la otra carpeta (p. ej. ya revisado), se quita de allí
            for otro in (destino_listo, destino_pend):
                if otro != destino:
                    for ext in (".json", ".txt", ".avisos.json"):
                        if os.path.exists(otro + ext):
                            os.remove(otro + ext)
            llave.guardar_informe(h, numero, c["fecha_ingreso"], c["acto"], r["estado"], destino and os.path.basename(destino))
        except (InformeNoValido, ConflictoLlave) as e:
            r["bloqueos"] = [str(e)]
        except Exception as e:  # cualquier fallo inesperado bloquea ese informe, no el lote
            r["bloqueos"] = [f"Error inesperado al procesar ({type(e).__name__}: {e})."]
        print({"listo": "LISTO", "revisar": "REVISAR (avisos)", "bloqueado": "BLOQUEADO"}[r["estado"]]
              + (f" · caso {r['numero']}" if r["numero"] else ""))
        resultados.append(r)
        if progreso:
            progreso(i, len(pdfs), r)
    # Resumen del último proceso (privado: lleva nombres de archivo), para la interfaz del Mac
    with open(os.path.join(privado, "ultimo_proceso.json"), "w", encoding="utf-8") as f:
        json.dump({"fecha": dt.datetime.now().replace(microsecond=0).isoformat(),
                   "informes": [{k: r.get(k) for k in ("archivo", "ruta", "estado", "bloqueos", "numero", "nuevo", "repetido",
                                                        "sin_carm", "fecha_ingreso", "sustituciones")} | {"avisos": len(r["avisos"])}
                                for r in resultados]}, f, ensure_ascii=False, indent=1)
    return resultados, llave


# ---------------------------------------------------------------------------
#  Informe del proceso (página web local, sin nada externo)
# ---------------------------------------------------------------------------
def _resaltar(texto):
    t = html.escape(texto)
    t = re.sub(r"\[([A-ZÁÉÍÓÚÑº ]{2,})\]", r'<mark class="et">[\1]</mark>', t)
    return t


def informe_html(resultados, avisos_equipo, privado, salida):
    n = {k: sum(1 for r in resultados if r["estado"] == k) for k in ("listo", "revisar", "bloqueado")}
    nuevos = sum(1 for r in resultados if r["nuevo"])
    tarjetas = []
    for r in resultados:
        chips = '<span class="chip gris">cabecera, firma y pie quitados</span>' + "".join(f'<span class="chip">{html.escape(k.lower())} · {v}</span>' for k, v in r["sustituciones"].items()) \
            or '<span class="chip gris">cabecera, firma y pie quitados · nada más que ocultar en el texto</span>'
        bloq = "".join(f"<li>{html.escape(b)}</li>" for b in r["bloqueos"])
        avis = "".join(f"<li><b>{html.escape(m)}</b><br><span class='ctx'>{html.escape(c).replace('⟦', '<mark>').replace('⟧', '</mark>')}</span></li>"
                       for m, c in r["avisos"])
        caso = (f"Caso <b>{r['numero']}</b> " + ('<span class="chip verde">paciente nuevo</span>' if r["nuevo"]
                else '<span class="chip azul">ya estaba en la llave (reingreso o repetido)</span>')) if r["numero"] else "Sin caso"
        if r.get("sin_carm"):
            caso += ' <span class="chip ambar">sin CIP autonómico: enlazado por NHC/DNI</span>'
        fechas = f" · ingreso {r.get('fecha_ingreso') or '?'} · alta {r.get('fecha_alta') or '?'}" if r["numero"] else ""
        texto = (f"<details><summary>Ver el texto anonimizado</summary><pre>{_resaltar(r['texto'])}</pre></details>"
                 if r["texto"] and r["estado"] != "bloqueado" else "")
        tarjetas.append(f"""
<section class="tarjeta {r['estado']}">
  <div class="fila"><span class="estado">{ {'listo': 'Listo', 'revisar': 'Revisar', 'bloqueado': 'Bloqueado'}[r['estado']] }</span>
  <span class="arch">{html.escape(r['archivo'])}</span>{' <span class="chip gris">ya procesado antes</span>' if r['repetido'] else ''}</div>
  <div class="meta">{caso}{fechas}</div>
  <div class="chips">{chips}</div>
  {f'<div class="caja roja"><b>Motivo del bloqueo</b><ul>{bloq}</ul></div>' if bloq else ''}
  {f'<div class="caja ambar"><b>Posibles nombres por revisar</b><ul>{avis}</ul><p class="nota">Si es un nombre, añádalo a <code>ocultar_tambien.txt</code>; si no lo es, a <code>no_son_nombres.txt</code>. Después vuelva a procesar la carpeta.</p></div>' if avis else ''}
  {texto}
</section>""")
    eq = "".join(f'<div class="caja roja">{html.escape(a)}</div>' for a in avisos_equipo)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>WILLEM · proceso de informes</title>
<style>
:root{{--fondo:#f4f6fb;--papel:#fff;--tinta:#1d2433;--suave:#5b6478;--borde:#dfe4ee;--verde:#0f9d6b;--ambar:#c77700;--rojo:#d23b3b;--azul:#2f6fde}}
@media (prefers-color-scheme:dark){{:root{{--fondo:#11151d;--papel:#1a202b;--tinta:#e6e9f0;--suave:#9aa3b5;--borde:#2c3443}}}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:24px 16px 60px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:var(--suave);margin:0 0 18px}}
.res{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}}
.res div{{background:var(--papel);border:1px solid var(--borde);border-radius:12px;padding:12px 14px}}
.res b{{display:block;font-size:26px}} .res .v b{{color:var(--verde)}} .res .a b{{color:var(--ambar)}} .res .r b{{color:var(--rojo)}}
.tarjeta{{background:var(--papel);border:1px solid var(--borde);border-left:6px solid var(--verde);border-radius:12px;padding:14px 16px;margin:12px 0}}
.tarjeta.revisar{{border-left-color:var(--ambar)}} .tarjeta.bloqueado{{border-left-color:var(--rojo)}}
.fila{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} .arch{{font-weight:600;word-break:break-all}}
.estado{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:2px 8px;border-radius:99px;background:var(--verde);color:#fff}}
.revisar .estado{{background:var(--ambar)}} .bloqueado .estado{{background:var(--rojo)}}
.meta{{color:var(--suave);margin:6px 0}} .chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font-size:12px;border:1px solid var(--borde);border-radius:99px;padding:1px 8px}} .chip.verde{{color:var(--verde)}} .chip.azul{{color:var(--azul)}} .chip.gris{{color:var(--suave)}} .chip.ambar{{color:var(--ambar)}}
.caja{{border-radius:10px;padding:10px 12px;margin:10px 0}} .caja ul{{margin:6px 0 0;padding-left:18px}}
.caja.roja{{background:color-mix(in srgb,var(--rojo) 12%,transparent)}} .caja.ambar{{background:color-mix(in srgb,var(--ambar) 14%,transparent)}}
.ctx{{color:var(--suave);font-size:13px}} mark{{background:#ffd54a;color:#000;border-radius:3px;padding:0 2px}}
mark.et{{background:color-mix(in srgb,var(--azul) 22%,transparent);color:inherit;font-weight:600}}
.nota{{font-size:13px;color:var(--suave);margin:8px 0 0}} code{{font-size:12px}}
details{{margin-top:10px}} summary{{cursor:pointer;color:var(--azul)}}
pre{{white-space:pre-wrap;word-wrap:break-word;background:var(--fondo);border-radius:8px;padding:12px;font:13px/1.45 ui-monospace,Menlo,monospace;max-height:520px;overflow:auto}}
.donde{{font-size:13px;color:var(--suave);background:var(--papel);border:1px solid var(--borde);border-radius:12px;padding:10px 14px}}
</style></head><body><main>
<h1>Proceso de informes de alta</h1>
<p class="sub">{dt.datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(resultados)} informe(s) · este resumen contiene nombres de archivo: no lo comparta.</p>
{eq}
<div class="res"><div class="v"><b>{n['listo']}</b>listos para compartir</div><div class="a"><b>{n['revisar']}</b>para revisar</div>
<div class="r"><b>{n['bloqueado']}</b>bloqueados</div><div><b>{nuevos}</b>pacientes nuevos</div></div>
<div class="donde">Listos: <code>{html.escape(os.path.join(salida, 'listos'))}</code><br>
Para revisar (privado): <code>{html.escape(os.path.join(privado, 'pendientes_de_revisar'))}</code><br>
Libro llave (privado): <code>{html.escape(os.path.join(privado, 'llave_willem.sqlite'))}</code></div>
{''.join(tarjetas)}
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Lee informes de alta en PDF, asigna número de caso y anonimiza.")
    ap.add_argument("entrada", nargs="*", help="carpeta(s) o PDF(s) a procesar")
    ap.add_argument("--privado", default=PRIVADO_DEF, help="carpeta privada (libro llave, avisos)")
    ap.add_argument("--salida", default=SALIDA_DEF, help="carpeta de informes anonimizados")
    ap.add_argument("--primer-numero", type=int, help="primer número de caso a usar (solo la primera vez)")
    ap.add_argument("--importar-llave", help="Excel de llave exportado desde la web (numero, cip, carm, nhc)")
    ap.add_argument("--exportar-llave", action="store_true", help="guarda una copia del libro llave en Excel")
    ap.add_argument("--abrir", action="store_true", help="abrir el resumen al terminar")
    ap.add_argument("--usuario", default="extractor")
    a = ap.parse_args()

    os.makedirs(a.privado, exist_ok=True)
    llave = Llave(os.path.join(a.privado, "llave_willem.sqlite"))
    if a.primer_numero:
        if llave.con.execute("SELECT COUNT(*) FROM llave").fetchone()[0]:
            print(f"Aviso: el libro llave ya tiene casos; el siguiente será max({a.primer_numero}, último + 1).")
        llave.poner_ajuste("primer_numero", a.primer_numero)
    if a.importar_llave:
        from servidor import leer_xlsx
        hojas = leer_xlsx(a.importar_llave)
        filas = hojas.get("LLAVE") or next(iter(hojas.values()), [])
        cab = [str(x or "").strip().lower() for x in filas[0]] if filas else []
        n = llave.importar([dict(zip(cab, f)) for f in filas[1:]])
        print(f"Libro llave: {n} caso(s) importado(s).")
    if not a.entrada:
        if a.exportar_llave:
            exportar_llave(llave, a.privado)
        elif not (a.primer_numero or a.importar_llave):
            ap.print_help()
        return

    pdfs = buscar_pdfs(a.entrada)
    print(f"\nRegistro WILLEM · procesado de informes ({len(pdfs)} PDF)\n")
    eq = avisos_del_equipo(a.privado)
    for x in eq:
        print("  ¡ATENCIÓN! " + x)
    resultados, llave = procesar(pdfs, a.privado, a.salida, a.usuario)
    carpeta_inf = os.path.join(a.privado, "resumenes_de_proceso")
    os.makedirs(carpeta_inf, exist_ok=True)
    ruta_html = os.path.join(carpeta_inf, f"proceso_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(informe_html(resultados, eq, a.privado, a.salida))
    if a.exportar_llave:
        exportar_llave(llave, a.privado)
    n = {k: sum(1 for r in resultados if r["estado"] == k) for k in ("listo", "revisar", "bloqueado")}
    print(f"\nListos: {n['listo']} · Para revisar: {n['revisar']} · Bloqueados: {n['bloqueado']}")
    print(f"Resumen: {ruta_html}")
    if a.abrir:
        if platform.system() == "Darwin":
            subprocess.run(["open", ruta_html])
        else:
            webbrowser.open("file://" + ruta_html)


def exportar_llave(llave, privado):
    from servidor import crear_xlsx
    ruta = os.path.join(privado, f"LLAVE_WILLEM_NO_COMPARTIR_{dt.date.today().isoformat()}.xlsx")
    with open(ruta, "wb") as f:
        f.write(crear_xlsx([("LLAVE", [["numero", "cip", "carm", "nhc", "notas", "creado", "creado_por", "dni"]] + llave.filas_llave())]))
    print(f"Libro llave exportado: {ruta}")


if __name__ == "__main__":
    main()
