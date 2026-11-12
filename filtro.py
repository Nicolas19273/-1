"""
filtro.py — Detecta palabras inapropiadas (groserías, insultos, términos
sexuales vulgares y ofensas discriminatorias) en español —con chilenismos—
y en inglés. Solo Python, sin librerías externas.

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
# Listas (se pueden escribir con o sin tildes; se normalizan solas)
# --------------------------------------------------------------------------- #

# Palabras completas: se tachan cuando aparecen como palabra entera.
PALABRAS = """
puta putas puto putos putita putitas putito putitos puton putona putear puteada puteando
putero puteria putada putadas hijueputa hijueputas hijoputa hijaputa hijoeputa hdp hdlgp
ptm ptmr ptmre
mierda mierdas mierdero mierdoso mierdosa mrd
cagar cagada cagadas cagado cagada cagon cagona cagando cago cagas caga cagan cague cagaste
cago cagaron
cabron cabrona cabrones cabronas cabronazo carajo carajos coño coños
joder jodido jodida jodidos jodidas jodete joderse
verga vergas vergon vergudo
pendejo pendeja pendejos pendejas pendejada
culo culos culero culera culeros culeras culiao culiaos culiado culiados culiada culiadas
culia culiaa culear culiar culeado culeada culiando culeando
ql qlo qla qlia qliao qlao qls qlos
chucha chuchas chuchetumare chuchetumadre chuchatumadre chuchatumare
conchetumare conchetumadre conchatumadre conchatumare conchesumadre conchesumare
conchasumadre conchasumare ctm csm ctmr
weon weona weones weonas weonao weonada wea weas weado weada
huevon huevona huevones huevonas hueon hueona hueones hueonas gueon guevon guevona
wn wna wns aweonao aweonado aweonada aweona ahuevonado ahuevonada ahueonado ahueonada
maraco maracos marica maricas maricon maricones maricona mariconas mariconazo maricueca
fleto fletos colipato colipatos joto jotos sidoso sidosa travelo travelos bollera bolleras
tortillera tortilleras
mongolico mongolica mongolicos mongolo mongola subnormal subnormales
imbecil imbeciles idiota idiotas estupido estupida estupidos estupidas tarado tarada tarados
pelotudo pelotuda pelotudos pelotudas boludo boluda boludos gilipollas gilipolla
pichula pichulas pichulon zorra zorras perra perras malparido malparida malparidos
gonorrea chingar chingada chingado chingadera chinga chingue chingon pinche pinches
mamon mamona mamones mamada mamadas mamahuevo mamaguevo follar follando follada
teta tetas tetona tetonas pajero pajera pajeros pajeras pajearse
chupala chupalo chupamela chupamelo chupapico chupapija
flaite flaites sudaca sudacas veneco venecos nazi nazis hitler
porno porn nudes
fuck fucks fucking fuckin fucker fuckers fucked fck fk fuk fukin motherfucker motherfuckers
wtf stfu shit shits shitty bullshit bitch bitches bitchy asshole assholes ass dumbass jackass
cunt cunts pussy pussies dickhead cocksucker bastard bastards slut sluts whore whores
nigger niggers nigga niggas faggot faggots fag fags retard retarded twat wanker kys
"""

# Pedazos que se tachan aunque estén pegados a otras palabras. Solo se ponen
# aquí los que NO aparecen dentro de palabras normales del español.
PEDAZOS = """
conchetu conchatu conchesu conchasu chuchetu chuchatu hijueput hijodeput hijadeput hijoput
putamadr culiao culiado culiaos aweona ahueona ahuevona maricon pendej mierd
weon hueon huevon gilipoll mamahuev mamaguev chupapic motherf fuck
"""

# Frases: se tachan cuando aparecen juntas, en este orden.
FRASES = [
    "concha de tu madre",
    "concha e tu madre",
    "concha tu madre",
    "concha su madre",
    "chupa pico",
    "chupen pico",
    "chupa la",
    "me cago en",
]

# --------------------------------------------------------------------------- #
# Normalización: lleva cada palabra a una forma simple para comparar
# --------------------------------------------------------------------------- #

_LETRAS_POR_SIMBOLOS = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "€": "e"}
)
_MARCA_ENE = ""  # para que la ñ no se convierta en n (año ≠ ano)
_PALABRA = re.compile(r"[\w@$€]+")


def _sin_tildes(texto: str) -> str:
    texto = texto.replace("ñ", _MARCA_ENE)
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.replace(_MARCA_ENE, "ñ")


def normalizar(palabra: str) -> str:
    """'WEÓÓÓN' -> 'weoon' · 'w3on' -> 'weon' · 'p_u_t_a' -> 'puta'"""
    t = _sin_tildes(palabra.lower()).translate(_LETRAS_POR_SIMBOLOS).replace("_", "")
    return re.sub(r"(.)\1{2,}", r"\1\1", t)  # 3 o más letras iguales -> 2


def _sin_dobles(t: str) -> str:
    return re.sub(r"(.)\1", r"\1", t)


def _tiene_dobles(t: str) -> bool:
    return re.search(r"(.)\1", t) is not None


_LISTA = {normalizar(p) for p in PALABRAS.split()}
assert all(re.search(r"(.)\1\1", p) is None for p in PALABRAS.split()), (
    "No pongas en la lista palabras con 3 letras iguales seguidas (se confundirían)"
)
# Para "weoon" -> "weon": solo con palabras que no tienen letras dobles propias
# (así "pera" no se confunde con "perra").
_LISTA_SIN_DOBLES = {p for p in _LISTA if not _tiene_dobles(p)}
_PEDAZOS = [normalizar(p) for p in PEDAZOS.split()]
_FRASES = [[normalizar(p) for p in frase.split()] for frase in FRASES]


def _es_mala(forma: str) -> bool:
    if not forma:
        return False
    if forma in _LISTA:
        return True
    sin_dobles = _sin_dobles(forma)
    if sin_dobles in _LISTA_SIN_DOBLES:
        return True
    return any(p in forma or p in sin_dobles for p in _PEDAZOS)


# --------------------------------------------------------------------------- #
# Búsqueda
# --------------------------------------------------------------------------- #


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

    @property
    def siempre(self) -> bool:
        return not self.cerca_de


_reglas: list[tuple[Regla, list[str], list[list[str]], list[list[str]]]] = []


def _formas(frase: str) -> list[str]:
    return [normalizar(m.group()) for m in _PALABRA.finditer(frase or "")]


def configurar(reglas: list[Regla]) -> None:
    """Reemplaza las reglas propias. Valen desde el siguiente texto revisado."""
    global _reglas
    compiladas = []
    for regla in reglas:
        frase = _formas(regla.palabra)
        if frase:
            cerca = [f for f in (_formas(c) for c in regla.cerca_de) if f]
            excepto = [f for f in (_formas(e) for e in regla.excepto) if f]
            compiladas.append((regla, frase, cerca, excepto))
    _reglas = compiladas


def reglas_actuales() -> list[Regla]:
    return [r for r, *_ in _reglas]


def palabras_base() -> list[str]:
    """La lista base (la de este archivo), para mostrarla en /admin."""
    return sorted(set(PALABRAS.split()))


def _igual(forma: str, objetivo: str) -> bool:
    return forma == objetivo or (not _tiene_dobles(objetivo) and _sin_dobles(forma) == objetivo)


def _apariciones(formas: list[str], frase: list[str]) -> list[int]:
    n = len(frase)
    return [
        i
        for i in range(len(formas) - n + 1)
        if all(_igual(formas[i + k], frase[k]) for k in range(n))
    ]


def _tramos_de_reglas(fichas) -> list[tuple[int, int]]:
    formas = [f for _, _, f in fichas]
    tramos = []
    for _regla, frase, cerca, excepto in _reglas:
        for i in _apariciones(formas, frase):
            j = i + len(frase)
            # ¿Está dentro de una excepción? ("y pico", "pico de")
            if any(a <= i and j <= a + len(e) for e in excepto for a in _apariciones(formas, e)):
                continue
            # ¿Tiene una palabra de contexto cerca?
            if cerca:
                desde, hasta = max(0, i - VENTANA), min(len(formas), j + VENTANA)
                if not any(
                    desde <= a and a + len(c) <= hasta and not (i <= a < j)
                    for c in cerca
                    for a in _apariciones(formas, c)
                ):
                    continue
            tramos.append((fichas[i][0], fichas[j - 1][1]))
    return tramos


def encontrar(texto: str | None) -> list[tuple[int, int]]:
    """Devuelve los tramos (inicio, fin) del texto que hay que tapar."""
    if not texto:
        return []
    fichas = [(m.start(), m.end(), normalizar(m.group())) for m in _PALABRA.finditer(texto)]
    tramos: list[tuple[int, int]] = []

    # 1) Palabras sueltas
    for inicio, fin, forma in fichas:
        if _es_mala(forma):
            tramos.append((inicio, fin))

    # 2) Frases
    formas = [f for _, _, f in fichas]
    for frase in _FRASES:
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
                    if _es_mala("".join(f for _, _, f in fichas[a:b])):
                        tramos.append((fichas[a][0], fichas[b - 1][1]))
                        break
        i = max(j, i + 1)

    # 4) Reglas propias (desde /admin), con su contexto
    tramos.extend(_tramos_de_reglas(fichas))

    return _unir(tramos)


def _unir(tramos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unidos: list[tuple[int, int]] = []
    for inicio, fin in sorted(tramos):
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(fin, unidos[-1][1]))
        else:
            unidos.append((inicio, fin))
    return unidos


def contiene(texto: str | None) -> bool:
    return bool(encontrar(texto))


def encontradas(texto: str | None) -> list[str]:
    """Las palabras inapropiadas tal como se escribieron, sin repetir."""
    vistas: list[str] = []
    for inicio, fin in encontrar(texto):
        palabra = (texto or "")[inicio:fin]
        if palabra.lower() not in (v.lower() for v in vistas):
            vistas.append(palabra)
    return vistas


def _ordenar_linea(linea: str) -> str:
    linea = re.sub(r"[ \t]{2,}", " ", linea)  # espacios dobles
    linea = re.sub(r"[ \t]+([,.;:!?)])", r"\1", linea)  # espacio antes de puntuación
    linea = re.sub(r"([,;:])(\s*[,;:.!?])+", r"\1", linea)  # puntuación repetida: ", ," -> ","
    linea = re.sub(r"^[\s,;:.!?-]+", "", linea)  # puntuación suelta al comienzo
    linea = re.sub(r"[\s,;:-]+$", "", linea)  # coma o guion colgando al final
    return linea.strip()


def quitar(texto: str | None) -> str:
    """Borra las palabras inapropiadas y ordena los espacios y comas que sobran."""
    if not texto:
        return texto or ""
    tramos = encontrar(texto)
    if not tramos:
        return texto
    partes, ultimo = [], 0
    for inicio, fin in tramos:
        partes.append(texto[ultimo:inicio])
        ultimo = fin
    partes.append(texto[ultimo:])
    return "\n".join(_ordenar_linea(l) for l in "".join(partes).split("\n")).strip()
