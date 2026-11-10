# Registro WILLEM · H.C.U. Virgen de la Arrixaca

Aplicación web **100 % local** para introducir los casos del registro WILLEM.
No usa internet ni servicios externos: los datos se quedan en el ordenador.

## Arrancar (Windows)

| Archivo | Para qué |
|---|---|
| `iniciar_demo.bat` | Probarla con **pacientes inventados** (usuario `admin`, contraseña `willem2026`) |
| `iniciar.bat` | Uso real, solo en este ordenador |
| `iniciar_red.bat` | Uso real, y además accesible desde otros PCs de la red del hospital |

Doble clic → se abre una ventana negra (el servidor, **no la cierre**) y el navegador.
La primera vez en uso real pedirá crear la cuenta del primer data manager.

## Si el ordenador no tiene Python

Python solo hace falta en **el ordenador que hace de servidor**. El resto del equipo
solo necesita un navegador (Chrome, Edge o Firefox) si se arranca con `iniciar_red.bat`.

**Opción A – Python portátil (sin instalar nada, sin permisos de administrador). Recomendada.**
1. En python.org → Downloads → Windows, descargue el *Windows embeddable package (64-bit)*
   (un .zip de unos 10 MB).
2. Descomprímalo en una carpeta llamada `python` **dentro** de esta carpeta, de forma que exista
   `python\python.exe`.
3. Listo: `iniciar.bat` lo usa automáticamente. Puede llevarse la carpeta entera en un USB.

**Opción B – Instalación normal.** Instalador de python.org (unos 25 MB). Marque
"Install just for me" (no pide administrador) y "Add python.exe to PATH".

No hace falta instalar ninguna librería adicional.

## Dónde están los datos

- `datos/registro.sqlite` → la base del registro (solo nº de caso, nunca CIP/NHC/nombre).
  **Copia de seguridad = copiar este archivo** (con el servidor cerrado).
- `llave/llave.sqlite` → libro llave (nº de caso ↔ CIP/CARM/NHC). Mejor en un USB cifrado:
  `iniciar.bat --llave E:\llave\llave.sqlite`
- `diccionario/diccionario_maestro.xlsx` → define el formulario. Editarlo cambia la aplicación
  (recargue la página).

## Estructura

```
servidor.py        servidor local (solo biblioteca estándar de Python)
demo.py            pacientes ficticios para la demostración
web/               interfaz (HTML, CSS, JavaScript; sin dependencias de internet)
diccionario/       diccionario maestro (Excel)
herramientas/      generador del diccionario a partir del CRF original
docs/              arquitectura
```

## Base de datos en una carpeta compartida (NAS)

```
iniciar.bat --datos \\NAS\willem\datos
```

El programa detecta que es una carpeta de red y usa un modo de SQLite seguro para ella.
**Importante:** el servidor debe estar abierto en **un solo ordenador a la vez**; los demás
entran con el navegador (`iniciar_red.bat`). El libro llave NO debe ir en la misma carpeta.
