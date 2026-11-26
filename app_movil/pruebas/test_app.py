"""
Prueba la app de Android de punta a punta, sin celular: arma las pantallas de
verdad (Flet), toca botones y escribe en los campos como lo haría una persona,
y habla con un servidor de Join In real que corre en este computador
(app.py de la raíz, con una base SQLite de prueba y sin enviar correos).

    python app_movil/pruebas/test_app.py

Necesita: flet, starlette, uvicorn, tzdata, certifi (requirements de la raíz + flet).
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "app_movil" / "src"))

os.environ.pop("BREVO_API_KEY", None)  # modo de prueba: el código se muestra en vez de enviarse por correo

# ----------------------------------------------------------------------------- servidor
import datos  # noqa: E402

if not datos.usa_postgres():
    datos.RUTA_BD = Path(tempfile.mkdtemp()) / "app.db"

import uvicorn  # noqa: E402

import acceso  # noqa: E402
import app as servidor_app  # noqa: E402
import filtro  # noqa: E402
import lugares  # noqa: E402

CLAVE = "clave-de-prueba-app"
datos.administracion.usar_clave(CLAVE)
acceso.acceso.SEGUNDOS_ENTRE_ENVIOS = 0
lugares.buscador.buscar = lambda q: (
    [lugares.Lugar("Cancha ULagos", "Av. Fuchslocher, Osorno", -40.58, -73.09, tipo="Cancha")] if q else []
)

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PUERTO = s.getsockname()[1]
_uvicorn = uvicorn.Server(uvicorn.Config(servidor_app.servidor, host="127.0.0.1", port=PUERTO, log_level="warning"))
threading.Thread(target=_uvicorn.run, daemon=True).start()
for _ in range(200):
    if _uvicorn.started:
        break
    time.sleep(0.05)
assert _uvicorn.started, "el servidor de prueba no partió"
BASE = f"http://127.0.0.1:{PUERTO}"

# ----------------------------------------------------------------------------- app
import flet as ft  # noqa: E402

from joinin import formato  # noqa: E402
from joinin.app import Almacen, AppJoinIn  # noqa: E402

FLET_REAL = not getattr(ft, "FALSO", False)


class PaginaFalsa:
    """Lo que la app usa de ft.Page: vistas, diálogos y actualizar."""

    def __init__(self):
        self.views: list = []
        self.dialogos: list = []
        self.avisos: list[str] = []
        self.on_view_pop = None
        self.actualizaciones = 0

    def update(self, *controles):
        self.actualizaciones += 1

    def show_dialog(self, dialogo):
        dialogo.open = True
        if type(dialogo).__name__ == "SnackBar":
            contenido = dialogo.content
            self.avisos.append(contenido if isinstance(contenido, str) else contenido.value)
        else:
            self.dialogos.append(dialogo)

    def pop_dialog(self):
        raise AssertionError("la app no debe usar pop_dialog (puede cerrar un aviso en vez del diálogo)")

    def run_task(self, *a, **k):
        pass

    @property
    def abiertos(self) -> list:
        return [d for d in self.dialogos if d.open]


class AlmacenFalso:
    """Como Almacen, pero en memoria (sin SharedPreferences)."""

    def __init__(self):
        self.datos: dict[str, str] = {}

    async def leer(self, clave):
        return self.datos.get(clave)

    async def guardar(self, clave, valor):
        self.datos[clave] = valor

    token = Almacen.token
    CLAVE_TOKEN = Almacen.CLAVE_TOKEN


# ----------------------------------------------------------------------------- recorrer pantallas

def _es_control(x) -> bool:
    return isinstance(x, ft.BaseControl)


def _atributos(control):
    """(nombre, valor) de cada propiedad. Flet real guarda los valores aparte: se leen por sus campos."""
    if dataclasses.is_dataclass(control):
        for campo_ in dataclasses.fields(control):
            yield campo_.name, getattr(control, campo_.name, None)
    else:
        yield from vars(control).items()


def hijos(control) -> list:
    salida = []
    for nombre, valor in _atributos(control):
        if nombre.startswith("_") or nombre in ("parent", "page", "data"):
            continue
        if _es_control(valor):
            salida.append(valor)
        elif isinstance(valor, (list, tuple)):
            salida.extend(v for v in valor if _es_control(v))
    return salida


def recorrer(raiz):
    """Todos los controles visibles bajo raiz (primero el de arriba)."""
    vistos = set()
    pila = [raiz]
    while pila:
        x = pila.pop()
        if id(x) in vistos or getattr(x, "visible", True) is False:
            continue
        vistos.add(id(x))
        yield x
        pila.extend(reversed(hijos(x)))


def texto_propio(x) -> str:
    for nombre in ("value", "content", "label", "text", "title", "tooltip"):
        v = getattr(x, nombre, None)
        if isinstance(v, str):
            return v
    return ""


def textos(raiz) -> list[str]:
    return [t for x in recorrer(raiz) if (t := texto_propio(x))]


def pantalla_visible(pagina: PaginaFalsa):
    """Si hay un diálogo abierto, solo se puede tocar ese (como en el celular)."""
    abiertos = pagina.abiertos
    return abiertos[-1] if abiertos else pagina.views[-1]


def hay(pagina, trozo: str) -> bool:
    return any(trozo in t for t in textos(pantalla_visible(pagina)))


def hay_exacto(pagina, texto: str) -> bool:
    return texto in textos(pantalla_visible(pagina))


try:  # Flet 1.x revisa cada control antes de dibujarlo (tipos, rangos, combinaciones)
    from flet.utils.validation import validate as _validar_flet
except Exception:
    _validar_flet = None

REVISADOS = 0


def revisar_controles(pagina) -> None:
    """Con Flet real: las mismas validaciones que Flet hace antes de dibujar la pantalla."""
    global REVISADOS
    for raiz in [*pagina.views, *pagina.abiertos]:
        for x in recorrer(raiz):
            if type(x).__name__ == "Row" and getattr(x, "scroll", None) is not None:
                assert str(x.scroll).endswith("HIDDEN") or x.scroll == "hidden", (
                    "una fila que se desliza de lado no debe mostrar barra (tapa los textos)"
                )
    if not FLET_REAL:
        return
    for raiz in [*pagina.views, *pagina.abiertos]:
        for x in recorrer(raiz):
            try:
                x.before_update()
            except (AssertionError, ValueError):
                raise
            except Exception:  # algunas piden estar dentro de una página real
                pass
            if _validar_flet is not None:
                _validar_flet(x)
            REVISADOS += 1


async def _disparar(manejador, control):
    assert manejador is not None, f"{type(control).__name__} no tiene acción"
    evento = SimpleNamespace(control=control, data=None, name="click")
    resultado = manejador(evento)
    if inspect.isawaitable(resultado):
        await resultado


def _candidatos(pagina, trozo: str, atributo: str = "on_click"):
    raiz = pantalla_visible(pagina)
    con_accion = [x for x in recorrer(raiz) if getattr(x, atributo, None) is not None]
    coinciden = []
    for x in con_accion:
        propio = texto_propio(x)
        if trozo == propio or any(trozo == t for t in textos(x)):
            coinciden.append(x)
    # el más «de adentro»: si una tarjeta tocable contiene al botón, se toca el botón
    return [x for x in coinciden if not any(o is not x and o in list(recorrer(x)) for o in coinciden)]


async def tocar(pagina, trozo: str, cual: int = 0):
    lista = _candidatos(pagina, trozo)
    assert lista, f"no encontré «{trozo}» para tocar. En pantalla: {textos(pantalla_visible(pagina))[:40]}"
    await _disparar(lista[cual].on_click, lista[cual])
    revisar_controles(pagina)


async def tocar_icono(pagina, tooltip: str, cual: int = 0):
    lista = [x for x in recorrer(pantalla_visible(pagina)) if getattr(x, "tooltip", None) == tooltip
             and getattr(x, "on_click", None) is not None]
    assert lista, f"no encontré el ícono «{tooltip}»"
    await _disparar(lista[cual].on_click, lista[cual])
    revisar_controles(pagina)


def campo(pagina, etiqueta: str):
    lista = [x for x in recorrer(pantalla_visible(pagina))
             if type(x).__name__ == "TextField" and getattr(x, "label", None) == etiqueta]
    assert lista, f"no encontré el campo «{etiqueta}»"
    return lista[0]


async def escribir(pagina, etiqueta: str, valor: str, enviar: bool = False):
    x = campo(pagina, etiqueta)
    x.value = valor
    for nombre in ("on_change", "on_blur") + (("on_submit",) if enviar else ()):
        if getattr(x, nombre, None) is not None:
            await _disparar(getattr(x, nombre), x)


async def deslizar_para_actualizar(pagina):
    """Como tirar la pantalla hacia abajo desde arriba."""
    indicadores = [x for x in recorrer(pagina.views[-1]) if type(x).__name__ == "RefreshIndicator"]
    assert indicadores, "esta pantalla no se actualiza deslizando"
    await _disparar(indicadores[0].on_refresh, indicadores[0])
    revisar_controles(pagina)


def ultimo_aviso(pagina) -> str:
    return pagina.avisos[-1] if pagina.avisos else ""


def nombre_pantalla(app) -> str:
    return type(app.actual).__name__


class CompartidorFalso:
    """Como ft.Share: guarda lo que la app quiso compartir."""

    def __init__(self):
        self.textos: list[tuple[str, str | None]] = []

    async def share_text(self, texto, subject=None, **k):
        self.textos.append((texto, subject))


class EnlacesFalsos:
    """Como ft.UrlLauncher: guarda los enlaces que la app quiso abrir."""

    def __init__(self):
        self.abiertos: list[str] = []

    async def launch_url(self, url, **k):
        self.abiertos.append(url)


class ActualizadorFalso:
    """Como ActualizadorAndroid, sin Android: permiso, descarga por partes e instalador."""

    def __init__(self, permiso=True, falla=False):
        self.permiso = permiso
        self.falla = falla
        self.pedidos_de_permiso = 0
        self.descargas: list[tuple[str, str]] = []
        self.instalados: list[int] = []
        self.cancelados: list[int] = []
        self.pasos = 0

    def puede_instalar(self):
        return self.permiso

    def pedir_permiso(self):
        self.pedidos_de_permiso += 1

    def descargar(self, url, version):
        self.descargas.append((url, version))
        return 42

    def estado(self, descarga):
        from joinin.actualizar import BAJANDO, FALLO, LISTO

        self.pasos += 1
        if self.falla:
            return FALLO, 0, 0
        return (BAJANDO, self.pasos * 20_000_000, 56_000_000) if self.pasos < 3 else (LISTO, 56_000_000, 56_000_000)

    def instalar(self, descarga):
        self.instalados.append(descarga)

    def cancelar(self, descarga):
        self.cancelados.append(descarga)


async def celular(token_inicial: str | None = None):
    pagina, almacen = PaginaFalsa(), AlmacenFalso()
    if token_inicial:
        almacen.datos[Almacen.CLAVE_TOKEN] = token_inicial
    app = AppJoinIn(pagina, almacen, url=BASE, compartidor=CompartidorFalso(), enlaces=EnlacesFalsos())
    await app.iniciar()
    revisar_controles(pagina)
    return app, pagina


async def ingresar(app, pagina, correo: str, nombre: str | None):
    await escribir(pagina, "Correo institucional", correo)
    await tocar(pagina, "Enviarme el código")
    codigo = app.actual.codigo_prueba
    assert codigo and len(codigo) == 6
    assert hay(pagina, f"tu código es {codigo}")
    await escribir(pagina, "Código", codigo)
    await tocar(pagina, "Entrar")
    if nombre is not None:
        assert hay(pagina, "¿Cómo te llamas?")
        await escribir(pagina, "Tu nombre", nombre)
        await tocar(pagina, "Listo")
    assert nombre_pantalla(app) == "PantallaTablero", nombre_pantalla(app)


# ----------------------------------------------------------------------------- la prueba

async def prueba():
    # 0) El token del celular se crea una vez y se guarda
    almacen = AlmacenFalso()
    t1 = await almacen.token()
    assert len(t1) == 32 and t1 == await almacen.token()
    print("OK: token del celular (32 hex, se guarda)")

    # 1) Sin servidor: pantalla de «Sin conexión» con Reintentar
    pagina_off = PaginaFalsa()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        cerrado = s.getsockname()[1]
    off = AppJoinIn(pagina_off, AlmacenFalso(), url=f"http://127.0.0.1:{cerrado}")
    await off.iniciar()
    assert nombre_pantalla(off) == "PantallaConectando" and hay(pagina_off, "Sin conexión")
    off.api.url = BASE  # vuelve el internet
    await tocar(pagina_off, "Reintentar")
    assert nombre_pantalla(off) == "PantallaIngreso"
    print("OK: sin conexión → Reintentar → ingreso")

    # 2) Ingreso de Ana: dominio, código malo, nombre la primera vez
    ana, pa = await celular()
    assert nombre_pantalla(ana) == "PantallaIngreso"
    await escribir(pa, "Correo institucional", "ana@gmail.com")
    await tocar(pa, "Enviarme el código")
    assert "alumnos.ulagos.cl" in ultimo_aviso(pa) and nombre_pantalla(ana) == "PantallaIngreso"
    await escribir(pa, "Correo institucional", "Ana.Rojas@alumnos.ulagos.cl")
    await tocar(pa, "Enviarme el código")
    codigo = ana.actual.codigo_prueba
    await escribir(pa, "Código", "000000" if codigo != "000000" else "111111")
    await tocar(pa, "Entrar")
    assert "no es correcto" in ultimo_aviso(pa)
    await tocar(pa, "Cambiar correo")
    assert hay(pa, "Ingresa con tu correo")
    await ingresar(ana, pa, "ana.rojas@alumnos.ulagos.cl", "Ana Rojas")
    assert ultimo_aviso(pa) == "¡Hola, Ana Rojas!" and hay(pa, "Hola, Ana")
    assert hay(pa, "No hay avisos abiertos")
    print("OK: ingreso con código (errores claros) y tablero vacío")

    # 3) Crear un aviso desde la app
    await tocar(pa, "Crear aviso")
    assert nombre_pantalla(ana) == "PantallaCrear"
    crear = ana.actual
    await tocar(pa, "Básquetbol")
    assert crear.categoria == "basquetbol"
    for _ in range(4):
        await tocar_icono(pa, "Uno más", 1)  # «Necesitamos en total»: 2 → 6
    await tocar_icono(pa, "Uno más", 0)  # «Ya somos»: 1 → 2
    assert (crear.actuales.valor, crear.necesarias.valor) == (2, 6) and hay(pa, "Faltan 4 personas")
    for _ in range(3):
        await tocar_icono(pa, "Uno más", 0)  # «Ya somos» 5: «necesitamos» sigue en 6
    await tocar_icono(pa, "Uno más", 0)  # 6 = 6: sube «necesitamos» a 7
    assert (crear.actuales.valor, crear.necesarias.valor) == (6, 7) and hay(pa, "Falta 1 persona")
    for _ in range(4):
        await tocar_icono(pa, "Uno menos", 0)
    assert (crear.actuales.valor, crear.necesarias.valor) == (2, 7)

    # un título con una palabra inapropiada se marca al salir del campo y el servidor no lo publica
    mala = next(p for p in filtro.filtro_palabras.palabras_base() if filtro.filtro_palabras.encontradas(f"hola {p}"))
    await escribir(pa, "Título", f"Partido {mala}")
    assert hay(pa, "El título tiene palabras inapropiadas")
    await tocar(pa, "Publicar aviso")  # el servidor lo rechaza y lo anota en «Bloqueados»
    assert "inapropiadas" in ultimo_aviso(pa) and nombre_pantalla(ana) == "PantallaCrear"
    await escribir(pa, "Título", "Basquetbol 3 vs 3")
    assert not hay(pa, "El título tiene palabras inapropiadas")

    # lugar desde el buscador
    await tocar(pa, "Buscar el lugar en el mapa")
    assert pa.abiertos and hay(pa, "Buscar en el mapa")
    await escribir(pa, "Buscar lugar", "ca")
    await tocar_icono(pa, "Buscar")
    assert hay(pa, "Escribe al menos 3 letras.")
    await escribir(pa, "Buscar lugar", "cancha")
    await tocar_icono(pa, "Buscar")
    await tocar(pa, "Cancha ULagos")
    assert not pa.abiertos
    assert campo(pa, "Lugar").value == "Cancha ULagos, Av. Fuchslocher, Osorno"
    assert (crear.lat, crear.lng) == (-40.58, -73.09) and hay(pa, "Ubicación marcada en el mapa")

    # fecha y hora con los selectores
    manana = formato.ahora().date() + timedelta(days=1)
    await _disparar(crear.boton_dia.on_click, crear.boton_dia)
    selector = pa.abiertos[-1]
    assert type(selector).__name__ == "DatePicker"
    selector.value = datetime(manana.year, manana.month, manana.day)
    await _disparar(selector.on_change, selector)
    selector.open = False
    await _disparar(crear.boton_hora.on_click, crear.boton_hora)
    selector = pa.abiertos[-1]
    assert type(selector).__name__ == "TimePicker"
    selector.value = datetime.strptime("20:30", "%H:%M").time()
    await _disparar(selector.on_change, selector)
    selector.open = False
    assert crear.boton_dia.content == "Mañana" and crear.boton_hora.content == "20:30"
    inicio = datetime.fromisoformat(crear.inicio_evento())
    assert inicio.date() == manana and (inicio.hour, inicio.minute) == (20, 30)

    # valor, detalles y duración
    await tocar(pa, "Tiene costo")
    await escribir(pa, "Valor por persona", "2.000")
    assert hay(pa, "Se mostrará como: $2.000 por persona")
    await escribir(pa, "Detalles (opcional)", "Traer polera oscura.")
    await tocar(pa, "48 horas")

    # si el servidor rechaza algo, se queda en el formulario con el mensaje
    await escribir(pa, "Título", "x")
    await tocar(pa, "Publicar aviso")
    assert "Título" in ultimo_aviso(pa) and nombre_pantalla(ana) == "PantallaCrear" and not pa.abiertos
    await escribir(pa, "Título", "Basquetbol 3 vs 3")
    await tocar(pa, "Publicar aviso")
    assert hay(pa, "¡Aviso publicado!") and hay(pa, "48 horas")
    await tocar(pa, "Compartir")
    texto, asunto = ana.compartidor.textos[-1]
    assert asunto == "Basquetbol 3 vs 3" and "«Basquetbol 3 vs 3»" in texto and "Faltan 5 personas" in texto
    assert "$2.000 por persona" in texto and "releases/latest/download/join-in.apk" in texto and pa.abiertos
    await tocar(pa, "Ver mi aviso")
    assert nombre_pantalla(ana) == "PantallaAviso" and len(pa.views) == 2 and not pa.abiertos
    assert hay(pa, "Este aviso es tuyo") and hay(pa, "Basquetbol 3 vs 3") and hay(pa, "$2.000 por persona")
    assert hay(pa, "Faltan 5 personas") and hay(pa, "Eliminar aviso") and not hay(pa, "Unirme")
    aviso_id = ana.actual.aviso_id
    assert any(x.url and "destination=-40.58%2C-73.09" in x.url
               for x in recorrer(pa.views[-1]) if getattr(x, "url", None))
    await ana.volver()
    assert nombre_pantalla(ana) == "PantallaTablero" and hay(pa, "Basquetbol 3 vs 3") and hay(pa, "Tu aviso")
    print("OK: crear aviso (categoría, cupos, filtro, lugar, fecha, valor, 48 h) y verlo")

    # 4) Beto lo ve, se une, comenta y denuncia
    beto, pb = await celular()
    await ingresar(beto, pb, "beto@alumnos.ulagos.cl", "Beto Soto")
    assert hay(pb, "Basquetbol 3 vs 3") and hay(pb, "Faltan 5 personas")
    await tocar(pb, "Fútbol")
    assert hay(pb, "No hay avisos de Fútbol")
    await tocar(pb, "Todos (1)")
    await tocar(pb, "Basquetbol 3 vs 3")
    assert nombre_pantalla(beto) == "PantallaAviso" and hay(pb, "Unirme")
    await tocar(pb, "Invitar")
    assert beto.compartidor.textos[-1][0].startswith("¡Nos falta gente! Básquetbol: «Basquetbol 3 vs 3»")
    await tocar_icono(pb, "Compartir")
    assert len(beto.compartidor.textos) == 2
    await tocar(pb, "Unirme")
    assert ultimo_aviso(pb).startswith("¡Listo! Te uniste") and hay(pb, "Ya estás dentro")
    assert hay(pb, "Faltan 4 personas") and hay(pb, "Se unió Beto Soto")

    await escribir(pb, "Escribe un comentario", "   ")
    await tocar_icono(pb, "Enviar")
    assert ultimo_aviso(pb) == "Escribe un comentario."
    await escribir(pb, "Escribe un comentario", "¿Llevo pelota?")
    await tocar_icono(pb, "Enviar")
    assert hay(pb, "¿Llevo pelota?") and hay(pb, "Comentarios (1)") and campo(pb, "Escribe un comentario").value == ""

    await tocar(pb, "Denunciar este aviso")
    assert hay(pb, "Denunciar aviso")
    await tocar(pb, "Enviar denuncia")
    assert hay(pb, "Elige un motivo.") and pb.abiertos
    grupo = next(x for x in recorrer(pb.abiertos[-1]) if type(x).__name__ == "RadioGroup")
    grupo.value = "spam"
    await escribir(pb, "Cuéntanos más (opcional)", "Es publicidad")
    await tocar(pb, "Enviar denuncia")
    assert not pb.abiertos and ultimo_aviso(pb) == "Gracias. La administración revisará este aviso."

    await beto.volver()
    await tocar_icono(pb, "Mi buzón")
    assert nombre_pantalla(beto) == "PantallaBuzon" and hay(pb, "Me uní (1)") and hay(pb, "Estás anotado")
    await tocar(pb, "Organizo (0)")
    assert hay(pb, "No tienes avisos publicados")
    await tocar(pb, "Me uní (1)")
    await tocar(pb, "Basquetbol 3 vs 3")
    await tocar(pb, "Salirme")
    assert hay(pb, "¿Salirte de este aviso?")
    await tocar(pb, "Me quedo")
    assert not pb.abiertos and hay(pb, "Ya estás dentro")
    await tocar(pb, "Salirme")
    await tocar(pb, "Salirme")  # el botón del diálogo
    assert ultimo_aviso(pb) == "Saliste del aviso. Tu cupo quedó libre." and hay(pb, "Unirme")
    await beto.volver()
    assert nombre_pantalla(beto) == "PantallaBuzon" and hay(pb, "Me uní (0)")
    print("OK: unirse, comentar, denunciar, buzón y salirse")

    # 5) Ana desliza el tablero hacia abajo y ve que alguien se unió y salió
    assert ana.actual.filtros.scroll == ft.ScrollMode.HIDDEN  # el error de la barra sobre las categorías
    await deslizar_para_actualizar(pa)
    assert hay(pa, "Faltan 5 personas")
    # Ana ve el comentario, comenta como organizadora y borra su comentario
    await tocar(pa, "Basquetbol 3 vs 3")
    assert hay(pa, "Beto Soto") and hay(pa, "¿Llevo pelota?")
    await escribir(pa, "Escribe un comentario", "Sí, porfa")
    await tocar_icono(pa, "Enviar")
    assert hay(pa, "Quien organiza") and hay(pa, "Sí, porfa")
    borrar = [x for x in recorrer(pa.views[-1]) if getattr(x, "tooltip", None) == "Borrar comentario"]
    assert len(borrar) == 1  # solo el suyo
    await tocar_icono(pa, "Borrar comentario")
    await tocar(pa, "Borrar")
    assert ultimo_aviso(pa) == "Comentario borrado." and not hay(pa, "Sí, porfa")
    # un segundo aviso para probar «Borrar todos» desde la administración
    await ana.volver()
    await tocar(pa, "Crear aviso")
    await escribir(pa, "Título", "Truco en la sala")
    await tocar(pa, "Juegos de mesa")
    await escribir(pa, "Lugar", "Sala de estudio")
    await tocar(pa, "Publicar aviso")
    await tocar(pa, "Volver al tablero")
    assert nombre_pantalla(ana) == "PantallaTablero" and hay(pa, "Todos (2)") and hay(pa, "Truco en la sala")
    print("OK: comentarios de quien organiza y borrar el propio")

    # 6) Administración desde un celular sin ingresar: no hay botón a la vista;
    #    se entra tocando 5 veces seguidas el logo «+1»
    adm, pd = await celular()
    assert not hay(pd, "Administración") and not hay(pd, "administra")
    for _ in range(4):
        await tocar(pd, "+1")
    assert nombre_pantalla(adm) == "PantallaIngreso"  # con 4 toques no pasa nada
    adm.actual.secreto.toques = [t - 10 for t in adm.actual.secreto.toques]  # toques viejos no cuentan
    await tocar(pd, "+1")
    assert nombre_pantalla(adm) == "PantallaIngreso"
    for _ in range(4):
        await tocar(pd, "+1")
    assert nombre_pantalla(adm) == "PantallaAdminEntrada" and hay(pd, "Solo para quien administra Join In")
    await escribir(pd, "Clave de administración", "mala")
    await tocar(pd, "Entrar")
    assert ultimo_aviso(pd) == "Clave incorrecta."
    await escribir(pd, "Clave de administración", CLAVE)
    await tocar(pd, "Entrar")
    assert nombre_pantalla(adm) == "PantallaAdmin" and adm.es_admin and len(pd.views) == 2
    assert hay(pd, "Avisos abiertos ahora") and hay(pd, "1 aviso por revisar")

    await tocar(pd, "Denuncias")
    assert hay(pd, "Basquetbol 3 vs 3") and hay(pd, "• Spam o publicidad (1)") and hay(pd, "“Es publicidad”")
    await tocar(pd, "Descartar denuncias")
    assert hay(pd, "No hay denuncias por revisar")
    await adm.volver()
    assert hay(pd, "Nada por revisar")

    await tocar(pd, "Palabras del filtro")
    await escribir(pd, "Palabra o frase", "zapallo")
    await tocar(pd, "Agregar al filtro")
    assert "contexto" in ultimo_aviso(pd)
    await escribir(pd, "Se filtra si aparece cerca de… (separa con comas)", "eres, tu")
    await tocar(pd, "Agregar al filtro")
    assert ultimo_aviso(pd) == "«zapallo» agregada. Ya se está filtrando." and hay(pd, "Se filtra cerca de: eres, tu")
    await escribir(pd, "Escribe un texto de ejemplo", "eres zapallo")
    await tocar(pd, "Probar")
    assert hay(pd, "Se bloquearía por: «zapallo»")
    await escribir(pd, "Escribe un texto de ejemplo", "sopa de zapallo")
    await tocar(pd, "Probar")
    assert hay(pd, "Pasa el filtro.")
    await tocar_icono(pd, "Quitar regla")
    await tocar(pd, "Quitar")
    assert hay(pd, "Todavía no hay reglas propias.")
    await adm.volver()

    await tocar(pd, "Bloqueados")
    assert hay(pd, "Título") and hay(pd, f"Partido {mala}")
    await tocar(pd, "Borrar registro")
    await tocar(pd, "Borrar")
    assert hay(pd, "No hay bloqueos registrados")
    await adm.volver()

    await tocar(pd, "Todos los avisos")
    assert hay(pd, "Todos (2)") and hay(pd, "Abiertos (2)") and not hay_exacto(pd, "Ver")  # sin ingresar no hay «Ver»
    await tocar(pd, "Eliminar", 1)  # el más antiguo: Basquetbol
    assert hay(pd, "«Basquetbol 3 vs 3» saldrá del tablero")
    await tocar(pd, "Eliminar")
    assert ultimo_aviso(pd) == "Aviso eliminado del tablero." and hay(pd, "Eliminado por la administración")
    assert hay(pd, "Eliminados (1)")
    await tocar(pd, "Eliminados (1)")
    await tocar(pd, "Borrar para siempre")
    await tocar(pd, "Borrar para siempre")  # el botón del diálogo
    assert ultimo_aviso(pd) == "«Basquetbol 3 vs 3» se borró para siempre." and hay(pd, "Todos (1)")
    await tocar(pd, "Borrar todos los avisos")
    await escribir(pd, "Escribe BORRAR para confirmar", "otra cosa")
    await tocar(pd, "Borrar todos")
    assert ultimo_aviso(pd) == "Escribe BORRAR para confirmar." and hay(pd, "Todos (1)")
    await tocar(pd, "Borrar todos los avisos")
    await escribir(pd, "Escribe BORRAR para confirmar", "borrar")
    await tocar(pd, "Borrar todos")
    assert ultimo_aviso(pd) == "Se borró 1 aviso." and hay(pd, "Todos (0)") and hay(pd, "No hay avisos aquí")
    await adm.volver()

    await tocar(pd, "Correos en uso")
    assert hay(pd, "ana.rojas@alumnos.ulagos.cl") and hay(pd, "beto@alumnos.ulagos.cl")
    await escribir(pd, "Buscar por nombre o correo", "beto")
    assert not hay(pd, "ana.rojas@alumnos.ulagos.cl") and hay(pd, "Beto Soto")
    await escribir(pd, "Buscar por nombre o correo", "nadie")
    assert hay(pd, "Ningún correo coincide con la búsqueda.")
    await escribir(pd, "Buscar por nombre o correo", "beto")
    await tocar_icono(pd, "Liberar correo")
    assert hay(pd, "¿Liberar este correo?")
    await tocar(pd, "No, dejarlo")
    assert hay(pd, "beto@alumnos.ulagos.cl")
    await tocar_icono(pd, "Liberar correo")
    await tocar(pd, "Sí, liberar")
    assert ultimo_aviso(pd) == "beto@alumnos.ulagos.cl quedó libre." and not hay(pd, "beto@alumnos.ulagos.cl")
    print("OK: administración: clave, denuncias, palabras, bloqueados, avisos (eliminar/borrar/todos), correos")

    # 7) A Beto le liberaron el correo: al refrescar vuelve al ingreso con el mensaje
    await beto.actual.refrescar()
    assert nombre_pantalla(beto) == "PantallaIngreso" and ultimo_aviso(pb) == servidor_app.MENSAJE_SIN_SESION
    await ingresar(beto, pb, "beto@alumnos.ulagos.cl", None)  # ya tiene nombre: entra directo
    print("OK: correo liberado → la app vuelve al ingreso y se puede entrar de nuevo")

    # 8) Cerrar la administración en todos los celulares
    await adm.volver()
    await tocar(pd, "Cerrar la administración en todos los celulares")
    await tocar(pd, "Cerrar en todos")
    assert ultimo_aviso(pd).startswith("Se cerró la administración en 1 sesión")
    assert nombre_pantalla(adm) == "PantallaIngreso" and not adm.es_admin
    # otro celular admin pierde el permiso a mitad de camino: vuelve a pedir la clave
    adm2, pd2 = await celular()
    for _ in range(5):
        await tocar(pd2, "+1")
    await escribir(pd2, "Clave de administración", CLAVE)
    await tocar(pd2, "Entrar")
    await tocar(pd2, "Correos en uso")
    datos.administracion.quitar_todos_los_admin()
    await adm2.actual.cargar()
    assert nombre_pantalla(adm2) == "PantallaAdminEntrada" and len(pd2.views) == 2
    assert ultimo_aviso(pd2) == servidor_app.MENSAJE_SIN_ADMIN
    print("OK: salir de la administración en todos, y volver a la clave si se pierde el permiso")

    # 9) Cerrar sesión en el celular y volver a entrar (sin pedir nombre)
    await tocar(pa, "Cerrar sesión")
    assert hay(pa, "¿Cerrar sesión?")
    await tocar(pa, "Cerrar sesión")  # el botón del diálogo
    assert nombre_pantalla(ana) == "PantallaIngreso" and ultimo_aviso(pa) == "Cerraste sesión en este celular."
    await ingresar(ana, pa, "ana.rojas@alumnos.ulagos.cl", None)
    # otro celular no puede usar el correo de Ana
    otro, po = await celular()
    await escribir(po, "Correo institucional", "ana.rojas@alumnos.ulagos.cl")
    await tocar(po, "Enviarme el código")
    if nombre_pantalla(otro) == "PantallaIngreso" and otro.actual.paso == "codigo":
        await escribir(po, "Código", otro.actual.codigo_prueba)
        await tocar(po, "Entrar")
    assert nombre_pantalla(otro) == "PantallaIngreso" and "celular" in ultimo_aviso(po).lower()
    print("OK: cerrar sesión, volver a entrar y un correo por celular")

    # 10) En el tablero, «Administración» no aparece en el menú de un estudiante cualquiera
    assert nombre_pantalla(ana) == "PantallaTablero" and not ana.es_admin
    assert not any(texto_propio(x) == "Administración" for x in recorrer(pa.views[-1]))
    for _ in range(5):
        await tocar(pa, "Join In")  # el título de arriba
    assert nombre_pantalla(ana) == "PantallaAdminEntrada"
    await escribir(pa, "Clave de administración", CLAVE)
    await tocar(pa, "Entrar")
    assert nombre_pantalla(ana) == "PantallaAdmin" and ana.es_admin
    await ana.volver()
    assert hay_exacto(pa, "Administración")  # ya administra: ahora sí está en el menú
    await tocar(pa, "Administración")
    await tocar(pa, "Salir de administración")
    assert nombre_pantalla(ana) == "PantallaTablero" and not ana.es_admin
    assert not any(texto_propio(x) == "Administración" for x in recorrer(pa.views[-1]))
    print("OK: la administración no se ve; se entra con 5 toques y solo quien administra la ve en el menú")

    # 11) Aviso de versión nueva (la app se instala desde GitHub, no desde Play Store)
    from joinin import app as nucleo
    from joinin.cliente import URL_DESCARGA, es_mas_nueva

    assert es_mas_nueva("1.0.10", "1.0.9") and not es_mas_nueva("1.0.9", "1.0.9") and not es_mas_nueva("", "1.0.9")
    assert nombre_pantalla(ana) == "PantallaTablero" and not hay(pa, "Actualización disponible")
    await nucleo.AppJoinIn.revisar_version(ana, lambda: "1.0.99")  # versión «dev»: no pregunta
    assert ana.version_nueva is None
    nucleo.VERSION = "1.0.5"
    try:
        await ana.revisar_version(lambda: "1.0.5")
        assert ana.version_nueva is None and not hay(pa, "Actualización disponible")
        await ana.revisar_version(lambda: (_ for _ in ()).throw(OSError("sin internet")))
        assert ana.version_nueva is None
        await ana.revisar_version(lambda: "1.0.6")
        assert ana.version_nueva == "1.0.6" and hay(pa, "Actualización disponible")
        await deslizar_para_actualizar(pa)  # sigue ahí después de actualizar
        assert hay(pa, "Actualización disponible") and hay(pa, "Join In 1.0.6 ya está lista")

        # Fuera de Android (sin actualizador): «Actualizar» abre el enlace de descarga
        await tocar(pa, "Actualizar")
        assert ana.enlaces.abiertos == [URL_DESCARGA]

        # En Android sin permiso para instalar: lo explica y abre el ajuste
        ana.actualizador = ActualizadorFalso(permiso=False)
        await tocar(pa, "Actualizar")
        assert hay(pa, "Un permiso, solo la primera vez")
        await tocar(pa, "Dar permiso")
        assert ana.actualizador.pedidos_de_permiso == 1 and not pa.abiertos and not ana.actualizador.descargas

        # Con permiso: baja con avance y abre el instalador de Android
        nucleo.SEGUNDOS_ENTRE_REVISIONES = 0
        vistos: list[str] = []
        original = pa.update

        def mirar(*a):
            if pa.abiertos:
                vistos.extend(t for t in textos(pa.abiertos[-1]) if "%" in t)
            return original(*a)

        pa.update = mirar
        ana.actualizador = ActualizadorFalso()
        await tocar(pa, "Actualizar")
        pa.update = original
        assert ana.actualizador.descargas == [(URL_DESCARGA, "1.0.6")] and ana.actualizador.instalados == [42], (ana.actualizador.descargas, ana.actualizador.instalados, ultimo_aviso(pa))
        assert "35 % · 20 de 56 MB" in vistos and not pa.abiertos

        # Si la descarga falla: lo dice, sin abrir el instalador
        ana.actualizador = ActualizadorFalso(falla=True)
        await tocar(pa, "Actualizar")
        assert "No se pudo bajar la actualización" in ultimo_aviso(pa) and not ana.actualizador.instalados
        assert not pa.abiertos

        # «Buscar actualizaciones» en el menú de la cuenta
        ana.actualizador = ActualizadorFalso()
        await ana.revisar_version(lambda: "1.0.5", manual=True)
        assert ultimo_aviso(pa) == "Ya tienes la última versión (1.0.5)."
        await ana.revisar_version(lambda: (_ for _ in ()).throw(OSError("sin internet")), manual=True)
        assert "No pudimos revisar" in ultimo_aviso(pa)
        await ana.revisar_version(lambda: "1.0.7", manual=True)  # hay una nueva: la baja e instala
        assert ana.actualizador.descargas == [(URL_DESCARGA, "1.0.7")] and ana.actualizador.instalados == [42]
        assert hay_exacto(pa, "Buscar actualizaciones")
    finally:
        nucleo.VERSION = "dev"
        nucleo.SEGUNDOS_ENTRE_REVISIONES = 0.5
        ana.actualizador = None
    await ana.revisar_version(manual=True)
    assert ultimo_aviso(pa) == "Esta es una versión de prueba: no se actualiza."
    print("OK: compartir, deslizar para actualizar y «Actualización disponible» (permiso, avance, instalador)")

    # 12) Textos de fechas y estados (los mismos que tenía la página)
    ref = datetime(2026, 11, 26, 10, 0, tzinfo=formato.ZONA_HORARIA)
    assert formato.texto_fecha_evento(ref.replace(hour=20), ref) == "Hoy, 20:00"
    assert formato.texto_fecha_evento(ref + timedelta(days=1), ref) == "Mañana, 10:00"
    assert formato.texto_fecha_evento(ref + timedelta(days=3), ref) == "dom 29 nov, 10:00"
    assert formato.texto_valor(0) == "Gratis" and formato.texto_valor(12500) == "$12.500 por persona"
    assert formato.texto_faltan(1) == "Falta 1 persona" and formato.texto_faltan(0) == "Grupo completo"
    assert formato.unir_nombres(["A", "B", "C", "D", "E"]) == "A, B, C y 2 más"
    assert formato.iniciales("ana rojas") == "AR" and formato.iniciales("") == "?"
    print("OK: textos de fechas, valores y cupos")

    if FLET_REAL:
        assert _validar_flet is not None and REVISADOS > 1000, REVISADOS
    print(f"OK: todo bien ({f'Flet real {ft.__version__}, {REVISADOS} controles validados' if FLET_REAL else 'Flet falso'})")


asyncio.run(prueba())
