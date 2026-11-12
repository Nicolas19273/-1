"""
datos.py — Reglas y almacenamiento de los avisos de "Falta Uno".

Dónde se guardan los datos:
  * En tu computador (sin configurar nada): un archivo SQLite, avisos.db.
  * En internet: si existe la variable de entorno DATABASE_URL, se usa esa
    base de datos PostgreSQL (por ejemplo, una gratuita de Neon).

La interfaz (app.py) solo llama a las funciones de este archivo: si más
adelante rehacemos el diseño, esta parte no se toca.

Reglas:
  * Quien publica indica cuántos son ahora y cuántos necesitan en total.
  * El aviso dura 24 o 48 horas (lo elige quien publica).
  * El aviso se cierra cuando:
      - se completan los cupos, o
      - se cumple el plazo de 24/48 h, o
      - llega la hora del evento (no tiene sentido unirse a algo que ya empezó).
  * Un aviso cerrado deja de aparecer en la lista, pero su página de detalle
    (/aviso/<id>) sigue mostrando quiénes se unieron.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

ZONA_HORARIA = ZoneInfo("America/Santiago")

URL_BD = os.environ.get("DATABASE_URL", "").strip()  # PostgreSQL en internet
RUTA_BD = Path(__file__).with_name("avisos.db")  # SQLite en tu computador

DURACIONES_PERMITIDAS = (24, 48)
MAX_PERSONAS = 100

LARGO_NOMBRE = (2, 40)
LARGO_TITULO = (3, 80)
LARGO_LUGAR = (3, 120)
LARGO_MAX_DESCRIPCION = 500

# clave interna -> nombre visible
CATEGORIAS: dict[str, str] = {
    "futbol": "Fútbol",
    "basquetbol": "Básquetbol",
    "tenis_padel": "Tenis / Pádel",
    "voleibol": "Vóleibol",
    "juegos_mesa": "Juegos de mesa",
    "videojuegos": "Videojuegos",
    "estudio": "Estudio",
    "salida": "Salida / Panorama",
    "otro": "Otro",
}

# Motivos por los que un aviso puede estar cerrado
COMPLETO = "completo"
VENCIDO = "vencido"
INICIADO = "iniciado"


class ErrorValidacion(Exception):
    """Error con un mensaje listo para mostrarle a la persona."""


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Aviso:
    id: int
    titulo: str
    categoria: str
    descripcion: str
    lugar: str
    inicio_evento: datetime
    personas_actuales: int  # cuántos eran al publicar (incluye a quien publica)
    personas_necesarias: int  # total que necesitan para el evento
    creador: str
    duracion_horas: int
    creado_en: datetime
    expira_en: datetime
    participantes: tuple[str, ...]  # quienes se unieron desde la página

    @property
    def ocupados(self) -> int:
        return self.personas_actuales + len(self.participantes)

    @property
    def cupos_libres(self) -> int:
        return max(self.personas_necesarias - self.ocupados, 0)

    @property
    def esta_lleno(self) -> bool:
        return self.cupos_libres == 0

    @property
    def cierra_en(self) -> datetime:
        """Momento en que el aviso deja de aceptar gente por tiempo."""
        return min(self.expira_en, self.inicio_evento)

    @property
    def nombre_categoria(self) -> str:
        return CATEGORIAS.get(self.categoria, "Otro")

    def motivo_cierre(self, ahora: datetime | None = None) -> str | None:
        """None si está abierto; si no, COMPLETO, INICIADO o VENCIDO."""
        ahora = _ahora(ahora)
        if self.esta_lleno:
            return COMPLETO
        if ahora >= self.inicio_evento:
            return INICIADO
        if ahora >= self.expira_en:
            return VENCIDO
        return None

    def esta_abierto(self, ahora: datetime | None = None) -> bool:
        return self.motivo_cierre(ahora) is None


# --------------------------------------------------------------------------- #
# Conexión: SQLite (local) o PostgreSQL (internet)
# --------------------------------------------------------------------------- #

_ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS avisos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo              TEXT    NOT NULL,
    categoria           TEXT    NOT NULL,
    descripcion         TEXT    NOT NULL DEFAULT '',
    lugar               TEXT    NOT NULL,
    inicio_evento       INTEGER NOT NULL,
    personas_actuales   INTEGER NOT NULL,
    personas_necesarias INTEGER NOT NULL,
    creador             TEXT    NOT NULL,
    duracion_horas      INTEGER NOT NULL,
    creado_en           INTEGER NOT NULL,
    expira_en           INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS participantes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    aviso_id  INTEGER NOT NULL REFERENCES avisos(id) ON DELETE CASCADE,
    nombre    TEXT    NOT NULL,
    unido_en  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_participantes_aviso ON participantes(aviso_id);
CREATE INDEX IF NOT EXISTS idx_avisos_cierre ON avisos(expira_en, inicio_evento)
"""

_ESQUEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS avisos (
    id                  BIGINT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo              TEXT    NOT NULL,
    categoria           TEXT    NOT NULL,
    descripcion         TEXT    NOT NULL DEFAULT '',
    lugar               TEXT    NOT NULL,
    inicio_evento       BIGINT  NOT NULL,
    personas_actuales   INTEGER NOT NULL,
    personas_necesarias INTEGER NOT NULL,
    creador             TEXT    NOT NULL,
    duracion_horas      INTEGER NOT NULL,
    creado_en           BIGINT  NOT NULL,
    expira_en           BIGINT  NOT NULL
);
CREATE TABLE IF NOT EXISTS participantes (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aviso_id  BIGINT NOT NULL REFERENCES avisos(id) ON DELETE CASCADE,
    nombre    TEXT   NOT NULL,
    unido_en  BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_participantes_aviso ON participantes(aviso_id);
CREATE INDEX IF NOT EXISTS idx_avisos_cierre ON avisos(expira_en, inicio_evento)
"""
# (los horarios se guardan como segundos Unix: un número entero)


def usa_postgres() -> bool:
    return URL_BD.startswith(("postgres://", "postgresql://"))


class _Conexion:
    """Envuelve SQLite o PostgreSQL para que el resto del código sea el mismo."""

    def __init__(self) -> None:
        self.es_postgres = usa_postgres()
        if self.es_postgres:
            import psycopg  # solo se necesita en el servidor
            from psycopg.rows import dict_row

            self._con = psycopg.connect(
                URL_BD,
                autocommit=True,
                row_factory=dict_row,
                prepare_threshold=None,
                connect_timeout=15,
            )
        else:
            self._con = sqlite3.connect(RUTA_BD, timeout=10, isolation_level=None)
            self._con.row_factory = sqlite3.Row
            self._con.execute("PRAGMA foreign_keys = ON")

    def ejecutar(self, sql: str, parametros=()):
        """Ejecuta SQL escrito con '?' como marcador (se adapta a PostgreSQL)."""
        if self.es_postgres:
            sql = sql.replace("?", "%s")
        return self._con.execute(sql, tuple(parametros))

    def insertar(self, sql: str, parametros) -> int:
        """Ejecuta un INSERT y devuelve el id nuevo."""
        if self.es_postgres:
            return self.ejecutar(sql + " RETURNING id", parametros).fetchone()["id"]
        return self.ejecutar(sql, parametros).lastrowid

    def bloquear_aviso(self, aviso_id: int):
        """Lee un aviso y lo bloquea hasta terminar la transacción."""
        extra = " FOR UPDATE" if self.es_postgres else ""
        return self.ejecutar(f"SELECT * FROM avisos WHERE id = ?{extra}", (aviso_id,)).fetchone()

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        if self.es_postgres:
            with self._con.transaction():
                yield
            return
        self._con.execute("BEGIN IMMEDIATE")  # SQLite: bloquea escrituras de otros
        try:
            yield
        except BaseException:
            self._con.execute("ROLLBACK")
            raise
        self._con.execute("COMMIT")

    def crear_tablas(self) -> None:
        esquema = _ESQUEMA_POSTGRES if self.es_postgres else _ESQUEMA_SQLITE
        if not self.es_postgres:
            self._con.execute("PRAGMA journal_mode = WAL")
        for sentencia in esquema.split(";"):
            if sentencia.strip():
                self._con.execute(sentencia)

    def cerrar(self) -> None:
        self._con.close()


@contextmanager
def _conexion() -> Iterator[_Conexion]:
    con = _Conexion()
    try:
        yield con
    finally:
        con.cerrar()


def inicializar() -> None:
    """Crea las tablas si no existen. Se puede llamar las veces que sea."""
    with _conexion() as con:
        con.crear_tablas()
    _invalidar_cache()


# --------------------------------------------------------------------------- #
# Caché en memoria
#
# Cada página abierta revisa cada pocos segundos si hay cambios. Para no
# consultar la base de datos todo el rato (la de Neon gratis tiene horas de
# cómputo limitadas), guardamos la lista en memoria y solo la volvemos a leer
# cuando alguien publica o se une. Funciona porque la app corre en un solo
# proceso, que es como corre NiceGUI.
# --------------------------------------------------------------------------- #

_candado = threading.Lock()
_version = 0
_cache_activos: list[Aviso] | None = None
_cache_activos_desde: datetime | None = None
_cache_detalle: dict[int, Aviso] = {}


def _invalidar_cache() -> None:
    global _version, _cache_activos, _cache_activos_desde
    with _candado:
        _version += 1
        _cache_activos = None
        _cache_activos_desde = None
        _cache_detalle.clear()


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #


def _ahora(ahora: datetime | None = None) -> datetime:
    return ahora if ahora is not None else datetime.now(ZONA_HORARIA)


def _a_ts(momento: datetime) -> int:
    return int(momento.timestamp())


def _de_ts(segundos: int) -> datetime:
    return datetime.fromtimestamp(int(segundos), ZONA_HORARIA)


def limpiar(texto: str | None) -> str:
    """Quita espacios sobrantes: '  Juan   Pérez ' -> 'Juan Pérez'."""
    return " ".join((texto or "").split())


def _clave_nombre(nombre: str) -> str:
    """Para comparar nombres sin importar mayúsculas: 'JUAN' == 'juan'."""
    return limpiar(nombre).casefold()


def _validar_largo(valor: str, campo: str, minimo: int, maximo: int) -> None:
    if len(valor) < minimo:
        raise ErrorValidacion(f"{campo}: escribe al menos {minimo} caracteres.")
    if len(valor) > maximo:
        raise ErrorValidacion(f"{campo}: máximo {maximo} caracteres.")


def _a_entero(valor, campo: str) -> int:
    if valor is None or valor == "":
        raise ErrorValidacion(f"Completa el campo «{campo}».")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ErrorValidacion(f"«{campo}» debe ser un número.") from None
    if not numero.is_integer():
        raise ErrorValidacion(f"«{campo}» debe ser un número entero.")
    return int(numero)


def armar_fecha_hora(fecha: str | None, hora: str | None) -> datetime:
    """Convierte '2026-11-14' + '20:30' en una fecha con zona horaria."""
    if not fecha:
        raise ErrorValidacion("Elige la fecha del evento.")
    if not hora:
        raise ErrorValidacion("Elige la hora del evento.")
    try:
        momento = datetime.strptime(f"{fecha} {hora[:5]}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise ErrorValidacion("La fecha u hora no es válida.") from None
    return momento.replace(tzinfo=ZONA_HORARIA)


def _fila_a_aviso(fila, participantes: list[str]) -> Aviso:
    return Aviso(
        id=int(fila["id"]),
        titulo=fila["titulo"],
        categoria=fila["categoria"],
        descripcion=fila["descripcion"],
        lugar=fila["lugar"],
        inicio_evento=_de_ts(fila["inicio_evento"]),
        personas_actuales=int(fila["personas_actuales"]),
        personas_necesarias=int(fila["personas_necesarias"]),
        creador=fila["creador"],
        duracion_horas=int(fila["duracion_horas"]),
        creado_en=_de_ts(fila["creado_en"]),
        expira_en=_de_ts(fila["expira_en"]),
        participantes=tuple(participantes),
    )


def _participantes_de(con: _Conexion, ids: list[int]) -> dict[int, list[str]]:
    resultado: dict[int, list[str]] = {i: [] for i in ids}
    if not ids:
        return resultado
    marcas = ",".join("?" * len(ids))
    filas = con.ejecutar(
        f"SELECT aviso_id, nombre FROM participantes "
        f"WHERE aviso_id IN ({marcas}) ORDER BY unido_en, id",
        ids,
    ).fetchall()
    for fila in filas:
        resultado[int(fila["aviso_id"])].append(fila["nombre"])
    return resultado


# --------------------------------------------------------------------------- #
# Operaciones
# --------------------------------------------------------------------------- #


def crear_aviso(
    *,
    creador: str,
    titulo: str,
    categoria: str,
    lugar: str,
    inicio_evento: datetime,
    personas_actuales,
    personas_necesarias,
    duracion_horas,
    descripcion: str = "",
    ahora: datetime | None = None,
) -> Aviso:
    """Valida los datos y publica el aviso. Lanza ErrorValidacion si algo falla."""
    ahora = _ahora(ahora)

    creador = limpiar(creador)
    titulo = limpiar(titulo)
    lugar = limpiar(lugar)
    descripcion = (descripcion or "").strip()

    # Se valida en el mismo orden en que aparecen los campos del formulario.
    _validar_largo(titulo, "Título", *LARGO_TITULO)
    if categoria not in CATEGORIAS:
        raise ErrorValidacion("Elige una categoría.")
    _validar_largo(lugar, "Lugar", *LARGO_LUGAR)

    if inicio_evento.tzinfo is None:
        inicio_evento = inicio_evento.replace(tzinfo=ZONA_HORARIA)
    if inicio_evento <= ahora:
        raise ErrorValidacion("La fecha y hora del evento ya pasaron.")
    if inicio_evento > ahora + timedelta(days=365):
        raise ErrorValidacion("El evento debe ser dentro del próximo año.")

    actuales = _a_entero(personas_actuales, "¿Cuántos son ahora?")
    necesarias = _a_entero(personas_necesarias, "¿Cuántos necesitan en total?")
    if actuales < 1:
        raise ErrorValidacion("Ustedes son al menos 1 (tú).")
    if necesarias > MAX_PERSONAS:
        raise ErrorValidacion(f"El máximo es {MAX_PERSONAS} personas por aviso.")
    if necesarias <= actuales:
        raise ErrorValidacion(
            "El total que necesitan debe ser mayor a los que ya son "
            "(si no, ¡no falta nadie!)."
        )

    if len(descripcion) > LARGO_MAX_DESCRIPCION:
        raise ErrorValidacion(f"Detalles: máximo {LARGO_MAX_DESCRIPCION} caracteres.")

    duracion = _a_entero(duracion_horas, "Duración del aviso")
    if duracion not in DURACIONES_PERMITIDAS:
        raise ErrorValidacion("El aviso puede durar 24 o 48 horas.")

    _validar_largo(creador, "Tu nombre", *LARGO_NOMBRE)

    expira_en = ahora + timedelta(hours=duracion)

    with _conexion() as con:
        nuevo_id = con.insertar(
            """
            INSERT INTO avisos (titulo, categoria, descripcion, lugar, inicio_evento,
                                personas_actuales, personas_necesarias, creador,
                                duracion_horas, creado_en, expira_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                titulo,
                categoria,
                descripcion,
                lugar,
                _a_ts(inicio_evento),
                actuales,
                necesarias,
                creador,
                duracion,
                _a_ts(ahora),
                _a_ts(expira_en),
            ),
        )
    _invalidar_cache()

    aviso = obtener_aviso(nuevo_id)
    assert aviso is not None
    return aviso


def obtener_aviso(aviso_id: int) -> Aviso | None:
    """Devuelve el aviso (abierto o cerrado) o None si no existe."""
    with _candado:
        if aviso_id in _cache_detalle:
            return _cache_detalle[aviso_id]
        version = _version

    with _conexion() as con:
        fila = con.ejecutar("SELECT * FROM avisos WHERE id = ?", (aviso_id,)).fetchone()
        if fila is None:
            return None
        aviso = _fila_a_aviso(fila, _participantes_de(con, [aviso_id])[aviso_id])

    with _candado:
        if version == _version:  # nadie escribió mientras leíamos
            _cache_detalle[aviso_id] = aviso
    return aviso


def avisos_activos(ahora: datetime | None = None) -> list[Aviso]:
    """Avisos abiertos (con cupo y dentro de plazo), del evento más próximo al más lejano."""
    global _cache_activos, _cache_activos_desde
    ahora = _ahora(ahora)

    with _candado:
        lista, desde, version = _cache_activos, _cache_activos_desde, _version

    if lista is None or desde is None or ahora < desde:
        ts = _a_ts(ahora)
        with _conexion() as con:
            filas = con.ejecutar(
                """
                SELECT a.*
                FROM avisos a
                LEFT JOIN participantes p ON p.aviso_id = a.id
                WHERE a.expira_en > ? AND a.inicio_evento > ?
                GROUP BY a.id
                HAVING a.personas_actuales + COUNT(p.id) < a.personas_necesarias
                ORDER BY a.inicio_evento ASC, a.id ASC
                """,
                (ts, ts),
            ).fetchall()
            nombres = _participantes_de(con, [int(f["id"]) for f in filas])
        lista = [_fila_a_aviso(f, nombres[int(f["id"])]) for f in filas]
        with _candado:
            if version == _version:
                _cache_activos, _cache_activos_desde = lista, ahora

    # Lo que se cerró por tiempo desde la última lectura se filtra aquí.
    return [a for a in lista if a.esta_abierto(ahora)]


def unirse(aviso_id: int, nombre: str, ahora: datetime | None = None) -> Aviso:
    """
    Suma a una persona al aviso y devuelve el aviso actualizado.

    Todo ocurre dentro de una transacción que bloquea el aviso: si dos
    personas presionan "Unirme" al mismo tiempo por el último cupo, solo una
    lo consigue.
    """
    ahora = _ahora(ahora)
    nombre = limpiar(nombre)
    _validar_largo(nombre, "Tu nombre", *LARGO_NOMBRE)

    with _conexion() as con, con.transaccion():
        fila = con.bloquear_aviso(aviso_id)
        if fila is None:
            raise ErrorValidacion("Este aviso no existe.")

        aviso = _fila_a_aviso(fila, _participantes_de(con, [aviso_id])[aviso_id])
        motivo = aviso.motivo_cierre(ahora)
        if motivo == COMPLETO:
            raise ErrorValidacion("Llegaste tarde: el grupo ya se completó.")
        if motivo == INICIADO:
            raise ErrorValidacion("El evento ya comenzó; el aviso está cerrado.")
        if motivo == VENCIDO:
            raise ErrorValidacion("Este aviso ya cerró: se acabó su plazo.")

        ya_estan = {_clave_nombre(n) for n in (aviso.creador, *aviso.participantes)}
        if _clave_nombre(nombre) in ya_estan:
            raise ErrorValidacion(
                f"Ya hay un «{nombre}» en este aviso. "
                "Agrega tu apellido o una inicial para diferenciarte."
            )

        con.ejecutar(
            "INSERT INTO participantes (aviso_id, nombre, unido_en) VALUES (?, ?, ?)",
            (aviso_id, nombre, _a_ts(ahora)),
        )
    _invalidar_cache()

    actualizado = obtener_aviso(aviso_id)
    assert actualizado is not None
    return actualizado
