// Propuestas de la IA local (fase 2): importación y estado de revisión.
// Misma lógica que servidor.py (importar_propuesta / ia_pendientes), para el modo navegador.
//
//  caso.ia = { codigoPregunta: { valor_texto, cita, aviso, origen, codigos:[campos], revisado } }
//  caso.informes = [{ fecha_ingreso, fecha_alta, servicio, titulo, texto, indice }]
// Un dato de la IA queda "pendiente" hasta que una persona lo confirma, lo cambia o lo borra.

export const NOMBRE_ORIGEN = { ia: "IA", cabecera: "cabecera del informe", calculado: "calculado de los reingresos", deducido: "deducido" };

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
    if (cods.some((c) => tieneValor(v[c]) && !deIA.has(c))) { omitidos++; continue; }
    for (const c of cods) {
      const nuevo = p.valores?.[c] ?? null;
      if ((v[c] ?? null) !== nuevo) auditoria.push([c, v[c] ?? null, nuevo]);
      if (nuevo === null) delete v[c]; else v[c] = nuevo;
    }
    caso.ia[k] = { valor_texto: String(meta.valor_texto ?? ""), cita: String(meta.cita ?? ""), aviso: String(meta.aviso ?? ""),
      origen: meta.origen || "ia", codigos: cods, revisado: false };
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
