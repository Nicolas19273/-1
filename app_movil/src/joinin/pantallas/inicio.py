"""Pantalla de arranque: se conecta con el servidor (que puede estar despertando)."""

from __future__ import annotations

import flet as ft

from .. import componentes as c
from ..app import Pantalla
from ..estilo import AMARILLO, FONDO, TINTA


def logo(tam: int = 72) -> ft.Container:
    """La ficha amarilla con «+1»: el que falta."""
    return ft.Container(
        content=ft.Text("+1", size=tam * 0.42, weight=ft.FontWeight.W_900, color=TINTA),
        width=tam,
        height=tam,
        bgcolor=AMARILLO,
        border=ft.Border.all(3, TINTA),
        border_radius=ft.BorderRadius.all(tam * 0.28),
        alignment=ft.Alignment.CENTER,
    )


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
            padding=ft.Padding.all(24),
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[logo(), c.titulo("Join In", 30), self.cuerpo],
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
