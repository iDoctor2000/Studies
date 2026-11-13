// Contraseña de acceso a la versión web. Generado por herramientas/cambiar_clave.py: NO editar a mano.
// Solo se guarda una huella cifrada (PBKDF2-SHA256), nunca la contraseña.
// Es una barrera ligera: los datos de pacientes nunca están en esta página.
export const ACCESO = { sal: "81f889124d8aa5f4e29b0144463ebf92", iteraciones: 310000, huella: "dab8715ccc688f48eb6dc1193e26e9ce1af9b4f97b74c523f2e24b18c9580574" };

const CLAVE_LOCAL = "willem_acceso";
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

async function derivar(clave) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(clave), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: enc.encode(ACCESO.sal), iterations: ACCESO.iteraciones }, k, 256);
  return hex(bits);
}

export async function comprobarClave(clave) {
  return (await derivar(clave)) === ACCESO.huella;
}

export function accesoConcedido() {
  try { return localStorage.getItem(CLAVE_LOCAL) === ACCESO.huella || sessionStorage.getItem(CLAVE_LOCAL) === ACCESO.huella; } catch { return false; }
}

export function recordarAcceso(enEsteDispositivo) {
  try { (enEsteDispositivo ? localStorage : sessionStorage).setItem(CLAVE_LOCAL, ACCESO.huella); } catch { /* sin almacenamiento */ }
}

export function olvidarAcceso() {
  try { localStorage.removeItem(CLAVE_LOCAL); sessionStorage.removeItem(CLAVE_LOCAL); } catch { /* nada */ }
}
