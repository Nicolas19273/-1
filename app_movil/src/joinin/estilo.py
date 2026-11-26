"""Colores e íconos de Join In (los mismos de la página)."""

import flet as ft

COLOR_PRINCIPAL = "#0E6B3F"  # verde cancha
TINTA = "#0B1F17"  # texto y botones oscuros
AMARILLO = "#FFD21F"  # el «+1»: el cupo que falta y los botones principales
FONDO = "#F3F4EF"  # gris papel
BLANCO = "#FFFFFF"
GRIS = "#5C6B63"
GRIS_SUAVE = "#E4E8E1"
ROJO = "#B3261E"
ROJO_SUAVE = "#FBE1DE"

ICONOS = {
    "futbol": ft.Icons.SPORTS_SOCCER,
    "basquetbol": ft.Icons.SPORTS_BASKETBALL,
    "tenis_padel": ft.Icons.SPORTS_TENNIS,
    "voleibol": ft.Icons.SPORTS_VOLLEYBALL,
    "juegos_mesa": ft.Icons.CASINO,
    "videojuegos": ft.Icons.SPORTS_ESPORTS,
    "estudio": ft.Icons.MENU_BOOK,
    "salida": ft.Icons.CELEBRATION,
    "otro": ft.Icons.CAMPAIGN,
}

# Cada categoría tiene su color: (fuerte, suave). El fuerte se lee bien con texto blanco.
COLORES = {
    "futbol": ("#0E6B3F", "#DDF0E3"),
    "basquetbol": ("#C2520A", "#FFE6D1"),
    "tenis_padel": ("#5A6A0B", "#EEF3C9"),
    "voleibol": ("#0B6E80", "#D6EFF3"),
    "juegos_mesa": ("#5B33B8", "#E9E1FA"),
    "videojuegos": ("#3B45B5", "#E0E3FB"),
    "estudio": ("#1D4FA8", "#DCE9FB"),
    "salida": ("#B3225F", "#FBE0EA"),
    "otro": ("#4A5A52", "#E4EAE6"),
}


def icono_de(categoria: str):
    return ICONOS.get(categoria, ICONOS["otro"])


def colores_de(categoria: str) -> tuple[str, str]:
    return COLORES.get(categoria, COLORES["otro"])


def tema() -> ft.Theme:
    return ft.Theme(color_scheme_seed=COLOR_PRINCIPAL)
