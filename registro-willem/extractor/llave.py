"""
Libro llave del Mac: número de caso <-> CIP autonómico (CARM), CIP SNS y NHC.

Es un archivo SQLite con la MISMA tabla "llave" que usa servidor.py (--llave), y además:
  - informes:      qué PDF se ha procesado (huella del archivo), de qué caso y con qué resultado
  - profesionales: directorio de nombres de profesionales que van apareciendo en los informes
                   (firmantes y primaria); se ocultan en los informes siguientes
NUNCA se copia al NAS ni a la carpeta compartida.
"""
import datetime as dt
import os
import sqlite3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS llave(
    numero INTEGER PRIMARY KEY, cip TEXT, carm TEXT, nhc TEXT, notas TEXT,
    creado TEXT, creado_por TEXT);
CREATE TABLE IF NOT EXISTS informes(
    huella TEXT PRIMARY KEY, numero INTEGER, fecha_ingreso TEXT, acto TEXT,
    estado TEXT, salida TEXT, procesado TEXT);
CREATE TABLE IF NOT EXISTS profesionales(
    nombre TEXT PRIMARY KEY, veces INTEGER, primera_vez TEXT);
CREATE TABLE IF NOT EXISTS ajustes(clave TEXT PRIMARY KEY, valor TEXT);
-- DNI aparte, para no alterar la tabla "llave" que comparte formato con servidor.py
CREATE TABLE IF NOT EXISTS llave_dni(numero INTEGER PRIMARY KEY, dni TEXT UNIQUE);
"""


def ahora():
    return dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


class ConflictoLlave(Exception):
    pass


class Llave:
    def __init__(self, ruta):
        os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.con.commit()

    # ---------------- ajustes ----------------
    def ajuste(self, clave, defecto=None):
        r = self.con.execute("SELECT valor FROM ajustes WHERE clave=?", (clave,)).fetchone()
        return r["valor"] if r else defecto

    def poner_ajuste(self, clave, valor):
        self.con.execute("INSERT OR REPLACE INTO ajustes VALUES(?,?)", (clave, str(valor)))
        self.con.commit()

    # ---------------- pacientes ----------------
    def buscar(self, carm=None, cip=None, nhc=None, dni=None):
        """Devuelve (fila, por_que_clave) o (None, None). Orden: CARM, CIP SNS, NHC, DNI."""
        for col, v in (("carm", carm), ("cip", cip), ("nhc", nhc)):
            if v:
                r = self.con.execute(f"SELECT * FROM llave WHERE {col}=?", (v,)).fetchone()
                if r:
                    return r, col
        if dni:
            r = self.con.execute("SELECT l.* FROM llave l JOIN llave_dni d ON d.numero=l.numero WHERE d.dni=?", (dni,)).fetchone()
            if r:
                return r, "dni"
        return None, None

    def dni_de(self, numero):
        r = self.con.execute("SELECT dni FROM llave_dni WHERE numero=?", (numero,)).fetchone()
        return r["dni"] if r else None

    def siguiente_numero(self):
        m = self.con.execute("SELECT COALESCE(MAX(numero),0) FROM llave").fetchone()[0]
        primero = int(self.ajuste("primer_numero", 1))
        return max(m + 1, primero)

    def caso_para(self, carm, cip, nhc, dni=None, usuario="extractor"):
        """Número de caso del paciente: el que ya tenía o uno nuevo. Devuelve (numero, es_nuevo, clave).

        Se enlaza por CIP autonómico (CARM); si el informe no lo trae, por CIP SNS, NHC o DNI.
        Si alguna clave del informe contradice a la guardada para ese caso, se bloquea."""
        dni = (dni or "").strip(" /").upper() or None
        if not (carm or nhc or dni or cip):
            raise ConflictoLlave("El informe no trae CIP autonómico, CIP SNS, NHC ni DNI: no se puede asignar caso.")
        fila, clave = self.buscar(carm, cip, nhc, dni)
        if fila:
            guardado = {"carm": fila["carm"], "cip": fila["cip"], "nhc": fila["nhc"], "dni": self.dni_de(fila["numero"])}
            nuevo = {"carm": carm, "cip": cip, "nhc": nhc, "dni": dni}
            choques = [k.upper() for k in nuevo if nuevo[k] and guardado[k] and str(nuevo[k]) != str(guardado[k])]
            if choques:
                raise ConflictoLlave(f"El paciente coincide con el caso {fila['numero']} por {clave.upper()}, pero no cuadra "
                                     f"el {', '.join(choques)}. Revise el libro llave antes de continuar.")
            for k in ("carm", "cip", "nhc"):
                if nuevo[k] and not guardado[k]:
                    self.con.execute(f"UPDATE llave SET {k}=? WHERE numero=?", (nuevo[k], fila["numero"]))
            if dni and not guardado["dni"]:
                self.con.execute("INSERT OR IGNORE INTO llave_dni VALUES(?,?)", (fila["numero"], dni))
            self.con.commit()
            return fila["numero"], False, clave
        n = self.siguiente_numero()
        nota = "Asignado automáticamente al leer el informe de alta" + ("" if carm else " (sin CIP autonómico: enlazado por NHC/DNI)")
        self.con.execute("INSERT INTO llave(numero,cip,carm,nhc,notas,creado,creado_por) VALUES(?,?,?,?,?,?,?)",
                         (n, cip or None, carm or None, nhc or None, nota, ahora(), usuario))
        if dni:
            self.con.execute("INSERT OR IGNORE INTO llave_dni VALUES(?,?)", (n, dni))
        self.con.commit()
        return n, True, None

    # ---------------- informes ----------------
    def informe(self, huella):
        return self.con.execute("SELECT * FROM informes WHERE huella=?", (huella,)).fetchone()

    def guardar_informe(self, huella, numero, fecha_ingreso, acto, estado, salida):
        self.con.execute("INSERT OR REPLACE INTO informes VALUES(?,?,?,?,?,?,?)",
                         (huella, numero, fecha_ingreso, acto, estado, salida, ahora()))
        self.con.commit()

    def informes_del_caso(self, numero):
        return self.con.execute("SELECT * FROM informes WHERE numero=? ORDER BY fecha_ingreso", (numero,)).fetchall()

    # ---------------- profesionales ----------------
    def profesionales(self):
        return [r["nombre"] for r in self.con.execute("SELECT nombre FROM profesionales ORDER BY nombre")]

    def anotar_profesionales(self, nombres):
        for n in nombres:
            n = " ".join((n or "").split()).strip(" ,/")
            if len(n) < 5:
                continue
            if self.con.execute("SELECT 1 FROM profesionales WHERE nombre=?", (n,)).fetchone():
                self.con.execute("UPDATE profesionales SET veces=veces+1 WHERE nombre=?", (n,))
            else:
                self.con.execute("INSERT INTO profesionales VALUES(?,?,?)", (n, 1, ahora()))
        self.con.commit()

    # ---------------- exportar / importar (mismo formato que la web) ----------------
    def filas_llave(self):
        return [[r["numero"], r["cip"], r["carm"], r["nhc"], r["notas"], r["creado"], r["creado_por"], r["dni"]]
                for r in self.con.execute("SELECT l.*, d.dni FROM llave l LEFT JOIN llave_dni d ON d.numero=l.numero ORDER BY l.numero")]

    def importar(self, filas):
        """filas: dicts con numero, cip, carm, nhc (p. ej. la llave exportada desde la web)."""
        n = 0
        for f in filas:
            try:
                num = int(f.get("numero"))
            except (TypeError, ValueError):
                continue
            if self.con.execute("SELECT 1 FROM llave WHERE numero=?", (num,)).fetchone():
                continue
            self.con.execute("INSERT INTO llave VALUES(?,?,?,?,?,?,?)",
                             (num, f.get("cip"), f.get("carm"), str(f.get("nhc")) if f.get("nhc") is not None else None,
                              f.get("notas"), f.get("creado") or ahora(), f.get("creado_por") or "importado"))
            if f.get("dni"):
                self.con.execute("INSERT OR IGNORE INTO llave_dni VALUES(?,?)", (num, str(f["dni"]).strip().upper()))
            n += 1
        self.con.commit()
        return n
