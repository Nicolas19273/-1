"""
lugares.py — Buscar lugares reales de Osorno (canchas, restaurantes, plazas…).

Usa servicios gratuitos basados en OpenStreetMap, sin claves ni tarjeta:
  1. Photon (photon.komoot.io), pensado para búsquedas rápidas.
  2. Nominatim (nominatim.openstreetmap.org) como respaldo si Photon falla.

Todo vive en la clase BuscadorLugares («servicio» en el diagrama UML). Al
final se crea una sola instancia y sus métodos quedan también como funciones
del módulo (lugares.buscar(...)), que es como los usa el resto del programa.

Todo queda dentro de ZONA (Osorno y alrededores): los servicios reciben la zona
y además se descarta en Python cualquier resultado que caiga fuera. Para
cambiar de ciudad basta con cambiar CENTRO y ZONA.

Reglas de uso que respetamos (sobre todo las de Nominatim:
https://operations.osmfoundation.org/policies/nominatim/):
  * Solo se consulta cuando la persona toca «Buscar» o toca el mapa
    (nada de autocompletar mientras escribe).
  * Máximo 1 consulta por segundo, para toda la página.
  * Las consultas repetidas se responden desde memoria.
  * Nos identificamos con un User-Agent propio.
  * Se muestra el crédito «© OpenStreetMap» junto a los resultados y el mapa.
Esto alcanza para un uso moderado (un proyecto universitario). Con muchísimos
usuarios habría que usar un servicio propio o de pago.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

# Osorno: Plaza de Armas y un recuadro de unos 18 km hacia cada lado, que
# cubre la ciudad y sus sectores (Rahue, Ovejería, Las Quemas, Pilauco…).
NOMBRE_ZONA = "Osorno"
CENTRO = (-40.57395, -73.13348)  # lat, lng
ZONA = (-73.35, -40.75, -72.90, -40.42)  # oeste, sur, este, norte
ZOOM_MINIMO = 12  # el mapa no se aleja más que esto (se ve Osorno completo)

MAX_RESULTADOS = 5
SEGUNDOS_ENTRE_CONSULTAS = 1.1
HORAS_EN_MEMORIA = 24

URL_PHOTON = "https://photon.komoot.io/api/"
URL_PHOTON_INVERSA = "https://photon.komoot.io/reverse"
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
URL_NOMINATIM_INVERSA = "https://nominatim.openstreetmap.org/reverse"
_SITIO = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
USER_AGENT = "FaltaUno/1.0 (proyecto universitario" + (f"; {_SITIO}" if _SITIO else "") + ")"


class ErrorBusqueda(Exception):
    """Mensaje listo para mostrar si no se pudo buscar."""



# --------------------------------------------------------------------------- #
# Tipo de lugar (para mostrar un ícono y una etiqueta en los resultados)
# --------------------------------------------------------------------------- #

# (clave OSM, valor OSM) -> (ícono de Material Icons, etiqueta). "*" = cualquier valor.
_TIPOS: dict[tuple[str, str], tuple[str, str]] = {
    ("leisure", "pitch"): ("sports_soccer", "Cancha"),
    ("leisure", "sports_centre"): ("sports", "Centro deportivo"),
    ("leisure", "stadium"): ("sports", "Estadio"),
    ("leisure", "sports_hall"): ("sports", "Gimnasio"),
    ("leisure", "fitness_centre"): ("fitness_center", "Gimnasio"),
    ("leisure", "swimming_pool"): ("pool", "Piscina"),
    ("leisure", "track"): ("sports", "Pista"),
    ("leisure", "park"): ("park", "Parque"),
    ("leisure", "garden"): ("park", "Jardín"),
    ("leisure", "playground"): ("park", "Juegos infantiles"),
    ("amenity", "restaurant"): ("restaurant", "Restaurante"),
    ("amenity", "fast_food"): ("fastfood", "Comida rápida"),
    ("amenity", "food_court"): ("restaurant", "Patio de comidas"),
    ("amenity", "cafe"): ("local_cafe", "Café"),
    ("amenity", "ice_cream"): ("local_cafe", "Heladería"),
    ("amenity", "bar"): ("local_bar", "Bar"),
    ("amenity", "pub"): ("local_bar", "Pub"),
    ("amenity", "school"): ("school", "Colegio"),
    ("amenity", "kindergarten"): ("school", "Jardín infantil"),
    ("amenity", "college"): ("school", "Instituto"),
    ("amenity", "university"): ("school", "Universidad"),
    ("amenity", "library"): ("local_library", "Biblioteca"),
    ("amenity", "community_centre"): ("groups", "Centro comunitario"),
    ("amenity", "cinema"): ("theaters", "Cine"),
    ("amenity", "theatre"): ("theaters", "Teatro"),
    ("amenity", "arts_centre"): ("theaters", "Centro cultural"),
    ("amenity", "hospital"): ("local_hospital", "Hospital"),
    ("amenity", "clinic"): ("local_hospital", "Clínica"),
    ("amenity", "parking"): ("local_parking", "Estacionamiento"),
    ("amenity", "bus_station"): ("directions_bus", "Terminal de buses"),
    ("highway", "bus_stop"): ("directions_bus", "Paradero"),
    ("highway", "*"): ("directions", "Calle"),
    ("shop", "supermarket"): ("shopping_cart", "Supermercado"),
    ("shop", "mall"): ("local_mall", "Mall"),
    ("shop", "*"): ("store", "Tienda"),
    ("tourism", "hotel"): ("hotel", "Hotel"),
    ("tourism", "hostel"): ("hotel", "Hostal"),
    ("tourism", "museum"): ("museum", "Museo"),
    ("tourism", "viewpoint"): ("photo_camera", "Mirador"),
    ("place", "house"): ("home", "Dirección"),
    ("place", "suburb"): ("location_city", "Sector"),
    ("place", "neighbourhood"): ("location_city", "Barrio"),
    ("place", "quarter"): ("location_city", "Barrio"),
    ("place", "*"): ("location_city", "Localidad"),
    ("building", "*"): ("apartment", "Edificio"),
}



@dataclass(frozen=True)
class Lugar:
    nombre: str
    detalle: str  # dirección y sector
    lat: float
    lng: float
    icono: str = "place"
    tipo: str = ""  # «Cancha», «Restaurante»… (puede ir vacío)

    @property
    def texto(self) -> str:
        """Lo que queda escrito en el campo «Lugar»."""
        completo = f"{self.nombre}, {self.detalle}" if self.detalle else self.nombre
        return completo[:120]

    @property
    def detalle_corto(self) -> str:
        """El detalle sin repetir «Osorno» (todo es de Osorno)."""
        return ", ".join(
            parte for parte in self.detalle.split(", ") if parte.strip().lower() != NOMBRE_ZONA.lower()
        )



class BuscadorLugares:
    """
    «servicio» Busca lugares y direcciones de Osorno en OpenStreetMap
    (Photon y, si falla, Nominatim), respetando 1 consulta por segundo.
    """

    NOMBRE_ZONA = NOMBRE_ZONA
    CENTRO = CENTRO
    ZONA = ZONA
    ZOOM_MINIMO = ZOOM_MINIMO
    MAX_RESULTADOS = MAX_RESULTADOS
    SEGUNDOS_ENTRE_CONSULTAS = SEGUNDOS_ENTRE_CONSULTAS
    URL_PHOTON = URL_PHOTON
    URL_NOMINATIM = URL_NOMINATIM

    def __init__(self) -> None:
        self.__turno = threading.Lock()
        self.__ultima_consulta = 0.0
        self.__memoria: dict[str, tuple[float, list[Lugar]]] = {}
        self.__memoria_direcciones: dict[tuple[float, float], tuple[float, str | None]] = {}

    # ------------------------------------------------------------------ #
    # Zona y distancias
    # ------------------------------------------------------------------ #

    @staticmethod
    def metros(punto_a: tuple[float, float], punto_b: tuple[float, float]) -> float:
        """Distancia aproximada en metros entre (lat, lng) y (lat, lng)
        (de sobra para distancias dentro de una ciudad)."""
        (lat1, lng1), (lat2, lng2) = punto_a, punto_b
        dy = (lat2 - lat1) * 111_320
        dx = (lng2 - lng1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
        return math.hypot(dx, dy)

    def dentro_de_zona(self, lat, lng) -> bool:
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return False
        oeste, sur, este, norte = self.ZONA
        return sur <= lat <= norte and oeste <= lng <= este

    # ------------------------------------------------------------------ #
    # Lectura de las respuestas
    # ------------------------------------------------------------------ #

    @staticmethod
    def tipo_de(clave: str | None, valor: str | None) -> tuple[str, str]:
        """(ícono, etiqueta) según las etiquetas de OpenStreetMap; si no se conoce, un pin."""
        clave, valor = (clave or "").lower(), (valor or "").lower()
        return _TIPOS.get((clave, valor)) or _TIPOS.get((clave, "*")) or ("place", "")

    @staticmethod
    def _unir(*partes: str | None) -> str:
        vistas: list[str] = []
        for parte in partes:
            parte = (parte or "").strip()
            if parte and parte.lower() not in (v.lower() for v in vistas):
                vistas.append(parte)
        return ", ".join(vistas)

    @staticmethod
    def _calle(calle: str | None, numero: str | None) -> str:
        return f"{calle} {numero}".strip() if calle and numero else (calle or "")

    def desde_photon(self, respuesta: dict) -> list[Lugar]:
        lugares = []
        if not isinstance(respuesta, dict):
            return lugares
        for f in respuesta.get("features") or []:
            try:
                lng, lat = f["geometry"]["coordinates"][:2]
            except (KeyError, TypeError, ValueError):
                continue
            p = f.get("properties") or {}
            calle = self._calle(p.get("street"), p.get("housenumber"))
            nombre = p.get("name") or calle or p.get("district") or p.get("city")
            if not nombre:
                continue
            zona = p.get("district") or p.get("locality")
            detalle = self._unir(calle if p.get("name") else "", zona, p.get("city"))
            if detalle.lower() == nombre.lower():
                detalle = ""
            icono, tipo = self.tipo_de(p.get("osm_key"), p.get("osm_value"))
            lugares.append(Lugar(nombre, detalle, float(lat), float(lng), icono, tipo))
        return lugares

    def desde_nominatim(self, respuesta: list) -> list[Lugar]:
        lugares = []
        for r in respuesta or []:
            try:
                lat, lng = float(r["lat"]), float(r["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            a = r.get("address") or {}
            calle = self._calle(a.get("road"), a.get("house_number"))
            partes_display = [x.strip() for x in (r.get("display_name") or "").split(",") if x.strip()]
            nombre = r.get("name") or calle or (partes_display[0] if partes_display else "")
            if not nombre:
                continue
            zona = a.get("suburb") or a.get("city_district") or a.get("neighbourhood")
            ciudad = a.get("city") or a.get("town") or a.get("village")
            detalle = self._unir(calle if r.get("name") else "", zona, ciudad)
            if not detalle:
                detalle = self._unir(*partes_display[1:4])
            if detalle.lower() == nombre.lower():
                detalle = ""
            icono, tipo = self.tipo_de(r.get("category") or r.get("class"), r.get("type"))
            lugares.append(Lugar(nombre, detalle, lat, lng, icono, tipo))
        return lugares

    def _sin_repetidos(self, lugares: list[Lugar]) -> list[Lugar]:
        vistos, unicos = set(), []
        for lugar in lugares:
            clave = (lugar.nombre.lower(), round(lugar.lat, 4), round(lugar.lng, 4))
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(lugar)
        return unicos[: self.MAX_RESULTADOS]

    def _solo_en_zona(self, lugares: list[Lugar]) -> list[Lugar]:
        return [lugar for lugar in lugares if self.dentro_de_zona(lugar.lat, lugar.lng)]

    def _texto_direccion(self, calle: str, nombre: str | None, zona: str | None, ciudad: str | None) -> str | None:
        """Para un punto tocado en el mapa se prefiere la dirección (calle y número)
        antes que el nombre del negocio más cercano; un parque o una cancha sin
        dirección quedan con su nombre."""
        principal = (calle or nombre or "").strip()
        if not principal:
            return None
        return self._unir(principal, zona, ciudad)[:120]

    def direccion_desde_photon(self, respuesta) -> str | None:
        if not isinstance(respuesta, dict):
            return None
        for f in respuesta.get("features") or []:
            p = f.get("properties") or {}
            texto = self._texto_direccion(
                self._calle(p.get("street"), p.get("housenumber")),
                p.get("name"),
                p.get("district") or p.get("locality"),
                p.get("city"),
            )
            if texto:
                return texto
        return None

    def direccion_desde_nominatim(self, respuesta) -> str | None:
        if not isinstance(respuesta, dict) or "error" in respuesta:
            return None
        a = respuesta.get("address") or {}
        return self._texto_direccion(
            self._calle(a.get("road"), a.get("house_number")),
            respuesta.get("name"),
            a.get("suburb") or a.get("city_district") or a.get("neighbourhood"),
            a.get("city") or a.get("town") or a.get("village"),
        )

    # ------------------------------------------------------------------ #
    # Consultas (con turno de 1 por segundo y memoria)
    # ------------------------------------------------------------------ #

    def _pedir_json(self, url: str):
        """GET respetando 1 consulta por segundo para toda la página."""
        with self.__turno:
            espera = self.SEGUNDOS_ENTRE_CONSULTAS - (time.monotonic() - self.__ultima_consulta)
            if espera > 0:
                time.sleep(espera)
            self.__ultima_consulta = time.monotonic()
        pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "es"})
        with urllib.request.urlopen(pedido, timeout=8) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))

    def _url_photon(self, consulta: str) -> str:
        oeste, sur, este, norte = self.ZONA
        lat, lng = self.CENTRO
        return self.URL_PHOTON + "?" + urllib.parse.urlencode(
            {
                "q": consulta,
                "limit": self.MAX_RESULTADOS + 3,
                "bbox": f"{oeste},{sur},{este},{norte}",
                "lat": lat,
                "lon": lng,
            }
        )

    def _url_nominatim(self, consulta: str) -> str:
        oeste, sur, este, norte = self.ZONA
        return self.URL_NOMINATIM + "?" + urllib.parse.urlencode(
            {
                "q": consulta,
                "format": "jsonv2",
                "limit": self.MAX_RESULTADOS,
                "countrycodes": "cl",
                "viewbox": f"{oeste},{norte},{este},{sur}",
                "bounded": 1,  # solo dentro del recuadro (sin esto, es solo una preferencia)
                "addressdetails": 1,
                "accept-language": "es",
            }
        )

    @staticmethod
    def _url_photon_inversa(lat: float, lng: float) -> str:
        return URL_PHOTON_INVERSA + "?" + urllib.parse.urlencode({"lat": lat, "lon": lng, "limit": 1})

    @staticmethod
    def _url_nominatim_inversa(lat: float, lng: float) -> str:
        return URL_NOMINATIM_INVERSA + "?" + urllib.parse.urlencode(
            {
                "lat": lat,
                "lon": lng,
                "format": "jsonv2",
                "zoom": 18,
                "addressdetails": 1,
                "accept-language": "es",
            }
        )

    def buscar(self, consulta: str | None) -> list[Lugar]:
        """
        Busca lugares dentro de Osorno. Devuelve hasta 5 (puede ser una lista vacía).
        Lanza ErrorBusqueda si ningún servicio respondió.
        """
        consulta = " ".join((consulta or "").split())
        if len(consulta) < 3:
            raise ErrorBusqueda("Escribe al menos 3 letras del lugar para buscarlo.")
        clave = consulta.lower()
        guardado = self.__memoria.get(clave)
        if guardado and time.time() - guardado[0] < HORAS_EN_MEMORIA * 3600:
            return guardado[1]

        errores = 0
        resultados: list[Lugar] = []
        for url, leer in (
            (self._url_photon(consulta), self.desde_photon),
            (self._url_nominatim(consulta), self.desde_nominatim),
        ):
            try:
                resultados = self._sin_repetidos(self._solo_en_zona(leer(self._pedir_json(url))))
            except Exception as error:  # servicio caído, sin internet, respuesta rara…
                errores += 1
                print(f"[lugares] no se pudo consultar {url.split('?')[0]}: {error}", flush=True)
                continue
            if resultados:
                break

        if errores == 2:
            raise ErrorBusqueda("No pudimos buscar en el mapa ahora. Escribe el lugar a mano.")
        if len(self.__memoria) > 500:
            self.__memoria.clear()
        self.__memoria[clave] = (time.time(), resultados)
        return resultados

    def direccion_de(self, lat, lng) -> str | None:
        """
        Dirección aproximada de un punto tocado en el mapa (ej: «Bulnes 750, Osorno»),
        para sugerirla en el campo «Lugar». None si no se encontró o el punto está
        fuera de la zona. Nunca lanza errores: es solo una ayuda.
        """
        if not self.dentro_de_zona(lat, lng):
            return None
        # ~10 metros de precisión: basta para una dirección y repite menos consultas
        clave = (round(float(lat), 4), round(float(lng), 4))
        guardado = self.__memoria_direcciones.get(clave)
        if guardado and time.time() - guardado[0] < HORAS_EN_MEMORIA * 3600:
            return guardado[1]

        respondio, texto = False, None
        for url, leer in (
            (self._url_photon_inversa(*clave), self.direccion_desde_photon),
            (self._url_nominatim_inversa(*clave), self.direccion_desde_nominatim),
        ):
            try:
                texto = leer(self._pedir_json(url))
                respondio = True
            except Exception as error:
                print(f"[lugares] no se pudo consultar {url.split('?')[0]}: {error}", flush=True)
                continue
            if texto:
                break

        if respondio:  # si ninguno respondió, no se guarda: puede andar a la próxima
            if len(self.__memoria_direcciones) > 2000:
                self.__memoria_direcciones.clear()
            self.__memoria_direcciones[clave] = (time.time(), texto)
        return texto


# --------------------------------------------------------------------------- #
# Una sola instancia para toda la página; sus métodos, como funciones del módulo
# --------------------------------------------------------------------------- #

buscador = BuscadorLugares()
metros = buscador.metros
dentro_de_zona = buscador.dentro_de_zona
tipo_de = buscador.tipo_de
desde_photon = buscador.desde_photon
desde_nominatim = buscador.desde_nominatim
direccion_desde_photon = buscador.direccion_desde_photon
direccion_desde_nominatim = buscador.direccion_desde_nominatim
_sin_repetidos = buscador._sin_repetidos
_solo_en_zona = buscador._solo_en_zona
_url_photon = buscador._url_photon
_url_nominatim = buscador._url_nominatim
_url_photon_inversa = buscador._url_photon_inversa
_url_nominatim_inversa = buscador._url_nominatim_inversa
buscar = buscador.buscar
direccion_de = buscador.direccion_de
