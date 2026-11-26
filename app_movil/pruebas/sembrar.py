"""
Llena un servidor local de Join In con datos de ejemplo para las capturas del
emulador, e imprime el recorrido.json que la app lee (servidor y token).

    python app_movil/pruebas/sembrar.py http://127.0.0.1:8765 CLAVE_ADMIN > recorrido.json

El servidor tiene que estar en modo de prueba (sin BREVO_API_KEY), así el
código para ingresar viene en la respuesta.
"""

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE = sys.argv[1].rstrip("/")
CLAVE = sys.argv[2]
ZONA = ZoneInfo("America/Santiago")


class Persona:
    def __init__(self, nombre: str, correo: str):
        self.token = secrets.token_hex(16)
        self.cabeceras = {"Authorization": f"Bearer {self.token}"}
        codigo = self.post("/api/ingreso/codigo", {"correo": correo})["codigo_prueba"]
        r = self.post("/api/ingreso/verificar", {"correo": correo, "codigo": codigo})
        if r.get("necesita_nombre"):
            self.post("/api/ingreso/registrar", {"correo": correo, "nombre": nombre})

    def post(self, ruta: str, cuerpo: dict) -> dict:
        r = requests.post(BASE + ruta, json=cuerpo, headers=self.cabeceras, timeout=30)
        assert r.ok, (ruta, r.status_code, r.text)
        return r.json()


def cuando(dias: int, hora: int, minuto: int = 0) -> str:
    momento = (datetime.now(ZONA) + timedelta(days=dias)).replace(hour=hora, minute=minuto, second=0,
                                                                  microsecond=0)
    if momento < datetime.now(ZONA) + timedelta(hours=1):
        momento += timedelta(days=1)
    return momento.isoformat()


def aviso(persona: Persona, **campos) -> int:
    base = {"valor": 0, "descripcion": "", "duracion_horas": 24, "lat": None, "lng": None}
    return persona.post("/api/avisos", {**base, **campos})["aviso"]["id"]


yo = Persona("Nicolás Pérez", "nicolas.perez@alumnos.ulagos.cl")
camila = Persona("Camila Rojas", "camila.rojas@alumnos.ulagos.cl")
matias = Persona("Matías Soto", "matias.soto@alumnos.ulagos.cl")
fernanda = Persona("Fernanda Vera", "fernanda.vera@alumnos.ulagos.cl")
diego = Persona("Diego Muñoz", "diego.munoz@alumnos.ulagos.cl")
javiera = Persona("Javiera Castro", "javiera.castro@alumnos.ulagos.cl")

pichanga = aviso(
    camila, titulo="Pichanga 7 vs 7, nos falta uno", categoria="futbol",
    lugar="Cancha sintética Campus Chuyaca", lat=-40.5874, lng=-73.0882, inicio_evento=cuando(0, 20, 30),
    personas_actuales=5, personas_necesarias=7, valor=1500,
    descripcion="Se paga la cancha entre todos. Traer polera oscura y canilleras.",
)
estudio = aviso(
    matias, titulo="Junta de estudio: Cálculo II", categoria="estudio",
    lugar="Biblioteca Campus Chuyaca, sala 3", inicio_evento=cuando(1, 16), personas_actuales=2,
    personas_necesarias=5, descripcion="Repasamos integrales para el certamen del viernes.",
)
aviso(
    fernanda, titulo="Catan y Dixit en la sala de estudiantes", categoria="juegos_mesa",
    lugar="Sala de estudiantes, edificio B", inicio_evento=cuando(0, 18), personas_actuales=3,
    personas_necesarias=6, duracion_horas=48,
)
aviso(
    diego, titulo="3 vs 3 en el gimnasio", categoria="basquetbol", lugar="Gimnasio universitario",
    inicio_evento=cuando(1, 19), personas_actuales=4, personas_necesarias=6,
)
aviso(
    javiera, titulo="Salida al Volcán Osorno", categoria="salida", lugar="Terminal de buses Osorno",
    inicio_evento=cuando(2, 8), personas_actuales=3, personas_necesarias=8, valor=5000,
    descripcion="Vamos en bus y subimos hasta el refugio. Llevar almuerzo.", duracion_horas=48,
)
mio = aviso(
    yo, titulo="Vóleibol en la playa de Maicolpué", categoria="voleibol", lugar="Playa Maicolpué",
    inicio_evento=cuando(2, 15), personas_actuales=2, personas_necesarias=8,
)
yo.post(f"/api/avisos/{pichanga}/unirse", {})
yo.post(f"/api/avisos/{estudio}/unirse", {})
matias.post(f"/api/avisos/{mio}/unirse", {})
camila.post(f"/api/avisos/{pichanga}/comentarios", {"texto": "¿Alguien trae pelota?"})
yo.post(f"/api/avisos/{pichanga}/comentarios", {"texto": "Yo llevo una, nos vemos allá."})
diego.post(f"/api/avisos/{estudio}/denunciar", {"motivo": "spam", "comentario": "Prueba"})
yo.post("/api/admin/entrar", {"clave": CLAVE})

print(json.dumps({"servidor": sys.argv[3] if len(sys.argv) > 3 else BASE, "token": yo.token}))
