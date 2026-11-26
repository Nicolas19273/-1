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
import time
import traceback
from typing import Any, Callable

import flet as ft

from .actualizar import FALLO, LISTO, crear_actualizador, leer_recorrido
from .cliente import URL_DESCARGA, ClienteAPI, ErrorServidor, es_mas_nueva, ultima_version_publicada
from .estilo import BLANCO, COLOR_PRINCIPAL, FONDO, FUENTES, GRIS_SUAVE, LETRA_TITULOS, ROJO, TINTA, tema
from .version import VERSION

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

    def vista_base(self, titulo: str | ft.Control | None, controles: list[ft.Control],
                   al_refrescar: Callable | None = None, encabezado: ft.Control | None = None, **extra) -> ft.View:
        """
        La vista con su barra de arriba. Con al_refrescar, se actualiza deslizando
        hacia abajo desde el comienzo («pull to refresh»), como en las apps del celular.
        El encabezado (si hay) va de borde a borde, arriba de todo, y se desliza con lo demás.
        """
        contenido = ft.Container(
            ft.Column(controles, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            padding=ft.Padding.only(left=16, right=16, top=4 if encabezado is None else 16, bottom=24),
        )
        partes: list[ft.Control] = ([encabezado] if encabezado is not None else []) + [contenido]
        if al_refrescar is not None:
            cuerpo: list[ft.Control] = [
                ft.RefreshIndicator(
                    content=ft.Column(partes, scroll=ft.ScrollMode.AUTO, expand=True, spacing=0),
                    on_refresh=al_refrescar,
                    color=COLOR_PRINCIPAL,
                    bgcolor=BLANCO,
                    expand=True,
                )
            ]
            desplazamiento = None
        else:
            cuerpo, desplazamiento = partes, ft.ScrollMode.AUTO
        if isinstance(titulo, str):
            titulo = ft.Text(titulo, font_family=LETRA_TITULOS, size=24, weight=ft.FontWeight.W_800, color=TINTA)
        al_tocar_titulo = extra.pop("al_tocar_titulo", None)
        return ft.View(
            route=self.ruta,
            controls=cuerpo,
            appbar=ft.AppBar(
                title=ft.Container(titulo, on_click=al_tocar_titulo) if al_tocar_titulo else titulo,
                bgcolor=FONDO,
                color=TINTA,
                elevation=0,
                actions=extra.pop("acciones", None) or [],
            ) if titulo is not None else None,
            bgcolor=FONDO,
            padding=ft.Padding.all(0),
            spacing=0,
            scroll=desplazamiento,
            **extra,
        )


SEGUNDOS_ENTRE_REVISIONES = 0.5  # cada cuánto se mira el avance de la descarga


class ToquesSecretos:
    """
    La entrada escondida a la administración: tocar algo varias veces seguidas
    (como las «opciones de desarrollador» de Android). No se ve ni se anuncia.
    """

    VECES = 5
    SEGUNDOS = 3

    def __init__(self, al_completar: Callable, reloj: Callable[[], float] = time.monotonic):
        self.al_completar = al_completar
        self.reloj = reloj
        self.toques: list[float] = []

    async def tocar(self, e=None) -> None:
        ahora = self.reloj()
        self.toques = [t for t in self.toques if ahora - t < self.SEGUNDOS] + [ahora]
        if len(self.toques) >= self.VECES:
            self.toques = []
            resultado = self.al_completar()
            if asyncio.iscoroutine(resultado):
                await resultado


class AppJoinIn:
    def __init__(self, page: ft.Page, almacen: Any, url: str | None = None, compartidor: Any = None,
                 enlaces: Any = None, actualizador: Any = None):
        self.page = page
        self.almacen = almacen
        self.url = url
        self.compartidor = compartidor  # ft.Share(): abre el menú de compartir del celular
        self.enlaces = enlaces  # ft.UrlLauncher(): abre un enlace en el navegador
        self.actualizador = actualizador  # ActualizadorAndroid, o None fuera de Android
        self.token_fijo: str | None = None  # solo en el recorrido de capturas del emulador
        self.version_nueva: str | None = None  # si en GitHub hay un APK más nuevo que este
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
        self.page.fonts = dict(FUENTES)
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = tema()
        self.page.bgcolor = FONDO
        token = self.token_fijo or await self.almacen.token()
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
        self.page.run_task(self.revisar_version)
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

    # ------------------------------------------------------------------ versión y compartir

    async def revisar_version(self, buscar: Callable[[], str | None] = ultima_version_publicada,
                              manual: bool = False) -> None:
        """
        Si en GitHub hay un APK más nuevo, el tablero muestra «Actualización disponible»
        (la app no está en Play Store). Con manual=True (menú de la cuenta) avisa el resultado.
        """
        if VERSION == "dev":
            if manual:
                self.avisar("Esta es una versión de prueba: no se actualiza.")
            return
        try:
            publicada = await asyncio.to_thread(buscar)
        except Exception:
            if manual:
                self.avisar("No pudimos revisar si hay una versión nueva. Revisa tu internet.", error=True)
            return
        if publicada and es_mas_nueva(publicada, VERSION):
            self.version_nueva = publicada
            mostrar = getattr(self.actual, "mostrar_version_nueva", None)
            if mostrar is not None:
                mostrar()
                self.page.update()
            if manual:
                await self.actualizar_app()
        elif manual:
            self.avisar(f"Ya tienes la última versión ({VERSION}).")

    async def probar_actualizador(self) -> None:
        """La prueba en el emulador: si adb dejó el archivo de prueba, recorre «Actualizar»."""
        if self.actualizador is None:
            return
        try:
            hay = await asyncio.to_thread(self.actualizador.hay_prueba)
        except Exception as error:
            print(f"[actualizar] {error!r}", flush=True)
            return
        if hay:
            print("[actualizar] prueba del actualizador", flush=True)
            self.version_nueva = self.version_nueva or "de prueba"
            await self.actualizar_app()

    async def abrir_enlace(self, url: str) -> None:
        if self.enlaces is None:
            return
        try:
            await self.enlaces.launch_url(url)
        except Exception as error:
            print(f"[enlace] {error!r}", flush=True)
            self.avisar("No se pudo abrir el enlace.", error=True)

    async def actualizar_app(self, e=None) -> None:
        """
        Baja la versión nueva y abre el instalador de Android, que la instala encima de esta.
        Sin actualizador (fuera de Android) o si algo falla, abre el enlace de descarga.
        """
        nueva = self.version_nueva
        if not nueva:
            return
        act = self.actualizador
        if act is None:
            await self.abrir_enlace(URL_DESCARGA)
            return
        try:
            puede = await asyncio.to_thread(act.puede_instalar)
        except Exception as error:
            print(f"[actualizar] {error!r}", flush=True)
            await self.abrir_enlace(URL_DESCARGA)
            return
        if not puede:
            self.preguntar(
                "Un permiso, solo la primera vez",
                "Para actualizarse sola, Join In necesita permiso para instalar apps. Toca «Dar permiso», "
                "activa «Permitir de esta fuente», vuelve atrás y toca «Actualizar» otra vez.",
                "Dar permiso",
                lambda: asyncio.to_thread(act.pedir_permiso),
                no="Ahora no",
            )
            return

        porcentaje = ft.Text("Empezando…", size=13, color=TINTA)
        barra = ft.ProgressBar(value=None, color=COLOR_PRINCIPAL, bgcolor=GRIS_SUAVE)
        estado = {"cancelado": False, "descarga": None}

        def cancelar(e=None):
            estado["cancelado"] = True
            self.cerrar_dialogo(dialogo)

        dialogo = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Actualizando a la versión {nueva}", weight=ft.FontWeight.W_800),
            content=ft.Column(
                [ft.Text("Bajando la versión nueva. Cuando termine, Android te preguntará si quieres "
                         "actualizar: toca «Actualizar». No pierdes tu sesión ni tus avisos.", color=TINTA),
                 barra, porcentaje],
                tight=True,
                spacing=12,
            ),
            actions=[ft.TextButton("Cancelar", on_click=cancelar)],
        )
        self.page.show_dialog(dialogo)
        try:
            descarga = await asyncio.to_thread(act.descargar, URL_DESCARGA, nueva)
            estado["descarga"] = descarga
            limite = time.monotonic() + 15 * 60  # con internet muy lento, hasta 15 minutos
            while True:
                if time.monotonic() > limite:
                    raise RuntimeError("la descarga tardó demasiado")
                if estado["cancelado"]:
                    await asyncio.to_thread(act.cancelar, descarga)
                    return
                situacion, bajados, total = await asyncio.to_thread(act.estado, descarga)
                if situacion == LISTO:
                    break
                if situacion == FALLO:
                    raise RuntimeError("la descarga falló")
                if total > 0:
                    barra.value = bajados / total
                    porcentaje.value = f"{bajados * 100 // total} % · {bajados / 1e6:.0f} de {total / 1e6:.0f} MB"
                self.page.update()
                await asyncio.sleep(SEGUNDOS_ENTRE_REVISIONES)
            self.cerrar_dialogo(dialogo)
            await asyncio.to_thread(act.instalar, descarga)
        except Exception as error:
            print(f"[actualizar] {error!r}\n{traceback.format_exc()}", flush=True)
            if not estado["cancelado"]:
                self.cerrar_dialogo(dialogo)
                self.avisar("No se pudo bajar la actualización. Revisa tu internet e inténtalo de nuevo.", error=True)

    async def compartir(self, texto: str, asunto: str | None = None) -> None:
        """Abre el menú de compartir del celular (WhatsApp, Instagram, correo…)."""
        if self.compartidor is None:
            return
        try:
            await self.compartidor.share_text(texto, subject=asunto)
        except Exception as error:
            print(f"[compartir] {error!r}", flush=True)
            self.avisar("No se pudo abrir el menú para compartir.", error=True)

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
    app = AppJoinIn(page, Almacen(), compartidor=ft.Share(), enlaces=ft.UrlLauncher(),
                    actualizador=crear_actualizador())
    recorrido = leer_recorrido(app.actualizador)  # solo en la prueba del emulador
    if recorrido:
        app.url, app.token_fijo = recorrido["servidor"], recorrido["token"]
    await app.iniciar()
    page.run_task(app.refrescar_periodicamente)
    if recorrido:
        from .recorrido import recorrer

        page.run_task(recorrer, app)
    else:
        page.run_task(app.probar_actualizador)
