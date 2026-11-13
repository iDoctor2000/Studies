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
    def buscar(self, carm=None, cip=None, nhc=None):
        """Devuelve (fila, por_que_clave) o (None, None)."""
        for col, v in (("carm", carm), ("cip", cip), ("nhc", nhc)):
            if v:
                r = self.con.execute(f"SELECT * FROM llave WHERE {col}=?", (v,)).fetchone()
                if r:
                    return r, col
        return None, None

    def siguiente_numero(self):
        m = self.con.execute("SELECT COALESCE(MAX(numero),0) FROM llave").fetchone()[0]
        primero = int(self.ajuste("primer_numero", 1))
        return max(m + 1, primero)

    def caso_para(self, carm, cip, nhc, usuario="extractor"):
        """Número de caso del paciente: el que ya tenía o uno nuevo. Devuelve (numero, es_nuevo)."""
        if not carm:
            raise ConflictoLlave("El informe no trae CIP autonómico (CARM): no se puede asignar caso con seguridad.")
        fila, clave = self.buscar(carm, cip, nhc)
        if fila:
            # Si se encontró por otra clave, el CARM tiene que coincidir (o estar vacío)
            if fila["carm"] and fila["carm"] != carm:
                raise ConflictoLlave(f"El {clave.upper()} ya pertenece al caso {fila['numero']}, pero con otro CIP autonómico. "
                                     "Revise el libro llave antes de continuar.")
            cambios = {k: v for k, v in (("carm", carm), ("cip", cip), ("nhc", nhc)) if v and not fila[k]}
            for k, v in cambios.items():
                self.con.execute(f"UPDATE llave SET {k}=? WHERE numero=?", (v, fila["numero"]))
            self.con.commit()
            return fila["numero"], False
        n = self.siguiente_numero()
        self.con.execute("INSERT INTO llave(numero,cip,carm,nhc,notas,creado,creado_por) VALUES(?,?,?,?,?,?,?)",
                         (n, cip or None, carm, nhc or None, "Asignado automáticamente al leer el informe de alta",
                          ahora(), usuario))
        self.con.commit()
        return n, True

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
        return [[r["numero"], r["cip"], r["carm"], r["nhc"], r["notas"], r["creado"], r["creado_por"]]
                for r in self.con.execute("SELECT * FROM llave ORDER BY numero")]

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
            n += 1
        self.con.commit()
        return n
