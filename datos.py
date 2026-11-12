"""
datos.py — Reglas y almacenamiento de los avisos de "Falta Uno".

Dónde se guardan los datos:
  * En tu computador (sin configurar nada): un archivo SQLite, avisos.db.
  * En internet: si existe la variable de entorno DATABASE_URL, se usa esa
    base de datos PostgreSQL (por ejemplo, una gratuita de Neon).

La interfaz (app.py) solo llama a las funciones de este archivo: si más
adelante rehacemos el diseño, esta parte no se toca.

Quién es quién (sin cuentas ni contraseñas):
  Cada navegador recibe un identificador al azar guardado en una cookie
  (lo pone app.py). Con él sabemos qué avisos publicó esa persona y a cuáles
  se unió, para mostrárselos en su buzón.

Reglas:
  * Quien publica indica cuántos son ahora y cuántos necesitan en total.
    No necesita escribir su nombre.
  * El aviso dura 24 o 48 horas (lo elige quien publica).
  * En el tablero público, el aviso desaparece cuando:
      - se completan los cupos, o
      - se cumple el plazo de 24/48 h, o
      - llega la hora del evento (no tiene sentido unirse a algo que ya empezó).
  * En el buzón de quien lo publicó, el aviso sigue visible (aunque se llene)
    hasta que se cumple su plazo de 24/48 h.
  * En el buzón de quien se unió, el aviso sigue visible hasta unas horas
    después de que empieza el evento, para recordar dónde y cuándo es.
  * Quien publicó un aviso puede eliminarlo. Sale del tablero y de su buzón;
    a quienes se habían unido les queda en el buzón marcado como cancelado.
  * Quien se unió puede salirse antes de que empiece el evento. Su cupo queda
    libre y, si el aviso sigue dentro de plazo, vuelve a aparecer en el
    tablero (eso pasa solo: el tablero siempre muestra los avisos con cupo).
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

import filtro  # palabras inapropiadas

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

ZONA_HORARIA = ZoneInfo("America/Santiago")

URL_BD = os.environ.get("DATABASE_URL", "").strip()  # PostgreSQL en internet
RUTA_BD = Path(__file__).with_name("avisos.db")  # SQLite en tu computador

DURACIONES_PERMITIDAS = (24, 48)
MAX_PERSONAS = 100
HORAS_EN_BUZON_TRAS_INICIO = 3  # el evento sigue en el buzón hasta 3 h después de empezar

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
CANCELADO = "cancelado"
COMPLETO = "completo"
VENCIDO = "vencido"
INICIADO = "iniciado"


class ErrorValidacion(Exception):
    """Error con un mensaje listo para mostrarle a la persona."""


# --------------------------------------------------------------------------- #
# Modelo
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Participante:
    nombre: str
    persona_id: str | None  # identificador del navegador (None en avisos antiguos)


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
    creador: str  # nombre de quien publicó (vacío en avisos nuevos)
    creador_id: str | None  # navegador de quien publicó
    duracion_horas: int
    creado_en: datetime
    expira_en: datetime
    cancelado_en: datetime | None  # cuándo lo eliminó quien lo publicó (None si sigue)
    inscritos: tuple[Participante, ...]  # quienes se unieron desde la página

    @property
    def participantes(self) -> tuple[str, ...]:
        return tuple(p.nombre for p in self.inscritos)

    @property
    def cancelado(self) -> bool:
        return self.cancelado_en is not None

    @property
    def ocupados(self) -> int:
        return self.personas_actuales + len(self.inscritos)

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
    def visible_en_buzon_hasta(self) -> datetime:
        """Hasta cuándo lo ve en su buzón alguien que se unió."""
        return self.inicio_evento + timedelta(hours=HORAS_EN_BUZON_TRAS_INICIO)

    @property
    def nombre_categoria(self) -> str:
        return CATEGORIAS.get(self.categoria, "Otro")

    def motivo_cierre(self, ahora: datetime | None = None) -> str | None:
        """None si está abierto; si no, CANCELADO, COMPLETO, INICIADO o VENCIDO."""
        ahora = _ahora(ahora)
        if self.cancelado:
            return CANCELADO
        if self.esta_lleno:
            return COMPLETO
        if ahora >= self.inicio_evento:
            return INICIADO
        if ahora >= self.expira_en:
            return VENCIDO
        return None

    def esta_abierto(self, ahora: datetime | None = None) -> bool:
        return self.motivo_cierre(ahora) is None

    def es_de(self, persona_id: str | None) -> bool:
        """¿Lo publicó esta persona?"""
        return bool(persona_id) and persona_id == self.creador_id

    def tiene_inscrito(self, persona_id: str | None) -> bool:
        """¿Esta persona ya se unió?"""
        return bool(persona_id) and any(p.persona_id == persona_id for p in self.inscritos)


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

# Columnas agregadas después de la primera versión. Se suman a las tablas que
# ya existen sin borrar nada (por eso no están en el CREATE TABLE de arriba).
_COLUMNAS_NUEVAS = (
    ("avisos", "creador_id", "TEXT"),
    ("participantes", "persona_id", "TEXT"),
    ("avisos", "cancelado_en", "BIGINT"),
)
_INDICES_NUEVOS = (
    "CREATE INDEX IF NOT EXISTS idx_avisos_creador ON avisos(creador_id)",
    "CREATE INDEX IF NOT EXISTS idx_participantes_persona ON participantes(persona_id)",
)


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

    def _columnas(self, tabla: str) -> set[str]:
        if self.es_postgres:
            filas = self.ejecutar(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ?",
                (tabla,),
            ).fetchall()
            return {f["column_name"] for f in filas}
        return {f["name"] for f in self._con.execute(f"PRAGMA table_info({tabla})")}

    def crear_tablas(self) -> None:
        esquema = _ESQUEMA_POSTGRES if self.es_postgres else _ESQUEMA_SQLITE
        if not self.es_postgres:
            self._con.execute("PRAGMA journal_mode = WAL")
        for sentencia in esquema.split(";"):
            if sentencia.strip():
                self._con.execute(sentencia)
        # Actualiza tablas creadas por versiones anteriores (no borra nada).
        for tabla, columna, tipo in _COLUMNAS_NUEVAS:
            if columna not in self._columnas(tabla):
                self._con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
        for sentencia in _INDICES_NUEVOS:
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
    """Crea o actualiza las tablas. Se puede llamar las veces que sea."""
    with _conexion() as con:
        con.crear_tablas()
    _invalidar_cache()


# --------------------------------------------------------------------------- #
# Caché en memoria
#
# Cada página abierta revisa cada pocos segundos si hay cambios. Para no
# consultar la base de datos todo el rato (la de Neon gratis tiene horas de
# cómputo limitadas), guardamos las listas en memoria y solo las volvemos a
# leer cuando alguien publica o se une. Funciona porque la app corre en un
# solo proceso, que es como corre NiceGUI.
# --------------------------------------------------------------------------- #

_candado = threading.Lock()
_version = 0
_cache_activos: tuple[datetime, list[Aviso]] | None = None
_cache_detalle: dict[int, Aviso] = {}
_cache_buzon: dict[str, tuple[datetime, list[Aviso], list[Aviso]]] = {}


def _invalidar_cache() -> None:
    global _version, _cache_activos
    with _candado:
        _version += 1
        _cache_activos = None
        _cache_detalle.clear()
        _cache_buzon.clear()


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


def _sin_groserias(texto: str, campo: str, plural: bool = False) -> None:
    """Si hay palabras inapropiadas, avisa cuáles para que la persona las cambie."""
    malas = filtro.encontradas(texto)
    if malas:
        lista = ", ".join(f"«{m}»" for m in malas)
        verbo = "tienen" if plural else "tiene"
        raise ErrorValidacion(
            f"{campo} {verbo} palabras inapropiadas ({lista}). Cámbialas para poder publicar."
        )


def _fila_a_aviso(fila, inscritos: list[Participante]) -> Aviso:
    # Lo guardado antes del filtro (o con palabras que se agreguen a la lista
    # después) se muestra sin esas palabras.
    return Aviso(
        id=int(fila["id"]),
        titulo=filtro.quitar(fila["titulo"]) or "Aviso",
        categoria=fila["categoria"],
        descripcion=filtro.quitar(fila["descripcion"]),
        lugar=filtro.quitar(fila["lugar"]) or "Lugar por confirmar",
        inicio_evento=_de_ts(fila["inicio_evento"]),
        personas_actuales=int(fila["personas_actuales"]),
        personas_necesarias=int(fila["personas_necesarias"]),
        creador=filtro.quitar(fila["creador"] or ""),
        creador_id=fila["creador_id"],
        duracion_horas=int(fila["duracion_horas"]),
        creado_en=_de_ts(fila["creado_en"]),
        expira_en=_de_ts(fila["expira_en"]),
        cancelado_en=_de_ts(fila["cancelado_en"]) if fila["cancelado_en"] is not None else None,
        inscritos=tuple(inscritos),
    )


def _inscritos_de(con: _Conexion, ids: list[int]) -> dict[int, list[Participante]]:
    resultado: dict[int, list[Participante]] = {i: [] for i in ids}
    if not ids:
        return resultado
    marcas = ",".join("?" * len(ids))
    filas = con.ejecutar(
        f"SELECT aviso_id, nombre, persona_id FROM participantes "
        f"WHERE aviso_id IN ({marcas}) ORDER BY unido_en, id",
        ids,
    ).fetchall()
    for fila in filas:
        nombre = filtro.quitar(fila["nombre"]) or "Anónimo"
        resultado[int(fila["aviso_id"])].append(Participante(nombre, fila["persona_id"]))
    return resultado


def _leer_avisos(con: _Conexion, sql: str, parametros) -> list[Aviso]:
    """Ejecuta un SELECT de avisos y les agrega sus participantes (sin repetir)."""
    filas, vistos = [], set()
    for fila in con.ejecutar(sql, parametros).fetchall():
        if int(fila["id"]) not in vistos:
            vistos.add(int(fila["id"]))
            filas.append(fila)
    inscritos = _inscritos_de(con, [int(f["id"]) for f in filas])
    return [_fila_a_aviso(f, inscritos[int(f["id"])]) for f in filas]


# --------------------------------------------------------------------------- #
# Operaciones
# --------------------------------------------------------------------------- #


def crear_aviso(
    *,
    titulo: str,
    categoria: str,
    lugar: str,
    inicio_evento: datetime,
    personas_actuales,
    personas_necesarias,
    duracion_horas,
    descripcion: str = "",
    creador_id: str | None = None,
    creador: str = "",
    ahora: datetime | None = None,
) -> Aviso:
    """Valida los datos y publica el aviso. Lanza ErrorValidacion si algo falla."""
    ahora = _ahora(ahora)

    titulo = limpiar(titulo)
    lugar = limpiar(lugar)
    creador = limpiar(creador)[: LARGO_NOMBRE[1]]
    descripcion = (descripcion or "").strip()

    # Se valida en el mismo orden en que aparecen los campos del formulario.
    _validar_largo(titulo, "Título", *LARGO_TITULO)
    _sin_groserias(titulo, "El título")
    if categoria not in CATEGORIAS:
        raise ErrorValidacion("Elige una categoría.")
    _validar_largo(lugar, "Lugar", *LARGO_LUGAR)
    _sin_groserias(lugar, "El lugar")
    creador = filtro.quitar(creador)

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
    _sin_groserias(descripcion, "Los detalles", plural=True)

    duracion = _a_entero(duracion_horas, "Duración del aviso")
    if duracion not in DURACIONES_PERMITIDAS:
        raise ErrorValidacion("El aviso puede durar 24 o 48 horas.")

    expira_en = ahora + timedelta(hours=duracion)

    with _conexion() as con:
        nuevo_id = con.insertar(
            """
            INSERT INTO avisos (titulo, categoria, descripcion, lugar, inicio_evento,
                                personas_actuales, personas_necesarias, creador,
                                creador_id, duracion_horas, creado_en, expira_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                creador_id or None,
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
        encontrados = _leer_avisos(con, "SELECT * FROM avisos WHERE id = ?", (aviso_id,))
    if not encontrados:
        return None
    aviso = encontrados[0]

    with _candado:
        if version == _version:  # nadie escribió mientras leíamos
            _cache_detalle[aviso_id] = aviso
    return aviso


def avisos_activos(ahora: datetime | None = None) -> list[Aviso]:
    """Tablero público: avisos con cupo y dentro de plazo, del más próximo al más lejano."""
    global _cache_activos
    ahora = _ahora(ahora)

    with _candado:
        guardado, version = _cache_activos, _version

    if guardado is None or ahora < guardado[0]:
        ts = _a_ts(ahora)
        with _conexion() as con:
            lista = _leer_avisos(
                con,
                """
                SELECT a.*
                FROM avisos a
                LEFT JOIN participantes p ON p.aviso_id = a.id
                WHERE a.expira_en > ? AND a.inicio_evento > ? AND a.cancelado_en IS NULL
                GROUP BY a.id
                HAVING a.personas_actuales + COUNT(p.id) < a.personas_necesarias
                ORDER BY a.inicio_evento ASC, a.id ASC
                """,
                (ts, ts),
            )
        with _candado:
            if version == _version:
                _cache_activos = (ahora, lista)
    else:
        lista = guardado[1]

    # Lo que se cerró por tiempo desde la última lectura se filtra aquí.
    return [a for a in lista if a.esta_abierto(ahora)]


def mi_buzon(persona_id: str | None, ahora: datetime | None = None) -> tuple[list[Aviso], list[Aviso]]:
    """
    Devuelve (me_uni, organizo) para el buzón de una persona.

    * me_uni: avisos a los que se unió, hasta unas horas después del evento.
    * organizo: avisos que publicó, hasta que se cumple su plazo de 24/48 h
      (aunque ya se hayan llenado).
    """
    if not persona_id:
        return [], []
    ahora = _ahora(ahora)

    with _candado:
        guardado, version = _cache_buzon.get(persona_id), _version

    if guardado is None or ahora < guardado[0]:
        ts = _a_ts(ahora)
        with _conexion() as con:
            me_uni = _leer_avisos(
                con,
                """
                SELECT a.* FROM avisos a
                JOIN participantes p ON p.aviso_id = a.id
                WHERE p.persona_id = ? AND a.inicio_evento > ?
                ORDER BY a.inicio_evento ASC, a.id ASC
                """,
                (persona_id, ts - HORAS_EN_BUZON_TRAS_INICIO * 3600),
            )
            organizo = _leer_avisos(
                con,
                """
                SELECT * FROM avisos
                WHERE creador_id = ? AND expira_en > ? AND cancelado_en IS NULL
                ORDER BY inicio_evento ASC, id ASC
                """,
                (persona_id, ts),
            )
        with _candado:
            if version == _version:
                _cache_buzon[persona_id] = (ahora, me_uni, organizo)
    else:
        _, me_uni, organizo = guardado

    return (
        [a for a in me_uni if ahora < a.visible_en_buzon_hasta],
        [a for a in organizo if ahora < a.expira_en],
    )


def nombre_usado(persona_id: str | None) -> str:
    """El último nombre con que esta persona se unió a algo (para no reescribirlo)."""
    if not persona_id:
        return ""
    with _conexion() as con:
        fila = con.ejecutar(
            "SELECT nombre FROM participantes WHERE persona_id = ? ORDER BY id DESC LIMIT 1",
            (persona_id,),
        ).fetchone()
    return fila["nombre"] if fila else ""


def unirse(
    aviso_id: int,
    nombre: str,
    persona_id: str | None = None,
    ahora: datetime | None = None,
) -> Aviso:
    """
    Suma a una persona al aviso y devuelve el aviso actualizado.

    Todo ocurre dentro de una transacción que bloquea el aviso: si dos
    personas presionan "Unirme" al mismo tiempo por el último cupo, solo una
    lo consigue.
    """
    ahora = _ahora(ahora)
    nombre = limpiar(nombre)
    _validar_largo(nombre, "Tu nombre", *LARGO_NOMBRE)
    if filtro.contiene(nombre):
        raise ErrorValidacion(
            "Ese nombre tiene palabras inapropiadas. Usa tu nombre real o un apodo amable."
        )

    with _conexion() as con, con.transaccion():
        fila = con.bloquear_aviso(aviso_id)
        if fila is None:
            raise ErrorValidacion("Este aviso no existe.")

        aviso = _fila_a_aviso(fila, _inscritos_de(con, [aviso_id])[aviso_id])
        if aviso.es_de(persona_id):
            raise ErrorValidacion("Este aviso es tuyo: ya cuentas dentro del grupo.")
        if aviso.tiene_inscrito(persona_id):
            raise ErrorValidacion("Ya estás anotado en este aviso. Míralo en tu buzón.")

        motivo = aviso.motivo_cierre(ahora)
        if motivo == CANCELADO:
            raise ErrorValidacion("Este aviso fue cancelado por quien lo publicó.")
        if motivo == COMPLETO:
            raise ErrorValidacion("Llegaste tarde: el grupo ya se completó.")
        if motivo == INICIADO:
            raise ErrorValidacion("El evento ya comenzó; el aviso está cerrado.")
        if motivo == VENCIDO:
            raise ErrorValidacion("Este aviso ya cerró: se acabó su plazo.")

        ya_estan = {_clave_nombre(n) for n in (aviso.creador, *aviso.participantes) if n}
        if _clave_nombre(nombre) in ya_estan:
            raise ErrorValidacion(
                f"Ya hay un «{nombre}» en este aviso. "
                "Agrega tu apellido o una inicial para diferenciarte."
            )

        con.ejecutar(
            "INSERT INTO participantes (aviso_id, nombre, persona_id, unido_en) VALUES (?, ?, ?, ?)",
            (aviso_id, nombre, persona_id or None, _a_ts(ahora)),
        )
    _invalidar_cache()

    actualizado = obtener_aviso(aviso_id)
    assert actualizado is not None
    return actualizado


def salirse(aviso_id: int, persona_id: str | None, ahora: datetime | None = None) -> Aviso:
    """
    Saca a una persona de un aviso al que se había unido y devuelve el aviso
    actualizado. Se puede hasta que empieza el evento. Si el aviso queda con
    cupo y dentro de plazo, vuelve a aparecer en el tablero.
    """
    ahora = _ahora(ahora)
    if not persona_id:
        raise ErrorValidacion("No pudimos reconocer tu navegador. Recarga la página.")

    with _conexion() as con, con.transaccion():
        fila = con.bloquear_aviso(aviso_id)
        if fila is None:
            raise ErrorValidacion("Este aviso no existe.")
        aviso = _fila_a_aviso(fila, _inscritos_de(con, [aviso_id])[aviso_id])
        if not aviso.tiene_inscrito(persona_id):
            raise ErrorValidacion("No estás anotado en este aviso.")
        if ahora >= aviso.inicio_evento and not aviso.cancelado:
            raise ErrorValidacion("El evento ya empezó: ya no puedes salirte desde aquí.")
        con.ejecutar(
            "DELETE FROM participantes WHERE aviso_id = ? AND persona_id = ?",
            (aviso_id, persona_id),
        )
    _invalidar_cache()

    actualizado = obtener_aviso(aviso_id)
    assert actualizado is not None
    return actualizado


def eliminar_aviso(aviso_id: int, persona_id: str | None, ahora: datetime | None = None) -> Aviso:
    """
    Quien publicó el aviso lo elimina. Desaparece del tablero y de su buzón.
    Quienes ya se habían unido lo siguen viendo en su buzón, marcado como
    cancelado, para que se enteren (y pueden quitarlo de ahí).
    """
    ahora = _ahora(ahora)
    with _conexion() as con, con.transaccion():
        fila = con.bloquear_aviso(aviso_id)
        if fila is None:
            raise ErrorValidacion("Este aviso no existe.")
        aviso = _fila_a_aviso(fila, [])
        if not aviso.es_de(persona_id):
            raise ErrorValidacion("Solo quien publicó el aviso puede eliminarlo.")
        if aviso.cancelado:
            raise ErrorValidacion("Este aviso ya estaba eliminado.")
        con.ejecutar(
            "UPDATE avisos SET cancelado_en = ? WHERE id = ?", (_a_ts(ahora), aviso_id)
        )
    _invalidar_cache()

    actualizado = obtener_aviso(aviso_id)
    assert actualizado is not None
    return actualizado
