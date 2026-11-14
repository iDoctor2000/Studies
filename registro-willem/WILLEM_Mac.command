#!/bin/sh
# Doble clic en el Mac: abre la Estación de informes de WILLEM (interfaz gráfica, sin internet).
# Deje esta ventana abierta mientras trabaja; al cerrarla, la estación se apaga.
cd "$(dirname "$0")" || exit 1
. ./herramientas/python_mac.sh
"$PY" extractor/estacion.py
