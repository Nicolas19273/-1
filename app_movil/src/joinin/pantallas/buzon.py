"""Mi buzón: los avisos a los que me uní y los que organizo, con cómo van."""

from __future__ import annotations

from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import BLANCO, COLOR_PRINCIPAL, ROJO, ROJO_SUAVE, TINTA
from .tablero import chip_filtro

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
        self.pestanas = ft.Row(spacing=8)
        self.lista = ft.Column([c.cargando("Abriendo tu buzón…")], spacing=12)
        self._pintar_pestanas()
        return self.vista_base(
            "Mi buzón",
            [c.suave("Aquí ves cómo van tus avisos, aunque ya no estén en el tablero."), self.pestanas, self.lista],
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
        self.pestanas.controls = [
            chip_filtro(f"Me uní ({n_uni})", self.pestana == ME_UNI, partial(self.cambiar, ME_UNI),
                        ft.Icons.GROUP, color=COLOR_PRINCIPAL),
            chip_filtro(f"Organizo ({n_org})", self.pestana == ORGANIZO, partial(self.cambiar, ORGANIZO),
                        ft.Icons.CAMPAIGN, color=COLOR_PRINCIPAL),
        ]

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
                                "Busca en el tablero un aviso que te guste y toca «Unirme».")
            else:
                vacio = c.vacio(ft.Icons.CAMPAIGN, "No tienes avisos publicados",
                                "Toca «Crear aviso» en el tablero para publicar lo que te falta.")
            self.lista.controls = [vacio]
            return
        self.lista.controls = [
            c.tarjeta_aviso(aviso, self.momento, partial(self.abrir, aviso["id"]), [self._estado(aviso)])
            for aviso in avisos
        ]

    def _estado(self, aviso: dict) -> ft.Control:
        principal, secundario = f.estado_en_buzon(aviso, self.momento)
        if aviso.get("cancelado"):
            return c.nota(principal, secundario, color=ROJO, fondo=ROJO_SUAVE)
        if aviso["cupos_libres"] <= 0:
            return c.nota(principal, secundario, color=BLANCO, fondo=COLOR_PRINCIPAL)
        return c.nota(principal, secundario, color=TINTA)

    async def abrir(self, aviso_id: int, e=None) -> None:
        from .aviso import PantallaAviso

        await self.app.ir(PantallaAviso(self.app, aviso_id))
