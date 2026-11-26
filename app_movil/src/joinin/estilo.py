"""
Colores, letras e íconos de Join In.

La idea: la ficha amarilla con «+1» (el que falta) sobre el verde de la cancha.
La ficha aparece en el logo, en cada aviso («+2»: faltan dos) y en el botón de
crear. Las letras son Archivo (licencia SIL OFL, en assets/fonts): angosta y
gruesa para títulos y números, como en un marcador; normal para el texto.
"""

import flet as ft

COLOR_PRINCIPAL = "#0E6B3F"  # verde cancha
CANCHA_OSCURA = "#0A4F2F"  # el fondo de la cancha en el ingreso
TINTA = "#0B1F17"  # texto y bordes de la ficha
AMARILLO = "#FFD21F"  # el «+1»: el cupo que falta y los botones principales
AMARILLO_SUAVE = "#FFF3C2"
FONDO = "#F3F4EF"  # gris papel
BLANCO = "#FFFFFF"
GRIS = "#5C6B63"
GRIS_SUAVE = "#E4E8E1"  # bordes y cupos vacíos
ROJO = "#B3261E"
ROJO_SUAVE = "#FBE1DE"

# Letras (los archivos están en src/assets/fonts; ver herramientas/armar_fuentes.py)
LETRA = "Archivo"
LETRA_TITULOS = "Archivo Condensada"
FUENTES = {
    LETRA: "fonts/Archivo.ttf",
    LETRA_TITULOS: "fonts/ArchivoCondensada.ttf",
}

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


def estilo_titulo(tam: int = 22, color: str = TINTA, peso=ft.FontWeight.W_800) -> ft.TextStyle:
    return ft.TextStyle(font_family=LETRA_TITULOS, size=tam, weight=peso, color=color)


def tema() -> ft.Theme:
    """El tema de toda la app: letras, campos de texto, diálogos y avisos de abajo."""
    redondeado = ft.RoundedRectangleBorder(radius=24)
    return ft.Theme(
        color_scheme_seed=COLOR_PRINCIPAL,
        color_scheme=ft.ColorScheme(
            primary=COLOR_PRINCIPAL,
            on_primary=BLANCO,
            secondary=AMARILLO,
            on_secondary=TINTA,
            surface=BLANCO,
            on_surface=TINTA,
            on_surface_variant=GRIS,
            outline=GRIS,
            outline_variant=GRIS_SUAVE,
            error=ROJO,
        ),
        font_family=LETRA,
        scaffold_bgcolor=FONDO,
        divider_color=GRIS_SUAVE,
        appbar_theme=ft.AppBarTheme(
            bgcolor=FONDO,
            color=TINTA,
            elevation=0,
            title_text_style=estilo_titulo(24),
        ),
        dialog_theme=ft.DialogTheme(
            bgcolor=BLANCO,
            shape=redondeado,
            title_text_style=estilo_titulo(24),
            content_text_style=ft.TextStyle(font_family=LETRA, size=15, color=TINTA),
        ),
        snackbar_theme=ft.SnackBarTheme(
            bgcolor=TINTA,
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=14),
            content_text_style=ft.TextStyle(font_family=LETRA, size=14, weight=ft.FontWeight.W_500, color=BLANCO),
        ),
        input_decoration_theme=ft.InputDecorationTheme(
            border=ft.OutlineInputBorder(border_radius=14, side=ft.BorderSide(1, GRIS_SUAVE)),
            filled=True,
            fill_color=BLANCO,
            label_style=ft.TextStyle(color=GRIS),
            hint_style=ft.TextStyle(color="#94A09A"),
        ),
        popup_menu_theme=ft.PopupMenuTheme(
            color=BLANCO,
            shape=ft.RoundedRectangleBorder(radius=16),
            label_text_style=ft.TextStyle(font_family=LETRA, size=15, weight=ft.FontWeight.W_500, color=TINTA),
        ),
    )
