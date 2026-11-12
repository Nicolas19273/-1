"""
app.py — Interfaz web de «Falta Uno», escrita 100 % en Python con NiceGUI.

En internet: Render ejecuta `python app.py` (ver README.md y render.yaml).

En tu computador, para probar cambios:
    pip install -r requirements.txt
    python app.py
y abre http://localhost:8080

Toda la lógica (cupos, plazos, base de datos) está en datos.py; este archivo
solo dibuja la página. Para cambiar el diseño más adelante, se edita aquí.

Páginas:
  /             tablero con los avisos abiertos
  /aviso/<id>   detalle de un aviso (para compartir el enlace)
  /buzon        «Mi buzón»: los avisos que publicaste y a los que te uniste
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import tempfile
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Callable

from fastapi import Request
from nicegui import app as servidor
from nicegui import ui
from starlette.middleware.base import BaseHTTPMiddleware

import datos
import filtro

# Render define estas variables; en tu computador no existen.
EN_INTERNET = "RENDER" in os.environ or "PORT" in os.environ
URL_PUBLICA = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

# --------------------------------------------------------------------------- #
# Apariencia
# --------------------------------------------------------------------------- #

COLOR_PRINCIPAL = "#1d6b45"  # verde cancha
FONDO = "#f4f2ec"  # blanco cálido
FUENTE = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
SEGUNDOS_ENTRE_REVISIONES = 3  # cada cuánto se buscan cambios para refrescar

ICONOS = {
    "futbol": "sports_soccer",
    "basquetbol": "sports_basketball",
    "tenis_padel": "sports_tennis",
    "voleibol": "sports_volleyball",
    "juegos_mesa": "casino",
    "videojuegos": "sports_esports",
    "estudio": "menu_book",
    "salida": "celebration",
    "otro": "campaign",
}

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

CIERRES = {
    datos.COMPLETO: ("groups", "¡Grupo completo!", "Ya están todos. Este aviso no recibe más gente."),
    datos.INICIADO: ("event_busy", "El evento ya comenzó", "El aviso se cerró a la hora del evento."),
    datos.VENCIDO: ("timer_off", "Aviso cerrado", "Se cumplió el plazo de {horas} horas."),
}

# Logo: dos personas y un «+1» amarillo (el que falta). Dibujado como SVG
# dentro de Python; se usa en la pestaña del navegador y en el encabezado.
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="fondo" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#145a38"/><stop offset="1" stop-color="#28a862"/>
</linearGradient></defs>
<rect width="64" height="64" rx="16" fill="url(#fondo)"/>
<g fill="#ffffff">
<circle cx="15" cy="24.5" r="6.5"/><path d="M6.7 49a8.3 8.3 0 0 1 16.6 0z"/>
<circle cx="32.5" cy="24.5" r="6.5"/><path d="M24.2 49a8.3 8.3 0 0 1 16.6 0z"/>
</g>
<circle cx="50" cy="36" r="11.5" fill="#ffd23f" stroke="#ffffff" stroke-opacity=".35" stroke-width="2.5"/>
<path d="M50 30.5v11M44.5 36h11" stroke="#0f3d26" stroke-width="3.4" stroke-linecap="round"/>
</svg>"""
LOGO_URL = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()

# Para la pestaña del navegador NiceGUI pide un archivo: lo escribimos al iniciar.
RUTA_FAVICON = Path(tempfile.gettempdir()) / "falta_uno_logo.svg"
RUTA_FAVICON.write_text(LOGO_SVG, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Quién es quién: un identificador al azar por navegador (cookie)
# --------------------------------------------------------------------------- #

COOKIE_IDENTIDAD = "falta_uno_id"
_FORMATO_ID = re.compile(r"^[0-9a-f]{32}$")


class IdentidadNavegador(BaseHTTPMiddleware):
    """
    A cada navegador le da un identificador al azar guardado en una cookie
    (dura un año). Así la página sabe qué avisos publicaste y a cuáles te
    uniste, sin cuentas ni contraseñas.
    """

    async def dispatch(self, request, call_next):
        actual = request.cookies.get(COOKIE_IDENTIDAD, "")
        nuevo = None if _FORMATO_ID.match(actual) else uuid.uuid4().hex
        request.state.persona_id = nuevo or actual
        respuesta = await call_next(request)
        if nuevo:
            respuesta.set_cookie(
                COOKIE_IDENTIDAD,
                nuevo,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="lax",
                secure=EN_INTERNET,
            )
        return respuesta


servidor.add_middleware(IdentidadNavegador)


def persona_de(request: Request) -> str | None:
    return getattr(request.state, "persona_id", None)


# --------------------------------------------------------------------------- #
# Textos
# --------------------------------------------------------------------------- #


def ahora() -> datetime:
    return datetime.now(datos.ZONA_HORARIA)


def texto_fecha_evento(momento: datetime, referencia: datetime) -> str:
    """'Hoy, 20:00' · 'Mañana, 20:00' · 'sáb 14 nov, 20:00'"""
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - referencia.date()).days
    if dias == 0:
        return f"Hoy, {hora}"
    if dias == 1:
        return f"Mañana, {hora}"
    return f"{DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]}, {hora}"


def texto_cuando(momento: datetime, referencia: datetime) -> str:
    """'hoy a las 20:00' · 'mañana a las 20:00' · 'el sáb 14 nov a las 20:00'"""
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - referencia.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    return f"el {DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]} a las {hora}"


def texto_tiempo_restante(hasta: datetime, referencia: datetime) -> str:
    minutos = int((hasta - referencia).total_seconds() // 60)
    if minutos < 1:
        return "Cierra en menos de 1 min"
    horas, mins = divmod(minutos, 60)
    if horas == 0:
        return f"Cierra en {mins} min"
    return f"Cierra en {horas} h {mins:02d} min"


def texto_faltan(cupos: int) -> str:
    if cupos <= 0:
        return "Grupo completo"
    return "Falta 1 persona" if cupos == 1 else f"Faltan {cupos} personas"


def unir_nombres(nombres: list[str], maximo: int = 3) -> str:
    if len(nombres) > maximo:
        return ", ".join(nombres[:maximo]) + f" y {len(nombres) - maximo} más"
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def texto_quienes(aviso: datos.Aviso) -> str:
    partes = [f"Organiza {aviso.creador}"] if aviso.creador else []  # avisos antiguos
    if aviso.participantes:
        verbo = "Se unió" if len(aviso.participantes) == 1 else "Se unieron"
        partes.append(f"{verbo} {unir_nombres(list(aviso.participantes))}")
    else:
        partes.append("Aún no se une nadie por la página")
    return " · ".join(partes)


def firma(avisos: list[datos.Aviso], momento: datetime) -> tuple:
    """Resumen de lo que se ve; si cambia, hay que redibujar."""
    minuto = int(momento.timestamp() // 60)  # para que avance la cuenta regresiva
    return minuto, tuple((a.id, a.ocupados, a.motivo_cierre(momento)) for a in avisos)


# --------------------------------------------------------------------------- #
# Piezas reutilizables
# --------------------------------------------------------------------------- #


def preparar_pagina() -> None:
    ui.colors(primary=COLOR_PRINCIPAL)
    ui.query("body").style(f"background-color: {FONDO}; font-family: {FUENTE}")


def encabezado(persona_id: str | None) -> Callable[[], None]:
    """Logo + botón «Buzón» con contador. Devuelve la función que actualiza el contador."""
    with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
        with ui.row().classes("items-center gap-3 no-wrap cursor-pointer").on(
            "click", lambda: ui.navigate.to("/")
        ):
            ui.image(LOGO_URL).props("no-spinner no-transition").classes("w-12 h-12 shrink-0")
            with ui.column().classes("gap-0"):
                with ui.row().classes("gap-1.5 no-wrap items-baseline"):
                    ui.label("Falta").classes(
                        "text-2xl font-black tracking-tight text-stone-900 leading-none"
                    )
                    ui.label("Uno").classes(
                        "text-2xl font-black tracking-tight text-primary leading-none"
                    )
                ui.label("Avisos para completar el grupo").classes("text-sm text-stone-500")
        with ui.button("Buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
            "unelevated rounded no-caps color=white text-color=grey-9"
        ).classes("shrink-0 border border-stone-300"):
            contador = ui.badge("", color="red").props("floating rounded")

    mostrado: dict = {"n": None}

    def actualizar() -> None:
        me_uni, organizo = datos.mi_buzon(persona_id)
        n = len(me_uni) + len(organizo)
        if n != mostrado["n"]:
            mostrado["n"] = n
            contador.set_text(str(n))
            contador.set_visibility(n > 0)

    actualizar()
    return actualizar


def dato(icono: str, texto: str) -> None:
    with ui.row().classes("items-start gap-2 no-wrap"):
        ui.icon(icono, size="18px").classes("text-stone-400 mt-0.5 shrink-0")
        ui.label(texto).classes("text-stone-700 whitespace-pre-line")


def etiqueta(texto: str, icono: str) -> None:
    with ui.row().classes(
        "items-center gap-1 no-wrap rounded-full bg-green-100 text-green-900 px-2.5 py-0.5 shrink-0"
    ):
        ui.icon(icono, size="14px")
        ui.label(texto).classes("text-xs font-bold whitespace-nowrap")


def barra_cupos(aviso: datos.Aviso) -> None:
    with ui.column().classes("w-full gap-1.5"):
        with ui.row().classes("w-full items-baseline justify-between no-wrap"):
            ui.label(texto_faltan(aviso.cupos_libres)).classes("text-base font-bold text-primary")
            ui.label(f"{aviso.ocupados} de {aviso.personas_necesarias}").classes(
                "text-sm text-stone-500"
            )
        ui.linear_progress(
            value=aviso.ocupados / aviso.personas_necesarias, show_value=False, size="10px"
        ).props("rounded track-color=grey-3")


def fila_persona(inicial: str | None, nombre: str, detalle: str, destacado: bool = False, icono: str | None = None) -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        color = "bg-primary text-white" if destacado else "bg-stone-200 text-stone-700"
        if icono:
            with ui.element("div").classes(
                f"w-9 h-9 rounded-full {color} flex items-center justify-center shrink-0"
            ):
                ui.icon(icono, size="20px")
        else:
            ui.label((inicial or "?")[:1].upper()).classes(
                f"w-9 h-9 rounded-full {color} font-bold flex items-center justify-center shrink-0"
            )
        with ui.column().classes("gap-0"):
            ui.label(nombre).classes("font-semibold text-stone-900 leading-tight")
            ui.label(detalle).classes("text-xs text-stone-500")


def lista_quienes(aviso: datos.Aviso, persona_id: str | None) -> None:
    ui.label("Quiénes van").classes("text-sm font-bold text-stone-700 mt-2")
    n = aviso.personas_actuales
    if aviso.es_de(persona_id):
        detalle = "Tu grupo (te incluye a ti)"
    elif aviso.creador:
        detalle = f"Ya estaban en el grupo · organiza {aviso.creador}"
    else:
        detalle = "Ya estaban en el grupo"
    fila_persona(None, f"{n} persona{'s' if n != 1 else ''}", detalle, icono="groups",
                 destacado=aviso.es_de(persona_id))
    for p in aviso.inscritos:
        soy_yo = bool(persona_id) and p.persona_id == persona_id
        fila_persona(p.nombre, p.nombre + (" (tú)" if soy_yo else ""), "Se unió por Falta Uno", destacado=soy_yo)


def aviso_de_cierre(aviso: datos.Aviso, motivo: str) -> None:
    icono, titulo, texto = CIERRES[motivo]
    fondo = "bg-green-50 border-green-200" if motivo == datos.COMPLETO else "bg-white border-stone-200"
    with ui.row().classes(f"w-full items-center gap-3 no-wrap rounded-2xl border p-4 {fondo}"):
        ui.icon(icono, size="28px").classes("text-primary shrink-0")
        with ui.column().classes("gap-0"):
            ui.label(titulo).classes("font-bold text-stone-900")
            ui.label(texto.format(horas=aviso.duracion_horas)).classes("text-sm text-stone-600")


def estado_en_buzon(aviso: datos.Aviso, momento: datetime, persona_id: str | None) -> None:
    """Recuadro al pie de cada tarjeta del buzón: cómo va y hasta cuándo se ve."""
    if aviso.es_de(persona_id):
        if aviso.esta_lleno:
            principal = "¡Se completó el grupo! 🎉"
        elif aviso.esta_abierto(momento):
            principal = "Buscando gente · " + texto_tiempo_restante(aviso.cierra_en, momento).lower()
        else:
            principal = "Ya no recibe más gente"
        secundario = f"Lo verás aquí hasta {texto_cuando(aviso.expira_en, momento)}."
    else:
        if momento >= aviso.inicio_evento:
            principal = "El evento ya empezó"
        elif aviso.esta_lleno:
            principal = "¡Grupo completo! Nos vemos ahí 🙌"
        else:
            principal = "Estás anotado · todavía " + texto_faltan(aviso.cupos_libres).lower()
        secundario = f"Se quita de tu buzón {texto_cuando(aviso.visible_en_buzon_hasta, momento)}."
    with ui.column().classes("w-full gap-0 rounded-xl bg-stone-50 border border-stone-200 px-4 py-3"):
        ui.label(principal).classes("font-bold text-stone-900")
        ui.label(secundario).classes("text-xs text-stone-500")


def tarjeta_aviso(
    aviso: datos.Aviso,
    momento: datetime,
    persona_id: str | None,
    al_unirse: Callable[[int], None],
    al_salirse: Callable[[int], None],
    modo: str = "tablero",  # "tablero" | "detalle" | "buzon"
) -> None:
    abierto = aviso.esta_abierto(momento)
    mio = aviso.es_de(persona_id)
    anotado = aviso.tiene_inscrito(persona_id)
    puede_salirse = anotado and momento < aviso.inicio_evento

    with ui.card().classes("w-full rounded-2xl shadow-none border border-stone-200 p-5 gap-3"):
        # Categoría y, a la derecha, tu rol o la cuenta regresiva
        with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
            with ui.row().classes("items-center gap-1.5 no-wrap"):
                ui.icon(ICONOS.get(aviso.categoria, "campaign"), size="18px").classes("text-primary")
                ui.label(aviso.nombre_categoria.upper()).classes(
                    "text-xs font-bold tracking-wider text-stone-500"
                )
            if mio:
                etiqueta("Tu aviso", "star")
            elif anotado:
                etiqueta("Anotado", "check")
            elif abierto:
                ui.label(texto_tiempo_restante(aviso.cierra_en, momento)).classes(
                    "text-xs text-stone-500 whitespace-nowrap"
                )

        # Título (fuera del detalle, lleva a la página del aviso)
        titulo = ui.label(aviso.titulo).classes("text-xl font-bold text-stone-900 leading-snug")
        if modo != "detalle":
            titulo.classes("cursor-pointer hover:underline").on(
                "click", lambda: ui.navigate.to(f"/aviso/{aviso.id}")
            )

        # Dónde y cuándo
        with ui.column().classes("gap-1"):
            dato("place", aviso.lugar)
            dato("schedule", texto_fecha_evento(aviso.inicio_evento, momento))

        if aviso.descripcion:
            descripcion = ui.label(aviso.descripcion).classes("text-stone-600 whitespace-pre-line")
            if modo == "tablero":
                descripcion.classes("line-clamp-3")

        barra_cupos(aviso)

        # Quiénes van
        if modo == "tablero":
            ui.label(texto_quienes(aviso)).classes("text-sm text-stone-500")
        else:
            lista_quienes(aviso, persona_id)

        # Pie de la tarjeta
        if modo == "buzon":
            estado_en_buzon(aviso, momento, persona_id)
        elif mio:
            ui.label("Es tu aviso: lo ves en tu buzón aunque se llene.").classes(
                "text-sm font-semibold text-primary"
            )
        elif anotado:
            ui.label("Ya estás anotado: lo tienes en tu buzón.").classes(
                "text-sm font-semibold text-primary"
            )

        if puede_salirse:
            ui.button(
                "Salirme del evento", icon="logout", on_click=partial(al_salirse, aviso.id)
            ).props("flat rounded no-caps dense color=red-8").classes("self-start -ml-1")
        elif not mio and not anotado and abierto and modo != "buzon":
            ui.button("Unirme", icon="person_add", on_click=partial(al_unirse, aviso.id)).props(
                "unelevated rounded no-caps"
            ).classes("w-full mt-1")


# --------------------------------------------------------------------------- #
# Diálogos
# --------------------------------------------------------------------------- #


def abrir_dialogo_unirse(
    aviso_id: int, capa: ui.element, persona_id: str | None, al_cambiar: Callable[[], None]
) -> None:
    aviso = datos.obtener_aviso(aviso_id)
    if aviso is None or not aviso.esta_abierto(ahora()):
        ui.notify("Este aviso ya se cerró.", type="warning", position="top")
        al_cambiar()
        return
    if aviso.es_de(persona_id) or aviso.tiene_inscrito(persona_id):
        ui.notify("Este aviso ya está en tu buzón.", type="info", position="top")
        al_cambiar()
        return

    with capa, ui.dialog() as dialogo, ui.card().classes("rounded-2xl p-0 gap-0").style(
        "width: 460px; max-width: 94vw"
    ):
        cuerpo = ui.column().classes("w-full p-6 gap-4")

    def mostrar_confirmacion(actualizado: datos.Aviso, quien: str) -> None:
        momento = ahora()
        cuerpo.clear()
        with cuerpo:
            ui.icon("check_circle", size="56px").classes("text-primary self-center")
            ui.label(f"¡Listo, {quien}! Estás anotado").classes(
                "text-2xl font-black text-stone-900 text-center w-full leading-tight"
            )
            if actualizado.esta_lleno:
                ui.label("Con eso se completó el grupo 🎉").classes(
                    "text-primary font-bold text-center w-full -mt-2"
                )
            with ui.column().classes("w-full gap-2 rounded-xl bg-stone-50 border border-stone-200 p-4"):
                ui.label(actualizado.titulo).classes("text-lg font-bold text-stone-900 leading-snug")
                dato("place", actualizado.lugar)
                dato("schedule", texto_fecha_evento(actualizado.inicio_evento, momento))
                if actualizado.descripcion:
                    dato("notes", actualizado.descripcion)
                dato(
                    "groups",
                    f"{actualizado.ocupados} de {actualizado.personas_necesarias} · "
                    f"{texto_faltan(actualizado.cupos_libres)}",
                )
            ui.label("Lo guardamos en tu buzón 📬 para que no se te olvide dónde y cuándo es.").classes(
                "text-sm text-stone-600 text-center w-full"
            )
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Listo", on_click=dialogo.close).props(
                    "flat rounded no-caps color=grey-8"
                ).classes("flex-1")
                ui.button("Ver mi buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
                    "unelevated rounded no-caps"
                ).classes("flex-1")

    def confirmar() -> None:
        try:
            actualizado = datos.unirse(aviso_id, nombre.value, persona_id=persona_id)
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            vigente = datos.obtener_aviso(aviso_id)
            if (
                vigente is None
                or not vigente.esta_abierto(ahora())
                or vigente.es_de(persona_id)
                or vigente.tiene_inscrito(persona_id)
            ):
                dialogo.close()
                al_cambiar()
            return
        al_cambiar()
        mostrar_confirmacion(actualizado, datos.limpiar(nombre.value))

    with cuerpo:
        ui.label("Te vas a unir a").classes("text-sm text-stone-500")
        ui.label(aviso.titulo).classes("text-xl font-bold text-stone-900 leading-snug -mt-3")
        with ui.column().classes("gap-1"):
            dato("place", aviso.lugar)
            dato("schedule", texto_fecha_evento(aviso.inicio_evento, ahora()))
        ui.label(texto_faltan(aviso.cupos_libres)).classes("font-bold text-primary")

        nombre = ui.input(
            "Tu nombre", placeholder="Ej: Pedro Soto", value=datos.nombre_usado(persona_id)
        ).props(f"outlined autofocus maxlength={datos.LARGO_NOMBRE[1]}").classes("w-full")
        nombre.on("keydown.enter", confirmar)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=dialogo.close).props("flat no-caps color=grey-8")
            ui.button("Confirmar", icon="check", on_click=confirmar).props(
                "unelevated rounded no-caps"
            )

    dialogo.on("hide", dialogo.delete)  # se borra al cerrarse
    dialogo.open()


def abrir_dialogo_salirse(
    aviso_id: int, capa: ui.element, persona_id: str | None, al_cambiar: Callable[[], None]
) -> None:
    aviso = datos.obtener_aviso(aviso_id)
    if aviso is None or not aviso.tiene_inscrito(persona_id):
        ui.notify("Ya no estás anotado en este aviso.", type="info", position="top")
        al_cambiar()
        return

    def confirmar() -> None:
        try:
            actualizado = datos.salirse(aviso_id, persona_id)
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            dialogo.close()
            al_cambiar()
            return
        dialogo.close()
        if actualizado.esta_abierto(ahora()):
            mensaje = f"Te saliste de «{actualizado.titulo}». El aviso volvió a abrirse para que otra persona tome tu lugar."
        else:
            mensaje = f"Te saliste de «{actualizado.titulo}». Tu cupo quedó libre."
        ui.notify(mensaje, type="info", position="top", multi_line=True)
        al_cambiar()

    with capa, ui.dialog() as dialogo, ui.card().classes("rounded-2xl p-6 gap-4").style(
        "width: 420px; max-width: 94vw"
    ):
        ui.icon("logout", size="40px").classes("text-red-700 self-center")
        ui.label("¿Salirte de este evento?").classes(
            "text-xl font-black text-stone-900 text-center w-full"
        )
        ui.label(aviso.titulo).classes("font-bold text-stone-700 text-center w-full -mt-3")
        ui.label(
            "Tu cupo quedará libre. Si el aviso sigue dentro de su plazo, vuelve a aparecer "
            "en el tablero para que otra persona lo tome. También se quitará de tu buzón."
        ).classes("text-sm text-stone-600 text-center w-full")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("No, me quedo", on_click=dialogo.close).props(
                "flat rounded no-caps color=grey-8"
            ).classes("flex-1")
            ui.button("Sí, salirme", on_click=confirmar).props(
                "unelevated rounded no-caps color=red-8"
            ).classes("flex-1")

    dialogo.on("hide", dialogo.delete)
    dialogo.open()


def abrir_dialogo_crear(
    capa: ui.element, base_url: str, persona_id: str | None, al_cambiar: Callable[[], None]
) -> None:
    momento = ahora()
    sugerida = (momento + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    with capa, ui.dialog().props("persistent") as dialogo, ui.card().classes(
        "rounded-2xl p-0 gap-0"
    ).style("width: 540px; max-width: 94vw"):
        cuerpo = ui.column().classes("w-full p-6 gap-4")

    def actualizar_resumen() -> None:
        actuales, necesarias = campo_actuales.value, campo_necesarias.value
        if actuales and necesarias and necesarias > actuales:
            faltan = int(necesarias - actuales)
            resumen.text = f"Buscan {faltan} persona{'s' if faltan != 1 else ''} más."
        else:
            resumen.text = ""

    def publicar() -> None:
        try:
            inicio = datos.armar_fecha_hora(campo_fecha.value, campo_hora.value)
            aviso = datos.crear_aviso(
                titulo=campo_titulo.value,
                categoria=campo_categoria.value,
                lugar=campo_lugar.value,
                inicio_evento=inicio,
                personas_actuales=campo_actuales.value,
                personas_necesarias=campo_necesarias.value,
                duracion_horas=campo_duracion.value,
                descripcion=campo_descripcion.value,
                creador_id=persona_id,
            )
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            return
        al_cambiar()
        mostrar_exito(aviso)
        if any(filtro.contiene(c.value) for c in (campo_titulo, campo_lugar, campo_descripcion)):
            ui.notify(
                "Algunas palabras inapropiadas se taparon con ****.",
                type="warning",
                position="top",
            )

    def mostrar_exito(aviso: datos.Aviso) -> None:
        enlace = f"{base_url}/aviso/{aviso.id}"
        tablero = "se completa el grupo"
        if aviso.cierra_en < aviso.expira_en:
            tablero += " o llega la hora del evento"
        cuerpo.clear()
        with cuerpo:
            ui.icon("check_circle", size="56px").classes("text-primary self-center")
            ui.label("¡Aviso publicado!").classes(
                "text-2xl font-black text-stone-900 text-center w-full"
            )
            ui.label(
                f"Lo verás en tu buzón 📬 durante {aviso.duracion_horas} horas, aunque se llene. "
                f"Del tablero público sale cuando {tablero}."
            ).classes("text-stone-600 text-center w-full -mt-2")
            ui.label("Compártelo por WhatsApp o donde quieras:").classes(
                "text-sm font-semibold text-stone-700 mt-2"
            )
            ui.input(value=enlace).props("outlined dense readonly").classes("w-full")
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Listo", on_click=dialogo.close).props(
                    "flat rounded no-caps color=grey-8"
                ).classes("flex-1")
                ui.button("Ver mi buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
                    "unelevated rounded no-caps"
                ).classes("flex-1")

    with cuerpo:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Nuevo aviso").classes("text-2xl font-black text-stone-900")
            ui.button(icon="close", on_click=dialogo.close).props("flat round dense color=grey-7")

        campo_titulo = ui.input(
            "Título", placeholder="Ej: Pichanga 7 vs 7, falta uno"
        ).props(f"outlined maxlength={datos.LARGO_TITULO[1]}").classes("w-full")

        campo_categoria = ui.select(datos.CATEGORIAS, label="Categoría", value="futbol").props(
            "outlined"
        ).classes("w-full")

        campo_lugar = ui.input("Lugar", placeholder="Ej: Cancha 3, Parque O'Higgins").props(
            f"outlined maxlength={datos.LARGO_LUGAR[1]}"
        ).classes("w-full")

        with ui.row().classes("w-full gap-3 no-wrap"):
            campo_fecha = ui.input("Fecha", value=sugerida.strftime("%Y-%m-%d")).props(
                f"outlined stack-label type=date min={momento:%Y-%m-%d}"
            ).classes("flex-1")
            campo_hora = ui.input("Hora", value=sugerida.strftime("%H:%M")).props(
                "outlined stack-label type=time"
            ).classes("flex-1")

        with ui.row().classes("w-full gap-3 no-wrap"):
            campo_actuales = ui.number(
                "¿Cuántos son?",
                placeholder="Ej: 9",
                min=1,
                max=datos.MAX_PERSONAS - 1,
                step=1,
                format="%d",
                on_change=actualizar_resumen,
            ).props("outlined").classes("flex-1")
            campo_necesarias = ui.number(
                "¿Cuántos necesitan?",
                placeholder="Ej: 10",
                min=2,
                max=datos.MAX_PERSONAS,
                step=1,
                format="%d",
                on_change=actualizar_resumen,
            ).props("outlined").classes("flex-1")
        resumen = ui.label("").classes("text-sm font-semibold text-primary -mt-2")

        campo_descripcion = ui.textarea(
            "Detalles (opcional)",
            placeholder="Ej: Se paga la cancha entre todos. Traer polera oscura.",
        ).props(f"outlined autogrow maxlength={datos.LARGO_MAX_DESCRIPCION}").classes("w-full")

        ui.label("¿Cuánto dura el aviso?").classes("text-sm font-semibold text-stone-700")
        campo_duracion = ui.toggle({24: "24 horas", 48: "48 horas"}, value=24).props(
            "spread no-caps unelevated rounded toggle-color=primary color=grey-3 text-color=grey-9"
        ).classes("w-full")
        ui.label(
            "En el tablero se cierra antes si se completa el grupo o llega la hora del evento. "
            "En tu buzón lo verás durante todo el plazo."
        ).classes("text-xs text-stone-500 -mt-2")

        ui.button("Publicar aviso", icon="campaign", on_click=publicar).props(
            "unelevated rounded no-caps size=lg"
        ).classes("w-full mt-2")

    dialogo.on("hide", dialogo.delete)
    dialogo.open()


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #


@ui.page("/", title="Falta Uno")
def pagina_inicio(request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    base_url = URL_PUBLICA or str(request.base_url).rstrip("/")
    capa = ui.element("div")  # los diálogos viven aquí, fuera de la lista que se redibuja
    estado: dict = {"categoria": None, "firma": None}

    def refrescar() -> None:
        lista.refresh()
        actualizar_contador()

    def elegir_categoria(clave: str | None) -> None:
        estado["categoria"] = clave
        lista.refresh()

    def chip(texto: str, cantidad: int, activo: bool, al_tocar, icono: str | None = None) -> None:
        estilo = "color=primary" if activo else "color=white text-color=grey-9"
        ui.button(f"{texto} · {cantidad}", icon=icono, on_click=al_tocar).props(
            f"unelevated rounded no-caps {estilo}"
        ).classes("shrink-0 border border-stone-300 px-3")

    al_unirse = partial(abrir_dialogo_unirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_salirse = partial(abrir_dialogo_salirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

    @ui.refreshable
    def lista() -> None:
        momento = ahora()
        activos = datos.avisos_activos(momento)
        estado["firma"] = firma(activos, momento)

        elegida = estado["categoria"]
        visibles = [a for a in activos if elegida in (None, a.categoria)]

        if activos or elegida:
            conteo = Counter(a.categoria for a in activos)
            with ui.row().classes("w-full gap-2 no-wrap overflow-x-auto pb-1"):
                chip("Todos", len(activos), elegida is None, partial(elegir_categoria, None))
                for clave, nombre in datos.CATEGORIAS.items():
                    if conteo[clave] or clave == elegida:
                        chip(
                            nombre,
                            conteo[clave],
                            clave == elegida,
                            partial(elegir_categoria, clave),
                            ICONOS[clave],
                        )

        if not visibles:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.image(LOGO_URL).props("no-spinner no-transition").classes("w-16 h-16 opacity-80")
                if elegida:
                    ui.label(f"No hay avisos abiertos de {datos.CATEGORIAS[elegida]}").classes(
                        "text-lg font-bold text-stone-700"
                    )
                else:
                    ui.label("No hay avisos abiertos").classes("text-lg font-bold text-stone-700")
                ui.label("Toca el botón + para publicar uno.").classes("text-stone-500")
            return

        for aviso in visibles:
            tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse)

    def revisar_cambios() -> None:
        momento = ahora()
        if firma(datos.avisos_activos(momento), momento) != estado["firma"]:
            lista.refresh()
        actualizar_contador()

    with ui.column().classes("w-full max-w-2xl mx-auto px-4 pt-6 pb-32 gap-5"):
        actualizar_contador = encabezado(persona_id)
        lista()

    with ui.page_sticky(position="bottom-right", x_offset=20, y_offset=20):
        ui.button(
            icon="add", on_click=lambda: abrir_dialogo_crear(capa, base_url, persona_id, refrescar)
        ).props("fab color=primary").tooltip("Publicar un aviso")

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


@ui.page("/aviso/{aviso_id}", title="Falta Uno · Aviso")
def pagina_aviso(aviso_id: int, request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    capa = ui.element("div")
    estado: dict = {"firma": None}

    def refrescar() -> None:
        contenido.refresh()
        actualizar_contador()

    al_unirse = partial(abrir_dialogo_unirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_salirse = partial(abrir_dialogo_salirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

    def leer() -> tuple[datos.Aviso | None, tuple | None]:
        momento = ahora()
        aviso = datos.obtener_aviso(aviso_id)
        return aviso, (firma([aviso], momento) if aviso else None)

    @ui.refreshable
    def contenido() -> None:
        momento = ahora()
        aviso, estado["firma"] = leer()

        if aviso is None:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.icon("search_off", size="48px").classes("text-stone-300")
                ui.label("Este aviso no existe").classes("text-lg font-bold text-stone-700")
            return

        motivo = aviso.motivo_cierre(momento)
        if motivo:
            aviso_de_cierre(aviso, motivo)
        tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, modo="detalle")

    def revisar_cambios() -> None:
        if leer()[1] != estado["firma"]:
            contenido.refresh()
        actualizar_contador()

    with ui.column().classes("w-full max-w-2xl mx-auto px-4 pt-6 pb-16 gap-4"):
        actualizar_contador = encabezado(persona_id)
        ui.button("Ver todos los avisos", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
            "flat no-caps dense color=grey-8"
        ).classes("self-start")
        contenido()

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


@ui.page("/buzon", title="Falta Uno · Mi buzón")
def pagina_buzon(request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    capa = ui.element("div")
    estado: dict = {"firma": None}

    def refrescar() -> None:
        contenido.refresh()
        actualizar_contador()

    al_unirse = partial(abrir_dialogo_unirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_salirse = partial(abrir_dialogo_salirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

    def leer() -> tuple[list[datos.Aviso], list[datos.Aviso], tuple]:
        momento = ahora()
        me_uni, organizo = datos.mi_buzon(persona_id, momento)
        return me_uni, organizo, (firma(me_uni, momento), firma(organizo, momento))

    def seccion(titulo: str, explicacion: str, icono: str) -> None:
        with ui.row().classes("w-full items-center gap-2 no-wrap mt-2"):
            ui.icon(icono, size="22px").classes("text-primary")
            ui.label(titulo).classes("text-lg font-black text-stone-900")
        ui.label(explicacion).classes("text-sm text-stone-500 -mt-3")

    @ui.refreshable
    def contenido() -> None:
        momento = ahora()
        me_uni, organizo, estado["firma"] = leer()

        if not me_uni and not organizo:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.icon("inbox", size="56px").classes("text-stone-300")
                ui.label("Tu buzón está vacío").classes("text-lg font-bold text-stone-700")
                ui.label(
                    "Cuando te unas a un evento o publiques uno, aparecerá aquí con todos sus detalles."
                ).classes("text-stone-500 max-w-sm")
                ui.button("Ver avisos abiertos", on_click=lambda: ui.navigate.to("/")).props(
                    "unelevated rounded no-caps"
                ).classes("mt-2")
            return

        if me_uni:
            seccion(
                "Me uní",
                "Dónde y cuándo es cada evento. Se quitan solos unas horas después de que empiezan.",
                "event_available",
            )
            for aviso in me_uni:
                tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, modo="buzon")

        if organizo:
            seccion(
                "Mis avisos",
                "Los que publicaste. Siguen aquí aunque se llenen, hasta que termina su plazo.",
                "campaign",
            )
            for aviso in organizo:
                tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, modo="buzon")

    def revisar_cambios() -> None:
        if leer()[2] != estado["firma"]:
            contenido.refresh()
        actualizar_contador()

    with ui.column().classes("w-full max-w-2xl mx-auto px-4 pt-6 pb-16 gap-4"):
        actualizar_contador = encabezado(persona_id)
        ui.button("Ver todos los avisos", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
            "flat no-caps dense color=grey-8"
        ).classes("self-start")
        ui.label("Mi buzón").classes("text-3xl font-black tracking-tight text-stone-900")
        contenido()
        ui.label(
            "Tu buzón se guarda en este navegador. Si abres la página en otro teléfono, "
            "en modo incógnito o borras las cookies, no verás estos eventos ahí."
        ).classes("text-xs text-stone-400 text-center w-full mt-6")

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #

@servidor.get("/salud")
def salud() -> dict:
    """Respuesta liviana para saber si el servidor está despierto (no usa la BD)."""
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Despertador: evita que Render duerma la página
#
# Render gratis duerme la página si pasan 15 minutos sin visitas. Mientras
# está despierta, la propia app se visita cada 10 minutos por su dirección
# pública. (Si aun así llegara a dormirse, la despierta el despertador
# externo de cron-job.org: ver README.md.)
# --------------------------------------------------------------------------- #

MINUTOS_ENTRE_VISITAS = 10
_tareas_de_fondo: set[asyncio.Task] = set()


def tocar_puerta() -> int:
    """Visita /salud por internet, como lo haría cualquier persona."""
    pedido = urllib.request.Request(
        f"{URL_PUBLICA}/salud", headers={"User-Agent": "falta-uno-despertador"}
    )
    with urllib.request.urlopen(pedido, timeout=30) as respuesta:
        return respuesta.status


async def despertador() -> None:
    while True:
        await asyncio.sleep(MINUTOS_ENTRE_VISITAS * 60)
        try:
            estado = await asyncio.to_thread(tocar_puerta)
            print(f"[despertador] visita a /salud: {estado}", flush=True)
        except Exception as error:  # un fallo puntual no debe detener la app
            print(f"[despertador] no se pudo visitar /salud: {error}", flush=True)


def iniciar_despertador() -> None:
    if not URL_PUBLICA:  # en tu computador no hace falta
        return
    tarea = asyncio.get_running_loop().create_task(despertador())
    _tareas_de_fondo.add(tarea)  # guardar la referencia para que no se pierda
    print(f"[despertador] activo: {URL_PUBLICA}/salud cada {MINUTOS_ENTRE_VISITAS} min", flush=True)


servidor.on_startup(iniciar_despertador)


datos.inicializar()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Falta Uno",
        favicon=str(RUTA_FAVICON),  # ícono de la pestaña del navegador
        language="es",
        host="0.0.0.0",  # acepta visitas desde fuera del servidor
        port=int(os.environ.get("PORT", 8080)),
        reload=not EN_INTERNET,  # en tu PC se recarga sola al editar
        show=not EN_INTERNET,  # en tu PC abre el navegador
    )
