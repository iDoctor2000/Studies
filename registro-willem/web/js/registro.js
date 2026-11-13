// Formato final del registro WILLEM: columnas y fila de cada caso.
// Lo usan la exportación a Excel y el envío directo al Excel corporativo.
//
// Reglas acordadas:
//  · Sí = 1, No = 0.
//  · Desconocido / Duda = en blanco.
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
export function valorador(dic, cabecera = cabeceraRegistro(dic)) {
  const cp = copias(dic);
  const conjunto = new Set(cabecera);
  const bruto = (v, k) => v[cp[k] || k];
  return (caso, col) => {
    if (col === "site_id") return SITE_ID;
    if (col === "patient_id") return caso.numero;
    if (col === "authored_at") return caso.creado || caso.valores.authored_at || "";
    const v = caso.valores;
    const x = bruto(v, col);
    if (col.endsWith("_date") && conjunto.has(col.slice(0, -5))) {
      if (x != null && x !== "" && !MARCAS.includes(x)) return x;
      const b = bruto(v, col.slice(0, -5));
      return b === 0 || b === 1 ? 0 : "";
    }
    return x == null || MARCAS.includes(x) ? "" : x;
  };
}

export function filaRegistro(dic, caso, cabecera = cabeceraRegistro(dic)) {
  const val = valorador(dic, cabecera);
  return cabecera.map((c) => val(caso, c));
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

/** [{diagnostico, fila}] — una entrada por diagnóstico del caso. */
export function filasDelCaso(dic, caso, cabecera = cabeceraRegistro(dic)) {
  const val = valorador(dic, cabecera);
  const campo = campoPorColumna(dic);
  return diagnosticosDelCaso(caso).map((g) => {
    const vista = { ...caso, valores: valoresParaDiagnostico(caso, g) };
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
