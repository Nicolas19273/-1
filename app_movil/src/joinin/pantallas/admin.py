"""
Administración: entrar con la clave, ver cifras y moderar (denuncias, palabras
del filtro, bloqueos, todos los avisos y correos en uso).

La clave vive solo en el servidor (variable CLAVE_ADMIN de Render). Este
celular queda como administrador hasta que salga.
"""

from __future__ import annotations

from collections import Counter
from functools import partial

import flet as ft

from .. import componentes as c
from .. import formato as f
from ..app import Pantalla
from ..estilo import BLANCO, COLOR_PRINCIPAL, GRIS, GRIS_SUAVE, ROJO, ROJO_SUAVE, TINTA
from .tablero import chip_filtro


async def abrir_administracion(app) -> None:
    """Entra directo al panel si este celular ya administra; si no, pide la clave."""
    await app.ir(PantallaAdminEntrada(app))


class PantallaAdminBase(Pantalla):
    """Algo que comparten todas las pantallas del panel."""

    es_de_admin = True

    async def pedir(self, funcion, *args, avisar: bool = True):
        r = await self.app.llamar(funcion, *args, avisar=avisar)
        error = self.app.ultimo_error
        if r is None and error is not None and error.estado == 403:
            await sesion_admin_perdida(self.app)
        return r


async def sesion_admin_perdida(app) -> None:
    """La administración se cerró (por ejemplo, «salir en todos»): se vuelve a pedir la clave."""
    app.es_admin = False
    while len(app.pantallas) > 1 and getattr(app.actual, "es_de_admin", False):
        app.page.views.pop()
        app.pantallas.pop()
    await app.ir(PantallaAdminEntrada(app))


# --------------------------------------------------------------------------- #
# Entrada con clave
# --------------------------------------------------------------------------- #


class PantallaAdminEntrada(Pantalla):
    ruta = "/admin/entrar"

    def vista(self) -> ft.View:
        self.campo_clave = ft.TextField(
            label="Clave de administración",
            password=True,
            can_reveal_password=True,
            autofocus=True,
            on_submit=self.entrar,
        )
        self.cuerpo = ft.Column(
            [c.cargando("Revisando…")],
            spacing=14,
        )
        return self.vista_base("Administración", [self.cuerpo])

    async def cargar(self) -> None:
        estado = await self.app.llamar(self.api.admin_estado)
        if estado is None:
            self.cuerpo.controls = [c.vacio(ft.Icons.WIFI_OFF, "Sin conexión", "Vuelve atrás e intenta de nuevo.")]
            return
        if estado.get("es_admin"):
            self.app.es_admin = True
            await self.app.cambiar(PantallaAdmin(self.app))
            return
        controles: list[ft.Control] = [
            ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS, size=56, color=COLOR_PRINCIPAL),
            c.titulo("Solo para quien administra Join In", 20),
            c.suave("Con la clave puedes revisar denuncias, ajustar el filtro de palabras, ver todos los avisos "
                    "y liberar correos. Este celular quedará como administrador hasta que salgas."),
        ]
        if not estado.get("hay_clave"):
            controles.append(c.nota("La administración está desactivada",
                                    "Falta configurar la clave en el servidor (CLAVE_ADMIN en Render).",
                                    color=ROJO, fondo=ROJO_SUAVE))
        else:
            controles += [self.campo_clave, ft.Row([c.boton_oscuro("Entrar", self.entrar, ft.Icons.LOCK_OPEN)])]
        self.cuerpo.controls = controles

    async def refrescar(self) -> None:
        pass

    async def entrar(self, e=None) -> None:
        clave = self.campo_clave.value or ""
        if not clave:
            self.app.avisar("Escribe la clave.", error=True)
            return
        if await self.app.llamar(self.api.admin_entrar, clave) is not None:
            self.app.es_admin = True
            self.campo_clave.value = ""
            self.app.avisar("Entraste a la administración.")
            await self.app.cambiar(PantallaAdmin(self.app))


# --------------------------------------------------------------------------- #
# Panel: cifras y secciones
# --------------------------------------------------------------------------- #


def cifra(valor: int, etiqueta: str, icono) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icono, size=22, color=COLOR_PRINCIPAL),
                ft.Text(str(valor), size=26, weight=ft.FontWeight.W_900, color=TINTA),
                ft.Text(etiqueta, size=12, color=GRIS),
            ],
            spacing=2,
            tight=True,
        ),
        width=156,
        bgcolor=BLANCO,
        border=ft.Border.all(1, GRIS_SUAVE),
        border_radius=ft.BorderRadius.all(16),
        padding=ft.Padding.all(12),
    )


class PantallaAdmin(PantallaAdminBase):
    ruta = "/admin"
    se_refresca_sola = True

    def vista(self) -> ft.View:
        self.cifras = ft.Row([c.cargando("Cargando cifras…")], wrap=True, spacing=8, run_spacing=8)
        self.totales = c.suave("")
        self.secciones = ft.Column(spacing=8)
        self._pintar_secciones({})
        return self.vista_base(
            "Administración",
            [
                self.cifras,
                self.totales,
                c.titulo("Moderar", 18),
                self.secciones,
                ft.Divider(color=GRIS_SUAVE),
                c.titulo("Tu sesión de administración", 18),
                c.suave("Sal cuando termines, sobre todo si el celular no es tuyo."),
                ft.Row([c.boton_oscuro("Salir de administración", self.salir, ft.Icons.LOGOUT)]),
                ft.Row([c.boton_peligro("Cerrar la administración en todos los celulares", self.preguntar_salir_todos,
                                        ft.Icons.PHONELINK_LOCK)]),
            ],
            al_refrescar=self.actualizar,
        )

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_resumen, avisar=False)
        if r is None:
            return
        x = r["cifras"]
        self.cifras.controls = [
            cifra(x["abiertos"], "Avisos abiertos ahora", ft.Icons.CAMPAIGN),
            cifra(x["publicados_7d"], "Publicados (7 días)", ft.Icons.ADD_CIRCLE_OUTLINE),
            cifra(x["unidos_7d"], "Personas unidas (7 días)", ft.Icons.GROUP_ADD),
            cifra(x["bloqueos_7d"], "Bloqueos del filtro (7 días)", ft.Icons.BLOCK),
            cifra(x["cancelados_7d"], "Avisos eliminados (7 días)", ft.Icons.DELETE_OUTLINE),
            cifra(x["denuncias_pendientes"], "Avisos con denuncias", ft.Icons.OUTLINED_FLAG),
        ]
        self.totales.value = (f"Avisos publicados desde el comienzo: {x['avisos_total']} · "
                              f"Estudiantes registrados: {x['estudiantes']}")
        self._pintar_secciones(x)

    async def actualizar(self, e=None) -> None:
        await self.cargar()
        self.app.avisar("Panel actualizado.")

    def _pintar_secciones(self, x: dict) -> None:
        def fila(icono, titulo: str, detalle: str, pantalla, alerta: bool = False) -> ft.Control:
            return c.tarjeta(
                [
                    ft.Row(
                        [
                            ft.Icon(icono, color=ROJO if alerta else COLOR_PRINCIPAL),
                            ft.Column([c.texto(titulo, 15, ft.FontWeight.W_800), c.suave(detalle)],
                                      spacing=0, expand=True, tight=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=GRIS),
                        ],
                        spacing=12,
                    )
                ],
                al_tocar=partial(self.abrir, pantalla),
                color=ROJO_SUAVE if alerta else BLANCO,
            )

        pendientes = x.get("denuncias_pendientes", 0)
        self.secciones.controls = [
            fila(ft.Icons.OUTLINED_FLAG, "Denuncias",
                 f"{pendientes} aviso{'s' if pendientes != 1 else ''} por revisar" if pendientes else "Nada por revisar",
                 PantallaAdminDenuncias, alerta=bool(pendientes)),
            fila(ft.Icons.SPELLCHECK, "Palabras del filtro", f"{x.get('reglas', 0)} reglas propias · probar el filtro",
                 PantallaAdminPalabras),
            fila(ft.Icons.BLOCK, "Bloqueados", "Lo que el filtro no dejó publicar", PantallaAdminBloqueados),
            fila(ft.Icons.CAMPAIGN, "Todos los avisos", "Ver, eliminar o borrar para siempre", PantallaAdminAvisos),
            fila(ft.Icons.ALTERNATE_EMAIL, "Correos en uso", "Liberar un correo para que ingrese de nuevo",
                 PantallaAdminCorreos),
        ]

    async def abrir(self, clase, e=None) -> None:
        await self.app.ir(clase(self.app))

    async def salir(self, e=None) -> None:
        if await self.pedir(self.api.admin_salir) is not None:
            self.app.es_admin = False
            self.app.avisar("Saliste de la administración.")
            await self.app.volver()

    def preguntar_salir_todos(self, e=None) -> None:
        self.app.preguntar(
            "¿Cerrar en todos los celulares?",
            "Todos los celulares y navegadores que administran, incluido este, tendrán que volver a escribir la clave.",
            "Cerrar en todos",
            self.salir_todos,
        )

    async def salir_todos(self) -> None:
        r = await self.pedir(self.api.admin_salir_todos)
        if r is not None:
            self.app.es_admin = False
            n = r.get("cerradas", 0)
            self.app.avisar(f"Se cerró la administración en {n} sesión{'es' if n != 1 else ''}.")
            await self.app.volver()


# --------------------------------------------------------------------------- #
# Denuncias
# --------------------------------------------------------------------------- #


class PantallaAdminDenuncias(PantallaAdminBase):
    ruta = "/admin/denuncias"

    def vista(self) -> ft.View:
        self.lista = ft.Column([c.cargando()], spacing=12)
        return self.vista_base("Denuncias", [c.suave("Avisos denunciados, del más denunciado al menos."), self.lista],
                               al_refrescar=self.actualizar)

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_denuncias)
        if r is None:
            return
        momento = f.ahora()
        if not r["denuncias"]:
            self.lista.controls = [c.vacio(ft.Icons.VERIFIED, "No hay denuncias por revisar", "Todo en orden.")]
            return
        tarjetas = []
        for grupo in r["denuncias"]:
            aviso, denuncias = grupo["aviso"], grupo["denuncias"]
            filas: list[ft.Control] = [
                ft.Row([c.chip_categoria(aviso["categoria"], aviso["nombre_categoria"]),
                        c.chip(f"{len(denuncias)} denuncia{'s' if len(denuncias) != 1 else ''}", ft.Icons.FLAG,
                               color=ROJO, fondo=ROJO_SUAVE)], spacing=6, wrap=True),
                c.texto(aviso["titulo"], 17, ft.FontWeight.W_800),
                c.suave(f"{aviso['lugar']} · {f.texto_fecha_evento(f.leer_fecha(aviso['inicio_evento']), momento)}"),
            ]
            if aviso.get("descripcion"):
                filas.append(c.suave(aviso["descripcion"]))
            for motivo, cantidad in Counter(d["nombre_motivo"] for d in denuncias).most_common():
                filas.append(c.texto(f"• {motivo} ({cantidad})", 14))
            for d in denuncias:
                if d.get("comentario"):
                    filas.append(ft.Text(f"“{d['comentario']}”", size=13, italic=True, color=GRIS))
            botones: list[ft.Control] = []
            if not aviso["cancelado"]:
                botones.append(c.boton_peligro("Eliminar aviso", partial(self.preguntar_eliminar, aviso)))
            else:
                botones.append(c.chip("Ya eliminado", ft.Icons.CHECK, color=GRIS))
            botones.append(c.boton_texto("Descartar denuncias", partial(self.descartar, aviso["id"]), ft.Icons.DONE))
            filas.append(ft.Row(botones, wrap=True))
            tarjetas.append(c.tarjeta(filas))
        self.lista.controls = tarjetas

    def preguntar_eliminar(self, aviso: dict, e=None) -> None:
        self.app.preguntar(
            "¿Eliminar este aviso?",
            f"«{aviso['titulo']}» saldrá del tablero y quienes se unieron lo verán como cancelado por la administración.",
            "Eliminar",
            partial(self.eliminar, aviso["id"]),
        )

    async def eliminar(self, aviso_id: int) -> None:
        if await self.pedir(self.api.admin_eliminar_aviso, aviso_id) is not None:
            await self.pedir(self.api.admin_descartar_denuncias, aviso_id, avisar=False)
            self.app.avisar("Aviso eliminado.")
            await self.cargar()

    async def descartar(self, aviso_id: int, e=None) -> None:
        if await self.pedir(self.api.admin_descartar_denuncias, aviso_id) is not None:
            self.app.avisar("Denuncias descartadas.")
            await self.cargar()


# --------------------------------------------------------------------------- #
# Palabras del filtro
# --------------------------------------------------------------------------- #


class PantallaAdminPalabras(PantallaAdminBase):
    ruta = "/admin/palabras"

    def __init__(self, app):
        super().__init__(app)
        self.en_contexto = True

    def vista(self) -> ft.View:
        self.campo_palabra = ft.TextField(label="Palabra o frase", hint_text="Ej: pico", max_length=60)
        self.modo = ft.Row(spacing=8, wrap=True)
        self.campo_cerca = ft.TextField(label="Se filtra si aparece cerca de… (separa con comas)",
                                        hint_text="Ej: chupa, chupen, mi, tu")
        self.campo_excepto = ft.TextField(label="Nunca se filtra en… (opcional, separa con comas)",
                                          hint_text="Ej: y pico, pico de")
        self.campo_prueba = ft.TextField(label="Escribe un texto de ejemplo", multiline=True, min_lines=2,
                                         on_submit=self.probar)
        self.resultado = c.texto("", 14, ft.FontWeight.W_700)
        self.lista = ft.Column([c.cargando()], spacing=8)
        self.base = c.suave("")
        self._pintar_modo()
        return self.vista_base(
            "Palabras del filtro",
            [
                c.tarjeta(
                    [
                        c.titulo("Agregar al filtro", 18),
                        c.suave("Se aplica al instante en toda la app, sin volver a publicar el código."),
                        self.campo_palabra,
                        self.modo,
                        self.campo_cerca,
                        self.campo_excepto,
                        c.suave("«Cerca» significa hasta unas pocas palabras antes o después. Las excepciones siempre "
                                "ganan. Mayúsculas, tildes y trucos como p1c0 se detectan igual."),
                        ft.Row([c.boton_oscuro("Agregar al filtro", self.agregar, ft.Icons.ADD)]),
                    ],
                    espacio=10,
                ),
                c.tarjeta(
                    [c.titulo("Probar el filtro", 18), self.campo_prueba,
                     ft.Row([c.boton_texto("Probar", self.probar, ft.Icons.PLAY_ARROW)]), self.resultado],
                    espacio=10,
                ),
                c.titulo("Reglas propias", 18),
                self.lista,
                self.base,
            ],
        )

    def _pintar_modo(self) -> None:
        self.modo.controls = [
            chip_filtro("Solo en contexto inadecuado", self.en_contexto, partial(self.elegir_modo, True),
                        color=COLOR_PRINCIPAL),
            chip_filtro("Siempre", not self.en_contexto, partial(self.elegir_modo, False), color=COLOR_PRINCIPAL),
        ]
        self.campo_cerca.visible = self.en_contexto

    def elegir_modo(self, en_contexto: bool, e=None) -> None:
        self.en_contexto = en_contexto
        self._pintar_modo()
        self.app.page.update()

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_reglas)
        if r is None:
            return
        self.campo_palabra.max_length = r.get("largo_max_regla", 60)
        self.base.value = (f"Además, el filtro trae {r['palabras_base']} palabras base. "
                           "Para cambiarlas hay que editar filtro.py.")
        if not r["reglas"]:
            self.lista.controls = [c.suave("Todavía no hay reglas propias.")]
            return
        filas = []
        for regla in r["reglas"]:
            detalle = [c.texto(regla["palabra"], 16, ft.FontWeight.W_800)]
            if regla["siempre"] or not regla["cerca_de"]:
                detalle.append(c.suave("Se filtra siempre"))
            else:
                detalle.append(c.suave("Se filtra cerca de: " + ", ".join(regla["cerca_de"])))
            if regla["excepto"]:
                detalle.append(c.suave("Nunca en: " + ", ".join(regla["excepto"])))
            filas.append(
                c.tarjeta([
                    ft.Row(
                        [ft.Column(detalle, spacing=2, expand=True, tight=True),
                         ft.IconButton(ft.Icons.CLOSE, tooltip="Quitar regla",
                                       on_click=partial(self.preguntar_borrar, regla))],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    )
                ])
            )
        self.lista.controls = filas

    async def agregar(self, e=None) -> None:
        cerca = (self.campo_cerca.value or "") if self.en_contexto else ""
        if self.en_contexto and not [p for p in cerca.split(",") if p.strip()]:
            self.app.avisar("Escribe al menos una palabra de contexto, o elige «Siempre».", error=True)
            return
        r = await self.pedir(self.api.admin_agregar_regla, self.campo_palabra.value or "", cerca,
                             self.campo_excepto.value or "")
        if r is not None:
            self.app.avisar(f"«{r['regla']['palabra']}» agregada. Ya se está filtrando.")
            self.campo_palabra.value = self.campo_cerca.value = self.campo_excepto.value = ""
            await self.cargar()

    async def probar(self, e=None) -> None:
        texto = (self.campo_prueba.value or "").strip()
        if not texto:
            self.resultado.value = ""
            return
        palabras = await self.pedir(self.api.admin_probar_filtro, texto)
        if palabras is None:
            return
        if palabras:
            self.resultado.value = "Se bloquearía por: " + ", ".join(f"«{p}»" for p in palabras)
            self.resultado.color = ROJO
        else:
            self.resultado.value = "Pasa el filtro."
            self.resultado.color = COLOR_PRINCIPAL

    def preguntar_borrar(self, regla: dict, e=None) -> None:
        self.app.preguntar("¿Quitar esta regla?", f"«{regla['palabra']}» dejará de filtrarse.", "Quitar",
                           partial(self.borrar, regla["id"]))

    async def borrar(self, regla_id: int) -> None:
        if await self.pedir(self.api.admin_borrar_regla, regla_id) is not None:
            self.app.avisar("Regla quitada.")
            await self.cargar()


# --------------------------------------------------------------------------- #
# Bloqueados
# --------------------------------------------------------------------------- #


class PantallaAdminBloqueados(PantallaAdminBase):
    ruta = "/admin/bloqueados"

    def vista(self) -> ft.View:
        self.explicacion = c.suave("Lo que el filtro no dejó publicar.")
        self.lista = ft.Column([c.cargando()], spacing=10)
        return self.vista_base(
            "Bloqueados",
            [self.explicacion, ft.Row([c.boton_peligro("Borrar registro", self.preguntar_borrar,
                                                       ft.Icons.DELETE_SWEEP)]), self.lista],
            al_refrescar=self.actualizar,
        )

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_bloqueados)
        if r is None:
            return
        momento = f.ahora()
        self.explicacion.value = f"Lo que el filtro no dejó publicar (se guarda {r['dias']} días)."
        if not r["bloqueados"]:
            self.lista.controls = [c.vacio(ft.Icons.BLOCK, "No hay bloqueos registrados", "")]
            return
        self.lista.controls = [
            c.tarjeta([
                ft.Row([c.chip(b["campo"], ft.Icons.BLOCK, color=ROJO, fondo=ROJO_SUAVE),
                        c.suave(f.texto_fecha_evento(f.leer_fecha(b["momento"]), momento), 12)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                c.texto(b["texto"], 14, selectable=True),
                ft.Text("Detectó: " + ", ".join(f"«{p}»" for p in b["palabras"]), size=12,
                        weight=ft.FontWeight.W_700, color=ROJO),
            ])
            for b in r["bloqueados"]
        ]

    def preguntar_borrar(self, e=None) -> None:
        self.app.preguntar("¿Borrar el registro?", "Se borran todos los bloqueos guardados.", "Borrar", self.borrar)

    async def borrar(self) -> None:
        if await self.pedir(self.api.admin_borrar_bloqueados) is not None:
            self.app.avisar("Registro borrado.")
            await self.cargar()


# --------------------------------------------------------------------------- #
# Todos los avisos
# --------------------------------------------------------------------------- #

TODOS, ABIERTOS, ELIMINADOS, TERMINADOS = "todos", "abiertos", "eliminados", "terminados"


def grupo_de(aviso: dict) -> str:
    if aviso.get("cancelado"):
        return ELIMINADOS
    return ABIERTOS if aviso.get("abierto") else TERMINADOS


class PantallaAdminAvisos(PantallaAdminBase):
    ruta = "/admin/avisos"

    def __init__(self, app):
        super().__init__(app)
        self.avisos: list[dict] = []
        self.grupo = TODOS
        self.momento = f.ahora()

    def vista(self) -> ft.View:
        self.filtros = ft.Row(scroll=ft.ScrollMode.HIDDEN, spacing=8)
        self.lista = ft.Column([c.cargando()], spacing=10)
        self._pintar_filtros()
        return self.vista_base(
            "Todos los avisos",
            [
                c.suave("Del más nuevo al más antiguo: abiertos, eliminados y terminados. «Eliminar» saca un aviso "
                        "del tablero y avisa a quienes se unieron; «Borrar para siempre» lo quita de la base de "
                        "datos, sin dejar rastro."),
                c.caja_peligro([
                    c.texto("Borrar todos los avisos", 15, ft.FontWeight.W_800, color=ROJO),
                    c.suave("Borra para siempre todos los avisos, con sus inscritos, comentarios y denuncias. "
                            "No se puede deshacer."),
                    ft.Row([c.boton_peligro("Borrar todos los avisos", self.preguntar_borrar_todos,
                                            ft.Icons.DELETE_FOREVER)]),
                ]),
                self.filtros,
                self.lista,
            ],
            al_refrescar=self.actualizar,
        )

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_avisos)
        if r is None:
            return
        self.avisos = r["avisos"]
        self.momento = f.leer_fecha(r["ahora"]) or f.ahora()
        self._pintar_filtros()
        self._pintar_lista()

    def _pintar_filtros(self) -> None:
        cuenta = Counter(grupo_de(a) for a in self.avisos)
        opciones = [(TODOS, f"Todos ({len(self.avisos)})"), (ABIERTOS, f"Abiertos ({cuenta[ABIERTOS]})"),
                    (ELIMINADOS, f"Eliminados ({cuenta[ELIMINADOS]})"), (TERMINADOS, f"Terminados ({cuenta[TERMINADOS]})")]
        self.filtros.controls = [
            chip_filtro(texto, self.grupo == clave, partial(self.filtrar, clave), color=COLOR_PRINCIPAL)
            for clave, texto in opciones
        ]

    def filtrar(self, grupo: str, e=None) -> None:
        self.grupo = grupo
        self._pintar_filtros()
        self._pintar_lista()
        self.app.page.update()

    def _pintar_lista(self) -> None:
        visibles = [a for a in self.avisos if self.grupo in (TODOS, grupo_de(a))]
        if not visibles:
            self.lista.controls = [c.vacio(ft.Icons.CAMPAIGN, "No hay avisos aquí", "")]
            return
        self.lista.controls = [self._tarjeta(a) for a in visibles]

    def _tarjeta(self, a: dict) -> ft.Control:
        grupo = grupo_de(a)
        if grupo == ELIMINADOS:
            marca = c.chip("Eliminado por la administración" if a.get("cancelado_por") == "admin"
                           else "Eliminado por quien lo publicó", ft.Icons.DELETE_OUTLINE, color=ROJO, fondo=ROJO_SUAVE)
        elif grupo == ABIERTOS:
            marca = c.chip("Abierto", ft.Icons.CAMPAIGN, color=BLANCO, fondo=COLOR_PRINCIPAL)
        else:
            principal = f.CIERRES.get(a.get("estado"), ("Terminado", ""))[0]
            marca = c.chip(principal, ft.Icons.EVENT_AVAILABLE, color=TINTA)
        inicio = f.leer_fecha(a["inicio_evento"])
        botones: list[ft.Control] = []
        if self.app.nombre:  # ver el detalle pide haber ingresado con el correo
            botones.append(c.boton_texto("Ver", partial(self.ver, a["id"]), ft.Icons.VISIBILITY))
        if grupo == ABIERTOS:
            botones.append(c.boton_peligro("Eliminar", partial(self.preguntar_eliminar, a), ft.Icons.REMOVE_CIRCLE_OUTLINE))
        botones.append(c.boton_peligro("Borrar para siempre", partial(self.preguntar_borrar, a), ft.Icons.DELETE_FOREVER))
        return c.tarjeta([
            ft.Row([c.chip_categoria(a["categoria"], a["nombre_categoria"]), marca], spacing=6, wrap=True),
            c.texto(a["titulo"], 16, ft.FontWeight.W_800),
            c.suave(f"Organiza {a['creador']} · {a['lugar']} · {f.texto_fecha_evento(inicio, self.momento)}"),
            c.suave(f"{a['ocupados']} de {a['personas_necesarias']} · {f.texto_comentarios(a.get('comentarios', 0))}"),
            ft.Row(botones, wrap=True, spacing=0),
        ])

    async def ver(self, aviso_id: int, e=None) -> None:
        from .aviso import PantallaAviso

        await self.app.ir(PantallaAviso(self.app, aviso_id))

    def preguntar_eliminar(self, a: dict, e=None) -> None:
        self.app.preguntar("¿Eliminar este aviso?",
                           f"«{a['titulo']}» saldrá del tablero y quienes se unieron lo verán como cancelado.",
                           "Eliminar", partial(self.eliminar, a["id"]))

    async def eliminar(self, aviso_id: int) -> None:
        if await self.pedir(self.api.admin_eliminar_aviso, aviso_id) is not None:
            self.app.avisar("Aviso eliminado del tablero.")
            await self.cargar()

    def preguntar_borrar(self, a: dict, e=None) -> None:
        self.app.preguntar("¿Borrar para siempre?",
                           f"«{a['titulo']}» se borrará de la base de datos con sus inscritos, comentarios y denuncias. "
                           "No se puede deshacer.",
                           "Borrar para siempre", partial(self.borrar, a["id"]))

    async def borrar(self, aviso_id: int) -> None:
        r = await self.pedir(self.api.admin_borrar_aviso, aviso_id)
        if r is not None:
            self.app.avisar(f"«{r['titulo']}» se borró para siempre.")
            await self.cargar()

    def preguntar_borrar_todos(self, e=None) -> None:
        self.confirmacion = ft.TextField(label="Escribe BORRAR para confirmar",
                                         capitalization=ft.TextCapitalization.CHARACTERS)
        self.app.preguntar(
            "¿Borrar todos los avisos?",
            "Se borrarán para siempre todos los avisos (abiertos, eliminados y terminados), con sus inscritos, "
            "comentarios y denuncias.",
            "Borrar todos",
            self.borrar_todos,
            contenido=self.confirmacion,
        )

    async def borrar_todos(self) -> None:
        r = await self.pedir(self.api.admin_borrar_todos, (self.confirmacion.value or "").strip())
        if r is not None:
            n = r["borrados"]
            self.app.avisar("Se borró 1 aviso." if n == 1 else f"Se borraron {n} avisos.")
            await self.cargar()


# --------------------------------------------------------------------------- #
# Correos en uso
# --------------------------------------------------------------------------- #


class PantallaAdminCorreos(PantallaAdminBase):
    ruta = "/admin/correos"

    def __init__(self, app):
        super().__init__(app)
        self.correos: list[dict] = []

    def vista(self) -> ft.View:
        self.busqueda = ft.TextField(label="Buscar por nombre o correo", prefix_icon=ft.Icons.SEARCH,
                                     on_change=self.filtrar)
        self.lista = ft.Column([c.cargando()], spacing=8)
        return self.vista_base(
            "Correos en uso",
            [
                c.suave("Cada correo entra en un solo celular. Si alguien cambió de celular o no puede entrar, "
                        "toca la X para liberar su correo: podrá ingresar de nuevo con un código."),
                self.busqueda,
                self.lista,
            ],
            al_refrescar=self.actualizar,
        )

    async def actualizar(self, e=None) -> None:
        await self.cargar()

    async def cargar(self) -> None:
        r = await self.pedir(self.api.admin_correos)
        if r is None:
            return
        self.correos = r["correos"]
        self._pintar()

    def filtrar(self, e=None) -> None:
        self._pintar()

    def _pintar(self) -> None:
        buscado = (self.busqueda.value or "").strip().lower()
        visibles = [x for x in self.correos
                    if not buscado or buscado in x["correo"].lower() or buscado in (x.get("nombre") or "").lower()]
        if not self.correos:
            self.lista.controls = [c.vacio(ft.Icons.ALTERNATE_EMAIL, "No hay correos en uso", "")]
            return
        if not visibles:
            self.lista.controls = [c.suave("Ningún correo coincide con la búsqueda.")]
            return
        momento = f.ahora()
        filas = []
        for x in visibles:
            usado = f.leer_fecha(x.get("usado"))
            filas.append(
                c.tarjeta([
                    ft.Row(
                        [
                            c.avatar(x.get("nombre") or x["correo"]),
                            ft.Column(
                                [c.texto(x.get("nombre") or "Sin nombre", 15, ft.FontWeight.W_800),
                                 c.texto(x["correo"], 13, selectable=True),
                                 c.suave("Último uso: " + (f.texto_hace(usado, momento) if usado else "—"), 12)],
                                spacing=0, expand=True, tight=True,
                            ),
                            ft.IconButton(ft.Icons.CLOSE, icon_color=ROJO, tooltip="Liberar correo",
                                          on_click=partial(self.preguntar_liberar, x["correo"])),
                        ],
                        spacing=12,
                    )
                ])
            )
        self.lista.controls = filas

    def preguntar_liberar(self, correo: str, e=None) -> None:
        self.app.preguntar(
            "¿Liberar este correo?",
            f"Se cerrará la sesión de {correo} en el celular que lo usa. Podrá ingresar de nuevo, "
            "desde cualquier celular, con un código nuevo.",
            "Sí, liberar",
            partial(self.liberar, correo),
            no="No, dejarlo",
        )

    async def liberar(self, correo: str) -> None:
        r = await self.pedir(self.api.admin_liberar_correo, correo)
        if r is not None:
            self.app.avisar(f"{r['correo']} quedó libre.")
            await self.cargar()
