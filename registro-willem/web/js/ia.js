// Propuestas de la IA local (fase 2): importación y estado de revisión.
// Misma lógica que servidor.py (importar_propuesta / ia_pendientes), para el modo navegador.
//
//  caso.ia = { codigoPregunta: { valor_texto, cita, aviso, origen, codigos:[campos], revisado } }
//  caso.informes = [{ fecha_ingreso, fecha_alta, servicio, titulo, texto, indice }]
// Un dato de la IA queda "pendiente" hasta que una persona lo confirma, lo cambia o lo borra.

export const NOMBRE_ORIGEN = { ia: "IA", cabecera: "cabecera del informe", calculado: "calculado de los reingresos", deducido: "deducido",
  nombre: "deducido del nombre (en el Mac; el nombre no se guarda)" };

const tieneValor = (x) => x !== null && x !== undefined && x !== "";

/** Claves de c.ia pendientes de revisar (con algún valor aún puesto). */
export function iaPendientes(caso) {
  const ia = caso?.ia || {}, v = caso?.valores || {};
  return Object.keys(ia).filter((k) => !ia[k].revisado && (k === "_diagnosticos" || (ia[k].codigos || []).some((c) => tieneValor(v[c]))));
}

/** Marca como revisadas las entradas que tocan alguno de los campos cambiados. Devuelve las claves marcadas. */
export function marcarPorCampos(ia, campos) {
  const set = new Set(campos), out = [];
  for (const [k, m] of Object.entries(ia || {})) {
    if (!m.revisado && (m.codigos || []).some((c) => set.has(c))) { m.revisado = true; out.push(k); }
  }
  return out;
}

/**
 * Aplica una propuesta de la IA a un caso (o crea el caso).
 * Nunca pisa lo que haya escrito una persona: solo rellena campos vacíos o que aún tengan un dato de la IA sin revisar.
 * Devuelve { caso, accion: "creado"|"actualizado"|"omitido", aplicados, omitidos, motivo, auditoria:[[campo, antes, despues]] }
 */
export function aplicarPropuesta(caso, p, { principales, diagnosticos, siteId, usuario, ahora }) {
  if (p?.formato !== "willem-propuesta-ia/1") return { accion: "omitido", motivo: "No es un archivo de propuestas de la IA" };
  const num = parseInt(p.numero_caso, 10);
  if (!(num > 0)) return { accion: "omitido", motivo: "Número de caso no válido" };
  if (caso?.estado === "validado") return { accion: "omitido", motivo: "El caso ya está validado" };
  // Un caso creado a mano con el mismo número podría ser OTRO paciente: nunca se mezcla
  if (caso && !Object.keys(caso.ia || {}).length) return { accion: "omitido", motivo: "Ya existe un caso con ese número creado a mano. Compruebe que la numeración del libro llave del Mac continúa la del registro (Estación → Ajustes → primer número)" };
  const auditoria = [];
  const t = ahora;
  let accion = "actualizado";
  if (!caso) {
    accion = "creado";
    const diags = (p.diagnosticos || []).map((d) => d.codigo).filter((g) => principales.includes(g));
    const principal = diags[0] || "OTRO";
    const sec = diags.slice(1);
    const otro = (p.diagnosticos || []).find((d) => d.codigo === "OTRO");
    caso = { numero: num, principal, secundarias: sec, estado: "borrador",
      valores: { site_id: siteId, patient_id: num, authored_at: t, ...diagnosticos(principal, sec) },
      creado: t, creado_por: usuario, modificado: t, modificado_por: usuario, ia: {}, informes: [] };
    if (principal === "OTRO" || sec.includes("OTRO")) caso.valores.other_disease = (otro?.texto || "").trim() || "Pendiente de revisar (propuesto por la IA)";
    const lista = diags.length ? diags : ["OTRO"];
    caso.ia._diagnosticos = {
      valor_texto: lista.join(", "), origen: "ia", revisado: false,
      cita: (p.diagnosticos || []).map((d) => `${d.codigo}: ${d.cita}`).join("\n"),
      aviso: [diags.length ? "" : "La IA no ha identificado ningún diagnóstico del estudio", ...(p.diagnosticos || []).map((d) => d.aviso).filter(Boolean)].filter(Boolean).join("; "),
      codigos: ["_diagnosticos"],
    };
    auditoria.push(["(caso creado)", null, principal]);
  }
  caso.ia = caso.ia || {};
  caso.informes = caso.informes || [];
  const v = caso.valores;
  // campos que tienen ahora un dato de la IA sin revisar: se pueden actualizar
  const deIA = new Set(Object.values(caso.ia).filter((m) => !m.revisado).flatMap((m) => m.codigos || []));
  let aplicados = 0, omitidos = 0;
  for (const [k, meta] of Object.entries(p.ia || {})) {
    const cods = (meta.codigos || []).filter((c) => /^[a-z0-9_]{1,80}$/.test(c) && !["site_id", "patient_id", "authored_at"].includes(c));
    if (!cods.length) continue;
    const nuevos = Object.fromEntries(cods.map((c) => [c, p.valores?.[c] ?? null]));
    const previo = caso.ia[k];
    // una persona ya revisó (confirmó, corrigió o quitó) esta misma propuesta: no se repite
    if (previo?.revisado && previo.valores_ia && JSON.stringify(previo.valores_ia) === JSON.stringify(nuevos)) { omitidos++; continue; }
    if (cods.some((c) => tieneValor(v[c]) && !deIA.has(c))) { omitidos++; continue; }
    for (const c of cods) {
      const nuevo = p.valores?.[c] ?? null;
      if ((v[c] ?? null) !== nuevo) auditoria.push([c, v[c] ?? null, nuevo]);
      if (nuevo === null) delete v[c]; else v[c] = nuevo;
    }
    caso.ia[k] = { valor_texto: String(meta.valor_texto ?? ""), cita: String(meta.cita ?? ""), aviso: String(meta.aviso ?? ""),
      origen: meta.origen || "ia", codigos: cods, revisado: false, valores_ia: nuevos };
    aplicados++;
  }
  for (const inf of p.informes || []) {
    const i = caso.informes.findIndex((x) => x.fecha_ingreso === inf.fecha_ingreso);
    const limpio = { fecha_ingreso: inf.fecha_ingreso, fecha_alta: inf.fecha_alta, servicio: inf.servicio, titulo: inf.titulo, texto: String(inf.texto || ""), indice: !!inf.indice };
    if (i >= 0) caso.informes[i] = limpio; else caso.informes.push(limpio);
  }
  caso.informes.sort((a, b) => String(a.fecha_ingreso).localeCompare(String(b.fecha_ingreso)));
  caso.modificado = t; caso.modificado_por = usuario;
  return { caso, accion, aplicados, omitidos, auditoria };
}

// ---------------------------------------------------------------------------
//  AUDITORÍA: ¿qué tal acierta la IA en cada variable?
//  Compara lo que propuso (valores_ia) con lo que ha quedado tras la revisión humana.
// ---------------------------------------------------------------------------
const esNo = (t) => /^(no|ninguno|ninguna)$/i.test(String(t).trim());
// Los diagnósticos del estudio se proponen y se auditan aparte (fila «Diagnósticos del estudio»)
const DE_DIAGNOSTICO = new Set(["ischemic_cardiomyopathy", "heart_failure", "aortic_stenosis", "hypertrophic_cardiomyopathy", "long_qt_syndrome",
  "amyloidosis_attr", "myocardial_infarction", "hypertensive_disease", "other_disease"]);
export const FILA_DIAGNOSTICOS = { codigo: "_diagnosticos", etiqueta: "Diagnósticos del estudio", pestana: "1. Diagnósticos", tipoCampo: "diagnosticos", pista: "" };
export const diagnosticosTexto = (c) => [c.principal, ...(c.secundarias || [])].filter(Boolean).join(", ");

/** Códigos de campo de una pregunta del formulario. */
export const codigosDe = (it) => (it.opciones ? it.opciones.map((o) => o.codigo) : [it.codigo]);

/** ¿Ha anotado una persona un dato positivo en esta pregunta? (no cuenta «No» ni Desconocido) */
function datoPositivo(it, v) {
  if (v[it.codigo] === "NC" || v[it.codigo] === "DUDA") return false;
  if (it.opciones) return it.opciones.some((o) => v[o.codigo] === 1 && !esNo(o.etiqueta));
  if (it.tipoCampo === "sino" || it.tipoCampo === "sinofecha") return v[it.codigo] === 1;
  return v[it.codigo] !== undefined && v[it.codigo] !== null && v[it.codigo] !== "";
}

/** Estado de una propuesta de la IA en un caso: pendiente | confirmado | corregido | quitado | revisado */
export function estadoPropuesta(m, v) {
  if (!m.revisado) return "pendiente";
  if (!m.valores_ia) return "revisado";
  const cods = Object.keys(m.valores_ia);
  if (cods.every((c) => !tieneValor(v[c]))) return "quitado";
  return cods.every((c) => (v[c] ?? null) === (m.valores_ia[c] ?? null)) ? "confirmado" : "corregido";
}

/**
 * Devuelve { casosIA, filas:[{it, propuestos, avisos, pendiente, confirmado, corregido, quitado, revisado, olvidos, acierto, detalle:[...] }] }
 * detalle: {numero, estado, ia: texto propuesto, cita, aviso}
 */
export function auditar(items, casos) {
  const conIA = casos.filter((c) => Object.keys(c.ia || {}).some((k) => k !== "_diagnosticos"));
  const filas = [];
  {  // diagnósticos: lo que propuso la IA frente a los que tiene ahora el caso
    const f = { it: FILA_DIAGNOSTICOS, propuestos: 0, avisos: 0, pendiente: 0, confirmado: 0, corregido: 0, quitado: 0, revisado: 0, olvidos: 0, detalle: [] };
    for (const c of casos) {
      const m = c.ia?._diagnosticos;
      if (!m) continue;
      const e = !m.revisado ? "pendiente" : m.valor_texto === diagnosticosTexto(c) ? "confirmado" : "corregido";
      f.propuestos++; f[e]++;
      if (m.aviso) f.avisos++;
      f.detalle.push({ numero: c.numero, estado: e, ia: m.valor_texto, cita: m.cita, aviso: m.aviso, origen: "ia" });
    }
    const j = f.confirmado + f.corregido;
    f.acierto = j ? f.confirmado / j : null;
    f.problemas = f.corregido;
    filas.push(f);
  }
  for (const it of items) {
    if (["fijo", "caso", "auto", "calculado"].includes(it.tipoCampo) || DE_DIAGNOSTICO.has(it.codigo)) continue;
    const f = { it, propuestos: 0, avisos: 0, pendiente: 0, confirmado: 0, corregido: 0, quitado: 0, revisado: 0, olvidos: 0, detalle: [] };
    for (const c of conIA) {
      const m = c.ia[it.codigo];
      if (m) {
        const e = estadoPropuesta(m, c.valores);
        f.propuestos++; f[e]++;
        if (m.aviso) f.avisos++;
        f.detalle.push({ numero: c.numero, estado: e, ia: m.valor_texto, cita: m.cita, aviso: m.aviso, origen: m.origen });
      } else if (datoPositivo(it, c.valores)) {
        f.olvidos++;
        f.detalle.push({ numero: c.numero, estado: "olvido", ia: "", cita: "", aviso: "" });
      }
    }
    const juzgados = f.confirmado + f.corregido + f.quitado;
    f.acierto = juzgados ? f.confirmado / juzgados : null;
    f.problemas = f.corregido + f.quitado + f.olvidos;
    filas.push(f);
  }
  return { casosIA: conIA.length, filas };
}
