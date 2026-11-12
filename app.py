"""
app.py — Interfaz web de «Falta Uno», escrita 100 % en Python con NiceGUI.

En internet: Render ejecuta `python app.py` (ver README.md y render.yaml).

En tu computador, para probar cambios:
    pip install -r requirements.txt
    python app.py
y abre http://localhost:8080

Toda la lógica (cupos, plazos, base de datos) está en datos.py; este archivo
solo dibuja la página. Para cambiar el diseño más adelante, se edita aquí.
"""

from __future__ import annotations

import asyncio
import os
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from functools import partial
from typing import Callable

from fastapi import Request
from nicegui import app as servidor
from nicegui import ui

import datos

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
    datos.INICIADO: ("sports", "El evento ya comenzó", "El aviso se cerró a la hora del evento."),
    datos.VENCIDO: ("timer_off", "Aviso cerrado", "Se cumplió el plazo de {horas} horas."),
}


# --------------------------------------------------------------------------- #
# Textos
# --------------------------------------------------------------------------- #


def ahora() -> datetime:
    return datetime.now(datos.ZONA_HORARIA)


def texto_fecha_evento(momento: datetime, referencia: datetime) -> str:
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - referencia.date()).days
    if dias == 0:
        return f"Hoy, {hora}"
    if dias == 1:
        return f"Mañana, {hora}"
    return f"{DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]}, {hora}"


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
    texto = f"Organiza {aviso.creador}"
    if aviso.participantes:
        verbo = "se unió" if len(aviso.participantes) == 1 else "se unieron"
        texto += f" · {verbo} {unir_nombres(list(aviso.participantes))}"
    return texto


def firma_lista(activos: list[datos.Aviso], momento: datetime) -> tuple:
    """Resumen de lo que se ve; si cambia, hay que redibujar."""
    minuto = int(momento.timestamp() // 60)  # para que avance la cuenta regresiva
    return minuto, tuple((a.id, a.ocupados) for a in activos)


def firma_detalle(aviso: datos.Aviso | None, momento: datetime) -> tuple | None:
    if aviso is None:
        return None
    return int(momento.timestamp() // 60), aviso.ocupados, aviso.motivo_cierre(momento)


# --------------------------------------------------------------------------- #
# Piezas reutilizables
# --------------------------------------------------------------------------- #


def preparar_pagina() -> None:
    ui.colors(primary=COLOR_PRINCIPAL)
    ui.query("body").style(f"background-color: {FONDO}; font-family: {FUENTE}")


def encabezado() -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap cursor-pointer").on(
        "click", lambda: ui.navigate.to("/")
    ):
        ui.label("+1").classes(
            "w-11 h-11 rounded-full bg-primary text-white text-lg font-black "
            "flex items-center justify-center shrink-0"
        )
        with ui.column().classes("gap-0"):
            ui.label("Falta Uno").classes(
                "text-2xl font-black tracking-tight text-stone-900 leading-none"
            )
            ui.label("Avisos para completar el grupo").classes("text-sm text-stone-500")


def dato(icono: str, texto: str) -> None:
    with ui.row().classes("items-start gap-2 no-wrap"):
        ui.icon(icono, size="18px").classes("text-stone-400 mt-0.5 shrink-0")
        ui.label(texto).classes("text-stone-700")


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


def persona(nombre: str, detalle: str, destacado: bool = False) -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        color = "bg-primary text-white" if destacado else "bg-stone-200 text-stone-700"
        ui.label(nombre[:1].upper()).classes(
            f"w-9 h-9 rounded-full {color} font-bold flex items-center justify-center shrink-0"
        )
        with ui.column().classes("gap-0"):
            ui.label(nombre).classes("font-semibold text-stone-900 leading-tight")
            ui.label(detalle).classes("text-xs text-stone-500")


def aviso_de_cierre(aviso: datos.Aviso, motivo: str) -> None:
    icono, titulo, texto = CIERRES[motivo]
    fondo = "bg-green-50 border-green-200" if motivo == datos.COMPLETO else "bg-white border-stone-200"
    with ui.row().classes(f"w-full items-center gap-3 no-wrap rounded-2xl border p-4 {fondo}"):
        ui.icon(icono, size="28px").classes("text-primary shrink-0")
        with ui.column().classes("gap-0"):
            ui.label(titulo).classes("font-bold text-stone-900")
            ui.label(texto.format(horas=aviso.duracion_horas)).classes("text-sm text-stone-600")


def tarjeta_aviso(
    aviso: datos.Aviso,
    momento: datetime,
    al_unirse: Callable[[int], None],
    detalle: bool = False,
) -> None:
    abierto = aviso.esta_abierto(momento)
    with ui.card().classes("w-full rounded-2xl shadow-none border border-stone-200 p-5 gap-3"):
        # Categoría y cuenta regresiva
        with ui.row().classes("w-full items-center justify-between no-wrap"):
            with ui.row().classes("items-center gap-1.5 no-wrap"):
                ui.icon(ICONOS.get(aviso.categoria, "campaign"), size="18px").classes("text-primary")
                ui.label(aviso.nombre_categoria.upper()).classes(
                    "text-xs font-bold tracking-wider text-stone-500"
                )
            if abierto:
                ui.label(texto_tiempo_restante(aviso.cierra_en, momento)).classes(
                    "text-xs text-stone-500 whitespace-nowrap"
                )

        # Título (en la lista lleva a la página del aviso)
        titulo = ui.label(aviso.titulo).classes("text-xl font-bold text-stone-900 leading-snug")
        if not detalle:
            titulo.classes("cursor-pointer hover:underline").on(
                "click", lambda: ui.navigate.to(f"/aviso/{aviso.id}")
            )

        # Dónde y cuándo
        with ui.column().classes("gap-1"):
            dato("place", aviso.lugar)
            dato("schedule", texto_fecha_evento(aviso.inicio_evento, momento))

        if aviso.descripcion:
            descripcion = ui.label(aviso.descripcion).classes("text-stone-600 whitespace-pre-line")
            if not detalle:
                descripcion.classes("line-clamp-3")

        barra_cupos(aviso)

        # Quiénes van
        if detalle:
            ui.label("Quiénes van").classes("text-sm font-bold text-stone-700 mt-2")
            otros = aviso.personas_actuales - 1
            persona(
                aviso.creador,
                "Organiza" + (f" · viene con {otros} más" if otros > 0 else ""),
                destacado=True,
            )
            for nombre in aviso.participantes:
                persona(nombre, "Se unió por Falta Uno")
        else:
            ui.label(texto_quienes(aviso)).classes("text-sm text-stone-500")

        if abierto:
            ui.button("Unirme", icon="person_add", on_click=partial(al_unirse, aviso.id)).props(
                "unelevated rounded no-caps"
            ).classes("w-full mt-1")


# --------------------------------------------------------------------------- #
# Diálogos
# --------------------------------------------------------------------------- #


def abrir_dialogo_unirse(aviso_id: int, capa: ui.element, al_cambiar: Callable[[], None]) -> None:
    aviso = datos.obtener_aviso(aviso_id)
    if aviso is None or not aviso.esta_abierto(ahora()):
        ui.notify("Este aviso ya se cerró.", type="warning", position="top")
        al_cambiar()
        return

    with capa, ui.dialog() as dialogo, ui.card().classes("rounded-2xl p-6 gap-4").style(
        "width: 440px; max-width: 94vw"
    ):
        ui.label("Te vas a unir a").classes("text-sm text-stone-500")
        ui.label(aviso.titulo).classes("text-xl font-bold text-stone-900 leading-snug -mt-3")
        with ui.column().classes("gap-1"):
            dato("place", aviso.lugar)
            dato("schedule", texto_fecha_evento(aviso.inicio_evento, ahora()))
        ui.label(texto_faltan(aviso.cupos_libres)).classes("font-bold text-primary")

        nombre = ui.input("Tu nombre", placeholder="Ej: Pedro Soto").props(
            f"outlined autofocus maxlength={datos.LARGO_NOMBRE[1]}"
        ).classes("w-full")

        def confirmar() -> None:
            try:
                actualizado = datos.unirse(aviso_id, nombre.value)
            except datos.ErrorValidacion as error:
                ui.notify(str(error), type="negative", position="top")
                vigente = datos.obtener_aviso(aviso_id)
                if vigente is None or not vigente.esta_abierto(ahora()):
                    dialogo.close()
                    al_cambiar()
                return

            dialogo.close()
            quien = datos.limpiar(nombre.value)
            if actualizado.esta_lleno:
                mensaje = f"¡Listo, {quien}! Con eso se completó el grupo 🎉"
            else:
                mensaje = f"¡Listo, {quien}! Te uniste. {texto_faltan(actualizado.cupos_libres)}."
            ui.notify(mensaje, type="positive", position="top")
            al_cambiar()

        nombre.on("keydown.enter", confirmar)

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=dialogo.close).props("flat no-caps color=grey-8")
            ui.button("Confirmar", icon="check", on_click=confirmar).props(
                "unelevated rounded no-caps"
            )

    dialogo.on("hide", dialogo.delete)  # se borra al cerrarse
    dialogo.open()


def abrir_dialogo_crear(capa: ui.element, base_url: str, al_cambiar: Callable[[], None]) -> None:
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
                creador=campo_creador.value,
                titulo=campo_titulo.value,
                categoria=campo_categoria.value,
                lugar=campo_lugar.value,
                inicio_evento=inicio,
                personas_actuales=campo_actuales.value,
                personas_necesarias=campo_necesarias.value,
                duracion_horas=campo_duracion.value,
                descripcion=campo_descripcion.value,
            )
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            return
        al_cambiar()
        mostrar_exito(aviso)

    def mostrar_exito(aviso: datos.Aviso) -> None:
        enlace = f"{base_url}/aviso/{aviso.id}"
        if aviso.cierra_en < aviso.expira_en:
            cierre = "Se cerrará a la hora del evento"
        else:
            cierre = f"Se cerrará solo en {aviso.duracion_horas} horas"
        cuerpo.clear()
        with cuerpo:
            ui.icon("check_circle", size="56px").classes("text-primary self-center")
            ui.label("¡Aviso publicado!").classes(
                "text-2xl font-black text-stone-900 text-center w-full"
            )
            ui.label(f"{cierre}, o antes si se completa el grupo.").classes(
                "text-stone-600 text-center w-full -mt-2"
            )
            ui.label("Guarda este enlace para ver quién se une:").classes(
                "text-sm font-semibold text-stone-700 mt-2"
            )
            ui.input(value=enlace).props("outlined dense readonly").classes("w-full")
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Listo", on_click=dialogo.close).props(
                    "flat rounded no-caps color=grey-8"
                ).classes("flex-1")
                ui.button(
                    "Ver mi aviso", on_click=lambda: ui.navigate.to(f"/aviso/{aviso.id}")
                ).props("unelevated rounded no-caps").classes("flex-1")

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
        ui.label("Se cierra antes si se completa el grupo o si llega la hora del evento.").classes(
            "text-xs text-stone-500 -mt-2"
        )

        campo_creador = ui.input("Tu nombre", placeholder="Así te verán los demás").props(
            f"outlined maxlength={datos.LARGO_NOMBRE[1]}"
        ).classes("w-full")

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
    base_url = URL_PUBLICA or str(request.base_url).rstrip("/")
    capa = ui.element("div")  # los diálogos viven aquí, fuera de la lista que se redibuja
    estado: dict = {"categoria": None, "firma": None}

    def refrescar() -> None:
        lista.refresh()

    def elegir_categoria(clave: str | None) -> None:
        estado["categoria"] = clave
        lista.refresh()

    def chip(texto: str, cantidad: int, activo: bool, al_tocar, icono: str | None = None) -> None:
        estilo = "color=primary" if activo else "color=white text-color=grey-9"
        ui.button(f"{texto} · {cantidad}", icon=icono, on_click=al_tocar).props(
            f"unelevated rounded no-caps {estilo}"
        ).classes("shrink-0 border border-stone-300 px-3")

    @ui.refreshable
    def lista() -> None:
        momento = ahora()
        activos = datos.avisos_activos(momento)
        estado["firma"] = firma_lista(activos, momento)

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
                ui.icon("sports_soccer", size="48px").classes("text-stone-300")
                if elegida:
                    ui.label(f"No hay avisos abiertos de {datos.CATEGORIAS[elegida]}").classes(
                        "text-lg font-bold text-stone-700"
                    )
                else:
                    ui.label("No hay avisos abiertos").classes("text-lg font-bold text-stone-700")
                ui.label("Toca el botón + para publicar uno.").classes("text-stone-500")
            return

        for aviso in visibles:
            tarjeta_aviso(aviso, momento, partial(abrir_dialogo_unirse, capa=capa, al_cambiar=refrescar))

    def revisar_cambios() -> None:
        momento = ahora()
        if firma_lista(datos.avisos_activos(momento), momento) != estado["firma"]:
            lista.refresh()

    with ui.column().classes("w-full max-w-2xl mx-auto px-4 pt-6 pb-32 gap-5"):
        encabezado()
        lista()

    with ui.page_sticky(position="bottom-right", x_offset=20, y_offset=20):
        ui.button(
            icon="add", on_click=lambda: abrir_dialogo_crear(capa, base_url, refrescar)
        ).props("fab color=primary").tooltip("Publicar un aviso")

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


@ui.page("/aviso/{aviso_id}", title="Falta Uno · Aviso")
def pagina_aviso(aviso_id: int) -> None:
    preparar_pagina()
    capa = ui.element("div")
    estado: dict = {"firma": None}

    def refrescar() -> None:
        contenido.refresh()

    @ui.refreshable
    def contenido() -> None:
        momento = ahora()
        aviso = datos.obtener_aviso(aviso_id)
        estado["firma"] = firma_detalle(aviso, momento)

        if aviso is None:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.icon("search_off", size="48px").classes("text-stone-300")
                ui.label("Este aviso no existe").classes("text-lg font-bold text-stone-700")
            return

        motivo = aviso.motivo_cierre(momento)
        if motivo:
            aviso_de_cierre(aviso, motivo)
        tarjeta_aviso(
            aviso,
            momento,
            partial(abrir_dialogo_unirse, capa=capa, al_cambiar=refrescar),
            detalle=True,
        )

    def revisar_cambios() -> None:
        momento = ahora()
        if firma_detalle(datos.obtener_aviso(aviso_id), momento) != estado["firma"]:
            contenido.refresh()

    with ui.column().classes("w-full max-w-2xl mx-auto px-4 pt-6 pb-16 gap-4"):
        encabezado()
        ui.button("Ver todos los avisos", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
            "flat no-caps dense color=grey-8"
        ).classes("self-start")
        contenido()

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
        favicon="⚽",
        language="es",
        host="0.0.0.0",  # acepta visitas desde fuera del servidor
        port=int(os.environ.get("PORT", 8080)),
        reload=not EN_INTERNET,  # en tu PC se recarga sola al editar
        show=not EN_INTERNET,  # en tu PC abre el navegador
    )
