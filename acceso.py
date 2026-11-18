"""
acceso.py — Ingreso con correo institucional (clase Acceso del informe).

Cómo funciona:
  1. El estudiante escribe su correo @alumnos.ulagos.cl.
  2. Le llega un código de 6 dígitos (vale 10 minutos, 5 intentos).
  3. La primera vez escribe su nombre: es el que verán los demás al unirse o
     comentar. El correo nunca se muestra.
  4. El correo queda unido a ese navegador por un año: desde ahí entra
     directo, sin código. Si otra persona intenta entrar con ese correo desde
     otro navegador, la página le dice que el correo ya está en uso (ni
     siquiera se envía el código). Para cambiar de navegador, el estudiante
     cierra sesión en el anterior; si ya no lo tiene, la administración
     puede liberar el correo desde /admin.

El correo se envía con la API HTTP de Brevo (Render gratis bloquea el envío
por SMTP). Se configura con dos variables de entorno, nunca en el código:
  * BREVO_API_KEY     — la clave de la API de Brevo.
  * CORREO_REMITENTE  — el correo verificado en Brevo que aparece como remitente.
Sin ellas, la página funciona en modo de prueba: el código se muestra en
pantalla, con un aviso visible, en vez de enviarse.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import datos
import filtro
from datos import ErrorValidacion

URL_BREVO = "https://api.brevo.com/v3/smtp/email"
_FORMATO_DISPOSITIVO = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class _CodigoPendiente:
    codigo: str
    vence: float
    intentos: int = 0


class Acceso:
    """«control» Ingreso con correo institucional, código por correo y sesiones."""

    DOMINIO_PERMITIDO = "alumnos.ulagos.cl"
    LARGO_CODIGO = 6
    MINUTOS_CODIGO = 10
    MAX_INTENTOS_CODIGO = 5
    MAX_DISPOSITIVOS = 1  # navegadores con sesión abierta por correo
    DIAS_SESION = 365
    COOKIE_SESION = "falta_uno_id"  # el mismo nombre de antes: nadie pierde lo que tenía
    SEGUNDOS_ENTRE_ENVIOS = 60
    MAX_ENVIOS_POR_HORA = 5  # por correo
    MAX_CORREOS_POR_DIA = 280  # el plan gratis de Brevo permite 300
    MINUTOS_EN_MEMORIA = 5  # cuánto se recuerda una sesión sin volver a la base de datos

    MENSAJE_EN_USO = (
        "Este correo ya está en uso en otro navegador. Si es tuyo, cierra sesión en ese navegador "
        "(botón con tus iniciales → Cerrar sesión) o pide a la administración que lo libere."
    )

    _CORREO = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?@" + re.escape(DOMINIO_PERMITIDO) + r"$")

    def __init__(
        self,
        clave_correo: str = "",
        remitente: str = "",
        enviar: Callable[[str, str], None] | None = None,
    ) -> None:
        self.__CLAVE_CORREO = clave_correo
        self.__remitente = remitente
        self.__enviar = enviar
        self.__codigos_pendientes: dict[str, _CodigoPendiente] = {}
        self.__verificados: dict[str, float] = {}  # correo -> hasta cuándo puede registrarse
        self.__envios: dict[str, list[float]] = {}
        self.__envios_del_dia: list[float] = []
        self.__sesiones: dict[str, tuple[str, str, float]] = {}  # dispositivo -> (persona, nombre, hasta)
        self.__candado = threading.Lock()

    # ------------------------------------------------------------------ #
    # Correo y código
    # ------------------------------------------------------------------ #

    @property
    def modo_prueba(self) -> bool:
        """Sin clave de Brevo el código se muestra en pantalla en vez de enviarse."""
        return self.__enviar is None and not (self.__CLAVE_CORREO and self.__remitente)

    def normalizar_correo(self, correo: str | None) -> str:
        return "".join((correo or "").split()).lower()

    def correo_valido(self, correo: str | None) -> bool:
        return bool(self._CORREO.match(self.normalizar_correo(correo)))

    def _exigir_correo(self, correo: str | None) -> str:
        correo = self.normalizar_correo(correo)
        if not correo:
            raise ErrorValidacion("Escribe tu correo institucional.")
        if not correo.endswith("@" + self.DOMINIO_PERMITIDO):
            raise ErrorValidacion(f"Usa tu correo institucional, el que termina en @{self.DOMINIO_PERMITIDO}.")
        if not self._CORREO.match(correo):
            raise ErrorValidacion("Ese correo no parece válido. Revisa que esté bien escrito.")
        return correo

    def _generar_codigo(self) -> str:
        return f"{secrets.randbelow(10 ** self.LARGO_CODIGO):0{self.LARGO_CODIGO}d}"

    def enviar_codigo(self, correo: str | None, dispositivo: str | None = None) -> str | None:
        """
        Envía un código nuevo al correo. Devuelve el código solo en modo de
        prueba (para mostrarlo en pantalla); si se envió por correo, None.
        Si el correo ya está en uso en otro navegador, no envía nada.
        """
        correo = self._exigir_correo(correo)
        with datos._conexion() as con:
            if self._en_uso(con, correo, dispositivo):
                raise ErrorValidacion(self.MENSAJE_EN_USO)
        momento = time.time()
        with self.__candado:
            self._limpiar_vencidos(momento)
            envios = [t for t in self.__envios.get(correo, []) if t > momento - 3600]
            if envios and momento - envios[-1] < self.SEGUNDOS_ENTRE_ENVIOS:
                espera = max(math.ceil(self.SEGUNDOS_ENTRE_ENVIOS - (momento - envios[-1])), 1)
                raise ErrorValidacion(f"Ya te enviamos un código. Puedes pedir otro en {espera} segundos.")
            if len(envios) >= self.MAX_ENVIOS_POR_HORA:
                raise ErrorValidacion("Pediste muchos códigos seguidos. Intenta de nuevo en una hora.")
            self.__envios_del_dia = [t for t in self.__envios_del_dia if t > momento - 86400]
            if not self.modo_prueba and len(self.__envios_del_dia) >= self.MAX_CORREOS_POR_DIA:
                raise ErrorValidacion("Hoy se enviaron muchos códigos. Intenta de nuevo mañana.")
            codigo = self._generar_codigo()
            envios.append(momento)
            self.__envios[correo] = envios
            self.__envios_del_dia.append(momento)
            self.__codigos_pendientes[correo] = _CodigoPendiente(codigo, momento + self.MINUTOS_CODIGO * 60)

        if self.modo_prueba:
            return codigo
        try:
            (self.__enviar or self._enviar_por_brevo)(correo, codigo)
        except ErrorValidacion:
            with self.__candado:
                self.__codigos_pendientes.pop(correo, None)
                self.__envios[correo] = self.__envios.get(correo, [])[:-1]
            raise
        return None

    def _enviar_por_brevo(self, correo: str, codigo: str) -> None:
        minutos = self.MINUTOS_CODIGO
        cuerpo = {
            "sender": {"name": "Join In", "email": self.__remitente},
            "to": [{"email": correo}],
            "subject": f"Tu código para Join In: {codigo}",
            "textContent": (
                f"Tu código para entrar a Join In es {codigo}.\n\n"
                f"Vale por {minutos} minutos. Si no lo pediste, ignora este correo."
            ),
            "htmlContent": (
                '<div style="font-family:Arial,sans-serif;font-size:16px;color:#1f2a44">'
                "<p>Tu código para entrar a <b>Join In</b> es:</p>"
                f'<p style="font-size:32px;letter-spacing:6px;font-weight:bold">{codigo}</p>'
                f"<p>Vale por {minutos} minutos. Si no lo pediste, ignora este correo.</p>"
                "</div>"
            ),
        }
        pedido = urllib.request.Request(
            URL_BREVO,
            data=json.dumps(cuerpo).encode("utf-8"),
            method="POST",
            headers={
                "api-key": self.__CLAVE_CORREO,
                "content-type": "application/json",
                "accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=15) as respuesta:
                respuesta.read()
        except urllib.error.HTTPError as error:
            # 401: clave mal copiada · 400: remitente sin verificar en Brevo
            print(f"[acceso] Brevo respondió {error.code} al enviar un código", flush=True)
            raise ErrorValidacion("No pudimos enviar el correo. Intenta de nuevo en unos minutos.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(f"[acceso] no se pudo conectar con Brevo: {error}", flush=True)
            raise ErrorValidacion("No pudimos enviar el correo. Intenta de nuevo en unos minutos.") from None

    def verificar_codigo(self, correo: str | None, codigo: str | None) -> bool:
        """
        True si el código es el último enviado a ese correo y sigue vigente.
        False si no coincide. Lanza ErrorValidacion si venció, si no se pidió
        o si se acabaron los intentos (hay que pedir otro).
        """
        correo = self._exigir_correo(correo)
        codigo = "".join((codigo or "").split())
        momento = time.time()
        with self.__candado:
            pendiente = self.__codigos_pendientes.get(correo)
            if pendiente is None:
                raise ErrorValidacion("Pide un código primero.")
            if momento > pendiente.vence:
                del self.__codigos_pendientes[correo]
                raise ErrorValidacion("El código venció. Pide uno nuevo.")
            if not hmac.compare_digest(codigo.encode(), pendiente.codigo.encode()):
                pendiente.intentos += 1
                if pendiente.intentos >= self.MAX_INTENTOS_CODIGO:
                    del self.__codigos_pendientes[correo]
                    raise ErrorValidacion("Fallaste el código demasiadas veces. Pide uno nuevo.")
                return False
            del self.__codigos_pendientes[correo]
            self.__verificados[correo] = momento + self.MINUTOS_CODIGO * 60
            return True

    def _limpiar_vencidos(self, momento: float) -> None:
        for correo in [c for c, p in self.__codigos_pendientes.items() if momento > p.vence]:
            del self.__codigos_pendientes[correo]
        for correo in [c for c, hasta in self.__verificados.items() if momento > hasta]:
            del self.__verificados[correo]
        for correo in [c for c, lista in self.__envios.items() if not lista or lista[-1] < momento - 3600]:
            del self.__envios[correo]

    # ------------------------------------------------------------------ #
    # Estudiantes y sesiones
    # ------------------------------------------------------------------ #

    def estudiante_existe(self, correo: str | None) -> bool:
        correo = self.normalizar_correo(correo)
        with datos._conexion() as con:
            return con.ejecutar("SELECT 1 FROM estudiantes WHERE correo = ?", (correo,)).fetchone() is not None

    def _validar_nombre(self, nombre: str | None, persona_id: str | None) -> str:
        nombre = datos.limpiar(nombre)
        datos._validar_largo(nombre, "Tu nombre", *datos.LARGO_NOMBRE)
        if not any(c.isalpha() for c in nombre):
            raise ErrorValidacion("Tu nombre debe tener letras.")
        if filtro.contiene(nombre):
            datos.registrar_filtrado("Nombre", nombre, filtro.encontradas(nombre), persona_id)
            raise ErrorValidacion("Ese nombre tiene palabras inapropiadas. Usa tu nombre real o un apodo amable.")
        return nombre

    def registrar(
        self, correo: str | None, nombre: str | None, dispositivo: str | None, ahora: datetime | None = None
    ) -> str:
        """
        Abre la sesión del navegador después de verificar el código. La primera
        vez crea al estudiante con su nombre; después el nombre se ignora.
        Devuelve el persona_id del estudiante.
        """
        correo = self._exigir_correo(correo)
        if not dispositivo or not _FORMATO_DISPOSITIVO.match(dispositivo):
            raise ErrorValidacion("No pudimos reconocer tu navegador. Recarga la página.")
        with self.__candado:
            if self.__verificados.get(correo, 0) < time.time():
                raise ErrorValidacion("Tu código ya no es válido. Pide uno nuevo.")

        ts = datos._a_ts(datos._ahora(ahora))
        ms = int((ahora.timestamp() if ahora else time.time()) * 1000)  # sesiones: al milisegundo
        nuevo = not self.estudiante_existe(correo)
        if nuevo:
            nombre = self._validar_nombre(nombre, dispositivo)

        with datos._conexion() as con, con.transaccion():
            if nuevo:
                con.ejecutar(
                    "INSERT INTO estudiantes (persona_id, correo, nombre, creado_en) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (correo) DO NOTHING",
                    (uuid.uuid4().hex, correo, nombre, ts),
                )
            fila = con.ejecutar(
                "SELECT persona_id, nombre FROM estudiantes WHERE correo = ?", (correo,)
            ).fetchone()
            persona_id, nombre = fila["persona_id"], fila["nombre"]
            if self._en_uso(con, correo, dispositivo):  # otro navegador entró mientras tanto
                raise ErrorValidacion(self.MENSAJE_EN_USO)
            self._traspasar_datos(con, dispositivo, persona_id)
            con.ejecutar("DELETE FROM sesiones WHERE dispositivo = ?", (dispositivo,))
            con.ejecutar(
                "INSERT INTO sesiones (dispositivo, persona_id, creada_en, usada_en) VALUES (?, ?, ?, ?)",
                (dispositivo, persona_id, ms, ms),
            )

        with self.__candado:
            self.__verificados.pop(correo, None)
            self.__sesiones.pop(dispositivo, None)
        datos._invalidar_cache()
        return persona_id

    def _limite_sesiones_ms(self) -> int:
        """Las sesiones creadas antes de esto ya cumplieron un año."""
        return int(time.time() * 1000) - self.DIAS_SESION * 86_400_000

    def _en_uso(self, con, correo: str, dispositivo: str | None) -> bool:
        """¿El correo ya tiene sesión abierta en otro navegador (y no queda lugar)?"""
        con.ejecutar(
            "DELETE FROM sesiones WHERE creada_en < ? AND persona_id IN "
            "(SELECT persona_id FROM estudiantes WHERE correo = ?)",
            (self._limite_sesiones_ms(), correo),
        )
        fila = con.ejecutar(
            "SELECT COUNT(*) AS n FROM sesiones s JOIN estudiantes e ON e.persona_id = s.persona_id "
            "WHERE e.correo = ? AND s.dispositivo <> ?",
            (correo, dispositivo or ""),
        ).fetchone()
        return int(fila["n"]) >= self.MAX_DISPOSITIVOS

    def liberar_correo(self, correo: str | None) -> int:
        """
        Para la administración: cierra la sesión de ese correo en todos los
        navegadores, para que el estudiante pueda entrar desde otro (por
        ejemplo, si cambió de celular). Devuelve cuántas sesiones cerró.
        """
        correo = self._exigir_correo(correo)
        with datos._conexion() as con:
            fila = con.ejecutar("SELECT persona_id FROM estudiantes WHERE correo = ?", (correo,)).fetchone()
            if fila is None:
                raise ErrorValidacion("Ningún estudiante ha ingresado con ese correo.")
            dispositivos = [
                f["dispositivo"]
                for f in con.ejecutar(
                    "SELECT dispositivo FROM sesiones WHERE persona_id = ?", (fila["persona_id"],)
                ).fetchall()
            ]
            con.ejecutar("DELETE FROM sesiones WHERE persona_id = ?", (fila["persona_id"],))
        with self.__candado:
            for dispositivo in dispositivos:
                self.__sesiones.pop(dispositivo, None)
        return len(dispositivos)

    def quitar_sesiones_de_mas(self) -> int:
        """
        Al iniciar: si un correo quedó abierto en más navegadores de los
        permitidos (versiones anteriores dejaban 2), deja solo el usado más
        recientemente. Devuelve cuántas sesiones cerró.
        """
        with datos._conexion() as con:
            n = int(con.ejecutar("SELECT COUNT(*) AS n FROM sesiones").fetchone()["n"])
            con.ejecutar(
                "DELETE FROM sesiones WHERE EXISTS (SELECT 1 FROM sesiones otra "
                "WHERE otra.persona_id = sesiones.persona_id AND (otra.usada_en > sesiones.usada_en "
                "OR (otra.usada_en = sesiones.usada_en AND otra.dispositivo > sesiones.dispositivo)))"
            )
            quedan = int(con.ejecutar("SELECT COUNT(*) AS n FROM sesiones").fetchone()["n"])
        with self.__candado:
            self.__sesiones.clear()
        return n - quedan

    @staticmethod
    def _traspasar_datos(con, dispositivo: str, persona_id: str) -> None:
        """
        Lo que este navegador hizo antes de que existiera el ingreso (avisos,
        uniones, comentarios) pasa a la cuenta del estudiante.
        """
        if dispositivo == persona_id:
            return
        for tabla in ("participantes", "denuncias"):  # sin quedar dos veces en el mismo aviso
            con.ejecutar(
                f"DELETE FROM {tabla} WHERE persona_id = ? AND aviso_id IN "
                f"(SELECT aviso_id FROM {tabla} WHERE persona_id = ?)",
                (dispositivo, persona_id),
            )
        con.ejecutar("UPDATE avisos SET creador_id = ? WHERE creador_id = ?", (persona_id, dispositivo))
        for tabla in ("participantes", "denuncias", "comentarios", "filtrados"):
            con.ejecutar(f"UPDATE {tabla} SET persona_id = ? WHERE persona_id = ?", (persona_id, dispositivo))

    def _sesion(self, dispositivo: str | None) -> tuple[str, str] | None:
        if not dispositivo:
            return None
        momento = time.time()
        with self.__candado:
            guardada = self.__sesiones.get(dispositivo)
        if guardada and momento < guardada[2]:
            return guardada[0], guardada[1]

        ms = int(momento * 1000)
        limite = self._limite_sesiones_ms()
        with datos._conexion() as con:
            fila = con.ejecutar(
                "SELECT s.persona_id, s.creada_en, s.usada_en, e.nombre FROM sesiones s "
                "JOIN estudiantes e ON e.persona_id = s.persona_id WHERE s.dispositivo = ?",
                (dispositivo,),
            ).fetchone()
            if fila is None:
                return None
            if int(fila["creada_en"]) < limite:  # pasó un año: hay que volver a ingresar
                con.ejecutar("DELETE FROM sesiones WHERE dispositivo = ?", (dispositivo,))
                return None
            if ms - int(fila["usada_en"]) > 3_600_000:  # basta con anotarlo una vez por hora
                con.ejecutar("UPDATE sesiones SET usada_en = ? WHERE dispositivo = ?", (ms, dispositivo))
        with self.__candado:
            self.__sesiones[dispositivo] = (
                fila["persona_id"],
                fila["nombre"],
                momento + self.MINUTOS_EN_MEMORIA * 60,
            )
        return fila["persona_id"], fila["nombre"]

    def persona_de(self, dispositivo: str | None) -> str | None:
        """El estudiante con sesión abierta en este navegador, o None."""
        sesion = self._sesion(dispositivo)
        return sesion[0] if sesion else None

    def nombre_de(self, persona_id: str | None) -> str:
        with datos._conexion() as con:
            return datos.nombre_de_estudiante(con, persona_id) or ""

    def nombre_en(self, dispositivo: str | None) -> str:
        """El nombre del estudiante con sesión en este navegador (sin otra consulta)."""
        sesion = self._sesion(dispositivo)
        return sesion[1] if sesion else ""

    def cerrar_sesion(self, dispositivo: str | None) -> None:
        if not dispositivo:
            return
        with datos._conexion() as con:
            con.ejecutar("DELETE FROM sesiones WHERE dispositivo = ?", (dispositivo,))
        with self.__candado:
            self.__sesiones.pop(dispositivo, None)


acceso = Acceso(
    clave_correo=os.environ.get("BREVO_API_KEY", "").strip(),
    remitente=os.environ.get("CORREO_REMITENTE", "").strip(),
)
