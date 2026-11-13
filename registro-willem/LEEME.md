# Registro WILLEM · H.C.U. Virgen de la Arrixaca

Aplicación web **100 % local** para introducir los casos del registro WILLEM.
No usa internet ni servicios externos: los datos se quedan en el ordenador.

## Opción recomendada: SIN instalar nada (modo navegador)

Abra **`dist/WILLEM.html`** con doble clic en **Microsoft Edge o Google Chrome**. Nada más.

- Cada persona elige su perfil (introducción de datos o data manager).
- Sus casos se guardan en el navegador **y** en un Excel propio (`WILLEM_<usuario>.xlsx`) dentro de la
  **carpeta compartida de SharePoint/OneDrive del SMS** que vincule (menú *Carpeta compartida*).
  OneDrive lo sube con la cuenta corporativa de cada persona; la aplicación no se conecta a internet.
- El data manager pulsa **Unir casos** para juntar los Excel de todo el equipo y luego **Exportar**.
- El libro llave se queda en el navegador del data manager (con copia en un sitio privado), nunca en la carpeta compartida.
- Para probar: botón *Solo quiero probarla con pacientes inventados*.

Si cambia el diccionario o el código, regenere el archivo con `python3 herramientas/construir_web.py`.
La carpeta `web/` también puede publicarse tal cual en GitHub Pages (funciona en modo navegador).

## Versión web central (GitHub Pages) y envío al registro

- Dirección para todo el equipo: **https://idoctor2000.github.io/Studies/** (se publica sola, mediante
  `.github/workflows/pages.yml`, cada vez que cambia `registro-willem/web/`). Solo contiene el programa;
  los datos de los pacientes nunca se suben a GitHub.
- **Enviar al registro** (botón en cada caso): inicia sesión con la cuenta del SMS y escribe la fila del caso
  en el Excel corporativo (tabla `WILLEM`, formato final). Reenviar actualiza la misma fila.
- Configuración (una vez): `web/datos/envio.json` con `clientId` y `tenantId` de la aplicación registrada por
  Informática y `excelUrl` del Excel. En la aplicación registrada debe figurar como URI de redirección (SPA):
  `https://idoctor2000.github.io/Studies/auth.html`. Permiso delegado: `Files.ReadWrite.All`.
- Formato: Sí = 1, No = 0, Desconocido/Duda = vacío. Columnas de fecha de un Sí/No: la fecha, 0 si se contestó
  sin fecha, vacío si es Desconocido o no se contestó.
- La carpeta compartida (Excel por persona + "Unir casos") sigue funcionando como copia de seguridad.
- **Contraseña de acceso** (versión web y `WILLEM.html`): la conoce el equipo; en el código solo hay una huella
  cifrada. Para cambiarla: `python3 herramientas/cambiar_clave.py`, luego `python3 herramientas/construir_web.py`
  y subir los cambios. Es una barrera ligera: los datos están protegidos por las cuentas y permisos del SMS.

## Opción con servidor (base de datos común en un PC)

### Arrancar (Windows)

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
extractor/         lectura y anonimización de informes de alta en PDF (Mac, sin internet)
docs/              arquitectura
```

## Base de datos en una carpeta compartida (NAS)

```
iniciar.bat --datos \\NAS\willem\datos
```

El programa detecta que es una carpeta de red y usa un modo de SQLite seguro para ella.
**Importante:** el servidor debe estar abierto en **un solo ordenador a la vez**; los demás
entran con el navegador (`iniciar_red.bat`). El libro llave NO debe ir en la misma carpeta.

## Informes de alta en PDF → casos anonimizados (Mac, fase 1)

Doble clic en **`procesar_informes.command`**, elija la carpeta o el USB con los PDF y espere.
Al terminar se abre un resumen en el navegador. No necesita internet ni instalar nada
(el lector de PDF va incluido en `extractor/vendor`).

Para cada informe:

1. Lee la **cabecera** por reglas fijas (NHC, CIP SNS, **CIP autonómico CARM**, nombre, fechas…).
2. Busca al paciente en el **libro llave** por su CARM: si ya estaba (reingreso), usa su número de
   caso; si no, le da el siguiente. Si el informe no trae CARM, enlaza por CIP SNS, NHC o DNI
   (si alguna clave contradice a otra ya guardada, el informe se bloquea para revisarlo). La primera vez puede fijar el primer número:
   `python3 extractor/procesar_informes.py --primer-numero 101`, o importar la llave que ya
   tenga la web: `--importar-llave LLAVE_WILLEM_NO_COMPARTIR_….xlsx`.
3. Quita cabecera, firma, pie y código lateral, y **sustituye** en el texto clínico nombres,
   teléfonos, DNI, CIP, NHC, domicilio, localidad y profesionales por `[PACIENTE]`, `[TELÉFONO]`…
   Las fechas y los datos clínicos se conservan.
4. **Doble control**: vuelve a buscar cada identificador en el resultado (sin tildes, sin espacios
   ni puntos). Si queda alguno, el informe se **bloquea**.

| Resultado | Dónde queda |
|---|---|
| **Listo** | `~/WILLEM_anonimizado/listos/caso_0007_ingreso_2025-05-18.json` (+ `.txt`) — se puede compartir |
| **Revisar** (posibles nombres, p. ej. "(Arce /Gañan)") | `~/WILLEM_privado/pendientes_de_revisar/` — privado |
| **Bloqueado** (sin CARM, escaneado, dos pacientes en un PDF, fallo del control) | no se guarda nada |

Para resolver un aviso: si es un nombre, añádalo a `~/WILLEM_privado/ocultar_tambien.txt`; si no
lo es, a `no_son_nombres.txt`. Vuelva a procesar la carpeta (es seguro repetir: mismo paciente,
mismo caso).

En `~/WILLEM_privado/` (NUNCA al NAS ni a la nube): `llave_willem.sqlite` (libro llave, mismo
formato que `servidor.py --llave`; además guarda qué PDF se procesó y un directorio de
profesionales que se ocultan en los informes siguientes), las listas y los resúmenes.
Requisitos: FileVault activado (el programa avisa si no lo está) y no mover esa carpeta a
Escritorio/Documentos si iCloud los sincroniza.

Pruebas con informes inventados: `python3 extractor/pruebas/probar_extractor.py`.

## Fase 2: la IA local rellena el formulario (Mac)

**Preparación (una vez):** instale **Ollama** (ollama.com) en el Mac y descargue un modelo local, por
ejemplo `ollama pull qwen3:30b` (unos 19 GB; va sobrado con 64 GB de memoria). Ollama trabaja solo
en este ordenador. El programa se niega a usar una IA que no esté en `localhost` y los modelos
"cloud" de Ollama. LM Studio también sirve (`--proveedor openai --url http://127.0.0.1:1234`).

**Uso:** después de la fase 1, doble clic en **`extraer_con_ia.command`**. Para cada caso de
`~/WILLEM_anonimizado/listos/`:

1. El informe más antiguo es el **ingreso índice**. La IA propone los **diagnósticos del estudio** y
   contesta, por tandas, todas las preguntas del formulario, cada una con la **frase literal** del
   informe en la que se basa. Sexo y fecha de nacimiento salen de la cabecera, sin IA.
2. **Comprobaciones automáticas.** Se avisa (en ámbar) si:
   - la frase no aparece en el informe,
   - el número no está en la frase,
   - el valor está fuera de rango,
   - la fecha está incompleta o es imposible.

   Lo que el formulario no mostraría (p. ej. datos de una prueba no realizada) se descarta.
3. Los informes posteriores (**reingresos**) rellenan el seguimiento: rehospitalización por IC o por
   otra causa con su fecha, y el fallecimiento si el alta es por exitus.
4. Deja un archivo por caso en `~/WILLEM_anonimizado/propuestas_ia/caso_XXXX.json`. Con `--rehacer`
   se repite; con `--casos 3,7` solo esos casos; con `--modelo` se cambia de modelo.

**Revisión en la web** (data manager): menú **Importar de la IA** → elegir la carpeta
`propuestas_ia` → Importar.

- Si el caso no existe, se crea con los diagnósticos propuestos. Si existe, solo se rellenan los campos
  vacíos: **nunca se pisa lo escrito por una persona**, y los casos validados no se tocan.
- Cada dato de la IA lleva la marca **IA** (morada, o ámbar si tiene aviso). Al pulsarla se ve la frase
  del informe y el botón «Ver en el informe», que abre el texto anonimizado con la frase resaltada.
- Un dato deja de estar pendiente cuando una persona lo confirma («Es correcto»), lo corrige o lo
  quita. También se pueden confirmar todos los de una pestaña de una vez.
- **No se puede validar un caso con datos de la IA sin revisar.** Todo queda en el historial
  (origen «IA» y «revisión IA»).

Pruebas (con una IA simulada): `python3 extractor/pruebas/probar_ia.py`.
