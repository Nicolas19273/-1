"""Mi buzón: los avisos a los que me uní y los que organizo, con cómo van."""

from __future__ import annotations

from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import BLANCO, COLOR_PRINCIPAL, ROJO, ROJO_SUAVE, TINTA

ME_UNI, ORGANIZO = "me_uni", "organizo"


class PantallaBuzon(Pantalla):
    ruta = "/buzon"
    se_refresca_sola = True

    def __init__(self, app):
        super().__init__(app)
        self.pestana = ME_UNI
        self.datos: dict | None = None
        self.momento = f.ahora()

    def vista(self) -> ft.View:
        self.pestanas = ft.Container()
        self.lista = ft.Column([c.cargando("Abriendo tu buzón…")], spacing=12)
        self._pintar_pestanas()
        return self.vista_base(
            "Mi buzón",
            [c.suave("Aquí ves cómo van tus avisos, aunque ya no estén en el tablero.", 14), self.pestanas,
             self.lista],
            al_refrescar=self.actualizar,
        )

    async def cargar(self) -> None:
        r = await self.app.llamar(self.api.buzon, avisar=self.datos is None)
        if r is None:
            if self.datos is None:
                self.lista.controls = [c.vacio(ft.Icons.WIFI_OFF, "No pudimos abrir tu buzón", "Desliza hacia abajo para reintentar.")]
            return
        self.datos = r
        self.momento = f.leer_fecha(r["ahora"]) or f.ahora()
        self._pintar_pestanas()
        self._pintar_lista()

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    def _pintar_pestanas(self) -> None:
        n_uni = len(self.datos[ME_UNI]) if self.datos else 0
        n_org = len(self.datos[ORGANIZO]) if self.datos else 0
        me_uni, organizo = f"Me uní ({n_uni})", f"Organizo ({n_org})"
        self.pestanas.content = c.pestanas(
            [(me_uni, ft.Icons.GROUP, partial(self.cambiar, ME_UNI)),
             (organizo, ft.Icons.CAMPAIGN, partial(self.cambiar, ORGANIZO))],
            me_uni if self.pestana == ME_UNI else organizo,
        )

    def cambiar(self, pestana: str, e=None) -> None:
        self.pestana = pestana
        self._pintar_pestanas()
        self._pintar_lista()
        self.app.page.update()

    def _pintar_lista(self) -> None:
        if self.datos is None:
            return
        avisos = self.datos[self.pestana]
        if not avisos:
            if self.pestana == ME_UNI:
                vacio = c.vacio(ft.Icons.INBOX, "Todavía no te unes a nada",
                                "Busca en el tablero un aviso que te guste y toca «Unirme».",
                                c.boton_oscuro("Ir al tablero", self.ir_al_tablero, ft.Icons.ARROW_BACK, expandir=False))
            else:
                vacio = c.vacio(ft.Icons.CAMPAIGN, "No tienes avisos publicados",
                                "Publica lo que te falta y aquí verás cómo se va llenando.",
                                c.boton_principal("Crear aviso", self.ir_a_crear, ft.Icons.ADD, expandir=False))
            self.lista.controls = [vacio]
            return
        self.lista.controls = [
            c.tarjeta_aviso(aviso, self.momento, partial(self.abrir, aviso["id"]), [self._estado(aviso)])
            for aviso in avisos
        ]

    def _estado(self, aviso: dict) -> ft.Control:
        principal, secundario = f.estado_en_buzon(aviso, self.momento)
        if aviso.get("cancelado"):
            return c.nota(principal, secundario, color=ROJO, fondo=ROJO_SUAVE, icono=ft.Icons.EVENT_BUSY)
        if aviso["cupos_libres"] <= 0:
            return c.nota(principal, secundario, color=BLANCO, fondo=COLOR_PRINCIPAL, icono=ft.Icons.CHECK_CIRCLE)
        return c.nota(principal, secundario, color=TINTA, fondo="#F1F3EE", icono=ft.Icons.INFO_OUTLINE)

    async def ir_al_tablero(self, e=None) -> None:
        await self.app.volver()

    async def ir_a_crear(self, e=None) -> None:
        from .crear import PantallaCrear

        await self.app.cambiar(PantallaCrear(self.app))

    async def abrir(self, aviso_id: int, e=None) -> None:
        from .aviso import PantallaAviso

        await self.app.ir(PantallaAviso(self.app, aviso_id))
