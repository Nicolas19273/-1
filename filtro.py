"""
filtro.py — Detecta palabras inapropiadas (groserías, insultos, términos
sexuales vulgares y ofensas discriminatorias) en español —con chilenismos—
y en inglés. Solo Python, sin librerías externas.

Todo vive en la clase FiltroPalabras («servicio» en el diagrama UML). Al
final del archivo se crea una sola instancia y sus métodos quedan también
como funciones del módulo (filtro.contiene(...)), que es como los usa el
resto del programa.

Qué hace:
  * contiene(texto)    -> True si encontró alguna
  * encontradas(texto) -> cuáles, tal como se escribieron (para avisarle a la persona)
  * quitar(texto)      -> el texto sin esas palabras (para lo que ya estaba guardado)

Trucos que detecta:
  * Mayúsculas y tildes:            WEÓN, Weón, weon
  * Números o símbolos por letras:  w3on, p4ja, mi3rd4, $hit, @weonao
  * Letras repetidas:               weooooon, ctmmmm, puuuta
  * Letras separadas:               p.u.t.a, c u l o, m-i-e-r-d-a
  * Palabras pegadas a otras:       weonculiao, conchetumaaare
  * Frases:                         "concha de tu madre", "chupa pico"

Cuida no tachar palabras normales que contienen una grosería adentro, por
ejemplo: película, ridículo, vehículo, computadora, disputa, Vergara,
Putaendo, Culiacán, "las 5 y pico", "Coca-Cola", "polla" (lotería), año.

Reglas propias (desde el panel /admin, sin tocar el código):
  Cada regla es una palabra o frase que se filtra:
    * siempre, o
    * solo en contexto: cuando aparece cerca (hasta 3 palabras antes o
      después) de alguna de sus "palabras de contexto";
  y nunca dentro de sus "excepciones". Ejemplo: «pico» se filtra cerca de
  «chupa» o «mi», pero nunca en «y pico» ni en «pico de».
  Las carga datos.py con configurar(...) y valen al instante.

Ningún filtro es perfecto: siempre puede aparecer una forma nueva de
escribir algo. Para agregar o quitar palabras de la lista base, edita las
listas de abajo (o agrega reglas propias desde /admin).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Listas: viven en filtro_listas.py (palabras, pedazos, frases y reglas de contexto)
# --------------------------------------------------------------------------- #

import filtro_listas as _listas  # noqa: E402

PALABRAS = _listas.PALABRAS
PEDAZOS = _listas.PEDAZOS
FRASES = _listas.FRASES
PERMITIDAS = _listas.PERMITIDAS

# --------------------------------------------------------------------------- #
# Reglas propias (se agregan desde /admin)
# --------------------------------------------------------------------------- #

VENTANA = 3  # cuántas palabras antes o después se mira para el contexto


@dataclass(frozen=True)
class Regla:
    id: int
    palabra: str  # palabra o frase
    cerca_de: tuple[str, ...] = ()  # vacío = se filtra siempre
    excepto: tuple[str, ...] = ()  # frases donde nunca se filtra
    salvo: tuple[str, ...] = ()  # si alguna aparece en el texto, no se filtra (charla, prevención...)

    @property
    def siempre(self) -> bool:
        return not self.cerca_de


def _reglas_base() -> list[Regla]:
    """Las reglas de contexto que trae el filtro (filtro_listas.REGLAS_BASE), con id 0."""
    reglas = []
    for palabras, cerca, excepto, salvo in _listas.REGLAS_BASE:
        formas = palabras if isinstance(palabras, list) else palabras.split()
        for forma in formas:
            reglas.append(Regla(0, forma, tuple(cerca), tuple(excepto), tuple(salvo)))
    return reglas


REGLAS_BASE = _reglas_base()


_MARCA_ENE = ""  # para que la ñ no se convierta en n (año ≠ ano)
_PALABRA = re.compile(r"[\w@$€]+")


class FiltroPalabras:
    """
    «servicio» Detecta palabras inapropiadas, incluso escritas con trucos.

    Las listas base (PALABRAS, PEDAZOS, FRASES) son públicas; sus versiones
    ya normalizadas y las reglas propias son privadas.
    """

    PALABRAS = PALABRAS
    PEDAZOS = PEDAZOS
    FRASES = FRASES
    PERMITIDAS = PERMITIDAS
    REGLAS_BASE = REGLAS_BASE
    VENTANA = VENTANA

    def __init__(self) -> None:
        self.__letras_por_simbolos = str.maketrans(
            {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "€": "e"}
        )
        assert all(re.search(r"(.)\1\1", p) is None for p in self.PALABRAS.split()), (
            "No pongas en la lista palabras con 3 letras iguales seguidas (se confundirían)"
        )
        self.__lista = {self.normalizar(p) for p in self.PALABRAS.split()}
        # Para "weoon" -> "weon": solo con palabras que no tienen letras dobles
        # propias (así "pera" no se confunde con "perra").
        self.__lista_sin_dobles = {p for p in self.__lista if not self._tiene_dobles(p)}
        self.__pedazos = [self.normalizar(p) for p in self.PEDAZOS.split()]
        self.__frases = [[self.normalizar(p) for p in frase.split()] for frase in self.FRASES]
        self.__permitidas = {self.normalizar(p) for p in self.PERMITIDAS.split()}
        self.__base = self._compilar(self.REGLAS_BASE)  # las del archivo: siempre están
        self.__reglas: list = []  # las propias (desde la administración)
        self.__indice: dict[str, list] = {}
        self._indexar()

    # ------------------------------------------------------------------ #
    # Normalización: lleva cada palabra a una forma simple para comparar
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sin_tildes(texto: str) -> str:
        texto = texto.replace("ñ", _MARCA_ENE)
        texto = unicodedata.normalize("NFD", texto)
        texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
        return texto.replace(_MARCA_ENE, "ñ")

    def normalizar(self, palabra: str) -> str:
        """'WEÓÓÓN' -> 'weoon' · 'w3on' -> 'weon' · 'p_u_t_a' -> 'puta'"""
        t = self._sin_tildes(palabra.lower()).translate(self.__letras_por_simbolos).replace("_", "")
        return re.sub(r"(.)\1{2,}", r"\1\1", t)  # 3 o más letras iguales -> 2

    @staticmethod
    def _sin_dobles(t: str) -> str:
        return re.sub(r"(.)\1", r"\1", t)

    @staticmethod
    def _tiene_dobles(t: str) -> bool:
        return re.search(r"(.)\1", t) is not None

    def _es_mala(self, forma: str) -> bool:
        if not forma or forma in self.__permitidas:
            return False
        if forma in self.__lista:
            return True
        sin_dobles = self._sin_dobles(forma)
        if sin_dobles in self.__lista_sin_dobles:
            return True
        return any(p in forma or p in sin_dobles for p in self.__pedazos)

    # ------------------------------------------------------------------ #
    # Reglas propias (las carga datos.py desde la base de datos)
    # ------------------------------------------------------------------ #

    def _formas(self, frase: str) -> list[str]:
        return [self.normalizar(m.group()) for m in _PALABRA.finditer(frase or "")]

    def _compilar(self, reglas: list[Regla]) -> list:
        compiladas = []
        for regla in reglas:
            frase = self._formas(regla.palabra)
            if frase:
                cerca = [f for f in (self._formas(c) for c in regla.cerca_de) if f]
                excepto = [f for f in (self._formas(e) for e in regla.excepto) if f]
                salvo = [f for f in (self._formas(e) for e in regla.salvo) if f]
                compiladas.append((regla, frase, cerca, excepto, salvo))
        return compiladas

    def _indexar(self) -> None:
        """Agrupa las reglas por su primera palabra, para mirar solo las que pueden calzar."""
        indice: dict[str, list] = {}
        for compilada in self.__base + self.__reglas:
            indice.setdefault(compilada[1][0], []).append(compilada)
        self.__indice = indice

    def configurar(self, reglas: list[Regla]) -> None:
        """Reemplaza las reglas propias. Valen desde el siguiente texto revisado."""
        self.__reglas = self._compilar(reglas)
        self._indexar()

    def reglas_actuales(self) -> list[Regla]:
        return [r for r, *_ in self.__reglas]

    def cantidad_base(self) -> dict[str, int]:
        """Cuánto trae el filtro de fábrica (para mostrarlo en la administración)."""
        return {
            "palabras": len(set(self.PALABRAS.split())),
            "frases": len(self.FRASES),
            "reglas": len(self.__base),
        }

    def palabras_base(self) -> list[str]:
        """La lista base (la de este archivo), para mostrarla en /admin."""
        return sorted(set(self.PALABRAS.split()))

    def _igual(self, forma: str, objetivo: str) -> bool:
        return forma == objetivo or (not self._tiene_dobles(objetivo) and self._sin_dobles(forma) == objetivo)

    def _apariciones(self, formas: list[str], frase: list[str]) -> list[int]:
        n = len(frase)
        return [
            i
            for i in range(len(formas) - n + 1)
            if all(self._igual(formas[i + k], frase[k]) for k in range(n))
        ]

    def _calza_en(self, formas: list[str], i: int, frase: list[str]) -> bool:
        n = len(frase)
        return i + n <= len(formas) and all(self._igual(formas[i + k], frase[k]) for k in range(n))

    def _tramos_de_reglas(self, fichas) -> list[tuple[int, int]]:
        formas = [f for _, _, f in fichas]
        tramos = []
        for i, forma in enumerate(formas):
            claves = {forma, self._sin_dobles(forma)}
            for clave in claves:
                for _regla, frase, cerca, excepto, salvo in self.__indice.get(clave, ()):
                    if not self._calza_en(formas, i, frase):
                        continue
                    j = i + len(frase)
                    # ¿Está dentro de una excepción? ("y pico", "pico de")
                    if any(a <= i and j <= a + len(e) for e in excepto for a in self._apariciones(formas, e)):
                        continue
                    # ¿Tiene una palabra de contexto cerca?
                    if cerca:
                        desde, hasta = max(0, i - self.VENTANA), min(len(formas), j + self.VENTANA)
                        # cerca = alguna parte de la frase de contexto cae dentro de la ventana
                        if not any(
                            a < hasta and a + len(c) > desde and not (i <= a < j)
                            for c in cerca
                            for a in self._apariciones(formas, c)
                        ):
                            continue
                    # ¿Es una charla, una clase, prevención...? Entonces no
                    if salvo and any(self._apariciones(formas, e) for e in salvo):
                        continue
                    tramos.append((fichas[i][0], fichas[j - 1][1]))
        return tramos

    # ------------------------------------------------------------------ #
    # Búsqueda
    # ------------------------------------------------------------------ #

    def encontrar(self, texto: str | None) -> list[tuple[int, int]]:
        """Devuelve los tramos (inicio, fin) del texto que hay que tapar."""
        if not texto:
            return []
        fichas = [(m.start(), m.end(), self.normalizar(m.group())) for m in _PALABRA.finditer(texto)]
        tramos: list[tuple[int, int]] = []

        # 1) Palabras sueltas
        for inicio, fin, forma in fichas:
            if self._es_mala(forma):
                tramos.append((inicio, fin))

        # 2) Frases
        formas = [f for _, _, f in fichas]
        for frase in self.__frases:
            n = len(frase)
            for i in range(len(formas) - n + 1):
                if formas[i : i + n] == frase:
                    tramos.append((fichas[i][0], fichas[i + n - 1][1]))

        # 3) Letras separadas: "p.u.t.a", "c u l o"
        i = 0
        while i < len(fichas):
            j = i
            while j < len(fichas) and len(fichas[j][2]) == 1:
                j += 1
            if j - i >= 3:
                # se prueba cada tramo de 3 o más letras seguidas, del más largo al más corto
                for a in range(i, j - 2):
                    for b in range(j, a + 2, -1):
                        if self._es_mala("".join(f for _, _, f in fichas[a:b])):
                            tramos.append((fichas[a][0], fichas[b - 1][1]))
                            break
            i = max(j, i + 1)

        # 4) Reglas de contexto (las del archivo y las propias desde la administración)
        tramos.extend(self._tramos_de_reglas(fichas))

        return self._unir(tramos, texto)

    @staticmethod
    def _unir(tramos: list[tuple[int, int]], texto: str = "") -> list[tuple[int, int]]:
        """Junta los tramos que se tocan o que solo tienen espacios entre medio."""
        unidos: list[tuple[int, int]] = []
        for inicio, fin in sorted(tramos):
            if unidos and (inicio <= unidos[-1][1] or not texto[unidos[-1][1]:inicio].strip(" ")):
                unidos[-1] = (unidos[-1][0], max(fin, unidos[-1][1]))
            else:
                unidos.append((inicio, fin))
        return unidos

    def contiene(self, texto: str | None) -> bool:
        return bool(self.encontrar(texto))

    def encontradas(self, texto: str | None) -> list[str]:
        """Las palabras inapropiadas tal como se escribieron, sin repetir."""
        vistas: list[str] = []
        for inicio, fin in self.encontrar(texto):
            palabra = (texto or "")[inicio:fin]
            if palabra.lower() not in (v.lower() for v in vistas):
                vistas.append(palabra)
        return vistas

    @staticmethod
    def _ordenar_linea(linea: str) -> str:
        linea = re.sub(r"[ \t]{2,}", " ", linea)  # espacios dobles
        linea = re.sub(r"[ \t]+([,.;:!?)])", r"\1", linea)  # espacio antes de puntuación
        linea = re.sub(r"([,;:])(\s*[,;:.!?])+", r"\1", linea)  # puntuación repetida: ", ," -> ","
        linea = re.sub(r"^[\s,;:.!?-]+", "", linea)  # puntuación suelta al comienzo
        linea = re.sub(r"[\s,;:-]+$", "", linea)  # coma o guion colgando al final
        return linea.strip()

    def quitar(self, texto: str | None) -> str:
        """Borra las palabras inapropiadas y ordena los espacios y comas que sobran."""
        if not texto:
            return texto or ""
        tramos = self.encontrar(texto)
        if not tramos:
            return texto
        partes, ultimo = [], 0
        for inicio, fin in tramos:
            partes.append(texto[ultimo:inicio])
            ultimo = fin
        partes.append(texto[ultimo:])
        return "\n".join(self._ordenar_linea(l) for l in "".join(partes).split("\n")).strip()


# --------------------------------------------------------------------------- #
# Una sola instancia para toda la página; sus métodos, como funciones del módulo
# --------------------------------------------------------------------------- #

filtro_palabras = FiltroPalabras()
normalizar = filtro_palabras.normalizar
configurar = filtro_palabras.configurar
reglas_actuales = filtro_palabras.reglas_actuales
palabras_base = filtro_palabras.palabras_base
encontrar = filtro_palabras.encontrar
contiene = filtro_palabras.contiene
encontradas = filtro_palabras.encontradas
quitar = filtro_palabras.quitar
cantidad_base = filtro_palabras.cantidad_base
