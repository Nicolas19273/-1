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
from urllib.parse import quote_plus
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
import lugares

# Render define estas variables; en tu computador no existen.
EN_INTERNET = "RENDER" in os.environ or "PORT" in os.environ
URL_PUBLICA = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")

# --------------------------------------------------------------------------- #
# Apariencia
# --------------------------------------------------------------------------- #

COLOR_PRINCIPAL = "#1F7A4D"  # verde cancha
TINTA = "#173B2B"  # texto y botones oscuros
AMARILLO = "#FFC93C"  # el «+1»: el cupo que falta y los botones principales
FONDO = "#FAF6EF"  # papel cálido
FUENTE = '"Nunito", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
FUENTES_WEB = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Fredoka:wght@500..700&family=Nunito:wght@400..800&family=Caveat:wght@600;700&display=swap">'
)
SEGUNDOS_ENTRE_REVISIONES = 3  # cada cuánto se buscan cambios para refrescar
MAX_CUPOS_DIBUJADOS = 16  # círculos por fila de cupos; el resto se resume

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

# Cada categoría tiene su color: (fuerte, suave). El fuerte se lee bien con texto blanco.
COLORES = {
    "futbol": ("#14713F", "#DDF0E3"),
    "basquetbol": ("#A8520F", "#FFE6D1"),
    "tenis_padel": ("#5A6A0B", "#EEF3C9"),
    "voleibol": ("#0E6E7E", "#D6EFF3"),
    "juegos_mesa": ("#5B3BA6", "#E9E1FA"),
    "videojuegos": ("#3B45B5", "#E0E3FB"),
    "estudio": ("#1F4E99", "#DCE9FB"),
    "salida": ("#A32458", "#FBE0EA"),
    "otro": ("#4E6157", "#E4EAE6"),
}

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

CIERRES = {
    datos.CANCELADO: ("event_busy", "Aviso cancelado", "Este aviso fue eliminado. El evento ya no se realiza."),
    datos.COMPLETO: ("groups", "¡Grupo completo!", "Ya están todos. Este aviso no recibe más gente."),
    datos.INICIADO: ("sports", "El evento ya comenzó", "El aviso se cerró a la hora del evento."),
    datos.VENCIDO: ("timer_off", "Aviso cerrado", "Se cumplió el plazo de {horas} horas."),
}

# Logo: dos caras sonrientes y un círculo amarillo con «+» (el que falta). Dibujado como SVG
# dentro de Python; se usa en la pestaña del navegador y en el encabezado.
LOGO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="20" fill="{COLOR_PRINCIPAL}"/>
<circle cx="19" cy="23" r="10" fill="#ffffff"/>
<circle cx="45" cy="23" r="10" fill="#ffffff"/>
<g fill="{TINTA}"><circle cx="15.6" cy="21.2" r="1.6"/><circle cx="22.4" cy="21.2" r="1.6"/>
<circle cx="41.6" cy="21.2" r="1.6"/><circle cx="48.4" cy="21.2" r="1.6"/></g>
<g fill="none" stroke="{TINTA}" stroke-width="2.1" stroke-linecap="round">
<path d="M15 25.8q4 3.6 8 0"/><path d="M41 25.8q4 3.6 8 0"/></g>
<circle cx="32" cy="45" r="11" fill="{AMARILLO}"/>
<path d="M32 39.6v10.8M26.6 45h10.8" stroke="{TINTA}" stroke-width="3.4" stroke-linecap="round"/>
</svg>"""
LOGO_URL = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()


def _icono_css(trazo: str) -> str:
    """Un ícono de línea como máscara CSS (toma el color del texto)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000" '
        f'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{trazo}</svg>'
    )
    return "url('data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode() + "')"


# Toda la apariencia en un solo lugar. Las clases «fu-…» se usan en las piezas
# de más abajo; el resto ajusta los componentes de NiceGUI/Quasar.
ESTILOS = (
    """<style>
:root {
  --tinta: #10241B; --verde: #14713F; --niebla: #EDF2EE; --suave: #F3F7F4;
  --amarillo: #FFD23F; --gris: #4E6157; --linea: #D5DFD8; --rojo: #8F2D1C; --rojo-suave: #FBE9E5;
}
body { -webkit-font-smoothing: antialiased; }
.fu-display { font-family: "Bricolage Grotesque", "DM Sans", system-ui, sans-serif; letter-spacing: -0.02em; }
.fu-gris { color: var(--gris); }
.fu-dato { color: #33473D; font-size: 15px; line-height: 1.4; }
.fu-hero { font-weight: 800; letter-spacing: -0.03em; line-height: 1.02; font-size: clamp(2.3rem, 5.2vw, 3.6rem); max-width: 16ch; }

/* Página: angosta en el celular, ancha en el computador */
.fu-contenedor { width: 100%; max-width: 1240px; margin: 0 auto; padding: 8px 4px 150px; display: flex; flex-direction: column; gap: 20px; }
.fu-angosto { max-width: 760px; }
@media (min-width: 768px) { .fu-contenedor { padding: 16px 24px 130px; gap: 24px; } }
.fu-rejilla { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; width: 100%; align-items: stretch; }
@media (min-width: 760px) { .fu-rejilla { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 1160px) { .fu-rejilla { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; } }
.fu-dos { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; width: 100%; align-items: start; }
@media (min-width: 1000px) { .fu-dos { grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr); gap: 20px; } }
.fu-columna { display: flex; flex-direction: column; gap: 16px; min-width: 0; }

/* Tarjetas */
.q-card.fu-card { background: #fff; border-radius: 28px; box-shadow: none; padding: 18px; gap: 14px; color: var(--tinta); }
@media (min-width: 768px) { .q-card.fu-card { padding: 22px; } }
@media (hover: hover) {
  .fu-card-viva { transition: transform .18s ease, box-shadow .18s ease; }
  .fu-card-viva:hover { transform: translateY(-3px); box-shadow: 0 14px 30px rgba(16, 36, 27, .10); }
}
.fu-icono-cat { width: 40px; height: 40px; border-radius: 14px; display: flex; align-items: center; justify-content: center; flex: none; }
.fu-titulo-tarjeta { font-size: 1.5rem; font-weight: 700; line-height: 1.12; }
.fu-titulo-tarjeta:hover { text-decoration: underline; text-decoration-thickness: 2px; text-underline-offset: 3px; }
.fu-titulo-aviso { font-size: clamp(1.9rem, 4vw, 2.5rem); font-weight: 800; line-height: 1.04; letter-spacing: -0.03em; }
.fu-cabecera { margin: -18px -18px 0; padding: 22px 20px 24px; border-radius: 28px 28px 24px 24px; color: #fff; }
@media (min-width: 768px) { .fu-cabecera { margin: -22px -22px 0; padding: 26px 26px 28px; } }
.fu-cabecera-texto { font-size: 15px; line-height: 1.45; opacity: .92; }
.fu-panel { background: var(--suave); border-radius: 20px; padding: 14px; }
.fu-falta { font-size: 1.6rem; font-weight: 800; line-height: 1.1; }
.fu-nota { background: var(--suave); border-radius: 18px; padding: 12px 16px; }
.fu-nota .text-xs { color: var(--gris); }
.fu-cierre { background: #fff; border-radius: 22px; padding: 16px; }
.fu-cierre-completo { background: var(--tinta); color: #fff; }
.fu-cierre-completo .q-icon { color: var(--amarillo); }

/* Cupos: un círculo por persona */
.fu-cupos { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.fu-cupo { width: 28px; height: 28px; border-radius: 14px; flex: none; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; font-weight: 700; line-height: 1; }
@media (max-width: 440px) { .fu-cupos { gap: 4px; } .fu-cupo { width: 25px; height: 25px; } }
.fu-acciones .q-btn.fu-cta { flex: 1 1 100%; }
.fu-cupo-libre { box-sizing: border-box; border: 2px dashed #9DB0A5; background: transparent; }
.fu-cupo-tuyo { background: var(--amarillo); color: var(--tinta); font-size: 18px; animation: fu-pulso 1.8s ease-out infinite; }
.fu-cupo-yo { background: var(--amarillo); color: var(--tinta); width: auto; padding: 0 10px; font-size: 12px; box-shadow: 0 0 0 4px rgba(255, 210, 63, .35); }
.fu-cupos-resto { font-size: 13px; font-weight: 700; color: var(--gris); padding: 0 4px; }
.fu-noche .fu-cupos-resto { color: #C9D6CE; }
.fu-noche .fu-cupo-libre { border-color: var(--amarillo); }
@keyframes fu-pulso { 0% { box-shadow: 0 0 0 0 rgba(255, 210, 63, .65); } 100% { box-shadow: 0 0 0 10px rgba(255, 210, 63, 0); } }
@keyframes fu-entra { from { transform: scale(.4); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.fu-festejo .fu-cupo { animation: fu-entra .35s cubic-bezier(.2, 1.4, .4, 1) backwards; }
.fu-festejo .fu-cupo:nth-child(n+2) { animation-delay: .04s; } .fu-festejo .fu-cupo:nth-child(n+4) { animation-delay: .08s; }
.fu-festejo .fu-cupo:nth-child(n+6) { animation-delay: .12s; } .fu-festejo .fu-cupo:nth-child(n+8) { animation-delay: .16s; }
.fu-festejo .fu-cupo:nth-child(n+10) { animation-delay: .2s; } .fu-festejo .fu-cupo-yo { animation-delay: .34s; }

/* Etiquetas y plazos */
.fu-etiqueta, .fu-plazo { display: inline-flex; flex-wrap: nowrap; align-items: center; gap: 5px; flex: none; border-radius: 14px; padding: 6px 10px; font-size: 13px; font-weight: 600; }
.fu-etiqueta { background: var(--amarillo); color: var(--tinta); }
.fu-etiqueta-roja { background: var(--rojo-suave); color: var(--rojo); }
.fu-plazo { background: var(--suave); color: var(--gris); }
.fu-plazo-pronto { background: #FFE9DC; color: #8A3A12; }
.fu-cabecera .fu-plazo { background: rgba(255, 255, 255, .18); color: #fff; }
.fu-avatar { width: 38px; height: 38px; border-radius: 19px; flex: none; display: flex; align-items: center; justify-content: center; background: var(--suave); color: var(--tinta); font-size: 13px; font-weight: 700; }
.fu-avatar-yo { background: var(--amarillo); }
.fu-avatar-organiza { background: var(--tinta); color: #fff; }
.fu-burbuja { background: var(--suave); border-radius: 4px 18px 18px 18px; padding: 9px 14px; min-width: 0; }

/* Botones */
.q-btn { transition: transform .12s ease, background-color .15s ease; }
.q-btn:active { transform: scale(.96); }
.q-btn.fu-cta, .q-btn.fu-oscuro, .q-btn.fu-blanco, .q-btn.fu-suave, .q-btn.fu-peligro, .q-btn.fu-chip {
  border-radius: 999px; font-weight: 600; min-height: 44px; padding: 0 18px; font-size: 15px;
}
.q-btn.fu-cta { background: var(--amarillo) !important; color: var(--tinta) !important; font-weight: 700; font-size: 17px; min-height: 52px; }
.q-btn.fu-cta:hover { background: #FFDB62 !important; }
.q-btn.fu-oscuro { background: var(--tinta) !important; color: #fff !important; }
.q-btn.fu-blanco { background: #fff !important; color: var(--tinta) !important; }
.q-btn.fu-suave { background: var(--suave) !important; color: var(--tinta) !important; }
.q-btn.fu-peligro { background: var(--rojo-suave) !important; color: var(--rojo) !important; }
.q-btn.fu-grande { min-height: 58px; font-size: 18px; }
.q-btn.fu-chip { background: #fff !important; color: var(--tinta) !important; flex: none; padding: 0 16px; }
.q-btn.fu-chip-suave { background: var(--suave) !important; }
.q-btn.fu-chip-activo { background: var(--tinta) !important; color: #fff !important; }
.fu-punto { width: 10px; height: 10px; border-radius: 5px; flex: none; margin-right: 8px; }
.fu-cuenta { margin-left: 8px; font-size: 13px; font-weight: 700; opacity: .65; }
.fu-insignia.q-badge { background: var(--amarillo); color: var(--tinta); font-weight: 700; font-size: 13px; min-width: 24px; height: 24px; border-radius: 12px; justify-content: center; margin-left: 8px; padding: 0 7px; }
.fu-accion { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 14px; border-radius: 22px; background: var(--suave); color: var(--tinta) !important; font-size: 15px; font-weight: 600; text-decoration: none !important; white-space: nowrap; transition: background-color .15s ease; }
.fu-accion:hover { background: #E4ECE6; }
.fu-llegar::before, .fu-comentar::before { content: ""; width: 18px; height: 18px; flex: none; background: currentColor; -webkit-mask: var(--icono) center / contain no-repeat; mask: var(--icono) center / contain no-repeat; }
.fu-llegar::before { --icono: ICONO_LLEGAR; }
.fu-comentar::before { --icono: ICONO_COMENTAR; }
.fu-noche .fu-accion { background: var(--suave); }
.fu-fab { position: fixed; z-index: 2000; left: 50%; transform: translateX(-50%); bottom: calc(20px + env(safe-area-inset-bottom)); }
@media (min-width: 768px) { .fu-fab { left: auto; right: 32px; bottom: 32px; transform: none; } }
.fu-fab .q-btn { min-height: 60px; padding: 0 26px 0 10px; font-size: 17px; font-weight: 700; box-shadow: 0 10px 24px rgba(16, 36, 27, .28); }
.fu-fab .q-btn .q-icon { background: var(--amarillo); color: var(--tinta); width: 40px; height: 40px; border-radius: 20px; font-size: 24px; margin-right: 12px; }

/* Formularios */
.q-field--outlined .q-field__control { border-radius: 16px; background: #fff; }
.q-field--outlined .q-field__control:before { border: 2px solid var(--linea); }
.q-field--outlined.q-field--rounded .q-field__control { border-radius: 28px; }
.fu-paso { display: flex; align-items: center; gap: 4px; background: var(--suave); border-radius: 26px; padding: 4px; flex: none; }
.fu-paso .q-btn { width: 44px; height: 44px; min-height: 44px; border-radius: 22px; background: #fff; color: var(--tinta); font-size: 22px; font-weight: 600; padding: 0; }
.fu-paso .q-field { width: 56px; }
.fu-paso .q-field__label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.fu-paso .q-field__control, .fu-paso .q-field__native { padding: 0; min-height: 44px; }
.fu-paso input { text-align: center; font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 24px; color: var(--tinta); -moz-appearance: textfield; }
.fu-paso input::-webkit-outer-spin-button, .fu-paso input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.fu-noche { background: var(--tinta) !important; color: #fff !important; }
.fu-previa { background: var(--tinta); color: #fff; border-radius: 20px; padding: 14px; }
.fu-previa .fu-falta { color: var(--amarillo); }
.q-btn-toggle.fu-opciones { background: var(--suave); border-radius: 26px; padding: 4px; box-shadow: none; }
.q-btn-toggle.fu-opciones .q-btn { border-radius: 22px !important; min-height: 44px; font-weight: 600; font-size: 15px; }

/* Diálogos: tarjeta al centro; el de crear ocupa toda la pantalla en el celular */
.q-dialog .q-card.fu-card { max-width: 94vw; }
.q-dialog .q-card.fu-gris-fondo { background: var(--niebla); }
.fu-seccion { background: #fff; border-radius: 24px; padding: 16px; display: flex; flex-direction: column; gap: 12px; width: 100%; }
@media (max-width: 599px) {
  .q-dialog__inner:has(.fu-pantalla) { padding: 0; }
  .q-dialog .q-card.fu-pantalla { width: 100vw !important; max-width: 100vw !important; height: 100dvh; max-height: 100dvh !important; border-radius: 0; }
}
:focus-visible { outline: 3px solid rgba(20, 113, 63, .55); outline-offset: 2px; }

/* ---- Capa «humana»: papel cálido, letras redondas, notas a mano y caras en los cupos ---- */
:root { --tinta: #173B2B; --verde: #1F7A4D; --niebla: #FAF6EF; --suave: #F2F3E8; --amarillo: #FFC93C; --gris: #56695E; --linea: #DCD9C7; }
.fu-display { font-family: "Fredoka", "Nunito", system-ui, sans-serif; letter-spacing: -0.005em; }
.fu-hero { font-weight: 600; line-height: 1.05; letter-spacing: -0.01em; }
.fu-hero::after { content: ""; display: block; width: min(230px, 62%); height: 14px; margin-top: 8px; background: var(--amarillo); -webkit-mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0NiIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDQ2IDE0Ij48cGF0aCBkPSJNMCA5IFEgMTEuNTAwIDAgMjMgNyBUIDQ2IDUiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzAwMCIgc3Ryb2tlLXdpZHRoPSI0IiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48L3N2Zz4=') left center / auto 100% repeat-x; mask: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0NiIgaGVpZ2h0PSIxNCIgdmlld0JveD0iMCAwIDQ2IDE0Ij48cGF0aCBkPSJNMCA5IFEgMTEuNTAwIDAgMjMgNyBUIDQ2IDUiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzAwMCIgc3Ryb2tlLXdpZHRoPSI0IiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48L3N2Zz4=') left center / auto 100% repeat-x; }
.fu-titulo-tarjeta { font-weight: 600; } .fu-titulo-aviso, .fu-falta { font-weight: 600; letter-spacing: 0; }
.fu-mano { font-family: "Caveat", "Nunito", cursive; font-weight: 700; font-size: 1.35rem; line-height: 1.1; color: var(--verde); }
.fu-noche .fu-mano, .fu-previa .fu-mano { color: var(--amarillo); }
.q-card.fu-card { border-radius: 30px 26px 32px 24px; box-shadow: 0 1px 0 rgba(23, 59, 43, .05), 0 10px 26px rgba(23, 59, 43, .06); }
.fu-panel, .fu-previa { border-radius: 22px 18px 24px 18px; }
.fu-seccion { border-radius: 26px 22px 28px 22px; }
.fu-icono-cat { border-radius: 16px 12px 16px 14px; }
.fu-cupo-cara { background-image: url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyOCAyOCI+PGNpcmNsZSBjeD0iMTAuMiIgY3k9IjEyIiByPSIxLjUiIGZpbGw9IiNmZmYiLz48Y2lyY2xlIGN4PSIxNy44IiBjeT0iMTIiIHI9IjEuNSIgZmlsbD0iI2ZmZiIvPjxwYXRoIGQ9Ik05LjYgMTYuNDAwcTQuNDAwIDMuODAwIDguODAwIDAiIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjkwMCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIi8+PC9zdmc+'); background-size: 100% 100%; }
.fu-paso input { font-family: "Fredoka", sans-serif; font-weight: 600; }
.fu-opciones .q-btn, .q-btn { font-family: inherit; }
/* Cómo funciona: tres pasos */
.fu-como.q-expansion-item { background: #fff; border-radius: 26px 22px 28px 22px; overflow: hidden; box-shadow: 0 1px 0 rgba(23, 59, 43, .05), 0 10px 26px rgba(23, 59, 43, .06); }
.fu-como .q-item { min-height: 56px; font-weight: 800; font-size: 16px; }
.fu-pasos { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; width: 100%; }
@media (min-width: 760px) { .fu-pasos { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; } }
.fu-numero { width: 38px; height: 38px; border-radius: 19px; flex: none; background: var(--amarillo); color: var(--tinta); display: flex; align-items: center; justify-content: center; font-family: "Fredoka", sans-serif; font-weight: 600; font-size: 20px; }
.fu-guia { background: #FFF3CF; border-radius: 20px 16px 22px 16px; padding: 12px 16px; color: var(--tinta); }
/* Administración: pestañas como botones */
.fu-pestanas .q-tab { border-radius: 999px; min-height: 46px; text-transform: none; font-weight: 800; margin-right: 6px; background: #fff; }
.fu-pestanas .q-tab--active { background: var(--tinta); color: #fff; }
.fu-pestanas .q-tab__indicator { display: none; }
.fu-pestanas .q-tab__label { font-size: 15px; }
.fu-cifra { font-family: "Fredoka", sans-serif; font-weight: 600; font-size: 2.2rem; line-height: 1; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
</style>""".replace("ICONO_LLEGAR", _icono_css('<path d="M4 11l16-7-7 16-2-7z"/>')).replace(
        "ICONO_COMENTAR", _icono_css('<path d="M5 5h14v10H10l-5 4z"/>')
    )
)

# Para la pestaña del navegador NiceGUI pide un archivo: lo escribimos al iniciar.
RUTA_FAVICON = Path(tempfile.gettempdir()) / "falta_uno_logo.svg"
RUTA_FAVICON.write_text(LOGO_SVG, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Quién es quién: un identificador al azar por navegador (cookie)
# --------------------------------------------------------------------------- #

# Marca en rojo el campo mientras se escribe si tiene palabras inapropiadas.
SIN_GROSERIAS = {"Tiene palabras inapropiadas: cámbialas para poder publicar.": lambda v: not filtro.contiene(v)}
NOMBRE_SIN_GROSERIAS = {"Ese nombre no está permitido. Usa tu nombre real o un apodo amable.": lambda v: not filtro.contiene(v)}

VALOR_EN_PESOS = {
    "Solo números, por ejemplo 2000 o 2.000": lambda v: not v or datos.formato_valor_ok(v),
    f"El máximo es ${datos.VALOR_MAXIMO:,} por persona".replace(",", "."): (
        lambda v: not v
        or not datos.formato_valor_ok(v)
        or int(v.replace(".", "")) <= datos.VALOR_MAXIMO
    ),
}

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
    return minuto, tuple((a.id, a.ocupados, a.motivo_cierre(momento), a.comentarios) for a in avisos)


def url_mapa(lugar: str, lat: float | None = None, lng: float | None = None) -> str:
    """Indicaciones de Google Maps hasta el lugar (en el celular abre la app).
    Si el aviso tiene la ubicación exacta, va directo a ese punto."""
    destino = f"{lat},{lng}" if lat is not None and lng is not None else lugar
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote_plus(destino)


def url_mapa_de(aviso: datos.Aviso) -> str:
    return url_mapa(aviso.lugar, aviso.lat, aviso.lng)


# --------------------------------------------------------------------------- #
# Mapas
# --------------------------------------------------------------------------- #
# Estilo: CARTO Voyager (moderno, nítido en celulares) si existe la variable de
# entorno CARTO_KEY (gratis: carto.com/basemaps/apikey). Sin clave se usa el
# mapa estándar de OpenStreetMap, con colores suavizados. Ver README.
CARTO_KEY = os.environ.get("CARTO_KEY", "").strip()
URL_CARTO = "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key="
CREDITO_CARTO = (
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, '
    '© <a href="https://carto.com/attributions">CARTO</a>'
)
URL_OSM = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CREDITO_OSM = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
ZOOM_CON_IMAGEN = 18  # hasta aquí hay imágenes del mapa en ambos estilos
ZOOM_MAXIMO = 20  # hasta aquí se puede acercar (las imágenes se amplían)
METROS_MISMO_LUGAR = 80  # si el pin se aleja más que esto del lugar buscado, es otro punto

# Pin fijo al centro del mapa: se mueve el mapa, no el pin (como en las apps de
# delivery). La punta queda justo en el centro.
PIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="52" height="66" viewBox="0 0 44 56">'
    f'<path d="M22 3.5C13 3.5 5.7 10.6 5.7 19.4c0 11.7 13.6 25.6 15 27a1.9 1.9 0 0 0 2.6 0c1.4-1.4 '
    f'15-15.3 15-27C38.3 10.6 31 3.5 22 3.5z" fill="{TINTA}" stroke="#fff" stroke-width="2.6"/>'
    f'<circle cx="22" cy="19.4" r="7.4" fill="{AMARILLO}"/>'
    f'<path d="M22 15.6v7.6M18.2 19.4h7.6" stroke="{TINTA}" stroke-width="2.4" stroke-linecap="round"/></svg>'
)
PIN_URL = "data:image/svg+xml;base64," + base64.b64encode(PIN_SVG.encode()).decode()

ESTILOS_MAPA = f"""<style>
.mapa-fu {{ position: relative; isolation: isolate; overflow: hidden; background: #e8ebe4; }}
.mapa-fu .leaflet-container {{ background: #e8ebe4; font-family: inherit; }}
.mapa-fu .leaflet-control-attribution {{
  font-size: 10px; line-height: 16px; padding: 0 6px; color: #57534e;
  background: rgba(255, 255, 255, .8) !important; border-top-left-radius: 8px;
}}
.mapa-fu .leaflet-control-attribution a {{ color: #44403c; }}
.mapa-fu .leaflet-attribution-flag {{ display: none !important; }}
.mapa-fu .leaflet-bar {{
  border: none !important; border-radius: 12px !important; overflow: hidden;
  box-shadow: 0 2px 10px rgba(0, 0, 0, .18) !important;
}}
.mapa-fu .leaflet-bar a {{
  width: 34px !important; height: 34px !important; line-height: 34px !important; color: #292524 !important;
}}
.mapa-fu.mapa-suave .leaflet-tile-pane {{ filter: saturate(.5) brightness(1.05) contrast(.95); }}
.mapa-fu .pin-centro {{
  position: absolute; left: 50%; top: 50%; width: 52px; height: 66px; margin: -56px 0 0 -26px;
  pointer-events: none; z-index: 650; background: url("{PIN_URL}") no-repeat center / contain;
  filter: drop-shadow(0 6px 8px rgba(16, 36, 27, .28));
}}
.mapa-fu .pin-centro::after {{
  content: ""; position: absolute; left: 50%; top: 56px; width: 14px; height: 14px; margin: -7px 0 0 -7px;
  border-radius: 50%; border: 2px solid {TINTA}; background: rgba(255, 210, 63, .55); z-index: -1;
  animation: fu-punto-mapa 1.8s ease-out infinite;
}}
@keyframes fu-punto-mapa {{ 0% {{ box-shadow: 0 0 0 0 rgba(16, 36, 27, .35); }} 100% {{ box-shadow: 0 0 0 14px rgba(16, 36, 27, 0); }} }}
.mapa-fu .fu-flotante {{ background: #fff; border-radius: 22px; box-shadow: 0 6px 18px rgba(16, 36, 27, .18); }}
.fu-hoja {{ position: relative; z-index: 1200; margin-top: -24px; background: #fff; border-radius: 28px 28px 0 0; box-shadow: 0 -8px 24px rgba(16, 36, 27, .12); }}
</style>"""

# El mapa ocupa todo su contenedor (sin altura mínima propia: si no, el pin
# del centro quedaría corrido).
ESTILO_LLENAR = "position: absolute; inset: 0; width: 100%; height: 100%; min-height: 0"

# Pide la ubicación al navegador (solo cuando la persona toca el botón).
JS_MI_UBICACION = (
    "new Promise((listo) => {"
    " if (!navigator.geolocation) { listo(null); return; }"
    " navigator.geolocation.getCurrentPosition("
    "  (p) => listo([p.coords.latitude, p.coords.longitude]),"
    "  () => listo(null),"
    "  {enableHighAccuracy: true, timeout: 10000, maximumAge: 60000});"
    "})"
)


def clases_mapa() -> str:
    return "mapa-fu" + ("" if CARTO_KEY else " mapa-suave")


def opciones_selector() -> dict:
    """Mapa para elegir: se arrastra y se acerca, pero no sale de Osorno."""
    oeste, sur, este, norte = lugares.ZONA
    return {
        "zoomControl": False,  # usamos botones propios, más grandes
        "scrollWheelZoom": True,
        "minZoom": lugares.ZOOM_MINIMO,
        "maxZoom": ZOOM_MAXIMO,
        "maxBounds": [[sur, oeste], [norte, este]],
        "maxBoundsViscosity": 1.0,
    }


def opciones_vista(controles: bool = True) -> dict:
    """
    Mapa para mirar: no se arrastra (la página se desplaza normal encima) y el
    zoom siempre es hacia el centro, así el pin del centro nunca se corre.
    """
    opciones: dict = {
        "dragging": False,
        "scrollWheelZoom": False,
        "boxZoom": False,
        "keyboard": False,
        "minZoom": lugares.ZOOM_MINIMO,
        "maxZoom": ZOOM_MAXIMO,
        "zoomControl": controles,
    }
    if controles:
        opciones.update(touchZoom="center", doubleClickZoom="center")
    else:
        opciones.update(touchZoom=False, doubleClickZoom=False)
    return opciones


def mapa_base(centro, zoom: int, opciones: dict):
    """Un mapa que llena su contenedor, con el estilo de la página."""
    mapa = ui.leaflet(center=tuple(centro), zoom=zoom, options=opciones).style(ESTILO_LLENAR)
    # La capa se define siempre aquí. «maxNativeZoom» es hasta dónde existen
    # imágenes del mapa; más cerca que eso, se amplía la última en vez de
    # quedar en gris.
    mapa.clear_layers()
    if CARTO_KEY:
        mapa.tile_layer(
            url_template=URL_CARTO + CARTO_KEY,
            options={"maxNativeZoom": ZOOM_CON_IMAGEN, "maxZoom": ZOOM_MAXIMO, "attribution": CREDITO_CARTO},
        )
    else:
        mapa.tile_layer(
            url_template=URL_OSM,
            options={"maxNativeZoom": ZOOM_CON_IMAGEN, "maxZoom": ZOOM_MAXIMO, "attribution": CREDITO_OSM},
        )
    def ajustar_tamano() -> None:  # por si se dibuja dentro de algo que recién aparece (un diálogo)
        mapa.run_map_method("invalidateSize")  # sin esperar respuesta (devuelve el mapa entero)

    ui.timer(0.5, ajustar_tamano, once=True)
    return mapa


def pin_centro() -> None:
    ui.element("div").classes("pin-centro")


def mapa_de_vista(lat: float, lng: float, alto: str = "15rem", controles: bool = True, zoom: int = 16):
    """Mapa para mirar dónde es, con el pin al centro. None si no se pudo dibujar."""
    try:
        with ui.element("div").classes(f"{clases_mapa()} w-full rounded-2xl border border-stone-200").style(
            f"height: {alto}"
        ) as caja:
            mapa = mapa_base((lat, lng), zoom, opciones_vista(controles))
            pin_centro()
        return caja, mapa
    except Exception as error:  # el mapa es un extra: si falla, el resto sigue
        print(f"[mapa] no se pudo dibujar: {error}", flush=True)
        return None


def _punto(valor) -> tuple[float, float] | None:
    """[lat, lng] o {"lat":…, "lng":…} -> (lat, lng). None si no se entiende."""
    try:
        if isinstance(valor, dict):
            return float(valor["lat"]), float(valor["lng"])
        return float(valor[0]), float(valor[1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def abrir_selector_ubicacion(
    capa: ui.element,
    *,
    lat: float | None,
    lng: float | None,
    consulta: str,
    al_confirmar: Callable,
) -> None:
    """
    Pantalla completa para elegir el punto, como en las apps de delivery:
    se busca o se mueve el mapa, el pin queda fijo al centro y se confirma.
    al_confirmar(lat, lng, lugar_buscado_o_None) se llama al tocar «Usar este punto».
    """
    hay_punto = lat is not None and lng is not None
    centro_inicial = (lat, lng) if hay_punto else lugares.CENTRO
    estado: dict = {"centro": centro_inicial, "elegido": None}

    async def buscar() -> None:
        boton_buscar.props("loading")
        try:
            encontrados = await asyncio.to_thread(lugares.buscar, campo.value)
        except lugares.ErrorBusqueda as error:
            ui.notify(str(error), type="warning", position="top")
            return
        finally:
            boton_buscar.props(remove="loading")
        mostrar_resultados(encontrados)

    def mostrar_resultados(encontrados: list) -> None:
        resultados.clear()
        with resultados, ui.card().classes("fu-card w-full max-w-2xl gap-1").style("padding: 10px; box-shadow: 0 10px 28px rgba(16, 36, 27, .2)"):
            with ui.row().classes("w-full items-center justify-between no-wrap pl-2"):
                ui.label(f"Resultados en {lugares.NOMBRE_ZONA}").classes(
                    "text-xs font-bold tracking-wide text-stone-500"
                )
                ui.button(icon="close", on_click=lambda: resultados.set_visibility(False)).props(
                    "flat round dense size=sm color=grey-7"
                )
            if not encontrados:
                with ui.row().classes("w-full items-center gap-3 no-wrap px-2 pb-2"):
                    ui.icon("search_off", size="22px").classes("text-stone-400 shrink-0")
                    ui.label(
                        f"No encontramos eso en {lugares.NOMBRE_ZONA}. Prueba con otro nombre o una "
                        "calle, o mueve el mapa hasta el lugar."
                    ).classes("text-sm text-stone-600")
            for lugar in encontrados:
                with ui.row().classes(
                    "w-full items-center gap-3 no-wrap rounded-2xl px-2 py-2 cursor-pointer hover:bg-stone-100"
                ).on("click", partial(elegir, lugar)):
                    with ui.element("div").classes("fu-avatar"):
                        ui.icon(lugar.icono, size="20px").classes("text-primary")
                    with ui.column().classes("gap-0 min-w-0 flex-1"):
                        ui.label(lugar.nombre).classes("font-semibold text-stone-900 leading-tight")
                        detalle = " · ".join(x for x in (lugar.tipo, lugar.detalle_corto) if x)
                        if detalle:
                            ui.label(detalle).classes("text-xs text-stone-500 ellipsis")
            ui.label("Datos de lugares © OpenStreetMap").classes("text-[10px] text-stone-400 px-2")
        resultados.set_visibility(True)

    def elegir(lugar) -> None:
        estado.update(elegido=lugar, centro=(lugar.lat, lugar.lng))
        resultados.set_visibility(False)
        mapa.run_map_method("flyTo", [lugar.lat, lugar.lng], 17)
        referencia.text = lugar.nombre + (f" · {lugar.detalle_corto}" if lugar.detalle_corto else "")

    def al_mover(evento) -> None:
        punto = _punto((getattr(evento, "args", None) or {}).get("center"))
        if punto is None:
            return
        estado["centro"] = punto
        elegido = estado["elegido"]
        if elegido is not None and lugares.metros(*punto, elegido.lat, elegido.lng) > METROS_MISMO_LUGAR:
            estado["elegido"] = None
            referencia.text = "Punto elegido a mano: el evento queda donde apunta el pin."

    def al_tocar(evento) -> None:
        punto = _punto((getattr(evento, "args", None) or {}).get("latlng"))
        if punto is not None:
            mapa.run_map_method("panTo", list(punto))  # tocar = llevar el pin ahí

    async def ir_a_mi_ubicacion() -> None:
        boton_gps.props("loading")
        try:
            punto = _punto(await ui.run_javascript(JS_MI_UBICACION, timeout=15))
        except Exception:
            punto = None
        finally:
            boton_gps.props(remove="loading")
        if punto is None:
            ui.notify(
                "No pudimos ver tu ubicación. Revisa que el navegador tenga permiso.",
                type="warning",
                position="top",
            )
            return
        if not lugares.dentro_de_zona(*punto):
            ui.notify(
                f"Parece que no estás en {lugares.NOMBRE_ZONA}. Busca el lugar o mueve el mapa.",
                type="info",
                position="top",
            )
            return
        estado.update(elegido=None, centro=punto)
        mapa.run_map_method("flyTo", list(punto), 17)
        referencia.text = "Tu ubicación actual. Ajusta el mapa si hace falta."

    # Los métodos del mapa se llaman sin esperar respuesta (devuelven el mapa entero).
    def acercar() -> None:
        mapa.run_map_method("zoomIn")

    def alejar() -> None:
        mapa.run_map_method("zoomOut")

    async def centro_actual() -> tuple[float, float]:
        """Lo pregunta al navegador; si no responde, usa el último movimiento conocido."""
        try:
            punto = _punto(await mapa.run_map_method("getCenter", timeout=3))
        except Exception:
            punto = None
        return punto or estado["centro"]

    async def confirmar() -> None:
        punto = await centro_actual()
        if not lugares.dentro_de_zona(*punto):
            ui.notify(
                f"Por ahora solo se pueden marcar lugares de {lugares.NOMBRE_ZONA}.",
                type="warning",
                position="top",
            )
            return
        elegido = estado["elegido"]
        if elegido is not None and lugares.metros(*punto, elegido.lat, elegido.lng) > METROS_MISMO_LUGAR:
            elegido = None
        selector.close()
        resultado = al_confirmar(punto[0], punto[1], elegido)
        if asyncio.iscoroutine(resultado):
            await resultado

    with capa, ui.dialog().props(
        "maximized transition-show=slide-up transition-hide=slide-down"
    ) as selector:
        with ui.element("div").classes("w-full h-full").style(
            f"display: flex; flex-direction: column; overflow: hidden; background: {FONDO}; color: {TINTA}"
        ):
            # Arriba: volver, título y buscador
            with ui.element("div").classes("w-full px-3 pt-3 pb-3").style("flex: none"):
                with ui.row().classes("w-full items-center gap-3 no-wrap"):
                    ui.button(icon="arrow_back", on_click=selector.close).props("flat round").classes(
                        "fu-blanco"
                    )
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label("¿Dónde es el evento?").classes(
                            "fu-display text-2xl font-extrabold leading-tight"
                        )
                        ui.label("Mueve el mapa hasta dejar el pin en el lugar").classes(
                            "fu-gris text-sm"
                        )
                with ui.row().classes("w-full items-center gap-2 no-wrap mt-3 max-w-2xl"):
                    campo = ui.input(
                        placeholder="Cancha, calle, parque…", value=consulta
                    ).props("outlined rounded enterkeyhint=search").classes("flex-1")
                    with campo.add_slot("prepend"):
                        ui.icon("search", size="22px").classes("fu-gris")
                    boton_buscar = ui.button("Buscar", on_click=buscar).props(
                        "unelevated no-caps"
                    ).classes("fu-oscuro")
                campo.on("keydown.enter", buscar)  # Enter = buscar (nunca mientras escribe)

            # Al medio: el mapa con el pin fijo, resultados y botones flotantes
            with ui.element("div").classes(clases_mapa()).style("flex: 1 1 auto; min-height: 0"):
                mapa = mapa_base(
                    centro_inicial, 17 if hay_punto else 14, opciones_selector()
                )
                mapa.on("map-moveend", al_mover)
                mapa.on("map-click", al_tocar)
                pin_centro()
                resultados = ui.element("div").classes("absolute top-0 inset-x-0 p-2").style(
                    "z-index: 1100; max-height: 70%; overflow-y: auto"
                )
                resultados.set_visibility(False)
                with ui.column().classes("absolute gap-2 items-center").style(
                    "right: 12px; bottom: 52px; z-index: 1050"
                ):
                    with ui.element("div").classes("fu-flotante"):
                        boton_gps = ui.button(icon="my_location", on_click=ir_a_mi_ubicacion).props(
                            "flat round size=lg color=primary"
                        ).tooltip("Mi ubicación")
                    with ui.column().classes("fu-flotante gap-0 overflow-hidden"):
                        ui.button(icon="add", on_click=acercar).props("flat round size=lg color=dark")
                        ui.button(icon="remove", on_click=alejar).props("flat round size=lg color=dark")

            # Abajo: a qué corresponde el punto y confirmar
            with ui.element("div").classes("fu-hoja w-full px-4 pt-4").style(
                "flex: none; padding-bottom: calc(16px + env(safe-area-inset-bottom))"
            ), ui.column().classes("w-full max-w-2xl mx-auto gap-0"):
                with ui.row().classes("w-full items-center gap-3 no-wrap"):
                    with ui.element("div").classes("fu-avatar fu-avatar-yo"):
                        ui.icon("place", size="22px")
                    referencia = ui.label(
                        "Este es el punto que marcaste. Mueve el mapa si hace falta."
                        if hay_punto
                        else "Busca el lugar o mueve el mapa: el evento queda donde apunta el pin."
                    ).classes("font-semibold leading-snug")
                ui.button("Usar este punto", icon="check", on_click=confirmar).props(
                    "unelevated no-caps"
                ).classes("fu-cta fu-grande w-full mt-3")

    selector.on("hide", selector.delete)  # se borra al cerrarse
    selector.open()


def texto_hace(momento: datetime, referencia: datetime) -> str:
    segundos = int((referencia - momento).total_seconds())
    if segundos < 60:
        return "recién"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    if segundos < 86400:
        return f"hace {segundos // 3600} h"
    return texto_fecha_evento(momento, referencia)


def texto_comentarios(n: int) -> str:
    if n == 0:
        return "Comentar"
    return f"{n} comentario{'s' if n != 1 else ''}"


ESTILO_ACCION = "fu-accion"


# --------------------------------------------------------------------------- #
# Piezas reutilizables
# --------------------------------------------------------------------------- #


def preparar_pagina() -> None:
    ui.colors(primary=COLOR_PRINCIPAL)
    ui.query("body").style(f"background-color: {FONDO}; color: {TINTA}; font-family: {FUENTE}")
    ui.add_head_html(FUENTES_WEB)
    ui.add_head_html(ESTILOS)
    ui.add_head_html(ESTILOS_MAPA)


def colores_de(categoria: str) -> tuple[str, str]:
    """(color fuerte, color suave) de la categoría."""
    return COLORES.get(categoria, COLORES["otro"])


def iniciales(nombre: str | None) -> str:
    partes = (nombre or "").split()
    if not partes:
        return "?"
    return (partes[0][:1] + (partes[1][:1] if len(partes) > 1 else "")).upper()


def encabezado(persona_id: str | None) -> Callable[[], None]:
    """Logo + botón «Buzón» con contador. Devuelve la función que actualiza el contador."""
    with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
        with ui.row().classes("items-center gap-3 no-wrap cursor-pointer").on(
            "click", lambda: ui.navigate.to("/")
        ):
            ui.image(LOGO_URL).props("no-spinner no-transition").classes("w-11 h-11 shrink-0")
            with ui.column().classes("gap-0"):
                ui.label("Falta Uno").classes("fu-display text-2xl font-extrabold leading-none")
                ui.label("Avisos para completar el grupo").classes("fu-gris text-sm max-sm:hidden")
        with ui.button("Buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
            "unelevated no-caps"
        ).classes("fu-blanco shrink-0"):
            contador = ui.badge("").classes("fu-insignia")

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


PASOS = [
    ("Publica lo que te falta", "Cuenta qué van a hacer, dónde, a qué hora y cuántas personas faltan."),
    ("Otros se suman con su nombre", "Sin cuentas ni contraseñas: tocan «Unirme», escriben su nombre y listo."),
    ("Se completa y se cierra solo", "Cuando ya no falta nadie, el aviso sale del tablero. Queda guardado en tu buzón."),
]


def como_funciona(abierto: bool) -> None:
    """Explicación en tres pasos; abierta si el tablero está vacío."""
    with ui.expansion("¿Cómo funciona Falta Uno?", icon="help_outline", value=abierto).classes("fu-como w-full"):
        with ui.element("div").classes("fu-pasos"):
            for numero, (titulo, texto) in enumerate(PASOS, start=1):
                with ui.row().classes("items-start gap-3 no-wrap"):
                    ui.label(str(numero)).classes("fu-numero")
                    with ui.column().classes("gap-0.5"):
                        ui.label(titulo).classes("font-extrabold leading-tight")
                        ui.label(texto).classes("fu-gris text-sm")


def guia(texto: str) -> None:
    """Nota amarilla que explica para qué sirve lo que viene."""
    with ui.row().classes("fu-guia w-full items-start gap-3 no-wrap"):
        ui.icon("lightbulb", size="22px").classes("shrink-0 mt-0.5")
        ui.label(texto).classes("text-sm font-semibold")


def volver_al_tablero() -> None:
    ui.button("Ver todos los avisos", icon="arrow_back", on_click=lambda: ui.navigate.to("/")).props(
        "flat no-caps"
    ).classes("fu-blanco self-start")


def dato(icono: str, texto: str) -> None:
    with ui.row().classes("items-start gap-2.5 no-wrap"):
        ui.icon(icono, size="19px").classes("fu-gris mt-0.5 shrink-0")
        ui.label(texto).classes("fu-dato whitespace-pre-line")


def datos_clave(aviso: datos.Aviso, momento: datetime) -> None:
    """Dónde, cuándo y cuánto cuesta."""
    with ui.column().classes("gap-2"):
        dato("place", aviso.lugar)
        dato("event", texto_fecha_evento(aviso.inicio_evento, momento))
        if aviso.valor is not None:
            dato("payments", datos.texto_valor(aviso.valor))


def etiqueta(texto: str, icono: str, rojo: bool = False) -> None:
    with ui.row().classes("fu-etiqueta" + (" fu-etiqueta-roja" if rojo else "")):
        ui.icon(icono, size="15px")
        ui.label(texto).classes("whitespace-nowrap")


def fila_cupos(aviso: datos.Aviso, persona_id: str | None, puede_unirse: bool) -> None:
    """
    Un círculo por cupo: los ocupados van rellenos (con iniciales si se unieron
    por la página), los libres punteados y, si puedes unirte, el siguiente
    libre en amarillo con un «+»: ese es el tuyo.
    """
    fuerte, _ = colores_de(aviso.categoria)
    cupos: list[tuple[str, str]] = [("grupo", "")] * aviso.personas_actuales
    for p in aviso.inscritos:
        soy_yo = bool(persona_id) and p.persona_id == persona_id
        cupos.append(("yo", "Tú") if soy_yo else ("persona", iniciales(p.nombre)))
    libres = max(aviso.personas_necesarias - len(cupos), 0)
    if libres:
        cupos.append(("siguiente", "+") if puede_unirse else ("libre", ""))
        cupos.extend([("libre", "")] * (libres - 1))

    # Grupos grandes: se resumen los del principio (y, si hace falta, los del final)
    sobran = max(len(cupos) - MAX_CUPOS_DIBUJADOS, 0)
    al_inicio = min(sobran, max(aviso.personas_actuales - 1, 0))
    al_final = sobran - al_inicio
    cupos = cupos[al_inicio : len(cupos) - al_final]

    with ui.row().classes("fu-cupos"):
        if al_inicio:
            ui.label(f"{al_inicio} +").classes("fu-cupos-resto")
        for tipo, texto in cupos:
            if tipo == "grupo":
                ui.element("div").classes("fu-cupo fu-cupo-cara").style(f"background-color: {fuerte}")
            elif tipo == "persona":
                ui.label(texto).classes("fu-cupo").style(f"background-color: {fuerte}")
            elif tipo == "yo":
                ui.label(texto).classes("fu-cupo fu-cupo-yo")
            elif tipo == "siguiente":
                ui.label(texto).classes("fu-cupo fu-cupo-tuyo")
            else:
                ui.element("div").classes("fu-cupo fu-cupo-libre")
        if al_final:
            ui.label(f"+ {al_final}").classes("fu-cupos-resto")


def barra_cupos(aviso: datos.Aviso, persona_id: str | None = None, puede_unirse: bool = False) -> None:
    """Recuadro «Falta 1 persona» con la fila de cupos."""
    with ui.column().classes("fu-panel w-full gap-3"):
        with ui.row().classes("w-full items-baseline justify-between gap-2"):
            ui.label(texto_faltan(aviso.cupos_libres)).classes("fu-display fu-falta")
            ui.label(f"{aviso.ocupados} de {aviso.personas_necesarias}").classes("fu-gris text-sm")
        fila_cupos(aviso, persona_id, puede_unirse)


def fila_persona(inicial: str | None, nombre: str, detalle: str, destacado: bool = False, icono: str | None = None) -> None:
    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        color = "fu-avatar-yo" if destacado else ""
        if icono:
            with ui.element("div").classes(f"fu-avatar {color}"):
                ui.icon(icono, size="20px")
        else:
            ui.label(iniciales(inicial)).classes(f"fu-avatar {color}")
        with ui.column().classes("gap-0"):
            ui.label(nombre).classes("font-semibold leading-tight")
            ui.label(detalle).classes("fu-gris text-xs")


def lista_quienes(aviso: datos.Aviso, persona_id: str | None) -> None:
    ui.label("Quiénes van").classes("text-base font-bold mt-1")
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
    clase = "fu-cierre fu-cierre-completo" if motivo == datos.COMPLETO else "fu-cierre"
    with ui.row().classes(f"w-full items-center gap-3 no-wrap {clase}"):
        ui.icon(icono, size="28px").classes("shrink-0")
        with ui.column().classes("gap-0"):
            ui.label(titulo).classes("fu-display text-lg font-bold")
            ui.label(texto.format(horas=aviso.duracion_horas)).classes("text-sm")


def estado_en_buzon(aviso: datos.Aviso, momento: datetime, persona_id: str | None) -> None:
    """Recuadro al pie de cada tarjeta del buzón: cómo va y hasta cuándo se ve."""
    if aviso.es_de(persona_id):
        if aviso.esta_lleno:
            principal = "¡Se completó el grupo!"
        elif aviso.esta_abierto(momento):
            principal = "Buscando gente · " + texto_tiempo_restante(aviso.cierra_en, momento).lower()
        else:
            principal = "Ya no recibe más gente"
        secundario = f"Lo verás aquí hasta {texto_cuando(aviso.expira_en, momento)}."
    elif aviso.cancelado:
        if aviso.cancelado_por == "admin":
            principal = "Cancelado por la administración"
        else:
            principal = "Cancelado por quien lo publicó"
        secundario = "Este evento ya no se realiza. Puedes quitarlo de tu buzón."
    else:
        if momento >= aviso.inicio_evento:
            principal = "El evento ya empezó"
        elif aviso.esta_lleno:
            principal = "¡Grupo completo! Nos vemos ahí"
        else:
            principal = "Estás anotado · todavía " + texto_faltan(aviso.cupos_libres).lower()
        secundario = f"Se quita de tu buzón {texto_cuando(aviso.visible_en_buzon_hasta, momento)}."
    with ui.column().classes("fu-nota w-full gap-0"):
        ui.label(principal).classes("font-bold")
        ui.label(secundario).classes("text-xs")


def tarjeta_aviso(
    aviso: datos.Aviso,
    momento: datetime,
    persona_id: str | None,
    al_unirse: Callable[[int], None],
    al_salirse: Callable[[int], None],
    al_eliminar: Callable[[int], None],
    al_denunciar: Callable[[int], None],
    modo: str = "tablero",  # "tablero" | "detalle" | "buzon"
) -> None:
    abierto = aviso.esta_abierto(momento)
    mio = aviso.es_de(persona_id)
    anotado = aviso.tiene_inscrito(persona_id)
    puede_salirse = anotado and (aviso.cancelado or momento < aviso.inicio_evento)
    puede_unirse = not mio and not anotado and abierto and modo != "buzon"
    fuerte, suave = colores_de(aviso.categoria)
    detalle = modo == "detalle"

    def estado_arriba() -> None:
        """A la derecha: tu rol o la cuenta regresiva."""
        if aviso.cancelado:
            etiqueta("Cancelado", "block", rojo=True)
        elif mio:
            etiqueta("Tu aviso", "star")
        elif anotado:
            etiqueta("Anotado", "check")
        elif abierto:
            apuro = (aviso.cierra_en - momento) <= timedelta(hours=6)
            with ui.row().classes("fu-plazo" + (" fu-plazo-pronto" if apuro else "")):
                ui.icon("schedule", size="15px")
                ui.label(texto_tiempo_restante(aviso.cierra_en, momento)).classes("whitespace-nowrap")

    with ui.card().classes("fu-card w-full" + ("" if detalle else " fu-card-viva")):
        if detalle:
            # Cabecera en el color de la categoría
            with ui.column().classes("fu-cabecera gap-3").style(f"background: {fuerte}"):
                with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.icon(ICONOS.get(aviso.categoria, "campaign"), size="20px")
                        ui.label(aviso.nombre_categoria).classes("text-sm font-semibold")
                    estado_arriba()
                ui.label(aviso.titulo).classes("fu-display fu-titulo-aviso")
                if aviso.descripcion:
                    ui.label(aviso.descripcion).classes("fu-cabecera-texto whitespace-pre-line")
        else:
            with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                with ui.row().classes("items-center gap-2.5 no-wrap min-w-0"):
                    with ui.element("div").classes("fu-icono-cat").style(
                        f"background: {suave}; color: {fuerte}"
                    ):
                        ui.icon(ICONOS.get(aviso.categoria, "campaign"), size="22px")
                    ui.label(aviso.nombre_categoria).classes("text-sm font-semibold ellipsis").style(
                        f"color: {fuerte}"
                    )
                estado_arriba()
            ui.label(aviso.titulo).classes("fu-display fu-titulo-tarjeta cursor-pointer").on(
                "click", lambda: ui.navigate.to(f"/aviso/{aviso.id}")
            )

        # Dónde, cuándo y cuánto
        datos_clave(aviso, momento)

        if aviso.descripcion and not detalle:
            descripcion = ui.label(aviso.descripcion).classes("fu-dato whitespace-pre-line")
            if modo == "tablero":
                descripcion.classes("line-clamp-3")

        barra_cupos(aviso, persona_id, puede_unirse)

        # Quiénes van
        if modo == "tablero":
            ui.label(texto_quienes(aviso)).classes("fu-gris text-sm")
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

        # Acciones: la principal, cómo llegar, comentarios y denunciar
        with ui.row().classes("fu-acciones w-full items-center gap-2 mt-auto"):
            if puede_unirse:
                ui.button("Unirme", on_click=partial(al_unirse, aviso.id)).props(
                    "unelevated no-caps"
                ).classes("fu-cta flex-1")
            if not aviso.cancelado:
                ui.link("Cómo llegar", url_mapa_de(aviso), new_tab=True).classes(
                    ESTILO_ACCION + " fu-llegar"
                )
                if not detalle:
                    ui.link(texto_comentarios(aviso.comentarios), f"/aviso/{aviso.id}").classes(
                        ESTILO_ACCION + " fu-comentar"
                    )
                if not mio:
                    ui.element("div").classes("grow")
                    ui.button(icon="outlined_flag", on_click=partial(al_denunciar, aviso.id)).props(
                        "flat round dense color=grey-7"
                    ).tooltip("Denunciar este aviso")

        if mio and not aviso.cancelado:
            ui.button(
                "Eliminar aviso", icon="delete_outline", on_click=partial(al_eliminar, aviso.id)
            ).props("flat no-caps").classes("fu-peligro self-start")
        elif puede_salirse:
            texto = "Quitar de mi buzón" if aviso.cancelado else "Salirme del evento"
            ui.button(texto, icon="logout", on_click=partial(al_salirse, aviso.id)).props(
                "flat no-caps"
            ).classes("fu-peligro self-start")


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

    with capa, ui.dialog() as dialogo, ui.card().classes("fu-card p-0 gap-0").style(
        "width: 460px"
    ) as tarjeta:
        cuerpo = ui.column().classes("w-full gap-4")

    def mostrar_confirmacion(actualizado: datos.Aviso, quien: str) -> None:
        """Pantalla oscura: tu círculo entra en amarillo a la fila de cupos."""
        momento = ahora()
        tarjeta.classes("fu-noche")
        cuerpo.clear()
        with cuerpo:
            ui.label(f"¡Listo, {quien}! Estás anotado").classes(
                "fu-display text-4xl font-extrabold w-full leading-none"
            )
            if actualizado.esta_lleno:
                ui.label("Con eso se completó el grupo").classes("font-bold w-full -mt-1").style(
                    f"color: {AMARILLO}"
                )
            with ui.element("div").classes("fu-festejo w-full"):
                fila_cupos(actualizado, persona_id, False)
            with ui.column().classes("fu-seccion").style(f"color: {TINTA}"):
                ui.label(actualizado.titulo).classes("fu-display text-xl font-bold leading-snug")
                dato("place", actualizado.lugar)
                dato("event", texto_fecha_evento(actualizado.inicio_evento, momento))
                if actualizado.valor is not None:
                    dato("payments", datos.texto_valor(actualizado.valor))
                if actualizado.descripcion:
                    dato("notes", actualizado.descripcion)
                dato(
                    "groups",
                    f"{actualizado.ocupados} de {actualizado.personas_necesarias} · "
                    f"{texto_faltan(actualizado.cupos_libres)}",
                )
                ui.link("Cómo llegar", url_mapa_de(actualizado), new_tab=True).classes(
                    ESTILO_ACCION + " fu-llegar self-start"
                )
            ui.label("Lo guardamos en tu buzón para que no se te olvide dónde y cuándo es.").classes(
                "text-sm w-full"
            ).style("color: #C9D6CE")
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Listo", on_click=dialogo.close).props("flat no-caps").classes(
                    "fu-blanco flex-1"
                )
                ui.button("Ver mi buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
                    "unelevated no-caps"
                ).classes("fu-cta flex-1")

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
        ui.label("Te vas a unir a").classes("fu-gris text-sm")
        ui.label(aviso.titulo).classes("fu-display text-2xl font-bold leading-tight -mt-3")
        datos_clave(aviso, ahora())
        with ui.column().classes("fu-panel w-full gap-3"):
            ui.label(texto_faltan(aviso.cupos_libres)).classes("fu-display fu-falta")
            fila_cupos(aviso, persona_id, True)
            ui.label("El círculo amarillo es tu lugar").classes("fu-mano")

        nombre = ui.input(
            "Tu nombre",
            placeholder="Ej: Pedro Soto",
            value=datos.nombre_usado(persona_id),
            validation=NOMBRE_SIN_GROSERIAS,
        ).props(f"outlined autofocus maxlength={datos.LARGO_NOMBRE[1]}").classes("w-full")
        nombre.on("keydown.enter", confirmar)

        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("Cancelar", on_click=dialogo.close).props("flat no-caps").classes("fu-suave")
            ui.button("Confirmar", icon="check", on_click=confirmar).props(
                "unelevated no-caps"
            ).classes("fu-cta flex-1")

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

    with capa, ui.dialog() as dialogo, ui.card().classes("fu-card").style("width: 420px"):
        ui.icon("logout", size="40px").classes("text-red-700 self-center")
        ui.label("¿Salirte de este evento?").classes(
            "fu-display text-2xl font-extrabold text-center w-full"
        )
        ui.label(aviso.titulo).classes("fu-gris font-semibold text-center w-full -mt-3")
        ui.label(
            "Tu cupo quedará libre. Si el aviso sigue dentro de su plazo, vuelve a aparecer "
            "en el tablero para que otra persona lo tome. También se quitará de tu buzón."
        ).classes("text-sm text-stone-600 text-center w-full")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("No, me quedo", on_click=dialogo.close).props("flat no-caps").classes("fu-suave flex-1")
            ui.button("Sí, salirme", on_click=confirmar).props("unelevated no-caps").classes("fu-peligro flex-1")

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

    with capa, ui.dialog() as dialogo, ui.card().classes("fu-card").style("width: 420px"):
        ui.icon("delete_outline", size="40px").classes("text-red-700 self-center")
        ui.label("¿Eliminar este aviso?").classes(
            "fu-display text-2xl font-extrabold text-center w-full"
        )
        ui.label(aviso.titulo).classes("fu-gris font-semibold text-center w-full -mt-3")
        donde = "del tablero y de tu buzón" if aviso.es_de(persona_id) else "del tablero y del buzón de su dueño"
        ui.label(f"Desaparecerá {donde}. {consecuencia} No se puede deshacer.").classes(
            "text-sm text-stone-600 text-center w-full"
        )
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("No, mantenerlo", on_click=dialogo.close).props("flat no-caps").classes("fu-suave flex-1")
            ui.button("Sí, eliminar", on_click=confirmar).props("unelevated no-caps").classes("fu-peligro flex-1")

    dialogo.on("hide", dialogo.delete)
    dialogo.open()


def abrir_dialogo_denunciar(
    aviso_id: int, capa: ui.element, persona_id: str | None, al_cambiar: Callable[[], None]
) -> None:
    aviso = datos.obtener_aviso(aviso_id)
    if aviso is None or aviso.cancelado:
        ui.notify("Este aviso ya no está disponible.", type="info", position="top")
        al_cambiar()
        return
    if aviso.es_de(persona_id):
        ui.notify("No puedes denunciar tu propio aviso.", type="info", position="top")
        return

    def enviar() -> None:
        try:
            datos.denunciar(aviso_id, persona_id, motivo.value, comentario.value)
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
            if "ya denunciaste" in str(error).lower():
                dialogo.close()
            return
        dialogo.close()
        ui.notify("Gracias. La administración revisará este aviso.", type="positive", position="top")
        al_cambiar()

    with capa, ui.dialog() as dialogo, ui.card().classes("fu-card").style("width: 440px"):
        ui.icon("outlined_flag", size="40px").classes("text-red-700 self-center")
        ui.label("Denunciar aviso").classes("fu-display text-2xl font-extrabold text-center w-full")
        ui.label(aviso.titulo).classes("fu-gris font-semibold text-center w-full -mt-3")
        ui.label("¿Qué pasa con este aviso?").classes("text-sm font-semibold text-stone-700")
        motivo = ui.radio(datos.MOTIVOS_DENUNCIA, value=None).classes("w-full -mt-2")
        comentario = ui.textarea("Cuéntanos más (opcional)").props(
            f"outlined autogrow maxlength={datos.LARGO_MAX_DENUNCIA}"
        ).classes("w-full")
        ui.label("Quien publicó el aviso no sabrá quién lo denunció.").classes("text-xs text-stone-500")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.button("Cancelar", on_click=dialogo.close).props("flat no-caps").classes("fu-suave flex-1")
            ui.button("Enviar denuncia", on_click=enviar).props("unelevated no-caps").classes("fu-peligro flex-1")

    dialogo.on("hide", dialogo.delete)
    dialogo.open()


def abrir_dialogo_crear(
    capa: ui.element, base_url: str, persona_id: str | None, al_cambiar: Callable[[], None]
) -> None:
    momento = ahora()
    sugerida = (momento + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)

    with capa, ui.dialog().props("persistent") as dialogo, ui.card().classes(
        "fu-card fu-gris-fondo fu-pantalla"
    ).style("width: 580px"):
        cuerpo = ui.column().classes("w-full gap-3")

    # Ubicación exacta (opcional), elegida en el selector a pantalla completa.
    # "texto_auto" es lo que escribimos nosotros en «Lugar» (desde el mapa): eso
    # se puede reemplazar; lo que escribió la persona, nunca. "turno" deja valer
    # solo la última elección si llegan dos respuestas.
    ubicacion: dict = {"lat": None, "lng": None, "texto_auto": None, "turno": 0, "direccion": None}
    vista: dict = {"direccion": None}

    def escrito_por_la_persona() -> bool:
        texto = (campo_lugar.value or "").strip()
        return bool(texto) and texto != ubicacion["texto_auto"]

    def abrir_selector() -> None:
        abrir_selector_ubicacion(
            capa,
            lat=ubicacion["lat"],
            lng=ubicacion["lng"],
            consulta=(campo_lugar.value or "").strip() if escrito_por_la_persona() else "",
            al_confirmar=al_elegir_punto,
        )

    def pintar_ubicacion() -> None:
        caja_ubicacion.clear()
        vista["direccion"] = None
        with caja_ubicacion:
            if ubicacion["lat"] is None:
                with ui.row().classes(
                    "w-full items-center gap-3 no-wrap rounded-2xl border-2 border-dashed border-stone-300 "
                    "px-3 py-3 cursor-pointer hover:border-green-800"
                ).on("click", abrir_selector):
                    with ui.element("div").classes("fu-avatar fu-avatar-yo"):
                        ui.icon("add_location_alt", size="22px")
                    with ui.column().classes("gap-0 flex-1 min-w-0"):
                        ui.label("Marcar en el mapa").classes("font-semibold text-stone-900 leading-tight")
                        ui.label("Opcional · así «Cómo llegar» lleva al punto exacto").classes(
                            "text-xs text-stone-500"
                        )
                    ui.icon("chevron_right", size="22px").classes("text-stone-400 shrink-0")
                return
            dibujo = mapa_de_vista(ubicacion["lat"], ubicacion["lng"], alto="8.5rem", controles=False)
            if dibujo:
                dibujo[1].on("map-click", abrir_selector)  # tocar la vista previa = cambiar
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("check_circle", size="20px").classes("text-primary shrink-0")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label("Ubicación marcada").classes("text-sm font-semibold text-stone-900 leading-tight")
                    vista["direccion"] = ui.label(ubicacion["direccion"] or "Punto marcado en el mapa").classes(
                        "text-xs text-stone-500 ellipsis"
                    )
                ui.button("Cambiar", on_click=abrir_selector).props("flat no-caps").classes("fu-suave")
                ui.button("Quitar", on_click=quitar_ubicacion).props("flat no-caps").classes("fu-peligro")

    async def al_elegir_punto(lat: float, lng: float, lugar) -> None:
        ubicacion.update(lat=lat, lng=lng)
        ubicacion["turno"] += 1
        turno = ubicacion["turno"]
        if lugar is not None:  # eligió un resultado de la búsqueda
            ubicacion["direccion"] = lugar.nombre + (f" · {lugar.detalle_corto}" if lugar.detalle_corto else "")
            if not escrito_por_la_persona():
                campo_lugar.value = lugar.texto
                ubicacion["texto_auto"] = lugar.texto
            pintar_ubicacion()
            return
        ubicacion["direccion"] = "Buscando la dirección…"
        pintar_ubicacion()
        try:
            texto = await asyncio.to_thread(lugares.direccion_de, lat, lng)
        except Exception:
            texto = None
        if turno != ubicacion["turno"]:  # ya eligió otro punto o lo quitó
            return
        ubicacion["direccion"] = f"Cerca de {texto}" if texto else "Punto marcado en el mapa"
        try:
            if texto and not escrito_por_la_persona():
                campo_lugar.value = texto
                ubicacion["texto_auto"] = texto
            if vista["direccion"] is not None:
                vista["direccion"].text = ubicacion["direccion"]
        except Exception:  # el formulario se cerró mientras buscábamos
            pass

    def quitar_ubicacion() -> None:
        ubicacion.update(lat=None, lng=None, direccion=None)
        ubicacion["turno"] += 1  # descarta una dirección que venía en camino
        pintar_ubicacion()

    def actualizar_valor() -> None:
        con_costo = campo_cobro.value == "pago"
        campo_valor.set_visibility(con_costo)
        # Solo números y puntos: cualquier otra cosa se borra al escribirla.
        texto = campo_valor.value or ""
        limpio = "".join(c for c in texto if c in "0123456789.")
        if limpio != texto:
            campo_valor.value = limpio
        vista_valor.set_visibility(con_costo)
        try:
            monto = datos.parsear_valor(limpio) if con_costo and limpio else None
        except datos.ErrorValidacion:
            monto = None
        vista_valor.text = f"Se mostrará como: {datos.texto_valor(monto)}" if monto else ""

    def actualizar_resumen() -> None:
        """Vista previa en vivo: así se verán los cupos en el tablero."""
        actuales, necesarias = campo_actuales.value, campo_necesarias.value
        caja_previa.clear()
        if actuales and necesarias and necesarias > actuales:
            faltan = int(necesarias - actuales)
            resumen.text = f"Buscan {faltan} persona{'s' if faltan != 1 else ''} más."
            dibujados = min(int(necesarias), MAX_CUPOS_DIBUJADOS * 2)
            ocupados = min(int(actuales), dibujados - 1)
            with caja_previa:
                for i in range(dibujados):
                    ui.element("div").classes("fu-cupo " + ("fu-cupo-cara" if i < ocupados else "fu-cupo-libre")).style(
                        f"background-color: {colores_de(campo_categoria.value)[0]}" if i < ocupados else ""
                    )
        else:
            resumen.text = ""
            with caja_previa:
                ui.label("Elige cuántos son y cuántos necesitan para ver cómo quedará.").classes("text-sm").style(
                    "color: #C9D6CE"
                )

    def paso(campo, cambio: int, minimo: int, maximo: int) -> None:
        """Botones − y + de «¿Cuántos son?» y «¿Cuántos necesitan?»."""
        actual = campo.value
        nuevo = minimo if actual is None else max(minimo, min(maximo, int(actual) + cambio))
        campo.set_value(nuevo)
        # «necesitan» siempre va al menos uno por encima de «son»
        if campo is campo_actuales and (campo_necesarias.value is None or campo_necesarias.value <= nuevo):
            campo_necesarias.set_value(min(nuevo + 1, datos.MAX_PERSONAS))

    def elegir_categoria(clave: str) -> None:
        campo_categoria.value = clave
        pintar_categorias()
        actualizar_resumen()

    def pintar_categorias() -> None:
        caja_categorias.clear()
        with caja_categorias:
            for clave, nombre in datos.CATEGORIAS.items():
                activo = clave == campo_categoria.value
                with ui.button(on_click=partial(elegir_categoria, clave)).props("flat no-caps").classes(
                    "fu-chip " + ("fu-chip-activo" if activo else "fu-chip-suave")
                ):
                    ui.element("div").classes("fu-punto").style(
                        f"background: {AMARILLO if activo else colores_de(clave)[0]}"
                    )
                    ui.label(nombre)

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
                lat=ubicacion["lat"],
                lng=ubicacion["lng"],
                valor=0 if campo_cobro.value == "gratis" else campo_valor.value,
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
            ui.label("¡Aviso publicado!").classes("fu-display text-4xl font-extrabold w-full leading-none mt-4")
            ui.label(
                f"Lo verás en tu buzón durante {aviso.duracion_horas} horas, aunque se llene. "
                f"Del tablero público sale cuando {tablero}."
            ).classes("fu-gris w-full")
            with ui.column().classes("fu-seccion"):
                ui.label("Compártelo por WhatsApp o donde quieras:").classes("text-sm font-semibold")
                ui.input(value=enlace).props("outlined dense readonly").classes("w-full")
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.button("Listo", on_click=dialogo.close).props("flat no-caps").classes("fu-blanco flex-1")
                ui.button("Ver mi buzón", icon="inbox", on_click=lambda: ui.navigate.to("/buzon")).props(
                    "unelevated no-caps"
                ).classes("fu-cta flex-1")
            ui.button(
                "¿Te equivocaste? Eliminar este aviso",
                icon="delete_outline",
                on_click=lambda: abrir_dialogo_eliminar(
                    aviso.id, capa, persona_id, al_cambiar, al_terminar=dialogo.close
                ),
            ).props("flat no-caps dense color=red-9").classes("self-center")

    OPCIONES = "spread no-caps unelevated toggle-color=dark color=grey-2 text-color=dark toggle-text-color=white"

    with cuerpo:
        with ui.row().classes("w-full items-center justify-between no-wrap px-1"):
            ui.label("Nuevo aviso").classes("fu-display text-3xl font-extrabold")
            ui.button(icon="close", on_click=dialogo.close).props("flat round").classes("fu-blanco")

        # ¿Qué van a hacer?
        with ui.column().classes("fu-seccion"):
            ui.label("¿Qué van a hacer?").classes("fu-display text-xl")
            ui.label("Elige una categoría y ponle un título claro").classes("fu-mano -mt-2")
            caja_categorias = ui.row().classes("w-full gap-2")
            campo_categoria = ui.select(datos.CATEGORIAS, label="Categoría", value="futbol")
            campo_categoria.set_visibility(False)  # se elige con los botones de arriba
            pintar_categorias()
            campo_titulo = ui.input(
                "Título", placeholder="Ej: Pichanga 7 vs 7, falta uno", validation=SIN_GROSERIAS
            ).props(f"outlined maxlength={datos.LARGO_TITULO[1]}").classes("w-full")

        # ¿Cuántos son?
        with ui.column().classes("fu-seccion"):
            ui.label("¿Cuántos son?").classes("fu-display text-xl")
            ui.label(f"Cuenta a todos, contigo incluido (máximo {datos.MAX_PERSONAS})").classes("fu-mano -mt-2")
            with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                ui.label("Ya somos").classes("font-extrabold")
                with ui.element("div").classes("fu-paso"):
                    ui.button("−", on_click=lambda: paso(campo_actuales, -1, 1, datos.MAX_PERSONAS - 1)).props(
                        "flat aria-label=\"Uno menos\""
                    )
                    campo_actuales = ui.number(
                        "¿Cuántos son?",
                        placeholder="9",
                        min=1,
                        max=datos.MAX_PERSONAS - 1,
                        step=1,
                        format="%d",
                        on_change=actualizar_resumen,
                    ).props("borderless dense")
                    ui.button("+", on_click=lambda: paso(campo_actuales, 1, 1, datos.MAX_PERSONAS - 1)).props(
                        "flat aria-label=\"Uno más\""
                    )
            with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                ui.label("Necesitamos en total").classes("font-extrabold")
                with ui.element("div").classes("fu-paso"):
                    ui.button("−", on_click=lambda: paso(campo_necesarias, -1, 2, datos.MAX_PERSONAS)).props(
                        "flat aria-label=\"Uno menos\""
                    )
                    campo_necesarias = ui.number(
                        "¿Cuántos necesitan?",
                        placeholder="10",
                        min=2,
                        max=datos.MAX_PERSONAS,
                        step=1,
                        format="%d",
                        on_change=actualizar_resumen,
                    ).props("borderless dense")
                    ui.button("+", on_click=lambda: paso(campo_necesarias, 1, 2, datos.MAX_PERSONAS)).props(
                        "flat aria-label=\"Uno más\""
                    )
            with ui.column().classes("fu-previa w-full gap-3"):
                ui.label("Así lo verán en el tablero").classes("fu-mano")
                resumen = ui.label("").classes("fu-display fu-falta")
                caja_previa = ui.row().classes("fu-cupos")
            actualizar_resumen()

        # ¿Dónde y cuándo?
        with ui.column().classes("fu-seccion"):
            ui.label("¿Dónde y cuándo?").classes("fu-display text-xl")
            ui.label("Mientras más exacto, más fácil llegar").classes("fu-mano -mt-2")
            campo_lugar = ui.input(
                "Lugar", placeholder="Ej: Cancha del liceo, Parque Chuyaca", validation=SIN_GROSERIAS
            ).props(
                f"outlined maxlength={datos.LARGO_LUGAR[1]}"
            ).classes("w-full")
            caja_ubicacion = ui.column().classes("w-full gap-2")
            pintar_ubicacion()
            with ui.row().classes("w-full gap-3 no-wrap"):
                campo_fecha = ui.input("Fecha", value=sugerida.strftime("%Y-%m-%d")).props(
                    f"outlined stack-label type=date min={momento:%Y-%m-%d}"
                ).classes("flex-1")
                campo_hora = ui.input("Hora", value=sugerida.strftime("%H:%M")).props(
                    "outlined stack-label type=time"
                ).classes("flex-1")

        # Valor, detalles y duración
        with ui.column().classes("fu-seccion"):
            ui.label("¿Cuánto cuesta por persona?").classes("fu-display text-xl")
            campo_cobro = ui.toggle(
                {"gratis": "Gratis ($0)", "pago": "Tiene costo"},
                value="gratis",
                on_change=lambda: actualizar_valor(),
            ).props(OPCIONES).classes("fu-opciones w-full")
            campo_valor = ui.input(
                "Valor por persona",
                placeholder="Ej: 2.000",
                on_change=lambda: actualizar_valor(),
                validation=VALOR_EN_PESOS,
            ).props("outlined prefix=$ suffix=CLP inputmode=numeric maxlength=7").classes("w-full")
            vista_valor = ui.label("").classes("fu-gris text-xs -mt-2")
            campo_valor.set_visibility(False)

            campo_descripcion = ui.textarea(
                "Detalles (opcional)",
                placeholder="Ej: Se paga la cancha entre todos. Traer polera oscura.",
                validation=SIN_GROSERIAS,
            ).props(f"outlined autogrow maxlength={datos.LARGO_MAX_DESCRIPCION}").classes("w-full")

            ui.label("¿Cuánto dura el aviso?").classes("fu-display text-xl")
            campo_duracion = ui.toggle({24: "24 horas", 48: "48 horas"}, value=24).props(OPCIONES).classes(
                "fu-opciones w-full"
            )
            ui.label(
                "En el tablero se cierra antes si se completa el grupo o llega la hora del evento. "
                "En tu buzón lo verás durante todo el plazo."
            ).classes("fu-gris text-xs")

        ui.button("Publicar aviso", on_click=publicar).props("unelevated no-caps").classes(
            "fu-cta fu-grande w-full"
        )

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

    def chip(texto: str, cantidad: int, activo: bool, al_tocar, color: str | None = None) -> None:
        with ui.button(texto, on_click=al_tocar).props("flat no-caps").classes(
            "fu-chip" + (" fu-chip-activo" if activo else "")
        ):
            ui.label(str(cantidad)).classes("fu-cuenta")

    al_unirse = partial(abrir_dialogo_unirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_salirse = partial(abrir_dialogo_salirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_eliminar = partial(abrir_dialogo_eliminar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_denunciar = partial(abrir_dialogo_denunciar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

    @ui.refreshable
    def lista() -> None:
        momento = ahora()
        activos = datos.avisos_activos(momento)
        estado["firma"] = firma(activos, momento)

        elegida = estado["categoria"]
        visibles = [a for a in activos if elegida in (None, a.categoria)]

        n = len(activos)
        ui.label(
            "Todavía no hay avisos abiertos en Osorno"
            if n == 0
            else f"{n} aviso{'s' if n != 1 else ''} abierto{'s' if n != 1 else ''} en Osorno"
        ).classes("fu-gris text-base -mt-3")

        if activos or elegida:
            conteo = Counter(a.categoria for a in activos)
            with ui.row().classes("w-full gap-2 no-wrap overflow-x-auto pb-1 md:flex-wrap"):
                chip("Todos", len(activos), elegida is None, partial(elegir_categoria, None))
                for clave, nombre in datos.CATEGORIAS.items():
                    if conteo[clave] or clave == elegida:
                        chip(
                            nombre,
                            conteo[clave],
                            clave == elegida,
                            partial(elegir_categoria, clave),
                        )

        if not visibles:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.image(LOGO_URL).props("no-spinner no-transition").classes("w-16 h-16")
                if elegida:
                    ui.label(f"No hay avisos abiertos de {datos.CATEGORIAS[elegida]}").classes(
                        "fu-display text-2xl font-bold"
                    )
                else:
                    ui.label("No hay avisos abiertos").classes("fu-display text-2xl font-bold")
                ui.label("¿Te falta gente para algo? Publica el primero con «Crear aviso».").classes("fu-gris")
            return

        with ui.element("div").classes("fu-rejilla"):
            for aviso in visibles:
                tarjeta_aviso(aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, al_denunciar)

    def revisar_cambios() -> None:
        momento = ahora()
        if firma(datos.avisos_activos(momento), momento) != estado["firma"]:
            lista.refresh()
        actualizar_contador()

    with ui.element("div").classes("fu-contenedor"):
        actualizar_contador = encabezado(persona_id)
        ui.label("¿A quién le falta gente hoy?").classes("fu-display fu-hero mt-2")
        como_funciona(abierto=not datos.avisos_activos(ahora()))
        lista()

    with ui.element("div").classes("fu-fab"):
        ui.button(
            "Crear aviso",
            icon="add",
            on_click=lambda: abrir_dialogo_crear(capa, base_url, persona_id, refrescar),
        ).props("unelevated no-caps").classes("fu-oscuro")

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


@ui.page("/aviso/{aviso_id}", title="Falta Uno · Aviso")
def pagina_aviso(aviso_id: int, request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    soy_admin = datos.es_admin(persona_id)
    capa = ui.element("div")
    estado: dict = {"firma": None, "comentarios": None}

    def refrescar() -> None:
        contenido.refresh()
        lista_comentarios.refresh()
        actualizar_contador()

    al_unirse = partial(abrir_dialogo_unirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_salirse = partial(abrir_dialogo_salirse, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_eliminar = partial(abrir_dialogo_eliminar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)
    al_denunciar = partial(abrir_dialogo_denunciar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

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
                ui.icon("search_off", size="48px").classes("fu-gris")
                ui.label("Este aviso no existe").classes("fu-display text-2xl font-bold")
            return

        motivo = aviso.motivo_cierre(momento)
        if motivo:
            aviso_de_cierre(aviso, motivo)
        tarjeta_aviso(
            aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, al_denunciar, modo="detalle"
        )

    # ------------------------------------------------------------ comentarios
    def borrar_comentario(comentario_id: int) -> None:
        try:
            datos.borrar_comentario(comentario_id, persona_id, como_admin=soy_admin)
        except datos.ErrorValidacion as error:
            ui.notify(str(error), type="negative", position="top")
        lista_comentarios.refresh()

    @ui.refreshable
    def lista_comentarios() -> None:
        aviso = datos.obtener_aviso(aviso_id)
        if aviso is None:
            return
        estado["comentarios"] = aviso.comentarios
        momento = ahora()
        comentarios = datos.comentarios_de(aviso_id)
        ui.label(f"Comentarios ({len(comentarios)})").classes("fu-display text-xl font-bold")
        if not comentarios:
            ui.label("Todavía no hay comentarios. ¿Tienes una pregunta? Escríbela aquí abajo.").classes(
                "text-sm text-stone-500"
            )
        for c in comentarios:
            del_dueno = aviso.es_de(c.persona_id)
            mio = bool(persona_id) and c.persona_id == persona_id
            nombre = "Quien organiza" if del_dueno else (c.nombre or "Anónimo")
            with ui.row().classes("w-full items-start gap-2.5 no-wrap"):
                color = "fu-avatar-organiza" if del_dueno else ("fu-avatar-yo" if mio else "")
                ui.label(iniciales(nombre)).classes(f"fu-avatar {color}")
                with ui.column().classes("fu-burbuja gap-0"):
                    with ui.row().classes("items-baseline gap-2 no-wrap"):
                        ui.label(nombre + (" (tú)" if mio else "")).classes("font-bold text-sm")
                        ui.label(texto_hace(c.momento, momento)).classes("fu-gris text-xs")
                    ui.label(c.texto).classes("break-words")
                ui.element("div").classes("grow")
                if mio or soy_admin:
                    ui.button(icon="close", on_click=partial(borrar_comentario, c.id)).props(
                        "flat round dense size=sm color=grey-6"
                    ).tooltip("Borrar comentario")

    def revisar_cambios() -> None:
        aviso, nueva_firma = leer()
        if nueva_firma != estado["firma"]:
            contenido.refresh()
        if aviso is not None and aviso.comentarios != estado["comentarios"]:
            lista_comentarios.refresh()
        actualizar_contador()

    with ui.element("div").classes("fu-contenedor"):
        actualizar_contador = encabezado(persona_id)
        volver_al_tablero()
        aviso_inicial = datos.obtener_aviso(aviso_id)
        # En el computador: el aviso a la izquierda; el mapa y los comentarios a la derecha
        with ui.element("div").classes("fu-dos" if aviso_inicial is not None else "fu-columna"):
            with ui.element("div").classes("fu-columna"):
                contenido()
            with ui.element("div").classes("fu-columna"):
                if aviso_inicial is not None and aviso_inicial.tiene_ubicacion and not aviso_inicial.cancelado:
                    with ui.card().classes("fu-card w-full"):
                        ui.label("Ubicación").classes("fu-display text-xl font-bold")
                        mapa_de_vista(aviso_inicial.lat, aviso_inicial.lng)
                        with ui.row().classes("w-full items-center justify-between gap-3"):
                            ui.label(aviso_inicial.lugar).classes("font-semibold min-w-0 flex-1")
                            ui.link("Cómo llegar", url_mapa_de(aviso_inicial), new_tab=True).classes(
                                ESTILO_ACCION + " fu-llegar shrink-0"
                            )
                if aviso_inicial is not None:
                    with ui.card().classes("fu-card w-full"):
                        lista_comentarios()
                        if not aviso_inicial.cancelado:
                            _formulario_comentario(aviso_inicial, persona_id, lista_comentarios.refresh)

    ui.timer(SEGUNDOS_ENTRE_REVISIONES, revisar_cambios)


def _formulario_comentario(
    aviso: datos.Aviso, persona_id: str | None, al_comentar: Callable[[], None]
) -> None:
    """Formulario fuera de la lista que se redibuja, para no perder lo que se está escribiendo."""
    ui.separator().classes("my-1")
    if aviso.es_de(persona_id):
        campo_nombre = None
        ui.label("Comentas como quien organiza.").classes("fu-gris text-xs")
    else:
        campo_nombre = ui.input(
            "Tu nombre", value=datos.nombre_usado(persona_id), validation=NOMBRE_SIN_GROSERIAS
        ).props(f"outlined dense maxlength={datos.LARGO_NOMBRE[1]}").classes("w-full")
    with ui.row().classes("w-full items-start gap-2 no-wrap"):
        campo_texto = ui.input(
            "Escribe un comentario…", placeholder="Ej: ¿Se paga la cancha?", validation=SIN_GROSERIAS
        ).props(f"outlined dense rounded maxlength={datos.LARGO_MAX_COMENTARIO} counter").classes("grow")

        def enviar() -> None:
            try:
                datos.comentar(
                    aviso.id, persona_id, campo_nombre.value if campo_nombre else "", campo_texto.value
                )
            except datos.ErrorValidacion as error:
                ui.notify(str(error), type="negative", position="top")
                return
            campo_texto.value = ""
            al_comentar()

        campo_texto.on("keydown.enter", enviar)
        ui.button(icon="arrow_upward", on_click=enviar).props("unelevated round color=primary").tooltip("Enviar")


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
    al_denunciar = partial(abrir_dialogo_denunciar, capa=capa, persona_id=persona_id, al_cambiar=refrescar)

    def leer() -> tuple[list[datos.Aviso], list[datos.Aviso], tuple]:
        momento = ahora()
        me_uni, organizo = datos.mi_buzon(persona_id, momento)
        return me_uni, organizo, (firma(me_uni, momento), firma(organizo, momento))

    def seccion(titulo: str, explicacion: str, icono: str) -> None:
        ui.label(titulo).classes("fu-display text-2xl font-bold mt-2")
        ui.label(explicacion).classes("fu-gris text-sm -mt-4")

    @ui.refreshable
    def contenido() -> None:
        momento = ahora()
        me_uni, organizo, estado["firma"] = leer()

        if not me_uni and not organizo:
            with ui.column().classes("w-full items-center text-center py-16 gap-2"):
                ui.icon("inbox", size="56px").classes("fu-gris")
                ui.label("Tu buzón está vacío").classes("fu-display text-2xl font-bold")
                ui.label(
                    "Cuando te unas a un evento o publiques uno, aparecerá aquí con todos sus detalles."
                ).classes("fu-gris max-w-sm")
                ui.button("Ver avisos abiertos", on_click=lambda: ui.navigate.to("/")).props(
                    "unelevated no-caps"
                ).classes("fu-cta mt-2")
            return

        if me_uni:
            seccion(
                "Me uní",
                "Dónde y cuándo es cada evento. Se quitan solos unas horas después de que empiezan.",
                "event_available",
            )
            with ui.element("div").classes("fu-rejilla"):
                for aviso in me_uni:
                    tarjeta_aviso(
                        aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, al_denunciar, modo="buzon"
                    )

        if organizo:
            seccion(
                "Mis avisos",
                "Los que publicaste. Siguen aquí aunque se llenen, hasta que termina su plazo.",
                "campaign",
            )
            with ui.element("div").classes("fu-rejilla"):
                for aviso in organizo:
                    tarjeta_aviso(
                        aviso, momento, persona_id, al_unirse, al_salirse, al_eliminar, al_denunciar, modo="buzon"
                    )

    def revisar_cambios() -> None:
        if leer()[2] != estado["firma"]:
            contenido.refresh()
        actualizar_contador()

    with ui.element("div").classes("fu-contenedor"):
        actualizar_contador = encabezado(persona_id)
        volver_al_tablero()
        ui.label("Mi buzón").classes("fu-display fu-hero")
        contenido()
        ui.label(
            "Tu buzón se guarda en este navegador. Si abres la página en otro teléfono, "
            "en modo incógnito o borras las cookies, no verás estos eventos ahí."
        ).classes("fu-gris text-xs text-center w-full mt-6")

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
    return ui.card().classes("fu-card w-full")


@ui.page("/admin", title="Falta Uno · Administración")
def pagina_admin(request: Request) -> None:
    preparar_pagina()
    persona_id = persona_de(request)
    cliente = getattr(request, "client", None)
    ip = getattr(cliente, "host", None) or "desconocida"
    capa = ui.element("div")

    with ui.element("div").classes("fu-contenedor fu-angosto"):
        encabezado(persona_id)
        with ui.row().classes("items-center gap-2 no-wrap"):
            ui.icon("admin_panel_settings", size="30px").classes("text-primary")
            ui.label("Administración").classes("fu-display fu-hero")

        if not CLAVE_ADMIN:
            with tarjeta_simple():
                ui.label("El panel está desactivado").classes("fu-display text-xl")
                ui.label(
                    "Para activarlo, en Render entra a tu servicio → Environment → Add Environment "
                    "Variable, crea CLAVE_ADMIN con una clave larga que solo tú conozcas y guarda. "
                    "Render reinicia la página solo."
                ).classes("fu-gris")
            return

        if not datos.es_admin(persona_id):
            _formulario_ingreso(persona_id, ip)
            return

        _panel(persona_id, capa)


def _formulario_ingreso(persona_id: str | None, ip: str) -> None:
    with tarjeta_simple():
        ui.label("Esta sección es solo para quien administra la página.").classes("fu-gris")
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

    guia(
        "Desde aquí cuidas la página: revisas las denuncias, decides qué palabras se filtran "
        "y puedes eliminar cualquier aviso."
    )
    with ui.tabs().props("no-caps align=left").classes("fu-pestanas w-full") as pestanas:
        p_resumen = ui.tab("Resumen", icon="insights")
        n_denuncias = len(datos.denuncias_pendientes())
        p_denuncias = ui.tab(f"Denuncias ({n_denuncias})" if n_denuncias else "Denuncias", icon="outlined_flag")
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
                    ("Avisos con denuncias por revisar", c["denuncias_pendientes"], "outlined_flag"),
                ]
                with ui.row().classes("w-full gap-3"):
                    for titulo, valor, icono in tarjetas:
                        with ui.card().classes(
                            "rounded-2xl shadow-none border border-stone-200 p-4 gap-1"
                        ).style("flex: 1 1 150px; min-width: 150px"):
                            ui.icon(icono, size="22px").classes("text-primary")
                            ui.label(str(valor)).classes("fu-cifra")
                            ui.label(titulo).classes("text-xs fu-gris")
                ui.label(f"Avisos publicados desde el comienzo: {c['avisos_total']}").classes(
                    "text-sm fu-gris"
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

        # ------------------------------------------------------------ Denuncias
        with ui.tab_panel(p_denuncias).classes("px-0 gap-4"):
            ui.label(
                f"Con {datos.UMBRAL_DENUNCIAS} denuncias de personas distintas, un aviso se oculta "
                "del tablero hasta que lo revises."
            ).classes("text-sm fu-gris")

            def tras_moderar() -> None:
                lista_denuncias.refresh()
                lista_avisos.refresh()
                cifras.refresh()

            def descartar(aviso_id: int) -> None:
                if not sigo_siendo_admin():
                    return
                datos.descartar_denuncias(aviso_id)
                ui.notify("Denuncias descartadas. El aviso se ve normal otra vez.", type="info", position="top")
                tras_moderar()

            @ui.refreshable
            def lista_denuncias() -> None:
                momento = ahora()
                pendientes = datos.denuncias_pendientes()
                if not pendientes:
                    ui.label("No hay denuncias por revisar.").classes("fu-gris")
                for aviso, denuncias in pendientes:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                            ui.label(aviso.titulo).classes(
                                "fu-display text-xl leading-snug cursor-pointer hover:underline"
                            ).on("click", partial(ui.navigate.to, f"/aviso/{aviso.id}"))
                            n = len(denuncias)
                            etiqueta(f"{n} denuncia{'s' if n != 1 else ''}", "outlined_flag", rojo=True)
                        if n >= datos.UMBRAL_DENUNCIAS and not aviso.cancelado:
                            ui.label("Oculto del tablero mientras lo revisas.").classes(
                                "text-sm font-semibold text-red-800"
                            )
                        ui.label(
                            f"{aviso.lugar} · {texto_fecha_evento(aviso.inicio_evento, momento)}"
                        ).classes("text-sm fu-gris")
                        if aviso.descripcion:
                            ui.label(aviso.descripcion).classes("text-sm fu-gris line-clamp-3")
                        for motivo_txt, cantidad in Counter(d.nombre_motivo for d in denuncias).most_common():
                            ui.label(f"• {motivo_txt} ({cantidad})").classes("text-sm ")
                        for d in denuncias:
                            if d.comentario:
                                ui.label(f"“{d.comentario}”").classes("text-sm italic fu-gris")
                        with ui.row().classes("gap-2"):
                            if not aviso.cancelado:
                                ui.button(
                                    "Eliminar aviso",
                                    icon="delete_outline",
                                    on_click=partial(
                                        abrir_dialogo_eliminar, aviso.id, capa, persona_id, tras_moderar,
                                        como_admin=True,
                                    ),
                                ).props("unelevated rounded no-caps color=red-8")
                            ui.button(
                                "Descartar denuncias", icon="done", on_click=partial(descartar, aviso.id)
                            ).props("flat rounded no-caps color=grey-9")

            lista_denuncias()

        # ------------------------------------------------------------ Palabras
        with ui.tab_panel(p_palabras).classes("px-0 gap-4"):
            with tarjeta_simple():
                ui.label("Agregar palabra o frase al filtro").classes("fu-display text-xl")
                ui.label(
                    "Se aplica al instante en toda la página, sin volver a publicar el código."
                ).classes("text-sm fu-gris -mt-2")
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
                ).classes("text-xs fu-gris")

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
                ui.label("Probar el filtro").classes("fu-display text-xl")
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
                        resultado.text = "Se bloquearía por: " + ", ".join(f"«{m}»" for m in malas)
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
                ui.label(f"Tus reglas ({len(propias)})").classes("fu-display text-xl mt-2")
                if not propias:
                    ui.label("Todavía no agregas palabras propias.").classes("fu-gris")
                for regla in propias:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-start justify-between no-wrap gap-2"):
                            with ui.column().classes("gap-0.5"):
                                ui.label(regla.palabra).classes("fu-display text-xl")
                                if regla.siempre:
                                    ui.label("Se filtra siempre").classes("text-sm fu-gris")
                                else:
                                    ui.label("Se filtra cerca de: " + ", ".join(regla.cerca_de)).classes(
                                        "text-sm fu-gris"
                                    )
                                if regla.excepto:
                                    ui.label("Nunca en: " + ", ".join(regla.excepto)).classes(
                                        "text-sm fu-gris"
                                    )
                            ui.button(
                                icon="delete_outline", on_click=partial(borrar_regla, regla.id, regla.palabra)
                            ).props("flat round color=red-8").tooltip("Quitar del filtro")

            lista_reglas()

            base = filtro.palabras_base()
            with ui.expansion(f"Lista base ({len(base)} palabras, se filtran siempre)", icon="list").classes(
                "w-full"
            ):
                ui.label(", ".join(base)).classes("text-xs fu-gris")
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
                ).classes("text-sm fu-gris")
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
                    ui.label("No hay bloqueos registrados.").classes("fu-gris")
                for bloqueo in registro:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-center justify-between no-wrap"):
                            etiqueta(bloqueo.campo, "block", rojo=True)
                            ui.label(texto_fecha_evento(bloqueo.momento, momento)).classes(
                                "text-xs fu-gris"
                            )
                        ui.label(bloqueo.texto).classes(" whitespace-pre-line break-words")
                        ui.label("Detectó: " + ", ".join(f"«{p}»" for p in bloqueo.palabras)).classes(
                            "text-xs font-semibold text-red-800"
                        )

            lista_bloqueados()

        # ------------------------------------------------------------ Avisos
        with ui.tab_panel(p_avisos).classes("px-0 gap-4"):
            ui.label("Los últimos 60 avisos, abiertos o no. Puedes eliminar cualquiera.").classes(
                "text-sm fu-gris"
            )

            def tras_eliminar() -> None:
                lista_avisos.refresh()
                lista_denuncias.refresh()
                cifras.refresh()

            @ui.refreshable
            def lista_avisos() -> None:
                momento = ahora()
                avisos = datos.todos_los_avisos(60)
                if not avisos:
                    ui.label("Todavía no hay avisos.").classes("fu-gris")
                for aviso in avisos:
                    with tarjeta_simple():
                        with ui.row().classes("w-full items-center justify-between no-wrap gap-2"):
                            ui.label(aviso.titulo).classes(
                                "fu-display text-xl leading-snug cursor-pointer hover:underline"
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
                        ).classes("text-sm fu-gris")
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
