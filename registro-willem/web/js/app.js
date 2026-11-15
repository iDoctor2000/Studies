// Registro WILLEM · aplicación web local
import { icono, ENFERMEDADES, PRINCIPALES } from "./iconos.js";
import { construirModelo, pestanasDelCaso, progresoPestana, progresoCaso, progresoItems, rellenarNo, visible,
  NC, DUDA, esMarca, marcaDe, admiteMarcas, dudasDelCaso, valoresPorDefecto, diagnosticosDe } from "./modelo.js";
import { anonimizar, extraer, EJEMPLO } from "./importador.js";
import * as L from "./local.js";
import * as ENV from "./envio.js";
import { comprobarClave, accesoConcedido, recordarAcceso } from "./acceso.js";
import { iaPendientes, marcarPorCampos, NOMBRE_ORIGEN, auditar, diagnosticosTexto } from "./ia.js";
import { crearXlsx, descargar } from "./xlsx.js";

// ===========================================================================
//  Utilidades
// ===========================================================================
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(4, "0");
const S = { info: null, yo: null, modelo: null, casos: [], modo: "servidor" };
const navegador = () => S.modo === "navegador";
const E = { caso: null, tab: null, pend: {}, origen: null, timer: null, guardando: false };

async function api(metodo, url, cuerpo, opts = {}) {
  if (navegador()) return L.apiLocal(metodo, url, cuerpo ? JSON.parse(JSON.stringify(cuerpo)) : undefined);
  const r = await fetch("api/" + url, {
    method: metodo, credentials: "same-origin", keepalive: !!opts.keepalive,
    headers: cuerpo ? { "Content-Type": "application/json" } : {},
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const datos = await r.json().catch(() => ({}));
  if (r.status === 401 && !url.startsWith("login")) { S.yo = null; pintarLogin(); throw new Error(datos.error || "Sesión caducada"); }
  if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
  return datos;
}

function toast(msg, tipo = "ok") {
  const t = document.createElement("div");
  t.className = "toast " + tipo;
  t.innerHTML = icono(tipo === "ok" ? "check" : tipo === "mal" ? "aviso" : "info") + `<span>${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = 0; setTimeout(() => t.remove(), 300); }, 3200);
}

function modal({ titulo, html, aceptar = "Aceptar", cancelar = "Cancelar", peligro = false, alAbrir, alAceptar }) {
  return new Promise((res) => {
    const velo = document.createElement("div");
    velo.className = "velo alto";
    const m = document.createElement("div");
    m.className = "modal";
    m.innerHTML = `<div class="cab"><h3>${esc(titulo)}</h3></div><div class="cuerpo">${html || ""}</div>
      <div class="pie">${cancelar ? `<button class="btn fantasma" data-x>${esc(cancelar)}</button>` : ""}
      <button class="btn ${peligro ? "peligro" : "primario"}" data-ok>${esc(aceptar)}</button></div>`;
    const cerrar = (v) => { velo.remove(); m.remove(); res(v); };
    velo.onclick = () => cerrar(false);
    m.querySelector("[data-x]")?.addEventListener("click", () => cerrar(false));
    m.querySelector("[data-ok]").addEventListener("click", async () => {
      if (alAceptar) { try { const r = await alAceptar(m); if (r === false) return; } catch (e) { const er = m.querySelector(".error"); if (er) er.textContent = e.message; else toast(e.message, "mal"); return; } }
      cerrar(true);
    });
    document.body.append(velo, m);
    alAbrir?.(m);
    m.querySelector("input,select,button[data-ok]")?.focus();
  });
}

function relativo(iso) {
  if (!iso) return "";
  const d = new Date(iso), s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "ahora mismo";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  if (s < 86400 * 2) return "ayer";
  if (s < 86400 * 30) return `hace ${Math.floor(s / 86400)} días`;
  return d.toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" });
}
const fmtFecha = (f) => (f ? new Date(f).toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" }) : "");
const iniciales = (n) => (n || "?").replace(/\(.*?\)/g, "").trim().split(/\s+/).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
const colorDe = (txt) => { let h = 0; for (const c of txt || "") h = (h * 31 + c.charCodeAt(0)) % 360; return `hsl(${h} 55% 48%)`; };

function anillo(pct, tam = 44, grosor = 5, color = "var(--c)") {
  const r = (tam - grosor) / 2, c = 2 * Math.PI * r;
  return `<span class="anillo" style="width:${tam}px;height:${tam}px">
    <svg width="${tam}" height="${tam}"><circle class="fondo" cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke-width="${grosor}"/>
    <circle class="valor" cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${grosor}" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct / 100)}"/></svg><b>${pct}%</b></span>`;
}

const pillEnf = (g, sec = false) => {
  const e = ENFERMEDADES[g];
  return e ? `<span class="pill ${sec ? "sec" : ""}" style="--c:${e.color}">${sec ? "" : icono(g)}${esc(sec ? e.corto : e.nombre)}</span>` : "";
};
const estadoPill = (e) => `<span class="estado ${e}">${{ borrador: "Borrador", completo: "Completo", validado: "Validado" }[e] || e}</span>`;
const esDM = () => S.yo?.rol === "dm";
// Cardiólogo revisor: revisa, corrige y valida casos, y ve la auditoría de la IA. No importa, exporta ni gestiona usuarios.
const puedeRevisar = () => ["dm", "rev"].includes(S.yo?.rol);
const NOMBRE_ROL = { dm: "Data manager", rev: "Cardiólogo revisor", intro: "Introducción de datos" };
const COLOR_ROL = { dm: "#7c3aed", rev: "#0369a1", intro: "#0f766e" };

// ===========================================================================
//  Arranque y enrutado
// ===========================================================================
async function detectarModo() {
  if (window.WILLEM_MODO === "navegador" || location.protocol === "file:") return "navegador";
  try {
    const r = await fetch("api/estado", { credentials: "same-origin" });
    const d = await r.json();
    if (d && d.centro) return "servidor";
  } catch { /* sin servidor */ }
  return "navegador";
}

async function arrancar() {
  aplicarTema();
  S.modo = await detectarModo();
  document.body.dataset.modo = S.modo;
  // Versión web (sin servidor): contraseña común del equipo antes de entrar
  if (navegador() && !accesoConcedido()) await pedirClave();
  try {
    S.info = await api("GET", "estado");
  } catch (e) {
    $("#raiz").innerHTML = `<div class="vacio">${icono("aviso")}<p>No se puede abrir la aplicación: ${esc(e.message)}</p></div>`;
    return;
  }
  if (navegador() && !S.info.usuario) return pintarPerfil();
  if (S.info.necesita_configuracion) return pintarConfiguracion();
  if (!S.info.usuario) return pintarLogin();
  S.yo = S.info.usuario;
  await entrar();
}

async function entrar() {
  const dic = await api("GET", "diccionario");
  S.dic = dic;
  S.modelo = construirModelo(dic);
  if (localStorage.getItem("willem_codigos") === null) localStorage.setItem("willem_codigos", puedeRevisar() ? "1" : "0");
  document.body.classList.toggle("sin-codigos", localStorage.getItem("willem_codigos") !== "1");
  pintarEstructura();
  window.onhashchange = enrutar;
  enrutar();
}

async function enrutar() {
  await vaciarPendientes();
  const [ruta, query] = (location.hash.slice(2) || "panel").split("?");
  const qs = new URLSearchParams(query || "");
  const [pag, a, b] = ruta.split("/").map((x) => { try { return decodeURIComponent(x); } catch { return x; } });
  $$(".nav a").forEach((x) => x.classList.toggle("activo", x.dataset.pag === pag || (pag === "caso" && x.dataset.pag === "casos")));
  window.scrollTo(0, 0);
  const c = $("#contenido");
  c.classList.remove("vintage");
  c.innerHTML = `<div class="cargando">${icono("logo", "latido-logo")}</div>`;
  try {
    if (pag === "panel") await pPanel();
    else if (pag === "casos") await pCasos(qs);
    else if (pag === "nuevo") await pNuevo(qs);
    else if (pag === "caso") await pCaso(+a, b);
    else if (pag === "llave" && esDM() && !S.info?.nas) await pLlave();
    else if (pag === "exportar" && esDM()) await pExportar();
    else if (pag === "usuarios" && esDM()) await pUsuarios();
    else if (pag === "diccionario") await pDiccionario();
    else if (pag === "dudas") await pDudas();
    else if (pag === "envio" && esDM() && !S.info?.nas) await pEnvio();
    else if (pag === "ia" && esDM()) await pIA();
    else if (pag === "auditoria" && puedeRevisar()) await pAuditoria();
    else if (pag === "carpeta" && navegador()) await pCarpeta();
    else if (pag === "unir" && navegador() && esDM()) await pUnir();
    else location.hash = "#/panel";
  } catch (e) {
    c.innerHTML = `<div class="vacio">${icono("aviso")}<p>${esc(e.message)}</p></div>`;
  }
}

function barra(titulo, migas = "", der = "") {
  $("#barra").innerHTML = `<div><div class="migas">${migas}</div><h1>${esc(titulo)}</h1></div>
    <div class="der">${der}
      <button class="btn fantasma btn-icono" id="btnCodigos" title="Mostrar / ocultar códigos de variable">${icono("codigo")}</button>
      <button class="btn fantasma btn-icono" id="btnTema" title="Tema claro / oscuro">${icono(document.documentElement.dataset.tema === "oscuro" ? "sol" : "luna")}</button>
    </div>`;
  $("#btnTema").onclick = () => { const t = document.documentElement.dataset.tema === "oscuro" ? "claro" : "oscuro"; localStorage.setItem("willem_tema", t); aplicarTema(); barra(titulo, migas, der); };
  $("#btnCodigos").onclick = () => {
    const on = localStorage.getItem("willem_codigos") !== "1";
    localStorage.setItem("willem_codigos", on ? "1" : "0");
    document.body.classList.toggle("sin-codigos", !on);
    toast(on ? "Códigos de variable visibles" : "Códigos de variable ocultos", "info");
  };
}

function aplicarTema() {
  const t = localStorage.getItem("willem_tema");
  if (t) document.documentElement.dataset.tema = t;
  else if (matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.dataset.tema = "oscuro";
}

// ===========================================================================
//  Login / configuración inicial
// ===========================================================================
// Electrocardiograma tipo monitor: 4 latidos (onda P, QRS, onda T) a lo ancho de la pantalla.
// Un punto luminoso dibuja la traza de izquierda a derecha y va borrando por delante el trazo
// anterior; al llegar al final vuelve a empezar por la izquierda.
const LATIDO = 350;
const ECG_PATH = "M0 80 " + Array.from({ length: 4 }, (_, k) => {
  const x = k * LATIDO;
  return `H${x} l12 -6 l10 6 H${x + 80} l8 10 l12 -70 l14 96 l10 -36 H${x + 200} q18 -22 36 0 H${x + LATIDO}`;
}).join(" ");
const ecgSvg = (clase) => `<svg class="${clase}" viewBox="0 0 1400 160" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <path class="ecg-barrido" d="${ECG_PATH}"/><circle class="ecg-punta" r="4.5" cx="-20" cy="80"/></svg>`;

const ECG_CICLO = 6500;  // ms por barrido: 4 latidos, trazado lento y sereno
const ECG_HUECO = 90;    // trozo borrado por delante del punto
function animarECG(t) {
  for (const p of document.querySelectorAll(".ecg-barrido")) {
    const L = +(p.dataset.l ||= p.getTotalLength());
    const punta = p.nextElementSibling;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { p.style.strokeDasharray = "none"; punta.style.display = "none"; continue; }
    const h = ((t % ECG_CICLO) / ECG_CICLO) * L;           // distancia recorrida por el punto
    p.style.strokeDasharray = `${L - ECG_HUECO} ${ECG_HUECO}`;
    p.style.strokeDashoffset = `${L - ECG_HUECO - h}`; // hueco justo por delante del punto
    const q = p.getPointAtLength(h);
    punta.setAttribute("cx", q.x); punta.setAttribute("cy", q.y);
  }
  requestAnimationFrame(animarECG);
}
requestAnimationFrame(animarECG);

function heroe() {
  return `<div class="heroe">
    <div class="marca" style="padding:0">
      <div class="logo">${icono("logo")}</div>
      <div><b>WILLEM</b><span>H.C.U. Virgen de la Arrixaca</span></div>
    </div>
    ${ecgSvg("ecg")}
    <div>
      <h1>Registro clínico de <span>cardiopatías</span></h1>
      <p>Insuficiencia cardiaca, cardiopatía isquémica, estenosis aórtica, miocardiopatía hipertrófica y amiloidosis ATTR. Todo gira en torno a la enfermedad principal de cada paciente.</p>
      <div class="sellos">
        <span>${icono("candado")} 100 % local, sin internet</span>
        <span>${icono("escudo")} Datos seudonimizados</span>
        <span>${icono("historial")} Registro de cambios</span>
      </div>
    </div>
  </div>`;
}

function pedirClave() {
  return new Promise((resolver) => {
    $("#raiz").innerHTML = `<div class="login">${heroe()}
      <div class="lado"><form class="caja form" id="fClave" autocomplete="off">
        <div><h2>Acceso restringido</h2><div class="sub">Escriba la contraseña del equipo del estudio.</div></div>
        <label>Contraseña<input class="inp" type="password" name="clave" required autofocus autocomplete="current-password"></label>
        <label style="flex-direction:row;align-items:center;gap:8px;font-weight:500"><input type="checkbox" name="recordar" checked> Recordar en este dispositivo</label>
        <div class="error" id="errClave"></div>
        <button class="btn primario grande" style="justify-content:center">${icono("candado")} Entrar</button>
      </form></div></div>`;
    const f = $("#fClave");
    let fallos = 0;
    f.onsubmit = async (ev) => {
      ev.preventDefault();
      const b = f.querySelector("button"); b.disabled = true;
      const ok = await comprobarClave(f.clave.value).catch(() => false);
      b.disabled = false;
      if (ok) { recordarAcceso(f.recordar.checked); return resolver(); }
      fallos++;
      $("#errClave").textContent = "Contraseña incorrecta";
      f.clave.value = ""; f.clave.focus();
      if (fallos >= 3) { b.disabled = true; setTimeout(() => (b.disabled = false), 3000 * fallos); }
    };
  });
}

function pintarLogin() {
  window.onhashchange = null;
  $("#raiz").innerHTML = `<div class="login">${heroe()}
    <div class="lado"><form class="caja form" id="fLogin" autocomplete="on">
      <div><h2>Bienvenida, bienvenido</h2><div class="sub">Inicie sesión para continuar</div></div>
      <label>Usuario<input class="inp" name="usuario" autocomplete="username" required autofocus></label>
      <label>Contraseña<input class="inp" type="password" name="clave" autocomplete="current-password" required></label>
      <div class="error" id="errLogin"></div>
      <button class="btn primario grande" style="justify-content:center">Entrar ${icono("flechaD")}</button>
      ${S.info?.demo ? `<div class="pista-demo"><b>Modo demostración</b> (pacientes inventados).<br>Data manager: <code>admin</code> · Cardiólogo revisor: <code>revisor</code> · Introductora: <code>carmen</code> · Contraseña: <code>willem2026</code></div>` : ""}
    </form></div></div>`;
  $("#fLogin").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try {
      await continuarLogin(await api("POST", "login", { usuario: f.get("usuario"), clave: f.get("clave") }));
    } catch (e) { $("#errLogin").textContent = e.message; }
  };
}

// ---------------------------------------------------------------------------
//  Doble factor (código de 6 cifras de una aplicación del móvil)
// ---------------------------------------------------------------------------
async function continuarLogin(r) {
  if (r?.paso === "codigo") return pedirCodigo(r.desafio);
  if (r?.paso === "configurar_2fa") return configurarDobleFactor(r);
  S.info = await api("GET", "estado");
  S.yo = S.info.usuario;
  if (r?.recuperacion) await mostrarRecuperacion(r.recuperacion);
  if (!location.hash || location.hash === "#/") location.hash = "#/panel";
  await entrar();
}

const cajaLogin = (html) => { $("#raiz").innerHTML = `<div class="login">${heroe()}<div class="lado">${html}</div></div>`; };
const inputCodigo = `<input class="inp codigo-2fa" name="codigo" inputmode="numeric" autocomplete="one-time-code" maxlength="9" placeholder="000 000" required autofocus>`;

function pedirCodigo(desafio) {
  cajaLogin(`<form class="caja form" id="fCod">
    <div class="ic-2fa">${icono("escudo")}</div>
    <div><h2>Verificación en dos pasos</h2><div class="sub">Abra la aplicación de códigos de su móvil y escriba el código de 6 cifras de <b>WILLEM Arrixaca</b>.</div></div>
    <label>Código${inputCodigo}</label>
    <div class="error" id="errCod"></div>
    <button class="btn primario grande" style="justify-content:center">Verificar ${icono("flechaD")}</button>
    <details class="ayuda-2fa"><summary>¿Ha perdido o cambiado el móvil?</summary>
      Escriba en la casilla uno de sus <b>códigos de recuperación</b> (del tipo <code>abcd-1234</code>); cada uno sirve una sola vez.
      Si no los tiene, pida a un data manager que le <b>reinicie el doble factor</b>.</details>
    <a href="#" id="volverLogin" class="sub">${icono("flechaI")} Volver</a>
  </form>`);
  $("#volverLogin").onclick = (ev) => { ev.preventDefault(); pintarLogin(); };
  $("#fCod").onsubmit = async (ev) => {
    ev.preventDefault();
    const codigo = new FormData(ev.target).get("codigo").replace(/\s/g, "");
    try { await continuarLogin(await api("POST", "login/codigo", { desafio, codigo })); }
    catch (e) { $("#errCod").textContent = e.message; if (/caducado/.test(e.message)) setTimeout(pintarLogin, 2200); }
  };
}

const cargarScript = (src) => new Promise((ok, mal) => {
  if (document.querySelector(`script[src="${src}"]`)) return ok();
  const sc = document.createElement("script"); sc.src = src; sc.onload = ok; sc.onerror = () => mal(new Error("No se pudo cargar " + src));
  document.head.append(sc);
});

async function configurarDobleFactor(r) {
  let qr = "";
  try {
    await cargarScript("vendor/qrcode.js");
    const q = window.qrcode(0, "M"); q.addData(r.uri); q.make();
    qr = q.createSvgTag(4, 2);
  } catch { qr = ""; }
  const clave = r.secreto.replace(/(.{4})/g, "$1 ").trim();
  cajaLogin(`<form class="caja form ancha" id="fAlta">
    <div class="ic-2fa">${icono("escudo")}</div>
    <div><h2>Active la verificación en dos pasos</h2><div class="sub">Por seguridad, el registro pide además un código que cambia cada 30 segundos en su móvil. Solo hay que configurarlo una vez.</div></div>
    <ol class="pasos-2fa">
      <li><b>Instale una aplicación de códigos</b> en el móvil: Google Authenticator, Microsoft Authenticator o, en el iPhone, la app <i>Contraseñas</i>.</li>
      <li><b>Escanee este código</b> con la aplicación («Añadir cuenta» → «Escanear código QR»):
        <div class="qr-2fa">${qr || "<span class='sub'>(no se ha podido dibujar el QR: use la clave de abajo)</span>"}</div>
        <div class="clave-2fa">¿No puede escanear? Elija «Introducir clave» y escriba: <code>${esc(clave)}</code> (cuenta: <b>${esc(r.usuario)}</b>)</div></li>
      <li><b>Escriba el código de 6 cifras</b> que le muestra ahora la aplicación:${inputCodigo}</li>
    </ol>
    <div class="error" id="errAlta"></div>
    <button class="btn primario grande" style="justify-content:center">${icono("check")} Activar y entrar</button>
    <a href="#" id="volverLogin" class="sub">${icono("flechaI")} Volver</a>
  </form>`);
  $("#volverLogin").onclick = (ev) => { ev.preventDefault(); pintarLogin(); };
  $("#fAlta").onsubmit = async (ev) => {
    ev.preventDefault();
    const codigo = new FormData(ev.target).get("codigo").replace(/\s/g, "");
    try { await continuarLogin(await api("POST", "login/activar", { desafio: r.desafio, codigo })); }
    catch (e) { $("#errAlta").textContent = e.message; if (/caducado/.test(e.message)) setTimeout(pintarLogin, 2200); }
  };
}

function mostrarRecuperacion(codigos) {
  return modal({
    titulo: "Guarde sus códigos de recuperación", cancelar: "", aceptar: "Ya los he guardado",
    html: `<p>Sirven para entrar si pierde o cambia el móvil. <b>Cada uno se puede usar una sola vez</b> y no se volverán a mostrar.</p>
      <div class="codigos-rec">${codigos.map((c) => `<code>${esc(c)}</code>`).join("")}</div>
      <p class="sub">Guárdelos en un sitio seguro (por ejemplo, impresos o en el gestor de contraseñas), nunca junto al libro llave.</p>
      <button class="btn pequeno" id="copRec">${icono("importar")} Copiar</button>`,
    alAbrir: (m) => { $("#copRec", m).onclick = async () => { try { await navigator.clipboard.writeText(codigos.join("\n")); toast("Copiados"); } catch { toast("Selecciónelos y cópielos a mano", "info"); } }; },
  });
}

function pintarConfiguracion() {
  $("#raiz").innerHTML = `<div class="login">${heroe()}
    <div class="lado"><form class="caja form" id="fConf">
      <div><h2>Primera puesta en marcha</h2><div class="sub">Cree la cuenta del primer <b>data manager</b>. Después podrá dar de alta al resto del equipo.</div></div>
      <label>Nombre y apellidos<input class="inp" name="nombre" required></label>
      <label>Usuario<input class="inp" name="usuario" required pattern="[a-zA-Z0-9._\\-]{3,30}"></label>
      <div class="fila"><label>Contraseña<input class="inp" type="password" name="clave" required minlength="8"></label>
      <label>Repetir<input class="inp" type="password" name="clave2" required minlength="8"></label></div>
      <div class="error" id="errConf"></div>
      <button class="btn primario grande" style="justify-content:center">Crear y entrar</button>
    </form></div></div>`;
  $("#fConf").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = Object.fromEntries(new FormData(ev.target));
    if (f.clave !== f.clave2) return ($("#errConf").textContent = "Las contraseñas no coinciden");
    try {
      await api("POST", "configurar", f);
      location.hash = "#/panel";
      await continuarLogin(await api("POST", "login", { usuario: f.usuario, clave: f.clave }));
    } catch (e) { $("#errConf").textContent = e.message; }
  };
}

// ===========================================================================
//  Estructura (barra lateral)
// ===========================================================================
function pintarEstructura() {
  const dm = esDM();
  $("#raiz").innerHTML = `<div class="app">
    <aside class="lateral">
      <a class="marca" href="#/panel"><div class="logo">${icono("logo")}</div><div><b>WILLEM</b><span>Registro · Arrixaca</span></div></a>
      <a class="nuevo-caso" href="#/nuevo">${icono("mas")} Nuevo caso</a>
      <nav class="nav">
        <div class="titulo">Trabajo</div>
        <a href="#/panel" data-pag="panel">${icono("panel")} Panel</a>
        <a href="#/casos" data-pag="casos">${icono("casos")} Casos <span class="contador" id="nCasos"></span></a>
        <a href="#/dudas" data-pag="dudas">${icono("bandera")} Dudas <span class="contador aviso oculto" id="nDudas"></span></a>
        <a href="#/diccionario" data-pag="diccionario">${icono("libro")} Diccionario</a>
        ${dm ? `<div class="titulo">Data manager</div>
        ${S.info?.nas ? "" : `<a href="#/llave" data-pag="llave">${icono("llave")} Libro llave</a>`}
        <a href="#/ia" data-pag="ia">${icono("chispa")} Importar de la IA</a>
        <a href="#/auditoria" data-pag="auditoria">${icono("lupa")} Auditoría de la IA</a>
        ${navegador() ? `<a href="#/unir" data-pag="unir">${icono("unir")} Unir casos</a>` : ""}
        ${S.info?.nas ? "" : `<a href="#/envio" data-pag="envio">${icono("enviar")} Envío al registro</a>`}
        <a href="#/exportar" data-pag="exportar">${icono("exportar")} Exportar</a>
        ${navegador() ? "" : `<a href="#/usuarios" data-pag="usuarios">${icono("usuarios")} Usuarios</a>`}` : ""}
        ${S.yo?.rol === "rev" ? `<div class="titulo">Revisión</div>
        <a href="#/auditoria" data-pag="auditoria">${icono("lupa")} Auditoría de la IA</a>` : ""}
        ${navegador() ? `<div class="titulo">Guardado</div><a href="#/carpeta" data-pag="carpeta">${icono("nube")} Carpeta compartida</a>` : ""}
      </nav>
      <div class="pie-lateral">
        ${S.info.demo ? `<div class="cinta-demo">MODO DEMOSTRACIÓN · datos ficticios</div>` : ""}
        ${navegador() ? `<button class="estado-carpeta" id="estCarpeta"></button>` : `<div class="local-ok">${icono("candado")} Funcionando en local · sin internet</div>`}
        <div class="tarjeta-usuario">
          <div class="avatar" style="background:${colorDe(S.yo.usuario)}">${esc(iniciales(S.yo.nombre))}</div>
          <div style="min-width:0"><div class="n">${esc(S.yo.nombre)}</div><div class="r">${NOMBRE_ROL[S.yo.rol] || "Introducción de datos"}</div></div>
          ${navegador() ? "" : `<button id="btnClave" title="Cambiar mi contraseña">${icono("llave")}</button>`}
          <button id="btnSalir" title="${navegador() ? "Cambiar de usuario" : "Cerrar sesión"}">${icono("salir")}</button>
        </div>
      </div>
    </aside>
    <main class="principal"><header class="barra" id="barra"></header><section class="contenido" id="contenido"></section></main>
    <button class="menu-movil" id="btnMenu" aria-label="Abrir menú">${icono("menu")}</button>
    <div class="velo-menu" id="veloMenu"></div>
  </div>`;
  const menu = (abrir) => { $(".lateral").classList.toggle("abierto", abrir); document.body.classList.toggle("menu-abierto", abrir); };
  $("#btnMenu").onclick = () => menu(!$(".lateral").classList.contains("abierto"));
  $("#veloMenu").onclick = () => menu(false);
  $(".lateral").addEventListener("click", (ev) => { if (ev.target.closest("a")) menu(false); });
  if ($("#btnClave")) $("#btnClave").onclick = () => modal({
    titulo: "Cambiar mi contraseña", aceptar: "Cambiar",
    html: `<form class="form" onsubmit="return false"><label>Contraseña actual<input class="inp" id="ca" type="password" autocomplete="current-password"></label>
      <label>Contraseña nueva (mín. 8)<input class="inp" id="cn" type="password" autocomplete="new-password"></label>
      <label>Repita la contraseña nueva<input class="inp" id="cn2" type="password" autocomplete="new-password"></label>
      <div class="sub">Si se la puso otra persona al darle de alta, cámbiela por una que solo conozca usted. Se cerrarán sus sesiones en otros equipos.</div><div class="error"></div></form>`,
    alAceptar: async (m) => {
      if ($("#cn", m).value !== $("#cn2", m).value) throw new Error("Las dos contraseñas nuevas no coinciden");
      await api("POST", "clave", { actual: $("#ca", m).value, nueva: $("#cn", m).value });
      toast("Contraseña cambiada");
    },
  });
  $("#btnSalir").onclick = async () => {
    await vaciarPendientes();
    if (navegador()) {
      const ok = await modal({ titulo: "Cambiar de usuario", aceptar: "Cambiar", html: `<p>Los casos <b>no se borran</b>: siguen guardados en este navegador y en la carpeta compartida.</p><p class="sub">Use esto solo si otra persona va a trabajar en este mismo ordenador.</p>` });
      if (!ok) return;
      await api("POST", "logout"); S.yo = null; location.hash = ""; return pintarPerfil();
    }
    await api("POST", "logout"); S.yo = null; location.hash = ""; pintarLogin();
  };
  if (navegador()) { L.alCambiarEstado(pintarEstadoCarpeta); pintarEstadoCarpeta(); }
  window.addEventListener("scroll", () => $("#barra")?.classList.toggle("sombra", scrollY > 4), { passive: true });
}

async function cargarCasos() {
  S.casos = await api("GET", "casos");
  S.casos.forEach((c) => { c.progreso = progresoCaso(S.modelo, c); c.dudas = dudasDelCaso(S.modelo, c); c.iaPend = iaPendientes(c).length; });
  const nd = S.casos.reduce((a, c) => a + c.dudas.length, 0) + S.casos.filter(tieneNota).length;
  const elD = $("#nDudas"); if (elD) { elD.textContent = nd || ""; elD.classList.toggle("oculto", !nd); }
  const n = $("#nCasos"); if (n) n.textContent = S.casos.length;
  return S.casos;
}

// ===========================================================================
//  PANEL
// ===========================================================================
function donut(datos, tam = 150, grosor = 22) {
  const total = datos.reduce((a, d) => a + d.v, 0) || 1;
  const r = (tam - grosor) / 2, c = 2 * Math.PI * r;
  let acc = 0;
  const arcos = datos.filter((d) => d.v).map((d) => {
    const l = (d.v / total) * c;
    const s = `<circle cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke="${d.c}" stroke-width="${grosor}" stroke-dasharray="${Math.max(l - 2, 0.1)} ${c}" stroke-dashoffset="${-acc}"><title>${esc(d.t)}: ${d.v}</title></circle>`;
    acc += l; return s;
  }).join("");
  return `<svg width="${tam}" height="${tam}" viewBox="0 0 ${tam} ${tam}" style="transform:rotate(-90deg)"><circle cx="${tam / 2}" cy="${tam / 2}" r="${r}" fill="none" stroke="var(--bg-2)" stroke-width="${grosor}"/>${arcos}</svg>`;
}

function barrasActividad(aud) {
  const dias = [];
  for (let i = 13; i >= 0; i--) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - i); dias.push({ d, n: 0 }); }
  for (const a of aud) {
    const f = new Date(a.fecha); f.setHours(0, 0, 0, 0);
    const x = dias.find((d) => d.d.getTime() === f.getTime()); if (x) x.n++;
  }
  const max = Math.max(1, ...dias.map((d) => d.n));
  const W = 420, H = 130, bw = W / dias.length;
  const barras = dias.map((d, i) => {
    const h = Math.max(3, (d.n / max) * (H - 26));
    return `<rect x="${i * bw + 5}" y="${H - 18 - h}" width="${bw - 10}" height="${h}" rx="5" fill="url(#gB)"><title>${d.d.toLocaleDateString("es-ES")}: ${d.n} cambios</title></rect>
      ${i % 2 === 0 ? `<text x="${i * bw + bw / 2}" y="${H - 3}" text-anchor="middle" font-size="10" fill="var(--ink-3)">${d.d.getDate()}/${d.d.getMonth() + 1}</text>` : ""}`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}"><defs><linearGradient id="gB" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#14b8a6"/><stop offset="1" stop-color="#0f766e" stop-opacity=".5"/></linearGradient></defs>${barras}</svg>`;
}

async function pPanel() {
  const hora = new Date().getHours();
  const saludo = hora < 14 ? "Buenos días" : hora < 21 ? "Buenas tardes" : "Buenas noches";
  barra("Panel", new Date().toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long", year: "numeric" }));
  const [casos, aud] = await Promise.all([cargarCasos(), api("GET", "auditoria?limite=1000")]);
  const tot = casos.length;
  const comp = casos.filter((c) => c.estado !== "borrador").length;
  const val = casos.filter((c) => c.estado === "validado").length;
  const media = tot ? Math.round(casos.reduce((a, c) => a + c.progreso.pct, 0) / tot) : 0;
  const mios = casos.filter((c) => c.modificado_por === S.yo.usuario && c.estado === "borrador");
  const porEnf = PRINCIPALES.map((g) => {
    const cs = casos.filter((c) => diagnosticosDe(c).includes(g));
    return { g, n: cs.length, pct: cs.length ? Math.round(cs.reduce((a, c) => a + c.progreso.pct, 0) / cs.length) : 0 };
  });
  const ultimos = [];
  const vistos = new Set();
  for (const a of aud) { const k = a.numero + a.usuario + a.fecha.slice(0, 13); if (!vistos.has(k)) { vistos.add(k); ultimos.push(a); } if (ultimos.length >= 7) break; }

  $("#contenido").innerHTML = `
    <div class="saludo">
      ${ecgSvg("ecg-fondo")}
      <h2>${saludo}, ${esc(S.yo.nombre.replace(/\(.*?\)/, "").split(" ")[0])}</h2>
      <p>${tot ? `Hay <b>${tot}</b> casos en el registro y la completitud media es del <b>${media}%</b>.` : "Todavía no hay casos. Empiece creando el primero."}
      ${mios.length ? ` Tiene <b>${mios.length}</b> caso${mios.length > 1 ? "s" : ""} en borrador.` : ""}</p>
      <div class="acciones">
        <a class="btn blanco" href="#/nuevo">${icono("mas")} Nuevo caso</a>
        <a class="btn" href="#/casos?estado=borrador">${icono("editar")} Continuar borradores</a>
        ${puedeRevisar() && S.casos.some((c) => c.iaPend) ? `<a class="btn" href="#/casos?ia=1">${icono("chispa")} Revisar lo de la IA (${S.casos.filter((c) => c.iaPend).length})</a>` : ""}
        ${esDM() ? `<a class="btn" href="#/exportar">${icono("exportar")} Exportar al registro</a>` : ""}
      </div>
    </div>
    <div class="grid g4" style="margin-bottom:18px">
      ${[["casos", tot, "Casos registrados"], ["check", comp, "Completos o validados"], ["escudo", val, "Validados"], ["rayo", media + "%", "Completitud media"]]
        .map(([i, v, e]) => `<div class="tarjeta kpi"><div class="ic">${icono(i)}</div><div><div class="v">${v}</div><div class="e">${e}</div></div></div>`).join("")}
    </div>
    <div class="bloque-tit" style="margin-top:6px">Por diagnóstico del estudio</div>
    <div class="grid g-enf" style="margin-bottom:18px">
      ${porEnf.map(({ g, n, pct }) => `<a class="enf-card" style="--c:${ENFERMEDADES[g].color}" href="#/casos?enf=${g}">
        <div class="ic">${icono(g)}</div><div class="num">${n}</div><div class="nom">${esc(ENFERMEDADES[g].nombre)}</div>
        <div class="barra-p"><i style="width:${pct}%"></i></div><div class="mini"><span>Completitud</span><b>${pct}%</b></div></a>`).join("")}
    </div>
    <div class="grid g-panel">
      <div class="tarjeta pad"><h3>Distribución</h3><div class="sub" style="margin-bottom:14px">Filas por diagnóstico (un paciente cuenta en cada una de sus patologías)</div>
        <div class="donut-wrap"><div style="position:relative;display:grid;place-items:center">${donut(porEnf.map((x) => ({ v: x.n, c: ENFERMEDADES[x.g].color, t: ENFERMEDADES[x.g].nombre })))}
          <div style="position:absolute;text-align:center"><div style="font-size:26px;font-weight:700">${tot}</div><div class="sub">casos</div></div></div>
          <div class="leyenda">${porEnf.map((x) => `<span><i style="background:${ENFERMEDADES[x.g].color}"></i>${esc(ENFERMEDADES[x.g].corto)}<b>${x.n}</b></span>`).join("")}</div></div>
      </div>
      <div class="tarjeta pad"><h3>Actividad</h3><div class="sub" style="margin-bottom:10px">Cambios registrados en los últimos 14 días</div>${barrasActividad(aud)}</div>
      <div class="tarjeta pad"><h3>Últimos movimientos</h3>
        <ul class="actividad">${ultimos.map((a) => `<li><span class="punto" style="background:${colorDe(a.usuario)}">${esc(iniciales(a.usuario))}</span>
          <div><div><b>${esc(a.usuario)}</b> ${a.campo === "(caso creado)" ? "creó el caso" : a.campo === "(caso eliminado)" ? "eliminó el caso" : "editó el caso"} <a href="#/caso/${a.numero}" class="num-caso">#${pad(a.numero)}</a>
          ${a.origen === "importacion" ? `<span class="origen">informe</span>` : ""}</div><div class="cuando">${relativo(a.fecha)}</div></div></li>`).join("") || `<li class="sub">Sin actividad todavía</li>`}</ul>
      </div>
    </div>`;
}

// ===========================================================================
//  LISTA DE CASOS
// ===========================================================================
async function pCasos(qs) {
  barra("Casos", "Registro WILLEM", `<a class="btn primario" href="#/nuevo">${icono("mas")} Nuevo caso</a>`);
  await cargarCasos();
  const F = { enf: qs.get("enf") || "", estado: qs.get("estado") || "", q: "", nota: qs.get("revisar") === "1", ia: qs.get("ia") === "1" };
  const cont = $("#contenido");
  const pintar = () => {
    const lista = S.casos.filter((c) => (!F.nota || tieneNota(c)) && (!F.ia || c.iaPend) && (!F.enf || diagnosticosDe(c).includes(F.enf)) && (!F.estado || c.estado === F.estado) && (!F.q || pad(c.numero).includes(F.q.replace(/\D/g, "")) && F.q.replace(/\D/g, "")));
    const cuenta = (g) => S.casos.filter((c) => diagnosticosDe(c).includes(g)).length;
    guardarCola(lista.map((c) => c.numero), [F.enf && ENFERMEDADES[F.enf]?.corto, F.estado && { borrador: "en borrador", completo: "completos", validado: "validados" }[F.estado],
      F.nota && "marcados para revisar", F.ia && "con datos de la IA por revisar"].filter(Boolean).join(" · "));
    cont.innerHTML = `
      <div class="filtros">
        <div class="buscador">${icono("buscar")}<input id="q" placeholder="Buscar por número de caso…" value="${esc(F.q)}" inputmode="numeric"></div>
        <span class="chip ${!F.enf ? "on" : ""}" data-enf="">Todas <span class="n">${S.casos.length}</span></span>
        ${PRINCIPALES.map((g) => `<span class="chip ${F.enf === g ? "on" : ""}" data-enf="${g}" style="--c:${ENFERMEDADES[g].color}">${icono(g)} ${esc(ENFERMEDADES[g].corto)} <span class="n">${cuenta(g)}</span></span>`).join("")}
      </div>
      <div class="filtros">
        ${[["", "Todos los estados"], ["borrador", "Borrador"], ["completo", "Completo"], ["validado", "Validado"]].map(([k, t]) => `<span class="chip ${F.estado === k ? "on" : ""}" data-estado="${k}">${t}</span>`).join("")}
        <span class="chip chip-estrella ${F.nota ? "on" : ""}" id="fNota" style="--c:#d97706">${icono("estrella")} Para revisar <span class="n">${S.casos.filter(tieneNota).length}</span></span>
        <span class="chip ${F.ia ? "on" : ""}" id="fIA" style="--c:var(--ia)">${icono("chispa")} Datos de la IA por revisar <span class="n">${S.casos.filter((c) => c.iaPend).length}</span></span>
      </div>
      <div class="tarjeta">
        ${lista.length ? `<table class="tabla"><thead><tr><th>Caso</th><th>Diagnósticos del estudio</th><th>Completitud</th><th>Estado</th><th>Registro</th><th>Última modificación</th></tr></thead><tbody>
        ${lista.map((c) => `<tr data-n="${c.numero}" style="--c:${ENFERMEDADES[c.principal]?.color}">
          <td><span class="num-caso"><small>#</small>${pad(c.numero)}</span> ${tieneNota(c) ? `<span class="estrella on" title="${esc(c.valores.nota_revision)}">${icono("estrella")}</span>` : ""}</td>
          <td><div class="diags-celda">${diagnosticosDe(c).map((g) => pillEnf(g, diagnosticosDe(c).length > 1)).join(" ")}</div></td>
          <td><div style="display:flex;align-items:center;gap:10px">${anillo(c.progreso.pct, 40, 4.5)}<span class="sub">${c.progreso.ok}/${c.progreso.tot}</span></div></td>
          <td>${estadoPill(c.estado)} ${c.dudas.length ? `<span class="pill sec" style="--c:#d97706" title="Dudas sin resolver">${icono("bandera")} ${c.dudas.length}</span>` : ""}${c.iaPend ? ` <span class="pill sec" style="--c:var(--ia)" title="Datos propuestos por la IA sin revisar">${icono("chispa")} ${c.iaPend}</span>` : ""}</td>
          <td>${pillEnvio(c)}</td>
          <td class="quien">${relativo(c.modificado)}<small>por ${esc(c.modificado_por)}</small></td></tr>`).join("")}
        </tbody></table>` : `<div class="vacio">${icono("casos")}<p>No hay casos con estos filtros.</p><a class="btn primario" href="#/nuevo">${icono("mas")} Crear un caso</a></div>`}
      </div>`;
    $$("[data-enf]", cont).forEach((x) => (x.onclick = () => { F.enf = x.dataset.enf; pintar(); }));
    $$("[data-estado]", cont).forEach((x) => (x.onclick = () => { F.estado = x.dataset.estado; pintar(); }));
    $("#fNota").onclick = () => { F.nota = !F.nota; pintar(); };
    $("#fIA").onclick = () => { F.ia = !F.ia; pintar(); };
    $$("tr[data-n]", cont).forEach((x) => (x.onclick = () => (location.hash = `#/caso/${x.dataset.n}`)));
    const q = $("#q");
    q.oninput = () => { F.q = q.value; const pos = q.selectionStart; pintar(); const nq = $("#q"); nq.focus(); nq.setSelectionRange(pos, pos); };
  };
  pintar();
}

// ===========================================================================
//  NUEVO CASO (asistente)
// ===========================================================================
/** Selector múltiple de diagnósticos (asistente y modal). sel = array en orden de selección. */
function selectorDiagnosticos(sel, otro) {
  return `<div class="elige-enf">${PRINCIPALES.map((g) => `<div class="enf-card ${sel.includes(g) ? "sel" : ""}" data-g="${g}" style="--c:${ENFERMEDADES[g].color}">
      <span class="marca-sel">${icono("check")}</span><div class="ic">${icono(g)}</div><h4>${esc(ENFERMEDADES[g].nombre)}</h4><p>${esc(ENFERMEDADES[g].desc)}</p></div>`).join("")}</div>
    ${sel.includes("OTRO") ? `<label class="otro-diag"><b>Otros: ¿qué diagnóstico?</b><input class="inp" id="otroTxt" value="${esc(otro || "")}" placeholder="Describa el diagnóstico (y su código CIE-11 si lo conoce)"></label>` : ""}`;
}

async function pNuevo(qs) {
  barra("Nuevo caso", "Casos ›");
  const proponer = !navegador() || esDM();
  const W = { paso: 1, numero: +qs.get("n") || (proponer ? (await api("GET", "siguiente")).numero : ""), sel: [], otro: "" };
  const cont = $("#contenido");
  const pintar = () => {
    const pasos = ["Número de caso", "Diagnósticos del estudio"];
    let cuerpo = "";
    if (W.paso === 1) {
      cuerpo = `<div class="tarjeta pad" style="max-width:760px">
        <h3>¿Qué número tiene este caso?</h3>
        <div class="sub" style="margin-bottom:18px">Es el número seudonimizado que asigna el data manager en el <b>libro llave</b>. Nunca escriba aquí el CIP, CARM, NHC ni el nombre del paciente.</div>
        <div class="campo-num"><input id="num" value="${W.numero ? pad(W.numero) : ""}" placeholder="0000" inputmode="numeric" maxlength="6"><div class="sub">${W.numero ? "Propuesto: el siguiente libre." : "Escriba el número que le ha dado el data manager."}${esDM() ? `<br><a href="#/llave">${icono("llave")} Asignarlo desde el libro llave</a>` : ""}</div></div>
        <div class="nav-sec"><span></span><button class="btn primario grande" id="sig">Continuar ${icono("flechaD")}</button></div></div>`;
    } else {
      cuerpo = `<div class="aviso-local">${icono("info")}<div><b>Marque todas las patologías por las que el paciente entra en el estudio.</b>
          Solo se preguntan aquí. En el Excel final el paciente saldrá <b>una vez por cada patología</b> (mismo número de caso).</div></div>
        ${selectorDiagnosticos(W.sel, W.otro)}
        <div class="nav-sec"><button class="btn grande" id="ant">${icono("flechaI")} Atrás</button>
          <span style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"><span class="num-caso" style="font-size:20px">#${pad(W.numero)}</span>${W.sel.map((g) => pillEnf(g, true)).join(" ")}
          <button class="btn primario grande" id="crear" ${W.sel.length ? "" : "disabled"}>${icono("check")} Crear caso y empezar</button></span></div>`;
    }
    cont.innerHTML = `<div class="pasos">${pasos.map((p, i) => `<div class="paso ${W.paso === i + 1 ? "on" : W.paso > i + 1 ? "hecho" : ""}"><b>${W.paso > i + 1 ? "✓" : i + 1}</b>${p}</div>`).join("")}</div>${cuerpo}`;
    $("#ant") && ($("#ant").onclick = () => { W.paso--; pintar(); });
    if (W.paso === 1) {
      const inp = $("#num"); inp.focus(); inp.select();
      const ir = () => { const n = parseInt(inp.value.replace(/\D/g, ""), 10); if (!n) return toast("Escriba un número de caso válido", "mal"); if (S.casos.some((c) => c.numero === n)) return toast(`El caso #${pad(n)} ya existe`, "mal"); W.numero = n; W.paso = 2; pintar(); };
      $("#sig").onclick = ir; inp.onkeydown = (e) => e.key === "Enter" && ir();
    } else {
      $$("[data-g]", cont).forEach((x) => (x.onclick = () => { const g = x.dataset.g; W.sel = W.sel.includes(g) ? W.sel.filter((y) => y !== g) : [...W.sel, g]; pintar(); }));
      $("#otroTxt")?.addEventListener("input", (ev) => (W.otro = ev.target.value));
      $("#crear").onclick = async () => {
        if (W.sel.includes("OTRO") && !W.otro.trim()) { toast("Describa el diagnóstico de 'Otros'", "mal"); return $("#otroTxt")?.focus(); }
        try {
          await api("POST", "casos", { numero: W.numero, principal: W.sel[0], secundarias: W.sel.slice(1) });
          const def = valoresPorDefecto(S.modelo, {});
          if (W.sel.includes("OTRO")) def.other_disease = W.otro.trim();
          if (Object.keys(def).length) await api("PUT", "casos/" + W.numero, { valores: def });
          toast(`Caso #${pad(W.numero)} creado`); location.hash = `#/caso/${W.numero}`;
        } catch (e) { toast(e.message, "mal"); }
      };
    }
  };
  await cargarCasos();
  pintar();
}

// ===========================================================================
//  EDITOR DE CASO
// ===========================================================================
const soloLectura = () => E.caso?.estado === "validado" && !puedeRevisar();

async function pCaso(num, tabId) {
  if (!S.casos.length) await cargarCasos();
  E.caso = await api("GET", "casos/" + num);
  E.pend = {}; E.origen = null;
  const tabs = pestanasDelCaso(S.modelo, E.caso);
  E.tab = tabs.find((t) => t.id === tabId) ? tabId : tabs[0].id; // siempre empieza por la primera pestaña ("Diagnósticos")
  E.cola = colaDe(num);
  barra(`Caso #${pad(num)}`, `<a href="#/casos">Casos</a> › ${esc(diagnosticosDe(E.caso).map((g) => ENFERMEDADES[g]?.corto || g).join(" · "))}`,
    `<button class="btn ${vintageActivo() ? "on-vintage" : ""}" id="bVista" title="Vista compacta de escritorio: más variables por pantalla y manejo con teclado">${icono("vintage")} ${vintageActivo() ? "Modo normal" : "Modo Vintage"}</button>${E.caso.informes?.length ? `<button class="btn" id="bInforme">${icono("libro")} Informe${E.caso.informes.length > 1 ? `s (${E.caso.informes.length})` : ""}</button>` : ""}<button class="btn" id="bImp">${icono("importar")} Importar informe</button><button class="btn fantasma" id="bHist">${icono("historial")} Historial</button>`);
  $("#bInforme")?.addEventListener("click", () => abrirInforme());
  $("#bVista").onclick = () => alternarVintage(num);
  $("#bImp").onclick = abrirImportador;
  $("#bHist").onclick = abrirHistorial;
  pintarCaso(true);
}

function pintarCaso(animar = false) {
  const c = E.caso, e = ENFERMEDADES[c.principal];
  const tabs = pestanasDelCaso(S.modelo, c);
  if (!tabs.find((t) => t.id === E.tab)) E.tab = tabs[0].id;
  const tab = tabs.find((t) => t.id === E.tab);
  const ti = tabs.indexOf(tab);
  const prog = progresoItems(tabs.flatMap((t) => t.bloques.flatMap((b) => b.items)), c.valores);
  const pt = progresoPestana(tab, c.valores);
  const tColor = e.color;
  const diags = diagnosticosDe(c);
  let nSec = 0;
  const cont = $("#contenido");
  const scroll = scrollY;
  const foco = document.activeElement?.dataset?.foco;
  const V = vintageActivo();
  E.vintage = V;
  cont.classList.toggle("vintage", V);

  cont.style.setProperty("--c", e.color);
  cont.innerHTML = `
    ${tiraPacientes(c)}
    <div class="cabecera-caso" style="--c:${e.color}">
      <div class="ic-grande">${icono(c.principal)}</div>
      <div><div class="t1">Diagnóstico${diags.length > 1 ? "s" : ""} del estudio · caso <span class="num-caso">#${pad(c.numero)}</span></div>
        <div class="t2">${esc(diags.length === 1 ? ENFERMEDADES[diags[0]].nombre : diags.map((g) => ENFERMEDADES[g].corto).join(" · "))}</div>
        <div class="secs">${diags.length > 1 ? diags.map((g) => `<span class="pill sec">${icono(g)} ${esc(ENFERMEDADES[g].nombre)}</span>`).join("") : ""}
          ${diags.includes("OTRO") && c.valores.other_disease ? `<span class="pill sec">${icono("OTRO")} ${esc(c.valores.other_disease)}</span>` : ""}
          ${(() => { const d = dudasDelCaso(S.modelo, c); return d.length ? `<a class="pill sec duda-pill" href="#/caso/${c.numero}/${encodeURIComponent(d[0].pestana)}" title="Ir a la primera duda">${icono("bandera")} ${d.length} duda${d.length > 1 ? "s" : ""}</a>` : ""; })()}
          ${(() => { const n = iaPendientes(c).length; return n ? `<button class="pill sec ia-pill" id="bIAPend" title="Ir al primer dato de la IA sin revisar">${icono("chispa")} ${n} dato${n > 1 ? "s" : ""} de la IA por revisar</button>` : ""; })()}
          ${soloLectura() ? "" : `<button class="btn pequeno" id="bDiag">${icono("editar")} Diagnósticos</button>`}</div></div>
      <div class="der">
        <span class="guardado" id="guardado">${icono("check")} Guardado</span>
        ${botonNota(c)}
        ${botonEnvio(c)}
        <select id="selEstado" ${soloLectura() ? "disabled" : ""}>
          <option value="borrador" ${c.estado === "borrador" ? "selected" : ""}>Borrador</option>
          <option value="completo" ${c.estado === "completo" ? "selected" : ""}>Completo</option>
          ${puedeRevisar() || c.estado === "validado" ? `<option value="validado" ${c.estado === "validado" ? "selected" : ""}>Validado</option>` : ""}
        </select>
        ${anillo(prog.pct, 64, 6, "#fff")}
      </div>
    </div>
    ${soloLectura() ? `<div class="banda-lectura">${icono("candado")} Caso validado: solo lectura.</div>` : ""}
    ${c.ia?._diagnosticos && !c.ia._diagnosticos.revisado ? `<div class="banda-ia">${icono("chispa")}<div><b>La IA propone ${c.ia._diagnosticos.valor_texto.includes(",") ? "estos diagnósticos" : "este diagnóstico"}: ${esc(diags.map((g) => ENFERMEDADES[g]?.nombre || g).join(" · "))}</b>
      ${c.ia._diagnosticos.aviso ? `<div class="aviso-ia">${icono("aviso")} ${esc(c.ia._diagnosticos.aviso)}</div>` : ""}
      <div class="sub">Compruébelo antes de seguir: de los diagnósticos depende qué preguntas se muestran y las filas del Excel.</div></div>
      <div class="acc"><button class="btn pequeno" data-ia="_diagnosticos">Ver de dónde lo saca</button>${soloLectura() ? "" : `<button class="btn pequeno" id="bDiag2">${icono("editar")} Cambiar</button><button class="btn pequeno primario" id="bDiagOk">${icono("check")} Son correctos</button>`}</div></div>` : ""}
    <div class="editor ${soloLectura() ? "solo-lectura" : ""}">
      <nav class="tarjeta indice">
        ${tabs.map((t, i) => {
          const p = progresoPestana(t, c.valores);
          const col = t.grupo ? ENFERMEDADES[t.grupo].color : "var(--brand)";
          const sep = i > 0 && tabs[i - 1].grupo && !t.grupo ? `<div class="sep"></div><div class="titulo-ind">Datos comunes</div>` : i === 1 && t.grupo ? `<div class="titulo-ind">Enfermedades</div>` : "";
          if (!t.grupo) nSec++;
          return `${sep}<a href="#/caso/${c.numero}/${encodeURIComponent(t.id)}" class="${t.id === E.tab ? "activo" : ""} ${p.pct === 100 ? "ok" : ""}" style="--c:${col}" data-tab="${esc(t.id)}">
            ${t.grupo ? `<span class="marca-enf">${icono(t.grupo)}</span>` : `<span class="n-sec">${p.pct === 100 ? "✓" : nSec}</span>`}
            <span class="t">${esc(t.titulo)}<span class="p">${t.principal ? "Principal · " : ""}${p.ok}/${p.tot} · ${p.pct}%</span></span>
            <span class="mini-barra"><i style="width:${p.pct}%"></i></span></a>`;
        }).join("")}
      </nav>
      <div style="--c:${tColor}">
        <div class="seccion-cab">
          <div>${tab.grupo ? pillEnf(tab.grupo) : ""}<h2 style="margin-top:${tab.grupo ? 8 : 0}px">${esc(tab.titulo)}</h2>
            <div class="sub">${pt.ok} de ${pt.tot} respondidos${tab.grupo ? " · campos específicos de esta enfermedad" : ""}</div></div>
          <div class="der">${!soloLectura() && iaDePestana(tab, c).length ? `<button class="btn ia" id="bConfIA" title="Da por revisados los datos propuestos por la IA que se ven en esta pestaña">${icono("chispa")} Confirmar lo de la IA (${iaDePestana(tab, c).length})</button>` : ""}${soloLectura() ? "" : `<button class="btn fantasma" id="bRellenarNC" title="Pone Desconocido en todas las preguntas Sí/No y listas sin contestar de esta pestaña">${icono("interrogacion")} Resto: Desconocido</button>
            <button class="btn" id="bRellenar" title="Pone No en todas las preguntas Sí/No y listas con opción «No» o «Ninguno» que estén sin contestar en esta pestaña">${icono("varita")} Marcar el resto como No</button>`}</div>
        </div>
        ${V ? `<div class="v-teclas" title="Con el foco en una pregunta">${icono("vintage")} <b>Teclado:</b> <kbd>S</kbd> Sí · <kbd>N</kbd> No · <kbd>?</kbd> Desconocido · <kbd>D</kbd> Duda · <kbd>Tab</kbd> o <kbd>↓</kbd> siguiente · <kbd>↑</kbd> anterior</div>` : ""}
        <div id="seccion" class="${V ? "v-paneles" : ""}">${V ? seccionVintage(tab, c) : tab.bloques.filter((b) => b.items.some((it) => visible(it, c.valores))).map((b) => `${b.grupo ? `<div class="bloque-tit bloque-enf" style="--c:${ENFERMEDADES[b.grupo].color}">${icono(b.grupo)} ${esc(b.subtitulo)}</div>`
          : b.subtitulo ? `<div class="bloque-tit">${esc(b.subtitulo)}</div>` : ""}
          <div class="campos">${b.items.filter((it) => visible(it, c.valores)).map((it) => campoHTML(it, c.valores, animar)).join("")}</div>`).join("")}</div>
        ${soloLectura() ? "" : `<div class="rellenar-abajo"><button class="btn grande" id="bRellenar2" title="Pone No en todas las preguntas Sí/No (y desplegables con opción No) que no haya contestado en esta pestaña">${icono("varita")} Todo lo que no he marcado, a «No»</button></div>`}
        <div class="nav-sec">
          ${ti > 0 ? `<a class="btn grande" href="#/caso/${c.numero}/${encodeURIComponent(tabs[ti - 1].id)}">${icono("flechaI")} ${esc(tabs[ti - 1].titulo)}</a>` : "<span></span>"}
          ${ti < tabs.length - 1 ? `<a class="btn color grande" href="#/caso/${c.numero}/${encodeURIComponent(tabs[ti + 1].id)}">${esc(tabs[ti + 1].titulo)} ${icono("flechaD")}</a>`
            : `<button class="btn color grande" id="bFin">${icono("check")} Terminar</button>`}
        </div>
      </div>
    </div>
    ${tiraPacientes(c, true)}`;
  $$("[data-ir]", cont).forEach((b) => (b.onclick = () => irAPaciente(+b.dataset.ir, b.dataset.tab === "1")));
  $$("[data-validar-sig]", cont).forEach((b) => (b.onclick = async () => {
    if (!(await cambiarEstado("validado", "Validado"))) return;
    if (E.cola.sig) irAPaciente(E.cola.sig, false);
    else { toast("Era el último paciente de la lista"); location.hash = "#/casos"; }
  }));

  // Navegación entre pestañas sin recargar el caso
  $$(".indice a, .nav-sec a", cont).forEach((a) => a.addEventListener("click", (ev) => {
    ev.preventDefault();
    const id = decodeURIComponent(a.getAttribute("href").split("/").pop());
    E.tab = id;
    history.replaceState(null, "", `#/caso/${c.numero}/${encodeURIComponent(id)}`);
    pintarCaso(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));
  if (!animar) window.scrollTo(0, scroll);
  if (foco) $(`[data-foco="${CSS.escape(foco)}"]`)?.focus();
  if (V && E.avanzar) {  // tras contestar con el teclado: a la fecha pendiente de esa pregunta o a la pregunta siguiente
    const filas = $$("#seccion .vf");
    const i = filas.findIndex((f) => f.dataset.k === E.avanzar.k);
    const fechaVacia = i >= 0 && [...filas[i].querySelectorAll("input.fecha")].find((x) => !x.value);
    const destino = fechaVacia || enfocable(filas[i + E.avanzar.paso] || filas[i]);
    destino?.focus();
    E.avanzar = null;
  }

  $("#bDiag")?.addEventListener("click", editarDiagnosticos);
  $("#bDiag2")?.addEventListener("click", editarDiagnosticos);
  $("#bDiagOk")?.addEventListener("click", () => revisarIA(["_diagnosticos"], "Diagnósticos confirmados"));
  $("#bIAPend")?.addEventListener("click", irAPendienteIA);
  $("[data-ia=_diagnosticos]", cont)?.addEventListener("click", () => abrirDatoIA("_diagnosticos"));
  $("#bConfIA")?.addEventListener("click", async () => {
    const ks = iaDePestana(tab, c);
    const conAviso = ks.filter((k) => c.ia[k].aviso).length;
    const ok = await modal({ titulo: "Confirmar los datos de la IA", aceptar: `Confirmar ${ks.length}`,
      html: `<p>Se darán por revisados los <b>${ks.length}</b> datos propuestos por la IA en <b>${esc(tab.titulo)}</b>.</p>
        ${conAviso ? `<p class="aviso-ia">${icono("aviso")} ${conAviso} de ellos tienen un aviso (fondo ámbar). Mírelos antes de confirmar.</p>` : ""}
        <p class="sub">Confírmelo solo si los ha comprobado con el informe. Quedará anotado en el historial.</p>` });
    if (ok) revisarIA(ks, `${ks.length} datos de la IA confirmados`);
  });
  $("#bEnviar")?.addEventListener("click", () => enviarAlRegistro(E.caso));
  $("#selEstado").onchange = async (ev) => { await cambiarEstado(ev.target.value, ev.target.selectedOptions[0].text); };
  $("#bFin")?.addEventListener("click", async () => {
    await vaciarPendientes();
    if (prog.pct < 100) toast(`Faltan ${prog.tot - prog.ok} campos por responder`, "info");
    else if (c.estado === "borrador") { E.caso = conInformes(await api("PUT", "casos/" + c.numero, { estado: "completo" })); toast("Caso marcado como completo"); }
    location.hash = "#/casos";
  });
  $("#bRellenarNC")?.addEventListener("click", async () => {
    const vv = c.valores, cambios = {};
    for (const it of tab.bloques.flatMap((b) => b.items)) {
      if (!admiteMarcas(it) || !visible(it, vv) || marcaDe(it, vv)) continue;
      if (it.opciones ? it.opciones.every((o) => vv[o.codigo] == null) : vv[it.codigo] == null) cambios[it.codigo] = NC;
    }
    const n = Object.keys(cambios).length;
    if (!n) return toast("No hay preguntas sin contestar en esta pestaña", "info");
    const ok = await modal({ titulo: "Marcar el resto como Desconocido", aceptar: `Poner Desconocido en ${n}`, html: `<p>Se marcarán como <b>Desconocido</b> (lo he buscado y no consta) las preguntas sin contestar de <b>${esc(tab.titulo)}</b>.</p><p class="sub">En el Excel final irán vacías. Quedará anotado en el historial.</p>` });
    if (ok) { aplicar(cambios, "relleno_no"); toast(`${n} respuestas marcadas como Desconocido`); }
  });
  $("#bRellenar2")?.addEventListener("click", () => $("#bRellenar").click());
  $("#bNota")?.addEventListener("click", editarNota);
  $("#bRellenar")?.addEventListener("click", async () => {
    const items = tab.bloques.flatMap((b) => b.items);
    const cambios = rellenarNo(items, c.valores);
    const n = new Set(Object.keys(cambios).map((k) => S.modelo.porCodigo[k]?.padre?.codigo || k)).size;
    if (!n) return toast("No hay preguntas Sí/No pendientes en esta pestaña", "info");
    const ok = await modal({ titulo: "Marcar el resto como No", aceptar: `Poner No en ${n}`, html: `<p>Se pondrá <b>No</b> en las preguntas de <b>${esc(tab.titulo)}</b> que estén sin contestar: las Sí/No y las listas que tengan la opción «No» o «Ninguno» (tabaquismo, diabetes, trastornos de la conducción…).</p><p class="sub">Lo ya marcado (Sí, Desconocido, Duda), los números y las fechas no se tocan. Quedará anotado en el historial.</p>` });
    if (ok) { aplicar(cambios, "relleno_no"); toast(`${n} respuestas puestas a No`); }
  });
  const sec = $("#seccion");
  sec.addEventListener("click", alClicar);
  sec.addEventListener("change", alCambiar);
  if (V) sec.addEventListener("keydown", teclaVintage);
  sec.addEventListener("input", (ev) => { if (ev.target.classList?.contains("fecha")) mascaraFecha(ev.target, ev); });
  actualizarGuardado();
}

// ---------------------------------------------------------------------------
//  PACIENTE ANTERIOR / SIGUIENTE
//  Se recorre la lista de «Casos» tal como se vio por última vez (con sus filtros): así, quien revisa
//  filtra «con datos de la IA por revisar» y va pasando de un paciente a otro sin volver a la lista.
// ---------------------------------------------------------------------------
function guardarCola(numeros, titulo) {
  S.cola = { numeros, titulo };
  try { sessionStorage.setItem("willem_cola", JSON.stringify(S.cola)); } catch { /* sin almacenamiento: solo en memoria */ }
}
function colaDe(num) {
  if (!S.cola) { try { S.cola = JSON.parse(sessionStorage.getItem("willem_cola") || "null"); } catch { S.cola = null; } }
  const existen = new Set(S.casos.map((c) => c.numero));
  let numeros = (S.cola?.numeros || []).filter((n) => existen.has(n)), titulo = S.cola?.titulo || "";
  if (!numeros.includes(num)) { numeros = S.casos.map((c) => c.numero); titulo = ""; } // el caso no está en la lista filtrada: se recorren todos
  const i = numeros.indexOf(num);
  return { i, total: numeros.length, ant: i > 0 ? numeros[i - 1] : null, sig: i >= 0 && i < numeros.length - 1 ? numeros[i + 1] : null, titulo };
}
function tiraPacientes(c, abajo = false) {
  const q = E.cola;
  if (!q || q.i < 0 || q.total < 2) return "";
  const validar = puedeRevisar() && c.estado !== "validado";
  return `<div class="tira-pac ${abajo ? "abajo" : ""}">
    <button class="btn" data-ir="${q.ant ?? ""}" data-tab="1" ${q.ant ? "" : "disabled"} title="${q.ant ? "Caso #" + pad(q.ant) : "Es el primero de la lista"}">${icono("flechaI")} Paciente anterior</button>
    <span class="pos"><b>${q.i + 1}</b> de <b>${q.total}</b>${q.titulo ? `<small>${esc(q.titulo)}</small>` : `<small>todos los casos</small>`}</span>
    ${validar ? `<button class="btn primario" data-validar-sig title="Da el caso por validado y abre el siguiente de la lista">${icono("check")} Validar y siguiente</button>` : ""}
    <button class="btn" data-ir="${q.sig ?? ""}" data-tab="1" ${q.sig ? "" : "disabled"} title="${q.sig ? "Caso #" + pad(q.sig) : "Es el último de la lista"}">Siguiente paciente ${icono("flechaD")}</button>
  </div>`;
}
/** Abre otro paciente guardando antes lo pendiente. Con mismaPestana, se queda en la pestaña en la que se estaba. */
async function irAPaciente(num, mismaPestana) {
  if (!num) return;
  await vaciarPendientes();
  location.hash = `#/caso/${num}` + (mismaPestana && E.tab ? "/" + encodeURIComponent(E.tab) : "");
}
/** Cambia el estado del caso abierto con todas las comprobaciones. Devuelve true si se cambió. */
async function cambiarEstado(valor, texto) {
  const c = E.caso;
  await vaciarPendientes();
  if (valor === "validado" && tieneNota(c) && !(await modal({ titulo: "Caso marcado para revisión", aceptar: "Validar igualmente",
    html: `<p>Este paciente tiene una nota de revisión (★):</p><blockquote class="cita-nota">${esc(c.valores.nota_revision)}</blockquote><p class="sub">Si ya está revisado, puede borrar la nota desde la estrella.</p>` }))) { pintarCaso(); return false; }
  if (valor === "validado" && dudasDelCaso(S.modelo, c).length) { toast("No se puede validar: hay dudas sin resolver en este caso", "mal"); pintarCaso(); return false; }
  if (valor === "validado" && iaPendientes(c).length) { toast(`No se puede validar: quedan ${iaPendientes(c).length} datos de la IA sin revisar`, "mal"); pintarCaso(); return false; }
  try { E.caso = conInformes(await api("PUT", "casos/" + c.numero, { estado: valor })); toast("Estado: " + texto); pintarCaso(); return true; }
  catch (er) { toast(er.message, "mal"); pintarCaso(); return false; }
}

// ---------------------------------------------------------------------------
//  MODO VINTAGE: vista compacta de escritorio (como las bases de datos clásicas)
//  Mismos datos, mismas reglas y mismo guardado; solo cambia cómo se pinta.
// ---------------------------------------------------------------------------
const VINTAGE_ANCHO_MIN = 1200;
const vintageActivo = () => localStorage.getItem("willem_vista") === "vintage" && innerWidth >= VINTAGE_ANCHO_MIN;

async function alternarVintage(num) {
  await vaciarPendientes();
  if (localStorage.getItem("willem_vista") === "vintage") localStorage.setItem("willem_vista", "normal");
  else {
    if (innerWidth < VINTAGE_ANCHO_MIN) {
      return modal({ titulo: "El Modo Vintage necesita una pantalla de escritorio", cancelar: "", aceptar: "Entendido",
        html: `<p>Muestra muchas variables a la vez, en letra pequeña y varias columnas, así que solo funciona en pantallas de al menos <b>${VINTAGE_ANCHO_MIN} píxeles de ancho</b> (un portátil o un monitor).</p>
          <p class="sub">En el móvil, en una tableta o con la ventana estrecha se usa el modo normal. Si está en un ordenador, agrande la ventana y vuelva a intentarlo.</p>` });
    }
    localStorage.setItem("willem_vista", "vintage");
    if (!localStorage.getItem("willem_vintage_visto")) {
      localStorage.setItem("willem_vintage_visto", "1");
      await modal({ titulo: "Modo Vintage", cancelar: "", aceptar: "Empezar",
        html: `<p>Vista compacta, al estilo de las bases de datos de siempre: <b>muchas más variables por pantalla</b>, sin apenas desplazarse.</p>
          <ul class="lista-vintage">
            <li>Cada bloque es un panel; las pestañas van arriba.</li>
            <li>Botones pequeños <b>NO · SÍ · ¿? · ${icono("bandera")}</b> (¿? = Desconocido, bandera = Duda). Pulsar otra vez el botón marcado lo deja sin contestar.</li>
            <li><b>Con el teclado:</b> <kbd>S</kbd> Sí, <kbd>N</kbd> No, <kbd>?</kbd> Desconocido, <kbd>D</kbd> Duda; pasa sola a la siguiente pregunta. <kbd>Tab</kbd>, <kbd>↓</kbd> y <kbd>↑</kbd> para moverse.</li>
            <li>Un punto ámbar marca lo que falta por contestar. Deje el ratón sobre una pregunta para ver su ayuda y su código.</li>
          </ul>
          <p class="sub">Los datos, el guardado automático y el Excel final son exactamente los mismos. Solo para pantalla de escritorio; puede volver al modo normal con el mismo botón.</p>` });
    }
  }
  pCaso(num, E.tab);
}
addEventListener("resize", () => { if (E.caso && $("#seccion") && E.vintage !== vintageActivo()) pintarCaso(); });

const enfocable = (fila) => fila && (fila.querySelector('[data-foco][tabindex="0"]') || fila.querySelector("input[data-foco], select[data-foco]") || fila.querySelector("[data-foco]"));

function seccionVintage(tab, c) {
  const v = c.valores;
  return tab.bloques.filter((b) => b.items.some((it) => visible(it, v))).map((b) => {
    const p = progresoItems(b.items, v);
    return `<section class="v-panel ${p.pct === 100 ? "completo" : ""}" style="--c:${b.grupo ? ENFERMEDADES[b.grupo].color : "var(--brand)"}">
      <h4>${b.grupo ? icono(b.grupo) : ""}<span>${esc(b.subtitulo || tab.titulo)}</span><i>${p.tot ? `${p.ok}/${p.tot}` : ""}</i></h4>
      ${b.items.filter((it) => visible(it, v)).map((it) => campoVintage(it, v)).join("")}</section>`;
  }).join("");
}

function campoVintage(it, v) {
  const k = esc(it.codigo);
  const mk = admiteMarcas(it) ? marcaDe(it, v) : null;
  const resp = (() => {
    if (mk) return mk === NC;
    switch (it.tipoCampo) {
      case "single": return it.opciones.some((o) => v[o.codigo] === 1);
      case "multi": return it.opciones.some((o) => v[o.codigo] != null);
      case "sinofecha": return v[it.codigo] === 0 || (v[it.codigo] === 1 && !!v[it.codigo + "_date"]);
      default: return v[it.codigo] != null && v[it.codigo] !== "";
    }
  })();
  const cuenta = !["fijo", "caso", "auto", "texto"].includes(it.tipoCampo);
  const mIA = E.caso?.ia?.[it.codigo];
  const conValor = mIA && (mIA.codigos || []).some((x) => v[x] != null && v[x] !== "");
  const pendIA = conValor && !mIA.revisado;
  const chipIA = conValor ? `<button class="ia-chip ${pendIA ? "pend" : ""} ${pendIA && mIA.aviso ? "aviso" : ""}" data-ia="${k}" tabindex="-1" title="${pendIA ? "Propuesto por la IA: pulse para ver de dónde lo saca" : "Dato de la IA ya revisado"}">IA${pendIA ? "" : " ✓"}</button>` : "";
  const ayuda = it.ayuda && !/^DUPLICADO|Solapa/.test(it.ayuda) ? it.ayuda : "";
  const tip = esc([it.etiqueta, ayuda, it.min != null && it.max != null ? `Rango esperado: ${it.min}–${it.max}${it.unidad ? " " + it.unidad : ""}` : "", "Código: " + it.codigo].filter(Boolean).join("\n"));
  const fechaInp = (kk, val, tit = "") => `<input type="text" class="inp fecha" inputmode="numeric" autocomplete="off" maxlength="10" placeholder="dd/mm/aaaa" title="${esc(tit)}"
      data-in="${esc(kk)}" data-t="fecha" data-foco="${esc(kk)}" value="${esc(isoAFecha(val))}">`;
  const marcas = () => `<button class="vm nc ${mk === NC ? "on" : ""}" data-marca="${NC}" data-mk="${k}" tabindex="-1" title="Desconocido: lo he buscado y no consta (tecla ?)">¿?</button><button class="vm duda ${mk === DUDA ? "on" : ""}" data-marca="${DUDA}" data-mk="${k}" tabindex="-1" title="Duda: que lo revise un data manager (tecla D)">${icono("bandera")}</button>`;
  let ctrl = "", extra = "", ancho = false;
  switch (it.tipoCampo) {
    case "fijo": ctrl = `<span class="v-fijo">${esc(it.fijo || v[it.codigo] || "")}</span>`; break;
    case "caso": ctrl = `<span class="v-fijo">#${pad(E.caso.numero)}</span>`; break;
    case "sino":
    case "sinofecha": {
      const x = v[it.codigo];
      ctrl = `<div class="vseg"><button class="no ${x === 0 ? "on" : ""}" data-sino="${k}" data-val="0" data-foco="${k}:0" tabindex="${x === 1 ? -1 : 0}">NO</button><button class="si ${x === 1 ? "on" : ""}" data-sino="${k}" data-val="1" data-foco="${k}:1" tabindex="${x === 1 ? 0 : -1}">SÍ</button>${marcas()}</div>`;
      if (it.tipoCampo === "sinofecha" && x === 1) ctrl += fechaInp(it.codigo + "_date", v[it.codigo + "_date"], "Fecha");
      break;
    }
    case "single": {
      const sel = it.opciones.find((o) => v[o.codigo] === 1);
      const corta = it.opciones.length <= 3 && it.opciones.reduce((n, o) => n + o.etiqueta.length, 0) <= 26;
      if (corta) ctrl = `<div class="vseg">${it.opciones.map((o, i) => `<button class="si ${v[o.codigo] === 1 ? "on" : ""}" data-g="${k}" data-o="${esc(o.codigo)}" data-foco="${esc(o.codigo)}" tabindex="${(sel ? sel === o : i === 0) ? 0 : -1}" title="${esc(o.codigo)}">${esc(o.etiqueta)}</button>`).join("")}${marcas()}</div>`;
      else ctrl = `<select class="vsel ${sel ? "on" : ""}" data-sel="${k}" data-foco="${k}:sel"><option value="">—</option>${it.opciones.map((o) => `<option value="${esc(o.codigo)}" ${sel === o ? "selected" : ""}>${esc(o.etiqueta)}</option>`).join("")}</select><div class="vseg">${marcas()}</div>`;
      if (it.conFecha && !mk) extra += `<div class="vx"><span>Fecha</span>${fechaInp(it.codigo, v[it.codigo])}</div>`;
      for (const o of it.opciones) if (o.conFecha && v[o.codigo] === 1) extra += `<div class="vx"><span>Fecha · ${esc(o.etiqueta)}</span>${fechaInp(o.codigo + "_date", v[o.codigo + "_date"])}</div>`;
      break;
    }
    case "multi": {
      ancho = it.opciones.length > 2 || it.opciones.reduce((n, o) => n + o.etiqueta.length, 0) > 22;
      ctrl = `<div class="vops">${it.opciones.map((o, i) => { const x = v[o.codigo]; return `<button class="vop ${x === 1 ? "on" : ""} ${x === 0 ? "cero" : ""}" data-g="${k}" data-o="${esc(o.codigo)}" data-foco="${esc(o.codigo)}" tabindex="${i === 0 ? 0 : -1}" title="${esc(o.codigo)}">${esc(o.etiqueta)}</button>`; }).join("")}<div class="vseg">${marcas()}</div></div>`;
      if (it.conFecha && !mk) extra += `<div class="vx"><span>Fecha</span>${fechaInp(it.codigo, v[it.codigo])}</div>`;
      for (const o of it.opciones) if (o.conFecha && v[o.codigo] === 1) extra += `<div class="vx"><span>Fecha · ${esc(o.etiqueta)}</span>${fechaInp(o.codigo + "_date", v[o.codigo + "_date"])}</div>`;
      break;
    }
    case "numero":
    case "entero": {
      const x = v[it.codigo];
      const fuera = x != null && ((it.min != null && x < it.min) || (it.max != null && x > it.max));
      ctrl = `<input class="inp num ${fuera ? "fuera" : ""}" data-in="${k}" data-t="${it.tipoCampo}" data-foco="${k}" inputmode="decimal" value="${x == null ? "" : String(x).replace(".", ",")}" title="${fuera ? "Fuera del rango esperado. " : ""}${it.min != null && it.max != null ? `Rango: ${it.min}–${it.max}` : ""}">${it.unidad ? `<span class="v-un">${esc(it.unidad)}</span>` : ""}`;
      break;
    }
    case "fecha": ctrl = fechaInp(it.codigo, v[it.codigo]); break;
    default:
      ancho = true;
      ctrl = `<input class="inp vtxt" data-in="${k}" data-t="texto" data-foco="${k}" value="${esc(v[it.codigo] || "")}" placeholder="Texto libre…">`;
  }
  if (mk === DUDA) extra += `<div class="vx duda">${icono("bandera")}<input class="inp vtxt" data-in="${k}_duda_nota" data-t="texto" data-foco="${k}_duda_nota" placeholder="¿Cuál es la duda?" value="${esc(v[it.codigo + "_duda_nota"] || "")}"></div>`;
  return `<div class="vf ${resp ? "resp" : cuenta ? "falta" : ""} ${mk === DUDA ? "con-duda" : ""} ${ancho ? "ancho" : ""} ${pendIA ? "ia-pend" + (mIA.aviso ? " ia-aviso" : "") : ""}" data-k="${k}">
    <div class="vl" title="${tip}"><span>${esc(it.etiqueta)}</span>${it.provisional ? `<sup title="Código provisional (no existe en el CRF oficial)">P</sup>` : ""}${chipIA}</div><div class="vc">${ctrl}</div>${extra}</div>`;
}

/** Teclado del Modo Vintage: S / N / ? / D contestan y pasan a la siguiente; flechas para moverse. */
function teclaVintage(ev) {
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const fila = ev.target.closest(".vf");
  if (!fila) return;
  const filas = $$("#seccion .vf"), i = filas.indexOf(fila);
  const enTexto = ["INPUT", "TEXTAREA"].includes(ev.target.tagName);
  if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && ev.target.tagName !== "SELECT") {
    const dest = enfocable(filas[i + (ev.key === "ArrowDown" ? 1 : -1)]);
    if (dest) { ev.preventDefault(); dest.focus(); }
    return;
  }
  if (enTexto || ev.target.tagName === "SELECT") return;
  if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
    const bs = [...fila.querySelectorAll(".vc button:not(.ia-chip)")], j = bs.indexOf(ev.target);
    const dest = bs[j + (ev.key === "ArrowRight" ? 1 : -1)];
    if (dest) { ev.preventDefault(); dest.focus(); }
    return;
  }
  if (soloLectura()) return;
  const it = S.modelo.porCodigo[fila.dataset.k];
  const t = ev.key.toLowerCase();
  let b = null;
  if (["sino", "sinofecha"].includes(it?.tipoCampo)) {
    if (t === "s") b = fila.querySelector('[data-sino][data-val="1"]');
    if (t === "n") b = fila.querySelector('[data-sino][data-val="0"]');
  }
  if (ev.key === "?" || ev.key === "¿") b = fila.querySelector('[data-marca="NC"]');
  if (t === "d") b = fila.querySelector('[data-marca="DUDA"]');
  if (!b) return;
  ev.preventDefault();
  const esDuda = b.dataset.marca === DUDA;
  if (b.classList.contains("on")) { if (!esDuda) enfocable(filas[i + 1])?.focus(); return; }  // ya estaba: solo avanza
  if (!esDuda) E.avanzar = { k: fila.dataset.k, paso: 1 };  // la duda deja el foco en su nota
  b.click();
}

function campoHTML(it, v, animar) {
  const cod = `<span class="cod" title="Código en el registro: ${esc(it.codigo)}">${esc(it.codigo)}</span>`;
  const prov = it.provisional ? ` <span class="prov" title="Este código no existe en el CRF oficial">PROVISIONAL</span>` : "";
  const ayuda = it.ayuda && !/^DUPLICADO|Solapa/.test(it.ayuda) ? `<div class="ayuda">${esc(it.ayuda)}</div>` : "";
  const est = animar ? "" : ' style="animation:none"';
  const mk = admiteMarcas(it) ? marcaDe(it, v) : null;
  const resp = (() => {
    if (mk) return mk === NC;
    switch (it.tipoCampo) {
      case "single": return it.opciones.some((o) => v[o.codigo] === 1);
      case "multi": return it.opciones.some((o) => v[o.codigo] != null);
      default: return v[it.codigo] != null && v[it.codigo] !== "";
    }
  })();
  const mIA = E.caso?.ia?.[it.codigo];
  const pendIA = mIA && !mIA.revisado && (mIA.codigos || []).some((k) => v[k] != null && v[k] !== "");
  const chipIA = mIA && (mIA.codigos || []).some((k) => v[k] != null && v[k] !== "")
    ? `<button class="ia-chip ${pendIA ? "pend" : ""} ${pendIA && mIA.aviso ? "aviso" : ""}" data-ia="${esc(it.codigo)}" title="${pendIA ? "Propuesto por la IA: pulse para ver de dónde lo saca" : "Dato de la IA ya revisado"}">${icono("chispa")}IA${pendIA ? "" : " ✓"}</button>` : "";
  const cab = `<div class="lab"><span>${esc(it.etiqueta)}${prov}</span>${chipIA}${cod}</div>${ayuda}`;
  const fechaInp = (k, val) => `<input type="text" class="inp fecha" inputmode="numeric" autocomplete="off" maxlength="10" placeholder="dd/mm/aaaa"
      data-in="${esc(k)}" data-t="fecha" data-foco="${esc(k)}" value="${esc(isoAFecha(val))}">`;
  const limpiar = (ks) => `<button class="limpiar" data-limpiar="${esc(ks.join(","))}" title="Borrar respuesta">${icono("x")}</button>`;
  let ctrl = "", ancho = false, aviso = "";
  const botonesMarca = () => `<div class="marcas-bt">
      <button class="mb ${mk === NC ? "on nc" : ""}" data-marca="${NC}" data-mk="${esc(it.codigo)}" title="Desconocido: lo he buscado y no consta">${icono("interrogacion")}<span>Desconocido</span></button>
      <button class="mb ${mk === DUDA ? "on duda" : ""}" data-marca="${DUDA}" data-mk="${esc(it.codigo)}" title="Duda: que lo revise un cardiólogo revisor o un data manager">${icono("bandera")}<span>Duda</span></button></div>`;
  const notaDuda = () => mk === DUDA ? `<div class="nota-duda">${icono("bandera")}<input class="inp" data-in="${esc(it.codigo)}_duda_nota" data-t="texto" data-foco="${esc(it.codigo)}_duda_nota"
      placeholder="¿Cuál es la duda? Ej.: «IMC 29,8: ¿cuenta como obesidad?»" value="${esc(v[it.codigo + "_duda_nota"] || "")}"></div>` : "";

  switch (it.tipoCampo) {
    case "fijo":
      ctrl = `<span class="fijo">${icono("candado")} ${esc(it.fijo || v[it.codigo] || "")}</span>`; break;
    case "caso":
      ctrl = `<span class="fijo">${icono("candado")} #${pad(E.caso.numero)}</span>`; break;
    case "sino":
    case "sinofecha": {
      const x = v[it.codigo];
      ctrl = `<div class="sino"><button class="si ${x === 1 ? "on" : ""}" data-sino="${esc(it.codigo)}" data-val="1" data-foco="${esc(it.codigo)}:1">Sí</button><button class="no ${x === 0 ? "on" : ""}" data-sino="${esc(it.codigo)}" data-val="0" data-foco="${esc(it.codigo)}:0">No</button></div>
        ${x != null ? limpiar([it.codigo, it.codigo + "_date", it.codigo + "_duda_nota"]) : ""}${botonesMarca()}`;
      if (it.tipoCampo === "sinofecha" && x === 1) ctrl += `<div class="fecha-op">${icono("historial")} <b>Fecha</b> ${fechaInp(it.codigo + "_date", v[it.codigo + "_date"])}</div>`;
      ctrl += notaDuda();
      break;
    }
    case "single":
    case "multi": {
      ancho = it.opciones.length > 5;
      const multi = it.tipoCampo === "multi";
      ctrl = `<div class="opciones">${it.opciones.map((o) => {
        const x = v[o.codigo];
        return `<button class="op ${x === 1 ? "on" : ""} ${multi && x === 0 ? "cero" : ""}" data-g="${esc(it.codigo)}" data-o="${esc(o.codigo)}" data-foco="${esc(o.codigo)}" title="${esc(o.codigo)}">${multi && x === 1 ? icono("check") : ""}${esc(o.etiqueta)}</button>`;
      }).join("")}</div>${it.opciones.some((o) => v[o.codigo] != null) || mk ? limpiar([it.codigo, it.codigo + "_duda_nota", ...it.opciones.flatMap((o) => [o.codigo, o.codigo + "_date"])]) : ""}${botonesMarca()}`;
      if (it.conFecha && !mk) ctrl += `<div class="fecha-op">${icono("historial")} <b>Fecha</b> ${fechaInp(it.codigo, v[it.codigo])}</div>`;
      for (const o of it.opciones) if (o.conFecha && v[o.codigo] === 1) ctrl += `<div class="fecha-op">${icono("historial")} <b>Fecha · ${esc(o.etiqueta)}</b> ${fechaInp(o.codigo + "_date", v[o.codigo + "_date"])}</div>`;
      if (multi && !mk) ctrl += `<div class="ayuda" style="width:100%">Las opciones no marcadas se guardan como No.</div>`;
      ctrl += notaDuda();
      break;
    }
    case "numero":
    case "entero": {
      const x = v[it.codigo];
      const fuera = x != null && ((it.min != null && x < it.min) || (it.max != null && x > it.max));
      ctrl = `<input class="inp num ${fuera ? "fuera" : ""}" data-in="${esc(it.codigo)}" data-t="${it.tipoCampo}" data-foco="${esc(it.codigo)}" inputmode="decimal" value="${x == null ? "" : String(x).replace(".", ",")}">
        ${it.unidad ? `<span class="unidad">${esc(it.unidad)}</span>` : ""}${it.min != null && it.max != null ? `<span class="rango">${String(it.min).replace(".", ",")}–${String(it.max).replace(".", ",")}</span>` : ""}`;
      if (fuera) aviso = `<div class="aviso-r">${icono("aviso")} Fuera del rango esperado. Compruebe el valor.</div>`;
      break;
    }
    case "fecha":
      ctrl = fechaInp(it.codigo, v[it.codigo]); break;
    default:
      ancho = true;
      ctrl = `<textarea class="inp" data-in="${esc(it.codigo)}" data-t="texto" data-foco="${esc(it.codigo)}" placeholder="Texto libre…">${esc(v[it.codigo] || "")}</textarea>`;
  }
  return `<div class="campo ${resp ? "respondido" : ""} ${mk === DUDA ? "con-duda" : ""} ${ancho ? "ancho" : ""} ${pendIA ? "ia-pend" + (mIA.aviso ? " ia-aviso" : "") : ""}" data-k="${esc(it.codigo)}"${est}>${cab}<div class="ctrl">${ctrl}</div>${aviso}</div>`;
}

function alClicar(ev) {
  const ia = ev.target.closest("[data-ia]");
  if (ia) return abrirDatoIA(ia.dataset.ia);
  if (soloLectura()) return;
  const v = E.caso.valores;
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.dataset.marca) {
    const k = b.dataset.mk, m = b.dataset.marca, it = S.modelo.porCodigo[k];
    const cambios = {};
    if (marcaDe(it, v) === m) { cambios[k] = null; cambios[k + "_duda_nota"] = null; }
    else {
      cambios[k] = m;
      if (m !== DUDA) cambios[k + "_duda_nota"] = null;
      if (it.opciones) it.opciones.forEach((o) => { cambios[o.codigo] = null; cambios[o.codigo + "_date"] = null; });
      else cambios[k + "_date"] = null;
    }
    for (const x of Object.keys(cambios)) if (cambios[x] === null && v[x] == null) delete cambios[x];
    aplicar(cambios);
    if (m === DUDA && cambios[k] === DUDA) setTimeout(() => $(`[data-foco="${CSS.escape(k + "_duda_nota")}"]`)?.focus(), 60);
  } else if (b.dataset.sino) {
    const k = b.dataset.sino, val = +b.dataset.val;
    if (E.vintage && v[k] === val) return aplicar({ [k]: null, ...(v[k + "_date"] ? { [k + "_date"]: null } : {}) });
    const cambios = { [k]: val };
    if (val === 0 && v[k + "_date"]) cambios[k + "_date"] = null;
    if (v[k + "_duda_nota"]) cambios[k + "_duda_nota"] = null;
    aplicar(cambios);
  } else if (b.dataset.limpiar) {
    aplicar(Object.fromEntries(b.dataset.limpiar.split(",").map((k) => [k, null])));
  } else if (b.dataset.o) {
    const g = S.modelo.porCodigo[b.dataset.g], o = b.dataset.o;
    const cambios = {};
    if (esMarca(v[g.codigo])) { cambios[g.codigo] = null; cambios[g.codigo + "_duda_nota"] = null; }
    if (g.tipoCampo === "single") {
      if (v[o] === 1) g.opciones.forEach((x) => { cambios[x.codigo] = null; cambios[x.codigo + "_date"] = null; });
      else g.opciones.forEach((x) => { cambios[x.codigo] = x.codigo === o ? 1 : 0; if (x.codigo !== o) cambios[x.codigo + "_date"] = null; });
    } else {
      cambios[o] = v[o] === 1 ? 0 : 1;
      if (cambios[o] === 0) cambios[o + "_date"] = null;
      g.opciones.forEach((x) => { if (x.codigo !== o && v[x.codigo] == null) cambios[x.codigo] = 0; });
    }
    for (const k of Object.keys(cambios)) if (cambios[k] === null && v[k] == null) delete cambios[k];
    aplicar(cambios);
  }
}

// ---- Fechas tecleadas: dd/mm/aaaa ----
const hoyIso = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
function isoAFecha(v) {
  const m = String(v || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
}
function fechaAIso(t) {
  const m = String(t).trim().match(/^(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4})$/) || String(t).trim().match(/^(\d{2})(\d{2})(\d{4})$/);
  if (!m) return null;
  const [d, mes, a] = [+m[1], +m[2], +m[3]];
  const f = new Date(Date.UTC(a, mes - 1, d));
  if (f.getUTCFullYear() !== a || f.getUTCMonth() !== mes - 1 || f.getUTCDate() !== d) return null; // p. ej. 31/02
  return `${a}-${String(mes).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
/**
 * Mientras se escribe: las barras se ponen solas (16042026 → 16/04/2026).
 * Si la persona escribe sus propias barras ("5/3/1948"), se respetan y se completan los ceros.
 */
function mascaraFecha(el, ev) {
  if (ev.inputType && ev.inputType.startsWith("delete")) return; // al borrar, no reescribir
  // "5/" → "05/": un día o mes de una cifra seguido de barra se completa con un cero
  const conCeros = el.value.replace(/(^|\D)(\d)(?=\D)/g, "$10$2");
  const dig = conCeros.replace(/\D/g, "").slice(0, 8);
  let s = dig.slice(0, 2);
  if (dig.length > 2) s += "/" + dig.slice(2, 4);
  if (dig.length > 4) s += "/" + dig.slice(4);
  if (dig.length === 2 || dig.length === 4) s += "/";
  el.value = s;
}

function alCambiar(ev) {
  if (soloLectura()) return;
  const el = ev.target;
  if (el.dataset.sel) {  // desplegable de selección única (Modo Vintage)
    const g = S.modelo.porCodigo[el.dataset.sel], o = el.value, v = E.caso.valores, cambios = {};
    if (esMarca(v[g.codigo])) { cambios[g.codigo] = null; cambios[g.codigo + "_duda_nota"] = null; }
    g.opciones.forEach((x) => { cambios[x.codigo] = o ? (x.codigo === o ? 1 : 0) : null; if (x.codigo !== o) cambios[x.codigo + "_date"] = null; });
    for (const k of Object.keys(cambios)) if (cambios[k] === null && v[k] == null) delete cambios[k];
    return aplicar(cambios);
  }
  if (!el.dataset.in) return;
  const k = el.dataset.in, t = el.dataset.t;
  let val = el.value.trim();
  if (t === "numero" || t === "entero") {
    if (val === "") val = null;
    else {
      const x = Number(val.replace(/\s/g, "").replace(",", "."));
      if (!isFinite(x)) { toast("Escriba un número (use coma o punto para decimales)", "mal"); el.value = E.caso.valores[k] ?? ""; return; }
      if (t === "entero" && !Number.isInteger(x)) { toast("Este campo es un número entero", "mal"); el.value = E.caso.valores[k] ?? ""; return; }
      val = x;
    }
  } else if (t === "fecha") {
    if (val === "") val = null;
    else {
      const iso = fechaAIso(val);
      if (!iso) { toast("Fecha no válida. Escríbala como dd/mm/aaaa (por ejemplo 16/04/1950)", "mal"); el.value = isoAFecha(E.caso.valores[k]); el.focus(); return; }
      if (iso > hoyIso()) { toast("La fecha no puede ser posterior a hoy", "mal"); el.value = isoAFecha(E.caso.valores[k]); el.focus(); return; }
      if (iso < "1900-01-01") { toast("Revise el año: es anterior a 1900", "mal"); el.value = isoAFecha(E.caso.valores[k]); el.focus(); return; }
      val = iso;
    }
  } else if (val === "") val = null;
  aplicar({ [k]: val });
}

function aplicar(cambios, origen = "formulario") {
  // Reglas por defecto que dependen de lo que acaba de cambiar (p. ej. consentimiento según tipo de reclutamiento)
  const def = valoresPorDefecto(S.modelo, { ...E.caso.valores, ...cambios }, { soloReglas: true, cambiados: cambios });
  for (const [k, x] of Object.entries(def)) if (!(k in cambios)) cambios[k] = x;
  if (E.origen && E.origen !== origen) vaciarPendientes();
  E.origen = origen;
  if (E.caso.ia) marcarPorCampos(E.caso.ia, Object.keys(cambios)); // lo que toca una persona deja de estar pendiente (igual que el servidor)
  for (const [k, val] of Object.entries(cambios)) {
    if (val === null || val === undefined) delete E.caso.valores[k];
    else E.caso.valores[k] = val;
    E.pend[k] = val ?? null;
  }
  clearTimeout(E.timer);
  E.timer = setTimeout(vaciarPendientes, 450);
  actualizarGuardado("pendiente");
  requestAnimationFrame(() => pintarCaso(false));
}

async function vaciarPendientes(keepalive = false) {
  clearTimeout(E.timer);
  if (!E.caso || !Object.keys(E.pend).length) return;
  const cuerpo = { valores: E.pend, origen: E.origen || "formulario" };
  const num = E.caso.numero;
  E.pend = {}; E.origen = null;
  actualizarGuardado("guardando");
  try {
    const r = await api("PUT", "casos/" + num, cuerpo, { keepalive });
    if (E.caso?.numero === num) {
      E.caso.estado = r.estado; E.caso.modificado = r.modificado; if (r.ia) E.caso.ia = r.ia;
      // mantener valores locales con cambios aún no enviados
      E.caso.valores = { ...r.valores, ...Object.fromEntries(Object.entries(E.pend).filter(([, x]) => x !== null)) };
      for (const [k, x] of Object.entries(E.pend)) if (x === null) delete E.caso.valores[k];
    }
    actualizarGuardado("ok");
  } catch (e) {
    actualizarGuardado("error");
    toast("No se pudo guardar: " + e.message, "mal");
  }
}

function actualizarGuardado(estado) {
  const g = $("#guardado");
  if (!g) return;
  estado = estado || (Object.keys(E.pend).length ? "pendiente" : "ok");
  g.className = "guardado " + (estado === "guardando" || estado === "pendiente" ? "guardando" : "");
  g.innerHTML = {
    ok: `${icono("check")} Guardado`, pendiente: `${icono("historial")} Guardando…`, guardando: `${icono("historial")} Guardando…`, error: `${icono("aviso")} Sin guardar`,
  }[estado];
}
window.addEventListener("beforeunload", () => vaciarPendientes(true));

async function editarDiagnosticos() {
  const c = E.caso;
  let sel = diagnosticosDe(c), otro = c.valores.other_disease || "";
  await modal({
    titulo: "Diagnósticos del estudio", aceptar: "Guardar",
    html: `<div class="sub" style="margin-bottom:10px">Marque todas las patologías por las que el paciente está en el estudio (una fila por cada una en el Excel final).</div>
      <div id="dSel" class="selector-modal"></div>
      <p class="sub" style="margin-top:12px">Si quita un diagnóstico, sus datos <b>no se borran</b>: simplemente dejan de mostrarse y de exportarse.</p><div class="error"></div>`,
    alAbrir: (m) => {
      const pin = () => {
        $("#dSel", m).innerHTML = `<div class="opciones">${PRINCIPALES.map((g) => `<span class="chip ${sel.includes(g) ? "on" : ""}" data-p="${g}" style="--c:${ENFERMEDADES[g].color}">${icono(g)} ${esc(ENFERMEDADES[g].nombre)}</span>`).join("")}</div>
          ${sel.includes("OTRO") ? `<label class="otro-diag"><b>Otros: ¿qué diagnóstico?</b><input class="inp" id="otroM" value="${esc(otro)}"></label>` : ""}`;
        $$("[data-p]", m).forEach((x) => (x.onclick = () => { const g = x.dataset.p; sel = sel.includes(g) ? sel.filter((y) => y !== g) : [...sel, g]; pin(); }));
        $("#otroM", m)?.addEventListener("input", (ev) => (otro = ev.target.value));
      };
      pin();
    },
    alAceptar: async () => {
      if (!sel.length) throw new Error("Marque al menos un diagnóstico");
      if (sel.includes("OTRO") && !otro.trim()) throw new Error("Describa el diagnóstico de 'Otros'");
      await vaciarPendientes();
      E.caso = conInformes(await api("PUT", "casos/" + c.numero, { principal: sel[0], secundarias: sel.slice(1),
        valores: { other_disease: sel.includes("OTRO") ? otro.trim() : null } }));
      toast("Diagnósticos actualizados");
      pCaso(c.numero, E.tab);
    },
  });
}

// ---------------------------------------------------------------------------
//  Cajón lateral genérico
// ---------------------------------------------------------------------------
function cajon(titulo, sub, icon) {
  const velo = document.createElement("div"); velo.className = "velo";
  const cj = document.createElement("aside"); cj.className = "cajon";
  cj.innerHTML = `<div class="cab"><div class="kpi" style="padding:0"><div class="ic">${icono(icon)}</div></div><div><h3>${esc(titulo)}</h3><div class="sub">${sub}</div></div>
    <button class="btn fantasma btn-icono" style="margin-left:auto" data-cerrar>${icono("x")}</button></div><div class="cuerpo"></div><div class="pie"></div>`;
  const cerrar = () => { velo.remove(); cj.remove(); document.removeEventListener("keydown", tecla); };
  const tecla = (e) => e.key === "Escape" && cerrar();
  velo.onclick = cerrar; cj.querySelector("[data-cerrar]").onclick = cerrar;
  document.addEventListener("keydown", tecla);
  document.body.append(velo, cj);
  return { cuerpo: $(".cuerpo", cj), pie: $(".pie", cj), cerrar };
}

async function abrirHistorial() {
  const c = E.caso;
  const cj = cajon(`Historial del caso #${pad(c.numero)}`, "Quién cambió qué y cuándo", "historial");
  cj.pie.remove();
  const aud = await api("GET", "auditoria?caso=" + c.numero + "&limite=500");
  const etq = (k) => {
    const base = k.replace(/_date$/, "");
    const it = S.modelo.porCodigo[k] || S.modelo.porCodigo[base];
    if (!it) return k;
    const pre = it.padre ? it.padre.etiqueta + " › " : "";
    return pre + it.etiqueta + (k.endsWith("_date") && !S.modelo.porCodigo[k] ? " (fecha)" : "");
  };
  const fmt = (x) => x == null ? "∅" : x === "1" ? "Sí" : x === "0" ? "No" : x === NC ? "Desconocido" : x === DUDA ? "Duda" : x;
  cj.cuerpo.innerHTML = aud.length ? `<ul class="historial">${aud.map((a) => `<li><div><div>${esc(fmtFecha(a.fecha))}</div><div class="cuando">${esc(a.fecha.slice(11, 16))} · ${esc(a.usuario)}</div></div>
    <div><div><b>${esc(a.campo.startsWith("(") ? a.campo.slice(1, -1) : etq(a.campo))}</b> ${a.origen !== "formulario" ? `<span class="origen">${{ importacion: "informe", ia: "IA", ia_revision: "revisión IA" }[a.origen] || "relleno No"}</span>` : ""}</div>
    <div class="cambio"><del>${esc(fmt(a.antes))}</del> → <ins>${esc(fmt(a.despues))}</ins></div></div></li>`).join("")}</ul>` : `<div class="vacio">Sin cambios registrados</div>`;
}

// ---------------------------------------------------------------------------
//  DATOS PROPUESTOS POR LA IA (fase 2)
// ---------------------------------------------------------------------------
const conInformes = (r) => (E.caso && r && !r.informes ? { ...r, informes: E.caso.informes } : r);

/** Claves de c.ia pendientes que se ven en la pestaña t. */
function iaDePestana(t, c) {
  const pend = new Set(iaPendientes(c));
  return t.bloques.flatMap((b) => b.items).filter((it) => visible(it, c.valores) && pend.has(it.codigo)).map((it) => it.codigo);
}

async function revisarIA(claves, msg) {
  await vaciarPendientes();
  try {
    E.caso = conInformes(await api("PUT", "casos/" + E.caso.numero, { ia_revisar: claves, origen: "ia_revision" }));
    toast(msg);
    pintarCaso();
  } catch (e) { toast(e.message, "mal"); }
}

function irAPendienteIA() {
  const c = E.caso, pend = new Set(iaPendientes(c));
  if (pend.has("_diagnosticos")) return window.scrollTo({ top: 0, behavior: "smooth" });
  for (const t of pestanasDelCaso(S.modelo, c)) {
    const it = t.bloques.flatMap((b) => b.items).find((x) => visible(x, c.valores) && pend.has(x.codigo));
    if (!it) continue;
    E.tab = t.id;
    history.replaceState(null, "", `#/caso/${c.numero}/${encodeURIComponent(t.id)}`);
    pintarCaso();
    const el = $(`#seccion [data-k="${CSS.escape(it.codigo)}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("destello");
    return;
  }
  toast("Hay datos de la IA en campos que ahora no se muestran: confírmelos desde «Datos de la IA» o quite el dato", "info");
}

async function abrirDatoIA(k) {
  const c = E.caso, m = c.ia?.[k];
  if (!m) return;
  const it = S.modelo.porCodigo[k];
  const titulo = k === "_diagnosticos" ? "Diagnósticos del estudio" : it?.etiqueta || k;
  const deCabecera = m.origen !== "ia";
  const puede = !soloLectura() && !m.revisado;
  await modal({
    titulo: m.revisado ? "Dato de la IA (ya revisado)" : "Dato propuesto por la IA",
    aceptar: puede ? "Es correcto" : "Cerrar", cancelar: puede ? "Cerrar" : "",
    html: `<div class="dato-ia"><div class="q">${esc(titulo)}</div><div class="v">${icono("chispa")} ${esc(m.valor_texto || "")}</div>
      ${m.origen !== "ia" ? `<div class="sub">Origen: ${esc(NOMBRE_ORIGEN[m.origen] || m.origen)}</div>` : ""}
      ${m.aviso ? `<div class="aviso-ia">${icono("aviso")} ${esc(m.aviso)}</div>` : ""}
      ${m.cita ? `<div class="sub" style="margin-top:12px">${deCabecera ? "Se basa en" : "Lo que dice el informe"}:</div><blockquote class="cita-ia">${esc(m.cita)}</blockquote>` : `<p class="sub">La IA no ha indicado la frase del informe.</p>`}
      <div class="acc">${c.informes?.length && m.cita ? `<button class="btn pequeno" id="iaVer">${icono("libro")} Ver en el informe</button>` : ""}
      ${puede && k !== "_diagnosticos" ? `<button class="btn pequeno peligro" id="iaQuitar">${icono("papelera")} Quitar el dato</button>` : ""}</div>
      ${puede ? `<p class="sub">Si no es correcto, corríjalo directamente en el formulario: al cambiarlo deja de estar pendiente.</p>` : ""}</div>`,
    alAbrir: (mm) => {
      $("#iaVer", mm)?.addEventListener("click", () => {
        mm.previousElementSibling?.remove(); mm.remove();
        abrirInforme(m.cita.split("\n").map((x) => x.replace(/^[A-Z]{2,4}:\s*/, "")), puede ? k : null);
      });
      $("#iaQuitar", mm)?.addEventListener("click", () => {
        mm.previousElementSibling?.remove(); mm.remove();
        aplicar(Object.fromEntries((m.codigos || []).map((x) => [x, null])));
        toast("Dato quitado");
      });
    },
    alAceptar: async () => { if (puede) await revisarIA([k], "Dato confirmado"); },
  });
}

/** Muestra el texto anonimizado de los informes del caso, resaltando las frases indicadas. */
function abrirInforme(citas = [], clave = null) {
  const infs = E.caso.informes || [];
  if (!infs.length) return toast("Este caso no tiene informes importados", "info");
  citas = (Array.isArray(citas) ? citas : [citas]).filter((x) => x && x.trim().length > 3);
  const cj = cajon("Informe anonimizado", "Texto del informe tal y como lo leyó la IA (sin datos personales)", "libro");
  if (clave) {
    const m = E.caso.ia[clave], it = S.modelo.porCodigo[clave];
    cj.pie.innerHTML = `<span class="sub" style="margin-right:auto">${icono("chispa")} ${esc(clave === "_diagnosticos" ? "Diagnósticos" : it?.etiqueta || clave)}: <b>${esc(m.valor_texto)}</b></span>
      <button class="btn fantasma" data-c>Cerrar</button><button class="btn primario" data-okia>${icono("check")} Es correcto</button>`;
    $("[data-c]", cj.pie).onclick = cj.cerrar;
    $("[data-okia]", cj.pie).onclick = async () => { cj.cerrar(); await revisarIA([clave], "Dato confirmado"); };
  } else cj.pie.remove();
  const resaltar = (texto) => {
    let h = esc(texto).replace(/\[([A-ZÁÉÍÓÚÑº ]{2,})\]/g, '<span class="marca-anon">[$1]</span>');
    for (const ci of citas) {
      const partes = esc(ci.trim()).split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
      try { h = h.replace(new RegExp(partes.join("\\s+"), "i"), (x) => `<mark class="cita">${x}</mark>`); } catch { /* cita rara */ }
    }
    return h;
  };
  let sel = Math.max(0, infs.findIndex((i) => citas.length && citas.some((ci) => i.texto.replace(/\s+/g, " ").toLowerCase().includes(ci.trim().replace(/\s+/g, " ").toLowerCase()))));
  const pintar = () => {
    const i = infs[sel];
    cj.cuerpo.innerHTML = `${infs.length > 1 ? `<div class="opciones" style="margin-bottom:12px">${infs.map((x, n) => `<button class="op ${n === sel ? "on" : ""}" data-inf="${n}">${x.indice ? "Ingreso índice" : "Reingreso"} · ${esc(fmtFecha(x.fecha_ingreso))}</button>`).join("")}</div>` : ""}
      <div class="sub">Ingreso ${esc(fmtFecha(i.fecha_ingreso))} · alta ${esc(fmtFecha(i.fecha_alta))}${i.servicio ? " · " + esc(i.servicio) : ""}</div>
      <pre class="informe-txt">${resaltar(i.texto)}</pre>`;
    $$("[data-inf]", cj.cuerpo).forEach((b) => (b.onclick = () => { sel = +b.dataset.inf; pintar(); }));
    setTimeout(() => $("mark.cita", cj.cuerpo)?.scrollIntoView({ block: "center" }), 50);
  };
  pintar();
}

// ---------------------------------------------------------------------------
//  IMPORTADOR DE INFORMES (local)
// ---------------------------------------------------------------------------
function abrirImportador() {
  if (soloLectura()) return toast("Caso validado: solo lectura", "mal");
  const cj = cajon("Importar informe", "Pegue el texto de un informe: se anonimiza y se extraen los datos aquí mismo", "importar");
  const I = { paso: 1, original: "", anon: null, props: [], sel: new Set(), editar: false, cabecera: true };
  const v = E.caso.valores;
  const tabsVis = new Set(pestanasDelCaso(S.modelo, E.caso).flatMap((t) => t.bloques.flatMap((b) => b.items.flatMap((i) => [i.codigo, ...(i.opciones || []).map((o) => o.codigo)]))));

  const pintar = () => {
    const pasos = `<div class="pasos-mini">${[1, 2, 3].map((n) => `<span class="${I.paso >= n ? "on" : ""}"></span>`).join("")}</div>`;
    const aviso = `<div class="aviso-local">${icono("candado")}<div><b>Todo ocurre en este ordenador.</b> El texto no se envía a ningún sitio y no se guarda: solo se guardan los datos que usted acepte.</div></div>`;
    if (I.paso === 1) {
      cj.cuerpo.innerHTML = `${pasos}${aviso}
        <textarea class="inp texto-informe" id="txt" placeholder="Pegue aquí el informe (eco, alta, consulta, analítica)…  Desde un PDF: seleccione todo (Ctrl+A), copie (Ctrl+C) y pegue (Ctrl+V).">${esc(I.original)}</textarea>
        <label style="display:flex;gap:8px;align-items:center;margin-top:12px;font-size:14px"><input type="checkbox" id="cab" ${I.cabecera ? "checked" : ""}> Quitar las líneas de cabecera con datos del paciente</label>`;
      cj.pie.innerHTML = `<button class="btn fantasma" id="ej" style="margin-right:auto">${icono("ojo")} Cargar un ejemplo ficticio</button><button class="btn primario" id="sig">${icono("escudo")} Anonimizar</button>`;
      $("#ej", cj.pie).onclick = () => { I.original = EJEMPLO; pintar(); };
      $("#sig", cj.pie).onclick = () => {
        I.original = $("#txt", cj.cuerpo).value; I.cabecera = $("#cab", cj.cuerpo).checked;
        if (!I.original.trim()) return toast("Pegue primero el texto del informe", "mal");
        I.anon = anonimizar(I.original, { quitarCabecera: I.cabecera }); I.paso = 2; I.editar = false; pintar();
      };
      $("#txt", cj.cuerpo).focus();
    } else if (I.paso === 2) {
      const tipos = {};
      I.anon.marcas.forEach((m) => (tipos[m.tipo] = (tipos[m.tipo] || 0) + 1));
      cj.cuerpo.innerHTML = `${pasos}
        <h3 style="margin:0 0 4px">Revise el texto anonimizado</h3>
        <div class="sub">En rojo lo que se ha ocultado. Si ve algún nombre u otro dato identificativo, pulse <b>Editar a mano</b> y bórrelo.</div>
        <div class="marcas">${Object.entries(tipos).map(([t, n]) => `<span class="pill sec">${esc(t)} · ${n}</span>`).join("") || `<span class="sub">No se ha detectado ningún identificador.</span>`}</div>
        ${I.editar ? `<textarea class="inp texto-informe" id="ed">${esc(I.anon.texto)}</textarea>`
          : `<div class="vista-anon">${esc(I.anon.texto).replace(/\[[A-ZÁÉÍÓÚÑ\/. ]{2,}\]/g, (m) => `<mark>${m}</mark>`)}</div>`}`;
      cj.pie.innerHTML = `<button class="btn fantasma" id="ant" style="margin-right:auto">${icono("flechaI")} Atrás</button>
        <button class="btn" id="edit">${icono("editar")} ${I.editar ? "Ver resaltado" : "Editar a mano"}</button><button class="btn primario" id="sig">${icono("varita")} Extraer datos</button>`;
      const leer = () => { if (I.editar) I.anon.texto = $("#ed", cj.cuerpo).value; };
      $("#ant", cj.pie).onclick = () => { I.paso = 1; pintar(); };
      $("#edit", cj.pie).onclick = () => { leer(); I.editar = !I.editar; pintar(); };
      $("#sig", cj.pie).onclick = () => {
        leer();
        I.props = extraer(I.anon.texto, S.modelo);
        I.sel = new Set(I.props.filter((p) => tabsVis.has(p.codigo) && Object.entries(p.cambios).every(([k]) => v[k] == null)).map((p) => p.id));
        I.paso = 3; pintar();
      };
    } else {
      const actual = (p) => {
        const dif = Object.entries(p.cambios).filter(([k, x]) => v[k] != null && v[k] !== x);
        return dif.length ? "Ya tiene otro valor: se sustituirá" : Object.entries(p.cambios).every(([k, x]) => v[k] === x) ? "Igual al valor actual" : "";
      };
      cj.cuerpo.innerHTML = `${pasos}
        <h3 style="margin:0 0 4px">${I.props.length} dato${I.props.length === 1 ? "" : "s"} encontrado${I.props.length === 1 ? "" : "s"}</h3>
        <div class="sub" style="margin-bottom:14px">Marque los que quiera incorporar. Debajo de cada uno verá la frase del informe de donde sale.</div>
        ${I.props.map((p) => `<label class="propuesta ${I.sel.has(p.id) ? "sel" : ""}" data-id="${esc(p.id)}">
          <input type="checkbox" ${I.sel.has(p.id) ? "checked" : ""}>
          <div><div class="t">${esc(p.titulo)}</div><div class="f">${esc(p.frag.antes)}<mark>${esc(p.frag.match)}</mark>${esc(p.frag.despues)}</div>
            ${p.aviso ? `<div class="av">${icono("aviso")} ${esc(p.aviso)}</div>` : ""}${!tabsVis.has(p.codigo) ? `<div class="otra">Campo de otra patología: no visible en este caso</div>` : ""}</div>
          <div><div class="val">${esc(p.valorTexto)}</div><div class="actual">${esc(actual(p))}</div></div></label>`).join("") || `<div class="vacio">${icono("buscar")}<p>No se han reconocido datos en este texto.</p></div>`}`;
      cj.pie.innerHTML = `<button class="btn fantasma" id="ant" style="margin-right:auto">${icono("flechaI")} Atrás</button>
        <button class="btn" id="todos">Marcar todos</button><button class="btn primario" id="ok" ${I.sel.size ? "" : "disabled"}>${icono("check")} Incorporar ${I.sel.size}</button>`;
      $$(".propuesta", cj.cuerpo).forEach((el) => el.querySelector("input").onchange = (ev) => { ev.target.checked ? I.sel.add(el.dataset.id) : I.sel.delete(el.dataset.id); pintar(); });
      $("#ant", cj.pie).onclick = () => { I.paso = 2; pintar(); };
      $("#todos", cj.pie).onclick = () => { I.props.forEach((p) => I.sel.add(p.id)); pintar(); };
      $("#ok", cj.pie).onclick = () => {
        const cambios = {};
        I.props.filter((p) => I.sel.has(p.id)).forEach((p) => Object.assign(cambios, p.cambios));
        aplicar(cambios, "importacion");
        vaciarPendientes();
        toast(`${I.sel.size} datos incorporados desde el informe`);
        cj.cerrar();
      };
    }
  };
  pintar();
}

// ===========================================================================
//  LIBRO LLAVE (solo data managers)
// ===========================================================================
async function pLlave() {
  barra("Libro llave", "Data manager");
  const cont = $("#contenido");
  let q = "", ver = new Set();
  const enmascarar = (s) => (s ? s.slice(0, 2) + "•".repeat(Math.max(0, s.length - 5)) + s.slice(-3) : "—");
  const pintar = async (asignado) => {
    const d = await api("GET", "llave" + (q ? "?q=" + encodeURIComponent(q) : ""));
    const cab = `<div class="llave-cab"><div class="ic-grande">${icono("llave")}</div><div><h2>Correspondencia nº de caso ↔ paciente</h2>
      <p>${d.local ? "Se guarda <b>solo en este navegador</b>, nunca en la carpeta compartida. Haga copias con el botón de abajo en un sitio privado (USB cifrado o carpeta personal de data manager)."
        : "Este archivo es lo único que permite saber quién es cada caso. Se guarda <b>aparte</b> de la base del registro, idealmente en un USB cifrado que solo tienen los data managers. Nunca se exporta."}</p></div>
      ${d.local ? `<div style="margin-left:auto;display:flex;gap:8px;flex-wrap:wrap"><button class="btn" id="llGuardar" style="background:rgba(255,255,255,.12);color:#fff;border-color:rgba(255,255,255,.25)">${icono("exportar")} Guardar copia</button>
        <label class="btn" style="background:rgba(255,255,255,.12);color:#fff;border-color:rgba(255,255,255,.25)">${icono("importar")} Cargar copia<input type="file" id="llCargar" accept=".xlsx" hidden></label></div>` : ""}</div>`;
    if (!d.disponible) {
      cont.innerHTML = `${cab}<div class="tarjeta pad"><h3>${icono("aviso")} Libro llave no disponible</h3>
        <p class="sub">No se encuentra la carpeta <code class="codigo">${esc(d.ruta)}</code>. Conecte el USB o arranque el servidor indicando la ruta:</p>
        <pre class="vista-anon">python servidor.py --llave E:\\llave\\llave.sqlite</pre></div>`;
      return;
    }
    cont.innerHTML = `${cab}
      <div class="grid g2" style="grid-template-columns:1.6fr 1fr">
        <div class="tarjeta pad">
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:14px"><h3 style="margin:0">Pacientes registrados <span class="sub">(${d.total})</span></h3>
            <div class="buscador" style="margin-left:auto">${icono("buscar")}<input id="ql" placeholder="Buscar CIP, CARM, NHC o nº…" value="${esc(q)}"></div></div>
          <table class="tabla compacta"><thead><tr><th>Caso</th><th>CIP</th><th>CARM</th><th>NHC</th><th>Alta</th><th></th></tr></thead><tbody>
          ${d.filas.map((f) => { const v = ver.has(f.numero); return `<tr style="cursor:default"><td><a class="num-caso" href="#/caso/${f.numero}">#${pad(f.numero)}</a></td>
            <td class="codigo">${esc(v ? f.cip || "—" : enmascarar(f.cip))}</td><td class="codigo">${esc(v ? f.carm || "—" : enmascarar(f.carm))}</td><td class="codigo">${esc(v ? f.nhc || "—" : enmascarar(f.nhc))}</td>
            <td class="quien">${esc(fmtFecha(f.creado))}<small>${esc(f.creado_por || "")}</small></td>
            <td><button class="btn fantasma btn-icono pequeno" data-ver="${f.numero}" title="Mostrar / ocultar">${icono("ojo")}</button></td></tr>`; }).join("") || `<tr><td colspan="6" class="vacio">Sin resultados</td></tr>`}
          </tbody></table>
        </div>
        <div class="tarjeta pad">
          ${asignado ? `<div class="numero-asignado"><div class="sub">Número de caso asignado</div><div class="n">#${pad(asignado)}</div>
            <a class="btn primario grande" href="#/nuevo?n=${asignado}" style="margin-top:10px">${icono("mas")} Crear el caso ahora</a>
            <div class="sub" style="margin-top:10px">Entregue este número (y solo este) a quien vaya a introducir los datos.</div>
            <button class="btn fantasma" id="llOtro" style="margin-top:8px">${icono("mas")} Dar de alta otro paciente</button></div>`
          : `<h3>Dar de alta un paciente</h3><div class="sub" style="margin-bottom:16px">Se le asignará el siguiente número de caso libre.</div>
          <form class="form" id="fl"><label>CIP autonómico<input class="inp" name="cip" autocomplete="off"></label>
            <label>CARM<input class="inp" name="carm" autocomplete="off"></label><label>NHC<input class="inp" name="nhc" autocomplete="off"></label>
            <label>Notas (opcional)<input class="inp" name="notas" autocomplete="off"></label><div class="error" id="errL"></div>
            <button class="btn primario grande">${icono("llave")} Asignar número de caso</button></form>`}
        </div></div>`;
    $("#llOtro")?.addEventListener("click", () => pintar());
    $("#llGuardar")?.addEventListener("click", () => L.exportarLlave());
    $("#llCargar")?.addEventListener("change", async (ev) => {
      try { const n = await L.importarLlave(ev.target.files[0]); toast(`${n} pacientes añadidos al libro llave`); pintar(); } catch (e) { toast(e.message, "mal"); }
    });
    const ql = $("#ql");
    ql.onkeydown = (e) => { if (e.key === "Enter") { q = ql.value.trim(); pintar(); } };
    $$("[data-ver]", cont).forEach((b) => (b.onclick = () => { const n = +b.dataset.ver; ver.has(n) ? ver.delete(n) : ver.add(n); pintar(asignado); }));
    $("#fl")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try { const r = await api("POST", "llave", Object.fromEntries(new FormData(ev.target))); toast(`Asignado el caso #${pad(r.numero)}`); pintar(r.numero); }
      catch (e) { $("#errL").textContent = e.message; }
    });
  };
  await pintar();
}

// ===========================================================================
//  EXPORTAR
// ===========================================================================
// ===========================================================================
//  AUDITORÍA DE LA IA: acierto por variable, detalle por caso y pistas clínicas
// ===========================================================================
/** Texto del valor actual de una pregunta en un caso (para comparar con lo que propuso la IA). */
function valorActualTexto(it, v, caso) {
  if (it.codigo === "_diagnosticos") return caso ? diagnosticosTexto(caso) : "";
  const m = v[it.codigo];
  if (m === NC) return "Desconocido";
  if (m === DUDA) return "Duda";
  const f = (x) => (x ? " · " + isoAFecha(x) : "");
  switch (it.tipoCampo) {
    case "sino": case "sinofecha": return m === 1 ? "Sí" + f(v[it.codigo + "_date"]) : m === 0 ? "No" : "";
    case "single": { const o = it.opciones.find((x) => v[x.codigo] === 1); return o ? o.etiqueta + f(v[o.codigo + "_date"]) : ""; }
    case "multi": return it.opciones.filter((x) => v[x.codigo] === 1).map((x) => x.etiqueta + f(v[x.codigo + "_date"])).join(", ");
    case "fecha": return isoAFecha(m);
    case "numero": case "entero": return m == null ? "" : String(m).replace(".", ",") + (it.unidad ? " " + it.unidad : "");
    default: return m == null ? "" : String(m);
  }
}
const ESTADO_AUD = { confirmado: ["Confirmado", "#16a34a"], corregido: ["Corregido", "#d97706"], quitado: ["Quitado", "#dc2626"], olvido: ["La IA no lo vio", "#7c3aed"],
  pendiente: ["Sin revisar", "#64748b"], revisado: ["Revisado", "#16a34a"] };

async function pAuditoria() {
  barra("Auditoría de la IA", NOMBRE_ROL[S.yo.rol] || "", `<button class="btn" id="audX">${icono("exportar")} Excel</button>`);
  await cargarCasos();
  let pistas = {};
  try { pistas = (await api("GET", "pistas")).pistas || {}; } catch { /* registro sin pistas */ }
  const A = auditar(S.modelo.items, S.casos);
  const F = { ver: "actividad", pest: "", q: "" };
  const cont = $("#contenido");
  const pistaDe = (it) => (it.codigo in pistas ? pistas[it.codigo] : it.pista || "");
  const tot = A.filas.reduce((t, f) => { for (const k of ["propuestos", "pendiente", "confirmado", "corregido", "quitado", "olvidos", "avisos"]) t[k] += f[k]; return t; },
    { propuestos: 0, pendiente: 0, confirmado: 0, corregido: 0, quitado: 0, olvidos: 0, avisos: 0 });
  const juzgados = tot.confirmado + tot.corregido + tot.quitado;
  const pct = (x) => (x == null ? "—" : Math.round(100 * x) + " %");

  const pintar = () => {
    const filas = A.filas.filter((f) => (F.ver === "todas" || (F.ver === "problemas" ? f.problemas > 0 : F.ver === "pista" ? !!pistaDe(f.it) : f.propuestos + f.olvidos > 0))
      && (!F.pest || f.it.pestana === F.pest) && (!F.q || (f.it.etiqueta + " " + f.it.codigo).toLowerCase().includes(F.q.toLowerCase())))
      .sort((a, b) => b.problemas - a.problemas || (a.acierto ?? 2) - (b.acierto ?? 2) || b.propuestos - a.propuestos);
    cont.innerHTML = `
      <div class="aviso-local">${icono("info")}<div><b>¿Qué tal acierta la IA en cada variable?</b> Se compara lo que propuso con lo que ha quedado después de que una persona lo revise.
        Si una variable falla a menudo, abra su fila, mire los casos y escriba una <b>pista clínica</b>: la IA la tendrá en cuenta la próxima vez (en el Mac: «Repetir solo unas variables»).</div></div>
      <div class="grid g-aud" style="margin-bottom:18px">
        <div class="tarjeta kpi"><div class="ic">${icono("casos")}</div><div><div class="v">${A.casosIA}</div><div class="e">casos con datos de la IA</div></div></div>
        <div class="tarjeta kpi"><div class="ic">${icono("chispa")}</div><div><div class="v">${tot.propuestos}</div><div class="e">datos propuestos · ${tot.pendiente} sin revisar</div></div></div>
        <div class="tarjeta kpi"><div class="ic">${icono("check")}</div><div><div class="v">${pct(juzgados ? tot.confirmado / juzgados : null)}</div><div class="e">acierto (de ${juzgados} revisados con detalle)</div></div></div>
        <div class="tarjeta kpi"><div class="ic">${icono("aviso")}</div><div><div class="v">${tot.corregido + tot.quitado}</div><div class="e">corregidos o quitados</div></div></div>
        <div class="tarjeta kpi"><div class="ic">${icono("ojo")}</div><div><div class="v">${tot.olvidos}</div><div class="e">datos que la IA no vio</div></div></div>
      </div>
      <div class="filtros">
        <div class="buscador">${icono("buscar")}<input id="audQ" placeholder="Buscar variable…" value="${esc(F.q)}"></div>
        ${[["actividad", "Con datos"], ["problemas", "Con fallos"], ["pista", "Con pista"], ["todas", "Todas"]].map(([k, t]) => `<span class="chip ${F.ver === k ? "on" : ""}" data-ver="${k}">${t}</span>`).join("")}
        <select class="inp" id="audP" style="width:auto;height:36px"><option value="">Todas las pestañas</option>${S.modelo.pestanas.map((p) => `<option ${F.pest === p ? "selected" : ""}>${esc(p)}</option>`).join("")}</select>
      </div>
      <div class="tarjeta" style="overflow-x:auto">${filas.length ? `<table class="tabla tabla-aud"><thead><tr><th>Variable</th><th title="Casos en los que la IA propuso un dato">Propuestas</th><th>Sin revisar</th>
          <th title="La persona lo dio por bueno">Confirmadas</th><th title="La persona cambió el valor">Corregidas</th><th title="La persona borró el dato">Quitadas</th>
          <th title="La IA no propuso nada y una persona anotó un dato positivo">No lo vio</th><th>Acierto</th><th>Pista clínica</th></tr></thead><tbody>
        ${filas.map((f) => `<tr data-k="${esc(f.it.codigo)}" class="${f.acierto != null && f.acierto < 0.8 && f.confirmado + f.corregido + f.quitado >= 3 ? "mal" : ""}">
          <td><b>${esc(f.it.etiqueta)}</b><small>${esc(f.it.pestana.replace(/^\d+\.\s*/, ""))} · <span class="codigo">${esc(f.it.codigo)}</span></small></td>
          <td>${f.propuestos}${f.avisos ? ` <span class="pill sec" style="--c:#d97706" title="Con aviso automático">${f.avisos}</span>` : ""}</td><td>${f.pendiente || ""}</td>
          <td class="ok">${f.confirmado + f.revisado || ""}</td><td class="warn">${f.corregido || ""}</td><td class="bad">${f.quitado || ""}</td><td class="ia">${f.olvidos || ""}</td>
          <td>${f.acierto == null ? `<span class="sub">—</span>` : `<div class="barra-aud" title="${f.confirmado} de ${f.confirmado + f.corregido + f.quitado}"><i style="width:${Math.round(100 * f.acierto)}%"></i><span>${pct(f.acierto)}</span></div>`}</td>
          <td class="pista-celda">${pistaDe(f.it) ? `<span class="${f.it.codigo in pistas ? "del-equipo" : ""}" title="${esc(pistaDe(f.it))}">${icono("editar")} ${esc(pistaDe(f.it))}</span>` : `<span class="sub">${icono("mas")} añadir</span>`}</td></tr>`).join("")}
        </tbody></table>` : `<div class="vacio">${icono("chispa")}<p>${A.casosIA ? "Ninguna variable con estos filtros." : "Todavía no hay casos importados de la IA."}</p></div>`}</div>`;
    $$("[data-ver]", cont).forEach((x) => (x.onclick = () => { F.ver = x.dataset.ver; pintar(); }));
    $("#audP").onchange = (ev) => { F.pest = ev.target.value; pintar(); };
    const q = $("#audQ"); q.oninput = () => { F.q = q.value; const pos = q.selectionStart; pintar(); const n = $("#audQ"); n.focus(); n.setSelectionRange(pos, pos); };
    $$("tr[data-k]", cont).forEach((tr) => (tr.onclick = () => detalle(A.filas.find((f) => f.it.codigo === tr.dataset.k))));
  };

  const detalle = (f) => {
    const it = f.it;
    const cj = cajon(it.etiqueta, `${esc(it.pestana.replace(/^\d+\.\s*/, ""))} · <span class="codigo">${esc(it.codigo)}</span>`, "lupa");
    const casoDe = (n) => S.casos.find((c) => c.numero === n);
    const orden = { quitado: 0, corregido: 1, olvido: 2, pendiente: 3, confirmado: 4, revisado: 5 };
    cj.cuerpo.innerHTML = `
      <div class="form"><label><b>Pista clínica para la IA</b>
        <textarea class="inp" id="pTxt" rows="4" placeholder="Ej.: «Si pone "resto igual" o "resto sin cambios", se mantiene el tratamiento previo».">${esc(pistaDe(it))}</textarea></label>
        <div class="sub">${it.codigo in pistas ? "Escrita por el equipo." : it.pista ? "Pista inicial del diccionario: puede cambiarla." : "Sin pista: escriba cómo quiere que la IA interprete esta variable."}
          Se aplica en la próxima extracción (en el Mac: «Pasar al registro» o «Actualizar pistas», y después ${it.codigo === "_diagnosticos" ? "repetir el caso entero, porque de los diagnósticos depende todo lo demás" : "«Repetir solo unas variables»"}).</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primario" id="pGuardar">${icono("check")} Guardar pista</button>
          ${it.codigo in pistas ? `<button class="btn" id="pRest">${it.pista ? "Volver a la inicial" : "Quitar pista"}</button>` : ""}</div></div>
      <h4 class="tit-det">Casos (${f.detalle.length})</h4>
      ${f.detalle.length ? `<ul class="lista-aud">${[...f.detalle].sort((a, b) => orden[a.estado] - orden[b.estado] || a.numero - b.numero).map((d) => {
        const c = casoDe(d.numero), fin = c ? valorActualTexto(it, c.valores, c) : "";
        const [txt, col] = ESTADO_AUD[d.estado];
        return `<li><div class="cab-aud"><a href="#/caso/${d.numero}" class="num-caso"><small>#</small>${pad(d.numero)}</a><span class="pill sec" style="--c:${col}">${txt}</span>
            <span class="cambio-aud">${d.estado === "olvido" ? `<del>(nada)</del> → <ins>${esc(fin)}</ins>` : d.estado === "confirmado" || d.estado === "pendiente" || d.estado === "revisado" ? `<b>${esc(d.ia)}</b>`
              : `<del>${esc(d.ia)}</del> → <ins>${esc(fin || "(sin dato)")}</ins>`}</span></div>
          ${d.cita ? `<blockquote class="cita-ia">${esc(d.cita)}</blockquote>` : ""}${d.aviso ? `<div class="aviso-ia">${icono("aviso")} ${esc(d.aviso)}</div>` : ""}</li>`;
      }).join("")}</ul>` : `<p class="sub">Ningún caso con datos de la IA en esta variable.</p>`}`;
    cj.pie.remove();
    const guardar = async (cuerpo, msg) => {
      try {
        await api("PUT", "pistas/" + it.codigo, cuerpo);
        if (cuerpo.restaurar) delete pistas[it.codigo]; else pistas[it.codigo] = cuerpo.texto.trim();
        toast(msg); cj.cerrar(); pintar();
      } catch (e) { toast(e.message, "mal"); }
    };
    $("#pGuardar", cj.cuerpo).onclick = () => guardar({ texto: $("#pTxt", cj.cuerpo).value }, "Pista guardada");
    $("#pRest", cj.cuerpo)?.addEventListener("click", () => guardar({ restaurar: true }, "Pista restaurada"));
    $$("a.num-caso", cj.cuerpo).forEach((a) => a.addEventListener("click", () => cj.cerrar()));
  };

  $("#audX").onclick = () => {
    const resumen = [["variable", "codigo", "pestaña", "propuestas", "con_aviso", "sin_revisar", "confirmadas", "corregidas", "quitadas", "la_IA_no_lo_vio", "acierto_%", "pista_clinica", "pista_del_equipo"],
      ...A.filas.filter((f) => f.propuestos + f.olvidos > 0 || pistaDe(f.it)).map((f) => [f.it.etiqueta, f.it.codigo, f.it.pestana, f.propuestos, f.avisos, f.pendiente, f.confirmado + f.revisado, f.corregido, f.quitado, f.olvidos,
        f.acierto == null ? "" : Math.round(100 * f.acierto), pistaDe(f.it), f.it.codigo in pistas ? "Sí" : ""])];
    const det = [["patient_id", "variable", "codigo", "estado", "valor_IA", "valor_final", "aviso", "frase_del_informe"]];
    for (const f of A.filas) for (const d of f.detalle) {
      const c = S.casos.find((x) => x.numero === d.numero);
      det.push([d.numero, f.it.etiqueta, f.it.codigo, ESTADO_AUD[d.estado][0], d.ia, c ? valorActualTexto(f.it, c.valores, c) : "", d.aviso, d.cita]);
    }
    descargar(crearXlsx([["Auditoria_IA", resumen], ["Detalle", det]]), `WILLEM_auditoria_IA_${hoyIso()}.xlsx`);
  };
  pintar();
}

async function pIA() {
  barra("Importar de la IA", "Propuestas de la IA local (Mac)");
  const cont = $("#contenido");
  let props = [];
  const pintar = (resultados) => {
    const existe = (n) => S.casos.find((c) => c.numero === n);
    cont.innerHTML = `
      <div class="tarjeta" style="padding:22px">
        <h2 style="margin-top:0">${icono("chispa")} Propuestas de la IA</h2>
        <p>En el Mac, la IA local lee los informes anonimizados y deja un archivo por caso en <code>WILLEM_anonimizado/propuestas_ia</code>.
          Elija esos archivos (o la carpeta entera) para cargarlos aquí.</p>
        <ul class="sub">
          <li>Si el caso no existe, se crea con los diagnósticos que propone la IA.</li>
          <li>Si existe, solo se rellenan los campos vacíos: <b>nunca se pisa lo que haya escrito una persona</b>. Los casos validados no se tocan.</li>
          <li>Cada dato queda marcado con ${icono("chispa")}<b>IA</b> hasta que alguien lo revisa; no se puede validar un caso con datos de la IA sin revisar.</li>
        </ul>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
          <label class="btn primario">${icono("importar")} Elegir archivos<input type="file" id="iaArch" accept=".json,application/json" multiple hidden></label>
          <label class="btn">${icono("casos")} Elegir carpeta<input type="file" id="iaCarp" webkitdirectory hidden></label>
        </div>
      </div>
      ${props.length ? `<div class="tarjeta" style="margin-top:16px"><table class="tabla"><thead><tr><th>Caso</th><th>Diagnósticos propuestos</th><th>Informes</th><th>Datos</th><th>Con aviso</th><th>En el registro</th></tr></thead><tbody>
        ${props.map((p) => { const c = existe(p.numero_caso); const n = Object.keys(p.ia || {}).length; const av = Object.values(p.ia || {}).filter((x) => x.aviso).length;
          return `<tr><td><span class="num-caso"><small>#</small>${pad(p.numero_caso)}</span></td>
          <td>${(p.diagnosticos || []).map((d) => ENFERMEDADES[d.codigo] ? pillEnf(d.codigo, true) : esc(d.codigo)).join(" ") || '<span class="sub">ninguno</span>'}</td>
          <td>${(p.informes || []).length}</td><td>${n}</td><td>${av ? `<span class="pill sec" style="--c:#d97706">${av}</span>` : "0"}</td>
          <td>${c ? (c.estado === "validado" ? '<span class="sub">validado: no se toca</span>' : "ya existe: se completa") : "<b>nuevo</b>"}</td></tr>`; }).join("")}
        </tbody></table>
        <div style="padding:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><button class="btn primario grande" id="iaImportar">${icono("chispa")} Importar ${props.length} caso${props.length > 1 ? "s" : ""}</button>
          <span class="sub">Los textos de los informes (anonimizados) se guardan con cada caso para poder revisarlos.</span></div></div>` : ""}
      ${resultados ? `<div class="tarjeta" style="margin-top:16px;padding:16px"><h3 style="margin-top:0">Resultado</h3><ul class="lista-res">${resultados.map((r) => `<li>${r.numero ? `<a href="#/caso/${r.numero}">Caso #${pad(r.numero)}</a>` : "—"}:
          <b>${{ creado: "creado", actualizado: "completado", omitido: "no importado" }[r.accion] || r.accion}</b>${r.aplicados ? ` · ${r.aplicados} datos` : ""}${r.omitidos ? ` · ${r.omitidos} campos ya rellenos por una persona (no se tocan)` : ""}${r.motivo ? ` · ${esc(r.motivo)}` : ""}</li>`).join("")}</ul>
          <a class="btn" href="#/casos?ia=1">${icono("chispa")} Ver los casos con datos de la IA por revisar</a></div>` : ""}`;
    const leer = async (files) => {
      const nuevas = [];
      for (const f of files) {
        if (!/caso_\d+\.json$/i.test(f.name)) continue;
        try { const p = JSON.parse(await f.text()); if (p.formato === "willem-propuesta-ia/1") nuevas.push(p); } catch { /* no es JSON */ }
      }
      if (!nuevas.length) return toast("No hay archivos de propuestas de la IA (caso_XXXX.json) en lo elegido", "mal");
      props = nuevas.sort((a, b) => a.numero_caso - b.numero_caso);
      pintar();
    };
    $("#iaArch").onchange = (ev) => leer([...ev.target.files]);
    $("#iaCarp").onchange = (ev) => leer([...ev.target.files]);
    $("#iaImportar")?.addEventListener("click", async () => {
      try {
        const r = await api("POST", "ia/importar", { propuestas: props });
        props = [];
        await cargarCasos();
        toast("Propuestas importadas");
        pintar(r.resultados);
      } catch (e) { toast(e.message, "mal"); }
    });
  };
  await cargarCasos();
  pintar();
}

async function pExportar() {
  barra("Exportar al registro", "Data manager");
  const [casos, cols] = await Promise.all([cargarCasos(), api("GET", "columnas")]);
  const val = casos.filter((c) => c.estado === "validado").length;
  $("#contenido").innerHTML = `
    <div class="grid g3" style="margin-bottom:18px">
      <div class="tarjeta kpi"><div class="ic">${icono("casos")}</div><div><div class="v">${casos.length}</div><div class="e">Casos (filas)</div></div></div>
      <div class="tarjeta kpi"><div class="ic">${icono("escudo")}</div><div><div class="v">${val}</div><div class="e">Validados</div></div></div>
      <div class="tarjeta kpi"><div class="ic">${icono("codigo")}</div><div><div class="v">${cols.registro.length}</div><div class="e">Columnas del registro</div></div></div>
    </div>
    <div class="grid g2">
      <div class="tarjeta pad"><h3>Descargar</h3><div class="sub" style="margin-bottom:16px">Una fila por paciente; columnas con los nombres del registro (en inglés). Sí = 1, No = 0, vacío = no consta.</div>
        <label style="display:flex;gap:8px;align-items:center;margin-bottom:18px"><input type="checkbox" id="soloVal"> Solo casos validados</label>
        <div style="display:flex;gap:10px;flex-wrap:wrap"><a class="btn primario grande" id="dX" href="api/exportar/xlsx">${icono("exportar")} Excel (.xlsx)</a>
        <a class="btn grande" id="dC" href="api/exportar/csv">${icono("exportar")} CSV</a></div>
        <div class="aviso-local" style="margin-top:18px">${icono("info")}<div>El Excel incluye una segunda hoja <b>Solo_local_NO_ENVIAR</b> con las variables propias que no pide el registro (si las hay). Bórrela antes de enviar.</div></div>
      </div>
      <div class="tarjeta pad"><h3>Columnas</h3><div class="sub" style="margin-bottom:12px">${cols.registro.length} del registro${cols.local.length ? ` · <span style="color:var(--warn)">${cols.local.length} solo locales</span>` : ""}</div>
        <div class="cols-prev">${cols.registro.map((c) => `<span>${esc(c)}</span>`).join("")}${cols.local.map((c) => `<span class="local">${esc(c)}</span>`).join("")}</div></div>
    </div>`;
  $("#soloVal").onchange = (e) => { const s = e.target.checked ? "?validados=1" : ""; $("#dX").href = "api/exportar/xlsx" + s; $("#dC").href = "api/exportar/csv" + s; };
  if (navegador()) {
    for (const [id, f] of [["#dX", "xlsx"], ["#dC", "csv"]]) $(id).onclick = (ev) => { ev.preventDefault(); L.exportarRegistro($("#soloVal").checked, f); };
  }
}

// ===========================================================================
//  USUARIOS
// ===========================================================================
async function pUsuarios() {
  barra("Usuarios", "Data manager", `<button class="btn primario" id="bNU">${icono("mas")} Nuevo usuario</button>`);
  const us = await api("GET", "usuarios");
  $("#contenido").innerHTML = `<div class="tarjeta"><table class="tabla"><thead><tr><th>Persona</th><th>Usuario</th><th>Rol</th><th>Estado</th>${navegador() ? "" : "<th>Doble factor</th>"}<th>Alta</th><th></th></tr></thead><tbody>
    ${us.map((u) => `<tr style="cursor:default"><td><div style="display:flex;gap:10px;align-items:center"><span class="avatar" style="background:${colorDe(u.usuario)}">${esc(iniciales(u.nombre))}</span><b>${esc(u.nombre)}</b></div></td>
      <td class="codigo">${esc(u.usuario)}</td><td><span class="pill" style="--c:${COLOR_ROL[u.rol] || "#0f766e"}">${NOMBRE_ROL[u.rol] || esc(u.rol)}</span></td>
      <td>${u.activo ? `<span class="estado validado">Activo</span>` : `<span class="estado borrador">Desactivado</span>`}${u.bloqueado_hasta ? ` <span class="pill sec" style="--c:#dc2626">${icono("candado")} Bloqueado</span>` : ""}</td>
      ${navegador() ? "" : `<td>${u.doble_factor ? `<span class="pill sec" style="--c:#16a34a">${icono("escudo")} Activado</span>` : `<span class="sub">${S.info?.doble_factor ? "Se configurará al entrar" : "No"}</span>`}</td>`}
      <td class="quien">${esc(fmtFecha(u.creado))}</td>
      <td style="text-align:right;white-space:nowrap">${u.id !== S.yo.id ? `<button class="btn pequeno" data-rol="${u.id}" data-r="${u.rol}">Cambiar rol</button> <button class="btn pequeno" data-act="${u.id}" data-a="${u.activo}">${u.activo ? "Desactivar" : "Activar"}</button>` : ""}
        <button class="btn pequeno" data-pw="${u.id}">Contraseña</button>
        ${u.doble_factor ? `<button class="btn pequeno" data-2fa="${u.id}" data-n="${esc(u.nombre)}" title="Si ha perdido o cambiado el móvil">Reiniciar doble factor</button>` : ""}
        ${u.bloqueado_hasta ? `<button class="btn pequeno" data-desb="${u.id}">Desbloquear</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
  const recargar = () => pUsuarios();
  $("#bNU").onclick = () => modal({
    titulo: "Nuevo usuario", aceptar: "Crear",
    html: `<form class="form" onsubmit="return false"><label>Nombre y apellidos<input class="inp" id="un"></label><div class="fila"><label>Usuario<input class="inp" id="uu"></label>
      <label>Rol<select class="inp" id="ur"><option value="intro">Introducción de datos</option><option value="rev">Cardiólogo revisor</option><option value="dm">Data manager</option></select></label></div>
      <label>Contraseña inicial (mín. 8)<input class="inp" id="up" type="password"></label>
      <div class="sub">Désela en persona o por un canal seguro, y pídale que la cambie al entrar (icono de la llave, junto a su nombre).</div><div class="error"></div></form>`,
    alAceptar: async (m) => { await api("POST", "usuarios", { nombre: $("#un", m).value, usuario: $("#uu", m).value, rol: $("#ur", m).value, clave: $("#up", m).value }); toast("Usuario creado"); recargar(); },
  });
  $$("[data-act]").forEach((b) => (b.onclick = async () => { try { await api("PUT", "usuarios/" + b.dataset.act, { activo: b.dataset.a !== "1" }); recargar(); } catch (e) { toast(e.message, "mal"); } }));
  $$("[data-rol]").forEach((b) => (b.onclick = () => modal({
    titulo: "Cambiar el perfil", aceptar: "Guardar",
    html: `<form class="form" onsubmit="return false"><label>Perfil<select class="inp" id="cr">${["intro", "rev", "dm"].map((r) => `<option value="${r}" ${r === b.dataset.r ? "selected" : ""}>${NOMBRE_ROL[r]}</option>`).join("")}</select></label>
      <div class="sub"><b>Introducción de datos:</b> crea y rellena casos.<br><b>Cardiólogo revisor:</b> además revisa, corrige y valida casos, y ve la auditoría de la IA.<br><b>Data manager:</b> además importa de la IA, exporta, borra casos y gestiona usuarios.</div><div class="error"></div></form>`,
    alAceptar: async (m) => { await api("PUT", "usuarios/" + b.dataset.rol, { rol: $("#cr", m).value }); toast("Perfil cambiado"); recargar(); },
  })));
  $$("[data-2fa]").forEach((b) => (b.onclick = async () => {
    if (!(await modal({ titulo: "Reiniciar el doble factor", aceptar: "Reiniciar", peligro: true,
      html: `<p><b>${esc(b.dataset.n)}</b> tendrá que volver a configurar la aplicación de códigos la próxima vez que entre (por ejemplo, porque ha cambiado de móvil).</p><p class="sub">Se cerrarán sus sesiones abiertas.</p>` }))) return;
    try { await api("PUT", "usuarios/" + b.dataset["2fa"], { reiniciar_2fa: true }); toast("Doble factor reiniciado"); recargar(); } catch (e) { toast(e.message, "mal"); }
  }));
  $$("[data-desb]").forEach((b) => (b.onclick = async () => { try { await api("PUT", "usuarios/" + b.dataset.desb, { desbloquear: true }); toast("Usuario desbloqueado"); recargar(); } catch (e) { toast(e.message, "mal"); } }));
  $$("[data-pw]").forEach((b) => (b.onclick = () => modal({
    titulo: "Cambiar contraseña", aceptar: "Guardar", html: `<form class="form" onsubmit="return false"><label>Nueva contraseña (mín. 8)<input class="inp" id="np" type="password"></label><div class="error"></div></form>`,
    alAceptar: async (m) => { await api("PUT", "usuarios/" + b.dataset.pw, { clave: $("#np", m).value }); toast("Contraseña cambiada"); },
  })));
}

// ===========================================================================
//  DICCIONARIO
// ===========================================================================
async function pDiccionario() {
  barra("Diccionario de variables", "Referencia");
  const M = S.modelo;
  let q = "", g = "";
  const filas = [];
  for (const it of M.items) {
    filas.push({ it, codigo: it.codigo, etiqueta: it.etiqueta, tipo: it.tipoCampo, grupos: it.grupos, cond: it.condTexto, padre: null });
    for (const o of it.opciones || []) filas.push({ it: o, codigo: o.codigo, etiqueta: o.etiqueta, tipo: "opción", grupos: it.grupos, cond: "", padre: it.etiqueta });
  }
  const TIPOS = { sino: "Sí/No", sinofecha: "Sí/No + fecha", single: "Una opción", multi: "Varias opciones", numero: "Número", entero: "Entero", fecha: "Fecha", texto: "Texto", fijo: "Fijo", caso: "Nº caso", auto: "Automático", "opción": "↳ opción" };
  const cont = $("#contenido");
  const pintar = () => {
    const lista = filas.filter((f) => (!g || f.grupos.includes(g)) && (!q || (f.codigo + " " + f.etiqueta + " " + (f.padre || "")).toLowerCase().includes(q.toLowerCase())));
    cont.innerHTML = `<div class="aviso-local">${icono("info")}<div>El formulario se construye leyendo <b>diccionario/diccionario_maestro.xlsx</b> (cargado ${esc(M.cargado?.replace("T", " ") || "")}). Para cambiar textos, rangos o qué campos ve cada enfermedad, edite ese Excel y recargue la página.</div></div>
      <div class="filtros"><div class="buscador">${icono("buscar")}<input id="qd" placeholder="Buscar variable…" value="${esc(q)}"></div>
        <span class="chip ${!g ? "on" : ""}" data-gg="">Todas</span><span class="chip ${g === "COMUN" ? "on" : ""}" data-gg="COMUN">Comunes</span>
        ${Object.keys(ENFERMEDADES).map((k) => `<span class="chip ${g === k ? "on" : ""}" data-gg="${k}" style="--c:${ENFERMEDADES[k].color}">${icono(k)} ${esc(ENFERMEDADES[k].corto)}</span>`).join("")}</div>
      <div class="tarjeta"><table class="tabla compacta"><thead><tr><th>Código</th><th>Texto en pantalla</th><th>Tipo</th><th>Se muestra en</th><th>Condición</th></tr></thead><tbody>
      ${lista.map((f) => `<tr style="cursor:default"><td class="codigo">${esc(f.codigo)}${f.it.provisional ? ` <span class="prov">PROV</span>` : ""}</td>
        <td>${f.padre ? `<span class="sub">${esc(f.padre)} › </span>` : ""}${esc(f.etiqueta)}</td><td class="sub">${TIPOS[f.tipo] || f.tipo}</td>
        <td>${f.grupos.map((x) => `<span class="tag-g" style="--c:${ENFERMEDADES[x]?.color || "var(--ink-3)"}">${x === "COMUN" ? "Común" : esc(ENFERMEDADES[x]?.corto || x)}</span>`).join("")}</td>
        <td class="codigo sub">${esc(f.cond)}</td></tr>`).join("")}</tbody></table></div>`;
    const qd = $("#qd");
    qd.oninput = () => { q = qd.value; const p = qd.selectionStart; pintar(); const n = $("#qd"); n.focus(); n.setSelectionRange(p, p); };
    $$("[data-gg]", cont).forEach((x) => (x.onclick = () => { g = x.dataset.gg; pintar(); }));
  };
  pintar();
}

// ===========================================================================
//  ENVÍO AL REGISTRO (Excel corporativo, Office 365 de la CARM)
// ===========================================================================
function pillEnvio(c) {
  const p = ENV.pendienteDeEnvio(S.dic, c);
  if (p === "nunca") return `<span class="sub">—</span>`;
  if (p === "cambios") return `<span class="pill sec" style="--c:#d97706" title="Se ha modificado después de enviarlo">${icono("enviar")} Cambios sin enviar</span>`;
  return `<span class="pill sec" style="--c:#16a34a" title="Enviado ${esc(fmtFecha(c.valores.registro_enviado))}">${icono("check")} Enviado</span>`;
}

function botonEnvio(c) {
  const p = ENV.pendienteDeEnvio(S.dic, c);
  const txt = p === "nunca" ? "Enviar al registro" : p === "cambios" ? "Reenviar cambios" : "Enviado";
  const tit = p === "" ? `Enviado ${relativo(c.valores.registro_enviado)} por ${c.valores.registro_enviado_por || ""}. Pulse para volver a enviar.` : "Escribe este caso en el Excel corporativo del registro";
  return `<button class="btn btn-envio ${p === "" ? "enviado" : p === "cambios" ? "cambios" : ""}" id="bEnviar" title="${esc(tit)}">${icono(p === "" ? "check" : "enviar")} ${txt}</button>`;
}

async function enviarAlRegistro(caso, { silencioso = false } = {}) {
  await vaciarPendientes();
  const est = await ENV.estadoEnvio();
  if (!est.ok) {
    if (silencioso) throw new Error(est.motivo);
    return modal({ titulo: "No se puede enviar todavía", cancelar: null, aceptar: "Entendido",
      html: `<p>${esc(est.motivo)}</p>${est.sinConfig ? `<p class="sub">${esDM() ? `Configúrelo en <a href="#/envio">Envío al registro</a>.` : "Avise a un data manager."}</p>` : ""}
        <p class="sub">Mientras tanto el caso está a salvo: se guarda en este ordenador y en la carpeta compartida.</p>` });
  }
  const dudas = dudasDelCaso(S.modelo, caso);
  if (dudas.length) {
    if (silencioso) throw new Error("tiene dudas sin resolver");
    return toast(`No se puede enviar: hay ${dudas.length} duda${dudas.length > 1 ? "s" : ""} sin resolver`, "mal");
  }
  const prog = progresoCaso(S.modelo, caso);
  if (!silencioso && prog.pct < 100) {
    const ok = await modal({ titulo: "El caso no está completo", aceptar: "Enviar igualmente",
      html: `<p>Faltan <b>${prog.tot - prog.ok}</b> preguntas por contestar (${prog.pct}% completado). Las que falten irán en blanco.</p><p class="sub">Podrá volver a enviarlo cuando lo complete: se actualizará la misma fila.</p>` });
    if (!ok) return;
  }
  const b = $("#bEnviar");
  if (b) { b.disabled = true; b.innerHTML = `${icono("historial")} Enviando…`; }
  try {
    const r = await ENV.enviarCaso(S.dic, caso);
    const act = await api("PUT", "casos/" + caso.numero, { valores: { registro_enviado: r.fecha, registro_huella: r.huella, registro_enviado_por: S.yo.usuario } });
    if (E.caso?.numero === caso.numero) { E.caso = act; pintarCaso(); }
    if (!silencioso) toast(`Caso #${pad(caso.numero)} ${r.accion === "añadido" ? "enviado" : "actualizado"} en el registro`);
    return r;
  } catch (e) {
    if (silencioso) throw e;
    toast("No se ha podido enviar: " + e.message, "mal");
    if (E.caso?.numero === caso.numero) pintarCaso();
  }
}

async function pEnvio() {
  barra("Envío al registro", "Data manager");
  const pintar = async (resultado) => {
    const est = await ENV.estadoEnvio();
    const c = est.conf || {};
    await cargarCasos();
    const listos = S.casos.filter((x) => x.estado !== "borrador" && !x.dudas.length && ENV.pendienteDeEnvio(S.dic, x));
    const cuenta = await ENV.cuentaActual();
    $("#contenido").innerHTML = `
      <div class="aviso-local">${icono("candado")}<div><b>Cómo funciona.</b> Cada persona inicia sesión con <b>su cuenta del SMS</b> y la aplicación escribe la fila del caso en el Excel corporativo, con el formato final del registro.
        Los datos van del navegador directamente al Office 365 de la CARM. La aplicación nunca ve contraseñas.</div></div>
      <div class="grid g2" style="grid-template-columns:1.1fr 1fr;align-items:start">
        <div class="tarjeta pad">
          <h3>Estado</h3>
          <div class="sub" style="margin:6px 0 14px">${est.ok ? `${icono("check")} Listo para enviar${cuenta ? ` · sesión: <b>${esc(cuenta.username)}</b>` : ""}` : esc(est.motivo)}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn primario" id="eProbar" ${est.ok ? "" : "disabled"}>${icono("nube")} Probar conexión</button>
            <button class="btn" id="eTodos" ${est.ok && listos.length ? "" : "disabled"}>${icono("enviar")} Enviar pendientes (${listos.length})</button>
          </div>
          <div class="sub" style="margin-top:10px">"Pendientes" = casos completos o validados, sin dudas, que no se han enviado o han cambiado desde el último envío.</div>
          <div id="eRes">${resultado || ""}</div>
        </div>
        <div class="tarjeta pad">
          <h3>Configuración</h3>
          <div class="sub" style="margin-bottom:12px">Los datos de la aplicación registrada por Informática y el enlace del Excel. Lo ideal es dejarlos en el archivo central <code>datos/envio.json</code> para que valgan para todos; aquí puede probarlos en este navegador.</div>
          <form class="form" id="fEnv" onsubmit="return false">
            <label>Id. de aplicación (cliente)<input class="inp" name="clientId" value="${esc(c.clientId || "")}" placeholder="00000000-0000-0000-0000-000000000000"></label>
            <label>Id. de directorio (inquilino)<input class="inp" name="tenantId" value="${esc(c.tenantId || "")}" placeholder="00000000-0000-0000-0000-000000000000"></label>
            <label>Enlace del Excel corporativo<input class="inp" name="excelUrl" value="${esc(c.excelUrl || "")}" placeholder="https://comunidaddemurcia.sharepoint.com/..."></label>
            <label>Nombre de la tabla<input class="inp" name="tabla" value="${esc(c.tabla || "WILLEM")}"></label>
            <div class="sub">Dirección de retorno que debe estar registrada en la aplicación: <code>${esc(new URL("auth.html", location.href).href)}</code></div>
            <button class="btn" id="eGuardar">${icono("check")} Guardar en este navegador</button>
          </form>
        </div>
      </div>`;
    $("#eGuardar").onclick = () => {
      const f = Object.fromEntries(new FormData($("#fEnv")));
      ENV.guardarConfigLocal(f); toast("Configuración guardada en este navegador"); pintar();
    };
    $("#eProbar").onclick = async () => {
      try {
        const r = await ENV.probarConexion(S.dic);
        pintar(`<div class="aviso-local" style="margin-top:14px">${icono("check")}<div>Conexión correcta como <b>${esc(r.cuenta || "")}</b>. Excel: <b>${esc(r.excel)}</b>, con la tabla preparada.</div></div>`);
      } catch (e) { toast(e.message, "mal"); }
    };
    $("#eTodos").onclick = async (ev) => {
      ev.target.disabled = true;
      const filas = [];
      for (const x of listos) {
        try { const r = await enviarAlRegistro(x, { silencioso: true }); filas.push(`<li>${icono("check")} #${pad(x.numero)} ${r.accion}</li>`); }
        catch (e) { filas.push(`<li style="color:var(--bad)">${icono("aviso")} #${pad(x.numero)}: ${esc(e.message)}</li>`); }
      }
      pintar(`<ul class="lista-envio">${filas.join("")}</ul>`);
    };
  };
  await pintar();
}

// ===========================================================================
//  NOTA DE REVISIÓN (★): texto libre por paciente para que lo revise el equipo
// ===========================================================================
const tieneNota = (c) => !!String(c?.valores?.nota_revision || "").trim();

function botonNota(c) {
  const on = tieneNota(c);
  return `<button class="btn btn-estrella ${on ? "on" : ""}" id="bNota" title="${on ? "Tiene nota de revisión: pulse para verla" : "Añadir una nota para que el equipo revise este paciente"}">${icono("estrella")}${on ? " Para revisar" : ""}</button>`;
}

async function editarNota() {
  const c = E.caso;
  let texto = c.valores.nota_revision || "";
  await modal({
    titulo: `Nota de revisión · caso #${pad(c.numero)}`, aceptar: "Guardar nota",
    html: `<p class="sub" style="margin-top:0">Escriba aquí cualquier duda sobre este paciente para que la revise el equipo. Mientras haya texto, la estrella queda encendida y el caso aparece en el filtro «Para revisar».</p>
      <textarea class="inp nota-larga" id="notaTxt" rows="9" placeholder="Por ejemplo: el informe de alta y el de la eco no coinciden en la FEVI; ¿qué fecha de diagnóstico usamos?">${esc(texto)}</textarea>
      ${texto ? `<button class="btn fantasma peligro" id="notaBorrar" style="margin-top:8px">${icono("papelera")} Borrar la nota (revisado)</button>` : ""}`,
    alAbrir: (m) => {
      const t = $("#notaTxt", m); t.focus(); t.setSelectionRange(t.value.length, t.value.length);
      $("#notaBorrar", m)?.addEventListener("click", () => { t.value = ""; m.querySelector("[data-ok]").click(); });
    },
    alAceptar: async (m) => {
      const nuevo = $("#notaTxt", m).value.trim();
      if (nuevo !== (c.valores.nota_revision || "")) {
        aplicar({ nota_revision: nuevo || null });
        await vaciarPendientes();
        toast(nuevo ? "Nota guardada: caso marcado para revisión" : "Nota borrada");
      }
    },
  });
}

// ===========================================================================
//  DUDAS PENDIENTES
// ===========================================================================
async function pDudas() {
  barra("Dudas y revisión", "Revisión");
  await cargarCasos();
  const filas = S.casos.flatMap((c) => c.dudas.map((d) => ({ c, d }))).sort((a, b) => a.c.numero - b.c.numero);
  const conNota = S.casos.filter(tieneNota).sort((a, b) => a.numero - b.numero);
  $("#contenido").innerHTML = `<div class="aviso-local">${icono("bandera")}<div>Preguntas marcadas como <b>Duda</b> por quien introdujo los datos. Un caso con dudas abiertas <b>no se puede validar</b>.
      Para resolverla, abra el caso y conteste Sí, No o Desconocido.</div></div>
    <div class="tarjeta">${filas.length ? `<table class="tabla"><thead><tr><th>Caso</th><th>Pregunta</th><th>Pestaña</th><th>Nota de la duda</th><th>Última modificación</th></tr></thead><tbody>
      ${filas.map(({ c, d }) => `<tr data-ir="#/caso/${c.numero}/${encodeURIComponent(d.pestana)}" style="--c:${ENFERMEDADES[c.principal]?.color}">
        <td><span class="num-caso"><small>#</small>${pad(c.numero)}</span><div style="margin-top:4px">${pillEnf(c.principal, true)}</div></td>
        <td><b>${esc(d.etiqueta)}</b><div class="codigo sub">${esc(d.codigo)}</div></td><td class="sub">${esc(d.tituloPestana)}</td>
        <td>${d.nota ? esc(d.nota) : `<span class="sub">— sin nota —</span>`}</td><td class="quien">${relativo(c.modificado)}<small>por ${esc(c.modificado_por)}</small></td></tr>`).join("")}
      </tbody></table>` : `<div class="vacio">${icono("check")}<p>No hay dudas pendientes en preguntas concretas.</p></div>`}</div>
    <div class="bloque-tit" style="margin-top:26px">${icono("estrella")} Pacientes marcados para revisión (${conNota.length})</div>
    <div class="tarjeta">${conNota.length ? `<table class="tabla"><thead><tr><th>Caso</th><th>Nota de revisión</th><th>Última modificación</th></tr></thead><tbody>
      ${conNota.map((c) => `<tr data-ir="#/caso/${c.numero}"><td><span class="num-caso"><small>#</small>${pad(c.numero)}</span> <span class="estrella on">${icono("estrella")}</span>
        <div style="margin-top:4px">${diagnosticosDe(c).map((g) => pillEnf(g, true)).join(" ")}</div></td>
        <td class="texto-nota">${esc(c.valores.nota_revision)}</td><td class="quien">${relativo(c.modificado)}<small>por ${esc(c.modificado_por)}</small></td></tr>`).join("")}
      </tbody></table>` : `<div class="vacio">${icono("estrella")}<p>Ningún paciente marcado con estrella.</p></div>`}</div>`;
  $$("tr[data-ir]").forEach((tr) => (tr.onclick = () => (location.hash = tr.dataset.ir)));
}

// ===========================================================================
//  MODO NAVEGADOR: perfil, carpeta compartida y unión de casos
// ===========================================================================
function pintarPerfil() {
  window.onhashchange = null;
  let rol = "intro";
  $("#raiz").innerHTML = `<div class="login">${heroe()}
    <div class="lado"><form class="caja form" id="fPerfil" autocomplete="off">
      <div><h2>¿Quién va a trabajar en este ordenador?</h2>
        <div class="sub">Sus casos se guardan en este navegador y en la carpeta compartida del SMS. No hay contraseña: el acceso lo protege su sesión de Windows.</div></div>
      <div class="roles">
        <button type="button" class="rol on" data-rol="intro">${icono("editar")}<b>Introducción de datos</b><span>Rellena sus casos</span></button>
        <button type="button" class="rol" data-rol="dm">${icono("escudo")}<b>Data manager</b><span>Libro llave, unir y exportar</span></button>
      </div>
      <label>Nombre y apellidos<input class="inp" name="nombre" required></label>
      <label>Nombre corto (para el archivo)<input class="inp" name="usuario" required placeholder="p. ej. carmen.ruiz"></label>
      <div class="error" id="errP"></div>
      <button class="btn primario grande" style="justify-content:center">Empezar ${icono("flechaD")}</button>
      <button type="button" class="btn fantasma" id="bDemo" style="justify-content:center">${icono("ojo")} Solo quiero probarla con pacientes inventados</button>
    </form></div></div>`;
  const f = $("#fPerfil");
  $$(".rol", f).forEach((b) => (b.onclick = () => { rol = b.dataset.rol; $$(".rol", f).forEach((x) => x.classList.toggle("on", x === b)); }));
  f.nombre.oninput = () => {
    if (f.usuario.dataset.tocado) return;
    f.usuario.value = f.nombre.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim().split(/\s+/).slice(0, 2).join(".").replace(/[^a-z0-9._-]/g, "");
  };
  f.usuario.oninput = () => (f.usuario.dataset.tocado = 1);
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("POST", "configurar", { nombre: f.nombre.value, usuario: f.usuario.value, rol });
      S.info = await api("GET", "estado"); S.yo = S.info.usuario;
      location.hash = (await L.infoCarpeta()).nombre ? "#/panel" : "#/carpeta";
      await entrar();
    } catch (e) { $("#errP").textContent = e.message; }
  };
  $("#bDemo").onclick = async () => {
    try {
      await api("POST", "configurar", { nombre: "Data manager (demo)", usuario: "admin", rol: "dm" });
      if ((await api("GET", "casos")).length === 0) await L.cargarDemo();
      S.info = await api("GET", "estado"); S.yo = S.info.usuario;
      location.hash = "#/panel"; await entrar();
    } catch (e) { $("#errP").textContent = e.message; }
  };
}

async function pintarEstadoCarpeta() {
  const b = $("#estCarpeta");
  if (!b) return;
  const i = await L.infoCarpeta();
  let cls = "mal", ic = "aviso", t1 = "Sin carpeta compartida", t2 = "Pulse para vincularla";
  if (i.nombre && i.permiso !== "granted") { cls = "aviso"; ic = "nube"; t1 = "Carpeta desconectada"; t2 = "Pulse para reconectar"; }
  else if (i.nombre && i.error) { cls = "mal"; ic = "aviso"; t1 = "No se pudo guardar"; t2 = "Pulse para ver el problema"; }
  else if (i.nombre) { cls = "ok"; ic = i.guardando || i.pendiente ? "historial" : "nube"; t1 = i.guardando || i.pendiente ? "Guardando…" : "Guardado en la carpeta"; t2 = `${i.nombre} · ${i.ultimo ? relativo(i.ultimo) : "—"}`; }
  b.className = "estado-carpeta " + cls;
  b.innerHTML = `${icono(ic)}<span><b>${t1}</b><small>${esc(t2)}</small></span>`;
  b.onclick = async () => {
    if (i.nombre && i.permiso !== "granted") { if (await L.reconectarCarpeta()) toast("Carpeta reconectada"); pintarEstadoCarpeta(); }
    else location.hash = "#/carpeta";
  };
}
setInterval(() => navegador() && pintarEstadoCarpeta(), 30000);

async function pCarpeta() {
  barra("Carpeta compartida", "Guardado");
  const pintar = async () => {
    const i = await L.infoCarpeta();
    const pasos = `<ol class="pasos-guia">
      <li><b>En SharePoint</b> (o Teams) del servicio, cree una carpeta, por ejemplo <code>WILLEM_datos</code>, y compártala con edición solo con el equipo del estudio.</li>
      <li>Ábrala en el navegador y pulse <b>Sincronizar</b> (o <b>Agregar acceso directo a Mis archivos</b>). Aparecerá en el Explorador de Windows, bajo <i>Servicio Murciano de Salud</i>.</li>
      <li>Pulse aquí <b>Vincular carpeta</b> y elija esa carpeta. A partir de entonces la aplicación guarda sola su Excel <code>${esc(i.archivo || "")}</code> y OneDrive lo sube con su cuenta del SMS.</li>
      <li>El libro llave <b>nunca</b> va en esta carpeta.</li></ol>`;
    let estado;
    if (!i.soportada) {
      estado = `<div class="tarjeta pad"><h3>${icono("aviso")} Este navegador no puede guardar en carpetas</h3>
        <p class="sub">Use <b>Microsoft Edge</b> o <b>Google Chrome</b>. Mientras tanto, sus casos están en este navegador: descargue una copia y guárdela usted en la carpeta compartida.</p>
        <button class="btn primario" id="cDesc">${icono("exportar")} Descargar mi archivo</button></div>`;
    } else if (!i.nombre) {
      estado = `<div class="tarjeta pad carpeta-cta"><div class="ic-gr">${icono("nube")}</div><div><h3>Vincule la carpeta compartida</h3>
        <p class="sub">Hasta que lo haga, sus casos solo están en este navegador y se perderían si se borra el historial.</p>
        <button class="btn primario grande" id="cElegir">${icono("nube")} Vincular carpeta</button></div></div>`;
    } else {
      const ok = i.permiso === "granted" && !i.error;
      estado = `<div class="tarjeta pad carpeta-cta ${ok ? "ok" : ""}"><div class="ic-gr">${icono(ok ? "check" : "aviso")}</div><div>
        <h3>${ok ? "Guardando automáticamente" : i.permiso !== "granted" ? "Hay que volver a dar permiso" : "Último guardado con error"}</h3>
        <p class="sub">Carpeta: <b>${esc(i.nombre)}</b> · Archivo: <code>${esc(i.archivo)}</code><br>Último guardado: <b>${i.ultimo ? esc(relativo(i.ultimo)) + " (" + esc(i.ultimo.replace("T", " ")) + ")" : "nunca"}</b>
        ${i.error && i.error !== "permiso" ? `<br><span style="color:var(--bad)">${esc(i.error)}</span>` : ""}</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${i.permiso !== "granted" ? `<button class="btn primario" id="cRecon">${icono("nube")} Reconectar</button>` : `<button class="btn primario" id="cAhora">${icono("check")} Guardar ahora</button>`}
          <button class="btn" id="cElegir">Cambiar de carpeta</button><button class="btn" id="cDesc">${icono("exportar")} Descargar copia</button>
          <button class="btn fantasma peligro" id="cOlvidar">Desvincular</button></div></div></div>`;
    }
    $("#contenido").innerHTML = `<div class="aviso-local">${icono("candado")}<div><b>Cómo se guardan los datos.</b> La aplicación no envía nada a internet. Escribe un Excel con <b>solo números de caso</b> en una carpeta de su ordenador; si esa carpeta está sincronizada con el OneDrive/SharePoint del SMS, OneDrive lo sube con su cuenta corporativa.</div></div>
      <div class="grid g2" style="grid-template-columns:1.1fr 1fr;align-items:start">${estado}<div class="tarjeta pad"><h3>Cómo prepararla (una sola vez)</h3>${pasos}</div></div>`;
    $("#cElegir")?.addEventListener("click", async () => {
      try { const r = await L.elegirCarpeta(); toast(r && (r.nuevos || r.actualizados) ? `Carpeta vinculada · recuperados ${r.nuevos + r.actualizados} casos de su archivo` : "Carpeta vinculada"); await cargarCasos(); pintar(); pintarEstadoCarpeta(); }
      catch (e) { if (e.name !== "AbortError") toast(e.message, "mal"); }
    });
    $("#cRecon")?.addEventListener("click", async () => { if (await L.reconectarCarpeta()) toast("Carpeta reconectada"); pintar(); pintarEstadoCarpeta(); });
    $("#cAhora")?.addEventListener("click", async () => { if (await L.guardarAhora()) toast("Guardado"); pintar(); });
    $("#cDesc")?.addEventListener("click", () => L.descargarCopia());
    $("#cOlvidar")?.addEventListener("click", async () => { if (await modal({ titulo: "Desvincular carpeta", aceptar: "Desvincular", peligro: true, html: "<p>Se dejará de guardar en la carpeta. Los casos siguen en este navegador y el archivo de la carpeta no se borra.</p>" })) { await L.olvidarCarpeta(); pintar(); pintarEstadoCarpeta(); } });
  };
  await pintar();
}

async function pUnir() {
  barra("Unir casos", "Data manager");
  const info = await L.infoCarpeta();
  const cont = $("#contenido");
  const tabla = (inf) => `<div class="tarjeta" style="margin-top:18px"><table class="tabla compacta"><thead><tr><th>Archivo</th><th>Nuevos</th><th>Actualizados</th><th>Sin cambios</th><th>Más reciente aquí</th><th>Avisos</th></tr></thead><tbody>
    ${inf.map((r) => `<tr style="cursor:default"><td class="codigo">${esc(r.archivo)}</td>${r.error ? `<td colspan="5" style="color:var(--bad)">${esc(r.error)}</td>` : `
      <td><b>${r.nuevos}</b></td><td><b>${r.actualizados}</b></td><td>${r.iguales}</td><td>${r.conservados}</td>
      <td>${r.conflictos.length ? `<span style="color:var(--warn)">${r.conflictos.map(esc).join("<br>")}</span>` : `<span class="sub">—</span>`}</td>`}</tr>`).join("") || `<tr><td colspan="6" class="vacio">No hay archivos de otras personas en la carpeta.</td></tr>`}</tbody></table></div>`;
  cont.innerHTML = `<div class="aviso-local">${icono("info")}<div>Lee los Excel <code>WILLEM_*.xlsx</code> de la carpeta compartida y los junta con sus casos. Si un caso está en varios sitios, <b>gana la versión modificada más recientemente</b>. Si dos personas usaron el mismo número para pacientes distintos, se avisa y no se mezcla.</div></div>
    <div class="tarjeta pad carpeta-cta"><div class="ic-gr">${icono("unir")}</div><div><h3>${info.nombre ? `Carpeta: ${esc(info.nombre)}` : "No hay carpeta vinculada"}</h3>
      <p class="sub">${info.nombre ? "Pulse para traer los casos de todo el equipo." : "Vincule la carpeta compartida o elija los archivos a mano."}</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${info.nombre && info.soportada ? `<button class="btn primario grande" id="uAhora">${icono("unir")} Unir casos de la carpeta</button>` : `<a class="btn primario" href="#/carpeta">${icono("nube")} Vincular carpeta</a>`}
      <label class="btn">${icono("importar")} Elegir archivos a mano<input type="file" id="uArch" accept=".xlsx" multiple hidden></label></div></div></div><div id="uRes"></div>`;
  const mostrar = async (inf) => {
    $("#uRes").innerHTML = tabla(inf);
    const n = inf.reduce((a, r) => a + (r.nuevos || 0) + (r.actualizados || 0), 0);
    toast(n ? (n === 1 ? "1 caso incorporado o actualizado" : `${n} casos incorporados o actualizados`) : "No había cambios nuevos", n ? "ok" : "info");
    await cargarCasos();
  };
  $("#uAhora")?.addEventListener("click", async (ev) => { ev.target.disabled = true; try { await mostrar(await L.unirCarpeta()); } catch (e) { toast(e.message, "mal"); } ev.target.disabled = false; });
  $("#uArch").onchange = async (ev) => { try { await mostrar(await L.unirArchivos([...ev.target.files])); } catch (e) { toast(e.message, "mal"); } };
}

arrancar();
