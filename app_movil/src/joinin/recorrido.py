"""
Recorrido automático por las pantallas, solo para las capturas del emulador
(app_movil/pruebas/emulador.sh). Avisa por el registro qué pantalla muestra
(«[recorrido] tablero»), y el emulador toma la foto.
"""

from __future__ import annotations

import asyncio

SEGUNDOS_POR_PANTALLA = 8


async def recorrer(app) -> None:
    from .pantallas.admin import PantallaAdmin, PantallaAdminAvisos
    from .pantallas.aviso import PantallaAviso
    from .pantallas.buzon import PantallaBuzon
    from .pantallas.crear import PantallaCrear

    async def foto(nombre: str) -> None:
        app.page.update()
        await asyncio.sleep(1.5)  # que termine de dibujar
        print(f"[recorrido] {nombre}", flush=True)
        await asyncio.sleep(SEGUNDOS_POR_PANTALLA)

    try:
        for _ in range(60):  # esperar a que conecte y cargue el tablero
            if type(app.actual).__name__ == "PantallaTablero" and getattr(app.actual, "cargado", False):
                break
            await asyncio.sleep(1)
        app.version_nueva = "9.9.9"  # para ver la tarjeta «Actualización disponible»
        app.actual.mostrar_version_nueva()
        await foto("tablero")
        avisos = getattr(app.actual, "avisos", [])
        if avisos:
            await app.ir(PantallaAviso(app, avisos[0]["id"]))
            await foto("aviso")
            await app.volver()
        # uno al que todavía no se unió (con la barra «Unirme» abajo)
        ajeno = next((a for a in avisos if not a.get("es_mio") and not a.get("me_uni")), None)
        if ajeno is not None:
            await app.ir(PantallaAviso(app, ajeno["id"]))
            await foto("aviso_unirse")
            await app.volver()
        await app.ir(PantallaCrear(app))
        await foto("crear")
        await app.page.views[-1].scroll_to(offset=-1, duration=0)  # abajo: la vista previa y «Publicar»
        await foto("crear_abajo")
        await app.volver()
        await app.ir(PantallaBuzon(app))
        await foto("buzon")
        await app.volver()
        await app.ir(PantallaAdmin(app))
        await foto("admin")
        await app.ir(PantallaAdminAvisos(app))
        await foto("admin_avisos")
    except Exception as error:
        import traceback

        print(f"[recorrido] error: {error!r}\n{traceback.format_exc()}", flush=True)
    print("[recorrido] fin", flush=True)
