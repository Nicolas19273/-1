"""Pantalla de arranque: se conecta con el servidor (que puede estar despertando)."""

from __future__ import annotations

import flet as ft

from .. import componentes as c
from ..app import Pantalla
from ..estilo import BLANCO, CANCHA_OSCURA, COLOR_PRINCIPAL, FONDO, LETRA_TITULOS

LINEA_DE_CAL = ft.Colors.with_opacity(0.22, BLANCO)


def logo(tam: int = 72) -> ft.Container:
    """La ficha amarilla con «+1»: el que falta."""
    return c.ficha("+1", tam)


def barra_de_color(color: str) -> ft.AppBar:
    """
    Una barra de arriba sin alto: pinta del mismo color la franja de la hora y la batería,
    y Android pone esos íconos en blanco porque el fondo es oscuro.
    """
    return ft.AppBar(toolbar_height=0, bgcolor=color, elevation=0, elevation_on_scroll=0,
                     automatically_imply_leading=False)


def mitad_de_cancha(centro: ft.Control, alto: int = 220) -> ft.Stack:
    """La línea de mitad de cancha y el círculo central, pintados con cal, con algo al medio."""
    return ft.Stack(
        [
            ft.Container(left=0, right=0, top=alto / 2 - 1, height=2, bgcolor=LINEA_DE_CAL),
            ft.Container(width=alto - 20, height=alto - 20, border=ft.Border.all(2, LINEA_DE_CAL),
                         border_radius=ft.BorderRadius.all(alto)),
            centro,
        ],
        alignment=ft.Alignment.CENTER,
        height=alto,
    )


def cancha(contenido: list[ft.Control], alto_centro: int = 220, centro: ft.Control | None = None) -> ft.Container:
    """El bloque verde de arriba del ingreso: la cancha con la ficha en el punto central."""
    return ft.Container(
        content=ft.Column(
            [
                mitad_de_cancha(centro or logo(88), alto_centro),
                ft.Container(
                    ft.Column(contenido, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=ft.Padding.symmetric(horizontal=24),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=4,
        ),
        gradient=ft.LinearGradient(begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
                                   colors=[CANCHA_OSCURA, COLOR_PRINCIPAL]),
        border_radius=ft.BorderRadius.only(bottom_left=32, bottom_right=32),
        padding=ft.Padding.only(top=8, bottom=28),
    )


def nombre_grande(tam: int = 56) -> ft.Text:
    return ft.Text("Join In", font_family=LETRA_TITULOS, size=tam, weight=ft.FontWeight.W_900, color=BLANCO,
                   text_align=ft.TextAlign.CENTER)


class PantallaConectando(Pantalla):
    ruta = "/inicio"

    def vista(self) -> ft.View:
        self.cuerpo = ft.Column(
            [c.cargando("Conectando con Join In…"), c.suave("La primera vez del día puede tardar hasta un minuto.")],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.View(
            route=self.ruta,
            bgcolor=FONDO,
            padding=ft.Padding.all(0),
            spacing=24,
            appbar=barra_de_color(CANCHA_OSCURA),
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
            controls=[cancha([nombre_grande()]), ft.Container(self.cuerpo, padding=ft.Padding.symmetric(horizontal=24))],
        )

    async def cargar(self) -> None:
        if not await self.app.conectar():
            self.cuerpo.controls = [
                c.vacio(ft.Icons.WIFI_OFF, "Sin conexión", "No pudimos conectarnos con Join In. Revisa tu internet."),
                c.boton_principal("Reintentar", self.reintentar, ft.Icons.REFRESH, expandir=False),
            ]

    async def reintentar(self, e=None) -> None:
        self.cuerpo.controls = [c.cargando("Conectando con Join In…")]
        self.app.page.update()
        await self.cargar()

    async def refrescar(self) -> None:
        pass
