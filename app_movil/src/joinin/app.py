"""
AppJoinIn: el corazón de la app de Android.

Guarda la sesión del celular, habla con el servidor (ClienteAPI) y maneja la
navegación: cada pantalla es una «vista» de Flet que se apila; el botón
atrás de Android (o la flecha de arriba) vuelve a la anterior.
"""

from __future__ import annotations

import asyncio
import re
import secrets
from typing import Any, Callable

import flet as ft

from .cliente import ClienteAPI, ErrorServidor
from .estilo import BLANCO, FONDO, ROJO, TINTA, tema

SEGUNDOS_ENTRE_REFRESCOS = 20  # cada cuánto se actualiza solo lo que está en pantalla
_FORMATO_TOKEN = re.compile(r"^[0-9a-f]{32}$")


class Almacen:
    """Lo que la app guarda en el celular: solo su token (sin correo ni datos personales)."""

    CLAVE_TOKEN = "join_in_token"

    def __init__(self) -> None:
        self._preferencias = ft.SharedPreferences()  # se guarda la referencia (Flet lo pide)

    async def leer(self, clave: str) -> str | None:
        return await self._preferencias.get(clave)

    async def guardar(self, clave: str, valor: str) -> None:
        await self._preferencias.set(clave, valor)

    async def token(self) -> str:
        """El token de este celular. La primera vez se crea al azar y se guarda."""
        actual = await self.leer(self.CLAVE_TOKEN)
        if isinstance(actual, str) and _FORMATO_TOKEN.match(actual):
            return actual
        nuevo = secrets.token_hex(16)
        await self.guardar(self.CLAVE_TOKEN, nuevo)
        return nuevo


class Pantalla:
    """Una pantalla de la app. Arma su vista y, si hace falta, carga datos del servidor."""

    ruta = "/"

    def __init__(self, app: "AppJoinIn"):
        self.app = app

    @property
    def api(self) -> ClienteAPI:
        return self.app.api

    def vista(self) -> ft.View:  # cada pantalla la arma
        raise NotImplementedError

    async def cargar(self) -> None:
        """Se llama al mostrar la pantalla (para pedir datos al servidor)."""

    async def refrescar(self) -> None:
        """Se llama sola cada cierto tiempo y al volver a esta pantalla."""
        await self.cargar()

    def vista_base(self, titulo: str | None, controles: list[ft.Control], **extra) -> ft.View:
        return ft.View(
            route=self.ruta,
            controls=controles,
            appbar=ft.AppBar(
                title=ft.Text(titulo or "", weight=ft.FontWeight.W_800, color=TINTA),
                bgcolor=FONDO,
                color=TINTA,
                actions=extra.pop("acciones", None) or [],
            ) if titulo is not None else None,
            bgcolor=FONDO,
            padding=ft.Padding.all(16),
            scroll=ft.ScrollMode.AUTO,
            **extra,
        )


class AppJoinIn:
    def __init__(self, page: ft.Page, almacen: Any, url: str | None = None):
        self.page = page
        self.almacen = almacen
        self.url = url
        self.api: ClienteAPI | None = None
        self.config: dict = {}
        self.nombre = ""
        self.es_admin = False
        self.pantallas: list[Pantalla] = []
        self.ocupado = False  # para no repetir un pedido mientras otro sigue en curso
        self.ultimo_error: ErrorServidor | None = None
        page.on_view_pop = self._al_volver_atras

    # ------------------------------------------------------------------ inicio

    async def iniciar(self) -> None:
        self.page.title = "Join In"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = tema()
        self.page.bgcolor = FONDO
        token = await self.almacen.token()
        self.api = ClienteAPI(token, self.url)
        from .pantallas.inicio import PantallaConectando

        await self.ir(PantallaConectando(self), reemplazar=True)

    async def conectar(self) -> bool:
        """Pide la configuración y quién es: decide si va al ingreso o al tablero."""
        config = await self.llamar(self.api.configuracion, avisar=False)
        if config is None:
            return False
        self.config = config
        yo = await self.llamar(self.api.yo, avisar=False)
        if yo is None:
            return False
        self.es_admin = bool(yo.get("es_admin"))
        if yo.get("ingresado"):
            self.nombre = yo.get("nombre", "")
            await self.ir_al_tablero()
        else:
            await self.ir_al_ingreso()
        return True

    async def ir_al_tablero(self) -> None:
        from .pantallas.tablero import PantallaTablero

        await self.ir(PantallaTablero(self), reemplazar=True)

    async def ir_al_ingreso(self) -> None:
        from .pantallas.ingreso import PantallaIngreso

        self.nombre = ""
        await self.ir(PantallaIngreso(self), reemplazar=True)

    # ------------------------------------------------------------------ navegación

    async def ir(self, pantalla: Pantalla, reemplazar: bool = False) -> None:
        if reemplazar:
            self.page.views.clear()
            self.pantallas.clear()
        self.pantallas.append(pantalla)
        self.page.views.append(pantalla.vista())
        self.page.update()
        await pantalla.cargar()
        self.page.update()

    async def cambiar(self, pantalla: Pantalla) -> None:
        """Reemplaza la pantalla de arriba (así «atrás» vuelve a la anterior a ella)."""
        if self.pantallas:
            self.page.views.pop()
            self.pantallas.pop()
        await self.ir(pantalla)

    async def volver(self) -> None:
        if len(self.page.views) > 1:
            self.page.views.pop()
            self.pantallas.pop()
            self.page.update()
            await self.actual.refrescar()
            self.page.update()

    async def _al_volver_atras(self, e=None) -> None:
        await self.volver()

    @property
    def actual(self) -> Pantalla | None:
        return self.pantallas[-1] if self.pantallas else None

    async def refrescar_periodicamente(self) -> None:
        """Mientras la app está abierta, actualiza sola la pantalla de arriba."""
        while True:
            await asyncio.sleep(SEGUNDOS_ENTRE_REFRESCOS)
            pantalla = self.actual
            if pantalla is None or self.ocupado or not getattr(pantalla, "se_refresca_sola", False):
                continue
            try:
                await pantalla.refrescar()
                self.page.update()
            except Exception as error:  # un fallo puntual no debe cerrar la app
                print(f"[refresco] {error!r}", flush=True)

    # ------------------------------------------------------------------ mensajes

    def avisar(self, mensaje: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                ft.Text(mensaje, color=BLANCO),
                bgcolor=ROJO if error else TINTA,
            )
        )

    def preguntar(self, titulo: str, explicacion: str, si: str, al_confirmar: Callable,
                  no: str = "Cancelar", contenido: ft.Control | None = None) -> ft.AlertDialog:
        """Ventana para confirmar algo (por ejemplo, eliminar)."""

        async def confirmar(e=None):
            self.cerrar_dialogo(dialogo)
            resultado = al_confirmar()
            if asyncio.iscoroutine(resultado):
                await resultado

        def cancelar(e=None):
            self.cerrar_dialogo(dialogo)

        cuerpo: list[ft.Control] = [ft.Text(explicacion, color=TINTA)]
        if contenido is not None:
            cuerpo.append(contenido)
        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo, weight=ft.FontWeight.W_800),
            content=ft.Column(cuerpo, tight=True, spacing=12),
            actions=[
                ft.TextButton(no, on_click=cancelar),
                ft.TextButton(si, on_click=confirmar, style=ft.ButtonStyle(color=ROJO)),
            ],
        )
        self.page.show_dialog(dialogo)
        return dialogo

    def cerrar_dialogo(self, dialogo: ft.DialogControl) -> None:
        """Cierra ese diálogo en particular (no «el último», que podría ser un aviso de abajo)."""
        dialogo.open = False
        try:
            dialogo.update()  # como lo hace Flet en pop_dialog
        except RuntimeError:  # todavía sin página (por ejemplo, en las pruebas)
            self.page.update()

    # ------------------------------------------------------------------ servidor

    async def llamar(self, funcion: Callable, *args, avisar: bool = True):
        """
        Hace un pedido al servidor sin congelar la pantalla. Si falla, muestra el
        mensaje y devuelve None. Si la sesión se cerró (por ejemplo, la
        administración liberó el correo), vuelve al ingreso.
        """
        self.ocupado = True
        self.ultimo_error = None
        try:
            return await asyncio.to_thread(funcion, *args)
        except ErrorServidor as error:
            self.ultimo_error = error
            if error.estado == 401 and funcion.__name__ not in ("yo", "configuracion"):
                self.avisar(error.mensaje, error=True)
                await self.ir_al_ingreso()
            elif avisar:
                self.avisar(error.mensaje, error=True)
            return None
        finally:
            self.ocupado = False


async def iniciar_app(page: ft.Page) -> None:
    app = AppJoinIn(page, Almacen())
    await app.iniciar()
    page.run_task(app.refrescar_periodicamente)
