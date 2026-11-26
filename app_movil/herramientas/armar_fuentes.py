"""
Arma las dos letras de la app a partir de Archivo (Omnibus-Type, licencia SIL OFL 1.1):

  Archivo.ttf             ancho normal, para el texto (peso 100–900, normal 400)
  ArchivoCondensada.ttf   angosta, para títulos y números (peso 400–900, normal 800)

Son la misma familia «variable» fijada en un ancho y recortada a los caracteres del
español (y algunos más), para que el APK no crezca de más. Flet elige el grosor con
FontWeight (W_400, W_800…).

Uso (una sola vez; los .ttf resultantes ya están en src/assets/fonts):
  python3 herramientas/armar_fuentes.py "Archivo[wdth,wght].ttf" src/assets/fonts
El archivo de origen está en https://github.com/google/fonts/tree/main/ofl/archivo
"""

import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Latín básico y Latín-1 (á é í ó ú ñ ü ¿ ¡ « »), Latín extendido A (nombres), comillas,
# guiones, puntos suspensivos, viñeta y el signo «+».
CARACTERES = "U+0020-007E,U+00A0-00FF,U+0100-017F,U+2010-2027,U+2030-203A,U+20AC,U+2122,U+2212"

VARIANTES = {
    "Archivo.ttf": {"wdth": 100, "wght": (100, 400, 900)},
    "ArchivoCondensada.ttf": {"wdth": 78, "wght": (400, 800, 900)},
}
NOMBRES = {"Archivo.ttf": "Archivo", "ArchivoCondensada.ttf": "Archivo Condensada"}


def armar(origen: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for archivo, ejes in VARIANTES.items():
        fuente = instancer.instantiateVariableFont(TTFont(origen), ejes)
        opciones = subset.Options()
        opciones.layout_features = ["*"]
        opciones.name_IDs = ["*"]
        opciones.notdef_outline = True
        recorte = subset.Subsetter(opciones)
        recorte.populate(unicodes=subset.parse_unicodes(CARACTERES))
        recorte.subset(fuente)
        nombre = NOMBRES[archivo]
        for registro in fuente["name"].names:
            if registro.nameID in (1, 16):
                registro.string = nombre
        fuente.save(destino / archivo)
        print(f"{archivo}: {(destino / archivo).stat().st_size // 1024} KB")


if __name__ == "__main__":
    armar(Path(sys.argv[1]), Path(sys.argv[2]))
