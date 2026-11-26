"""El tablero: los avisos abiertos ahora, con filtro por categoría."""

from __future__ import annotations

from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla, ToquesSecretos
from ..version import VERSION
from ..estilo import AMARILLO, BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, LETRA_TITULOS, TINTA, colores_de, icono_de

TODAS = ""


def texto_version() -> str:
    return "(versión de prueba)" if VERSION == "dev" else f"versión {VERSION}"


def chip_filtro(etiqueta: str, elegido: bool, al_tocar, icono=None, color: str = TINTA,
                fondo: str = GRIS_SUAVE) -> ft.Container:
    """Un botón redondo que se marca cuando está elegido (para filtros y opciones)."""
    hijos: list[ft.Control] = []
    if icono is not None:
        hijos.append(ft.Icon(icono, size=16, color=BLANCO if elegido else color))
    hijos.append(ft.Text(etiqueta, size=13, weight=ft.FontWeight.W_700, color=BLANCO if elegido else TINTA))
    return ft.Container(
        content=ft.Row(hijos, spacing=6, tight=True),
        bgcolor=color if elegido else BLANCO,
        border=ft.Border.all(1, color if elegido else GRIS_SUAVE),
        border_radius=ft.BorderRadius.all(20),
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        on_click=al_tocar,
        ink=True,
    )


def marca(al_tocar=None) -> ft.Control:
    """La ficha chica con «+1» y el nombre: el título de arriba del tablero."""
    return ft.Container(
        ft.Row(
            [c.ficha("+1", 30), ft.Text("Join In", font_family=LETRA_TITULOS, size=26, weight=ft.FontWeight.W_900,
                                        color=TINTA)],
            spacing=10,
            tight=True,
        ),
        on_click=al_tocar,
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
        self.saludo = c.titulo(self._texto_saludo(), 34)
        self.resumen = c.suave("Buscando avisos…", 14)
        # Sin barra de desplazamiento: en el celular se pintaba encima de los nombres.
        self.filtros = ft.Row(scroll=ft.ScrollMode.HIDDEN, spacing=8)
        self.banner = ft.Container(visible=False)
        self.lista = ft.Column([c.cargando("Buscando avisos…")], spacing=12)
        self._pintar_filtros()
        self.mostrar_version_nueva()
        # Solo quien ya administra ve «Administración» en el menú; para entrar la primera
        # vez se toca 5 veces seguidas el título «Join In» de arriba.
        self.item_admin = ft.PopupMenuItem(icon=ft.Icons.ADMIN_PANEL_SETTINGS, content="Administración",
                                           on_click=self.ir_a_admin, visible=self.app.es_admin)
        menu = ft.PopupMenuButton(
            icon=ft.Icons.ACCOUNT_CIRCLE,
            tooltip="Tu cuenta",
            menu_position=ft.PopupMenuPosition.UNDER,
            items=[
                ft.PopupMenuItem(icon=ft.Icons.INBOX, content="Mi buzón", on_click=self.ir_al_buzon),
                self.item_admin,
                ft.PopupMenuItem(),
                ft.PopupMenuItem(icon=ft.Icons.LOGOUT, content="Cerrar sesión", on_click=self.preguntar_salir),
                ft.PopupMenuItem(icon=ft.Icons.SYSTEM_UPDATE, content="Buscar actualizaciones",
                                 on_click=self.buscar_actualizaciones),
                ft.PopupMenuItem(icon=ft.Icons.INFO_OUTLINE, content=f"Join In {texto_version()}"),
            ],
        )
        return self.vista_base(
            marca(),
            [
                ft.Column([self.saludo, self.resumen], spacing=0),
                self.banner,
                self.filtros,
                self.lista,
                ft.Container(height=72),  # espacio para que el botón flotante no tape la última tarjeta
            ],
            al_refrescar=self.actualizar,
            al_tocar_titulo=ToquesSecretos(self.ir_a_admin).tocar,
            acciones=[
                ft.IconButton(ft.Icons.INBOX_OUTLINED, tooltip="Mi buzón", on_click=self.ir_al_buzon),
                menu,
                ft.Container(width=4),
            ],
            floating_action_button=ft.FloatingActionButton(
                content=ft.Text("Crear aviso", size=16, weight=ft.FontWeight.W_800, color=TINTA),
                icon=ft.Icons.ADD,
                bgcolor=AMARILLO,
                foreground_color=TINTA,
                shape=ft.RoundedRectangleBorder(radius=18, side=ft.BorderSide(2, TINTA)),
                elevation=2,
                on_click=self.ir_a_crear,
            ),
        )

    def mostrar_version_nueva(self) -> None:
        """Una tarjeta arriba si hay un APK más nuevo para descargar."""
        nueva = self.app.version_nueva
        self.banner.visible = bool(nueva)
        if not nueva:
            return
        self.banner.content = c.tarjeta(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SYSTEM_UPDATE, color=TINTA, size=26),
                        ft.Column(
                            [c.titulo("Actualización disponible", 21),
                             c.texto(f"Join In {nueva} ya está lista. Se instala encima de esta: "
                                     "no pierdes tu sesión ni tus avisos.", 13)],
                            spacing=2, expand=True, tight=True,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Row([c.boton_oscuro("Actualizar", self.app.actualizar_app, ft.Icons.SYSTEM_UPDATE_ALT,
                                       expandir=False)]),
            ],
            color=AMARILLO,
            borde=TINTA,
            espacio=12,
        )

    async def buscar_actualizaciones(self, e=None) -> None:
        await self.app.revisar_version(manual=True)

    def _texto_resumen(self) -> str:
        n = len(self.avisos)
        if n == 0:
            return "Ahora no hay avisos abiertos."
        return "Hay 1 aviso abierto ahora." if n == 1 else f"Hay {n} avisos abiertos ahora."

    def _texto_saludo(self) -> str:
        nombre = (self.app.nombre or "").split()
        return f"Hola, {nombre[0]}" if nombre else "Hola"

    # ------------------------------------------------------------------ datos

    async def cargar(self) -> None:
        r = await self.app.llamar(self.api.tablero, avisar=not self.cargado)
        if r is None:
            if not self.cargado:
                self.resumen.value = "Sin conexión con Join In"
                self.lista.controls = [
                    c.vacio(ft.Icons.WIFI_OFF, "No pudimos cargar el tablero", "Revisa tu internet y desliza hacia abajo para reintentar."),
                ]
            return
        self.cargado = True
        self.momento = f.leer_fecha(r["ahora"]) or f.ahora()
        self.avisos = r["avisos"]
        self.saludo.value = self._texto_saludo()
        self.resumen.value = self._texto_resumen()
        self.item_admin.visible = self.app.es_admin
        self.mostrar_version_nueva()
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
                                "Sé el primero: publica lo que te falta y deja que el resto se una.",
                                c.boton_principal("Publicar un aviso", self.ir_a_crear, ft.Icons.ADD, expandir=False))
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
