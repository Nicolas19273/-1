"""Piezas de interfaz que se repiten en varias pantallas."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import flet as ft

from . import formato as f
from .estilo import (AMARILLO, AMARILLO_SUAVE, BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, LETRA_TITULOS, ROJO,
                     ROJO_SUAVE, TINTA, colores_de, icono_de)

MAX_SEGMENTOS = 12  # hasta cuántos cupos se dibujan uno por uno en la barra
MAX_CUPOS_ALINEACION = 20  # hasta cuántos círculos se dibujan en «quiénes van»


def texto(valor: str, tam: int = 14, peso=None, color: str = TINTA, **kw) -> ft.Text:
    return ft.Text(valor, size=tam, weight=peso, color=color, **kw)


def titulo(valor: str, tam: int = 24, color: str = TINTA, **kw) -> ft.Text:
    """Títulos y números: la letra angosta y gruesa, como en un marcador."""
    return ft.Text(valor, size=tam, weight=ft.FontWeight.W_800, color=color, font_family=LETRA_TITULOS, **kw)


def suave(valor: str, tam: int = 13, **kw) -> ft.Text:
    return ft.Text(valor, size=tam, color=GRIS, **kw)


def tarjeta(contenido: list[ft.Control], al_tocar: Callable | None = None, color: str = BLANCO,
            borde: str = GRIS_SUAVE, espacio: int = 8, relleno: int = 16) -> ft.Container:
    return ft.Container(
        content=ft.Column(contenido, spacing=espacio, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        bgcolor=color,
        border=ft.Border.all(1, borde),
        border_radius=ft.BorderRadius.all(20),
        padding=ft.Padding.all(relleno),
        on_click=al_tocar,
        ink=al_tocar is not None,
    )


# ----------------------------------------------------------------------------- la ficha

def ficha(valor: str | None = "+1", tam: int = 48, fondo: str = AMARILLO, color: str = TINTA,
          borde: str = TINTA, icono=None) -> ft.Container:
    """La ficha de Join In: el cuadrado amarillo con «+1». Con otro número, los cupos que faltan."""
    if icono is not None:
        dentro: ft.Control = ft.Icon(icono, size=tam * 0.5, color=color)
    else:
        largo = len(valor or "")
        letra = tam * (0.46 if largo <= 2 else 0.38 if largo == 3 else 0.3)
        dentro = ft.Text(valor, size=round(letra), weight=ft.FontWeight.W_900, color=color,
                         font_family=LETRA_TITULOS, no_wrap=True)
    return ft.Container(
        content=dentro,
        width=tam,
        height=tam,
        bgcolor=fondo,
        border=ft.Border.all(max(2, round(tam / 22)), borde),
        border_radius=ft.BorderRadius.all(tam * 0.28),
        alignment=ft.Alignment.CENTER,
    )


def ficha_cupos(aviso: dict, tam: int = 48) -> ft.Container:
    """«+2» en amarillo si faltan dos; un visto en verde si se completó; gris si se canceló."""
    if aviso.get("cancelado"):
        return ficha(None, tam, fondo=GRIS_SUAVE, color=GRIS, borde=GRIS_SUAVE, icono=ft.Icons.CLOSE)
    if aviso["cupos_libres"] <= 0:
        return ficha(None, tam, fondo=COLOR_PRINCIPAL, color=BLANCO, borde=COLOR_PRINCIPAL, icono=ft.Icons.CHECK)
    return ficha(f"+{aviso['cupos_libres']}", tam)


# ----------------------------------------------------------------------------- chips y datos

def chip(etiqueta: str, icono=None, color: str = TINTA, fondo: str = GRIS_SUAVE) -> ft.Container:
    hijos: list[ft.Control] = []
    if icono is not None:
        hijos.append(ft.Icon(icono, size=15, color=color))
    hijos.append(ft.Text(etiqueta, size=12, weight=ft.FontWeight.W_700, color=color))
    return ft.Container(
        content=ft.Row(hijos, spacing=4, tight=True),
        bgcolor=fondo,
        border_radius=ft.BorderRadius.all(20),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


def chip_categoria(categoria: str, nombre: str) -> ft.Container:
    fuerte, claro = colores_de(categoria)
    return chip(nombre, icono_de(categoria), color=fuerte, fondo=claro)


def etiqueta_categoria(categoria: str, nombre: str) -> ft.Row:
    """El ícono de la categoría en su círculo de color, con el nombre al lado."""
    fuerte, claro = colores_de(categoria)
    return ft.Row(
        [
            ft.Container(ft.Icon(icono_de(categoria), size=16, color=fuerte), width=28, height=28, bgcolor=claro,
                         border_radius=ft.BorderRadius.all(14), alignment=ft.Alignment.CENTER),
            ft.Text(nombre, size=13, weight=ft.FontWeight.W_700, color=fuerte),
        ],
        spacing=8,
        tight=True,
    )


def dato(icono, valor: str, color: str = TINTA, color_icono: str = GRIS, tam: int = 14) -> ft.Row:
    return ft.Row(
        [ft.Icon(icono, size=17, color=color_icono), ft.Text(valor, size=tam, color=color, expand=True)],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def precio(aviso: dict) -> ft.Container | None:
    if aviso.get("valor") is None:
        return None
    if aviso["valor"] == 0:
        return chip("Gratis", ft.Icons.MONEY_OFF, color=COLOR_PRINCIPAL, fondo="#DDF0E3")
    return chip(f.texto_valor(aviso["valor"]), ft.Icons.PAYMENTS, color=TINTA, fondo=AMARILLO)


# ----------------------------------------------------------------------------- cupos

def barra_cupos(ocupados: int, necesarias: int, alto: int = 8) -> ft.Row:
    """
    Cuántos van de cuántos se necesitan. Con pocos cupos, uno por uno (verde los
    ocupados, amarillo los que faltan); con muchos, una sola barra.
    """
    ocupados = max(0, min(ocupados, necesarias))
    libres = max(necesarias - ocupados, 0)
    redondeo = ft.BorderRadius.all(alto / 2)
    if 0 < necesarias <= MAX_SEGMENTOS:
        return ft.Row(
            [ft.Container(expand=1, height=alto, border_radius=redondeo,
                          bgcolor=COLOR_PRINCIPAL if i < ocupados else AMARILLO)
             for i in range(necesarias)],
            spacing=3,
        )
    partes: list[ft.Control] = []
    if ocupados:
        partes.append(ft.Container(expand=ocupados, height=alto, bgcolor=COLOR_PRINCIPAL, border_radius=redondeo))
    if libres:
        partes.append(ft.Container(expand=libres, height=alto, bgcolor=AMARILLO, border_radius=redondeo))
    return ft.Row(partes, spacing=3)


def resumen_cupos(aviso: dict) -> ft.Column:
    return ft.Column(
        [
            barra_cupos(aviso["ocupados"], aviso["personas_necesarias"]),
            ft.Row(
                [
                    ft.Text(f.texto_faltan(aviso["cupos_libres"]), size=14, weight=ft.FontWeight.W_700, color=TINTA),
                    ft.Text(f"{aviso['ocupados']} de {aviso['personas_necesarias']}", size=13, color=GRIS),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
        ],
        spacing=8,
        tight=True,
    )


def _cupo(contenido: ft.Control | None, fondo: str, borde: str | None = None, tam: int = 34) -> ft.Container:
    return ft.Container(
        content=contenido,
        width=tam,
        height=tam,
        bgcolor=fondo,
        border=ft.Border.all(2, borde) if borde else None,
        border_radius=ft.BorderRadius.all(tam / 2),
        alignment=ft.Alignment.CENTER,
    )


def alineacion(aviso: dict) -> ft.Row:
    """
    Quiénes van, como una alineación: un círculo por persona. Quien organiza en verde
    oscuro, los que se unieron con sus iniciales y los cupos libres en amarillo.
    """
    necesarias = aviso["personas_necesarias"]
    ocupados = max(0, min(aviso["ocupados"], necesarias))
    inscritos = list(aviso.get("inscritos") or [])
    sin_nombre = max(ocupados - 1 - len(inscritos), 0)  # amigos que ya venían con quien organiza
    circulos: list[ft.Control] = [
        _cupo(ft.Text(f.iniciales(aviso.get("creador")), size=12, weight=ft.FontWeight.W_800, color=BLANCO),
              COLOR_PRINCIPAL)
    ]
    circulos += [_cupo(ft.Icon(ft.Icons.PERSON, size=18, color=COLOR_PRINCIPAL), "#DDF0E3") for _ in range(sin_nombre)]
    circulos += [_cupo(ft.Text(f.iniciales(nombre), size=12, weight=ft.FontWeight.W_800, color=COLOR_PRINCIPAL),
                       "#DDF0E3") for nombre in inscritos]
    circulos += [_cupo(ft.Icon(ft.Icons.ADD, size=18, color=TINTA), AMARILLO_SUAVE, AMARILLO)
                 for _ in range(max(necesarias - ocupados, 0))]
    if len(circulos) > MAX_CUPOS_ALINEACION:
        resto = len(circulos) - (MAX_CUPOS_ALINEACION - 1)
        circulos = circulos[: MAX_CUPOS_ALINEACION - 1] + [
            _cupo(ft.Text(f"+{resto}", size=11, weight=ft.FontWeight.W_800, color=TINTA), GRIS_SUAVE)
        ]
    return ft.Row(circulos, wrap=True, spacing=6, run_spacing=6)


# ----------------------------------------------------------------------------- tarjeta de aviso

def tarjeta_aviso(aviso: dict, momento: datetime, al_tocar: Callable | None,
                  pie: list[ft.Control] | None = None) -> ft.Container:
    """La tarjeta de un aviso en el tablero, el buzón y el panel."""
    inicio = f.leer_fecha(aviso["inicio_evento"])
    cabeza: list[ft.Control] = [etiqueta_categoria(aviso["categoria"], aviso["nombre_categoria"])]
    valor = precio(aviso)
    if valor is not None:
        cabeza.append(valor)
    filas: list[ft.Control] = [
        ft.Row(cabeza, alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row(
            [
                ft.Column(
                    [
                        titulo(aviso["titulo"], 23),
                        dato(ft.Icons.SCHEDULE, f.texto_fecha_evento(inicio, momento)),
                        dato(ft.Icons.PLACE_OUTLINED, aviso["lugar"]),
                    ],
                    spacing=4,
                    expand=True,
                    tight=True,
                ),
                ficha_cupos(aviso, 52),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=12,
        ),
        ft.Container(height=2),
        resumen_cupos(aviso),
    ]
    if aviso.get("abierto"):
        filas.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.TIMER_OUTLINED, size=15, color=GRIS),
                    ft.Text(f.texto_tiempo_restante(f.leer_fecha(aviso["cierra_en"]), momento), size=12, color=GRIS),
                    ft.Container(width=6),
                    ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=14, color=GRIS),
                    ft.Text(f.texto_comentarios(aviso.get("comentarios", 0)), size=12, color=GRIS),
                ],
                spacing=4,
                wrap=True,
            )
        )
    if pie:
        filas.extend(pie)
    return tarjeta(filas, al_tocar, espacio=10)


def pestanas(opciones: list[tuple[str, object, Callable]], elegida) -> ft.Container:
    """Un selector de dos o tres partes (como «Me uní | Organizo»): la elegida va en blanco."""
    partes: list[ft.Control] = []
    for etiqueta, icono, al_tocar in opciones:
        activa = etiqueta == elegida
        partes.append(
            ft.Container(
                content=ft.Row(
                    [ft.Icon(icono, size=17, color=COLOR_PRINCIPAL if activa else GRIS),
                     ft.Text(etiqueta, size=14, weight=ft.FontWeight.W_700, color=TINTA if activa else GRIS)],
                    spacing=6,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                expand=1,
                bgcolor=BLANCO if activa else None,
                border=ft.Border.all(1, GRIS_SUAVE) if activa else None,
                border_radius=ft.BorderRadius.all(12),
                padding=ft.Padding.symmetric(vertical=10),
                alignment=ft.Alignment.CENTER,
                on_click=al_tocar,
                ink=True,
            )
        )
    return ft.Container(
        content=ft.Row(partes, spacing=4),
        bgcolor=GRIS_SUAVE,
        border_radius=ft.BorderRadius.all(15),
        padding=ft.Padding.all(4),
    )


# ----------------------------------------------------------------------------- notas, botones y estados

def nota(principal: str, secundario: str = "", color: str = TINTA, fondo: str = GRIS_SUAVE, icono=None) -> ft.Container:
    textos: list[ft.Control] = [ft.Text(principal, size=14, weight=ft.FontWeight.W_700, color=color)]
    if secundario:
        textos.append(ft.Text(secundario, size=13, color=color))
    columna = ft.Column(textos, spacing=2, tight=True, expand=icono is not None)
    contenido: ft.Control = columna
    if icono is not None:
        contenido = ft.Row([ft.Icon(icono, size=20, color=color), columna], spacing=10,
                           vertical_alignment=ft.CrossAxisAlignment.START)
    return ft.Container(
        content=contenido,
        bgcolor=fondo,
        border_radius=ft.BorderRadius.all(14),
        padding=ft.Padding.symmetric(horizontal=14, vertical=12),
    )


def _estilo_boton(fondo: str, color: str, vertical: int = 16, tam: int = 16) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor=fondo,
        color=color,
        elevation=0,
        shape=ft.RoundedRectangleBorder(radius=16),
        padding=ft.Padding.symmetric(horizontal=18, vertical=vertical),
        text_style=ft.TextStyle(size=tam, weight=ft.FontWeight.W_700),
    )


def boton_principal(etiqueta: str, al_tocar: Callable | None, icono=None, expandir: bool = True) -> ft.Button:
    """El botón amarillo (con borde de tinta, como la ficha): lo principal de cada pantalla."""
    estilo = _estilo_boton(AMARILLO, TINTA)
    estilo.side = ft.BorderSide(2, TINTA)
    estilo.text_style = ft.TextStyle(size=16, weight=ft.FontWeight.W_800)
    return ft.Button(etiqueta, icon=icono, on_click=al_tocar, expand=expandir, style=estilo)


def boton_oscuro(etiqueta: str, al_tocar: Callable | None, icono=None, expandir: bool = True) -> ft.Button:
    return ft.Button(etiqueta, icon=icono, on_click=al_tocar, expand=expandir,
                     style=_estilo_boton(TINTA, BLANCO, vertical=14, tam=15))


def boton_claro(etiqueta: str, al_tocar: Callable | None = None, icono=None, color: str = COLOR_PRINCIPAL,
                url: str | None = None, expandir: bool = False) -> ft.Button:
    """Botón blanco (por ejemplo, «Cómo llegar» sobre el color de la categoría)."""
    return ft.Button(etiqueta, icon=icono, on_click=al_tocar, url=url, expand=expandir,
                     style=_estilo_boton(BLANCO, color, vertical=12, tam=14))


def boton_peligro(etiqueta: str, al_tocar: Callable | None, icono=ft.Icons.DELETE_OUTLINE) -> ft.TextButton:
    return ft.TextButton(etiqueta, icon=icono, on_click=al_tocar,
                         style=ft.ButtonStyle(color=ROJO, text_style=ft.TextStyle(weight=ft.FontWeight.W_700)))


def boton_texto(etiqueta: str, al_tocar: Callable | None, icono=None) -> ft.TextButton:
    return ft.TextButton(etiqueta, icon=icono, on_click=al_tocar,
                         style=ft.ButtonStyle(color=COLOR_PRINCIPAL, text_style=ft.TextStyle(weight=ft.FontWeight.W_700)))


def vacio(icono, encabezado: str, explicacion: str, accion: ft.Control | None = None) -> ft.Container:
    hijos: list[ft.Control] = [
        ft.Container(ft.Icon(icono, size=30, color=GRIS), width=64, height=64, bgcolor=GRIS_SUAVE,
                     border_radius=ft.BorderRadius.all(32), alignment=ft.Alignment.CENTER),
        ft.Container(height=4),
        titulo(encabezado, 22, text_align=ft.TextAlign.CENTER),
        ft.Text(explicacion, size=14, color=GRIS, text_align=ft.TextAlign.CENTER),
    ]
    if accion is not None:
        hijos += [ft.Container(height=6), accion]
    return ft.Container(
        content=ft.Column(hijos, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, tight=True),
        padding=ft.Padding.symmetric(horizontal=20, vertical=36),
        alignment=ft.Alignment.CENTER,
    )


def cargando(mensaje: str = "Cargando…") -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [ft.ProgressRing(color=COLOR_PRINCIPAL, stroke_width=3), ft.Text(mensaje, size=13, color=GRIS)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
            tight=True,
        ),
        padding=ft.Padding.symmetric(vertical=40),
        alignment=ft.Alignment.CENTER,
    )


def avatar(nombre: str, color: str = GRIS_SUAVE, texto_color: str = TINTA) -> ft.CircleAvatar:
    return ft.CircleAvatar(
        content=ft.Text(f.iniciales(nombre), size=13, weight=ft.FontWeight.W_800, color=texto_color),
        bgcolor=color,
        radius=18,
    )


def mensaje_error(valor: str = "") -> ft.Text:
    return ft.Text(valor, size=13, color=ROJO, visible=bool(valor))


def caja_peligro(contenido: list[ft.Control]) -> ft.Container:
    return ft.Container(
        content=ft.Column(contenido, spacing=8, tight=True),
        bgcolor=ROJO_SUAVE,
        border_radius=ft.BorderRadius.all(16),
        padding=ft.Padding.all(14),
    )
