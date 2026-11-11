// MODO NAVEGADOR: la aplicación funciona sin servidor.
// · Los datos se guardan en este navegador (IndexedDB).
// · Y, si se elige una carpeta (p. ej. sincronizada con OneDrive/SharePoint del SMS),
//   se escribe automáticamente un Excel por persona: WILLEM_<usuario>.xlsx
// · El data manager "une" todos los Excel de la carpeta.
// Nada se envía a internet desde aquí: si la carpeta se sube a Office 365 lo hace OneDrive,
// con la cuenta corporativa de cada persona.
import { crearXlsx, leerXlsx, descargar } from "./xlsx.js";

const SITE_ID = "HCUVA";
const MARCAS = ["NC", "DUDA"]; // Desconocido / Duda: en el Excel final van vacíos
const PRINCIPALES = ["IC", "ISQ", "EAO", "MCH", "ATTR", "QTL"];
const TODOS = PRINCIPALES;
const DIAG = { IC: "heart_failure", ISQ: "ischemic_cardiomyopathy", EAO: "aortic_stenosis", MCH: "hypertrophic_cardiomyopathy", ATTR: "amyloidosis_attr", QTL: "long_qt_syndrome" };
const META = ["numero", "principal", "secundarias", "estado", "creado", "creado_por", "modificado", "modificado_por"];
const VERSION_ARCHIVO = 1;

const ahora = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19); };
const err = (msg) => { const e = new Error(msg); throw e; };
const diagnosticos = (p, sec) => Object.fromEntries(Object.entries(DIAG).map(([g, c]) => [c, g === p || sec.includes(g) ? 1 : 0]));

// ---------------------------------------------------------------------------
// IndexedDB
// ---------------------------------------------------------------------------
let _db;
function abrir() {
  if (_db) return _db;
  _db = new Promise((res, rej) => {
    const r = indexedDB.open("willem", 1);
    r.onupgradeneeded = () => {
      const d = r.result;
      d.createObjectStore("kv");
      d.createObjectStore("casos", { keyPath: "numero" });
      d.createObjectStore("auditoria", { keyPath: "id", autoIncrement: true }).createIndex("numero", "numero");
      d.createObjectStore("llave", { keyPath: "numero" });
    };
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
  return _db;
}
async function tx(store, modo, fn) {
  const d = await abrir();
  return new Promise((res, rej) => {
    const t = d.transaction(store, modo);
    let out;
    Promise.resolve(fn(t.objectStore(store))).then((v) => (out = v));
    t.oncomplete = () => res(out);
    t.onerror = () => rej(t.error);
    t.onabort = () => rej(t.error);
  });
}
const req = (r) => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
const kvGet = (k) => tx("kv", "readonly", (s) => req(s.get(k)));
const kvSet = (k, v) => tx("kv", "readwrite", (s) => s.put(v, k));
const todos = (store) => tx(store, "readonly", (s) => req(s.getAll()));
const uno = (store, k) => tx(store, "readonly", (s) => req(s.get(k)));
const poner = (store, v) => tx(store, "readwrite", (s) => s.put(v));
const auditar = (filas) => tx("auditoria", "readwrite", (s) => filas.forEach((f) => s.add(f)));

// ---------------------------------------------------------------------------
// Diccionario
// ---------------------------------------------------------------------------
let _dic;
async function diccionario() {
  if (_dic) return _dic;
  if (window.WILLEM_DIC) return (_dic = window.WILLEM_DIC);
  const r = await fetch("datos/diccionario.json");
  if (!r.ok) err("No se encuentra el diccionario (datos/diccionario.json)");
  return (_dic = await r.json());
}
async function columnas(soloLocal = false) {
  const d = await diccionario();
  const cols = [];
  for (const f of [...d.campos, ...d.locales]) {
    const exp = String(f.exportar_al_registro || "");
    const esLocal = exp.toLowerCase().startsWith("solo local");
    if (exp.toLowerCase() === "no" || esLocal !== soloLocal) continue;
    const spec = String(f.columnas_en_exportacion || f.codigo_variable);
    if (spec.startsWith("(")) continue;
    spec.split(";").map((c) => c.trim()).filter(Boolean).forEach((c) => cols.push(c));
  }
  return cols;
}

// ---------------------------------------------------------------------------
// API emulada (mismas rutas que servidor.py)
// ---------------------------------------------------------------------------
const perfil = () => kvGet("perfil");

export async function apiLocal(metodo, url, b) {
  const [ruta, query] = url.split("?");
  const q = new URLSearchParams(query || "");
  const [rec, id] = ruta.split("/");
  const yo = await perfil();
  const R = `${metodo} ${rec}`;

  if (R === "GET estado") return { necesita_configuracion: !yo, demo: !!(await kvGet("demo")), centro: SITE_ID, usuario: yo || null, modo: "navegador" };
  if (R === "POST configurar") {
    const usuario = (b.usuario || "").trim().toLowerCase();
    if (!/^[a-z0-9._-]{3,30}$/.test(usuario)) err("Usuario: 3-30 letras minúsculas, números, punto o guion (sin espacios ni tildes)");
    if (!(b.nombre || "").trim()) err("Falta el nombre");
    if (!["dm", "intro"].includes(b.rol)) err("Elija el perfil");
    await kvSet("perfil", { id: 1, usuario, nombre: b.nombre.trim(), rol: b.rol });
    navigator.storage?.persist?.();
    return { ok: true };
  }
  if (R === "POST logout") { await vaciarGuardado(); await kvSet("perfil", null); return { ok: true }; }
  if (!yo) err("Identifíquese primero");
  if (R === "GET diccionario") return diccionario();
  if (R === "GET columnas") return { registro: await columnas(false), local: await columnas(true) };

  if (R === "GET casos") {
    if (id) { const c = await uno("casos", +id); if (!c) err("Caso no encontrado"); return c; }
    return (await todos("casos")).sort((a, b2) => (b2.modificado || "").localeCompare(a.modificado || ""));
  }
  if (R === "GET siguiente") {
    const nums = [...(await todos("casos")), ...(await todos("llave"))].map((x) => x.numero);
    return { numero: (nums.length ? Math.max(...nums) : 0) + 1 };
  }
  if (R === "POST casos") {
    const num = parseInt(b.numero, 10);
    if (!(num > 0)) err("Número de caso no válido");
    if (!PRINCIPALES.includes(b.principal)) err("Elija la enfermedad principal");
    if (await uno("casos", num)) err(`El caso ${String(num).padStart(4, "0")} ya existe`);
    const sec = (b.secundarias || []).filter((s) => TODOS.includes(s) && s !== b.principal);
    const t = ahora();
    const caso = { numero: num, principal: b.principal, secundarias: sec, estado: "borrador",
      valores: { site_id: SITE_ID, patient_id: num, authored_at: t, ...diagnosticos(b.principal, sec) },
      creado: t, creado_por: yo.usuario, modificado: t, modificado_por: yo.usuario };
    await poner("casos", caso);
    await auditar([{ numero: num, usuario: yo.usuario, fecha: t, campo: "(caso creado)", antes: null, despues: b.principal, origen: "formulario" }]);
    programarGuardado();
    return { ok: true, numero: num };
  }
  if (R === "PUT casos") {
    const c = await uno("casos", +id);
    if (!c) err("Caso no encontrado");
    if (c.estado === "validado" && yo.rol !== "dm") err("Caso validado: solo un data manager puede modificarlo");
    const origen = ["formulario", "importacion", "relleno_no"].includes(b.origen) ? b.origen : "formulario";
    const cambios = [];
    const valores = { ...c.valores };
    if ("principal" in b || "secundarias" in b) {
      const np = b.principal ?? c.principal;
      if (!PRINCIPALES.includes(np)) err("Enfermedad principal no válida");
      const ns = (b.secundarias ?? c.secundarias).filter((s) => TODOS.includes(s) && s !== np);
      if (np !== c.principal) cambios.push(["(enfermedad principal)", c.principal, np]);
      if (ns.join() !== c.secundarias.join()) cambios.push(["(diagnósticos secundarios)", c.secundarias.join(), ns.join()]);
      c.principal = np; c.secundarias = ns;
      b.valores = { ...(b.valores || {}), ...diagnosticos(np, ns) };
    }
    for (let [k, v] of Object.entries(b.valores || {})) {
      if (["site_id", "patient_id", "authored_at"].includes(k)) continue;
      if (!/^[a-z0-9_]{1,80}$/.test(k)) err("Campo no válido: " + k);
      if (v === "") v = null;
      if ((valores[k] ?? null) !== v) { cambios.push([k, valores[k] ?? null, v]); if (v === null) delete valores[k]; else valores[k] = v; }
    }
    if (b.estado && b.estado !== c.estado && ["borrador", "completo", "validado"].includes(b.estado)) {
      if ((b.estado === "validado" || c.estado === "validado") && yo.rol !== "dm") err("Solo un data manager puede validar");
      if (b.estado === "validado" && Object.values(valores).includes("DUDA")) err("No se puede validar: el caso tiene dudas sin resolver");
      cambios.push(["(estado)", c.estado, b.estado]); c.estado = b.estado;
    }
    if (cambios.length) {
      const t = ahora();
      Object.assign(c, { valores, modificado: t, modificado_por: yo.usuario });
      await poner("casos", c);
      await auditar(cambios.map(([campo, a, d]) => ({ numero: c.numero, usuario: yo.usuario, fecha: t, campo, antes: a == null ? null : String(a), despues: d == null ? null : String(d), origen })));
      programarGuardado();
    }
    return c;
  }
  if (R === "DELETE casos") {
    if (yo.rol !== "dm") err("Solo los data managers pueden hacer esto");
    await tx("casos", "readwrite", (s) => s.delete(+id));
    await auditar([{ numero: +id, usuario: yo.usuario, fecha: ahora(), campo: "(caso eliminado)", antes: null, despues: null, origen: "formulario" }]);
    programarGuardado();
    return { ok: true };
  }
  if (R === "GET auditoria") {
    let filas = q.get("caso") ? await tx("auditoria", "readonly", (s) => req(s.index("numero").getAll(+q.get("caso")))) : await todos("auditoria");
    filas.sort((a, b2) => (b2.fecha || "").localeCompare(a.fecha || "") || b2.id - a.id);
    return filas.slice(0, +(q.get("limite") || 200));
  }
  if (R === "GET llave") {
    if (yo.rol !== "dm") err("Solo los data managers pueden hacer esto");
    let filas = await todos("llave");
    const texto = (q.get("q") || "").trim().toUpperCase();
    if (texto) filas = filas.filter((f) => [f.cip, f.carm, f.nhc, String(f.numero)].some((x) => (x || "").toUpperCase().includes(texto)));
    filas.sort((a, b2) => b2.numero - a.numero);
    return { disponible: true, local: true, total: (await todos("llave")).length, filas: filas.slice(0, 50) };
  }
  if (R === "POST llave") {
    if (yo.rol !== "dm") err("Solo los data managers pueden hacer esto");
    const [cip, carm, nhc] = ["cip", "carm", "nhc"].map((k) => (b[k] || "").trim().toUpperCase());
    if (!cip && !carm && !nhc) err("Introduzca al menos CIP, CARM o NHC");
    const ll = await todos("llave");
    for (const [k, v] of [["cip", cip], ["carm", carm], ["nhc", nhc]]) {
      const ya = v && ll.find((f) => f[k] === v);
      if (ya) err(`Este paciente ya tiene el caso nº ${String(ya.numero).padStart(4, "0")}`);
    }
    const { numero } = await apiLocal("GET", "siguiente");
    await poner("llave", { numero, cip: cip || null, carm: carm || null, nhc: nhc || null, notas: (b.notas || "").trim(), creado: ahora(), creado_por: yo.usuario });
    return { ok: true, numero };
  }
  if (R === "GET usuarios") return [];
  err("Operación no disponible en el modo navegador");
}

// ---------------------------------------------------------------------------
// Exportación final (data manager)
// ---------------------------------------------------------------------------
export async function exportarRegistro(soloValidados = false, formato = "xlsx") {
  const cols = (await columnas(false)).filter((c) => !["site_id", "patient_id", "authored_at"].includes(c));
  const loc = await columnas(true);
  const casos = (await todos("casos")).filter((c) => !soloValidados || c.estado === "validado").sort((a, b) => a.numero - b.numero);
  const dic = await diccionario();
  const copias = Object.fromEntries(dic.campos.filter((d) => String(d.copiar_de || "").trim()).map((d) => [d.codigo_variable, String(d.copiar_de).trim()]));
  const val = (c, k) => { const x = c.valores[copias[k] || k]; return x == null || MARCAS.includes(x) ? "" : x; };
  const reg = [["site_id", "patient_id", "authored_at", ...cols], ...casos.map((c) => [SITE_ID, c.numero, c.creado, ...cols.map((k) => val(c, k))])];
  const sello = ahora().replace(/[-:]/g, "").replace("T", "_").slice(0, 13);
  if (formato === "csv") {
    const csv = reg.map((f) => f.map((x) => { const s = String(x ?? ""); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(";")).join("\r\n");
    return descargar(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }), `WILLEM_${SITE_ID}_${sello}.csv`);
  }
  const hojas = [["WILLEM_registro", reg]];
  if (loc.length) hojas.push(["Solo_local_NO_ENVIAR", [["patient_id", ...loc], ...casos.map((c) => [c.numero, ...loc.map((k) => val(c, k))])]]);
  const marcas = casos.flatMap((c) => Object.entries(c.valores).filter(([, x]) => MARCAS.includes(x)).sort()
    .map(([k, x]) => [c.numero, k, x === "NC" ? "Desconocido" : "Duda", c.valores[k + "_duda_nota"] || ""]));
  if (marcas.length) hojas.push(["Desconocido_Duda_NO_ENVIAR", [["patient_id", "variable", "estado", "nota_duda"], ...marcas]]);
  descargar(crearXlsx(hojas), `WILLEM_${SITE_ID}_${sello}.xlsx`);
}

export async function exportarLlave() {
  const ll = (await todos("llave")).sort((a, b) => a.numero - b.numero);
  descargar(crearXlsx([["LLAVE", [["numero", "cip", "carm", "nhc", "notas", "creado", "creado_por"], ...ll.map((f) => [f.numero, f.cip, f.carm, f.nhc, f.notas, f.creado, f.creado_por])]]]),
    `LLAVE_WILLEM_NO_COMPARTIR_${ahora().slice(0, 10)}.xlsx`);
}
export async function importarLlave(file) {
  const h = await leerXlsx(await file.arrayBuffer());
  const filas = h.LLAVE || Object.values(h)[0] || [];
  const cab = filas[0] || [];
  let n = 0;
  for (const f of filas.slice(1)) {
    const o = Object.fromEntries(cab.map((k, i) => [k, f[i] ?? null]));
    if (!o.numero) continue;
    o.numero = +o.numero;
    if (!(await uno("llave", o.numero))) { await poner("llave", o); n++; }
  }
  return n;
}

// ---------------------------------------------------------------------------
// Archivo de trabajo de cada persona: WILLEM_<usuario>.xlsx
// ---------------------------------------------------------------------------
async function archivoTrabajo() {
  const yo = await perfil();
  const cols = await columnas(false);
  const casos = (await todos("casos")).sort((a, b) => a.numero - b.numero);
  const aud = (await todos("auditoria")).sort((a, b) => a.id - b.id);
  const cab = [...META, ...cols.filter((c) => !META.includes(c)), "json_valores"];
  const filas = casos.map((c) => [c.numero, c.principal, c.secundarias.join(","), c.estado, c.creado, c.creado_por, c.modificado, c.modificado_por,
    ...cols.filter((k) => !META.includes(k)).map((k) => c.valores[k] ?? ""), JSON.stringify(c.valores)]);
  return crearXlsx([
    ["casos", [cab, ...filas]],
    ["historial", [["numero", "usuario", "fecha", "campo", "antes", "despues", "origen"], ...aud.map((a) => [a.numero, a.usuario, a.fecha, a.campo, a.antes, a.despues, a.origen])]],
    ["info", [["clave", "valor"], ["aplicacion", "Registro WILLEM"], ["version_archivo", VERSION_ARCHIVO], ["usuario", yo?.usuario], ["nombre", yo?.nombre], ["generado", ahora()],
      ["aviso", "Archivo de trabajo. No editar a mano: use la aplicación. Contiene solo números de caso (sin datos identificativos)."]]],
  ]);
}

async function leerArchivoTrabajo(buffer) {
  const h = await leerXlsx(buffer);
  if (!h.casos) err("Este Excel no es un archivo de trabajo de WILLEM");
  const [cab, ...filas] = h.casos;
  const ix = Object.fromEntries(cab.map((k, i) => [k, i]));
  const casos = filas.filter((f) => f[ix.numero]).map((f) => {
    let valores;
    try { valores = JSON.parse(f[ix.json_valores]); } catch { valores = {}; }
    return { numero: +f[ix.numero], principal: f[ix.principal], secundarias: f[ix.secundarias] ? String(f[ix.secundarias]).split(",") : [],
      estado: f[ix.estado] || "borrador", creado: f[ix.creado], creado_por: f[ix.creado_por], modificado: f[ix.modificado], modificado_por: f[ix.modificado_por], valores };
  });
  const aud = (h.historial || []).slice(1).filter((f) => f[0] != null).map((f) => ({ numero: +f[0], usuario: f[1], fecha: f[2], campo: f[3], antes: f[4] ?? null, despues: f[5] ?? null, origen: f[6] }));
  const info = Object.fromEntries((h.info || []).slice(1).map((f) => [f[0], f[1]]));
  return { casos, aud, info };
}

/** Une casos y su historial en la base de este navegador. Gana la versión modificada más recientemente. */
async function fusionar({ casos, aud }, origenNombre) {
  const rep = { archivo: origenNombre, nuevos: 0, actualizados: 0, iguales: 0, conservados: 0, conflictos: [] };
  for (const c of casos) {
    const l = await uno("casos", c.numero);
    if (!l) { await poner("casos", c); rep.nuevos++; continue; }
    if (l.creado_por !== c.creado_por && l.creado !== c.creado) {
      rep.conflictos.push(`#${String(c.numero).padStart(4, "0")}: creado por ${l.creado_por} y por ${c.creado_por} (¿número repetido?)`);
      continue;
    }
    if ((c.modificado || "") > (l.modificado || "")) { await poner("casos", c); rep.actualizados++; }
    else if ((c.modificado || "") === (l.modificado || "")) rep.iguales++;
    else rep.conservados++;
  }
  const existentes = new Set((await todos("auditoria")).map((a) => [a.numero, a.usuario, a.fecha, a.campo].join("|")));
  const nuevas = aud.filter((a) => !existentes.has([a.numero, a.usuario, a.fecha, a.campo].join("|")));
  if (nuevas.length) await auditar(nuevas);
  return rep;
}

// ---------------------------------------------------------------------------
// Carpeta compartida (OneDrive / SharePoint sincronizado)
// ---------------------------------------------------------------------------
export const soportaCarpeta = () => "showDirectoryPicker" in window;
// La carpeta elegida se recuerda entre sesiones (IndexedDB) y se mantiene en memoria.
let _carpeta;
async function carpeta() {
  if (window.__WILLEM_CARPETA_PRUEBAS) return window.__WILLEM_CARPETA_PRUEBAS; // solo pruebas automáticas
  if (_carpeta === undefined) _carpeta = (await kvGet("carpeta")) || null;
  return _carpeta;
}
const nombreArchivo = (u) => `WILLEM_${u}.xlsx`;
const estado = { ultimo: null, error: null, guardando: false, timer: null, oyentes: new Set() };
const avisar = () => estado.oyentes.forEach((f) => f());
export const alCambiarEstado = (f) => estado.oyentes.add(f);

export async function infoCarpeta() {
  const h = await carpeta();
  let permiso = null;
  if (h) { try { permiso = await h.queryPermission({ mode: "readwrite" }); } catch { permiso = null; } }
  const yo = await perfil();
  return { soportada: soportaCarpeta(), nombre: h ? h.name || "(carpeta)" : null, permiso, ultimo: estado.ultimo || (await kvGet("ultimoGuardado")), error: estado.error,
    guardando: estado.guardando, archivo: yo ? nombreArchivo(yo.usuario) : null, pendiente: !!estado.timer };
}

export async function elegirCarpeta() {
  const h = await window.showDirectoryPicker({ id: "willem", mode: "readwrite" });
  await kvSet("carpeta", h);
  _carpeta = h;
  const yo = await perfil();
  let rep = null;
  try {
    const fh = await h.getFileHandle(nombreArchivo(yo.usuario));
    rep = await fusionar(await leerArchivoTrabajo(await (await fh.getFile()).arrayBuffer()), fh.name);
  } catch (e) { if (e.name !== "NotFoundError") throw e; }
  await guardarAhora();
  return rep;
}

export async function reconectarCarpeta() {
  const h = await carpeta();
  if (!h) return false;
  const p = await h.requestPermission({ mode: "readwrite" });
  if (p === "granted") await guardarAhora();
  return p === "granted";
}

export async function olvidarCarpeta() { await kvSet("carpeta", null); _carpeta = null; estado.error = null; avisar(); }

function programarGuardado() {
  clearTimeout(estado.timer);
  estado.timer = setTimeout(() => { estado.timer = null; guardarAhora(); }, 1500);
  avisar();
}
async function vaciarGuardado() { if (estado.timer) { clearTimeout(estado.timer); estado.timer = null; await guardarAhora(); } }
window.addEventListener("pagehide", () => { if (estado.timer) guardarAhora(); });

export async function guardarAhora() {
  const h = await carpeta();
  const yo = await perfil();
  if (!h || !yo) { avisar(); return false; }
  try {
    if ((await h.queryPermission({ mode: "readwrite" })) !== "granted") { estado.error = "permiso"; avisar(); return false; }
    estado.guardando = true; avisar();
    const fh = await h.getFileHandle(nombreArchivo(yo.usuario), { create: true });
    const w = await fh.createWritable();
    await w.write(await archivoTrabajo());
    await w.close();
    estado.ultimo = ahora(); estado.error = null;
    await kvSet("ultimoGuardado", estado.ultimo);
    return true;
  } catch (e) {
    estado.error = e.message || String(e);
    return false;
  } finally { estado.guardando = false; avisar(); }
}

export async function descargarCopia() {
  const yo = await perfil();
  descargar(await archivoTrabajo(), nombreArchivo(yo.usuario));
}

/** Data manager: lee todos los WILLEM_*.xlsx de la carpeta y los une. */
export async function unirCarpeta() {
  const h = await carpeta();
  if (!h) err("Primero vincule la carpeta compartida");
  if ((await h.queryPermission({ mode: "read" })) !== "granted" && (await h.requestPermission({ mode: "readwrite" })) !== "granted") err("Sin permiso para leer la carpeta");
  const yo = await perfil();
  const informes = [];
  for await (const [nombre, entrada] of h.entries()) {
    if (entrada.kind !== "file" || !/^WILLEM_.+\.xlsx$/i.test(nombre) || nombre === nombreArchivo(yo.usuario)) continue;
    try { informes.push(await fusionar(await leerArchivoTrabajo(await (await entrada.getFile()).arrayBuffer()), nombre)); }
    catch (e) { informes.push({ archivo: nombre, error: e.message }); }
  }
  await guardarAhora();
  return informes;
}

/** Sin carpeta (Safari/Firefox): unir archivos elegidos a mano. */
export async function unirArchivos(files) {
  const informes = [];
  for (const f of files) {
    try { informes.push(await fusionar(await leerArchivoTrabajo(await f.arrayBuffer()), f.name)); }
    catch (e) { informes.push({ archivo: f.name, error: e.message }); }
  }
  programarGuardado();
  return informes;
}

// ---------------------------------------------------------------------------
// Demostración
// ---------------------------------------------------------------------------
export async function cargarDemo() {
  let d = window.WILLEM_DEMO;
  if (!d) { const r = await fetch("datos/demo.json").catch(() => null); d = r && r.ok ? await r.json() : null; }
  if (!d) err("No se encuentran los datos de demostración");
  for (const c of d.casos) await poner("casos", c);
  await auditar(d.auditoria.map(({ id, ...a }) => a));
  for (const l of d.llave) await poner("llave", l);
  await kvSet("demo", true);
}

export async function borrarTodo() {
  const d = await abrir();
  d.close(); _db = null;
  await new Promise((res, rej) => { const r = indexedDB.deleteDatabase("willem"); r.onsuccess = res; r.onerror = () => rej(r.error); r.onblocked = res; });
}
