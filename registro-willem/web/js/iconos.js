// Iconos propios (SVG, trazo 24x24) y metadatos de cada enfermedad.
const P = {
  panel: '<rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/>',
  casos: '<path d="M4 6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M8 13h8M8 16h5"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  llave: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M15 8l2 2"/>',
  exportar: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/>',
  usuarios: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.5a5 5 0 0 1 5.5 5"/>',
  libro: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7M8 11h7"/>',
  salir: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 16l-4-4 4-4M6 12h10"/>',
  buscar: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  flechaD: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  flechaI: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  importar: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
  historial: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  escudo: '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="m9 12 2 2 4-4"/>',
  candado: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  varita: '<path d="m4 20 11-11M14 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM19 11l.7 1.3L21 13l-1.3.7L19 15l-.7-1.3L17 13l1.3-.7z"/>',
  editar: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  aviso: '<path d="M12 3 2 20h20z"/><path d="M12 10v5M12 17.5v.5"/>',
  luna: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
  codigo: '<path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>',
  papelera: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  ojo: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  nube: '<path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18 9.5a4 4 0 0 1-.5 8.5z"/><path d="m9.5 13.5 2 2 3.5-3.5"/>',
  unir: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="12" r="2.5"/><path d="M8.5 6c4 0 5 6 7 6M8.5 18c4 0 5-6 7-6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  enviar: '<path d="M4 12 20 4l-6 16-3-7z"/><path d="m11 13 9-9"/>',
  bandera: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  interrogacion: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.2v.3"/>',
  rayo: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  // ---- enfermedades ----
  IC: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/><path d="M3 12.5h4l1.5-2.5 2 5 1.5-2.5h3"/>',
  ISQ: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/><path d="M12 7c-1 2.5 1.5 4 0 6.5s1 3.5 0 6.5" stroke-dasharray="2 2"/>',
  EAO: '<circle cx="12" cy="12" r="8"/><path d="M12 12 12 4M12 12l6.9 4M12 12l-6.9 4"/>',
  MCH: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 7.5 2.8C19.5 15.4 12 20 12 20z"/><path d="M12 9.5v8.5" stroke-width="3.2"/>',
  ATTR: '<path d="m12 3 7.8 4.5v9L12 21l-7.8-4.5v-9z"/><path d="m12 8 3.5 2v4L12 16l-3.5-2v-4z"/>',
  QTL: '<path d="M2 13h3l1.5-3 2 7 2-11 2 7h3.5c1 0 1.5-2 3-2s2 2 3 2"/>',
  logo: '<path d="M12 20.5s-8-4.9-8-10.9A4.6 4.6 0 0 1 12 6.6a4.6 4.6 0 0 1 8 3c0 6-8 10.9-8 10.9z"/><path d="M2.5 12.5h5l1.6-3 2.2 6 1.8-4.5 1.2 1.5h7"/>',
};

export function icono(nombre, clase = "") {
  return `<svg class="ico ${clase}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[nombre] || ""}</svg>`;
}

export const ENFERMEDADES = {
  IC: {
    nombre: "Insuficiencia cardiaca", corto: "IC", color: "#e11d48",
    desc: "FEVI, tipo de IC (reducida / levemente reducida / preservada), NYHA, strain y péptidos natriuréticos.",
  },
  ISQ: {
    nombre: "Cardiopatía isquémica / IAM", corto: "Isquémica", color: "#ea7a0b",
    desc: "Infarto (IAMCEST / IAMSEST, OMI / NOMI), coronariografía, TIMI, stents y revascularización.",
  },
  EAO: {
    nombre: "Estenosis aórtica", corto: "EAo", color: "#2563eb",
    desc: "Gravedad (leve / moderada / grave), Vmax, gradiente medio y área valvular.",
  },
  MCH: {
    nombre: "Miocardiopatía hipertrófica", corto: "MCH", color: "#7c3aed",
    desc: "Obstructiva o no, grosor máximo, estudio genético y antecedentes familiares.",
  },
  ATTR: {
    nombre: "Amiloidosis cardiaca ATTR", corto: "ATTR", color: "#059669",
    desc: "Subtipo (ATTRwt / ATTRv), Perugini, biopsia, genética, túnel carpiano, polineuropatía, disautonomía.",
  },
  QTL: {
    nombre: "Síndrome de QT largo", corto: "QT largo", color: "#0891b2",
    desc: "Diagnóstico, estudio genético, síncope y antecedentes arrítmicos.",
  },
};

export const PRINCIPALES = ["IC", "ISQ", "EAO", "MCH", "ATTR", "QTL"];
