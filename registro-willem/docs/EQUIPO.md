# Registro WILLEM · Qué tiene que hacer cada persona

Hoja para repartir al equipo. Antes de enviarla, sustituya `DIRECCIÓN-DEL-REGISTRO` por la dirección
real (por ejemplo `https://idoctornas:8443`).

## Para todos: preparar el equipo (una sola vez)

Se entra desde un **ordenador propio o dedicado** (o un iPad). **No desde los ordenadores del hospital.**

1. **Proteja su equipo**:
   - disco cifrado (Mac: Ajustes → Privacidad y seguridad → FileVault; Windows: BitLocker o
     «Cifrado del dispositivo»);
   - cuenta con contraseña y bloqueo automático de pantalla;
   - sistema y navegador actualizados;
   - si el ordenador lo usa más gente en casa, cree una cuenta de usuario solo para esto.
2. **Instale Tailscale** (tailscale.com, App Store o Microsoft Store) y cree su cuenta. Es una red
   privada cifrada: sin ella, el registro no se ve.
3. Recibirá un **enlace de invitación** del responsable del registro. Ábralo con su cuenta de Tailscale y acepte.
4. Instale en el móvil una aplicación de códigos: **Google Authenticator**, **Microsoft
   Authenticator** o la app **Contraseñas** del iPhone.

## Para todos: entrar la primera vez

1. Con Tailscale **activado**, abra en el navegador: `DIRECCIÓN-DEL-REGISTRO`
2. El navegador avisará de que el certificado «no es de confianza». Es normal en una red privada:
   pulse «Avanzado» → «Continuar».
3. Escriba su **usuario** y la **contraseña inicial** que le han dado.
4. Aparecerá un **código QR**: escanéelo con la aplicación de códigos del móvil y escriba el
   código de 6 cifras.
5. **Guarde los 8 códigos de recuperación** en un sitio seguro. Sirven si pierde el móvil.
6. **Cambie la contraseña** por una que solo conozca usted: icono de la **llave**, abajo a la
   izquierda, junto a su nombre.

A partir de ahí, cada vez: Tailscale activado → dirección del registro → usuario, contraseña y el
código del móvil.

## Normas

- El usuario es **personal**: no se comparte. Todo lo que se hace queda anotado con su nombre.
- En el registro **nunca** se escriben nombres, NHC, DNI, CIP ni teléfonos. Solo el número de caso.
- No haga capturas de pantalla ni copie datos fuera del registro.
- Cierre la sesión al terminar (icono de salida, junto a su nombre).
- Si pierde el móvil o el ordenador, o sospecha que alguien conoce su contraseña, **avise
  enseguida** al responsable del registro.
- Tras 5 contraseñas o códigos equivocados, el usuario se bloquea 15 minutos.

---

## Personal de introducción de datos

- **Casos** → abra un caso → rellene las pestañas. Se guarda solo.
- Botón **Modo Vintage** (arriba a la derecha, dentro del caso): más variables por pantalla y manejo
  con teclado (`S` Sí, `N` No, `?` Desconocido, `D` Duda). Necesita pantalla de portátil o de escritorio.
- Los datos con la marca morada **IA** los ha propuesto la inteligencia artificial a partir del
  informe. Pulse la marca para ver la frase del informe y:
  - **«Es correcto»** si coincide,
  - corríjalo si no,
  - **«Ver en el informe»** para leer el texto completo (ya sin datos personales).
- Si no está segura de un dato, márquelo como **Duda** (bandera): lo verá un cardiólogo.
- Cuando el caso esté completo, cambie el estado a **Completo**.
- Un caso **validado** ya no se puede modificar.

## Cardiólogos revisores

Todo lo anterior y, además:

- **Dudas**: lista de las preguntas marcadas con bandera por el personal, para resolverlas.
- Revisar los casos **completos**, corregir lo necesario y pasarlos a **Validado**. No se puede
  validar un caso con dudas sin resolver o con datos de la IA sin revisar.
- Un caso validado se puede corregir o devolver a «Completo».
- **Auditoría de la IA**: acierto de la IA en cada variable. Al pulsar una variable se ven los casos
  y se puede escribir una **pista clínica** (el criterio que debe seguir la IA).

## Data manager (responsable del registro)

- En casa: Estación de informes del Mac → anonimizar, rellenar con IA y **Pasar al registro**.
- **Usuarios**: altas, perfiles, desbloqueos y «Reiniciar doble factor» si alguien cambia de móvil.
- **Exportar**: Excel final con el formato del CRF.
- Tras cambiar pistas clínicas: en la Estación, «Actualizar pistas» → «Repetir solo unas variables…»
  → «Pasar al registro».
- Si alguien deja el proyecto: desactivar su usuario y retirarle el NAS compartido en Tailscale.
