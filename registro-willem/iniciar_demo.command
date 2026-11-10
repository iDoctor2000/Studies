#!/bin/sh
# Doble clic en Mac: abre la DEMOSTRACIÓN (pacientes inventados)
cd "$(dirname "$0")" && exec python3 servidor.py --demo
