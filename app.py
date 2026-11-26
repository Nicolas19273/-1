"""
Join In: servidor de la app.

La app de Android (carpeta app_movil/) habla con este servidor por
internet. Aquí no hay páginas web: solo una API que responde en JSON y usa
las mismas clases de siempre (Acceso, GestorAvisos, Administracion,
BuscadorLugares y FiltroPalabras). Las claves (base de datos, Brevo y
administración) se quedan en el servidor y nunca viajan a los celulares.

Cada celular se identifica con un token propio (32 letras y números al azar)
que la app crea la primera vez y manda en cada pedido:

    Authorization: Bearer <token>

Es el mismo «dispositivo» que antes guardaba la cookie del navegador: un
correo queda unido a un solo celular.

Para probarlo en tu computador:  python app.py   (queda en http://localhost:8080)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Callable

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import acceso
import datos
import filtro
import lugares
from datos import ErrorValidacion

EN_INTERNET = "RENDER" in os.environ or "PORT" in os.environ
URL_PUBLICA = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
VERSION_API = 1
# Siempre el APK más nuevo (lo publica .github/workflows/app.yml al subir a main).
URL_DESCARGA_APP = "https://github.com/Nicolas19273/-1/releases/latest/download/join-in.apk"

_FORMATO_TOKEN = re.compile(r"^[0-9a-f]{32}$")

MENSAJE_SIN_SESION = "Ingresa con tu correo institucional."
MENSAJE_SIN_ADMIN = "Esta sección es solo para quien administra Join In."


class ErrorHTTP(Exception):
    """Un error con su código HTTP y un mensaje listo para mostrar en la app."""

    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


def ahora() -> datetime:
    return datetime.now(datos.ZONA_HORARIA)


def fecha(momento: datetime | None) -> str | None:
    """Fecha y hora en formato ISO 8601, con la zona horaria de Chile."""
    return momento.astimezone(datos.ZONA_HORARIA).isoformat() if momento else None


def leer_fecha(texto) -> datetime:
    """Fecha y hora que manda la app (ISO 8601). Sin zona, se asume la de Chile."""
    if isinstance(texto, datetime):
        momento = texto
    else:
        try:
            momento = datetime.fromisoformat(str(texto or "").strip())
        except ValueError:
            raise ErrorValidacion("Elige la fecha y la hora del evento.") from None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=datos.ZONA_HORARIA)
    return momento


class API:
    """
    «interfaz» La frontera entre la app y el servidor: recibe los pedidos de
    la app, revisa quién los hace y se los pasa a las clases de control.
    No decide reglas: solo traduce entre JSON y esas clases.
    """

    def __init__(
        self,
        acceso_: acceso.Acceso,
        gestor: datos.GestorAvisos,
        buscador: lugares.BuscadorLugares,
        filtro_: filtro.FiltroPalabras,
        administracion: datos.Administracion,
    ):
        self.acceso = acceso_
        self.gestor = gestor
        self.buscador = buscador
        self.filtro = filtro_
        self.administracion = administracion

    # ------------------------------------------------------------------ #
    # Quién pide
    # ------------------------------------------------------------------ #

    @staticmethod
    def _dispositivo(request: Request) -> str | None:
        """El token del celular, o None si no vino o no tiene el formato correcto."""
        valor = request.headers.get("authorization", "")
        if not valor.lower().startswith("bearer "):
            return None
        token = valor[7:].strip().lower()
        return token if _FORMATO_TOKEN.match(token) else None

    def _persona(self, request: Request) -> str:
        """El estudiante con sesión en este celular (401 si no hay)."""
        persona_id = self.acceso.persona_de(self._dispositivo(request))
        if persona_id is None:
            raise ErrorHTTP(401, MENSAJE_SIN_SESION)
        return persona_id

    def _quien_administra(self, request: Request) -> str | None:
        """
        Con qué nombre se guarda la sesión de administración: la cuenta del
        estudiante si ingresó con su correo; si no, el propio celular. Así se
        puede entrar al panel aunque el correo esté en uso en otro celular.
        """
        dispositivo = self._dispositivo(request)
        persona_id = self.acceso.persona_de(dispositivo)
        celular = f"celular:{dispositivo}" if dispositivo else None
        if persona_id and celular and self.administracion.es_admin(celular):
            # Entró al panel sin cuenta y después ingresó: la sesión pasa a su cuenta.
            self.administracion.agregar_admin(persona_id)
            self.administracion.quitar_admin(celular)
        return persona_id or celular

    def _admin(self, request: Request) -> str:
        admin_id = self._quien_administra(request)
        if not self.administracion.es_admin(admin_id):
            raise ErrorHTTP(403, MENSAJE_SIN_ADMIN)
        return admin_id

    @staticmethod
    def _ip(request: Request) -> str:
        cliente = request.client
        return getattr(cliente, "host", None) or "desconocida"

    @staticmethod
    def _numero(request: Request, nombre: str) -> int:
        try:
            return int(request.path_params[nombre])
        except (KeyError, ValueError):
            raise ErrorHTTP(404, "No encontramos eso.") from None

    def _aviso(self, aviso_id: int) -> datos.Aviso:
        aviso = self.gestor.obtener_aviso(aviso_id)
        if aviso is None:
            raise ErrorHTTP(404, "Este aviso ya no existe.")
        return aviso

    # ------------------------------------------------------------------ #
    # Cómo se ve cada cosa en JSON
    # ------------------------------------------------------------------ #

    def aviso_json(self, aviso: datos.Aviso, persona_id: str | None, momento: datetime) -> dict:
        """Un aviso para la app. No incluye identificadores de otras personas."""
        motivo = aviso.motivo_cierre(momento)
        return {
            "id": aviso.id,
            "titulo": aviso.titulo,
            "categoria": aviso.categoria,
            "nombre_categoria": aviso.nombre_categoria,
            "descripcion": aviso.descripcion,
            "lugar": aviso.lugar,
            "lat": aviso.lat,
            "lng": aviso.lng,
            "inicio_evento": fecha(aviso.inicio_evento),
            "creado_en": fecha(aviso.creado_en),
            "expira_en": fecha(aviso.expira_en),
            "cierra_en": fecha(aviso.cierra_en),
            "visible_en_buzon_hasta": fecha(aviso.visible_en_buzon_hasta),
            "duracion_horas": aviso.duracion_horas,
            "personas_actuales": aviso.personas_actuales,
            "personas_necesarias": aviso.personas_necesarias,
            "ocupados": aviso.ocupados,
            "cupos_libres": aviso.cupos_libres,
            "valor": aviso.valor,
            "creador": aviso.creador,
            "inscritos": [p.nombre for p in aviso.inscritos],
            "comentarios": aviso.comentarios,
            "cancelado": aviso.cancelado,
            "cancelado_por": aviso.cancelado_por,
            "estado": motivo,  # None si está abierto
            "abierto": motivo is None,
            "es_mio": bool(persona_id) and aviso.es_de(persona_id),
            "me_uni": bool(persona_id) and aviso.tiene_inscrito(persona_id),
        }

    @staticmethod
    def comentario_json(comentario: datos.Comentario, aviso: datos.Aviso, persona_id: str | None) -> dict:
        del_dueno = aviso.es_de(comentario.persona_id)
        return {
            "id": comentario.id,
            "nombre": "Quien organiza" if del_dueno else (comentario.nombre or "Anónimo"),
            "texto": comentario.texto,
            "momento": fecha(comentario.momento),
            "de_quien_organiza": del_dueno,
            "es_mio": bool(persona_id) and comentario.persona_id == persona_id,
        }

    @staticmethod
    def lugar_json(lugar: lugares.Lugar) -> dict:
        return {
            "nombre": lugar.nombre,
            "detalle": lugar.detalle,
            "lat": lugar.lat,
            "lng": lugar.lng,
            "tipo": lugar.tipo,
            "texto": lugar.texto,
        }

    @staticmethod
    def regla_json(regla: filtro.Regla) -> dict:
        return {
            "id": regla.id,
            "palabra": regla.palabra,
            "cerca_de": list(regla.cerca_de),
            "excepto": list(regla.excepto),
            "siempre": regla.siempre,
        }

    # ------------------------------------------------------------------ #
    # General
    # ------------------------------------------------------------------ #

    def salud(self, request: Request, cuerpo: dict) -> dict:
        """Respuesta liviana para saber si el servidor está despierto (no usa la BD)."""
        return {"ok": True, "version": VERSION_API}

    def inicio(self, request: Request, cuerpo: dict) -> dict:
        """Quien abra el enlace antiguo en el navegador ve a dónde se fue Join In."""
        return {
            "join_in": "Join In ahora es una app para Android.",
            "descarga": URL_DESCARGA_APP,
            "version_api": VERSION_API,
        }

    def configuracion(self, request: Request, cuerpo: dict) -> dict:
        """Las reglas fijas que la app necesita para armar los formularios."""
        g = self.gestor
        return {
            "version": VERSION_API,
            "dominio": self.acceso.DOMINIO_PERMITIDO,
            "largo_codigo": self.acceso.LARGO_CODIGO,
            "modo_prueba": self.acceso.modo_prueba,
            "categorias": [{"clave": k, "nombre": v} for k, v in g.CATEGORIAS.items()],
            "duraciones": list(g.DURACIONES_PERMITIDAS),
            "max_personas": g.MAX_PERSONAS,
            "largo_titulo": list(g.LARGO_TITULO),
            "largo_lugar": list(datos.LARGO_LUGAR),
            "largo_nombre": list(datos.LARGO_NOMBRE),
            "largo_max_descripcion": g.LARGO_MAX_DESCRIPCION,
            "largo_max_comentario": datos.LARGO_MAX_COMENTARIO,
            "largo_max_denuncia": datos.LARGO_MAX_DENUNCIA,
            "valor_maximo": g.VALOR_MAXIMO,
            "motivos_denuncia": [{"clave": k, "nombre": v} for k, v in datos.MOTIVOS_DENUNCIA.items()],
            "zona": {
                "nombre": self.buscador.NOMBRE_ZONA,
                "centro": list(self.buscador.CENTRO),
            },
        }

    # ------------------------------------------------------------------ #
    # Ingreso con correo institucional
    # ------------------------------------------------------------------ #

    def pedir_codigo(self, request: Request, cuerpo: dict) -> dict:
        dispositivo = self._dispositivo(request)
        if dispositivo is None:
            raise ErrorValidacion("No pudimos reconocer tu celular. Cierra la app y ábrela de nuevo.")
        correo = cuerpo.get("correo")
        codigo = self.acceso.enviar_codigo(correo, dispositivo)
        respuesta = {"correo": self.acceso.normalizar_correo(correo)}
        if codigo is not None:  # solo en modo de prueba (sin Brevo configurado)
            respuesta["codigo_prueba"] = codigo
        return respuesta

    def verificar_codigo(self, request: Request, cuerpo: dict) -> dict:
        """
        Revisa el código. Si el estudiante ya existe, abre la sesión de una vez;
        si es nuevo, la app le pide su nombre y llama a «registrar».
        """
        dispositivo = self._dispositivo(request)
        correo = cuerpo.get("correo")
        if not self.acceso.verificar_codigo(correo, cuerpo.get("codigo")):
            raise ErrorValidacion("Ese código no es correcto. Revisa el último correo que te llegó.")
        if not self.acceso.estudiante_existe(correo):
            return {"listo": False, "necesita_nombre": True}
        self.acceso.registrar(correo, "", dispositivo)
        return {"listo": True, "nombre": self.acceso.nombre_en(dispositivo)}

    def registrar(self, request: Request, cuerpo: dict) -> dict:
        dispositivo = self._dispositivo(request)
        self.acceso.registrar(cuerpo.get("correo"), cuerpo.get("nombre"), dispositivo)
        return {"listo": True, "nombre": self.acceso.nombre_en(dispositivo)}

    def yo(self, request: Request, cuerpo: dict) -> dict:
        dispositivo = self._dispositivo(request)
        persona_id = self.acceso.persona_de(dispositivo)
        admin_id = self._quien_administra(request)
        return {
            "ingresado": persona_id is not None,
            "nombre": self.acceso.nombre_en(dispositivo) if persona_id else "",
            "es_admin": self.administracion.es_admin(admin_id),
        }

    def salir(self, request: Request, cuerpo: dict) -> dict:
        self.acceso.cerrar_sesion(self._dispositivo(request))
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # Avisos
    # ------------------------------------------------------------------ #

    def tablero(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        momento = ahora()
        avisos = self.gestor.avisos_activos(momento)
        return {"ahora": fecha(momento), "avisos": [self.aviso_json(a, persona_id, momento) for a in avisos]}

    def ver_aviso(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        momento = ahora()
        aviso = self._aviso(self._numero(request, "aviso_id"))
        comentarios = self.gestor.comentarios_de(aviso.id)
        return {
            "ahora": fecha(momento),
            "aviso": self.aviso_json(aviso, persona_id, momento),
            "comentarios": [self.comentario_json(c, aviso, persona_id) for c in comentarios],
        }

    def crear_aviso(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        campos = {
            k: cuerpo.get(k)
            for k in (
                "titulo", "categoria", "lugar", "personas_actuales", "personas_necesarias",
                "duracion_horas", "descripcion", "lat", "lng", "valor",
            )
            if k in cuerpo
        }
        campos["inicio_evento"] = leer_fecha(cuerpo.get("inicio_evento"))
        aviso = self.gestor.crear_aviso(campos, persona_id)
        return {"aviso": self.aviso_json(aviso, persona_id, ahora())}

    def unirse(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        aviso = self.gestor.unirse(self._numero(request, "aviso_id"), persona_id)
        return {"aviso": self.aviso_json(aviso, persona_id, ahora())}

    def salirse(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        aviso = self.gestor.salirse(self._numero(request, "aviso_id"), persona_id)
        return {"aviso": self.aviso_json(aviso, persona_id, ahora())}

    def eliminar(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        aviso = self.gestor.eliminar_aviso(self._numero(request, "aviso_id"), persona_id)
        return {"aviso": self.aviso_json(aviso, persona_id, ahora())}

    def comentar(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        aviso = self._aviso(self._numero(request, "aviso_id"))
        comentario = self.gestor.comentar(aviso.id, persona_id, cuerpo.get("texto") or "")
        return {"comentario": self.comentario_json(comentario, aviso, persona_id)}

    def borrar_comentario(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        como_admin = self.administracion.es_admin(self._quien_administra(request))
        self.gestor.borrar_comentario(self._numero(request, "comentario_id"), persona_id, como_admin=como_admin)
        return {"ok": True}

    def denunciar(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        self.gestor.denunciar(
            self._numero(request, "aviso_id"), persona_id, cuerpo.get("motivo"), cuerpo.get("comentario") or ""
        )
        return {"ok": True}

    def buzon(self, request: Request, cuerpo: dict) -> dict:
        persona_id = self._persona(request)
        momento = ahora()
        me_uni, organizo = self.gestor.mi_buzon(persona_id, momento)
        return {
            "ahora": fecha(momento),
            "me_uni": [self.aviso_json(a, persona_id, momento) for a in me_uni],
            "organizo": [self.aviso_json(a, persona_id, momento) for a in organizo],
        }

    def revisar_texto(self, request: Request, cuerpo: dict) -> dict:
        """Mientras se escribe: qué palabras inapropiadas tiene el texto (para marcarlas)."""
        self._persona(request)
        texto = str(cuerpo.get("texto") or "")[:2000]
        return {"palabras": self.filtro.encontradas(texto)}

    # ------------------------------------------------------------------ #
    # Lugares (OpenStreetMap)
    # ------------------------------------------------------------------ #

    def buscar_lugares(self, request: Request, cuerpo: dict) -> dict:
        self._persona(request)
        resultados = self.buscador.buscar(request.query_params.get("q", ""))
        return {"lugares": [self.lugar_json(l) for l in resultados]}

    def direccion(self, request: Request, cuerpo: dict) -> dict:
        self._persona(request)
        try:
            lat = float(request.query_params.get("lat", ""))
            lng = float(request.query_params.get("lng", ""))
        except ValueError:
            raise ErrorValidacion("Ubicación no válida.") from None
        return {
            "direccion": self.buscador.direccion_de(lat, lng),
            "dentro_de_zona": self.buscador.dentro_de_zona(lat, lng),
        }

    # ------------------------------------------------------------------ #
    # Administración
    # ------------------------------------------------------------------ #

    def admin_estado(self, request: Request, cuerpo: dict) -> dict:
        return {
            "hay_clave": self.administracion.hay_clave,
            "es_admin": self.administracion.es_admin(self._quien_administra(request)),
        }

    def admin_entrar(self, request: Request, cuerpo: dict) -> dict:
        admin_id = self._quien_administra(request)
        if admin_id is None:
            raise ErrorValidacion("No pudimos reconocer tu celular. Cierra la app y ábrela de nuevo.")
        self.administracion.entrar(admin_id, cuerpo.get("clave"), self._ip(request))
        return {"es_admin": True}

    def admin_salir(self, request: Request, cuerpo: dict) -> dict:
        self.administracion.quitar_admin(self._admin(request))
        return {"ok": True}

    def admin_salir_todos(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        return {"cerradas": self.administracion.quitar_todos_los_admin()}

    def admin_resumen(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        return {"cifras": self.administracion.estadisticas(ahora())}

    def admin_denuncias(self, request: Request, cuerpo: dict) -> dict:
        admin_id = self._admin(request)
        momento = ahora()
        return {
            "denuncias": [
                {
                    "aviso": self.aviso_json(aviso, admin_id, momento),
                    "denuncias": [
                        {
                            "id": d.id,
                            "motivo": d.motivo,
                            "nombre_motivo": d.nombre_motivo,
                            "comentario": d.comentario,
                            "momento": fecha(d.momento),
                        }
                        for d in lista
                    ],
                }
                for aviso, lista in self.administracion.denuncias_pendientes()
            ]
        }

    def admin_descartar_denuncias(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        self.administracion.descartar_denuncias(self._numero(request, "aviso_id"))
        return {"ok": True}

    def admin_reglas(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        return {
            "reglas": [self.regla_json(r) for r in self.administracion.reglas()],
            "palabras_base": len(self.filtro.palabras_base()),
            "largo_max_regla": self.administracion.LARGO_MAX_REGLA,
        }

    def admin_agregar_regla(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        regla = self.administracion.agregar_regla(
            cuerpo.get("palabra") or "", cuerpo.get("cerca_de") or "", cuerpo.get("excepto") or ""
        )
        return {"regla": self.regla_json(regla)}

    def admin_borrar_regla(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        self.administracion.borrar_regla(self._numero(request, "regla_id"))
        return {"ok": True}

    def admin_probar_filtro(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        texto = str(cuerpo.get("texto") or "")[:2000]
        return {"palabras": self.filtro.encontradas(texto)}

    def admin_bloqueados(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        return {
            "dias": self.administracion.DIAS_REGISTRO_FILTRADOS,
            "bloqueados": [
                {"id": f.id, "momento": fecha(f.momento), "campo": f.campo, "texto": f.texto, "palabras": list(f.palabras)}
                for f in self.administracion.filtrados_recientes()
            ],
        }

    def admin_borrar_bloqueados(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        self.administracion.borrar_filtrados()
        return {"ok": True}

    def admin_avisos(self, request: Request, cuerpo: dict) -> dict:
        admin_id = self._admin(request)
        momento = ahora()
        avisos = self.administracion.todos_los_avisos(None)
        return {"ahora": fecha(momento), "avisos": [self.aviso_json(a, admin_id, momento) for a in avisos]}

    def admin_eliminar_aviso(self, request: Request, cuerpo: dict) -> dict:
        """Sacar del tablero (quienes se unieron lo ven como cancelado)."""
        admin_id = self._admin(request)
        aviso = self.gestor.eliminar_aviso(self._numero(request, "aviso_id"), admin_id, como_admin=True)
        return {"aviso": self.aviso_json(aviso, admin_id, ahora())}

    def admin_borrar_aviso(self, request: Request, cuerpo: dict) -> dict:
        """Borrar para siempre, con sus inscritos, comentarios y denuncias."""
        admin_id = self._admin(request)
        aviso = self.gestor.borrar_aviso(self._numero(request, "aviso_id"), admin_id)
        return {"titulo": aviso.titulo}

    def admin_borrar_todos(self, request: Request, cuerpo: dict) -> dict:
        admin_id = self._admin(request)
        if str(cuerpo.get("confirmacion") or "").strip().upper() != "BORRAR":
            raise ErrorValidacion("Escribe BORRAR para confirmar.")
        return {"borrados": self.gestor.borrar_todos_los_avisos(admin_id)}

    def admin_correos(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        return {
            "correos": [
                {"correo": c["correo"], "nombre": c["nombre"], "usado": fecha(c["usado"])}
                for c in self.acceso.correos_en_uso()
            ]
        }

    def admin_liberar_correo(self, request: Request, cuerpo: dict) -> dict:
        self._admin(request)
        correo = cuerpo.get("correo")
        cerradas = self.acceso.liberar_correo(correo)
        return {"correo": self.acceso.normalizar_correo(correo), "sesiones_cerradas": cerradas}

    # ------------------------------------------------------------------ #
    # Rutas
    # ------------------------------------------------------------------ #

    def rutas(self) -> list[Route]:
        r = _ruta
        return [
            r("GET", "/", self.inicio),
            r("GET", "/salud", self.salud),
            r("GET", "/api/salud", self.salud),
            r("GET", "/api/configuracion", self.configuracion),
            r("POST", "/api/ingreso/codigo", self.pedir_codigo),
            r("POST", "/api/ingreso/verificar", self.verificar_codigo),
            r("POST", "/api/ingreso/registrar", self.registrar),
            r("GET", "/api/yo", self.yo),
            r("POST", "/api/salir", self.salir),
            r("GET", "/api/avisos", self.tablero),
            r("POST", "/api/avisos", self.crear_aviso),
            r("GET", "/api/avisos/{aviso_id}", self.ver_aviso),
            r("POST", "/api/avisos/{aviso_id}/unirse", self.unirse),
            r("POST", "/api/avisos/{aviso_id}/salirse", self.salirse),
            r("POST", "/api/avisos/{aviso_id}/eliminar", self.eliminar),
            r("POST", "/api/avisos/{aviso_id}/comentarios", self.comentar),
            r("POST", "/api/avisos/{aviso_id}/denunciar", self.denunciar),
            r("DELETE", "/api/comentarios/{comentario_id}", self.borrar_comentario),
            r("GET", "/api/buzon", self.buzon),
            r("POST", "/api/filtro/revisar", self.revisar_texto),
            r("GET", "/api/lugares", self.buscar_lugares),
            r("GET", "/api/direccion", self.direccion),
            r("GET", "/api/admin/estado", self.admin_estado),
            r("POST", "/api/admin/entrar", self.admin_entrar),
            r("POST", "/api/admin/salir", self.admin_salir),
            r("POST", "/api/admin/salir-todos", self.admin_salir_todos),
            r("GET", "/api/admin/resumen", self.admin_resumen),
            r("GET", "/api/admin/denuncias", self.admin_denuncias),
            r("POST", "/api/admin/denuncias/{aviso_id}/descartar", self.admin_descartar_denuncias),
            r("GET", "/api/admin/reglas", self.admin_reglas),
            r("POST", "/api/admin/reglas", self.admin_agregar_regla),
            r("DELETE", "/api/admin/reglas/{regla_id}", self.admin_borrar_regla),
            r("POST", "/api/admin/filtro/probar", self.admin_probar_filtro),
            r("GET", "/api/admin/bloqueados", self.admin_bloqueados),
            r("DELETE", "/api/admin/bloqueados", self.admin_borrar_bloqueados),
            r("GET", "/api/admin/avisos", self.admin_avisos),
            r("POST", "/api/admin/avisos/{aviso_id}/eliminar", self.admin_eliminar_aviso),
            r("DELETE", "/api/admin/avisos/{aviso_id}", self.admin_borrar_aviso),
            r("POST", "/api/admin/avisos/borrar-todos", self.admin_borrar_todos),
            r("GET", "/api/admin/correos", self.admin_correos),
            r("POST", "/api/admin/correos/liberar", self.admin_liberar_correo),
        ]


def _ruta(metodo: str, camino: str, funcion: Callable[[Request, dict], dict]) -> Route:
    """
    Envuelve un método de la API: lee el JSON del pedido, corre el método en
    otro hilo (la base de datos no debe frenar al servidor) y convierte los
    errores en respuestas con un mensaje para la app.
    """

    async def manejar(request: Request) -> JSONResponse:
        cuerpo: dict = {}
        if metodo in ("POST", "DELETE"):
            crudo = await request.body()
            if crudo:
                try:
                    cuerpo = json.loads(crudo)
                except ValueError:
                    return JSONResponse({"error": "Pedido no válido."}, status_code=400)
                if not isinstance(cuerpo, dict):
                    return JSONResponse({"error": "Pedido no válido."}, status_code=400)
        try:
            resultado = await run_in_threadpool(funcion, request, cuerpo)
        except ErrorHTTP as error:
            return JSONResponse({"error": error.mensaje}, status_code=error.estado)
        except ErrorValidacion as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        except lugares.ErrorBusqueda as error:
            return JSONResponse({"error": str(error)}, status_code=503)
        return JSONResponse(resultado)

    return Route(camino, manejar, methods=[metodo])


async def no_encontrado(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse({"error": "No encontramos eso."}, status_code=404)


async def error_interno(request: Request, error: Exception) -> JSONResponse:
    print(f"[error] {request.method} {request.url.path}: {error!r}", flush=True)
    return JSONResponse({"error": "Algo falló en el servidor. Intenta de nuevo en un rato."}, status_code=500)


# --------------------------------------------------------------------------- #
# Despertador (APAGADO por defecto)
#
# Render gratis duerme el servidor si pasan 15 minutos sin pedidos y lo
# despierta solo cuando llega uno (tarda cerca de 1 minuto). Si algún día
# quieres que no se duerma nunca, crea en Render la variable de entorno
# DESPERTADOR con el valor «si»: el servidor se visitará solo cada 10 minutos.
# --------------------------------------------------------------------------- #

DESPERTADOR_ENCENDIDO = os.environ.get("DESPERTADOR", "").strip().lower() in {"si", "sí", "1", "true"}
MINUTOS_ENTRE_VISITAS = 10
_tareas_de_fondo: set[asyncio.Task] = set()


def tocar_puerta() -> int:
    pedido = urllib.request.Request(f"{URL_PUBLICA}/salud", headers={"User-Agent": "join-in-despertador"})
    with urllib.request.urlopen(pedido, timeout=30) as respuesta:
        return respuesta.status


async def despertador() -> None:
    while True:
        await asyncio.sleep(MINUTOS_ENTRE_VISITAS * 60)
        try:
            estado = await asyncio.to_thread(tocar_puerta)
            print(f"[despertador] visita a /salud: {estado}", flush=True)
        except Exception as error:  # un fallo puntual no debe detener el servidor
            print(f"[despertador] no se pudo visitar /salud: {error}", flush=True)


@asynccontextmanager
async def ciclo_de_vida(app: Starlette):
    """Al arrancar el servidor: enciende el despertador si está pedido."""
    if URL_PUBLICA and DESPERTADOR_ENCENDIDO:
        tarea = asyncio.get_running_loop().create_task(despertador())
        _tareas_de_fondo.add(tarea)
        print(f"[despertador] activo: {URL_PUBLICA}/salud cada {MINUTOS_ENTRE_VISITAS} min", flush=True)
    yield


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #

datos.inicializar()
acceso.acceso.quitar_sesiones_de_mas()  # un correo, un celular

api = API(acceso.acceso, datos.gestor, lugares.buscador, filtro.filtro_palabras, datos.administracion)
servidor = Starlette(
    routes=api.rutas(),
    exception_handlers={404: no_encontrado, 500: error_interno},
    lifespan=ciclo_de_vida,
)

if __name__ == "__main__":
    uvicorn.run(
        servidor,
        host="0.0.0.0",  # acepta pedidos desde fuera del servidor
        port=int(os.environ.get("PORT", 8080)),
        proxy_headers=True,  # en Render, la IP real viene en X-Forwarded-For
        forwarded_allow_ips="*",
    )
