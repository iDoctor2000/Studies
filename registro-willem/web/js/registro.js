// Formato final del registro WILLEM: columnas y fila de cada caso.
// Lo usan la exportación a Excel y el envío directo al Excel corporativo.
//
// Reglas acordadas:
//  · Sí = 1, No = 0.
//  · Desconocido / Duda = en blanco. (Opción al exportar: Desconocido como -1 y, en fechas, 0000-00-00.)
//  · Columnas de fecha asociadas a un Sí/No (p. ej. hypertension_date):
//      fecha si la hay; 0 si la pregunta está contestada (Sí o No) pero no hay fecha;
//      en blanco si la pregunta es Desconocido, Duda o no se ha contestado.
//  · Campos calculados (copiar_de) toman el valor de otro campo.

export const SITE_ID = "HCUVA";

// Diagnósticos del estudio y su variable en el registro. "OTRO" se describe en other_disease.
export const DIAG = {
  ISQ: "ischemic_cardiomyopathy", IC: "heart_failure", EAO: "aortic_stenosis", MCH: "hypertrophic_cardiomyopathy",
  QTL: "long_qt_syndrome", ATTR: "amyloidosis_attr", IAM: "myocardial_infarction", HTA: "hypertensive_disease",
};
export const diagnosticosDelCaso = (caso) => [caso.principal, ...(caso.secundarias || [])].filter(Boolean);
export const MARCAS = ["NC", "DUDA"];
const FIJAS = ["site_id", "patient_id", "authored_at"];

// Las columnas del Excel final siguen SIEMPRE el orden del CRF original (columna orden_registro),
// aunque el formulario muestre los campos en otro orden.
const ordenRegistro = (f) => (Number(f.orden_registro) > 0 ? Number(f.orden_registro) : 1e6);
export function columnasRegistro(dic, soloLocal = false) {
  const cols = [];
  const campos = [...dic.campos, ...(dic.locales || [])].map((f, i) => [f, i]).sort((a, b) => ordenRegistro(a[0]) - ordenRegistro(b[0]) || a[1] - b[1]).map(([f]) => f);
  for (const f of campos) {
    const exp = String(f.exportar_al_registro || "");
    const esLocal = exp.toLowerCase().startsWith("solo local");
    if (exp.toLowerCase() === "no" || esLocal !== soloLocal) continue;
    const spec = String(f.columnas_en_exportacion || f.codigo_variable);
    if (spec.startsWith("(")) continue;
    spec.split(";").map((c) => c.trim()).filter(Boolean).forEach((c) => cols.push(c));
  }
  return cols;
}

/** Cabecera del Excel final: exactamente las columnas del CRF original, en su orden. */
export function cabeceraRegistro(dic) {
  const cols = columnasRegistro(dic);
  return [...FIJAS.filter((c) => !cols.includes(c)), ...cols];
}

function copias(dic) {
  return Object.fromEntries(dic.campos.filter((d) => String(d.copiar_de || "").trim()).map((d) => [String(d.codigo_variable), String(d.copiar_de).trim()]));
}

/** Devuelve una función (caso, columna) -> valor exportado. */
export const FECHA_DESCONOCIDA = "0000-00-00";
/** opciones.desconocido: "blanco" (por defecto) o "-1" (Desconocido = -1; en fechas, 0000-00-00). La Duda va siempre en blanco. */
export function valorador(dic, cabecera = cabeceraRegistro(dic), opciones = {}) {
  const cp = copias(dic);
  const conjunto = new Set(cabecera);
  const campo = campoPorColumna(dic);
  const menos1 = opciones.desconocido === "-1";
  const esFecha = (col) => col.endsWith("_date") || /^date/.test(String(campo[col]?.tipo_formulario || campo[col]?.tipo || ""));
  const bruto = (v, k) => v[cp[k] || k];
  return (caso, col) => {
    if (col === "site_id") return SITE_ID;
    if (col === "patient_id") return caso.numero;
    if (col === "authored_at") return caso.creado || caso.valores.authored_at || "";
    const v = caso.valores;
    const x = bruto(v, col);
    if (menos1 && x === "NC") return esFecha(col) ? FECHA_DESCONOCIDA : -1;
    if (col.endsWith("_date") && conjunto.has(col.slice(0, -5))) {
      if (x != null && x !== "" && !MARCAS.includes(x)) return x;
      const b = bruto(v, col.slice(0, -5));
      return b === 0 || b === 1 ? 0 : "";
    }
    return x == null || MARCAS.includes(x) ? "" : x;
  };
}

export function filaRegistro(dic, caso, cabecera = cabeceraRegistro(dic), opciones = {}) {
  const val = valorador(dic, cabecera, opciones);
  const vista = { ...caso, valores: prepararValores(dic, caso, { ...caso.valores }) };
  return cabecera.map((c) => val(vista, c));
}

// ---------------------------------------------------------------------------
// UNA FILA POR DIAGNÓSTICO
// Un paciente con varias patologías sale en el Excel como una fila por patología:
//  · mismo patient_id (nº de caso) en todas: los ECG se enlazarán después por el CIP;
//  · en cada fila, su diagnóstico = 1 y los demás diagnósticos del estudio = 0;
//  · datos comunes repetidos; campos específicos solo los de esa patología.
// ---------------------------------------------------------------------------
const _campos = new WeakMap();
function campoPorColumna(dic) {
  if (_campos.has(dic)) return _campos.get(dic);
  const m = {};
  for (const f of [...dic.campos, ...(dic.locales || [])]) {
    const spec = String(f.columnas_en_exportacion || f.codigo_variable);
    if (spec.startsWith("(")) continue;
    spec.split(";").map((c) => c.trim()).filter(Boolean).forEach((c) => (m[c] = f));
  }
  _campos.set(dic, m);
  return m;
}

function aplicaA(f, g) {
  if (!f) return true;
  const grupos = String(f.patologias || "COMUN").toUpperCase().split(/[\s,;]+/).filter(Boolean);
  if (!grupos.includes("COMUN") && !grupos.includes(g)) return false;
  const cond = String(f.mostrar_solo_si || "");
  return !Object.entries(DIAG).some(([G, c]) => G !== g && new RegExp(`\\b${c}\\b`).test(cond));
}

/** Valores del caso vistos desde un diagnóstico concreto. */
export function valoresParaDiagnostico(caso, g) {
  const v = { ...caso.valores };
  for (const [G, c] of Object.entries(DIAG)) v[c] = G === g ? 1 : 0;
  if (g !== "OTRO") delete v.other_disease;
  return v;
}

// ---------------------------------------------------------------------------
// CAMPOS CALCULADOS (columna "calcular" del diccionario)
//   "CONDICIÓN -> VALOR ; CONDICIÓN -> VALOR | fecha: CAMPO"
//   · gana la primera regla que se cumple; "y" une condiciones;
//   · VALOR es un número o el nombre de otro campo;
//   · si ninguna se cumple, el campo queda en blanco;
//   · "| fecha: CAMPO": si el resultado es 1, su columna _date toma la fecha de CAMPO.
// ---------------------------------------------------------------------------
const OPS = { "<=": (a, b) => a <= b, ">=": (a, b) => a >= b, "!=": (a, b) => a != b, "<": (a, b) => a < b, ">": (a, b) => a > b, "=": (a, b) => a == b };
const num = (x) => (x !== "" && x !== null && !isNaN(+x) ? +x : x);
const vacio = (x) => x === undefined || x === null || x === "";
const esNumero = (x) => typeof x === "number" && isFinite(x);

/** Años cumplidos entre dos fechas AAAA-MM-DD. */
export function edadEn(nacimiento, fecha) {
  const a = String(nacimiento || "").match(/^(\d{4})-(\d{2})-(\d{2})/), b = String(fecha || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!a || !b) return null;
  let e = +b[1] - +a[1];
  if (b[2] + b[3] < a[2] + a[3]) e--;
  return e >= 0 && e < 130 ? e : null;
}

// Cálculos programados: "calcular = funcion: NOMBRE". Devuelven el valor, o undefined si no se puede calcular
// (entonces se respeta lo que hubiera). Mismas fórmulas que servidor.py.
export const FUNCIONES = {
  /** Filtrado glomerular MDRD-4 (IDMS): 175 × Cr^-1,154 × edad^-0,203 × 0,742 si mujer. Edad en la fecha de la analítica. */
  mdrd(v, ctx) {
    const cr = v.creatinine;
    const sexo = v.biological_sex_female === 1 ? 0.742 : v.biological_sex_male === 1 ? 1 : null;
    if (!esNumero(cr) || cr <= 0 || sexo === null) return undefined;
    const diag = Object.keys(v).filter((k) => k.endsWith("_diagnosis_date") && /^\d{4}-/.test(String(v[k]))).map((k) => v[k]).sort()[0];
    const ref = [v.laboratory_biomarkers_test, diag, ctx.creado].find((f) => /^\d{4}-\d{2}-\d{2}/.test(String(f || "")));
    const edad = edadEn(v.dob, ref);
    if (!edad) return undefined;
    return Math.round(175 * Math.pow(cr, -1.154) * Math.pow(edad, -0.203) * sexo * 10) / 10;
  },
  /** Síndrome cardiorrenal: IC (diagnóstico del estudio o ingreso previo por IC) + (ERC o MDRD < 60). */
  sindrome_cardiorrenal(v, ctx) {
    const previo = v.prior_heart_failure_hospitalization;
    const ic = (ctx.diagnosticos || []).includes("IC") || previo === 1 ? 1 : previo === 0 ? 0 : previo === "NC" ? "NC" : "DUDA";
    // el filtrado se calcula aquí mismo: en el diccionario va después y aún no estaría hecho
    const erc = v.chronic_kidney_disease, fg = FUNCIONES.mdrd(v, ctx) ?? v.glomerular_filtration_rate_mdrd;
    const renal = erc === 1 || (esNumero(fg) && fg < 60) ? 1 : erc === 0 ? 0 : erc === "NC" ? "NC" : "DUDA";
    if (ic === 1 && renal === 1) return 1;
    if (ic === 0 || renal === 0) return 0;
    return ic === "DUDA" || renal === "DUDA" ? "DUDA" : "NC";
  },
};

/** ¿Se cumple "a = 1 O b = 1 Y c != 0"? (misma gramática que mostrar_solo_si) */
export function cumpleCondicion(texto, v) {
  const c = String(texto || "").trim();
  if (!c) return true;
  return c.split(/\s+O\s+/i).some((parte) => parte.split(/\s+Y\s+/i).every((t) => {
    const m = t.match(/([a-z0-9_]+)\s*(=|!=)\s*(\S+)/i);
    if (!m) return true;
    const val = isNaN(+m[3]) ? m[3] : +m[3];
    return m[2] === "=" ? v[m[1]] == val : v[m[1]] != val;
  }));
}

/**
 * Valores por defecto al exportar (columna valor_por_defecto):
 *  · regla "a = 0 -> 0": si el campo está vacío, o no se muestra (su condición no se cumple), y la regla se cumple;
 *  · valor fijo ("1"): solo en campos ocultos que estén vacíos (p. ej. criterios de elegibilidad).
 */
export function aplicarDefectos(dic, v) {
  for (const f of dic.campos) {
    const d = String(f.valor_por_defecto ?? "").trim();
    if (!d) continue;
    const cod = String(f.codigo_variable);
    if (d.includes("->")) {
      if (!vacio(v[cod]) && cumpleCondicion(f.mostrar_solo_si, v)) continue;
      for (const regla of d.split(";")) {
        const m = regla.match(/([a-z0-9_]+)\s*=\s*(\S+)\s*->\s*(\S+)/i);
        if (m && String(v[m[1]]) === m[2]) { v[cod] = isNaN(+m[3]) ? m[3] : +m[3]; break; }
      }
    } else if (vacio(v[cod]) && /^s[ií]$/i.test(String(f.oculto || "").trim())) v[cod] = isNaN(+d) ? d : +d;
  }
  return v;
}

/** Valores listos para exportar o mostrar: por defecto + calculados. ctx = { diagnosticos, creado } */
export function prepararValores(dic, caso, v = { ...caso.valores }) {
  aplicarDefectos(dic, v);
  return aplicarCalculos(dic, v, { diagnosticos: diagnosticosDelCaso(caso), creado: caso.creado });
}

export function aplicarCalculos(dic, v, ctx = {}) {
  for (const f of dic.campos) {
    const spec = String(f.calcular || "").trim();
    if (!spec) continue;
    const fn = spec.match(/^funcion:\s*([a-z0-9_]+)/i);
    if (fn) {
      const res = FUNCIONES[fn[1]]?.(v, ctx);
      if (res !== undefined) v[String(f.codigo_variable)] = res;
      continue;
    }
    const [reglas, extra] = spec.split("|");
    const fecha = (extra || "").match(/fecha:\s*([a-z0-9_]+)/i)?.[1];
    let res;
    for (const regla of reglas.split(";")) {
      const [cond, valor] = regla.split("->").map((x) => x && x.trim());
      if (!cond || valor === undefined) continue;
      const cumple = cond.split(/\s+y\s+/i).every((at) => {
        const m = at.trim().match(/^([a-z0-9_]+)\s*(<=|>=|!=|<|>|=)\s*(\S+)$/i);
        if (!m) return false;
        const x = v[m[1]];
        if (x === undefined || x === null || x === "" || MARCAS.includes(x)) return false;
        return OPS[m[2]](num(x), num(m[3]));
      });
      if (cumple) { res = /^-?\d+(\.\d+)?$/.test(valor) ? +valor : v[valor]; break; }
    }
    const cod = String(f.codigo_variable);
    if (res === undefined || res === null || res === "") { delete v[cod]; delete v[cod + "_date"]; continue; }
    v[cod] = res;
    if (fecha) { if (res === 1 && v[fecha]) v[cod + "_date"] = v[fecha]; else delete v[cod + "_date"]; }
  }
  return v;
}

/** [{diagnostico, fila}] — una entrada por diagnóstico del caso. */
export function filasDelCaso(dic, caso, cabecera = cabeceraRegistro(dic), opciones = {}) {
  const val = valorador(dic, cabecera, opciones);
  const campo = campoPorColumna(dic);
  return diagnosticosDelCaso(caso).map((g) => {
    const vista = { ...caso, valores: prepararValores(dic, caso, valoresParaDiagnostico(caso, g)) };
    return { diagnostico: g, fila: cabecera.map((c) => (aplicaA(campo[c], g) ? val(vista, c) : "")) };
  });
}

/** Huella de la fila: sirve para saber si un caso enviado ha cambiado después. */
export function huella(fila) {
  let h = 0x811c9dc5;
  const s = JSON.stringify(fila);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0");
}
