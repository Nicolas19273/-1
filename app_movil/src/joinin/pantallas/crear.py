"""Crear un aviso: qué, cuántos, dónde y cuándo, cuánto cuesta y cuánto dura."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, TINTA, colores_de, icono_de
from .tablero import chip_filtro

DIAS_LARGOS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def texto_dia(dia: date, hoy: date) -> str:
    if dia == hoy:
        return "Hoy"
    if dia == hoy + timedelta(days=1):
        return "Mañana"
    return f"{DIAS_LARGOS[dia.weekday()].capitalize()} {dia.day} {f.MESES[dia.month - 1]}"


def seccion(titulo: str, ayuda: str, controles: list[ft.Control]) -> ft.Container:
    return c.tarjeta([c.titulo(titulo, 18), c.suave(ayuda), *controles], espacio=12)


class Contador:
    """«−  9  +»: para elegir cuántas personas son."""

    def __init__(self, valor: int, minimo: int, maximo: int, al_cambiar):
        self.valor = valor
        self.minimo = minimo
        self.maximo = maximo
        self.al_cambiar = al_cambiar
        self.numero = ft.Text(str(valor), size=20, weight=ft.FontWeight.W_800, color=TINTA, width=44,
                              text_align=ft.TextAlign.CENTER)
        self.control = ft.Container(
            content=ft.Row(
                [
                    ft.IconButton(ft.Icons.REMOVE, tooltip="Uno menos", on_click=partial(self.mover, -1)),
                    self.numero,
                    ft.IconButton(ft.Icons.ADD, tooltip="Uno más", on_click=partial(self.mover, 1)),
                ],
                spacing=0,
                tight=True,
            ),
            bgcolor=BLANCO,
            border=ft.Border.all(1, GRIS_SUAVE),
            border_radius=ft.BorderRadius.all(24),
        )

    def poner(self, valor: int) -> None:
        self.valor = max(self.minimo, min(self.maximo, valor))
        self.numero.value = str(self.valor)

    def mover(self, paso: int, e=None) -> None:
        self.poner(self.valor + paso)
        self.al_cambiar()


class PantallaCrear(Pantalla):
    ruta = "/crear"

    def __init__(self, app):
        super().__init__(app)
        cfg = app.config
        self.max_personas = int(cfg.get("max_personas", 40))
        self.duraciones = list(cfg.get("duraciones", [24, 48]))
        categorias = cfg.get("categorias", [])
        self.categoria = categorias[0]["clave"] if categorias else ""
        self.duracion = self.duraciones[0]
        self.con_costo = False
        self.lat: float | None = None
        self.lng: float | None = None
        sugerida = (f.ahora() + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        self.dia: date = sugerida.date()
        self.hora: time = sugerida.time()
        self.publicando = False

    # ------------------------------------------------------------------ vista

    def vista(self) -> ft.View:
        cfg = self.app.config
        largo_titulo = cfg.get("largo_titulo", [3, 80])[1]
        largo_lugar = cfg.get("largo_lugar", [3, 120])[1]

        # ¿Qué van a hacer?
        self.categorias = ft.Row(wrap=True, spacing=8, run_spacing=8)
        self.campo_titulo = ft.TextField(label="Título", hint_text="Ej: Pichanga 7 vs 7, falta uno",
                                         max_length=largo_titulo, on_blur=self.revisar_titulo)
        self.aviso_titulo = c.mensaje_error()

        # ¿Cuántos son?
        self.actuales = Contador(1, 1, self.max_personas - 1, self.cambiaron_personas)
        self.necesarias = Contador(2, 2, self.max_personas, self.cambiaron_personas)
        self.previa_faltan = ft.Text("", size=18, weight=ft.FontWeight.W_800, color=TINTA)
        self.previa_barra = ft.Column()

        # ¿Dónde y cuándo?
        self.campo_lugar = ft.TextField(label="Lugar", hint_text="Ej: Cancha del liceo, Parque Chuyaca",
                                        max_length=largo_lugar, on_blur=self.revisar_lugar)
        self.aviso_lugar = c.mensaje_error()
        self.ubicacion = ft.Column(spacing=6)
        self.boton_dia = ft.OutlinedButton("", icon=ft.Icons.CALENDAR_MONTH, on_click=self.elegir_dia, expand=True)
        self.boton_hora = ft.OutlinedButton("", icon=ft.Icons.SCHEDULE, on_click=self.elegir_hora, expand=True)

        # Valor
        self.opciones_costo = ft.Row(spacing=8, wrap=True)
        self.campo_valor = ft.TextField(
            label="Valor por persona",
            hint_text="Ej: 2.000",
            prefix=ft.Text("$ "),
            suffix=ft.Text("CLP"),
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=7,
            visible=False,
            on_change=self.cambio_valor,
        )
        self.previa_valor = c.suave("")

        # Detalles y duración
        self.campo_descripcion = ft.TextField(
            label="Detalles (opcional)",
            hint_text="Ej: Se paga la cancha entre todos. Traer polera oscura.",
            multiline=True,
            min_lines=2,
            max_lines=6,
            max_length=cfg.get("largo_max_descripcion", 500),
            on_blur=self.revisar_descripcion,
        )
        self.aviso_descripcion = c.mensaje_error()
        self.opciones_duracion = ft.Row(spacing=8, wrap=True)

        self.boton_publicar = c.boton_principal("Publicar aviso", self.publicar, ft.Icons.CAMPAIGN)

        self._pintar_categorias()
        self.cambiaron_personas(actualizar=False)
        self._pintar_ubicacion()
        self._pintar_fecha()
        self._pintar_costo()
        self._pintar_duracion()

        return self.vista_base(
            "Crear aviso",
            [
                seccion("¿Qué van a hacer?", "Elige una categoría y ponle un título claro.",
                        [self.categorias, self.campo_titulo, self.aviso_titulo]),
                seccion(
                    "¿Cuántos son?",
                    f"Cuenta a todos, contigo incluido (máximo {self.max_personas}).",
                    [
                        ft.Row([c.texto("Ya somos", 15, ft.FontWeight.W_700), self.actuales.control],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Row([c.texto("Necesitamos en total", 15, ft.FontWeight.W_700), self.necesarias.control],
                               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        c.nota("Así lo verán en el tablero"),
                        self.previa_faltan,
                        self.previa_barra,
                    ],
                ),
                seccion(
                    "¿Dónde y cuándo?",
                    "Mientras más exacto, más fácil llegar.",
                    [self.campo_lugar, self.aviso_lugar, self.ubicacion, ft.Row([self.boton_dia, self.boton_hora])],
                ),
                seccion("¿Cuánto cuesta por persona?", "Si se paga algo (cancha, entrada), indícalo.",
                        [self.opciones_costo, self.campo_valor, self.previa_valor]),
                seccion("Detalles", "Lo que conviene saber antes de ir.", [self.campo_descripcion, self.aviso_descripcion]),
                seccion(
                    "¿Cuánto dura el aviso?",
                    "En el tablero se cierra antes si se completa el grupo o llega la hora del evento. "
                    "En tu buzón lo verás durante todo el plazo.",
                    [self.opciones_duracion],
                ),
                ft.Row([self.boton_publicar]),
                ft.Container(height=24),
            ],
        )

    # ------------------------------------------------------------------ partes

    def _pintar_categorias(self) -> None:
        chips = []
        for cat in self.app.config.get("categorias", []):
            fuerte, claro = colores_de(cat["clave"])
            chips.append(chip_filtro(cat["nombre"], cat["clave"] == self.categoria,
                                     partial(self.elegir_categoria, cat["clave"]),
                                     icono_de(cat["clave"]), color=fuerte, fondo=claro))
        self.categorias.controls = chips

    def elegir_categoria(self, clave: str, e=None) -> None:
        self.categoria = clave
        self._pintar_categorias()
        self.app.page.update()

    def cambiaron_personas(self, actualizar: bool = True) -> None:
        if self.necesarias.valor <= self.actuales.valor:
            self.necesarias.poner(self.actuales.valor + 1)
        faltan = self.necesarias.valor - self.actuales.valor
        self.previa_faltan.value = f.texto_faltan(faltan)
        self.previa_barra.controls = [c.barra_cupos(self.actuales.valor, self.necesarias.valor)]
        if actualizar:
            self.app.page.update()

    def _pintar_ubicacion(self) -> None:
        controles: list[ft.Control] = []
        if self.lat is not None:
            controles.append(
                ft.Row(
                    [
                        c.chip("Ubicación marcada en el mapa", ft.Icons.PIN_DROP, color=BLANCO, fondo=COLOR_PRINCIPAL),
                        ft.IconButton(ft.Icons.CLOSE, icon_size=18, tooltip="Quitar ubicación",
                                      on_click=self.quitar_ubicacion),
                    ],
                    spacing=4,
                )
            )
        controles.append(ft.Row([c.boton_texto("Buscar el lugar en el mapa", self.abrir_buscador, ft.Icons.SEARCH)]))
        self.ubicacion.controls = controles

    def quitar_ubicacion(self, e=None) -> None:
        self.lat = self.lng = None
        self._pintar_ubicacion()
        self.app.page.update()

    def _pintar_fecha(self) -> None:
        self.boton_dia.content = texto_dia(self.dia, f.ahora().date())
        self.boton_hora.content = self.hora.strftime("%H:%M")

    def _pintar_costo(self) -> None:
        self.opciones_costo.controls = [
            chip_filtro("Gratis ($0)", not self.con_costo, partial(self.elegir_costo, False), ft.Icons.MONEY_OFF,
                        color=COLOR_PRINCIPAL),
            chip_filtro("Tiene costo", self.con_costo, partial(self.elegir_costo, True), ft.Icons.PAYMENTS,
                        color=COLOR_PRINCIPAL),
        ]
        self.campo_valor.visible = self.con_costo
        self.previa_valor.visible = self.con_costo
        self.cambio_valor(actualizar=False)

    def elegir_costo(self, con_costo: bool, e=None) -> None:
        self.con_costo = con_costo
        self._pintar_costo()
        self.app.page.update()

    def cambio_valor(self, e=None, actualizar: bool = False) -> None:
        texto = (self.campo_valor.value or "").replace("$", "").replace(" ", "")
        limpio = texto.replace(".", "")
        if limpio.isdigit() and int(limpio) > 0:
            self.previa_valor.value = "Se mostrará como: " + f.texto_valor(int(limpio))
        else:
            self.previa_valor.value = ""
        if actualizar:
            self.app.page.update()

    def _pintar_duracion(self) -> None:
        self.opciones_duracion.controls = [
            chip_filtro(f"{horas} horas", horas == self.duracion, partial(self.elegir_duracion, horas),
                        ft.Icons.TIMER, color=COLOR_PRINCIPAL)
            for horas in self.duraciones
        ]

    def elegir_duracion(self, horas: int, e=None) -> None:
        self.duracion = horas
        self._pintar_duracion()
        self.app.page.update()

    # ------------------------------------------------------------------ fecha y hora

    def elegir_dia(self, e=None) -> None:
        hoy = f.ahora()
        selector = ft.DatePicker(
            value=datetime.combine(self.dia, time(12)),
            first_date=datetime.combine(hoy.date(), time(0)),
            last_date=datetime.combine(hoy.date() + timedelta(days=364), time(0)),
            help_text="¿Qué día es el evento?",
            cancel_text="Cancelar",
            confirm_text="Listo",
            on_change=self.cambio_dia,
        )
        self.app.page.show_dialog(selector)

    def cambio_dia(self, e) -> None:
        valor = e.control.value
        if isinstance(valor, datetime):
            self.dia = valor.date()
        elif isinstance(valor, date):
            self.dia = valor
        self._pintar_fecha()
        self.app.page.update()

    def elegir_hora(self, e=None) -> None:
        selector = ft.TimePicker(
            value=self.hora,
            help_text="¿A qué hora empieza?",
            cancel_text="Cancelar",
            confirm_text="Listo",
            on_change=self.cambio_hora,
        )
        self.app.page.show_dialog(selector)

    def cambio_hora(self, e) -> None:
        valor = e.control.value
        if isinstance(valor, time):
            self.hora = valor.replace(second=0, microsecond=0)
        self._pintar_fecha()
        self.app.page.update()

    def inicio_evento(self) -> str:
        momento = datetime.combine(self.dia, self.hora)
        if f.ZONA_HORARIA is not None:
            momento = momento.replace(tzinfo=f.ZONA_HORARIA)
        return momento.isoformat()

    # ------------------------------------------------------------------ buscar lugar

    def abrir_buscador(self, e=None) -> None:
        zona = self.app.config.get("zona", {}).get("nombre", "Osorno")
        self.campo_busqueda = ft.TextField(
            label="Buscar lugar",
            hint_text="Ej: Parque Chuyaca",
            value=(self.campo_lugar.value or "").strip(),
            autofocus=True,
            on_submit=self.buscar,
            expand=True,
        )
        self.resultados = ft.Column([c.suave(f"Busca canchas, plazas o calles de {zona}.")], spacing=4, tight=True)
        self.dialogo_buscador = ft.AlertDialog(
            title=ft.Text("Buscar en el mapa", weight=ft.FontWeight.W_800),
            content=ft.Column(
                [
                    ft.Row([self.campo_busqueda, ft.IconButton(ft.Icons.SEARCH, tooltip="Buscar", on_click=self.buscar)]),
                    self.resultados,
                    ft.Text("Datos de mapas © OpenStreetMap", size=11, color=GRIS),
                ],
                tight=True,
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                width=420,
            ),
            actions=[ft.TextButton("Cerrar", on_click=self.cerrar_buscador)],
        )
        self.app.page.show_dialog(self.dialogo_buscador)

    def cerrar_buscador(self, e=None) -> None:
        self.app.cerrar_dialogo(self.dialogo_buscador)

    async def buscar(self, e=None) -> None:
        consulta = (self.campo_busqueda.value or "").strip()
        if len(consulta) < 3:
            self.resultados.controls = [c.suave("Escribe al menos 3 letras.")]
            self.app.page.update()
            return
        self.resultados.controls = [c.cargando("Buscando…")]
        self.app.page.update()
        lugares = await self.app.llamar(self.api.buscar_lugares, consulta)
        if lugares is None:
            self.resultados.controls = [c.suave("No pudimos buscar ahora. Escribe el lugar a mano.")]
        elif not lugares:
            self.resultados.controls = [c.suave("No encontramos ese lugar. Prueba con otro nombre.")]
        else:
            self.resultados.controls = [
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.PLACE, color=COLOR_PRINCIPAL),
                    title=ft.Text(lugar["nombre"], weight=ft.FontWeight.W_700),
                    subtitle=ft.Text(lugar.get("detalle") or "", size=12),
                    on_click=partial(self.elegir_lugar, lugar),
                )
                for lugar in lugares
            ]
        self.app.page.update()

    def elegir_lugar(self, lugar: dict, e=None) -> None:
        self.campo_lugar.value = (lugar.get("texto") or lugar["nombre"])[: self.app.config.get("largo_lugar", [3, 120])[1]]
        self.lat, self.lng = lugar["lat"], lugar["lng"]
        self.aviso_lugar.visible = False
        self._pintar_ubicacion()
        self.cerrar_buscador()

    # ------------------------------------------------------------------ palabras inapropiadas

    async def _revisar(self, campo: ft.TextField, aviso: ft.Text, que: str) -> None:
        texto = (campo.value or "").strip()
        palabras = await self.app.llamar(self.api.revisar_texto, texto, avisar=False) if texto else []
        if palabras:
            lista = ", ".join(f"«{p}»" for p in palabras)
            aviso.value = f"{que} tiene palabras inapropiadas ({lista}). Cámbialas para poder publicar."
            aviso.visible = True
        else:
            aviso.visible = False
        self.app.page.update()

    async def revisar_titulo(self, e=None) -> None:
        await self._revisar(self.campo_titulo, self.aviso_titulo, "El título")

    async def revisar_lugar(self, e=None) -> None:
        await self._revisar(self.campo_lugar, self.aviso_lugar, "El lugar")

    async def revisar_descripcion(self, e=None) -> None:
        await self._revisar(self.campo_descripcion, self.aviso_descripcion, "Los detalles")

    # ------------------------------------------------------------------ publicar

    def campos(self) -> dict:
        return {
            "titulo": (self.campo_titulo.value or "").strip(),
            "categoria": self.categoria,
            "lugar": (self.campo_lugar.value or "").strip(),
            "lat": self.lat,
            "lng": self.lng,
            "inicio_evento": self.inicio_evento(),
            "personas_actuales": self.actuales.valor,
            "personas_necesarias": self.necesarias.valor,
            "valor": (self.campo_valor.value or "").strip() if self.con_costo else 0,
            "descripcion": (self.campo_descripcion.value or "").strip(),
            "duracion_horas": self.duracion,
        }

    async def publicar(self, e=None) -> None:
        if self.publicando:
            return
        self.publicando = True
        self.boton_publicar.disabled = True
        self.app.page.update()
        try:
            r = await self.app.llamar(self.api.crear_aviso, self.campos())
        finally:
            self.publicando = False
            self.boton_publicar.disabled = False
        if r is None:
            return
        aviso = r["aviso"]
        self.dialogo_publicado = ft.AlertDialog(
            modal=True,
            title=ft.Text("¡Aviso publicado!", weight=ft.FontWeight.W_800),
            content=ft.Text(
                f"«{aviso['titulo']}» ya está en el tablero. Lo verás en tu buzón durante "
                f"{aviso['duracion_horas']} horas, aunque se llene.",
                color=TINTA,
            ),
            actions=[
                ft.TextButton("Volver al tablero", on_click=self.volver_al_tablero),
                ft.TextButton("Ver mi aviso", on_click=partial(self.ver_aviso, aviso["id"]),
                              style=ft.ButtonStyle(color=COLOR_PRINCIPAL)),
            ],
        )
        self.app.page.show_dialog(self.dialogo_publicado)

    async def volver_al_tablero(self, e=None) -> None:
        self.app.cerrar_dialogo(self.dialogo_publicado)
        await self.app.volver()

    async def ver_aviso(self, aviso_id: int, e=None) -> None:
        from .aviso import PantallaAviso

        self.app.cerrar_dialogo(self.dialogo_publicado)
        # El aviso reemplaza a esta pantalla: «atrás» vuelve al tablero.
        await self.app.cambiar(PantallaAviso(self.app, aviso_id))
