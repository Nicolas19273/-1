"""
Actualizar Join In desde la propia app, sin pasar por el navegador.

La app no está en Play Store: cada versión nueva es un APK en GitHub Releases.
En Android, el «Actualizar» del tablero:

1. baja el APK con el DownloadManager de Android (con su notificación),
2. muestra el avance en la app,
3. abre el instalador de Android («¿Quieres actualizar esta app?»).

Android instala la versión nueva encima de la actual (sin perder la sesión)
solo si las dos están firmadas con la misma clave: por eso el APK se firma
siempre con la clave del proyecto (ver app_movil/README.md).

Las llamadas a Android se hacen con pyjnius. Fuera de Android (o si algo
falla) la app abre el enlace de descarga, como antes.
"""

from __future__ import annotations

import os

MIME_APK = "application/vnd.android.package-archive"
# Solo para la prueba automática en el emulador: adb deja este archivo en la carpeta de
# la app y, al abrirse, la app recorre «Actualizar» completo (ver pruebas/emulador.sh).
ARCHIVO_PRUEBA = "prueba-actualizar"

BAJANDO, LISTO, FALLO = "bajando", "listo", "fallo"


def _con_id(metodo, descarga: int):
    """
    setFilterById(long...) y remove(long...) reciben «varargs» de Java: pyjnius los
    quiere sueltos (metodo(7)); algunas versiones los quieren en lista (metodo([7])).
    """
    try:
        return metodo(descarga)
    except Exception:
        return metodo([descarga])


def en_android() -> bool:
    """Flet deja este nombre en el entorno al correr dentro de la app de Android."""
    return bool(os.getenv("MAIN_ACTIVITY_HOST_CLASS_NAME"))


def crear_actualizador() -> "ActualizadorAndroid | None":
    """El actualizador de Android, o None si no se puede (otro sistema, sin pyjnius…)."""
    if not en_android():
        return None
    try:
        return ActualizadorAndroid()
    except Exception as error:  # sin pyjnius o sin actividad: se usará el enlace
        print(f"[actualizar] sin actualizador de Android: {error!r}", flush=True)
        return None


class ActualizadorAndroid:
    """Baja e instala el APK nuevo con las herramientas de Android (vía pyjnius)."""

    def __init__(self):
        from jnius import autoclass, cast  # solo existe dentro de la app de Android

        self._clase = autoclass
        anfitrion = autoclass(os.environ["MAIN_ACTIVITY_HOST_CLASS_NAME"])
        self.actividad = anfitrion.mActivity
        if self.actividad is None:
            raise RuntimeError("todavía no hay actividad de Android")
        Context = autoclass("android.content.Context")
        self.descargas = cast(
            "android.app.DownloadManager", self.actividad.getSystemService(Context.DOWNLOAD_SERVICE)
        )
        self.DM = autoclass("android.app.DownloadManager")
        self.Intent = autoclass("android.content.Intent")
        self.Uri = autoclass("android.net.Uri")

    def hay_prueba(self) -> bool:
        File = self._clase("java.io.File")
        archivo = File(self.actividad.getExternalFilesDir(None), ARCHIVO_PRUEBA)
        if archivo.exists():
            archivo.delete()
            return True
        return False

    # ------------------------------------------------------------------ permiso

    def puede_instalar(self) -> bool:
        """Desde Android 8, cada app necesita permiso para instalar otras apps (o su actualización)."""
        if self._clase("android.os.Build$VERSION").SDK_INT < 26:
            return True
        return bool(self.actividad.getPackageManager().canRequestPackageInstalls())

    def pedir_permiso(self) -> None:
        """Abre el ajuste «Instalar apps desconocidas» de Join In."""
        Settings = self._clase("android.provider.Settings")
        intento = self.Intent(
            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
            self.Uri.parse("package:" + self.actividad.getPackageName()),
        )
        intento.addFlags(self.Intent.FLAG_ACTIVITY_NEW_TASK)
        self.actividad.startActivity(intento)

    # ------------------------------------------------------------------ descarga

    def descargar(self, url: str, version: str) -> int:
        """Empieza la descarga y devuelve su número (para preguntar cómo va)."""
        Request = self._clase("android.app.DownloadManager$Request")
        Environment = self._clase("android.os.Environment")
        File = self._clase("java.io.File")
        nombre = f"join-in-{version}.apk"
        carpeta = self.actividad.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
        anterior = File(carpeta, nombre)
        if anterior.exists():  # de un intento anterior: si no, Android lo guarda como «-1.apk»
            anterior.delete()
        pedido = Request(self.Uri.parse(url))
        pedido.setTitle(f"Join In {version}")
        pedido.setDescription("Actualización de Join In")
        pedido.setMimeType(MIME_APK)
        pedido.setNotificationVisibility(Request.VISIBILITY_VISIBLE)
        pedido.setDestinationInExternalFilesDir(self.actividad, Environment.DIRECTORY_DOWNLOADS, nombre)
        return int(self.descargas.enqueue(pedido))

    def estado(self, descarga: int) -> tuple[str, int, int]:
        """(BAJANDO | LISTO | FALLO, bytes bajados, bytes en total)."""
        Query = self._clase("android.app.DownloadManager$Query")
        consulta = Query()
        _con_id(consulta.setFilterById, descarga)
        cursor = self.descargas.query(consulta)
        try:
            if cursor is None or not cursor.moveToFirst():
                return FALLO, 0, 0
            estado = cursor.getInt(cursor.getColumnIndex(self.DM.COLUMN_STATUS))
            bajados = cursor.getLong(cursor.getColumnIndex(self.DM.COLUMN_BYTES_DOWNLOADED_SO_FAR))
            total = cursor.getLong(cursor.getColumnIndex(self.DM.COLUMN_TOTAL_SIZE_BYTES))
        finally:
            if cursor is not None:
                cursor.close()
        if estado == self.DM.STATUS_SUCCESSFUL:
            return LISTO, bajados, total
        if estado == self.DM.STATUS_FAILED:
            return FALLO, bajados, total
        return BAJANDO, max(bajados, 0), max(total, 0)

    def cancelar(self, descarga: int) -> None:
        _con_id(self.descargas.remove, descarga)

    # ------------------------------------------------------------------ instalar

    def instalar(self, descarga: int) -> None:
        """Abre el instalador de Android con el APK recién bajado."""
        uri = self.descargas.getUriForDownloadedFile(descarga)
        if uri is None:
            raise RuntimeError("Android no encontró el archivo descargado")
        intento = self.Intent(self.Intent.ACTION_VIEW)
        intento.setDataAndType(uri, MIME_APK)
        intento.addFlags(self.Intent.FLAG_GRANT_READ_URI_PERMISSION | self.Intent.FLAG_ACTIVITY_NEW_TASK)
        self.actividad.startActivity(intento)
