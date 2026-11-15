#!/bin/sh
# Doble clic en Mac: abre la DEMOSTRACIÓN (pacientes inventados) para probarla desde un iPad
# o un móvil conectados a la MISMA wifi. Solo para pruebas: va sin HTTPS.
# El registro de verdad se usará desde el iPad a través del NAS (ver docs/NAS.md).
cd "$(dirname "$0")" || exit 1
. ./herramientas/python_mac.sh
echo ""
echo "  PRUEBA DESDE EL IPAD (pacientes inventados)"
echo "  1. El iPad debe estar en la misma wifi que este Mac."
echo "  2. Si macOS pregunta si Python puede aceptar conexiones entrantes, pulse «Permitir»."
echo "  3. En Safari del iPad, escriba la dirección que aparece abajo en «Desde otros equipos»."
echo "  4. Usuario: admin   Contraseña: willem2026   (son los de la demostración)"
exec "$PY" servidor.py --demo --red --puerto 8770
