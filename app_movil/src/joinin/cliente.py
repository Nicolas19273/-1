"""
ClienteAPI: la parte de la app que habla con el servidor de Join In.

Usa solo la biblioteca estándar de Python (urllib), así funciona igual en el
celular. Cada pedido lleva el token del celular («Authorization: Bearer»);
el servidor responde en JSON y, si algo falla, con {"error": "mensaje"}.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

URL_SERVIDOR = os.environ.get("JOIN_IN_SERVIDOR", "https://falta-uno.onrender.com").rstrip("/")

# Render gratis duerme el servidor sin uso: el primer pedido puede tardar ~1 minuto.
SEGUNDOS_ESPERA = 75

SIN_CONEXION = "No pudimos conectarnos con Join In. Revisa tu internet e intenta de nuevo."


class ErrorServidor(Exception):
    """Un error con el mensaje listo para mostrar. estado: código HTTP (0 = sin conexión)."""

    def __init__(self, mensaje: str, estado: int = 0):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


def _contexto_ssl() -> ssl.SSLContext:
    """En Android no siempre hay certificados del sistema: se usan los de certifi."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # sin certifi (por ejemplo, en una prueba local)
        return ssl.create_default_context()


class ClienteAPI:
    def __init__(self, token: str, url: str | None = None, espera: float = SEGUNDOS_ESPERA):
        self.token = token
        self.url = (url or URL_SERVIDOR).rstrip("/")
        self.espera = espera
        self._ssl = _contexto_ssl() if self.url.startswith("https") else None

    # ------------------------------------------------------------------ #

    def _pedir(self, metodo: str, camino: str, cuerpo: dict | None = None, params: dict | None = None) -> dict:
        url = self.url + camino
        if params:
            url += "?" + urllib.parse.urlencode(params)
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        pedido = urllib.request.Request(
            url,
            data=datos,
            method=metodo,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "JoinIn-App/1.0",
            },
        )
        try:
            with urllib.request.urlopen(pedido, timeout=self.espera, context=self._ssl) as respuesta:
                return json.loads(respuesta.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                mensaje = json.loads(error.read() or b"{}").get("error")
            except ValueError:
                mensaje = None
            raise ErrorServidor(mensaje or "Algo falló en el servidor. Intenta de nuevo.", error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise ErrorServidor(SIN_CONEXION, 0) from None

    def _get(self, camino: str, **params) -> dict:
        return self._pedir("GET", camino, params={k: v for k, v in params.items() if v is not None} or None)

    def _post(self, camino: str, cuerpo: dict | None = None) -> dict:
        return self._pedir("POST", camino, cuerpo or {})

    def _delete(self, camino: str, cuerpo: dict | None = None) -> dict:
        return self._pedir("DELETE", camino, cuerpo or {})

    # ------------------------------------------------------------------ General

    def configuracion(self) -> dict:
        return self._get("/api/configuracion")

    def yo(self) -> dict:
        return self._get("/api/yo")

    # ------------------------------------------------------------------ Ingreso

    def pedir_codigo(self, correo: str) -> dict:
        return self._post("/api/ingreso/codigo", {"correo": correo})

    def verificar_codigo(self, correo: str, codigo: str) -> dict:
        return self._post("/api/ingreso/verificar", {"correo": correo, "codigo": codigo})

    def registrar(self, correo: str, nombre: str) -> dict:
        return self._post("/api/ingreso/registrar", {"correo": correo, "nombre": nombre})

    def salir(self) -> dict:
        return self._post("/api/salir")

    # ------------------------------------------------------------------ Avisos

    def tablero(self) -> dict:
        return self._get("/api/avisos")

    def ver_aviso(self, aviso_id: int) -> dict:
        return self._get(f"/api/avisos/{int(aviso_id)}")

    def crear_aviso(self, campos: dict) -> dict:
        return self._post("/api/avisos", campos)

    def unirse(self, aviso_id: int) -> dict:
        return self._post(f"/api/avisos/{int(aviso_id)}/unirse")

    def salirse(self, aviso_id: int) -> dict:
        return self._post(f"/api/avisos/{int(aviso_id)}/salirse")

    def eliminar(self, aviso_id: int) -> dict:
        return self._post(f"/api/avisos/{int(aviso_id)}/eliminar")

    def comentar(self, aviso_id: int, texto: str) -> dict:
        return self._post(f"/api/avisos/{int(aviso_id)}/comentarios", {"texto": texto})

    def borrar_comentario(self, comentario_id: int) -> dict:
        return self._delete(f"/api/comentarios/{int(comentario_id)}")

    def denunciar(self, aviso_id: int, motivo: str, comentario: str = "") -> dict:
        return self._post(f"/api/avisos/{int(aviso_id)}/denunciar", {"motivo": motivo, "comentario": comentario})

    def buzon(self) -> dict:
        return self._get("/api/buzon")

    def revisar_texto(self, texto: str) -> list[str]:
        return self._post("/api/filtro/revisar", {"texto": texto}).get("palabras", [])

    def buscar_lugares(self, consulta: str) -> list[dict]:
        return self._get("/api/lugares", q=consulta).get("lugares", [])

    def direccion(self, lat: float, lng: float) -> dict:
        return self._get("/api/direccion", lat=lat, lng=lng)

    # ------------------------------------------------------------------ Administración

    def admin_estado(self) -> dict:
        return self._get("/api/admin/estado")

    def admin_entrar(self, clave: str) -> dict:
        return self._post("/api/admin/entrar", {"clave": clave})

    def admin_salir(self) -> dict:
        return self._post("/api/admin/salir")

    def admin_salir_todos(self) -> dict:
        return self._post("/api/admin/salir-todos")

    def admin_resumen(self) -> dict:
        return self._get("/api/admin/resumen")

    def admin_denuncias(self) -> dict:
        return self._get("/api/admin/denuncias")

    def admin_descartar_denuncias(self, aviso_id: int) -> dict:
        return self._post(f"/api/admin/denuncias/{int(aviso_id)}/descartar")

    def admin_reglas(self) -> dict:
        return self._get("/api/admin/reglas")

    def admin_agregar_regla(self, palabra: str, cerca_de: str = "", excepto: str = "") -> dict:
        return self._post("/api/admin/reglas", {"palabra": palabra, "cerca_de": cerca_de, "excepto": excepto})

    def admin_borrar_regla(self, regla_id: int) -> dict:
        return self._delete(f"/api/admin/reglas/{int(regla_id)}")

    def admin_probar_filtro(self, texto: str) -> list[str]:
        return self._post("/api/admin/filtro/probar", {"texto": texto}).get("palabras", [])

    def admin_bloqueados(self) -> dict:
        return self._get("/api/admin/bloqueados")

    def admin_borrar_bloqueados(self) -> dict:
        return self._delete("/api/admin/bloqueados")

    def admin_avisos(self) -> dict:
        return self._get("/api/admin/avisos")

    def admin_eliminar_aviso(self, aviso_id: int) -> dict:
        return self._post(f"/api/admin/avisos/{int(aviso_id)}/eliminar")

    def admin_borrar_aviso(self, aviso_id: int) -> dict:
        return self._delete(f"/api/admin/avisos/{int(aviso_id)}")

    def admin_borrar_todos(self, confirmacion: str) -> dict:
        return self._post("/api/admin/avisos/borrar-todos", {"confirmacion": confirmacion})

    def admin_correos(self) -> dict:
        return self._get("/api/admin/correos")

    def admin_liberar_correo(self, correo: str) -> dict:
        return self._post("/api/admin/correos/liberar", {"correo": correo})
