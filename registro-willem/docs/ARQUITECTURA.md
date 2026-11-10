# Registro WILLEM – Arquitectura propuesta

## 1. Dos bases separadas (seudonimización)

```
 OFFLINE (PC del hospital, sin acceso desde fuera)      ONLINE (web, base anonimizada)
 ┌──────────────────────────────────────┐              ┌───────────────────────────────────┐
 │  LIBRO LLAVE (archivo cifrado)       │              │  BASE DEL REGISTRO                │
 │  nº caso  ↔  CIP / CARM / NHC        │   solo el    │  nº caso + datos clínicos         │
 │  Solo data managers                  │  nº de caso  │  Sin nombre, CIP, NHC, teléfono…  │
 │                                      │ ───────────► │  Trabajadoras + data managers     │
 └──────────────────────────────────────┘              └───────────────────────────────────┘
```

Flujo de alta de un paciente:
1. El data manager abre el libro llave, busca el CIP/CARM y, si no existe, se genera el
   siguiente nº de caso (p. ej. 0001, 0002…).
2. Entrega a la trabajadora el nº de caso y la documentación.
3. La trabajadora introduce los datos en la web usando solo el nº de caso.

Nunca se escribe el CIP/CARM en la base online. La base online sigue siendo un dato
**seudonimizado** (no anónimo) según el RGPD: requiere aprobación del CEIm, acceso con
usuario y contraseña, conexión cifrada (HTTPS) y servidor en la UE (idealmente del hospital).

## 2. Roles

| Rol | Puede |
|---|---|
| Data manager (3) | Todo: crear casos, revisar, corregir, exportar, gestionar usuarios, libro llave |
| Introductora de datos | Crear y rellenar casos; no exporta ni borra |

Todo cambio queda registrado (quién, qué, cuándo).

## 3. Diccionario maestro

`diccionario/diccionario_maestro.xlsx` define todos los campos. La aplicación lo lee:
para añadir, quitar o traducir un campo se edita el Excel, no el código.

## 4. Importación de informes

1. Anonimización **en el navegador**, antes de enviar nada al servidor: quitar cabecera,
   nombres, CIP, NHC, DNI, teléfonos, direcciones. Vista previa obligatoria. El informe no se guarda.
2. Extracción por reglas locales (sin IA externa ni internet).
3. Revisión humana campo a campo antes de guardar.

## Datos de prueba

En este repositorio NUNCA se guardan datos reales de pacientes.
