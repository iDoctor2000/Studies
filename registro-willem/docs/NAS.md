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
3. Cada colaborador: instalar Tailscale en su ordenador y aceptar la invitación que usted le envíe
   desde la consola de Tailscale (login.tailscale.com → Users → Invite).
4. En la consola de Tailscale, anote el nombre del NAS, por ejemplo `idoctornas`. Con MagicDNS
   activado se llega a él como `idoctornas` o `idoctornas.<su-red>.ts.net`.

(Alternativa sin Tailscale: el paquete **VPN Server** de Synology con WireGuard u OpenVPN, que sí
exige abrir un puerto UDP en el router.)

## 3. Copiar la aplicación al NAS

1. En el Mac, actualice el proyecto:
   ```bash
   cd ~/WILLEM && git pull
   ```
2. En el Finder: Ir → Conectarse al servidor → `smb://idoctornas` → carpeta compartida **docker**
   (si no existe, créela en DSM con File Station). Dentro, cree la carpeta **willem**.
3. Copie dentro de `docker/willem/`:
   - la carpeta entera `~/WILLEM/registro-willem` → quedará `docker/willem/registro-willem/`
   - el archivo `registro-willem/nas/docker-compose.yml` → quedará `docker/willem/docker-compose.yml`

La base de datos se creará sola en `docker/willem/datos/`. Para actualizar la aplicación más
adelante basta con sustituir la carpeta `registro-willem`: los datos están aparte.

## 4. Crear el contenedor (Container Manager)

1. Centro de paquetes → instalar **Container Manager** (si no lo tiene).
2. Container Manager → **Proyecto** → **Crear**:
   - Nombre: `willem`
   - Ruta: `/docker/willem`
   - Origen: «Usar el docker-compose.yml existente».
   - No configure el portal web de Web Station.
3. Siguiente → Hecho. Se construye la imagen (un par de minutos) y arranca el contenedor
   `willem-registro`. Debe aparecer **en ejecución** y, al poco, «healthy» (sano).

Qué hace el contenedor: solo escucha dentro del propio NAS (127.0.0.1:8765), con el sistema de
archivos en solo lectura, sin libro llave, con el doble factor obligatorio y con una copia diaria
de la base de datos en `datos/copias` (se guardan 14 días).

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

El NAS usa su propio certificado. La primera vez, el navegador avisará de que «no es de confianza»:
es normal en una red privada. Compruebe la huella del certificado y acéptelo. La estación del Mac
también le pedirá confirmar la huella una vez y, a partir de ahí, solo hablará con ese certificado.

## 6. Cortafuegos del NAS

Panel de control → Seguridad → **Cortafuegos** → activar → Editar reglas del perfil:

1. Permitir **8443** desde la red de Tailscale: IP de origen «Subred» `100.64.0.0`, máscara `255.192.0.0`.
2. Permitir los puertos de DSM (5000/5001) y SMB **solo** desde su red de casa (p. ej. `192.168.1.0/24`)
   y desde Tailscale.
3. Al final: **Denegar** todo lo demás.

Cuidado: cree primero las reglas de «Permitir» para su propia red, o podría quedarse sin acceso a DSM.

## 7. Primera puesta en marcha del registro

1. Desde el Mac (con Tailscale activo), abra `https://idoctornas:8443`.
2. Cree la cuenta del primer **data manager**.
3. Active el **doble factor**: escanee el código QR con Google Authenticator, Microsoft
   Authenticator o la app Contraseñas del iPhone, y escriba el código de 6 cifras.
4. **Guarde los 8 códigos de recuperación** en un sitio seguro, nunca junto al libro llave.
5. Usuarios → dé de alta al equipo. Cada persona activará su doble factor la primera vez que entre.
   Si alguien cambia de móvil: Usuarios → «Reiniciar doble factor».

Protecciones de la web: 5 contraseñas o códigos erróneos bloquean la cuenta 15 minutos (un data
manager puede desbloquearla). 20 intentos fallidos desde un mismo equipo bloquean ese equipo
15 minutos. La sesión caduca a las 12 horas.

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
2. Sustituya `docker/willem/registro-willem` por la carpeta nueva.
3. Container Manager → Proyecto → `willem` → Acción → **Construir** (o Detener → Construir → Iniciar).

Los datos (`docker/willem/datos`) no se tocan.

## Lista de comprobación final

- [ ] DSM actualizado, `admin` desactivado, doble factor en DSM.
- [ ] Ningún puerto abierto en el router; QuickConnect sin usar para el registro.
- [ ] Tailscale en el NAS, en el Mac y en cada colaborador.
- [ ] Contenedor `willem-registro` en ejecución y sano.
- [ ] Proxy inverso HTTPS 8443 → localhost:8765.
- [ ] Cortafuegos: 8443 solo desde Tailscale; DSM solo desde casa y Tailscale.
- [ ] Primer data manager con doble factor y códigos de recuperación guardados.
- [ ] Estación del Mac apuntando a `https://…:8443` con el certificado confirmado.
- [ ] Hyper Backup diario y cifrado de `docker/willem/datos`, con una restauración probada.
- [ ] Libro llave y PDF solo en el Mac (FileVault activado).
