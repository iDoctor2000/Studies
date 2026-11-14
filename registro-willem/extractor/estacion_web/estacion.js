// WILLEM · Estación de informes (Mac). Interfaz local: todo ocurre en este ordenador.
import { icono as iconoBase } from "./iconos.js";

// ---------------------------------------------------------------------------
//  Utilidades
// ---------------------------------------------------------------------------
const EXTRA = {
  carpeta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  usb: '<rect x="7" y="9" width="10" height="12" rx="2"/><path d="M9 9V3h6v6M10.5 5.5h.01M13.5 5.5h.01"/>',
  ia: '<rect x="5" y="5" width="14" height="14" rx="3"/><path d="M9 1.5v3M15 1.5v3M9 19.5v3M15 19.5v3M1.5 9h3M1.5 15h3M19.5 9h3M19.5 15h3"/><path d="m9.5 15 1.8-6h1.4l1.8 6M10.2 13h3.6"/>',
  mascara: '<path d="M3 9c0-2 2-3 4.5-3S12 7.5 12 7.5 14 6 16.5 6 21 7 21 9c0 4.5-3 8-6 8-1.5 0-2-1.5-3-1.5S10.5 17 9 17c-3 0-6-3.5-6-8z"/><path d="M7.5 11.2h2M14.5 11.2h2"/>',
  registro: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/><path d="m15 16 1.5 1.5L19 15"/>',
  ojoNo: '<path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-3.2 3.9M6.5 7.6C3.8 9.3 2 12 2 12s3.5 6 10 6a9.7 9.7 0 0 0 4.4-1"/><path d="M9.9 10a3 3 0 0 0 4.1 4.1"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icono = (n, c = "") => (EXTRA[n]
  ? `<svg class="ico ${c}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${EXTRA[n]}</svg>`
  : iconoBase(n, c));
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(4, "0");
const fecha = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
const mmss = (s) => { s = Math.max(0, Math.round(s)); return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : s >= 60 ? `${Math.floor(s / 60)} min ${s % 60 ? (s % 60) + " s" : ""}` : `${s} s`; };

// Clave de esta sesión: llega en la dirección (#t=...) y se quita de la barra
const S = { token: "", estado: null, trabajo: null, vista: "circuito", avisos: null, llave: null, mostrar: false, q: "", rehacer: false, ocupado: false };
{
  const m = location.hash.match(/t=([\w-]+)/);
  if (m) { S.token = m[1]; try { sessionStorage.setItem("estacion_t", m[1]); } catch { /* sin almacenamiento */ } history.replaceState(null, "", location.pathname); }
  else { try { S.token = sessionStorage.getItem("estacion_t") || ""; } catch { /* sin almacenamiento */ } }
}

async function api(metodo, ruta, cuerpo) {
  const r = await fetch("/api/" + ruta, {
    method: metodo, headers: { "X-Token": S.token, ...(cuerpo ? { "Content-Type": "application/json" } : {}) },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
}

function toast(msg, tipo = "ok") {
  const t = document.createElement("div");
  t.className = "toast " + tipo;
  t.innerHTML = icono(tipo === "ok" ? "check" : tipo === "mal" ? "aviso" : "info") + `<span>${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.classList.add("fuera"); setTimeout(() => t.remove(), 350); }, 3800);
}

function modal({ titulo, html, aceptar = "Aceptar", cancelar = "Cancelar", peligro = false, alAbrir, alAceptar }) {
  return new Promise((res) => {
    const velo = document.createElement("div"); velo.className = "velo";
    const m = document.createElement("div"); m.className = "modal"; m.setAttribute("role", "dialog");
    m.innerHTML = `<h3>${esc(titulo)}</h3><div class="m-cuerpo">${html || ""}</div><div class="m-error"></div>
      <div class="m-pie">${cancelar ? `<button class="btn fantasma" data-x>${esc(cancelar)}</button>` : ""}<button class="btn ${peligro ? "peligro" : "primario"}" data-ok>${esc(aceptar)}</button></div>`;
    const cerrar = (v) => { velo.remove(); m.remove(); document.removeEventListener("keydown", tecla); res(v); };
    const tecla = (e) => { if (e.key === "Escape") cerrar(false); if (e.key === "Enter" && e.target.tagName === "INPUT") $("[data-ok]", m).click(); };
    document.addEventListener("keydown", tecla);
    velo.onclick = () => cerrar(false);
    $("[data-x]", m)?.addEventListener("click", () => cerrar(false));
    $("[data-ok]", m).addEventListener("click", async () => {
      if (alAceptar) {
        const b = $("[data-ok]", m); b.disabled = true;
        try { if ((await alAceptar(m)) === false) { b.disabled = false; return; } }
        catch (e) { $(".m-error", m).textContent = e.message; b.disabled = false; return; }
      }
      cerrar(true);
    });
    document.body.append(velo, m);
    alAbrir?.(m);
    ($("input", m) || $("[data-ok]", m)).focus();
  });
}

// ---------------------------------------------------------------------------
//  Electrocardiograma del encabezado (mismo trazado que la web del registro)
// ---------------------------------------------------------------------------
const LATIDO = 350;
const ECG = "M0 80 " + Array.from({ length: 4 }, (_, k) => {
  const x = k * LATIDO;
  return `H${x} l12 -6 l10 6 H${x + 80} l8 10 l12 -70 l14 96 l10 -36 H${x + 200} q18 -22 36 0 H${x + LATIDO}`;
}).join(" ");
function animarECG(t) {
  const p = $(".ecg-barrido");
  if (p) {
    const L = +(p.dataset.l ||= p.getTotalLength());
    const punta = p.nextElementSibling;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { p.style.strokeDasharray = "none"; punta.style.display = "none"; }
    else {
      const ciclo = S.trabajo?.activo ? 3200 : 6500; // durante un trabajo, el corazón va más deprisa
      S.fase = (S.fase || 0) + ((t - (S.tAnt || t)) / ciclo);
      S.tAnt = t;
      const h = (S.fase % 1) * L;
      p.style.strokeDasharray = `${L - 90} 90`;
      p.style.strokeDashoffset = `${L - 90 - h}`;
      const q = p.getPointAtLength(h);
      punta.setAttribute("cx", q.x); punta.setAttribute("cy", q.y);
    }
  }
  requestAnimationFrame(animarECG);
}

// ---------------------------------------------------------------------------
//  Esqueleto
// ---------------------------------------------------------------------------
function tema() {
  let t = null; try { t = localStorage.getItem("estacion_tema"); } catch { /* */ }
  if (t) document.documentElement.dataset.tema = t; else delete document.documentElement.dataset.tema;
}

function esqueleto() {
  $("#app").innerHTML = `
  <header class="heroe">
    <svg class="ecg" viewBox="0 0 1400 160" preserveAspectRatio="none" aria-hidden="true"><path class="ecg-barrido" d="${ECG}"/><circle class="ecg-punta" r="4.5" cx="-20" cy="80"/></svg>
    <div class="h-arriba">
      <div class="marca"><div class="logo">${icono("logo")}</div><div><b>WILLEM</b><span>Estación de informes · Arrixaca</span></div></div>
      <div class="estados" id="estados"></div>
      <button class="tema" id="bTema" title="Tema claro / oscuro">${icono("luna", "i-luna")}${icono("sol", "i-sol")}</button>
    </div>
    <h1>De los informes en PDF al registro,<br><span>sin que un solo dato personal salga del Mac.</span></h1>
    <nav class="pestanas" id="pestanas">
      ${[["circuito", "unir", "Circuito"], ["avisos", "bandera", "Avisos"], ["llave", "llave", "Libro llave"], ["ajustes", "editar", "Ajustes"]]
        .map(([k, i, t]) => `<button data-v="${k}">${icono(i)}<span>${t}</span><b class="cuenta" data-cuenta="${k}"></b></button>`).join("")}
    </nav>
  </header>
  <main id="vista"></main>
  <footer class="pie">${icono("candado")} Todo ocurre en este ordenador (127.0.0.1). Los informes originales no se copian; el libro llave nunca sale de su carpeta privada.</footer>`;
  $$("#pestanas button").forEach((b) => (b.onclick = () => irA(b.dataset.v)));
  $("#bTema").onclick = () => {
    const oscuro = matchMedia("(prefers-color-scheme: dark)").matches;
    const actual = document.documentElement.dataset.tema || (oscuro ? "oscuro" : "claro");
    try { localStorage.setItem("estacion_tema", actual === "oscuro" ? "claro" : "oscuro"); } catch { /* */ }
    tema();
  };
  requestAnimationFrame(animarECG);
}

function irA(v) {
  S.vista = v;
  $$("#pestanas button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  if (v === "avisos") cargarAvisos();
  else if (v === "llave") cargarLlave();
  else pintarVista();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------------------
//  Estado (cada pocos segundos)
// ---------------------------------------------------------------------------
async function refrescar() {
  try {
    S.estado = await api("GET", "estado");
    S.trabajo = S.estado.trabajo;
  } catch (e) {
    if (/Sesión no válida/.test(e.message)) return sinSesion();
    return;
  }
  pintarEstados();
  if (S.vista === "circuito") pintarCircuito();
  if (S.vista === "ajustes" && !$("#vista .ajustes")) pintarVista();
}

function sinSesion() {
  $("#app").innerHTML = `<div class="sin-sesion"><div class="logo">${icono("logo")}</div><h2>Abra la estación desde el Mac</h2>
    <p>Por seguridad, esta página solo funciona si se abre con un doble clic en <b>WILLEM_Mac.command</b>.</p></div>`;
}

function pintarEstados() {
  const e = S.estado; if (!e) return;
  const ia = e.ia, eq = e.equipo, rg = e.registro;
  const pill = (cl, ic, txt, tit, accion = "") => `<button class="pildora ${cl}" ${accion} title="${esc(tit)}"><i class="punto"></i>${icono(ic)}<span>${esc(txt)}</span></button>`;
  $("#estados").innerHTML = [
    ia.ok ? pill("ok", "ia", `IA local · ${ia.modelo}`, "Ollama funcionando en este Mac con el modelo elegido")
      : ia.en_marcha ? pill("aviso", "ia", "Falta el modelo", `Ollama está abierto pero no tiene ${ia.modelo}. En el Terminal: ollama pull ${ia.modelo}`, 'data-ir="ajustes"')
        : pill("mal", "ia", "Ollama apagado", "Pulse para arrancarlo", 'data-acc="ollama"'),
    eq.filevault === true ? pill("ok", "escudo", "Disco cifrado", "FileVault está activado")
      : eq.filevault === false ? pill("mal", "escudo", "FileVault apagado", "Actívelo en Ajustes del Sistema → Privacidad y seguridad → FileVault")
        : pill("gris", "escudo", "FileVault: no es un Mac", "Esta comprobación solo funciona en macOS"),
    rg.ok ? pill("ok", "registro", "Registro conectado", rg.url) : pill("gris", "registro", "Registro cerrado", `Pulse para abrir el registro (${rg.url})`, 'data-acc="registro"'),
  ].join("");
  $$("#estados [data-acc]").forEach((b) => (b.onclick = () => (b.dataset.acc === "ollama" ? arrancarOllama() : arrancarRegistro())));
  $$("#estados [data-ir]").forEach((b) => (b.onclick = () => irA(b.dataset.ir)));
  const c = e.cuentas;
  const cuenta = { avisos: c.pendientes, llave: c.llave };
  $$("[data-cuenta]").forEach((x) => { const n = cuenta[x.dataset.cuenta]; x.textContent = n || ""; x.classList.toggle("aviso", x.dataset.cuenta === "avisos" && n > 0); });
}

async function arrancarOllama() {
  toast("Arrancando Ollama…", "info");
  try { const r = await api("POST", "ollama"); toast(r.mensaje, r.ok ? "ok" : "mal"); } catch (e) { toast(e.message, "mal"); }
  setTimeout(refrescar, 2500);
}
async function arrancarRegistro() {
  toast("Abriendo el registro…", "info");
  try { const r = await api("POST", "registro/arrancar"); toast(r.mensaje, r.ok ? "ok" : "mal"); } catch (e) { toast(e.message, "mal"); }
  refrescar();
}

// ---------------------------------------------------------------------------
//  Vista: CIRCUITO
// ---------------------------------------------------------------------------
function pintarVista() {
  $$("#pestanas button").forEach((b) => b.classList.toggle("on", b.dataset.v === S.vista));
  if (S.vista === "circuito") { $("#vista").innerHTML = `<div class="circuito-vista"></div>`; pintarCircuito(true); }
  else if (S.vista === "avisos") pintarAvisos();
  else if (S.vista === "llave") pintarLlave();
  else pintarAjustes();
}

const animarCifra = (el, nuevo) => {
  const viejo = +(el.dataset.v ?? 0);
  el.dataset.v = nuevo;
  if (viejo === nuevo) { el.textContent = nuevo; return; }
  const t0 = performance.now();
  const paso = (t) => {
    const k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(viejo + (nuevo - viejo) * e);
    if (k < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
};

function pasos() {
  const e = S.estado, c = e.cuentas, en = e.entrada, u = e.ultimo, t = S.trabajo || {};
  const corriendo = (tipo) => t.activo && t.tipo === tipo;
  const ocupado = !!t.activo;
  return [
    { k: "entrada", color: "#3b82f6", ic: "usb", n: en.pdfs, tit: "Informes en PDF",
      desc: en.existe ? `${icono("carpeta")} ${esc(en.nombre)}` : "Elija la carpeta o el USB con los informes de alta",
      boton: `<button class="btn" data-acc="elegir" ${ocupado ? "disabled" : ""}>${icono("carpeta")} ${en.existe ? "Cambiar carpeta" : "Elegir carpeta o USB"}</button>`,
      estado: en.pdfs ? "listo" : "" },
    { k: "anonimizar", color: "#14b8a6", ic: "mascara", n: c.listos, tit: "Anonimizados",
      desc: u ? `Último lote: <b>${u.listo}</b> listos · <b>${u.revisar}</b> a revisar · <b class="${u.bloqueado ? "rojo" : ""}">${u.bloqueado}</b> bloqueados` : "Lee la cabecera, asigna el número de caso y quita los datos personales",
      boton: `<button class="btn primario" data-acc="anonimizar" ${ocupado || !en.pdfs ? "disabled" : ""}>${icono("play")} Anonimizar ${en.pdfs ? plural(en.pdfs, "informe", "informes") : ""}</button>`,
      estado: corriendo("anonimizar") ? "trabajando" : c.listos ? "listo" : "" },
    { k: "revisar", color: "#f59e0b", ic: "bandera", n: c.pendientes, tit: "Avisos por revisar",
      desc: c.pendientes ? "Posibles nombres en el texto: decida con un botón si se ocultan" : "Ningún informe pendiente de revisar",
      boton: c.pendientes ? `<button class="btn ambar" data-acc="avisos">${icono("bandera")} Revisar ${plural(c.pendientes, "informe", "informes")}</button>`
        : `<span class="hecho">${icono("check")} Todo revisado</span>`,
      estado: c.pendientes ? "atencion" : c.listos ? "listo" : "" },
    { k: "ia", color: "#7c5cf0", ic: "chispa", n: c.sin_ia, tit: "Casos para la IA",
      desc: `${plural(c.casos_listos, "caso anonimizado", "casos anonimizados")} · ${plural(c.propuestas, "con propuesta", "con propuesta")}<label class="chk"><input type="checkbox" id="rehacer" ${S.rehacer ? "checked" : ""}> repetir también los ya hechos</label>`,
      boton: `<button class="btn ia" data-acc="ia" ${ocupado || (!c.sin_ia && !(S.rehacer && c.casos_listos)) || !e.ia.ok ? "disabled" : ""}>${icono("chispa")} Rellenar con IA</button>`,
      estado: corriendo("ia") ? "trabajando" : c.propuestas && !c.sin_ia ? "listo" : "" },
    { k: "registro", color: "#e11d48", ic: "enviar", n: c.sin_pasar, tit: "Propuestas por pasar",
      desc: e.registro.ok ? `Destino: ${esc(e.registro.url.replace(/^https?:\/\//, ""))}` : "El registro no está abierto",
      boton: e.registro.ok ? `<button class="btn rosa" data-acc="registro" ${ocupado || !c.sin_pasar ? "disabled" : ""}>${icono("enviar")} Pasar al registro</button>`
        : `<button class="btn" data-acc="abrirRegistro">${icono("registro")} Abrir el registro</button>`,
      estado: corriendo("registro") ? "trabajando" : c.propuestas && !c.sin_pasar ? "listo" : "" },
  ];
}

function pintarCircuito(forzar = false) {
  const cont = $(".circuito-vista");
  if (!cont || !S.estado) return;
  const ps = pasos();
  if (forzar || !$(".circuito", cont)) {
    cont.innerHTML = `
      <section class="circuito" id="circuito">${ps.map((p, i) => `
        <article class="paso" data-paso="${p.k}" style="--c:${p.color};--i:${i}">
          <div class="p-cab"><span class="p-num">${i + 1}</span><span class="p-ic">${icono(p.ic)}</span></div>
          <div class="cifra" data-v="0">0</div>
          <div class="p-tit"></div><div class="p-desc"></div><div class="p-acc"></div>
        </article>${i < ps.length - 1 ? `<div class="enlace" data-enlace="${i}"><i></i></div>` : ""}`).join("")}
      </section>
      <section id="trabajo"></section>
      <section class="rejilla">
        <div class="tarjeta" id="comprobaciones"></div>
        <div class="tarjeta" id="ultimo"></div>
      </section>`;
  }
  ps.forEach((p, i) => {
    const el = $(`[data-paso="${p.k}"]`, cont);
    el.className = `paso ${p.estado}`;
    animarCifra($(".cifra", el), p.n || 0);
    $(".p-tit", el).textContent = p.tit;
    if ($(".p-desc", el).innerHTML !== p.desc) $(".p-desc", el).innerHTML = p.desc;
    if ($(".p-acc", el).innerHTML !== p.boton) $(".p-acc", el).innerHTML = p.boton;
    const enl = $(`[data-enlace="${i}"]`, cont);
    if (enl) enl.classList.toggle("fluye", !!(S.trabajo?.activo && ({ anonimizar: 0, ia: 2, registro: 3 }[S.trabajo.tipo] === i || ({ ia: 3 }[S.trabajo.tipo] === i))));
  });
  $$("[data-acc]", cont).forEach((b) => (b.onclick = () => accion(b.dataset.acc)));
  const r = $("#rehacer", cont); if (r) r.onchange = () => { S.rehacer = r.checked; pintarCircuito(); };
  pintarTrabajo();
  pintarComprobaciones();
  pintarUltimo();
}

function pintarComprobaciones() {
  const e = S.estado, el = $("#comprobaciones"); if (!el) return;
  const fila = (ok, tit, sub, boton = "") => `<li class="${ok === true ? "ok" : ok === false ? "mal" : "gris"}"><span class="semaforo">${icono(ok === true ? "check" : ok === false ? "x" : "info")}</span>
    <div><b>${tit}</b><span>${sub}</span></div>${boton}</li>`;
  el.innerHTML = `<h3>${icono("escudo")} Comprobaciones de este Mac</h3><ul class="checks">
    ${fila(e.equipo.filevault, "Cifrado del disco (FileVault)", e.equipo.filevault === true ? "Activado: si pierde el Mac, los datos no se pueden leer" : e.equipo.filevault === false ? "Desactivado: actívelo antes de usar informes reales" : "Solo se comprueba en macOS")}
    ${fila(e.ia.en_marcha, "Ollama (IA local)", e.ia.en_marcha ? `En marcha · ${e.ia.modelos.length} modelo(s) instalado(s)` : "No está abierto", e.ia.en_marcha ? "" : `<button class="btn peq" data-c="ollama">Arrancar</button>`)}
    ${fila(e.ia.ok, `Modelo ${esc(e.ia.modelo)}`, e.ia.ok ? "Instalado y listo" : `En el Terminal: <code>ollama pull ${esc(e.ia.modelo)}</code>`)}
    ${fila(e.registro.ok, "Registro WILLEM", e.registro.ok ? `Conectado · ${esc(e.registro.url)}` : `Cerrado · ${esc(e.registro.url)}`, e.registro.ok ? "" : `<button class="btn peq" data-c="registro">Abrir</button>`)}
    ${e.equipo.avisos.filter((x) => !/FileVault/.test(x)).map((x) => fila(false, "Atención", esc(x))).join("")}
  </ul>`;
  $$("[data-c]", el).forEach((b) => (b.onclick = () => (b.dataset.c === "ollama" ? arrancarOllama() : arrancarRegistro())));
}

function pintarUltimo() {
  const e = S.estado, el = $("#ultimo"); if (!el) return;
  const u = e.ultimo, c = e.cuentas;
  el.innerHTML = `<h3>${icono("historial")} Cómo va el registro</h3>
    <div class="mini-kpis">
      <div><b>${c.llave}</b><span>pacientes en el libro llave</span></div>
      <div><b>${c.casos_listos}</b><span>casos anonimizados</span></div>
      <div><b>${c.propuestas}</b><span>con propuesta de la IA</span></div>
      <div><b>${c.propuestas - c.sin_pasar}</b><span>pasados al registro</span></div>
    </div>
    ${u ? `<div class="ult-lote">Último lote (${esc(new Date(u.fecha).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }))}): ${plural(u.total, "informe", "informes")}</div>
      ${u.bloqueados.length ? `<ul class="bloqueados">${u.bloqueados.map((b) => `<li>${icono("candado")}<div><b>${esc(b.archivo)}</b><span>${esc(b.motivo)}</span></div></li>`).join("")}</ul>` : ""}` : `<p class="sub">Aún no se ha procesado ningún informe.</p>`}
    <div class="carpetas">
      <button class="btn peq fantasma" data-ab="listos">${icono("carpeta")} Anonimizados</button>
      <button class="btn peq fantasma" data-ab="propuestas">${icono("carpeta")} Propuestas IA</button>
      <button class="btn peq fantasma" data-ab="privado">${icono("candado")} Carpeta privada</button>
    </div>`;
  $$("[data-ab]", el).forEach((b) => (b.onclick = () => abrir(b.dataset.ab)));
}

async function abrir(que) {
  try { const r = await api("POST", "abrir", { que }); if (!r.abierto) toast("Carpeta: " + r.ruta, "info"); } catch (e) { toast(e.message, "mal"); }
}

// ---------------------------------------------------------------------------
//  Trabajo en curso
// ---------------------------------------------------------------------------
const TITULOS = { anonimizar: ["mascara", "#14b8a6"], ia: ["chispa", "#7c5cf0"], registro: ["enviar", "#e11d48"] };
function pintarTrabajo() {
  const el = $("#trabajo"); if (!el) return;
  const t = S.trabajo;
  if (!t?.tipo) { el.innerHTML = ""; el.className = ""; return; }
  const [ic, color] = TITULOS[t.tipo] || ["info", "#0f766e"];
  const pct = t.total ? Math.round((100 * t.hecho) / t.total) : 0;
  const ahora = (t.fin || Date.now() / 1000);
  const trans = ahora - t.inicio;
  const eta = t.activo && t.hecho > 0 && t.total > t.hecho ? (trans / t.hecho) * (t.total - t.hecho) : null;
  const clase = `trabajo ${t.activo ? "activo" : ""} ${t.error ? "error" : t.activo ? "" : "fin"}`;
  if (!$(".tr-cab", el) || el.dataset.tipo !== t.tipo + t.inicio) {
    el.dataset.tipo = t.tipo + t.inicio;
    el.innerHTML = `<div class="tr-cab"><span class="tr-ic">${icono(ic)}</span><div class="tr-txt"><h3></h3><div class="tr-msg"></div></div><div class="tr-pct"></div></div>
      <div class="barra"><i></i></div><div class="tr-meta"><span class="tr-tiempo"></span><span class="tr-eta"></span></div>
      <div class="tr-res"></div><ol class="tr-log"></ol>`;
  }
  el.className = clase;
  el.style.setProperty("--c", color);
  $("h3", el).textContent = t.titulo + (t.activo ? "" : t.error ? " · detenido" : " · terminado");
  const r0 = t.resultado;
  const final = !t.activo && !t.error && r0 ? ({
    anonimizar: () => `${plural(r0.listo + r0.revisar + r0.bloqueado, "informe leído", "informes leídos")} · ${plural(r0.nuevos, "paciente nuevo", "pacientes nuevos")} en el libro llave`,
    ia: () => `${plural(r0.campos, "dato propuesto", "datos propuestos")} en ${plural(r0.casos, "caso", "casos")}: ahora se pasan al registro para revisarlos`,
    registro: () => `${plural(r0.creado, "caso creado", "casos creados")} y ${plural(r0.actualizado, "completado", "completados")} en el registro`,
  }[t.tipo] || (() => ""))() : "";
  $(".tr-msg", el).textContent = t.error || final || t.mensaje || "";
  $(".tr-pct", el).textContent = t.activo || !t.error ? `${t.activo ? pct : 100}%` : "";
  $(".barra i", el).style.width = `${t.activo ? pct : t.error ? pct : 100}%`;
  $(".tr-tiempo", el).innerHTML = `${icono("reloj")} ${mmss(trans)}${t.activo ? " en marcha" : ""}`;
  $(".tr-eta", el).textContent = eta ? `≈ ${mmss(eta)} restantes` : t.total ? `${t.hecho} de ${t.total}` : "";
  const lineas = (t.lineas || []).slice(-14).reverse();
  const log = $(".tr-log", el);
  const nuevoLog = lineas.map((l) => `<li class="${/BLOQUEADO|✗/.test(l) ? "mal" : /revisar/.test(l) ? "aviso" : ""}">${esc(l)}</li>`).join("");
  if (log.innerHTML !== nuevoLog) log.innerHTML = nuevoLog;
  const res = $(".tr-res", el);
  const r = t.resultado;
  let html = "";
  if (!t.activo && r) {
    if (t.tipo === "anonimizar") html = `<div class="chips"><span class="chip verde"><b>${r.listo}</b> listos</span><span class="chip ambar"><b>${r.revisar}</b> para revisar</span><span class="chip rojo"><b>${r.bloqueado}</b> bloqueados</span><span class="chip"><b>${r.nuevos}</b> pacientes nuevos</span></div>
      <div class="tr-botones"><button class="btn peq" data-r="resumen">${icono("libro")} Ver el resumen</button>${r.revisar ? `<button class="btn peq ambar" data-r="avisos">${icono("bandera")} Revisar avisos</button>` : ""}</div>`;
    if (t.tipo === "ia") html = `<div class="chips"><span class="chip violeta"><b>${r.casos}</b> casos</span><span class="chip violeta"><b>${r.campos}</b> datos propuestos</span><span class="chip ambar"><b>${r.avisos}</b> con aviso</span><span class="chip">${icono("reloj")} ${mmss(r.segundos)}</span></div>
      ${r.errores?.length ? `<ul class="errores">${r.errores.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      <div class="tr-botones"><button class="btn peq" data-r="resumen">${icono("libro")} Ver el resumen</button></div>`;
    if (t.tipo === "registro") html = `<div class="chips"><span class="chip verde"><b>${r.creado}</b> casos creados</span><span class="chip"><b>${r.actualizado}</b> completados</span><span class="chip gris"><b>${r.omitido}</b> no importados</span></div>
      <p class="sub">Cada dato de la IA queda marcado en el registro hasta que una persona lo revise.</p>
      <div class="tr-botones"><a class="btn peq" href="${esc(r.url)}/#/casos?ia=1" target="_blank" rel="noopener">${icono("registro")} Revisarlos en el registro</a></div>`;
  }
  if (res.innerHTML !== html) {
    res.innerHTML = html;
    $$("[data-r]", res).forEach((b) => (b.onclick = () => (b.dataset.r === "avisos" ? irA("avisos") : abrir("resumen"))));
  }
}

let sondeo = null;
function vigilar() {
  clearInterval(sondeo);
  sondeo = setInterval(async () => {
    try { S.trabajo = await api("GET", "trabajo"); } catch { return; }
    pintarTrabajo();
    if (S.vista === "circuito") $$(".enlace").forEach((x, i) => x.classList.toggle("fluye", !!(S.trabajo.activo && (({ anonimizar: [0], ia: [2, 3], registro: [3] })[S.trabajo.tipo] || []).includes(i))));
    if (!S.trabajo.activo) {
      clearInterval(sondeo);
      await refrescar();
      if (S.trabajo.error) toast(S.trabajo.error, "mal");
      else toast(`${S.trabajo.titulo}: terminado`);
    }
  }, 600);
}

async function accion(a) {
  try {
    if (a === "elegir") {
      const r = await api("POST", "elegir");
      if (!r.cancelado) toast(`${r.nombre}: ${plural(r.pdfs, "PDF", "PDF")}`);
      return refrescar();
    }
    if (a === "avisos") return irA("avisos");
    if (a === "abrirRegistro") return arrancarRegistro();
    if (a === "anonimizar") { await api("POST", "anonimizar"); }
    if (a === "ia") { await api("POST", "ia", { rehacer: S.rehacer }); }
    if (a === "registro") {
      const ok = await modal({
        titulo: "Pasar al registro", aceptar: "Entrar y pasar",
        html: `<p>Se enviarán <b>${plural(S.estado.cuentas.sin_pasar, "propuesta", "propuestas")}</b> de la IA (anonimizadas) a <b>${esc(S.estado.registro.url)}</b>.</p>
          <label class="campo"><span>Usuario del registro (data manager)</span><input id="rUsu" autocomplete="username" value="${esc(S.estado.ajustes.usuario_registro || "")}"></label>
          <label class="campo"><span>Contraseña</span><input id="rCla" type="password" autocomplete="current-password"></label>
          <p class="sub">${icono("candado")} La contraseña no se guarda en ningún sitio.</p>`,
        alAbrir: (m) => { if ($("#rUsu", m).value) setTimeout(() => $("#rCla", m).focus(), 30); },
        alAceptar: async (m) => { await api("POST", "registro", { usuario: $("#rUsu", m).value, clave: $("#rCla", m).value }); },
      });
      if (!ok) return;
    }
    S.trabajo = await api("GET", "trabajo");
    pintarCircuito();
    vigilar();
  } catch (e) { toast(e.message, "mal"); }
}

// ---------------------------------------------------------------------------
//  Vista: AVISOS
// ---------------------------------------------------------------------------
async function cargarAvisos() {
  try { S.avisos = await api("GET", "avisos"); } catch (e) { return toast(e.message, "mal"); }
  pintarVista();
}

const DECIDIDO = { ocultar: ["Ocultado", "violeta"], no_es: ["No es un nombre", "verde"], visto: ["Revisado", "verde"] };
function pintarAvisos() {
  const L = S.avisos || [];
  const cont = $("#vista");
  if (!L.length) {
    cont.innerHTML = `<div class="vacio grande"><div class="vacio-ic">${icono("check")}</div><h2>No hay avisos pendientes</h2>
      <p>Todos los informes anonimizados están listos. Si un informe tiene posibles nombres en el texto, aparecerá aquí.</p>
      <button class="btn" id="volver">${icono("flechaI")} Volver al circuito</button></div>`;
    $("#volver").onclick = () => irA("circuito");
    return;
  }
  cont.innerHTML = `<div class="cab-vista"><div><h2>${icono("bandera")} Avisos por revisar</h2>
      <p class="sub">La anonimización ha dejado estas frases dudosas. Decida en cada una: si es un nombre se sustituye por <span class="anon">[PERSONA]</span> y se ocultará también en los informes siguientes.</p></div>
      <div class="aviso-privado">${icono("candado")} Pantalla privada: contiene posibles nombres</div></div>
    ${L.map((inf) => `
    <article class="inf" data-base="${esc(inf.base)}">
      <div class="inf-cab"><span class="num">#${pad(inf.numero)}</span><div><b>Caso ${pad(inf.numero)} · ingreso ${fecha(inf.fecha_ingreso)}</b><span>${icono("importar")} ${esc(inf.archivo || "")}</span></div>
        <span class="pend">${plural(inf.pendientes, "aviso pendiente", "avisos pendientes")}</span></div>
      <ul class="avisos">${inf.avisos.map((a) => {
        const ctx = esc(a.contexto).replace("⟦", "<mark>").replace("⟧", "</mark>");
        const d = DECIDIDO[a.resuelto];
        const nombres = a.palabras.map((w) => `«${esc(w)}»`).join(" y ");
        return `<li class="${a.resuelto ? "hecho" : ""}">
          <div class="a-mot">${icono(a.resuelto ? "check" : "aviso")} ${esc(a.motivo)} ${d ? `<span class="chip ${d[1]}">${d[0]}</span>` : ""}</div>
          <div class="a-ctx">${ctx}</div>
          ${a.resuelto ? "" : `<div class="a-acc">
            ${a.palabras.length ? `<button class="btn violeta" data-d="ocultar" data-id="${a.id}">${icono("mascara")} Es un nombre: ocultar ${nombres}</button>
              <button class="btn" data-d="no_es" data-id="${a.id}">${icono("check")} No es un nombre</button>` : ""}
            <button class="btn fantasma" data-d="visto" data-id="${a.id}">Visto: no hay dato personal</button></div>`}
        </li>`;
      }).join("")}</ul>
      <div class="inf-pie">
        <form class="ocultar-otra"><input placeholder="Ocultar otra palabra o nombre en este informe…" aria-label="Palabra a ocultar"><button class="btn peq">${icono("mascara")} Ocultar</button></form>
        <button class="btn peq fantasma" data-texto>${icono("ojo")} Ver el texto completo</button>
        <button class="btn peq peligro-suave" data-descartar>${icono("papelera")} Descartar informe</button>
      </div>
      <pre class="texto oculto"></pre>
    </article>`).join("")}`;
  $$(".inf", cont).forEach((art) => {
    const base = art.dataset.base, inf = L.find((x) => x.base === base);
    $$("[data-d]", art).forEach((b) => (b.onclick = () => decidir(base, +b.dataset.id, b.dataset.d)));
    $("form", art).onsubmit = (ev) => { ev.preventDefault(); const v = $("input", art).value.trim(); if (v) decidir(base, null, "ocultar_texto", v); };
    $("[data-texto]", art).onclick = () => {
      const pre = $("pre", art);
      if (pre.classList.toggle("oculto")) return;
      const dudosas = inf.avisos.filter((a) => !a.resuelto).flatMap((a) => a.palabras);
      let h = esc(inf.texto).replace(/\[([A-ZÁÉÍÓÚÑº ]{2,})\]/g, '<span class="anon">[$1]</span>');
      for (const w of dudosas) h = h.replace(new RegExp(`(?<![\\wÁ-ú])(${w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})(?![\\wÁ-ú])`, "g"), "<mark>$1</mark>");
      pre.innerHTML = h;
    };
    $("[data-descartar]", art).onclick = async () => {
      if (!(await modal({ titulo: "Descartar este informe", peligro: true, aceptar: "Descartar", html: `<p>El informe del caso <b>${pad(inf.numero)}</b> no se usará: se borra su versión anonimizada. El PDF original no se toca.</p><p class="sub">Úselo si el texto tiene demasiados datos personales para limpiarlos con seguridad.</p>` }))) return;
      try { await api("POST", "descartar", { base }); toast("Informe descartado"); cargarAvisos(); refrescar(); } catch (e) { toast(e.message, "mal"); }
    };
  });
}

async function decidir(base, id, decision, texto = "") {
  try {
    const r = await api("POST", "avisos", { base, id, decision, texto });
    if (r.estado === "listo") toast("Informe revisado: pasa a «listos» y ya puede ir a la IA");
    else if (decision === "ocultar" || decision === "ocultar_texto") toast(`${plural(r.ocultadas, "sustitución", "sustituciones")} en el texto` + (r.anadidas.length ? ` · se ocultará también en los siguientes informes` : ""));
    else toast("Anotado");
    await cargarAvisos();
    refrescar();
  } catch (e) { toast(e.message, "mal"); }
}

// ---------------------------------------------------------------------------
//  Vista: LIBRO LLAVE
// ---------------------------------------------------------------------------
async function cargarLlave() {
  try { S.llave = await api("GET", "llave?q=" + encodeURIComponent(S.q)); } catch (e) { return toast(e.message, "mal"); }
  if (S.vista === "llave" && $("#vista .llave")) pintarFilasLlave(); else pintarVista();
}

const tapar = (v) => (v == null || v === "" ? "—" : S.mostrar ? esc(v) : `<span class="tapado">${"•".repeat(Math.max(3, String(v).length - 4))}</span>${esc(String(v).slice(-4))}`);
function pintarLlave() {
  $("#vista").innerHTML = `<div class="llave">
    <div class="cab-vista"><div><h2>${icono("llave")} Libro llave</h2><p class="sub">Número de caso ↔ CIP autonómico, CIP SNS, NHC y DNI. Solo existe en este Mac (carpeta privada) y nunca va al registro ni al NAS.</p></div>
      <div class="aviso-privado">${icono("candado")} Datos identificativos: no haga capturas de pantalla</div></div>
    <div class="barra-llave">
      <label class="buscar">${icono("buscar")}<input id="qLlave" placeholder="Buscar por nº de caso, CARM, NHC o DNI…" value="${esc(S.q)}"></label>
      <button class="btn" id="bMostrar">${icono(S.mostrar ? "ojoNo" : "ojo")} ${S.mostrar ? "Ocultar datos" : "Mostrar datos"}</button>
      <button class="btn" id="bExportar">${icono("exportar")} Copia en Excel</button>
    </div>
    <div class="tarjeta tabla-env"><table class="tabla"><thead><tr><th>Caso</th><th>CIP autonómico</th><th>CIP SNS</th><th>NHC</th><th>DNI</th><th>Informes</th><th>Último ingreso</th><th>En la llave desde</th></tr></thead><tbody id="filasLlave"></tbody></table></div>
    <p class="sub" id="pieLlave"></p></div>`;
  let tq;
  $("#qLlave").oninput = (ev) => { S.q = ev.target.value; clearTimeout(tq); tq = setTimeout(cargarLlave, 250); };
  $("#bMostrar").onclick = () => { S.mostrar = !S.mostrar; pintarLlave(); pintarFilasLlave(); };
  $("#bExportar").onclick = async () => {
    try { const r = await api("POST", "llave/exportar"); toast(r.abierto ? "Copia guardada en la carpeta privada" : "Guardada en " + r.ruta); } catch (e) { toast(e.message, "mal"); }
  };
  pintarFilasLlave();
}
function pintarFilasLlave() {
  const ll = S.llave; if (!ll) return;
  $("#filasLlave").innerHTML = ll.filas.length ? ll.filas.map((f) => `<tr><td><span class="num">#${pad(f.numero)}</span></td><td class="mono">${tapar(f.carm)}</td><td class="mono">${tapar(f.cip)}</td>
      <td class="mono">${tapar(f.nhc)}</td><td class="mono">${tapar(f.dni)}</td><td>${f.n_inf || 0}</td><td>${fecha(f.ultimo)}</td><td>${fecha(f.creado)}</td></tr>`).join("")
    : `<tr><td colspan="8" class="vacio-fila">${S.q ? "Nada coincide con la búsqueda" : "El libro llave está vacío: se rellena solo al anonimizar"}</td></tr>`;
  $("#pieLlave").textContent = `${plural(ll.total, "paciente", "pacientes")} en el libro llave · primer número de caso: ${ll.primer_numero}`;
}

// ---------------------------------------------------------------------------
//  Vista: AJUSTES
// ---------------------------------------------------------------------------
function pintarAjustes() {
  const e = S.estado, a = e.ajustes, mods = e.ia.modelos || [];
  $("#vista").innerHTML = `<div class="ajustes">
    <div class="cab-vista"><div><h2>${icono("editar")} Ajustes</h2><p class="sub">Se guardan en la carpeta privada de este Mac.</p></div></div>
    <div class="rejilla">
      <form class="tarjeta form" id="fAj">
        <h3>${icono("usb")} Informes</h3>
        <label class="campo"><span>Carpeta o USB con los PDF</span><div class="fila-campo"><input name="carpeta" value="${esc(a.carpeta)}" placeholder="/Volumes/USB/informes">${e.equipo.mac ? `<button type="button" class="btn" id="bElegir">${icono("carpeta")} Elegir…</button>` : ""}</div></label>
        <h3>${icono("ia")} Inteligencia artificial local</h3>
        <label class="campo"><span>Modelo</span><input name="modelo" list="lMods" value="${esc(a.modelo)}"><datalist id="lMods">${mods.map((m) => `<option value="${esc(m)}">`).join("")}</datalist>
          <small>${mods.length ? `Instalados: ${mods.map(esc).join(", ")}` : "Ollama no está abierto o no tiene modelos"}</small></label>
        <label class="campo"><span>Dirección de Ollama</span><input name="url_ia" value="${esc(a.url_ia)}"><small>Siempre en este Mac (127.0.0.1)</small></label>
        <h3>${icono("registro")} Registro</h3>
        <label class="campo"><span>Dirección del registro</span><input name="url_registro" value="${esc(a.url_registro)}"><small>En este Mac: http://127.0.0.1:8765 · más adelante, el NAS</small></label>
        <label class="campo"><span>Usuario (data manager)</span><input name="usuario_registro" value="${esc(a.usuario_registro)}" autocomplete="username"></label>
        <div class="form-pie"><button class="btn primario">${icono("check")} Guardar</button></div>
      </form>
      <div>
        <div class="tarjeta form">
          <h3>${icono("llave")} Números de caso</h3>
          <p class="sub">Si en el registro ya hay casos numerados a mano, empiece la numeración automática después del último.</p>
          <form class="fila-campo" id="fNum"><input name="primer_numero" inputmode="numeric" placeholder="Primer número (p. ej. 101)"><button class="btn">Fijar</button></form>
          <small class="sub">Solo se puede cambiar mientras el libro llave esté vacío.</small>
        </div>
        <div class="tarjeta form">
          <h3>${icono("carpeta")} Carpetas</h3>
          <div class="ruta"><b>Privada</b> (libro llave, avisos, resúmenes)<code>${esc(e.carpetas.privado)}</code><button class="btn peq" data-ab="privado">Abrir</button></div>
          <div class="ruta"><b>Anonimizada</b> (lo que se puede compartir)<code>${esc(e.carpetas.salida)}</code><button class="btn peq" data-ab="listos">Abrir</button></div>
        </div>
        <div class="tarjeta form como">
          <h3>${icono("info")} Cómo funciona</h3>
          <ol><li><b>Anonimizar:</b> lee la cabecera del PDF, asigna el número de caso con el libro llave y quita nombres, teléfonos, NHC, CIP y direcciones. Un doble control bloquea el informe si queda algún dato.</li>
            <li><b>Avisos:</b> posibles nombres que solo una persona puede decidir.</li>
            <li><b>IA:</b> el modelo local propone los datos del formulario, cada uno con la frase del informe en la que se basa.</li>
            <li><b>Registro:</b> las propuestas llegan marcadas «IA» y nada se valida sin que una persona lo revise.</li></ol>
        </div>
      </div>
    </div></div>`;
  $("#fAj").onsubmit = async (ev) => {
    ev.preventDefault();
    const d = Object.fromEntries(new FormData(ev.target));
    try { await api("POST", "ajustes", d); toast("Ajustes guardados"); refrescar(); } catch (er) { toast(er.message, "mal"); }
  };
  $("#bElegir")?.addEventListener("click", async () => { await accion("elegir"); pintarAjustes(); });
  $("#fNum").onsubmit = async (ev) => {
    ev.preventDefault();
    const n = parseInt(new FormData(ev.target).get("primer_numero"), 10);
    if (!(n > 0)) return toast("Escriba un número", "mal");
    try { await api("POST", "ajustes", { primer_numero: n }); toast(`El primer caso nuevo será el ${pad(n)}`); } catch (er) { toast(er.message, "mal"); }
  };
  $$("[data-ab]").forEach((b) => (b.onclick = () => abrir(b.dataset.ab)));
}

// ---------------------------------------------------------------------------
tema();
addEventListener("hashchange", () => { if (/t=[\w-]+/.test(location.hash)) location.reload(); });
if (!S.token) sinSesion();
else {
  esqueleto();
  await refrescar();
  if (S.estado) { irA("circuito"); if (S.trabajo?.activo) vigilar(); }
  setInterval(() => { if (!S.trabajo?.activo && document.visibilityState === "visible") refrescar(); }, 4000);
}
