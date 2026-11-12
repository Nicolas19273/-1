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
  /admin        panel de administración (solo con la clave CLAVE_ADMIN)
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import os
import re
import tempfile
import time
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
    datos.CANCELADO: ("event_busy", "Aviso cancelado", "Este aviso fue eliminado. El evento ya no se realiza."),
    datos.COMPLETO: ("groups", "¡Grupo completo!", "Ya están todos. Este aviso no recibe más gente."),
    datos.INICIADO: ("sports", "El evento ya comenzó", "El aviso se cerró a la hora del evento."),
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

# Marca en rojo el campo mientras se escribe si tiene palabras inapropiadas.
SIN_GROSERIAS = {"Tiene palabras inapropiadas: cámbialas para poder publicar.": lambda v: not filtro.contiene(v)}
NOMBRE_SIN_GROSERIAS = {"Ese nombre no está permitido. Usa tu nombre real o un apodo amable.": lambda v: not filtro.contiene(v)}

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


def etiqueta(texto: str, icono: str, rojo: bool = False) -> None:
    colores = "bg-red-100 text-red-900" if rojo else "bg-green-100 text-green-900"
    with ui.row().classes(
        f"items-center gap-1 no-wrap rounded-full {colores} px-2.5 py-0.5 shrink-0"
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
    elif aviso.cancelado:
        if aviso.cancelado_por == "admin":
            principal = "Cancelado por la administración 🚫"
        else:
            principal = "Cancelado por quien lo publicó 🚫"
        secundario = "Este evento ya no se realiza. Puedes quitarlo de tu buzón."
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
    al_eliminar: Callable[[int], None],
    modo: str = "tablero",  # "tablero" | "detalle" | "buzon"
) -> None:
    abierto = aviso.esta_abierto(momento)
    mio = aviso.es_de(persona_id)
    anotado = aviso.tiene_inscrito(persona_id)
    puede_salirse = anotado and (aviso.cancelado or momento < aviso.inicio_evento)

    with ui.card().classes("w-full rounded-2xl shadow-none border border-stone-200 p-5 gap-3"):
        # Categoría y, a la derecha, tu rol o la cuenta regresiva
        with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
            with ui.row().classes("items-center gap-1.5 no-wrap"):
                ui.icon(ICONOS.get(aviso.categoria, "campaign"), size="18px").classes("text-primary")
                ui.label(aviso.nombre_categoria.upper()).classes(
                    "text-xs font-bold tracking-wider text-stone-500"
                )
            if aviso.cancelado:
                etiqueta("Cancelado", "block", rojo=True)
            elif mio:
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
        elif aviso.cancelado:
            pass  # el recuadro de "Aviso cancelado" ya lo explica
        elif mio:
            ui.label("Es tu aviso: lo ves en tu buzón aunque se llene.").classes(
                "text-sm font-semibold text-primary"
            )
        elif anotado:
            ui.label("Ya estás anotado: lo tienes en tu buzón.").classes(
                "text-sm font-semibold text-primary"
            )

        if mio and not aviso.cancelado:
            ui.button(
                "Eliminar aviso", icon="delete_outline", on_click=partial(al_eliminar, aviso.id)
            ).props("flat rounded no-caps dense color=red-8").classes("self-start -ml-1")
        elif puede_salirse:
            texto = "Quitar de mi buzón" if aviso.cancelado else "Salirme del evento"
            ui.button(texto, icon="logout", on_click=partial(al_salirse, aviso.id)).props(
                "flat rounded no-caps dense color=red-8"
            ).classes("self-start -ml-1")
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
            "Tu nombre",
            placeholder="Ej: Pedro Soto",
            value=datos.nombre_usado(persona_id),
            validation=NOMBRE_SIN_GROSERIAS,
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
    if aviso.cancelado:  # solo quitarlo del buzón: no hace falta preguntar
        try:
            datos.salirse(aviso_id, persona_id)
            ui.notify("Lo quitamos de tu buzón.", type="info", position="top")
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
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


def abrir_dialogo_eliminar(
    aviso_id: int,
    capa: ui.element,
    persona_id: str | None,
    al_cambiar: Callable[[], None],
    al_terminar: Callable[[], None] | None = None,
    como_admin: bool = False,
) -> None:
    aviso = datos.obtener_aviso(aviso_id)
    permitido = aviso is not None and (
        aviso.es_de(persona_id) or (como_admin and datos.es_admin(persona_id))
    )
    if not permitido or aviso.cancelado:
        ui.notify("Este aviso ya no se puede eliminar.", type="info", position="top")
        al_cambiar()
        return

    def confirmar() -> None:
        try:
            datos.eliminar_aviso(aviso_id, persona_id, como_admin=como_admin)
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            dialogo.close()
            al_cambiar()
            return
        dialogo.close()
        ui.notify(f"Eliminaste «{aviso.titulo}».", type="info", position="top")
        al_cambiar()
        if al_terminar:
            al_terminar()

    n = len(aviso.inscritos)
    if n:
        consecuencia = (
            f"{'La persona que se unió verá' if n == 1 else f'Las {n} personas que se unieron verán'} "
            "en su buzón que el evento se canceló."
        )
    else:
        consecuencia = "Nadie se ha unido todavía."

    with capa, ui.dialog() as dialogo, ui.card().classes("rounded-2xl p-6 gap-4").style(
        "width: 420px; max-width: 94vw"
    ):
        ui.icon("delete_outline", size="40px").classes("text-red-700 self-center")
        ui.label("¿Eliminar este aviso?").classes(
            "text-xl font-black text-stone-900 text-center w-full"
        )
        ui.label(aviso.titulo).classes("font-bold text-stone-700 text-center w-full -mt-3")
        donde = "del tablero y de tu buzón" if aviso.es_de(persona_id) else "del tablero y del buzón de su dueño"
        ui.label(f"Desaparecerá {donde}. {consecuencia} No se puede deshacer.").classes(
            "text-sm text-stone-600 text-center w-full"
        )
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("No, mantenerlo", on_click=dialogo.close).props(
                "flat rounded no-caps color=grey-8"
            ).classes("flex-1")
            ui.button("Sí, eliminar", on_click=confirmar).props(
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
            ui.button(
                "¿Te equivocaste? Eliminar este aviso",
                icon="delete_outline",
                on_click=lambda: abrir_dialogo_eliminar(
                    aviso.id, capa, persona_id, al_cambiar, al_terminar=dialogo.close
                ),
            ).props("flat rounded no-caps dense color=red-8").classes("self-center")

    with cuerpo:
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            ui.label("Nuevo aviso").classes("text-2xl font-black text-stone-900")
            ui.button(icon="close", on_click=dialogo.close).props("flat round dense color=grey-7")

        campo_titulo = ui.input(
            "Título", placeholder="Ej: Pichanga 7 vs 7, falta uno", validation=SIN_GROSERIAS
        ).props(f"outlined maxlength={datos.LARGO_TITULO[1]}").classes("w-full")

        campo_categoria = ui.select(datos.CATEGORIAS, label="Categoría", value="futbol").props(
            "outlined"
        ).classes("w-full")

        campo_lugar = ui.input(
            "Lugar", placeholder="Ej: Cancha 3, Parque O'Higgins", validation=SIN_GROSERIAS
        ).props(
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
            validation=SIN_GROSERIAS,
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
    al_eliminar = partial(abrir_dialogo_eliminar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

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
            tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar)

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
    al_eliminar = partial(abrir_dialogo_eliminar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

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
        tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, modo="detalle")

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
    al_eliminar = partial(abrir_dialogo_eliminar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

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
                tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, modo="buzon")

        if organizo:
            seccion(
                "Mis avisos",
                "Los que publicaste. Siguen aquí aunque se llenen, hasta que termina su plazo.",
                "campaign",
            )
            for aviso in organizo:
                tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, modo="buzon")

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
# Panel de administración (/admin): solo para quien administra la página
#
# Se activa creando en Render la variable de entorno CLAVE_ADMIN (ver README).
# Quien escribe la clave correcta queda como administrador en ese navegador
# hasta que cierre la sesión. La dirección /admin no aparece en ningún botón.
# --------------------------------------------------------------------------- #

CLAVE_ADMIN = os.environ.get("CLAVE_ADMIN", "")
MAX_INTENTOS = 5  # intentos fallidos permitidos…
MINUTOS_BLOQUEO = 15  # …cada tantos minutos, por dirección IP
_intentos_fallidos: dict[str, list[float]] = {}


def clave_correcta(clave: str | None) -> bool:
    return bool(CLAVE_ADMIN) and hmac.compare_digest((clave or "").encode(), CLAVE_ADMIN.encode())


def _demasiados_intentos(quien: str) -> bool:
    limite = time.time() - MINUTOS_BLOQUEO * 60
    recientes = [t for t in _intentos_fallidos.get(quien, []) if t > limite]
    _intentos_fallidos[quien] = recientes
    return len(recientes) >= MAX_INTENTOS


def _anotar_intento_fallido(quien: str) -> None:
    _intentos_fallidos.setdefault(quien, []).append(time.time())


ESTADOS_ADMIN = {
    None: "Abierto",
    datos.COMPLETO: "Completo",
    datos.INICIADO: "Ya empezó",
    datos.VENCIDO: "Plazo cumplido",
}


def tarjeta_simple() -> ui.card:
    return ui.card().classes("w-full rounded-2xl shadow-none border border-stone-200 p-5 gap-3")


@ui.page("/admin", title="Falta Uno · Administración")
def pagina_admin(request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    cliente = getattr(request, "client", None)
    ip = getattr(cliente, "host", None) or "desconocida"
    capa = ui.element("div")

    with ui.column().classes("w-full max-w-3xl mx-auto px-4 pt-6 pb-16 gap-4"):
        encabezado(persona_id)
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.icon("admin_panel_settings", size="30px").classes("text-primary")
            ui.label("Administración").classes("text-3xl font-black tracking-tight text-stone-900")

        if not CLAVE_ADMIN:
            with tarjeta_simple():
                ui.label("El panel está desactivado").classes("text-lg font-bold text-stone-900")
                ui.label(
                    "Para activarlo, en Render entra a tu servicio → Environment → Add Environment "
                    "Variable, crea CLAVE_ADMIN con una clave larga que solo tú conozcas y guarda. "
                    "Render reinicia la página solo."
                ).classes("text-stone-600")
            return

        if not datos.es_admin(persona_id):
            _formulario_ingreso(persona_id, ip)
            return

        _panel(persona_id, capa)


def _formulario_ingreso(persona_id: str | None, ip: str) -> None:
    with tarjeta_simple():
        ui.label("Esta sección es solo para quien administra la página.").classes("text-stone-600")
        clave = ui.input("Clave de administración", password=True, password_toggle_button=True).props(
            "outlined autofocus"
        ).classes("w-full")

        def entrar() -> None:
            if _demasiados_intentos(ip):
                ui.notify(
                    f"Demasiados intentos. Espera {MINUTOS_BLOQUEO} minutos.", type="negative", position="top"
                )
                return
            if not clave_correcta(clave.value):
                _anotar_intento_fallido(ip)
                ui.notify("Clave incorrecta.", type="negative", position="top")
                return
            try:
                datos.agregar_admin(persona_id)
            except datos.ErrorValidacion as error:
                ui.notify(str(error), type="negative", position="top")
                return
            ui.navigate.to("/admin")

        clave.on("keydown.enter", entrar)
        ui.button("Entrar", icon="login", on_click=entrar).props("unelevated rounded no-caps").classes(
            "self-end"
        )


def _panel(persona_id: str | None, capa: ui.element) -> None:
    def sigo_siendo_admin() -> bool:
        if datos.es_admin(persona_id):
            return True
        ui.notify("Tu sesión de administración se cerró.", type="warning", position="top")
        ui.navigate.to("/admin")
        return False

    with ui.tabs().classes("w-full") as pestanas:
        p_resumen = ui.tab("Resumen", icon="insights")
        p_palabras = ui.tab("Palabras", icon="spellcheck")
        p_bloqueados = ui.tab("Bloqueados", icon="block")
        p_avisos = ui.tab("Avisos", icon="campaign")

    with ui.tab_panels(pestanas, value=p_resumen).classes("w-full bg-transparent"):
        # ------------------------------------------------------------ Resumen
        with ui.tab_panel(p_resumen).classes("px-0 gap-4"):

            @ui.refreshable
            def cifras() -> None:
                c = datos.estadisticas()
                tarjetas = [
                    ("Avisos abiertos ahora", c["abiertos"], "campaign"),
                    ("Publicados (7 días)", c["publicados_7d"], "add_circle_outline"),
                    ("Personas unidas (7 días)", c["unidos_7d"], "group_add"),
                    ("Bloqueos del filtro (7 días)", c["bloqueos_7d"], "block"),
                    ("Avisos eliminados (7 días)", c["cancelados_7d"], "delete_outline"),
                    ("Reglas propias del filtro", c["reglas"], "spellcheck"),
                ]
                with ui.row().classes("w-full gap-3"):
                    for titulo, valor, icono in tarjetas:
                        with ui.card().classes(
                            "rounded-2xl shadow-none border border-stone-200 p-4 gap-1"
                        ).style("flex: 1 1 150px; min-width: 150px"):
                            ui.icon(icono, size="22px").classes("text-primary")
                            ui.label(str(valor)).classes("text-3xl font-black text-stone-900 leading-none")
                            ui.label(titulo).classes("text-xs text-stone-500")
                ui.label(f"Avisos publicados desde el comienzo: {c['avisos_total']}").classes(
                    "text-sm text-stone-500"
                )

            cifras()

            def cerrar_sesion() -> None:
                datos.quitar_admin(persona_id)
                ui.navigate.to("/admin")

            def cerrar_todas() -> None:
                n = datos.quitar_todos_los_admin()
                ui.notify(f"Se cerraron {n} sesiones de administración.", type="info", position="top")
                ui.navigate.to("/admin")

            with ui.row().classes("w-full justify-between"):
                ui.button("Actualizar", icon="refresh", on_click=cifras.refresh).props(
                    "flat rounded no-caps color=grey-9"
                )
                ui.button("Cerrar sesión de administración", icon="logout", on_click=cerrar_sesion).props(
                    "flat rounded no-caps color=red-8"
                )
            ui.button(
                "Cerrar la sesión de administración en todos los navegadores",
                icon="phonelink_lock",
                on_click=cerrar_todas,
            ).props("flat rounded no-caps dense color=red-8").classes("self-end")
            ui.label(
                "Úsalo si entraste desde un computador ajeno o si cambiaste la clave."
            ).classes("text-xs text-stone-400 self-end -mt-3")

        # ------------------------------------------------------------ Palabras
        with ui.tab_panel(p_palabras).classes("px-0 gap-4"):
            with tarjeta_simple():
                ui.label("Agregar palabra o frase al filtro").classes("text-lg font-bold text-stone-900")
                ui.label(
                    "Se aplica al instante en toda la página, sin volver a publicar el código."
                ).classes("text-sm text-stone-500 -mt-2")
                campo_palabra = ui.input("Palabra o frase", placeholder="Ej: pico").props(
                    f"outlined maxlength={datos.LARGO_MAX_REGLA}"
                ).classes("w-full")
                modo = ui.toggle(
                    {"contexto": "Solo en contexto inadecuado", "siempre": "Siempre"},
                    value="contexto",
                    on_change=lambda: campo_cerca.set_visibility(modo.value == "contexto"),
                ).props("spread no-caps unelevated rounded toggle-color=primary color=grey-3 text-color=grey-9").classes(
                    "w-full"
                )
                campo_cerca = ui.input(
                    "Se filtra si aparece cerca de… (separa con comas)",
                    placeholder="Ej: chupa, chupen, mi, tu",
                ).props("outlined").classes("w-full")
                campo_excepto = ui.input(
                    "Nunca se filtra en… (opcional, separa con comas)",
                    placeholder="Ej: y pico, pico de",
                ).props("outlined").classes("w-full")
                ui.label(
                    f"«Cerca» significa hasta {filtro.VENTANA} palabras antes o después. "
                    "Las excepciones siempre ganan. Mayúsculas, tildes y trucos como p1c0 se detectan igual."
                ).classes("text-xs text-stone-500")

                def agregar() -> None:
                    if not sigo_siendo_admin():
                        return
                    en_contexto = modo.value == "contexto"
                    if en_contexto and not [p for p in (campo_cerca.value or "").split(",") if p.strip()]:
                        ui.notify(
                            "Escribe al menos una palabra de contexto, o elige «Siempre».",
                            type="negative",
                            position="top",
                        )
                        return
                    try:
                        regla = datos.agregar_regla(
                            campo_palabra.value,
                            cerca_de=campo_cerca.value if en_contexto else "",
                            excepto=campo_excepto.value,
                        )
                    except datos.ErrorValidacion as error:
                        ui.notify(str(error), type="negative", position="top")
                        return
                    ui.notify(f"«{regla.palabra}» agregada. Ya se está filtrando.", type="positive", position="top")
                    campo_palabra.value = campo_cerca.value = campo_excepto.value = ""
                    lista_reglas.refresh()
                    probar()

                ui.button("Agregar al filtro", icon="add", on_click=agregar).props(
                    "unelevated rounded no-caps"
                ).classes("self-end")

            with tarjeta_simple():
                ui.label("Probar el filtro").classes("text-lg font-bold text-stone-900")
                prueba = ui.textarea(
                    "Escribe un texto de ejemplo", on_change=lambda: probar()
                ).props("outlined autogrow").classes("w-full")
                resultado = ui.label("").classes("font-semibold")

                def probar() -> None:
                    texto = prueba.value or ""
                    if not texto.strip():
                        resultado.text = ""
                        return
                    malas = filtro.encontradas(texto)
                    if malas:
                        resultado.text = "🚫 Se bloquearía por: " + ", ".join(f"«{m}»" for m in malas)
                    else:
                        resultado.text = "✅ Se podría publicar"

            def borrar_regla(regla_id: int, palabra: str) -> None:
                if not sigo_siendo_admin():
                    return
                datos.borrar_regla(regla_id)
                ui.notify(f"Se quitó «{palabra}» del filtro.", type="info", position="top")
                lista_reglas.refresh()
                probar()

            @ui.refreshable
            def lista_reglas() -> None:
                propias = datos.reglas()
                ui.label(f"Tus reglas ({len(propias)})").classes("text-lg font-black text-stone-900 mt-2")
                if not propias:
                    ui.label("Todavía no agregas palabras propias.").classes("text-stone-500")
                for regla in propias:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-start justify-between no-wrap gap-2"):
                            with ui.column().classes("gap-0.5"):
                                ui.label(regla.palabra).classes("text-lg font-bold text-stone-900")
                                if regla.siempre:
                                    ui.label("Se filtra siempre").classes("text-sm text-stone-600")
                                else:
                                    ui.label("Se filtra cerca de: " + ", ".join(regla.cerca_de)).classes(
                                        "text-sm text-stone-600"
                                    )
                                if regla.excepto:
                                    ui.label("Nunca en: " + ", ".join(regla.excepto)).classes(
                                        "text-sm text-stone-500"
                                    )
                            ui.button(
                                icon="delete_outline", on_click=partial(borrar_regla, regla.id, regla.palabra)
                            ).props("flat round color=red-8").tooltip("Quitar del filtro")

            lista_reglas()

            base = filtro.palabras_base()
            with ui.expansion(f"Lista base ({len(base)} palabras, se filtran siempre)", icon="list").classes(
                "w-full"
            ):
                ui.label(", ".join(base)).classes("text-xs text-stone-500")
                ui.label("La lista base está en filtro.py: para cambiarla hay que editar ese archivo.").classes(
                    "text-xs text-stone-400 mt-2"
                )

        # ------------------------------------------------------------ Bloqueados
        with ui.tab_panel(p_bloqueados).classes("px-0 gap-4"):

            def borrar_registro() -> None:
                if not sigo_siendo_admin():
                    return
                datos.borrar_filtrados()
                ui.notify("Registro borrado.", type="info", position="top")
                lista_bloqueados.refresh()
                cifras.refresh()

            with ui.row().classes("w-full justify-between items-center"):
                ui.label(
                    f"Lo que el filtro no dejó publicar (se guarda {datos.DIAS_REGISTRO_FILTRADOS} días)."
                ).classes("text-sm text-stone-500")
                with ui.row().classes("gap-1"):
                    ui.button(icon="refresh", on_click=lambda: lista_bloqueados.refresh()).props(
                        "flat round color=grey-9"
                    ).tooltip("Actualizar")
                    ui.button("Borrar registro", icon="delete_sweep", on_click=borrar_registro).props(
                        "flat rounded no-caps color=red-8"
                    )

            @ui.refreshable
            def lista_bloqueados() -> None:
                momento = ahora()
                registro = datos.filtrados_recientes(100)
                if not registro:
                    ui.label("No hay bloqueos registrados.").classes("text-stone-500")
                for bloqueo in registro:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            etiqueta(bloqueo.campo, "block", rojo=True)
                            ui.label(texto_fecha_evento(bloqueo.momento, momento)).classes(
                                "text-xs text-stone-500"
                            )
                        ui.label(bloqueo.texto).classes("text-stone-800 whitespace-pre-line break-words")
                        ui.label("Detectó: " + ", ".join(f"«{p}»" for p in bloqueo.palabras)).classes(
                            "text-xs font-semibold text-red-800"
                        )

            lista_bloqueados()

        # ------------------------------------------------------------ Avisos
        with ui.tab_panel(p_avisos).classes("px-0 gap-4"):
            ui.label("Los últimos 60 avisos, abiertos o no. Puedes eliminar cualquiera.").classes(
                "text-sm text-stone-500"
            )

            def tras_eliminar() -> None:
                lista_avisos.refresh()
                cifras.refresh()

            @ui.refreshable
            def lista_avisos() -> None:
                momento = ahora()
                avisos = datos.todos_los_avisos(60)
                if not avisos:
                    ui.label("Todavía no hay avisos.").classes("text-stone-500")
                for aviso in avisos:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                            ui.label(aviso.titulo).classes(
                                "text-lg font-bold text-stone-900 leading-snug cursor-pointer hover:underline"
                            ).on("click", partial(ui.navigate.to, f"/aviso/{aviso.id}"))
                            if aviso.cancelado:
                                quien = "por admin" if aviso.cancelado_por == "admin" else "por su dueño"
                                etiqueta(f"Eliminado {quien}", "delete_outline", rojo=True)
                            else:
                                etiqueta(ESTADOS_ADMIN[aviso.motivo_cierre(momento)], "info")
                        ui.label(
                            f"{aviso.nombre_categoria} · {aviso.lugar} · "
                            f"{texto_fecha_evento(aviso.inicio_evento, momento)} · "
                            f"{aviso.ocupados} de {aviso.personas_necesarias}"
                        ).classes("text-sm text-stone-600")
                        if not aviso.cancelado:
                            ui.button(
                                "Eliminar",
                                icon="delete_outline",
                                on_click=partial(
                                    abrir_dialogo_eliminar,
                                    aviso.id,
                                    capa,
                                    persona_id,
                                    tras_eliminar,
                                    como_admin=True,
                                ),
                            ).props("flat rounded no-caps dense color=red-8").classes("self-start -ml-1")

            lista_avisos()


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
