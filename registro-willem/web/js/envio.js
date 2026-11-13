// ENVÍO AL REGISTRO: escribe cada caso como una fila en el Excel corporativo (Office 365 de la CARM).
//
// · Cada persona inicia sesión con SU cuenta del SMS (Microsoft Entra ID). La aplicación
//   nunca ve ni guarda contraseñas: Microsoft le da un permiso temporal (token).
// · Los datos van directamente del navegador a graph.microsoft.com (Office 365 de la CARM).
// · El Excel tiene una tabla "WILLEM" con la cabecera del formato final; si no existe, se crea.
// · Si el caso ya estaba enviado, se actualiza su fila (se busca por patient_id).
//
// Configuración: web/datos/envio.json (la rellena el data manager una vez) o, en un ordenador
// concreto, desde la pantalla "Envío al registro" (se guarda en ese navegador).
import { cabeceraRegistro, filasDelCaso, huella, DIAG } from "./registro.js";

const GRAPH = "https://graph.microsoft.com/v1.0";
let _conf, _app, _libro;

export async function configEnvio() {
  if (_conf) return _conf;
  let base = {};
  if (window.WILLEM_ENVIO) base = window.WILLEM_ENVIO;
  else {
    try { const r = await fetch("datos/envio.json", { cache: "no-store" }); if (r.ok) base = await r.json(); } catch { /* sin archivo */ }
  }
  let local = {};
  try { local = JSON.parse(localStorage.getItem("willem_envio") || "{}"); } catch { /* nada */ }
  _conf = { tabla: "WILLEM", scopes: ["Files.ReadWrite.All"], ...base, ...Object.fromEntries(Object.entries(local).filter(([, v]) => v)) };
  return _conf;
}

export function guardarConfigLocal(c) {
  localStorage.setItem("willem_envio", JSON.stringify(c));
  _conf = undefined; _app = undefined; _libro = undefined;
}

/** ¿Se puede enviar desde aquí? Devuelve {ok, motivo} */
export async function estadoEnvio() {
  const c = await configEnvio();
  if (window.__WILLEM_TOKEN_PRUEBAS) return { ok: true, conf: c };
  if (!/^https?:$/.test(location.protocol)) return { ok: false, motivo: "El envío directo solo funciona desde la versión web (no al abrir el archivo con doble clic).", conf: c };
  if (!window.msal) return { ok: false, motivo: "No se ha cargado el módulo de inicio de sesión de Microsoft.", conf: c };
  if (!c.clientId || !c.tenantId || !c.excelUrl) return { ok: false, motivo: "Falta la configuración (identificadores de la aplicación y enlace del Excel).", conf: c, sinConfig: true };
  return { ok: true, conf: c };
}

// ---------------------------------------------------------------------------
// Inicio de sesión (MSAL, biblioteca oficial de Microsoft)
// ---------------------------------------------------------------------------
async function app() {
  if (_app) return _app;
  const c = await configEnvio();
  const redirectUri = new URL("auth.html", location.href).href;
  _app = new window.msal.PublicClientApplication({
    auth: { clientId: c.clientId, authority: `https://login.microsoftonline.com/${c.tenantId}`, redirectUri },
    cache: { cacheLocation: "sessionStorage" },
  });
  await _app.initialize();
  return _app;
}

async function token() {
  if (window.__WILLEM_TOKEN_PRUEBAS) return window.__WILLEM_TOKEN_PRUEBAS; // solo pruebas automáticas
  const a = await app();
  const c = await configEnvio();
  const cuenta = a.getActiveAccount() || a.getAllAccounts()[0];
  const req = { scopes: c.scopes, account: cuenta };
  if (cuenta) {
    try { return (await a.acquireTokenSilent(req)).accessToken; } catch { /* hay que volver a pedirlo */ }
  }
  const r = await a.acquireTokenPopup({ scopes: c.scopes, prompt: cuenta ? undefined : "select_account" });
  a.setActiveAccount(r.account);
  return r.accessToken;
}

export async function cuentaActual() {
  if (window.__WILLEM_TOKEN_PRUEBAS) return { username: "pruebas@sms" };
  try { const a = await app(); return a.getActiveAccount() || a.getAllAccounts()[0] || null; } catch { return null; }
}

export async function iniciarSesion() { await token(); return cuentaActual(); }

// ---------------------------------------------------------------------------
// Microsoft Graph
// ---------------------------------------------------------------------------
async function g(metodo, ruta, cuerpo) {
  const t = await token();
  const r = await fetch(GRAPH + ruta, {
    method: metodo, headers: { Authorization: "Bearer " + t, "Content-Type": "application/json" },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  if (r.status === 204) return null;
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(traducirError(r.status, d.error?.message));
    e.status = r.status; e.codigo = d.error?.code;
    throw e;
  }
  return d;
}

function traducirError(status, msg) {
  if (status === 401) return "La sesión de Microsoft ha caducado. Vuelva a intentarlo.";
  if (status === 403) return "Su cuenta no tiene permiso para escribir en ese Excel. Pida acceso de edición al data manager.";
  if (status === 404) return "No se encuentra el Excel o la tabla. Revise el enlace en la configuración.";
  if (status === 409 || status === 423) return "El Excel está ocupado en este momento. Espere unos segundos y vuelva a enviar.";
  if (status === 429 || status === 503) return "Office 365 está saturado. Espere un momento y vuelva a enviar.";
  return msg || `Error ${status} de Office 365`;
}

const idCompartido = (url) => "u!" + btoa(unescape(encodeURIComponent(url))).replace(/=+$/, "").replace(/\//g, "_").replace(/\+/g, "-");
const letra = (i) => { let s = ""; i++; while (i) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); } return s; };
const paraExcel = (x) => (typeof x === "string" && /^\d{4}-\d{2}-\d{2}/.test(x) ? "'" + x : x ?? ""); // fechas como texto ISO

async function libro() {
  if (_libro) return _libro;
  const c = await configEnvio();
  const it = await g("GET", `/shares/${idCompartido(c.excelUrl.trim())}/driveItem?$select=id,name,webUrl,parentReference`);
  _libro = { base: `/drives/${it.parentReference.driveId}/items/${it.id}/workbook`, nombre: it.name, webUrl: it.webUrl };
  return _libro;
}

/** Comprueba (o crea) la tabla con la cabecera del registro. */
async function asegurarTabla(cab) {
  const c = await configEnvio();
  const L = await libro();
  const t = encodeURIComponent(c.tabla);
  try {
    const h = await g("GET", `${L.base}/tables/${t}/headerRowRange?$select=values`);
    const actual = h.values[0].map(String);
    const faltan = cab.filter((x) => !actual.includes(x));
    if (faltan.length) throw new Error(`La tabla "${c.tabla}" del Excel no tiene ${faltan.length} columnas del formato actual (p. ej. ${faltan.slice(0, 3).join(", ")}). Use un Excel nuevo o avise al data manager.`);
    return actual;
  } catch (e) {
    if (e.status !== 404 && e.codigo !== "ItemNotFound") throw e;
  }
  // Crear la tabla en la primera hoja
  const hojas = await g("GET", `${L.base}/worksheets?$select=name`);
  const hoja = encodeURIComponent(hojas.value[0].name);
  const rango = `A1:${letra(cab.length - 1)}1`;
  await g("PATCH", `${L.base}/worksheets/${hoja}/range(address='${rango}')`, { values: [cab] });
  const tabla = await g("POST", `${L.base}/worksheets/${hoja}/tables/add`, { address: rango, hasHeaders: true });
  await g("PATCH", `${L.base}/tables/${encodeURIComponent(tabla.id || tabla.name)}`, { name: c.tabla });
  return cab;
}

/** Prueba de conexión: inicia sesión, abre el Excel y prepara la tabla. */
export async function probarConexion(dic) {
  const cuenta = await iniciarSesion();
  const L = await libro();
  await asegurarTabla(cabeceraRegistro(dic));
  return { cuenta: cuenta?.username, excel: L.nombre, webUrl: L.webUrl };
}

/**
 * Envía (o actualiza) un caso: UNA FILA POR DIAGNÓSTICO.
 * Cada fila del Excel se reconoce por patient_id + qué diagnóstico vale 1 (o ninguno, si es "Otros").
 * Si se quita un diagnóstico del caso, su fila se vacía (y se reutiliza más adelante).
 * Devuelve {accion, filas, huella, fecha}.
 */
export async function enviarCaso(dic, caso) {
  const c = await configEnvio();
  const cab = cabeceraRegistro(dic);
  const columnasExcel = await asegurarTabla(cab);
  const filas = filasDelCaso(dic, caso, cab);
  const L = await libro();
  const t = encodeURIComponent(c.tabla);
  const columna = async (nombre) => (await g("GET", `${L.base}/tables/${t}/columns/${encodeURIComponent(nombre)}/dataBodyRange?$select=values`)).values.map((r) => r[0]);
  const ids = await columna("patient_id");
  const flags = {};
  for (const [G, cod] of Object.entries(DIAG)) flags[G] = await columna(cod);
  const esDe = (i, G) => (G === "OTRO" ? Object.values(flags).every((col) => String(col[i]) !== "1") : String(flags[G][i]) === "1");
  const usadas = new Set();
  let añadidas = 0, actualizadas = 0;
  for (const { diagnostico, fila } of filas) {
    const porNombre = Object.fromEntries(cab.map((k, i) => [k, fila[i]]));
    const valores = columnasExcel.map((k) => paraExcel(porNombre[k] ?? ""));
    let i = ids.findIndex((x, j) => !usadas.has(j) && String(x) === String(caso.numero) && esDe(j, diagnostico));
    if (i >= 0) actualizadas++;
    else { i = ids.findIndex((x, j) => !usadas.has(j) && (x === "" || x === null)); añadidas++; }
    if (i >= 0) { await g("PATCH", `${L.base}/tables/${t}/rows/itemAt(index=${i})`, { values: [valores] }); usadas.add(i); ids[i] = caso.numero; }
    else { await g("POST", `${L.base}/tables/${t}/rows`, { values: [valores] }); ids.push(caso.numero); usadas.add(ids.length - 1); }
  }
  // Filas antiguas de este caso (diagnóstico retirado): se vacían
  for (let i = 0; i < ids.length; i++) {
    if (!usadas.has(i) && String(ids[i]) === String(caso.numero)) {
      await g("PATCH", `${L.base}/tables/${t}/rows/itemAt(index=${i})`, { values: [columnasExcel.map(() => "")] });
    }
  }
  const accion = añadidas && !actualizadas ? "añadido" : "actualizado";
  return { accion, filas: filas.length, huella: huella(filas.map((x) => x.fila)), fecha: new Date().toISOString() };
}

/** ¿El caso tiene cambios que no se han enviado? */
export function pendienteDeEnvio(dic, caso) {
  const v = caso.valores;
  if (!v.registro_enviado) return "nunca";
  return huella(filasDelCaso(dic, caso).map((x) => x.fila)) === v.registro_huella ? "" : "cambios";
}
