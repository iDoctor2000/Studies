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
export const MARCAS = ["NC", "DUDA"];
const FIJAS = ["site_id", "patient_id", "authored_at"];

export function columnasRegistro(dic, soloLocal = false) {
  const cols = [];
  for (const f of [...dic.campos, ...(dic.locales || [])]) {
    const exp = String(f.exportar_al_registro || "");
    const esLocal = exp.toLowerCase().startsWith("solo local");
    if (exp.toLowerCase() === "no" || esLocal !== soloLocal) continue;
    const spec = String(f.columnas_en_exportacion || f.codigo_variable);
    if (spec.startsWith("(")) continue;
    spec.split(";").map((c) => c.trim()).filter(Boolean).forEach((c) => cols.push(c));
  }
  return cols;
}

/** Cabecera del Excel final, en el orden del registro. */
export function cabeceraRegistro(dic) {
  return [...FIJAS, ...columnasRegistro(dic).filter((c) => !FIJAS.includes(c))];
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

/** Huella de la fila: sirve para saber si un caso enviado ha cambiado después. */
export function huella(fila) {
  let h = 0x811c9dc5;
  const s = JSON.stringify(fila);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0");
}
