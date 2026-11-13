// Construye el formulario a partir del diccionario maestro (Excel).
// Todo pivota en torno a la ENFERMEDAD PRINCIPAL del caso.
import { ENFERMEDADES } from "./iconos.js";

// Diagnósticos del estudio y su variable en el registro ("Otros" va en texto libre: other_disease)
export const DIAG = {
  ISQ: "ischemic_cardiomyopathy", IC: "heart_failure", EAO: "aortic_stenosis", MCH: "hypertrophic_cardiomyopathy",
  QTL: "long_qt_syndrome", ATTR: "amyloidosis_attr", IAM: "myocardial_infarction", HTA: "hypertensive_disease",
};
const DIAG_CODIGOS = new Set(Object.values(DIAG));
const GRUPOS = Object.keys(DIAG);

const txt = (v) => (v === null || v === undefined ? "" : String(v).trim());

function unidad(r) {
  const f = txt(r.formato_unidades_notas).split(";")[0].trim();
  if (!f || /YYYY|code|dropdown|ICD|free text|follow/i.test(f) || f.length > 22) return "";
  return f.replace("standard drinks/week", "UBE/sem").replace("hours/week", "h/sem").replace("beats/min", "lpm");
}

/** Analiza "a = 1 O b = 1" -> función(valores) */
function compilarCondicion(c) {
  c = txt(c);
  if (!c) return { fn: () => true, refs: [] };
  const refs = [];
  const ors = c.split(/\s+O\s+/i).map((parte) =>
    parte.split(/\s+Y\s+/i).map((t) => {
      const m = t.match(/([a-z0-9_]+)\s*(=|!=)\s*(\S+)/i);
      if (!m) return () => true;
      refs.push(m[1]);
      const val = isNaN(+m[3]) ? m[3] : +m[3];
      return m[2] === "=" ? (v) => v[m[1]] == val : (v) => v[m[1]] != val;
    })
  );
  return { fn: (v) => ors.some((ands) => ands.every((f) => f(v))), refs };
}

export function construirModelo(dic) {
  const items = [];
  let grupo = null;
  const filas = [...dic.campos, ...dic.locales];
  for (const r of filas) {
    if (/^s[ií]$/i.test(txt(r.oculto))) { grupo = null; continue; } // campos ocultos: no se muestran
    const codigo = txt(r.codigo_variable);
    const ctrl = txt(r.control_en_pantalla);
    const base = {
      codigo, etiqueta: txt(r.texto_ES) || txt(r.texto_original_EN) || codigo,
      ayuda: txt(r.ayuda_ES), original: txt(r.texto_original_EN),
      grupos: txt(r.patologias || "COMUN").toUpperCase().split(/[\s,;]+/).filter(Boolean),
      cond: compilarCondicion(r.mostrar_solo_si), condTexto: txt(r.mostrar_solo_si),
      pestana: txt(r["pestaña"]) || "Otros", bloque: txt(r.bloque), local: !!r.local, provisional: !!txt(r.codigo_provisional),
      min: r.valor_min === null || r.valor_min === "" || r.valor_min === undefined ? null : +r.valor_min,
      max: r.valor_max === null || r.valor_max === "" || r.valor_max === undefined ? null : +r.valor_max,
      unidad: unidad(r), fijo: txt(r.valor_fijo), tipo: txt(r.tipo_formulario) || txt(r.tipo),
      defecto: r.valor_por_defecto === null || r.valor_por_defecto === undefined ? "" : r.valor_por_defecto,
    };
    if (txt(r.tipo_seleccion)) {
      grupo = { ...base, tipoCampo: txt(r.tipo_seleccion).startsWith("m") ? "multi" : "single",
                conFecha: /fecha/i.test(ctrl), opciones: [] };
      items.push(grupo);
      continue;
    }
    if (txt(r.pertenece_a_pregunta) && grupo) {
      grupo.opciones.push({ codigo, etiqueta: base.etiqueta, conFecha: /date/.test(base.tipo), ayuda: base.ayuda, defecto: base.defecto });
      continue;
    }
    grupo = null;
    let tipoCampo;
    if (codigo === "authored_at") tipoCampo = "auto";
    else if (codigo === "patient_id") tipoCampo = "caso";
    else if (base.fijo || /Fijo/i.test(ctrl)) tipoCampo = "fijo";
    else if (base.tipo === "boolean, date") tipoCampo = "sinofecha";
    else if (base.tipo === "boolean") tipoCampo = "sino";
    else if (base.tipo === "date" || base.tipo === "datetime") tipoCampo = "fecha";
    else if (base.tipo === "float") tipoCampo = /entero/i.test(ctrl) ? "entero" : "numero";
    else tipoCampo = "texto";
    items.push({ ...base, tipoCampo });
  }
  const porCodigo = {};
  for (const it of items) {
    porCodigo[it.codigo] = it;
    (it.opciones || []).forEach((o) => (porCodigo[o.codigo] = { ...o, padre: it }));
  }
  const pestanas = [...new Set(items.map((i) => i.pestana))];
  return { items, porCodigo, pestanas, cargado: dic.cargado };
}

const quitarNumero = (s) => s.replace(/^\d+\.\s*/, "");

/** Diagnósticos del estudio de un caso, en el orden en que se eligieron. */
export const diagnosticosDe = (caso) => [caso.principal, ...(caso.secundarias || [])].filter(Boolean);

/**
 * Organiza el formulario de un caso en pestañas (columna "pestaña" del diccionario).
 * Solo se muestran los campos comunes y los de los diagnósticos del caso.
 * En la pestaña de diagnósticos, los campos se agrupan por diagnóstico.
 * Devuelve [{id, titulo, bloques:[{subtitulo, grupo?, items}]}].
 */
export function pestanasDelCaso(modelo, caso) {
  const activos = diagnosticosDe(caso);
  const pestDiag = modelo.pestanas.find((p) => /diagn[oó]stico/i.test(p));
  const grupoDe = (it) => {
    const g = activos.find((a) => it.grupos.includes(a));
    if (g) return g;
    return activos.find((a) => DIAG[a] && it.cond.refs.includes(DIAG[a])) || null;
  };
  const tabs = new Map(modelo.pestanas.map((p) => [p, { id: "p:" + p, titulo: quitarNumero(p), bloques: new Map() }]));
  for (const it of modelo.items) {
    if (DIAG_CODIGOS.has(it.codigo) || it.tipoCampo === "auto") continue;
    const g = grupoDe(it);
    if (!it.grupos.includes("COMUN") && !g) continue;
    const t = tabs.get(it.pestana);
    if (!t) continue;
    let clave = it.bloque || "", grupo = null;
    if (it.pestana === pestDiag && g) { clave = "g:" + g; grupo = g; }
    if (!t.bloques.has(clave)) t.bloques.set(clave, { subtitulo: grupo ? ENFERMEDADES[grupo]?.nombre || grupo : it.bloque || "", grupo, items: [] });
    t.bloques.get(clave).items.push(it);
  }
  const out = [];
  for (const t of tabs.values()) {
    let bloques = [...t.bloques.values()];
    if (t.id === "p:" + pestDiag) bloques.sort((a, b) => activos.indexOf(a.grupo) - activos.indexOf(b.grupo));
    if (bloques.length) out.push({ ...t, bloques });
  }
  return out;
}

export function visible(it, v) {
  return it.cond.fn(v);
}

// Respuestas especiales en preguntas Sí/No y listas
export const NC = "NC";     // Desconocido: se buscó y no consta (cuenta como respondido)
export const DUDA = "DUDA"; // Duda: pendiente de revisar por un data manager (no cuenta)
export const esMarca = (x) => x === NC || x === DUDA;
export const marcaDe = (it, v) => (it.tipoCampo === "single" || it.tipoCampo === "multi" ? v[it.codigo] : esMarca(v[it.codigo]) ? v[it.codigo] : null);
export const admiteMarcas = (it) => ["sino", "sinofecha", "single", "multi"].includes(it.tipoCampo);

/** Cuenta campos respondidos / totales en una lista de items visibles. */
export function progresoItems(items, v) {
  let tot = 0, ok = 0;
  for (const it of items) {
    if (!visible(it, v)) continue;
    const m = admiteMarcas(it) ? marcaDe(it, v) : null;
    if (m === NC) { tot++; ok++; continue; }
    if (m === DUDA) { tot++; continue; }
    switch (it.tipoCampo) {
      case "fijo": case "caso": case "auto": case "texto": continue;
      case "single": tot++; if (it.opciones.some((o) => v[o.codigo] === 1)) ok++; break;
      case "multi": tot++; if (it.opciones.some((o) => v[o.codigo] === 1 || v[o.codigo] === 0)) ok++; break;
      case "sinofecha": tot++; if (v[it.codigo] === 0 || (v[it.codigo] === 1 && v[it.codigo + "_date"])) ok++; break;
      default: tot++; if (v[it.codigo] !== undefined && v[it.codigo] !== null && v[it.codigo] !== "") ok++;
    }
  }
  return { ok, tot, pct: tot ? Math.round((100 * ok) / tot) : 100 };
}

export function progresoPestana(t, v) {
  return progresoItems(t.bloques.flatMap((b) => b.items), v);
}

export function progresoCaso(modelo, caso) {
  const tabs = pestanasDelCaso(modelo, caso);
  return progresoItems(tabs.flatMap((t) => t.bloques.flatMap((b) => b.items)), caso.valores);
}

/** "Marcar el resto como No": solo campos Sí/No y listas múltiples sin tocar. */
export function rellenarNo(items, v) {
  const cambios = {};
  for (const it of items) {
    if (!visible(it, { ...v, ...cambios })) continue;
    if ((it.tipoCampo === "sino" || it.tipoCampo === "sinofecha") && (v[it.codigo] === undefined || v[it.codigo] === null)) {
      cambios[it.codigo] = 0;
    }
    if (it.tipoCampo === "multi" && !esMarca(v[it.codigo]) && it.opciones.every((o) => v[o.codigo] === undefined || v[o.codigo] === null)) {
      it.opciones.forEach((o) => (cambios[o.codigo] = 0));
    }
  }
  return cambios;
}

/** Dudas abiertas de un caso: [{codigo, etiqueta, pestana, nota}] */
export function dudasDelCaso(modelo, caso) {
  const out = [];
  for (const t of pestanasDelCaso(modelo, caso)) {
    for (const b of t.bloques) for (const it of b.items) {
      if (admiteMarcas(it) && visible(it, caso.valores) && marcaDe(it, caso.valores) === DUDA) {
        out.push({ codigo: it.codigo, etiqueta: it.etiqueta, pestana: t.id, tituloPestana: t.titulo, nota: caso.valores[it.codigo + "_duda_nota"] || "" });
      }
    }
  }
  return out;
}

/**
 * Valores por defecto (columna valor_por_defecto del diccionario).
 *  · un valor fijo ("1", "HCUVA") se aplica al crear el caso;
 *  · una regla "a = 1 -> 0 ; b = 1 -> 1" se aplica cuando cambia a o b y el campo está vacío.
 */
export function valoresPorDefecto(modelo, v, { soloReglas = false, cambiados = null } = {}) {
  const out = {};
  const todos = modelo.items.flatMap((it) => [it, ...(it.opciones || [])]);
  for (const it of todos) {
    const d = String(it.defecto ?? "").trim();
    if (!d || (v[it.codigo] !== undefined && v[it.codigo] !== null)) continue;
    if (d.includes("->")) {
      for (const regla of d.split(";")) {
        const m = regla.match(/([a-z0-9_]+)\s*=\s*(\S+)\s*->\s*(\S+)/i);
        if (!m) continue;
        if (cambiados && !(m[1] in cambiados)) continue;
        if (String(v[m[1]]) === m[2]) { out[it.codigo] = isNaN(+m[3]) ? m[3] : +m[3]; break; }
      }
    } else if (!soloReglas) out[it.codigo] = isNaN(+d) ? d : +d;
  }
  return out;
}

export { GRUPOS };
