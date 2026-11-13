#!/bin/sh
# Doble clic en el Mac: la IA local (Ollama) rellena el formulario de los casos ya anonimizados.
cd "$(dirname "$0")" || exit 1
python3 extractor/ia/extraer_ia.py --abrir "$@"
echo ""
echo "Puede cerrar esta ventana."
