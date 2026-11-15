# Registro WILLEM en el NAS (Synology DS1522+, DSM 7.4)

Guía paso a paso para dejar el registro central en el NAS con todas las medidas de seguridad.
Los nombres de los menús pueden variar un poco según la versión de DSM.

```
  Mac Studio (en casa)                              NAS Synology (DS1522+)
  ┌────────────────────────────┐                    ┌──────────────────────────────────────┐
  │ PDF → Estación de informes │                    │ Proxy inverso HTTPS de DSM  :8443    │
  │  · libro llave (SOLO aquí) │ ── red privada ──► │        │                             │
  │  · anonimiza + IA local    │   (Tailscale,      │        ▼  solo desde el propio NAS   │
  │  · «Pasar al registro»     │    cifrada)        │ Contenedor «willem-registro» :8765   │
  └────────────────────────────┘                    │  · casos con número (seudonimizados) │
  Colaboradores: navegador + Tailscale ───────────► │  · doble factor obligatorio          │
                                                    │  · copia diaria en datos/copias      │
                                                    └──────────────────────────────────────┘
```

Reglas de oro:
- **No se abre ningún puerto en el router.** Se entra solo por la red privada (Tailscale).
- **El libro llave y los PDF nunca van al NAS.** En el NAS solo hay números de caso.
- **Todo acceso lleva contraseña + código del móvil**, tanto en DSM como en el registro.
- Recuerde: los datos seudonimizados siguen siendo datos de salud. Este montaje debe estar descrito
  en el protocolo aprobado por el CEIm y comunicado al Delegado de Protección de Datos.

---

## 1. Proteger el propio NAS (una vez)

1. **Actualizar DSM**: Panel de control → Actualizar y restaurar.
2. **Doble factor en su cuenta de DSM**: menú de usuario (arriba a la derecha) → Opciones personales →
   Seguridad → Verificación en dos pasos.
3. **Desactivar la cuenta `admin` de serie** y la de invitado (Panel de control → Usuario y grupo) y
   usar su cuenta personal con contraseña larga.
4. **Bloqueo automático**: Panel de control → Seguridad → Protección → activar el bloqueo
   automático de IP (p. ej. 5 intentos en 10 minutos).
5. **Sin acceso desde Internet**: compruebe en el router que no hay reenvíos de puertos hacia el NAS
   y desactive la configuración automática del router (UPnP) en DSM: Panel de control → Acceso externo.
   No use QuickConnect para el registro.

## 2. Red privada con Tailscale

Tailscale crea una red cifrada entre sus equipos sin abrir puertos.

1. En el NAS: Centro de paquetes → buscar **Tailscale** → Instalar → Abrir → iniciar sesión con su cuenta.
2. En el Mac Studio: instalar **Tailscale** (App Store) e iniciar sesión con la misma cuenta.
3. Cada colaborador instala Tailscale en el equipo desde el que vaya a trabajar (ordenador, iPad o
   móvil) y crea **su propia cuenta** gratuita. Usted le **comparte solo el NAS**: consola de
   Tailscale (login.tailscale.com) → Machines → menú «…» del NAS → **Share…** → enviar el enlace.
   Así cada persona ve únicamente el NAS, no su Mac ni sus otros equipos, y se le puede retirar el
   acceso en cualquier momento desde esa misma pantalla.
   Importante: Tailscale tiene que estar instalado en el equipo de cada persona. **No se entra desde
   los ordenadores corporativos del hospital**: cada persona usa un ordenador propio o dedicado a
   esto, desde su casa o desde donde esté (ver «Equipos de los colaboradores», más abajo).
4. En la consola de Tailscale, anote el nombre del NAS, por ejemplo `idoctornas`. Con MagicDNS
   activado se llega a él como `idoctornas` o `idoctornas.<su-red>.ts.net`.
5. **Reglas de acceso (antes de compartir el NAS con nadie).** Por defecto Tailscale deja que todos
   los equipos lleguen a todo: un colaborador podría ver DSM y las carpetas del NAS.
   Consola de Tailscale → **Access controls** → sustituya la política por esta (ponga su correo):
   ```json
   {
     "groups": { "group:admin": ["su-correo@ejemplo.com"] },
     "hosts":  { "nas": "100.x.y.z" },
     "acls": [
       { "action": "accept", "src": ["group:admin"],      "dst": ["*:*"] },
       { "action": "accept", "src": ["autogroup:shared"], "dst": ["nas:8443"] }
     ]
   }
   ```
   (`100.x.y.z` es la IP de Tailscale del NAS, la que aparece junto a su nombre en la consola.)
   La primera regla es para usted: sus equipos lo ven todo. La segunda es para las personas con las
   que comparte el NAS (paso 3): solo pueden abrir el puerto del registro (8443), **ni DSM, ni las
   carpetas, ni nada más**. No hay que añadir a nadie a mano: vale para todo el que acepte su
   invitación, y deja de valer en cuanto le retire el NAS compartido.
   **Compruébelo con el primer colaborador**: debe poder abrir `https://idoctornas:8443` y **no**
   debe poder abrir DSM (`https://idoctornas:5001`).

   Importante: el paquete Tailscale de Synology entrega lo que llega por la red privada como si
   viniera del propio NAS. Por eso **el cortafuegos de DSM no filtra el tráfico de Tailscale**: lo
   que de verdad limita a los colaboradores son estas reglas.

(Alternativa sin Tailscale: el paquete **VPN Server** de Synology con WireGuard u OpenVPN, que sí
exige abrir un puerto UDP en el router.)

## 3. Copiar la aplicación al NAS

1. En el Mac, actualice el proyecto:
   ```bash
   cd ~/WILLEM && git pull
   ```
2. En el Finder: Ir → Conectarse al servidor → `smb://idoctornas` → carpeta compartida **docker**
   (si no existe, créela en DSM con File Station). Dentro, cree la carpeta **willem**.
3. Copie dentro de `docker/willem/` **solo los archivos del proyecto, sin su base local**
   (`registro-willem/datos/` del Mac no debe ir al NAS). Lo más seguro, en Terminal:
   ```bash
   cd ~/WILLEM && git archive HEAD registro-willem | tar -x -C /Volumes/docker/willem
   cp registro-willem/nas/docker-compose.yml /Volumes/docker/willem/
   mkdir -p /Volumes/docker/willem/datos
   ```
   Quedarán `docker/willem/registro-willem/`, `docker/willem/docker-compose.yml` y la carpeta
   vacía `docker/willem/datos/`. **Créela usted**: Synology no la crea sola y, sin ella, el
   contenedor no arranca («Bind mount failed: … datos does not exist»).

La base de datos se creará sola dentro de `datos/`. Para actualizar la aplicación más adelante
basta con sustituir la carpeta `registro-willem`: los datos están aparte.

## 4. Crear el contenedor (Container Manager)

1. Centro de paquetes → instalar **Container Manager** (si no lo tiene).
2. Container Manager → **Proyecto** → **Crear**:
   - Nombre: `willem`
   - Ruta: `/docker/willem`
   - Origen: «Usar el docker-compose.yml existente».
   - No configure el portal web de Web Station.
3. Siguiente → Hecho. Se construye la imagen (un par de minutos) y arranca el contenedor
   `willem-registro`. Debe aparecer **en ejecución** y, al poco, «healthy» (sano).

Qué hace el contenedor: escucha en 127.0.0.1:8765 del NAS, con el sistema de archivos en solo
lectura, sin libro llave, con el doble factor obligatorio y con una copia diaria de la base de
datos en `datos/copias` (se guardan 14 días). Al arrancar crea `datos/clave_proxy.txt`: **solo
atiende las peticiones que traen esa clave**, que añade el proxy del paso 5. Así, aunque alguien
llegue al 8765 por otra vía (el Tailscale de Synology lo hace posible), recibe «403».

## 5. HTTPS: proxy inverso de DSM

Panel de control → Portal de inicio de sesión → **Avanzado** → **Proxy inverso** → Crear:

| Campo | Valor |
|---|---|
| Descripción | WILLEM |
| Origen · Protocolo | HTTPS |
| Origen · Nombre de host | `*` (o el nombre del NAS en Tailscale) |
| Origen · Puerto | **8443** |
| Origen · Activar HSTS | Sí |
| Destino · Protocolo | HTTP |
| Destino · Nombre de host | `localhost` |
| Destino · Puerto | **8765** |

Después, en esa misma regla → **Encabezado personalizado** → Crear → Crear:
nombre `X-Willem-Proxy`, valor = el contenido de `docker/willem/datos/clave_proxy.txt`
(en el Mac: `tr -d '\n' < /Volumes/docker/willem/datos/clave_proxy.txt | pbcopy` y pegar con ⌘V;
luego vacíe el portapapeles). Sin esta cabecera el registro responde «403».

El NAS usa su propio certificado. La primera vez, el navegador avisará de que «no es de confianza»:
es normal en una red privada. Compruebe la huella del certificado y acéptelo. La estación del Mac
también le pedirá confirmar la huella una vez y, a partir de ahí, solo hablará con ese certificado.

## 6. Cortafuegos del NAS

Panel de control → Seguridad → **Cortafuegos** → activar → Editar reglas del perfil:

1. Permitir **8443** desde la red de Tailscale: IP de origen «Subred» `100.64.0.0`, máscara `255.192.0.0`.
2. Permitir los puertos de DSM (5000/5001) y SMB **solo** desde su red de casa (p. ej. `192.168.1.0/24`).
   Si quiere administrar el NAS desde fuera, hágalo con sus propios equipos por Tailscale; las reglas
   del paso 2.5 impiden que los invitados lleguen a esos puertos.
3. Al final: **Denegar** todo lo demás.

Cuidado: cree primero las reglas de «Permitir» para su propia red, o podría quedarse sin acceso a DSM.

Este cortafuegos protege frente a la red de casa. Frente a la red de Tailscale no sirve (véase el
paso 2.5): allí mandan las reglas de acceso de Tailscale.

## 7. Primera puesta en marcha del registro

1. Desde el Mac (con Tailscale activo), abra `https://idoctornas:8443`.
2. Cree la cuenta del primer **data manager**.
3. Active el **doble factor**: escanee el código QR con Google Authenticator, Microsoft
   Authenticator o la app Contraseñas del iPhone, y escriba el código de 6 cifras.
4. **Guarde los 8 códigos de recuperación** en un sitio seguro, nunca junto al libro llave.
5. Usuarios → dé de alta al equipo, cada persona con **su propio usuario** y el perfil que le toca:

   | Perfil | Para quién | Qué puede hacer |
   |---|---|---|
   | **Introducción de datos** | personal que mete casos | crear y rellenar casos (modo normal y Modo Vintage); no puede tocar un caso ya validado |
   | **Cardiólogo revisor** | cardiólogos que revisan | lo anterior y además revisar, corregir y **validar** casos, ver la **Auditoría de la IA** y escribir pistas clínicas |
   | **Data manager** | quien administra el registro | todo: además **importa de la IA**, exporta el Excel, borra casos y gestiona usuarios |

   Solo el data manager puede importar de la IA, y además hace falta la Estación del Mac, que es
   donde están las propuestas. Lo recomendable es que haya un único data manager.
   Cada persona activará su doble factor la primera vez que entre.
   Póngales una contraseña inicial y pídales que la cambien al entrar (icono de la llave, junto a
   su nombre). La hoja **[EQUIPO.md](EQUIPO.md)** explica a cada persona lo que tiene que hacer.
   Si alguien cambia de móvil: Usuarios → «Reiniciar doble factor».
6. **Desde un iPad o un móvil**: con Tailscale activado, abrir `https://idoctornas:8443` en Safari,
   aceptar el certificado la primera vez y, si se quiere, Compartir → «Añadir a pantalla de inicio».

Protecciones de la web: 5 contraseñas o códigos erróneos bloquean la cuenta 15 minutos (un data
manager puede desbloquearla). 20 intentos fallidos desde un mismo equipo bloquean ese equipo
15 minutos. La sesión caduca a las 12 horas.

## Equipos de los colaboradores

El registro no se abre a Internet ni se usa desde los ordenadores del hospital. Cada persona entra
desde un ordenador **propio o dedicado**, en su casa o donde esté, con estas condiciones mínimas:

- **Tailscale** instalado y con su propia cuenta (paso 2).
- **Disco cifrado**: FileVault en Mac, BitLocker o «Cifrado del dispositivo» en Windows.
- Cuenta de usuario **con contraseña** y bloqueo automático de pantalla. Si el ordenador es
  compartido con la familia, una cuenta de usuario aparte para esto.
- Sistema y navegador **actualizados**.
- No guardar la contraseña del registro en un navegador compartido ni hacer capturas o copias de
  los datos.

El registro es una página web: **en el ordenador de cada persona no queda guardado ningún dato**.
Para el Modo Vintage hace falta pantalla de portátil o de escritorio; en un iPad se usa el modo normal.

Qué se puede hacer desde casa: revisar y completar los casos que ha rellenado la IA, porque cada
caso lleva guardado el **texto anonimizado del informe** («Ver en el informe»). Lo que exija
consultar la historia clínica solo se puede hacer en el hospital: allí se mira la historia en el
ordenador del hospital y se escribe en el portátil propio, conectado con los datos del móvil.

Si alguien deja el proyecto o pierde el equipo: desactive su usuario en el registro (Usuarios) y
retírele el NAS compartido en la consola de Tailscale.

## 8. Conectar la Estación de informes del Mac

En la estación (`WILLEM_Mac.command`) → **Ajustes** → Dirección del registro:
`https://idoctornas:8443` → Guardar. En el circuito aparecerá «Confirmar certificado»: revise la
huella y confíe en ella. «Pasar al registro» le pedirá usuario, contraseña y el código del móvil.

## 9. Copias de seguridad (imprescindible)

El contenedor deja cada día una copia coherente en `docker/willem/datos/copias/`.
Además, con **Hyper Backup**:

1. Crear → Tarea de copia de seguridad de datos → destino: disco USB externo (o un segundo NAS).
2. Carpetas: `docker/willem/datos`.
3. Programación diaria. Active el **cifrado del lado del cliente** y guarde la contraseña aparte.
4. **Pruebe a restaurar** una copia una vez, para saber que funciona.

## 10. Actualizar la aplicación

1. En el Mac: `cd ~/WILLEM && git pull`.
2. Sustituya `docker/willem/registro-willem` por la carpeta nueva (con `git archive`, como en el paso 3).
3. Container Manager → Proyecto → `willem` → Acción → **Detener** → **Limpiar**. Luego, en
   **Imagen**, elimine `willem-registro:local` (si no, «Crear» reutiliza la imagen vieja).
   Por último, Proyecto → `willem` → Acción → **Crear**: reconstruye y arranca.

Los datos (`docker/willem/datos`) no se tocan.

## Lista de comprobación final

- [ ] DSM actualizado, `admin` desactivado, doble factor en DSM.
- [ ] Ningún puerto abierto en el router; QuickConnect sin usar para el registro.
- [ ] Tailscale en el NAS, en el Mac y en cada colaborador; los invitados solo llegan al puerto 8443.
- [ ] Equipos de los colaboradores con disco cifrado, contraseña y bloqueo de pantalla.
- [ ] Contenedor `willem-registro` en ejecución y sano.
- [ ] Proxy inverso HTTPS 8443 → localhost:8765, con la cabecera `X-Willem-Proxy`.
- [ ] `http://<nas>:8765` responde «403» desde otro equipo de Tailscale.
- [ ] Reglas de acceso de Tailscale: los colaboradores solo llegan a `nas:8443`.
- [ ] Cortafuegos: 8443 solo desde Tailscale; DSM solo desde casa y Tailscale.
- [ ] Primer data manager con doble factor y códigos de recuperación guardados.
- [ ] Estación del Mac apuntando a `https://…:8443` con el certificado confirmado.
- [ ] Hyper Backup diario y cifrado de `docker/willem/datos`, con una restauración probada.
- [ ] Libro llave y PDF solo en el Mac (FileVault activado).
