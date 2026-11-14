#!/bin/sh
# Doble clic en Mac: abre la DEMOSTRACIÓN (pacientes inventados)
cd "$(dirname "$0")" || exit 1
. ./herramientas/python_mac.sh
exec "$PY" servidor.py --demo
