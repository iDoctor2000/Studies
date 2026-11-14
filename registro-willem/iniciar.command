#!/bin/sh
# Doble clic en Mac: uso real
cd "$(dirname "$0")" || exit 1
. ./herramientas/python_mac.sh
exec "$PY" servidor.py "$@"
