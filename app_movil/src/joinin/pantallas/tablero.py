"""El tablero: los avisos abiertos ahora, con filtro por categoría."""

from __future__ import annotations

from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import AMARILLO, BLANCO, COLOR_PRINCIPAL, GRIS_SUAVE, TINTA, colores_de, icono_de

TODAS = ""


def chip_filtro(etiqueta: str, elegido: bool, al_tocar, icono=None, color: str = TINTA,
                fondo: str = GRIS_SUAVE) -> ft.Container:
    """Un botón redondo que se marca cuando está elegido (para filtros y opciones)."""
    hijos: list[ft.Control] = []
    if icono is not None:
        hijos.append(ft.Icon(icono, size=18, color=BLANCO if elegido else color))
    hijos.append(ft.Text(etiqueta, size=13, weight=ft.FontWeight.W_700, color=BLANCO if elegido else color))
    return ft.Container(
        content=ft.Row(hijos, spacing=6, tight=True),
        bgcolor=color if elegido else fondo,
        border=ft.Border.all(1, color if elegido else GRIS_SUAVE),
        border_radius=ft.BorderRadius.all(22),
        padding=ft.Padding.symmetric(horizontal=14, vertical=9),
        on_click=al_tocar,
        ink=True,
    )


class PantallaTablero(Pantalla):
    ruta = "/"
    se_refresca_sola = True

    def __init__(self, app):
        super().__init__(app)
        self.avisos: list[dict] = []
        self.momento = f.ahora()
        self.filtro = TODAS
        self.cargado = False

    def vista(self) -> ft.View:
        self.saludo = c.titulo(self._texto_saludo(), 24)
        self.filtros = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        self.lista = ft.Column([c.cargando("Buscando avisos…")], spacing=12)
        self._pintar_filtros()
        menu = ft.PopupMenuButton(
            icon=ft.Icons.ACCOUNT_CIRCLE,
            tooltip="Tu cuenta",
            menu_position=ft.PopupMenuPosition.UNDER,
            items=[
                ft.PopupMenuItem(icon=ft.Icons.INBOX, content="Mi buzón", on_click=self.ir_al_buzon),
                ft.PopupMenuItem(icon=ft.Icons.ADMIN_PANEL_SETTINGS, content="Administración", on_click=self.ir_a_admin),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(icon=ft.Icons.LOGOUT, content="Cerrar sesión", on_click=self.preguntar_salir),
            ],
        )
        return self.vista_base(
            "Join In",
            [
                self.saludo,
                c.suave("Estos son los avisos abiertos ahora. Toca uno para ver los detalles y unirte."),
                self.filtros,
                self.lista,
                ft.Container(height=80),  # espacio para que el botón flotante no tape la última tarjeta
            ],
            acciones=[
                ft.IconButton(ft.Icons.REFRESH, tooltip="Actualizar", on_click=self.actualizar),
                ft.IconButton(ft.Icons.INBOX, tooltip="Mi buzón", on_click=self.ir_al_buzon),
                menu,
            ],
            floating_action_button=ft.FloatingActionButton(
                content="Crear aviso",
                icon=ft.Icons.ADD,
                bgcolor=AMARILLO,
                foreground_color=TINTA,
                on_click=self.ir_a_crear,
            ),
        )

    def _texto_saludo(self) -> str:
        nombre = (self.app.nombre or "").split()
        return f"Hola, {nombre[0]}" if nombre else "Hola"

    # ------------------------------------------------------------------ datos

    async def cargar(self) -> None:
        r = await self.app.llamar(self.api.tablero, avisar=not self.cargado)
        if r is None:
            if not self.cargado:
                self.lista.controls = [
                    c.vacio(ft.Icons.WIFI_OFF, "No pudimos cargar el tablero", "Revisa tu internet y toca Actualizar."),
                ]
            return
        self.cargado = True
        self.momento = f.leer_fecha(r["ahora"]) or f.ahora()
        self.avisos = r["avisos"]
        self.saludo.value = self._texto_saludo()
        self._pintar_filtros()
        self._pintar_lista()

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    # ------------------------------------------------------------------ dibujo

    def _pintar_filtros(self) -> None:
        categorias = self.app.config.get("categorias", [])
        cuenta: dict[str, int] = {}
        for aviso in self.avisos:
            cuenta[aviso["categoria"]] = cuenta.get(aviso["categoria"], 0) + 1
        chips = [chip_filtro(f"Todos ({len(self.avisos)})", self.filtro == TODAS, partial(self.filtrar, TODAS),
                             ft.Icons.APPS, color=COLOR_PRINCIPAL)]
        for cat in categorias:
            fuerte, claro = colores_de(cat["clave"])
            n = cuenta.get(cat["clave"], 0)
            chips.append(
                chip_filtro(
                    f"{cat['nombre']} ({n})" if n else cat["nombre"],
                    self.filtro == cat["clave"],
                    partial(self.filtrar, cat["clave"]),
                    icono_de(cat["clave"]),
                    color=fuerte,
                    fondo=claro,
                )
            )
        self.filtros.controls = chips

    def _pintar_lista(self) -> None:
        visibles = [a for a in self.avisos if self.filtro in (TODAS, a["categoria"])]
        if not visibles:
            if self.filtro == TODAS:
                vacio = c.vacio(ft.Icons.EVENT_BUSY, "No hay avisos abiertos",
                                "Sé el primero: toca «Crear aviso» y publica lo que te falta.")
            else:
                nombre = next((x["nombre"] for x in self.app.config.get("categorias", []) if x["clave"] == self.filtro),
                              "esta categoría")
                vacio = c.vacio(icono_de(self.filtro), f"No hay avisos de {nombre}",
                                "Prueba con otra categoría o publica uno tú.")
            self.lista.controls = [vacio]
            return
        self.lista.controls = [
            c.tarjeta_aviso(aviso, self.momento, partial(self.abrir, aviso["id"]), self._pie(aviso))
            for aviso in visibles
        ]

    @staticmethod
    def _pie(aviso: dict) -> list[ft.Control]:
        marcas: list[ft.Control] = []
        if aviso.get("es_mio"):
            marcas.append(c.chip("Tu aviso", ft.Icons.STAR, color=TINTA, fondo=AMARILLO))
        elif aviso.get("me_uni"):
            marcas.append(c.chip("Ya estás dentro", ft.Icons.CHECK_CIRCLE, color=BLANCO, fondo=COLOR_PRINCIPAL))
        return [ft.Row(marcas, spacing=6)] if marcas else []

    # ------------------------------------------------------------------ acciones

    def filtrar(self, categoria: str, e=None) -> None:
        self.filtro = categoria
        self._pintar_filtros()
        self._pintar_lista()
        self.app.page.update()

    async def abrir(self, aviso_id: int, e=None) -> None:
        from .aviso import PantallaAviso

        await self.app.ir(PantallaAviso(self.app, aviso_id))

    async def ir_a_crear(self, e=None) -> None:
        from .crear import PantallaCrear

        await self.app.ir(PantallaCrear(self.app))

    async def ir_al_buzon(self, e=None) -> None:
        from .buzon import PantallaBuzon

        await self.app.ir(PantallaBuzon(self.app))

    async def ir_a_admin(self, e=None) -> None:
        from .admin import abrir_administracion

        await abrir_administracion(self.app)

    def preguntar_salir(self, e=None) -> None:
        self.app.preguntar(
            "¿Cerrar sesión?",
            "Este celular dejará de entrar directo. Para volver, ingresa de nuevo con tu correo y un código.",
            "Cerrar sesión",
            self.salir,
        )

    async def salir(self) -> None:
        if await self.app.llamar(self.api.salir) is not None:
            self.app.avisar("Cerraste sesión en este celular.")
            await self.app.ir_al_ingreso()
