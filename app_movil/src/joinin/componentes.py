"""Piezas de interfaz que se repiten en varias pantallas."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import flet as ft

from . import formato as f
from .estilo import AMARILLO, BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, ROJO, ROJO_SUAVE, TINTA, colores_de, icono_de


def texto(valor: str, tam: int = 14, peso=None, color: str = TINTA, **kw) -> ft.Text:
    return ft.Text(valor, size=tam, weight=peso, color=color, **kw)


def titulo(valor: str, tam: int = 22) -> ft.Text:
    return ft.Text(valor, size=tam, weight=ft.FontWeight.W_800, color=TINTA)


def suave(valor: str, tam: int = 13) -> ft.Text:
    return ft.Text(valor, size=tam, color=GRIS)


def tarjeta(contenido: list[ft.Control], al_tocar: Callable | None = None, color: str = BLANCO,
            borde: str = GRIS_SUAVE, espacio: int = 8) -> ft.Container:
    return ft.Container(
        content=ft.Column(contenido, spacing=espacio, tight=True),
        bgcolor=color,
        border=ft.Border.all(1, borde),
        border_radius=ft.BorderRadius.all(16),
        padding=ft.Padding.all(14),
        on_click=al_tocar,
        ink=al_tocar is not None,
    )


def chip(etiqueta: str, icono=None, color: str = TINTA, fondo: str = GRIS_SUAVE) -> ft.Container:
    hijos: list[ft.Control] = []
    if icono is not None:
        hijos.append(ft.Icon(icono, size=16, color=color))
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


def dato(icono, valor: str) -> ft.Row:
    return ft.Row(
        [ft.Icon(icono, size=18, color=GRIS), ft.Text(valor, size=14, color=TINTA, expand=True)],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def barra_cupos(ocupados: int, necesarias: int) -> ft.Row:
    """Barra de cuántos van de cuántos se necesitan."""
    ocupados = max(0, min(ocupados, necesarias))
    libres = max(necesarias - ocupados, 0)
    partes: list[ft.Control] = []
    if ocupados:
        partes.append(ft.Container(expand=ocupados, height=8, bgcolor=COLOR_PRINCIPAL, border_radius=ft.BorderRadius.all(4)))
    if libres:
        partes.append(ft.Container(expand=libres, height=8, bgcolor=AMARILLO, border_radius=ft.BorderRadius.all(4)))
    return ft.Row(partes, spacing=3)


def resumen_cupos(aviso: dict) -> ft.Column:
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Text(f.texto_faltan(aviso["cupos_libres"]), size=15, weight=ft.FontWeight.W_800, color=TINTA),
                    ft.Text(f"{aviso['ocupados']} de {aviso['personas_necesarias']}", size=13, color=GRIS),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            barra_cupos(aviso["ocupados"], aviso["personas_necesarias"]),
        ],
        spacing=6,
        tight=True,
    )


def tarjeta_aviso(aviso: dict, momento: datetime, al_tocar: Callable | None,
                  pie: list[ft.Control] | None = None) -> ft.Container:
    """La tarjeta de un aviso en el tablero, el buzón y el panel."""
    inicio = f.leer_fecha(aviso["inicio_evento"])
    filas: list[ft.Control] = [
        ft.Row(
            [chip_categoria(aviso["categoria"], aviso["nombre_categoria"])]
            + ([chip(f.texto_valor(aviso["valor"]), ft.Icons.PAYMENTS, color=TINTA, fondo=AMARILLO)]
               if aviso.get("valor") is not None else []),
            spacing=6,
            wrap=True,
        ),
        ft.Text(aviso["titulo"], size=18, weight=ft.FontWeight.W_800, color=TINTA),
        dato(ft.Icons.SCHEDULE, f.texto_fecha_evento(inicio, momento)),
        dato(ft.Icons.PLACE, aviso["lugar"]),
        resumen_cupos(aviso),
    ]
    if aviso.get("abierto"):
        filas.append(suave(f.texto_tiempo_restante(f.leer_fecha(aviso["cierra_en"]), momento)
                           + " · " + f.texto_comentarios(aviso.get("comentarios", 0))))
    if pie:
        filas.extend(pie)
    return tarjeta(filas, al_tocar)


def nota(principal: str, secundario: str = "", color: str = TINTA, fondo: str = GRIS_SUAVE) -> ft.Container:
    hijos: list[ft.Control] = [ft.Text(principal, size=14, weight=ft.FontWeight.W_700, color=color)]
    if secundario:
        hijos.append(ft.Text(secundario, size=12, color=color))
    return ft.Container(
        content=ft.Column(hijos, spacing=2, tight=True),
        bgcolor=fondo,
        border_radius=ft.BorderRadius.all(12),
        padding=ft.Padding.all(12),
    )


def boton_principal(etiqueta: str, al_tocar: Callable | None, icono=None, expandir: bool = True) -> ft.Button:
    return ft.Button(
        etiqueta,
        icon=icono,
        on_click=al_tocar,
        expand=expandir,
        style=ft.ButtonStyle(
            bgcolor=AMARILLO,
            color=TINTA,
            shape=ft.RoundedRectangleBorder(radius=14),
            padding=ft.Padding.symmetric(horizontal=18, vertical=16),
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_800),
        ),
    )


def boton_oscuro(etiqueta: str, al_tocar: Callable | None, icono=None, expandir: bool = True) -> ft.Button:
    return ft.Button(
        etiqueta,
        icon=icono,
        on_click=al_tocar,
        expand=expandir,
        style=ft.ButtonStyle(
            bgcolor=TINTA,
            color=BLANCO,
            shape=ft.RoundedRectangleBorder(radius=14),
            padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        ),
    )


def boton_peligro(etiqueta: str, al_tocar: Callable | None, icono=ft.Icons.DELETE_OUTLINE) -> ft.TextButton:
    return ft.TextButton(etiqueta, icon=icono, on_click=al_tocar, style=ft.ButtonStyle(color=ROJO))


def boton_texto(etiqueta: str, al_tocar: Callable | None, icono=None) -> ft.TextButton:
    return ft.TextButton(etiqueta, icon=icono, on_click=al_tocar, style=ft.ButtonStyle(color=COLOR_PRINCIPAL))


def vacio(icono, encabezado: str, explicacion: str) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icono, size=48, color=GRIS),
                ft.Text(encabezado, size=17, weight=ft.FontWeight.W_800, color=TINTA, text_align=ft.TextAlign.CENTER),
                ft.Text(explicacion, size=14, color=GRIS, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
            tight=True,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=32),
        alignment=ft.Alignment.CENTER,
    )


def cargando(mensaje: str = "Cargando…") -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [ft.ProgressRing(color=COLOR_PRINCIPAL), ft.Text(mensaje, size=13, color=GRIS)],
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
        border_radius=ft.BorderRadius.all(14),
        padding=ft.Padding.all(14),
    )
