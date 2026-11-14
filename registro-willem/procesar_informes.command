#!/bin/sh
# Doble clic en el Mac: elegir la carpeta (o el USB) con los informes PDF y procesarlos.
cd "$(dirname "$0")" || exit 1
. ./herramientas/python_mac.sh
CARPETA=$(osascript -e 'POSIX path of (choose folder with prompt "Elija la carpeta o el USB con los informes de alta (PDF)")' 2>/dev/null) || exit 0
"$PY" extractor/procesar_informes.py "$CARPETA" --abrir
echo ""
echo "Puede cerrar esta ventana."
