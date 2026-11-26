"""Textos de fechas, cupos y precios, iguales a los que tenía la página."""

from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo

    ZONA_HORARIA = ZoneInfo("America/Santiago")
except Exception:  # sin datos de zonas horarias: la hora local del celular
    ZONA_HORARIA = None

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

CANCELADO, COMPLETO, INICIADO, VENCIDO = "cancelado", "completo", "iniciado", "vencido"


def ahora() -> datetime:
    if ZONA_HORARIA is not None:
        return datetime.now(ZONA_HORARIA)
    return datetime.now(timezone.utc).astimezone()


def leer_fecha(texto: str | None) -> datetime | None:
    """Fecha ISO del servidor, pasada a la hora de Chile."""
    if not texto:
        return None
    momento = datetime.fromisoformat(texto)
    return momento.astimezone(ZONA_HORARIA) if ZONA_HORARIA is not None else momento


def texto_fecha_evento(momento: datetime, referencia: datetime) -> str:
    """'Hoy, 20:00' · 'Mañana, 20:00' · 'sáb 14 nov, 20:00'"""
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - referencia.date()).days
    if dias == 0:
        return f"Hoy, {hora}"
    if dias == 1:
        return f"Mañana, {hora}"
    return f"{DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]}, {hora}"


def texto_cuando(momento: datetime, referencia: datetime) -> str:
    """'hoy a las 20:00' · 'mañana a las 20:00' · 'el sáb 14 nov a las 20:00'"""
    hora = momento.strftime("%H:%M")
    dias = (momento.date() - referencia.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"mañana a las {hora}"
    return f"el {DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]} a las {hora}"


def texto_tiempo_restante(hasta: datetime, referencia: datetime) -> str:
    minutos = int((hasta - referencia).total_seconds() // 60)
    if minutos < 1:
        return "Cierra en menos de 1 min"
    horas, mins = divmod(minutos, 60)
    if horas == 0:
        return f"Cierra en {mins} min"
    return f"Cierra en {horas} h {mins:02d} min"


def texto_faltan(cupos: int) -> str:
    if cupos <= 0:
        return "Grupo completo"
    return "Falta 1 persona" if cupos == 1 else f"Faltan {cupos} personas"


def unir_nombres(nombres: list[str], maximo: int = 3) -> str:
    if not nombres:
        return ""
    if len(nombres) > maximo:
        return ", ".join(nombres[:maximo]) + f" y {len(nombres) - maximo} más"
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


def texto_quienes(aviso: dict) -> str:
    partes = [f"Organiza {aviso['creador']}"] if aviso.get("creador") else []
    inscritos = aviso.get("inscritos") or []
    if inscritos:
        verbo = "Se unió" if len(inscritos) == 1 else "Se unieron"
        partes.append(f"{verbo} {unir_nombres(list(inscritos))}")
    else:
        partes.append("Aún no se une nadie por la app")
    return " · ".join(partes)


def texto_hace(momento: datetime, referencia: datetime) -> str:
    segundos = int((referencia - momento).total_seconds())
    if segundos < 60:
        return "recién"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    if segundos < 86400:
        return f"hace {segundos // 3600} h"
    return texto_fecha_evento(momento, referencia)


def texto_comentarios(n: int) -> str:
    if n == 0:
        return "Sin comentarios"
    return f"{n} comentario{'s' if n != 1 else ''}"


def texto_valor(valor: int | None) -> str:
    """0 -> 'Gratis' · 2000 -> '$2.000 por persona'"""
    if valor is None:
        return ""
    if valor == 0:
        return "Gratis"
    return f"${valor:,} por persona".replace(",", ".")


def iniciales(nombre: str | None) -> str:
    partes = (nombre or "").split()
    if not partes:
        return "?"
    return (partes[0][:1] + (partes[1][:1] if len(partes) > 1 else "")).upper()


CIERRES = {
    CANCELADO: ("Aviso cancelado", "Este aviso fue eliminado. El evento ya no se realiza."),
    COMPLETO: ("¡Grupo completo!", "Ya están todos. Este aviso no recibe más gente."),
    INICIADO: ("El evento ya comenzó", "El aviso se cerró a la hora del evento."),
    VENCIDO: ("Aviso cerrado", "Se cumplió el plazo de {horas} horas."),
}


def estado_en_buzon(aviso: dict, momento: datetime) -> tuple[str, str]:
    """(principal, secundario): cómo va un aviso del buzón y hasta cuándo se ve."""
    inicio = leer_fecha(aviso["inicio_evento"])
    if aviso.get("es_mio"):
        if aviso["cupos_libres"] <= 0:
            principal = "¡Se completó el grupo!"
        elif aviso.get("abierto"):
            principal = "Buscando gente · " + texto_tiempo_restante(leer_fecha(aviso["cierra_en"]), momento).lower()
        else:
            principal = "Ya no recibe más gente"
        secundario = f"Lo verás aquí hasta {texto_cuando(leer_fecha(aviso['expira_en']), momento)}."
    elif aviso.get("cancelado"):
        if aviso.get("cancelado_por") == "admin":
            principal = "Cancelado por la administración"
        else:
            principal = "Cancelado por quien lo publicó"
        secundario = "Este evento ya no se realiza."
    else:
        if momento >= inicio:
            principal = "El evento ya empezó"
        elif aviso["cupos_libres"] <= 0:
            principal = "¡Grupo completo! Nos vemos ahí"
        else:
            principal = "Estás anotado · todavía " + texto_faltan(aviso["cupos_libres"]).lower()
        secundario = f"Se quita de tu buzón {texto_cuando(leer_fecha(aviso['visible_en_buzon_hasta']), momento)}."
    return principal, secundario


def url_como_llegar(aviso: dict) -> str:
    """Indicaciones de Google Maps hasta el lugar (en el celular abre la app de mapas)."""
    from urllib.parse import quote_plus

    if aviso.get("lat") is not None and aviso.get("lng") is not None:
        destino = f"{aviso['lat']},{aviso['lng']}"
    else:
        destino = aviso.get("lugar", "")
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote_plus(destino)


def texto_para_compartir(aviso: dict, momento: datetime, enlace: str) -> str:
    """El mensaje para WhatsApp u otra app: qué es, cuándo, dónde, cuántos faltan y cómo unirse."""
    inicio = leer_fecha(aviso["inicio_evento"])
    lineas = [
        f"¡Nos falta gente! {aviso['nombre_categoria']}: «{aviso['titulo']}»",
        f"{texto_fecha_evento(inicio, momento)} · {aviso['lugar']}",
    ]
    detalle = texto_faltan(aviso["cupos_libres"])
    if aviso.get("valor") is not None:
        detalle += " · " + texto_valor(aviso["valor"])
    lineas.append(detalle)
    lineas.append(f"Únete desde la app Join In (estudiantes ULagos): {enlace}")
    return "\n".join(lineas)
