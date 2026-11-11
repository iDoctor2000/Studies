// Importación de informes 100 % LOCAL: anonimización + extracción por reglas.
// El texto nunca sale del navegador y no se guarda en ningún sitio.

// ---------------------------------------------------------------------------
// 1) ANONIMIZACIÓN
// ---------------------------------------------------------------------------
const CABECERA = /^\s*(paciente|nombre|apellidos?|nhc|n\.?\s?h\.?\s?c\.?|n[º°o]?\s*(de\s*)?historia|historia\s+cl[ií]nica|cip|sip|carm|tarjeta|dni|nif|nie|pasaporte|f(echa)?\.?\s*(de\s*)?nac(imiento)?|direcci[oó]n|domicilio|poblaci[oó]n|localidad|c\.?\s?p\.?|tel[eé]fono|tfno|m[oó]vil|e-?mail|correo|cama|habitaci[oó]n|n[º°]\s*episodio|episodio|asegurad|aseguradora|m[eé]dico\s+(solicitante|responsable)|solicitado\s+por|fdo\.?|firmado)\b.*$/gim;

const PATRONES = [
  ["DNI/NIE", /\b(?:\d{8}\s?-?[A-HJ-NP-TV-Z]|[XYZ]\s?-?\d{7}\s?-?[A-HJ-NP-TV-Z])\b/g],
  ["NHC", /\b(?:NHC|N\.\s?H\.\s?C\.?|historia(?:\s+cl[ií]nica)?|n[º°o]\s*historia)\s*[:#nº°.\-]*\s*\d{4,10}\b/gi],
  ["CIP/SIP", /\b(?:CIP|SIP|CARM|tarjeta\s+sanitaria)\s*[:#nº°.\-]*\s*[A-Z0-9]{6,20}\b/gi],
  ["CIP", /\b[A-Z]{4}\d{6,10}\b/g],
  ["Teléfono", /(?<![\d/.,-])(?:\+34\s?)?[6789]\d{2}[\s.-]?\d{2,3}[\s.-]?\d{2,3}[\s.-]?\d{0,3}(?![\d/.,-])/g],
  ["Email", /\b[\w.+-]+@[\w-]+\.[\w.]+\b/g],
  ["Nombre", /\b(?:D\.ª|D\.|Dña\.?|Don|Doña|Sr\.|Sra\.|Dr\.|Dra\.)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de\s+|del\s+|la\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3}/g],
  ["Nombre", /\b[A-ZÁÉÍÓÚÑ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ]{2,}){1,3},\s*[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]+)?/g],
  ["Dirección", /\b(?:C\/|Calle|Avda\.?|Avenida|Plaza|Pza\.?|Ctra\.?|Carretera|Camino)\s+[^\n,;]{2,40}(?:,?\s*n?[º°]?\s*\d+)?/gi],
  ["C.P.", /\b30\d{3}(?=\s+(?:\(|[A-ZÁÉÍÓÚ][a-záéíóúñ]+))/g],
];

/** Devuelve { texto, marcas:[{tipo, original}] } */
export function anonimizar(texto, { quitarCabecera = true } = {}) {
  const marcas = [];
  let t = texto.replace(/\r/g, "");
  if (quitarCabecera) {
    t = t.replace(CABECERA, (m) => {
      marcas.push({ tipo: "Línea de cabecera", original: m.trim() });
      return "[CABECERA ELIMINADA]";
    });
    t = t.replace(/(\[CABECERA ELIMINADA\]\n?){2,}/g, "[CABECERA ELIMINADA]\n");
  }
  for (const [tipo, re] of PATRONES) {
    t = t.replace(re, (m) => {
      if (/^\[/.test(m)) return m;
      marcas.push({ tipo, original: m.trim() });
      return `[${tipo.toUpperCase()}]`;
    });
  }
  return { texto: t, marcas };
}

// ---------------------------------------------------------------------------
// 2) EXTRACCIÓN POR REGLAS
// ---------------------------------------------------------------------------
const NUM = String.raw`(-?\d{1,3}(?:\.\d{3})+|-?\d+(?:[.,]\d+)?)`;
const n = (s) => {
  s = String(s).trim();
  if (/^-?\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  return +s.replace(",", ".");
};
const SEP = String.raw`[^\d\n-]{0,28}?`;

// Valores numéricos: [código, regex, transformación opcional]
const NUMERICOS = [
  ["echocardiography_lvef", new RegExp(String.raw`\b(?:FEVI|FEVi|FE\s?VI|fracci[oó]n de eyecci[oó]n(?: del VI)?)(?:\s*\(?(?:biplano|Simpson|visual)\)?)?${SEP}${NUM}\s*%`, "i")],
  ["echocardiography_lvedd", new RegExp(String.raw`\b(?:DTDVI|DTD\s?VI|di[aá]metro telediast[oó]lico(?: del VI| VI)?)${SEP}${NUM}\s*mm`, "i")],
  ["echocardiography_septal_thickness_plax", new RegExp(String.raw`\b(?:SIV|septo(?: interventricular)?|TIV)(?:\s*\(?PLAX\)?)?${SEP}${NUM}\s*mm`, "i")],
  ["echocardiography_posterior_wall_thickness_plax", new RegExp(String.raw`\b(?:PP|pared posterior)(?:\s*\(?PLAX\)?)?${SEP}${NUM}\s*mm`, "i")],
  ["echocardiography_max_lv_wall_thickness", new RegExp(String.raw`\b(?:grosor|espesor) (?:parietal )?m[aá]ximo${SEP}${NUM}\s*mm`, "i")],
  ["echocardiography_lv_global_longitudinal_strain", new RegExp(String.raw`\b(?:strain(?: longitudinal)?(?: global)?|SLG|GLS)[^\d\n-]{0,28}?${NUM}\s*%`, "i"), (x) => -Math.abs(x)],
  ["echocardiography_aortic_valve_area", new RegExp(String.raw`\b(?:AVA|[aá]rea valvular(?: a[oó]rtica)?|[aá]rea (?:a[oó]rtica|efectiva))${SEP}${NUM}\s*cm`, "i")],
  ["echocardiography_aortic_vmax", new RegExp(String.raw`\b(?:V\.?\s?m[aá]x(?:ima)?|velocidad (?:pico|m[aá]xima)(?: a[oó]rtica)?)${SEP}${NUM}\s*m\/s`, "i")],
  ["echocardiography_aortic_mean_gradient", new RegExp(String.raw`\b(?:gradiente medio|G\.?\s?med(?:io)?|GM)(?: a[oó]rtico)?${SEP}${NUM}\s*mm\s?Hg`, "i")],
  ["natriuretic_peptide_nt_probnp", new RegExp(String.raw`\bNT[\s-]?pro[\s-]?BNP${SEP}${NUM}`, "i")],
  ["natriuretic_peptide_bnp", new RegExp(String.raw`(?<!pro[\s-]?)\bBNP\b${SEP}${NUM}`, "i")],
  ["troponin_t_hs", new RegExp(String.raw`\b(?:troponina T|TnT|hs-?TnT|TnT-?us)${SEP}${NUM}`, "i")],
  ["troponin_i_hs", new RegExp(String.raw`\b(?:troponina I|TnI|hs-?TnI|TnI-?us)${SEP}${NUM}`, "i")],
  ["creatinine", new RegExp(String.raw`\b(?:creatinina|Cr)\b${SEP}${NUM}`, "i")],
  ["glomerular_filtration_rate_mdrd", new RegExp(String.raw`\b(?:FG(?:e)?|filtrado glomerular(?: estimado)?|MDRD|CKD-?EPI)${SEP}${NUM}`, "i")],
  ["resting_heart_rate", new RegExp(String.raw`\b(?:FC|frecuencia card[ií]aca)${SEP}${NUM}\s*(?:lpm|l\.p\.m|x'|bpm|latidos)?`, "i")],
  ["weight", new RegExp(String.raw`\bpeso${SEP}${NUM}\s*kg`, "i")],
  ["height", new RegExp(String.raw`\b(?:talla|altura)${SEP}${NUM}\s*(cm|m)\b`, "i"), (x) => (x < 3 ? Math.round(x * 100) : x)],
  ["mi_number_of_stents", /\b(\d)\s*stents?\b/i],
];

// Diagnósticos / antecedentes Sí-No con detección de negación
const BOOLEANOS = [
  ["hypertension", /\b(HTA|hipertensi[oó]n arterial|hipertenso)\b/i],
  ["diabetes_mellitus_type_2", /\b(DM\s?(?:tipo\s?)?2|DM2|diabetes(?: mellitus)? tipo 2|diab[eé]tico tipo 2)\b/i],
  ["diabetes_mellitus_type_1", /\b(DM\s?(?:tipo\s?)?1|DM1|diabetes(?: mellitus)? tipo 1)\b/i],
  ["dyslipidaemia", /\b(dislipemia|DLP|dislipidemia|hipercolesterolemia)\b/i],
  ["clinically_diagnosed_obesity", /\b(obesidad|obeso)\b/i],
  ["prior_atrial_fibrillation", /\b(fibrilaci[oó]n auricular|FA (?:parox[ií]stica|persistente|permanente)|FA\b(?! de))/i],
  ["prior_atrial_flutter", /\bflutter auricular\b/i],
  ["prior_sustained_ventricular_tachycardia", /\b(TV sostenida|taquicardia ventricular sostenida)\b/i],
  ["prior_stroke_tia", /\b(ictus|AIT|accidente cerebrovascular|ACV)\b/i],
  ["chronic_kidney_disease", /\b(ERC|enfermedad renal cr[oó]nica|insuficiencia renal cr[oó]nica|IRC)\b/i],
  ["chronic_pulmonary_disease", /\b(EPOC|enfermedad pulmonar obstructiva|asma)\b/i],
  ["obstructive_sleep_apnoea", /\b(SAHS|SAOS|apnea(?:s)? (?:obstructiva )?del sue[ñn]o)\b/i],
  ["peripheral_arterial_disease", /\b(enfermedad arterial perif[eé]rica|arteriopat[ií]a perif[eé]rica|EAP)\b/i],
  ["chronic_liver_disease", /\b(cirrosis|hepatopat[ií]a cr[oó]nica)\b/i],
  ["pacemaker_implanted", /\b(marcapasos|MCP)\b/i],
  ["icd_implanted", /\b(DAI|desfibrilador autom[aá]tico)\b/i],
  ["carpal_tunnel_syndrome", /\bt[uú]nel (?:del )?carpiano\b/i],
  ["lumbar_canal_stenosis", /\bestenosis (?:de(?:l)? )?canal lumbar\b/i],
  ["polyneuropathy", /\bpolineuropat[ií]a\b/i],
  ["dysautonomia", /\bdisautonom[ií]a\b/i],
  ["amyloidosis_attr_mgus", /\b(GMSI|gammapat[ií]a monoclonal)\b/i],
  ["ecg_low_voltage", /\bbajo voltaje\b/i],
  ["bicuspid_aortic_valve", /\b(v[aá]lvula a[oó]rtica bic[uú]spide|bicuspide|bic[uú]spide)\b/i],
  ["history_syncope", /\bs[ií]ncope\b/i],
  ["family_history_hcm", /\bantecedentes? familiar(?:es)? de (?:MCH|miocardiopat[ií]a hipertr[oó]fica)\b/i],
  ["myocardial_infarction", /\b(IAM|infarto (?:agudo )?(?:de )?miocardio|IAMCEST|IAMSEST|SCACEST|SCASEST)\b/i],
  ["coronary_revascularization_pci", /\b(ICP|ACTP|angioplastia|stent)\b/i],
  ["coronary_revascularization_cabg", /\b(bypass|cirug[ií]a de revascularizaci[oó]n|CABG|injerto aortocoronario)\b/i],
  ["history_major_bleeding", /\b(sangrado mayor|hemorragia digestiva)\b/i],
];

// Selección única: [código opción, regex]
const SELECCIONES = [
  ["myocardial_infarction_stemi", /\b(IAMCEST|SCACEST|STEMI|IAM con elevaci[oó]n del ST)\b/i],
  ["myocardial_infarction_nstemi", /\b(IAMSEST|SCASEST|NSTEMI|IAM sin elevaci[oó]n del ST)\b/i],
  ["aortic_stenosis_severe", /\b(estenosis a[oó]rtica (?:severa|grave)|EAo (?:severa|grave))\b/i],
  ["aortic_stenosis_moderate", /\b(estenosis a[oó]rtica moderada|EAo moderada)\b/i],
  ["aortic_stenosis_mild", /\b(estenosis a[oó]rtica (?:leve|ligera)|EAo (?:leve|ligera))\b/i],
  ["hypertrophic_cardiomyopathy_obstructive", /\b(MCH obstructiva|miocardiopat[ií]a hipertr[oó]fica obstructiva|MCHO)\b/i],
  ["hypertrophic_cardiomyopathy_non_obstructive", /\b(MCH no obstructiva|miocardiopat[ií]a hipertr[oó]fica no obstructiva)\b/i],
  ["amyloidosis_attr_wild", /\b(ATTR\s?wt|ATTR-?wt|wild[\s-]?type|tipo salvaje|ATTR nativa)\b/i],
  ["amyloidosis_attr_variant", /\b(ATTRv|ATTR-?m|hereditaria|variante (?:pat[oó]gena )?(?:en )?TTR|Val\d+\w+|V\d{2,3}[A-Z])\b/i],
  ["heart_failure_lvef_reduced", /\b(IC(?:FE)?r|ICFEr|FEVI reducida|HFrEF)\b/i],
  ["heart_failure_lvef_midrange", /\b(ICFElr|ICFEm|FEVI (?:levemente reducida|ligeramente reducida|intermedia)|HFmrEF)\b/i],
  ["heart_failure_lvef_preserved", /\b(ICFEp|FEVI preservada|HFpEF)\b/i],
  ["tobacco_habit_ex_smoker", /\b(ex-?fumador(?:a)?|exfumador(?:a)?|ex tabaquismo)\b/i],
  ["tobacco_habit_non_smoker", /\b(no fumador(?:a)?|nunca fumador(?:a)?|niega (?:h[aá]bito )?tab[aá]quico|sin h[aá]bitos? t[oó]xicos?)\b/i],
  ["tobacco_habit_smoker", /\b(fumador(?:a)? activ[oa]|fumador(?:a)? de \d+|tabaquismo activo|fuma \d+)\b/i],
];

const NEGACION = /\b(no|niega|sin|descarta(?:d[oa])?|negativ[oa] para|ausencia de|no presenta|no se objetiva|excluida?)\b[^.;\n]{0,35}$/i;

function fragmento(texto, ini, fin) {
  const a = Math.max(0, ini - 50), b = Math.min(texto.length, fin + 50);
  return { antes: (a > 0 ? "…" : "") + texto.slice(a, ini), match: texto.slice(ini, fin), despues: texto.slice(fin, b) + (b < texto.length ? "…" : "") };
}

/** Devuelve propuestas [{id, codigo, titulo, valorTexto, cambios, frag, aviso}] */
export function extraer(texto, modelo) {
  const props = [];
  const ya = new Set();
  const etq = (c) => modelo.porCodigo[c]?.etiqueta || c;
  const push = (p) => { if (!ya.has(p.id) && modelo.porCodigo[p.codigo]) { ya.add(p.id); props.push(p); } };

  // Sexo (p. ej. "Varón de 72 años")
  let m = texto.match(/\b(var[oó]n|hombre|mujer)\b(?:\s+de\s+\d{1,3}\s+a[ñn]os)?/i);
  if (m) {
    const varon = !/mujer/i.test(m[1]);
    push({ id: "sexo", codigo: "biological_sex_male", titulo: "Sexo biológico", valorTexto: varon ? "Varón" : "Mujer",
      cambios: { biological_sex_male: varon ? 1 : 0, biological_sex_female: varon ? 0 : 1 }, frag: fragmento(texto, m.index, m.index + m[0].length) });
  }

  // Tensión arterial  "TA 135/80"
  m = texto.match(/\b(?:TA|PA|T\.A\.|tensi[oó]n arterial|presi[oó]n arterial)[^\d\n]{0,15}(\d{2,3})\s*\/\s*(\d{2,3})/i);
  if (m) {
    push({ id: "ta", codigo: "systolic_blood_pressure_mean", titulo: "Presión arterial", valorTexto: `${m[1]}/${m[2]} mmHg`,
      cambios: { systolic_blood_pressure_mean: +m[1], diastolic_blood_pressure_mean: +m[2] }, frag: fragmento(texto, m.index, m.index + m[0].length) });
  }

  for (const [codigo, re, tf] of NUMERICOS) {
    const r = texto.match(re);
    if (!r) continue;
    let val = n(r[1]);
    if (tf) val = tf(val, r);
    if (!isFinite(val)) continue;
    const it = modelo.porCodigo[codigo];
    let aviso = "";
    if (it && it.min !== null && it.max !== null && (val < it.min || val > it.max)) aviso = `Fuera del rango esperado (${it.min}–${it.max})`;
    push({ id: codigo, codigo, titulo: etq(codigo), valorTexto: String(val).replace(".", ",") + (it?.unidad ? " " + it.unidad : ""),
      cambios: { [codigo]: val }, frag: fragmento(texto, r.index, r.index + r[0].length), aviso });
  }

  // NYHA
  m = texto.match(/\bNYHA\s*(?:clase\s*|grado\s*)?(IV|III|II|I|[1-4])\b/i) || texto.match(/\bclase funcional\s*(IV|III|II|I|[1-4])\b/i);
  if (m) {
    const romano = { 1: "I", 2: "II", 3: "III", 4: "IV" }[m[1]] || m[1].toUpperCase();
    const cods = ["nyha_class_i", "nyha_class_ii", "nyha_class_iii", "nyha_class_iv"];
    const elegido = "nyha_class_" + romano.toLowerCase();
    push({ id: "nyha", codigo: "nyha_class_i", titulo: "Clase funcional NYHA", valorTexto: "NYHA " + romano,
      cambios: Object.fromEntries(cods.map((c) => [c, c === elegido ? 1 : 0])), frag: fragmento(texto, m.index, m.index + m[0].length) });
  }

  // Perugini
  m = texto.match(/\bPerugini[^\d\n]{0,15}([0-3])\b/i) || texto.match(/\bgrado\s*([0-3])\s*(?:de|en la escala de)\s*Perugini\b/i);
  if (m) {
    const cods = [0, 1, 2, 3].map((g) => "scintigraphy_perugini_score_grade_" + g);
    push({ id: "perugini", codigo: cods[0], titulo: "Grado de Perugini", valorTexto: "Grado " + m[1],
      cambios: { scintigraphy_procedure_done: 1, ...Object.fromEntries(cods.map((c, i) => [c, i === +m[1] ? 1 : 0])) }, frag: fragmento(texto, m.index, m.index + m[0].length) });
  }

  // TIMI
  m = texto.match(/\bTIMI\s*(?:flujo\s*)?([0-3])\b/i);
  if (m) {
    const cods = [0, 1, 2, 3].map((g) => "timi_coronary_grade_flow_" + g);
    push({ id: "timi", codigo: cods[0], titulo: "Flujo TIMI", valorTexto: "TIMI " + m[1],
      cambios: { coronary_angiography_done: 1, ...Object.fromEntries(cods.map((c, i) => [c, i === +m[1] ? 1 : 0])) }, frag: fragmento(texto, m.index, m.index + m[0].length) });
  }

  // Selecciones únicas
  for (const [codigo, re] of SELECCIONES) {
    const r = texto.match(re);
    if (!r) continue;
    const op = modelo.porCodigo[codigo];
    if (!op?.padre) continue;
    const padre = op.padre;
    if (ya.has("grupo:" + padre.codigo)) continue;
    ya.add("grupo:" + padre.codigo);
    const cambios = {};
    if (padre.tipoCampo === "single") padre.opciones.forEach((o) => (cambios[o.codigo] = o.codigo === codigo ? 1 : 0));
    else cambios[codigo] = 1;
    if (padre.codigo === "heart_failure_type") cambios.heart_failure_lvef = 1; // pregunta llave del tipo según FEVI
    push({ id: codigo, codigo, titulo: padre.etiqueta, valorTexto: op.etiqueta, cambios, frag: fragmento(texto, r.index, r.index + r[0].length) });
  }

  // Sí / No con negación
  for (const [codigo, re] of BOOLEANOS) {
    const r = texto.match(re);
    if (!r) continue;
    const previo = texto.slice(Math.max(0, r.index - 60), r.index);
    const negado = NEGACION.test(previo);
    push({ id: codigo, codigo, titulo: etq(codigo), valorTexto: negado ? "No" : "Sí", negado,
      cambios: { [codigo]: negado ? 0 : 1 }, frag: fragmento(texto, r.index, r.index + r[0].length),
      aviso: negado ? "Detectado con negación: compruebe que es correcto" : "" });
  }

  // Fecha del informe -> fecha de eco / analítica si hay valores de esas pruebas
  m = texto.match(/\b(?:fecha(?: del? (?:estudio|informe|exploraci[oó]n))?|realizado(?: el)?)\s*[:\-]?\s*(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})/i);
  if (m) {
    const y = m[3].length === 2 ? "20" + m[3] : m[3];
    const f = `${y}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
    const hayEco = props.some((p) => p.codigo.startsWith("echocardiography"));
    const hayLab = props.some((p) => /natriuretic|troponin|creatinine|glomerular/.test(p.codigo));
    if (hayEco) push({ id: "fecha_eco", codigo: "echocardiography_procedure", titulo: etq("echocardiography_procedure"), valorTexto: f.split("-").reverse().join("/"),
      cambios: { echocardiography_procedure: f }, frag: fragmento(texto, m.index, m.index + m[0].length), aviso: "Fecha tomada del informe: compruébela" });
    if (hayLab) push({ id: "fecha_lab", codigo: "laboratory_biomarkers_test", titulo: etq("laboratory_biomarkers_test"), valorTexto: f.split("-").reverse().join("/"),
      cambios: { laboratory_biomarkers_test: f }, frag: fragmento(texto, m.index, m.index + m[0].length), aviso: "Fecha tomada del informe: compruébela" });
  }
  return props;
}

export const EJEMPLO = `HOSPITAL CLÍNICO UNIVERSITARIO VIRGEN DE LA ARRIXACA
Servicio de Cardiología - Laboratorio de Ecocardiografía
Paciente: GARCÍA PÉREZ, Antonio
NHC: 1234567      CIP: MURC0123456789
Fecha de nacimiento: 03/05/1948
Domicilio: C/ Mayor 12, 30120 El Palmar (Murcia)   Teléfono: 968 123 456
Médico solicitante: Dr. Fernández Ruiz

INFORME DE ECOCARDIOGRAMA TRANSTORÁCICO
Fecha del estudio: 14/10/2026

Varón de 78 años. HTA y dislipemia en tratamiento. DM tipo 2. Exfumador. No FA conocida.
Síndrome del túnel carpiano bilateral intervenido. Disnea NYHA II.
Peso 74 kg, talla 1,70 m. TA 128/76 mmHg, FC 72 lpm.

Ventrículo izquierdo no dilatado (DTDVI 46 mm) con hipertrofia concéntrica severa:
SIV 18 mm, PP 16 mm, grosor máximo 19 mm. FEVI (biplano) 52 %.
Strain longitudinal global -11,5 % con patrón de respeto apical.
Válvula aórtica trivalva, esclerosada, sin estenosis significativa: Vmax 1,9 m/s.

Analítica: NT-proBNP 3.450 pg/mL, troponina T 48 ng/L, creatinina 1,21 mg/dL, FG 58 mL/min.
Gammagrafía con DPD: captación cardiaca grado 3 de Perugini.
Conclusión: hallazgos sugestivos de amiloidosis cardiaca por transtiretina (ATTRwt).

Fdo.: Dra. López Martínez`;
