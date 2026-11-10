// Lectura y escritura de archivos .xlsx en el navegador, sin librerías externas.

// ---------------------------------------------------------------------------
// ZIP
// ---------------------------------------------------------------------------
const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** Crea un zip sin compresión (método "store"). archivos: [{nombre, datos: string|Uint8Array}] */
function crearZip(archivos) {
  const enc = new TextEncoder();
  const partes = [], central = [];
  let offset = 0;
  for (const a of archivos) {
    const nombre = enc.encode(a.nombre);
    const datos = typeof a.datos === "string" ? enc.encode(a.datos) : a.datos;
    const crc = crc32(datos);
    const lh = new DataView(new ArrayBuffer(30));
    lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true); lh.setUint16(8, 0, true);
    lh.setUint16(10, 0, true); lh.setUint16(12, 0x21, true); lh.setUint32(14, crc, true);
    lh.setUint32(18, datos.length, true); lh.setUint32(22, datos.length, true); lh.setUint16(26, nombre.length, true); lh.setUint16(28, 0, true);
    partes.push(new Uint8Array(lh.buffer), nombre, datos);
    const ch = new DataView(new ArrayBuffer(46));
    ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true); ch.setUint16(8, 0x0800, true);
    ch.setUint16(10, 0, true); ch.setUint16(12, 0, true); ch.setUint16(14, 0x21, true); ch.setUint32(16, crc, true);
    ch.setUint32(20, datos.length, true); ch.setUint32(24, datos.length, true); ch.setUint16(28, nombre.length, true);
    ch.setUint32(42, offset, true);
    central.push(new Uint8Array(ch.buffer), nombre);
    offset += 30 + nombre.length + datos.length;
  }
  const tamCentral = central.reduce((s, p) => s + p.length, 0);
  const fin = new DataView(new ArrayBuffer(22));
  fin.setUint32(0, 0x06054b50, true); fin.setUint16(8, archivos.length, true); fin.setUint16(10, archivos.length, true);
  fin.setUint32(12, tamCentral, true); fin.setUint32(16, offset, true);
  return new Blob([...partes, ...central, new Uint8Array(fin.buffer)], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

async function leerZip(buffer) {
  const u8 = new Uint8Array(buffer), dv = new DataView(buffer);
  let eocd = -1;
  for (let i = u8.length - 22; i >= Math.max(0, u8.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw new Error("El archivo no es un Excel (.xlsx) válido");
  const n = dv.getUint16(eocd + 10, true);
  let p = dv.getUint32(eocd + 16, true);
  const dec = new TextDecoder();
  const out = {};
  for (let i = 0; i < n; i++) {
    const metodo = dv.getUint16(p + 10, true), tam = dv.getUint32(p + 20, true);
    const ln = dv.getUint16(p + 28, true), le = dv.getUint16(p + 30, true), lc = dv.getUint16(p + 32, true);
    const off = dv.getUint32(p + 42, true);
    const nombre = dec.decode(u8.subarray(p + 46, p + 46 + ln));
    p += 46 + ln + le + lc;
    const ini = off + 30 + dv.getUint16(off + 26, true) + dv.getUint16(off + 28, true);
    const crudo = u8.subarray(ini, ini + tam);
    out[nombre] = async () => {
      if (metodo === 0) return dec.decode(crudo);
      if (metodo !== 8) throw new Error("Compresión no soportada");
      const ds = new Blob([crudo]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      return await new Response(ds).text();
    };
  }
  return out;
}

// ---------------------------------------------------------------------------
// XLSX
// ---------------------------------------------------------------------------
const xesc = (s) => String(s).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const letra = (i) => { let s = ""; i++; while (i) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); } return s; };

function hojaXml(filas) {
  const o = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>'];
  filas.forEach((fila, ri) => {
    o.push(`<row r="${ri + 1}">`);
    fila.forEach((v, ci) => {
      if (v === null || v === undefined || v === "") return;
      const ref = letra(ci) + (ri + 1), st = ri === 0 ? ' s="1"' : "";
      if (typeof v === "number" && isFinite(v)) o.push(`<c r="${ref}"${st}><v>${v}</v></c>`);
      else o.push(`<c r="${ref}" t="inlineStr"${st}><is><t xml:space="preserve">${xesc(v)}</t></is></c>`);
    });
    o.push("</row>");
  });
  o.push("</sheetData></worksheet>");
  return o.join("");
}

/** hojas: [[nombre, filas]] -> Blob .xlsx */
export function crearXlsx(hojas) {
  const ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
  const archivos = [
    { nombre: "[Content_Types].xml", datos: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + hojas.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("") + "</Types>" },
    { nombre: "_rels/.rels", datos: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>' },
    { nombre: "xl/workbook.xml", datos: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook ${ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>` + hojas.map(([n], i) => `<sheet name="${xesc(n)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("") + "</sheets></workbook>" },
    { nombre: "xl/_rels/workbook.xml.rels", datos: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + hojas.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("") + `<Relationship Id="rId${hojas.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>` },
    { nombre: "xl/styles.xml", datos: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet ${ns}><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>` },
    ...hojas.map(([, filas], i) => ({ nombre: `xl/worksheets/sheet${i + 1}.xml`, datos: hojaXml(filas) })),
  ];
  return crearZip(archivos);
}

/** Lee un .xlsx -> { nombreHoja: [[celdas]] } */
export async function leerXlsx(buffer) {
  const z = await leerZip(buffer);
  const P = new DOMParser();
  const xml = async (n) => (z[n] ? P.parseFromString(await z[n](), "application/xml") : null);
  const porTag = (doc, t) => [...doc.getElementsByTagNameNS("*", t)];
  const compartidas = [];
  const ss = await xml("xl/sharedStrings.xml");
  if (ss) for (const si of porTag(ss, "si")) compartidas.push(porTag(si, "t").map((t) => t.textContent).join(""));
  const wb = await xml("xl/workbook.xml");
  const rels = await xml("xl/_rels/workbook.xml.rels");
  const destino = {};
  for (const r of porTag(rels, "Relationship")) destino[r.getAttribute("Id")] = r.getAttribute("Target");
  const hojas = {};
  for (const h of porTag(wb, "sheet")) {
    const rid = h.getAttribute("r:id") || h.getAttributeNS("http://schemas.openxmlformats.org/officeDocument/2006/relationships", "id");
    let t = (destino[rid] || "").replace(/^\//, "");
    if (!t.startsWith("xl/")) t = "xl/" + t;
    const doc = await xml(t);
    if (!doc) continue;
    const filas = [];
    for (const row of porTag(doc, "row")) {
      const fila = [];
      for (const c of porTag(row, "c")) {
        const ref = c.getAttribute("r") || "";
        let i = 0;
        for (const ch of ref.match(/[A-Z]+/)?.[0] || "A") i = i * 26 + (ch.charCodeAt(0) - 64);
        i--;
        const tipo = c.getAttribute("t");
        const v = porTag(c, "v")[0]?.textContent;
        let val = null;
        if (tipo === "s" && v != null) val = compartidas[+v];
        else if (tipo === "inlineStr") val = porTag(c, "t").map((x) => x.textContent).join("");
        else if (tipo === "str") val = v ?? null;
        else if (tipo === "b") val = v === "1" ? 1 : 0;
        else if (v != null) val = isFinite(+v) ? +v : v;
        while (fila.length < i) fila.push(null);
        fila[i] = val;
      }
      filas.push(fila);
    }
    hojas[h.getAttribute("name")] = filas;
  }
  return hojas;
}

export function descargar(blob, nombre) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
