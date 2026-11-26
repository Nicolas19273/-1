"""
Ingreso con el correo institucional: correo → código de 6 dígitos → (la
primera vez) nombre. Después, este celular entra directo.
"""

from __future__ import annotations

import flet as ft

from .. import componentes as c
from ..app import Pantalla, ToquesSecretos
from ..estilo import BLANCO, FONDO, GRIS_SUAVE, TINTA
from .inicio import logo


class PantallaIngreso(Pantalla):
    ruta = "/ingreso"

    def __init__(self, app):
        super().__init__(app)
        self.paso = "correo"
        self.correo = ""
        self.codigo_prueba: str | None = None
        # La administración no tiene botón: se entra tocando 5 veces seguidas el logo «+1».
        self.secreto = ToquesSecretos(self.ir_a_admin)

    def vista(self) -> ft.View:
        self.tarjeta = ft.Container(
            bgcolor=BLANCO,
            border=ft.Border.all(1, GRIS_SUAVE),
            border_radius=ft.BorderRadius.all(20),
            padding=ft.Padding.all(18),
        )
        self.pintar()
        marca = ft.Column(
            [
                ft.Container(logo(80), on_click=self.secreto.tocar),
                ft.Text("Join In", size=36, weight=ft.FontWeight.W_900, color=TINTA),
                c.texto("Arma tu panorama con estudiantes de la ULagos: únete a un partido, una junta de "
                        "estudio o una salida, o publica lo que te falta.", 15, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )
        # Esta pantalla no tiene barra de arriba: SafeArea evita que el logo y el título
        # queden debajo de la barra de estado del celular (la hora, la batería).
        # Todo va centrado en la pantalla, con el nombre de la app bien a la vista.
        return ft.View(
            route=self.ruta,
            bgcolor=FONDO,
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
            scroll=ft.ScrollMode.AUTO,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.SafeArea(
                    content=ft.Column([marca, self.tarjeta], spacing=28,
                                      horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                    minimum_padding=ft.Padding.symmetric(vertical=16),
                ),
            ],
        )

    # ------------------------------------------------------------------ pasos

    def pintar(self) -> None:
        dominio = self.app.config.get("dominio", "alumnos.ulagos.cl")
        largo = self.app.config.get("largo_codigo", 6)
        if self.paso == "correo":
            self.campo_correo = ft.TextField(
                label="Correo institucional",
                hint_text=f"nombre@{dominio}",
                value=self.correo,
                keyboard_type=ft.KeyboardType.EMAIL,
                autofocus=bool(self.correo),  # al abrir la app, sin teclado: primero se ve todo
                on_submit=self.enviar,
            )
            controles = [
                c.titulo("Ingresa con tu correo", 20),
                c.suave(f"Solo pueden entrar estudiantes con correo @{dominio}. Te enviaremos un código."),
                self.campo_correo,
                ft.Row([c.boton_principal("Enviarme el código", self.enviar, ft.Icons.MAIL)]),
            ]
        elif self.paso == "codigo":
            self.campo_codigo = ft.TextField(
                label="Código",
                hint_text="6 dígitos",
                keyboard_type=ft.KeyboardType.NUMBER,
                max_length=largo,
                autofocus=True,
                on_submit=self.verificar,
            )
            controles = [
                c.titulo("Revisa tu correo", 20),
                c.suave(f"Te enviamos un código de {largo} dígitos a {self.correo}. Vale 10 minutos."),
            ]
            if self.codigo_prueba:
                controles.append(c.nota("Modo de prueba", f"El servidor no envía correos: tu código es {self.codigo_prueba}."))
            controles += [
                self.campo_codigo,
                ft.Row([c.boton_principal("Entrar", self.verificar, ft.Icons.LOGIN)]),
                ft.Row(
                    [c.boton_texto("Reenviar código", self.reenviar), c.boton_texto("Cambiar correo", self.cambiar_correo)],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ]
        else:  # nombre
            self.campo_nombre = ft.TextField(
                label="Tu nombre",
                hint_text="Ej: Camila Vera",
                max_length=self.app.config.get("largo_nombre", [2, 40])[1],
                capitalization=ft.TextCapitalization.WORDS,
                autofocus=True,
                on_submit=self.registrar,
            )
            controles = [
                c.titulo("¿Cómo te llamas?", 20),
                c.suave("Es lo que verán los demás cuando te unas a un aviso. Solo te lo pedimos esta vez."),
                self.campo_nombre,
                ft.Row([c.boton_principal("Listo", self.registrar, ft.Icons.CHECK)]),
            ]
        controles.append(c.suave("Un correo, un celular: después de esta vez, este celular entra directo."))
        self.tarjeta.content = ft.Column(controles, spacing=14, tight=True)

    def _cambiar_a(self, paso: str) -> None:
        self.paso = paso
        self.pintar()
        self.app.page.update()

    # ------------------------------------------------------------------ acciones

    async def enviar(self, e=None) -> None:
        correo = (self.campo_correo.value or "").strip()
        r = await self.app.llamar(self.api.pedir_codigo, correo)
        if r is None:
            return
        self.correo = r["correo"]
        self.codigo_prueba = r.get("codigo_prueba")
        self._cambiar_a("codigo")

    async def reenviar(self, e=None) -> None:
        r = await self.app.llamar(self.api.pedir_codigo, self.correo)
        if r is not None:
            self.codigo_prueba = r.get("codigo_prueba")
            self.pintar()
            self.app.avisar("Te enviamos un código nuevo.")

    def cambiar_correo(self, e=None) -> None:
        self.codigo_prueba = None
        self._cambiar_a("correo")

    async def verificar(self, e=None) -> None:
        codigo = "".join((self.campo_codigo.value or "").split())
        r = await self.app.llamar(self.api.verificar_codigo, self.correo, codigo)
        if r is None:
            return
        if r.get("necesita_nombre"):
            self._cambiar_a("nombre")
            return
        await self.entrar(r)

    async def registrar(self, e=None) -> None:
        r = await self.app.llamar(self.api.registrar, self.correo, (self.campo_nombre.value or "").strip())
        if r is not None:
            await self.entrar(r)

    async def entrar(self, respuesta: dict) -> None:
        self.app.nombre = respuesta.get("nombre", "")
        self.app.avisar(f"¡Hola, {self.app.nombre}!")
        await self.app.ir_al_tablero()

    async def ir_a_admin(self, e=None) -> None:
        from .admin import abrir_administracion

        await abrir_administracion(self.app)

    async def refrescar(self) -> None:
        pass
