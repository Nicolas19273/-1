"""
El detalle de un aviso: datos, cupos, quiénes van, unirse o salirse,
eliminar (si es tuyo), denunciar y comentarios.
"""

from __future__ import annotations

from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import AMARILLO, BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, ROJO, ROJO_SUAVE, TINTA


class PantallaAviso(Pantalla):
    ruta = "/aviso"
    se_refresca_sola = True

    def __init__(self, app, aviso_id: int):
        super().__init__(app)
        self.aviso_id = int(aviso_id)
        self.aviso: dict | None = None
        self.comentarios: list[dict] = []
        self.momento = f.ahora()

    def vista(self) -> ft.View:
        self.cuerpo = ft.Column([c.cargando("Cargando aviso…")], spacing=14)
        self.titulo_comentarios = c.titulo("Comentarios", 18)
        self.lista_comentarios = ft.Column(spacing=10)
        # El campo se crea una sola vez: así el refresco automático no borra lo que escribes.
        self.campo_comentario = ft.TextField(
            label="Escribe un comentario",
            hint_text="Ej: ¿Alguien tiene pelota?",
            multiline=True,
            min_lines=1,
            max_lines=4,
            max_length=self.app.config.get("largo_max_comentario", 300),
            expand=True,
            on_submit=self.comentar,
        )
        self.fila_comentar = ft.Row(
            [self.campo_comentario, ft.IconButton(ft.Icons.SEND, tooltip="Enviar", icon_color=COLOR_PRINCIPAL,
                                                   on_click=self.comentar)],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.seccion_comentarios = ft.Column(
            [ft.Divider(color=GRIS_SUAVE), self.titulo_comentarios, self.lista_comentarios, self.fila_comentar],
            spacing=10,
            visible=False,
        )
        return self.vista_base(
            "Aviso",
            [self.cuerpo, self.seccion_comentarios],
            acciones=[ft.IconButton(ft.Icons.REFRESH, tooltip="Actualizar", on_click=self.actualizar)],
        )

    # ------------------------------------------------------------------ datos

    async def cargar(self) -> None:
        r = await self.app.llamar(self.api.ver_aviso, self.aviso_id, avisar=self.aviso is None)
        if r is None:
            if self.aviso is None:
                self.cuerpo.controls = [
                    c.vacio(ft.Icons.ERROR_OUTLINE, "No pudimos abrir este aviso", "Puede que ya no exista."),
                    c.boton_principal("Volver", self.volver, ft.Icons.ARROW_BACK, expandir=False),
                ]
            return
        self.momento = f.leer_fecha(r["ahora"]) or f.ahora()
        self.aviso = r["aviso"]
        self.comentarios = r["comentarios"]
        self.pintar()

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    async def volver(self, e=None) -> None:
        await self.app.volver()

    # ------------------------------------------------------------------ dibujo

    def pintar(self) -> None:
        a = self.aviso
        inicio = f.leer_fecha(a["inicio_evento"])
        controles: list[ft.Control] = [
            ft.Row(
                [c.chip_categoria(a["categoria"], a["nombre_categoria"])]
                + ([c.chip(f.texto_valor(a["valor"]), ft.Icons.PAYMENTS, color=TINTA, fondo=AMARILLO)]
                   if a.get("valor") is not None else []),
                spacing=6,
                wrap=True,
            ),
            c.titulo(a["titulo"], 24),
        ]
        cierre = self._cierre()
        if cierre is not None:
            controles.append(cierre)
        controles += [
            c.dato(ft.Icons.SCHEDULE, f.texto_fecha_evento(inicio, self.momento)),
            c.dato(ft.Icons.PLACE, a["lugar"]),
            ft.Row(
                [
                    ft.Button(
                        "Cómo llegar",
                        icon=ft.Icons.DIRECTIONS,
                        url=f.url_como_llegar(a),
                        style=ft.ButtonStyle(bgcolor=BLANCO, color=COLOR_PRINCIPAL,
                                             shape=ft.RoundedRectangleBorder(radius=12)),
                    )
                ]
            ),
            c.tarjeta([c.resumen_cupos(a), c.suave(f.texto_quienes(a))]),
        ]
        if a["abierto"]:
            controles.append(c.suave(f.texto_tiempo_restante(f.leer_fecha(a["cierra_en"]), self.momento)))
        if a.get("descripcion"):
            controles += [c.titulo("Detalles", 16), c.texto(a["descripcion"], 15, selectable=True)]
        controles += self._acciones()
        self.cuerpo.controls = controles
        self._pintar_comentarios()

    def _cierre(self) -> ft.Control | None:
        estado = self.aviso.get("estado")
        if not estado:
            return None
        principal, secundario = f.CIERRES.get(estado, ("Aviso cerrado", ""))
        secundario = secundario.format(horas=self.aviso["duracion_horas"])
        if estado == f.CANCELADO:
            if self.aviso.get("cancelado_por") == "admin":
                secundario = "La administración sacó este aviso del tablero."
            return c.nota(principal, secundario, color=ROJO, fondo=ROJO_SUAVE)
        if estado == f.COMPLETO:
            return c.nota(principal, secundario, color=BLANCO, fondo=COLOR_PRINCIPAL)
        return c.nota(principal, secundario)

    def _acciones(self) -> list[ft.Control]:
        a = self.aviso
        empezo = self.momento >= f.leer_fecha(a["inicio_evento"])
        filas: list[ft.Control] = []
        if a["es_mio"]:
            filas.append(c.nota("Este aviso es tuyo", "Lo verás en tu buzón aunque se llene."))
            if not a["cancelado"]:
                filas.append(ft.Row([c.boton_peligro("Eliminar aviso", self.preguntar_eliminar)]))
        elif a["me_uni"]:
            filas.append(c.nota("Ya estás dentro", "Te esperamos. Si no puedes ir, sal para liberar tu cupo.",
                                color=BLANCO, fondo=COLOR_PRINCIPAL))
            if not a["cancelado"] and not empezo:
                filas.append(ft.Row([c.boton_peligro("Salirme", self.preguntar_salirse, ft.Icons.LOGOUT)]))
        elif a["abierto"]:
            filas.append(ft.Row([c.boton_principal("Unirme", self.unirse, ft.Icons.GROUP_ADD)]))
        if not a["es_mio"] and not a["cancelado"]:
            filas.append(ft.Row([c.boton_texto("Denunciar este aviso", self.abrir_denuncia, ft.Icons.FLAG_OUTLINED)],
                                alignment=ft.MainAxisAlignment.END))
        return filas

    def _pintar_comentarios(self) -> None:
        a = self.aviso
        self.seccion_comentarios.visible = True
        n = len(self.comentarios)
        self.titulo_comentarios.value = "Comentarios" + (f" ({n})" if n else "")
        if not self.comentarios:
            self.lista_comentarios.controls = [c.suave("Aún no hay comentarios. Pregunta lo que necesites saber.")]
        else:
            self.lista_comentarios.controls = [self._comentario(x) for x in self.comentarios]
        hasta = f.leer_fecha(a["visible_en_buzon_hasta"])
        self.fila_comentar.visible = not a["cancelado"] and (hasta is None or self.momento < hasta)

    def _comentario(self, x: dict) -> ft.Control:
        momento = f.leer_fecha(x["momento"])
        de_quien_organiza = x.get("de_quien_organiza")
        cabeza: list[ft.Control] = [
            ft.Text(x["nombre"], size=13, weight=ft.FontWeight.W_800, color=COLOR_PRINCIPAL if de_quien_organiza else TINTA),
            ft.Text(f.texto_hace(momento, self.momento) if momento else "", size=12, color=GRIS),
        ]
        fila: list[ft.Control] = [
            c.avatar(x["nombre"], color=COLOR_PRINCIPAL if de_quien_organiza else GRIS_SUAVE,
                     texto_color=BLANCO if de_quien_organiza else TINTA),
            ft.Column(
                [ft.Row(cabeza, spacing=8, wrap=True), ft.Text(x["texto"], size=14, color=TINTA, selectable=True)],
                spacing=2,
                expand=True,
                tight=True,
            ),
        ]
        if x.get("es_mio") or self.app.es_admin:
            fila.append(ft.IconButton(ft.Icons.CLOSE, icon_size=18, icon_color=GRIS, tooltip="Borrar comentario",
                                      on_click=partial(self.preguntar_borrar_comentario, x["id"])))
        return ft.Row(fila, vertical_alignment=ft.CrossAxisAlignment.START, spacing=10)

    # ------------------------------------------------------------------ acciones

    async def unirse(self, e=None) -> None:
        r = await self.app.llamar(self.api.unirse, self.aviso_id)
        if r is not None:
            self.app.avisar(f"¡Listo! Te uniste a «{r['aviso']['titulo']}». Lo verás en tu buzón.")
            await self.cargar()

    def preguntar_salirse(self, e=None) -> None:
        self.app.preguntar("¿Salirte de este aviso?", "Tu cupo quedará libre para otra persona.", "Salirme",
                           self.salirse, no="Me quedo")

    async def salirse(self) -> None:
        if await self.app.llamar(self.api.salirse, self.aviso_id) is not None:
            self.app.avisar("Saliste del aviso. Tu cupo quedó libre.")
            await self.cargar()

    def preguntar_eliminar(self, e=None) -> None:
        self.app.preguntar(
            "¿Eliminar este aviso?",
            "Saldrá del tablero y quienes se unieron lo verán como cancelado. No se puede deshacer.",
            "Eliminar",
            self.eliminar,
        )

    async def eliminar(self) -> None:
        if await self.app.llamar(self.api.eliminar, self.aviso_id) is not None:
            self.app.avisar("Eliminaste el aviso.")
            await self.cargar()

    async def comentar(self, e=None) -> None:
        texto = (self.campo_comentario.value or "").strip()
        if not texto:
            self.app.avisar("Escribe un comentario.", error=True)
            return
        if await self.app.llamar(self.api.comentar, self.aviso_id, texto) is not None:
            self.campo_comentario.value = ""
            await self.cargar()

    def preguntar_borrar_comentario(self, comentario_id: int, e=None) -> None:
        self.app.preguntar("¿Borrar este comentario?", "Se quitará para todos.", "Borrar",
                           partial(self.borrar_comentario, comentario_id))

    async def borrar_comentario(self, comentario_id: int) -> None:
        if await self.app.llamar(self.api.borrar_comentario, comentario_id) is not None:
            self.app.avisar("Comentario borrado.")
            await self.cargar()

    # ------------------------------------------------------------------ denuncia

    def abrir_denuncia(self, e=None) -> None:
        motivos = self.app.config.get("motivos_denuncia", [])
        self.motivo = ft.RadioGroup(
            content=ft.Column([ft.Radio(value=m["clave"], label=m["nombre"]) for m in motivos], spacing=0, tight=True),
        )
        self.error_denuncia = c.mensaje_error()
        self.detalle_denuncia = ft.TextField(
            label="Cuéntanos más (opcional)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            max_length=self.app.config.get("largo_max_denuncia", 300),
        )
        self.dialogo_denuncia = ft.AlertDialog(
            modal=True,
            title=ft.Text("Denunciar aviso", weight=ft.FontWeight.W_800),
            content=ft.Column(
                [
                    ft.Text("¿Qué tiene de malo? La administración lo revisará. Nadie sabrá que fuiste tú.", color=TINTA),
                    self.motivo,
                    self.detalle_denuncia,
                    self.error_denuncia,
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._cerrar_dialogo),
                ft.TextButton("Enviar denuncia", on_click=self.denunciar, style=ft.ButtonStyle(color=ROJO)),
            ],
        )
        self.app.page.show_dialog(self.dialogo_denuncia)

    def _cerrar_dialogo(self, e=None) -> None:
        self.app.cerrar_dialogo(self.dialogo_denuncia)

    def _error_en_denuncia(self, mensaje: str) -> None:
        self.error_denuncia.value = mensaje
        self.error_denuncia.visible = True
        self.app.page.update()

    async def denunciar(self, e=None) -> None:
        if not self.motivo.value:
            self._error_en_denuncia("Elige un motivo.")
            return
        r = await self.app.llamar(self.api.denunciar, self.aviso_id, self.motivo.value,
                                  (self.detalle_denuncia.value or "").strip(), avisar=False)
        if r is None:
            if self.app.ultimo_error is not None and self.app.ultimo_error.estado != 401:
                self._error_en_denuncia(self.app.ultimo_error.mensaje)
            return
        self.app.cerrar_dialogo(self.dialogo_denuncia)
        self.app.avisar("Gracias. La administración revisará este aviso.")
