# Elige un Python que funcione de verdad en este Mac (lo usan los archivos .command).
# Primero el de Apple (/usr/bin/python3, con el que está probado todo); después cualquier otro.
# Se descartan los que no pueden leer PDF/XML, cifrar o usar la base de datos (p. ej. algún
# Python de Homebrew roto tras actualizar macOS).
PY=""
for candidato in /usr/bin/python3 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if "$candidato" -c "import sys, pyexpat, sqlite3, ssl, zipfile; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "  No se encuentra un Python que funcione en este Mac."
  echo "  Abra el Terminal y escriba:   xcode-select --install"
  echo "  (instala el Python de Apple). Después vuelva a hacer doble clic."
  echo ""
  exit 1
fi
