"""
lugares.py — Buscar lugares reales (canchas, restaurantes, plazas…) por nombre.

Usa servicios gratuitos basados en OpenStreetMap, sin claves ni tarjeta:
  1. Photon (photon.komoot.io), pensado para búsquedas rápidas.
  2. Nominatim (nominatim.openstreetmap.org) como respaldo si Photon falla.

Reglas de uso que respetamos (sobre todo las de Nominatim:
https://operations.osmfoundation.org/policies/nominatim/):
  * Solo se busca cuando la persona toca «Buscar» (nada de autocompletar).
  * Máximo 1 consulta por segundo, para toda la página.
  * Las búsquedas repetidas se responden desde memoria.
  * Nos identificamos con un User-Agent propio.
  * Se muestra el crédito «© OpenStreetMap» junto a los resultados.
Esto alcanza para un uso moderado (un proyecto universitario). Con muchísimos
usuarios habría que usar un servicio propio o de pago.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

# Solo resultados dentro de Chile, con preferencia por Santiago.
CHILE_BBOX = (-75.8, -56.0, -66.4, -17.4)  # oeste, sur, este, norte
CENTRO_PREFERIDO = (-33.45, -70.66)  # Santiago
MAX_RESULTADOS = 5
SEGUNDOS_ENTRE_CONSULTAS = 1.1
HORAS_EN_MEMORIA = 24

URL_PHOTON = "https://photon.komoot.io/api/"
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_SITIO = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
USER_AGENT = "FaltaUno/1.0 (proyecto universitario" + (f"; {_SITIO}" if _SITIO else "") + ")"


class ErrorBusqueda(Exception):
    """Mensaje listo para mostrar si no se pudo buscar."""


@dataclass(frozen=True)
class Lugar:
    nombre: str
    detalle: str  # dirección o comuna
    lat: float
    lng: float

    @property
    def texto(self) -> str:
        """Lo que queda escrito en el campo «Lugar»."""
        completo = f"{self.nombre}, {self.detalle}" if self.detalle else self.nombre
        return completo[:120]


# --------------------------------------------------------------------------- #
# Lectura de las respuestas
# --------------------------------------------------------------------------- #


def _unir(*partes: str | None) -> str:
    vistas: list[str] = []
    for parte in partes:
        parte = (parte or "").strip()
        if parte and parte.lower() not in (v.lower() for v in vistas):
            vistas.append(parte)
    return ", ".join(vistas)


def _calle(calle: str | None, numero: str | None) -> str:
    return f"{calle} {numero}".strip() if calle and numero else (calle or "")


def desde_photon(respuesta: dict) -> list[Lugar]:
    lugares = []
    for f in respuesta.get("features") or []:
        try:
            lng, lat = f["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        p = f.get("properties") or {}
        calle = _calle(p.get("street"), p.get("housenumber"))
        nombre = p.get("name") or calle or p.get("district") or p.get("city")
        if not nombre:
            continue
        zona = p.get("district") or p.get("locality")
        detalle = _unir(calle if p.get("name") else "", zona, p.get("city"))
        if detalle.lower() == nombre.lower():
            detalle = ""
        lugares.append(Lugar(nombre, detalle, float(lat), float(lng)))
    return lugares


def desde_nominatim(respuesta: list) -> list[Lugar]:
    lugares = []
    for r in respuesta or []:
        try:
            lat, lng = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        a = r.get("address") or {}
        calle = _calle(a.get("road"), a.get("house_number"))
        partes_display = [x.strip() for x in (r.get("display_name") or "").split(",") if x.strip()]
        nombre = r.get("name") or calle or (partes_display[0] if partes_display else "")
        if not nombre:
            continue
        zona = a.get("suburb") or a.get("city_district") or a.get("neighbourhood")
        ciudad = a.get("city") or a.get("town") or a.get("village")
        detalle = _unir(calle if r.get("name") else "", zona, ciudad)
        if not detalle:
            detalle = _unir(*partes_display[1:4])
        if detalle.lower() == nombre.lower():
            detalle = ""
        lugares.append(Lugar(nombre, detalle, lat, lng))
    return lugares


def _sin_repetidos(lugares: list[Lugar]) -> list[Lugar]:
    vistos, unicos = set(), []
    for lugar in lugares:
        clave = (lugar.nombre.lower(), round(lugar.lat, 4), round(lugar.lng, 4))
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(lugar)
    return unicos[:MAX_RESULTADOS]


# --------------------------------------------------------------------------- #
# Consultas (con turno de 1 por segundo y memoria)
# --------------------------------------------------------------------------- #

_turno = threading.Lock()
_ultima_consulta = 0.0
_memoria: dict[str, tuple[float, list[Lugar]]] = {}


def _pedir_json(url: str):
    """GET respetando 1 consulta por segundo para toda la página."""
    global _ultima_consulta
    with _turno:
        espera = SEGUNDOS_ENTRE_CONSULTAS - (time.monotonic() - _ultima_consulta)
        if espera > 0:
            time.sleep(espera)
        _ultima_consulta = time.monotonic()
    pedido = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"}
    )
    with urllib.request.urlopen(pedido, timeout=8) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def _url_photon(consulta: str) -> str:
    oeste, sur, este, norte = CHILE_BBOX
    lat, lng = CENTRO_PREFERIDO
    return URL_PHOTON + "?" + urllib.parse.urlencode(
        {
            "q": consulta,
            "limit": MAX_RESULTADOS + 3,
            "bbox": f"{oeste},{sur},{este},{norte}",
            "lat": lat,
            "lon": lng,
        }
    )


def _url_nominatim(consulta: str) -> str:
    return URL_NOMINATIM + "?" + urllib.parse.urlencode(
        {
            "q": consulta,
            "format": "jsonv2",
            "limit": MAX_RESULTADOS,
            "countrycodes": "cl",
            "addressdetails": 1,
            "accept-language": "es",
        }
    )


def buscar(consulta: str | None) -> list[Lugar]:
    """
    Busca lugares en Chile. Devuelve hasta 5 (puede ser una lista vacía).
    Lanza ErrorBusqueda si ningún servicio respondió.
    """
    consulta = " ".join((consulta or "").split())
    if len(consulta) < 3:
        raise ErrorBusqueda("Escribe al menos 3 letras del lugar para buscarlo.")
    clave = consulta.lower()
    guardado = _memoria.get(clave)
    if guardado and time.time() - guardado[0] < HORAS_EN_MEMORIA * 3600:
        return guardado[1]

    errores = 0
    resultados: list[Lugar] = []
    for url, leer in ((_url_photon(consulta), desde_photon), (_url_nominatim(consulta), desde_nominatim)):
        try:
            resultados = _sin_repetidos(leer(_pedir_json(url)))
        except Exception as error:  # servicio caído, sin internet, respuesta rara…
            errores += 1
            print(f"[lugares] no se pudo consultar {url.split('?')[0]}: {error}", flush=True)
            continue
        if resultados:
            break

    if errores == 2:
        raise ErrorBusqueda("No pudimos buscar en el mapa ahora. Escribe el lugar a mano.")
    if len(_memoria) > 500:
        _memoria.clear()
    _memoria[clave] = (time.time(), resultados)
    return resultados
