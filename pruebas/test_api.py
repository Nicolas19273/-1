"""
Prueba la API del servidor (app.py) con un servidor real en un puerto local
y pedidos HTTP de verdad (requests), como los hará la app del celular.
Corre en SQLite y en PostgreSQL (el runner pone DATABASE_URL).
"""
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import datos  # noqa: E402

if not datos.usa_postgres():
    datos.RUTA_BD = Path(tempfile.mkdtemp()) / "api.db"

import uvicorn  # noqa: E402

import acceso  # noqa: E402
import app  # noqa: E402
import lugares  # noqa: E402

CLAVE = "clave-de-prueba-api"
datos.administracion.usar_clave(CLAVE)
acceso.acceso.SEGUNDOS_ENTRE_ENVIOS = 0  # en la prueba no hay que esperar entre códigos

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PUERTO = s.getsockname()[1]
servidor = uvicorn.Server(uvicorn.Config(app.servidor, host="127.0.0.1", port=PUERTO, log_level="warning"))
threading.Thread(target=servidor.run, daemon=True).start()
for _ in range(100):
    if servidor.started:
        break
    time.sleep(0.05)
BASE = f"http://127.0.0.1:{PUERTO}"


class Celular:
    """Un celular con su token, como la app."""

    def __init__(self, token):
        self.token = token

    def pedir(self, metodo, camino, esperado=200, **kw):
        r = requests.request(
            metodo, BASE + camino, headers={"Authorization": f"Bearer {self.token}"}, timeout=10, **kw
        )
        assert r.status_code == esperado, (metodo, camino, r.status_code, r.text)
        return r.json()

    def get(self, camino, esperado=200, **kw):
        return self.pedir("GET", camino, esperado, **kw)

    def post(self, camino, cuerpo=None, esperado=200):
        return self.pedir("POST", camino, esperado, json=cuerpo or {})

    def delete(self, camino, cuerpo=None, esperado=200):
        return self.pedir("DELETE", camino, esperado, json=cuerpo or {})

    def ingresar(self, correo, nombre=None):
        r = self.post("/api/ingreso/codigo", {"correo": correo})
        assert r["correo"] == correo.lower() and len(r["codigo_prueba"]) == 6
        v = self.post("/api/ingreso/verificar", {"correo": correo, "codigo": r["codigo_prueba"]})
        if v.get("necesita_nombre"):
            assert nombre, "estudiante nuevo: falta el nombre"
            v = self.post("/api/ingreso/registrar", {"correo": correo, "nombre": nombre})
        assert v["listo"] is True
        return v


ANA, BETO, CATA, ADMIN = Celular("a" * 32), Celular("b" * 32), Celular("c" * 32), Celular("d" * 32)
SIN_TOKEN = Celular("")
MALO = Celular("no-es-un-token")

# 0) Salud y configuración (sin sesión)
assert SIN_TOKEN.get("/salud") == {"ok": True, "version": 1}
conf = SIN_TOKEN.get("/api/configuracion")
assert conf["dominio"] == "alumnos.ulagos.cl" and conf["modo_prueba"] is True and conf["largo_codigo"] == 6
assert {"clave": "futbol", "nombre": datos.CATEGORIAS["futbol"]} in conf["categorias"]
assert conf["duraciones"] == [24, 48] and conf["max_personas"] == 40 and conf["valor_maximo"] == 80000
assert conf["zona"]["nombre"] == "Osorno" and len(conf["zona"]["centro"]) == 2
assert SIN_TOKEN.get("/no-existe", esperado=404) == {"error": "No encontramos eso."}
assert SIN_TOKEN.get("/")["descarga"] == app.URL_DESCARGA_APP  # el enlace antiguo lleva a la app
print("OK: salud, configuración y 404 en JSON")

# 1) Sin sesión no se ve nada; el token inválido tampoco sirve
assert SIN_TOKEN.get("/api/avisos", esperado=401)["error"] == app.MENSAJE_SIN_SESION
assert MALO.get("/api/buzon", esperado=401)["error"] == app.MENSAJE_SIN_SESION
assert SIN_TOKEN.post("/api/ingreso/codigo", {"correo": "x@alumnos.ulagos.cl"}, esperado=400)["error"].startswith(
    "No pudimos reconocer tu celular"
)
assert ANA.get("/api/yo") == {"ingresado": False, "nombre": "", "es_admin": False}
print("OK: sin sesión responde 401 con un mensaje para la app")

# 2) Ingreso: dominio, código malo, nombre la primera vez, después directo
assert "alumnos.ulagos.cl" in ANA.post("/api/ingreso/codigo", {"correo": "ana@gmail.com"}, esperado=400)["error"]
r = ANA.post("/api/ingreso/codigo", {"correo": "Ana.Rojas@alumnos.ulagos.cl"})
assert r["correo"] == "ana.rojas@alumnos.ulagos.cl"
malo = "000000" if r["codigo_prueba"] != "000000" else "111111"
assert "no es correcto" in ANA.post(
    "/api/ingreso/verificar", {"correo": r["correo"], "codigo": malo}, esperado=400
)["error"]
v = ANA.post("/api/ingreso/verificar", {"correo": r["correo"], "codigo": r["codigo_prueba"]})
assert v == {"listo": False, "necesita_nombre": True}
assert "nombre" in ANA.post(
    "/api/ingreso/registrar", {"correo": r["correo"], "nombre": "x"}, esperado=400
)["error"].lower()
assert ANA.post("/api/ingreso/registrar", {"correo": r["correo"], "nombre": "Ana Rojas"}) == {
    "listo": True,
    "nombre": "Ana Rojas",
}
assert ANA.get("/api/yo") == {"ingresado": True, "nombre": "Ana Rojas", "es_admin": False}
BETO.ingresar("beto@alumnos.ulagos.cl", "Beto")
CATA.ingresar("cata@alumnos.ulagos.cl", "Cata")
# un correo, un celular: otro celular no puede entrar con el correo de Ana
OTRO = Celular("e" * 32)
assert "en uso" in OTRO.post("/api/ingreso/codigo", {"correo": "ana.rojas@alumnos.ulagos.cl"}, esperado=400)["error"]
# salir y volver a entrar (ya registrada: no pide nombre)
assert BETO.post("/api/salir") == {"ok": True}
assert BETO.get("/api/yo")["ingresado"] is False
assert BETO.ingresar("beto@alumnos.ulagos.cl")["nombre"] == "Beto"
print("OK: ingreso con código (nombre la primera vez), un correo un celular, salir y volver")

# 3) Crear aviso: validaciones con mensaje y aviso creado
ahora = datetime.now(datos.ZONA_HORARIA)
inicio = (ahora + timedelta(hours=5)).replace(second=0, microsecond=0)
base = {
    "titulo": "Pichanga en la ULagos",
    "categoria": "futbol",
    "lugar": "Cancha de pasto sintético",
    "inicio_evento": inicio.isoformat(),
    "personas_actuales": 8,
    "personas_necesarias": 10,
    "duracion_horas": 24,
    "descripcion": "Traigan petos",
    "valor": 0,
    "lat": -40.5868,
    "lng": -73.0885,
}
assert "Título" in ANA.post("/api/avisos", {**base, "titulo": "x"}, esperado=400)["error"]
assert "fecha" in ANA.post("/api/avisos", {**base, "inicio_evento": "mañana"}, esperado=400)["error"]
assert ANA.post("/api/avisos", {**base, "titulo": "Una weá de partido"}, esperado=400)["error"]
aviso = ANA.post("/api/avisos", base)["aviso"]
assert aviso["titulo"] == "Pichanga en la ULagos" and aviso["es_mio"] is True and aviso["me_uni"] is False
assert aviso["cupos_libres"] == 2 and aviso["ocupados"] == 8 and aviso["abierto"] is True and aviso["estado"] is None
assert aviso["nombre_categoria"] == datos.CATEGORIAS["futbol"] and aviso["creador"] == "Ana Rojas"
assert datetime.fromisoformat(aviso["inicio_evento"]) == inicio and aviso["valor"] == 0
assert "creador_id" not in aviso and "persona_id" not in str(aviso)
# sin zona horaria se asume la de Chile
sin_zona = ANA.post("/api/avisos", {**base, "titulo": "Ajedrez", "categoria": "juegos_mesa",
                                    "inicio_evento": inicio.replace(tzinfo=None).isoformat(),
                                    "personas_actuales": 1, "personas_necesarias": 2})["aviso"]
assert datetime.fromisoformat(sin_zona["inicio_evento"]) == inicio
print("OK: crear aviso (validaciones, filtro, fechas con y sin zona, sin ids ajenos)")

# 4) Tablero, detalle, unirse, salirse, lleno
tab = BETO.get("/api/avisos")
ids = [a["id"] for a in tab["avisos"]]
assert aviso["id"] in ids and sin_zona["id"] in ids and datetime.fromisoformat(tab["ahora"]).tzinfo
mio = next(a for a in tab["avisos"] if a["id"] == aviso["id"])
assert mio["es_mio"] is False and mio["me_uni"] is False
u = BETO.post(f"/api/avisos/{aviso['id']}/unirse")["aviso"]
assert u["me_uni"] is True and u["inscritos"] == ["Beto"] and u["cupos_libres"] == 1
assert "Ya estás" in BETO.post(f"/api/avisos/{aviso['id']}/unirse", esperado=400)["error"]
assert ANA.post(f"/api/avisos/{aviso['id']}/unirse", esperado=400)["error"]  # no se une a su propio aviso
s = BETO.post(f"/api/avisos/{aviso['id']}/salirse")["aviso"]
assert s["me_uni"] is False and s["cupos_libres"] == 2
BETO.post(f"/api/avisos/{aviso['id']}/unirse")
lleno = CATA.post(f"/api/avisos/{aviso['id']}/unirse")["aviso"]
assert lleno["cupos_libres"] == 0 and lleno["estado"] == datos.COMPLETO and lleno["abierto"] is False
assert aviso["id"] not in [a["id"] for a in CATA.get("/api/avisos")["avisos"]], "lleno: sale del tablero"
det = CATA.get(f"/api/avisos/{aviso['id']}")
assert det["aviso"]["me_uni"] is True and det["aviso"]["inscritos"] == ["Beto", "Cata"] and det["comentarios"] == []
assert ANA.get("/api/avisos/999999", esperado=404)["error"] == "Este aviso ya no existe."
assert ANA.get("/api/avisos/abc", esperado=404)
print("OK: tablero, detalle, unirse/salirse, grupo completo sale del tablero, 404")

# 5) Comentarios: nombre, quien organiza, borrar el propio, no el ajeno
c1 = BETO.post(f"/api/avisos/{aviso['id']}/comentarios", {"texto": "¿Llevo pelota?"})["comentario"]
assert c1["nombre"] == "Beto" and c1["es_mio"] is True and c1["de_quien_organiza"] is False
c2 = ANA.post(f"/api/avisos/{aviso['id']}/comentarios", {"texto": "Sí, porfa"})["comentario"]
assert c2["nombre"] == "Quien organiza" and c2["de_quien_organiza"] is True
assert ANA.post(f"/api/avisos/{aviso['id']}/comentarios", {"texto": ""}, esperado=400)["error"]
vista = CATA.get(f"/api/avisos/{aviso['id']}")
assert [c["texto"] for c in vista["comentarios"]] == ["¿Llevo pelota?", "Sí, porfa"]
assert vista["aviso"]["comentarios"] == 2 and not any(c["es_mio"] for c in vista["comentarios"])
assert CATA.delete(f"/api/comentarios/{c1['id']}", esperado=400)["error"]  # no es suyo
assert BETO.delete(f"/api/comentarios/{c1['id']}") == {"ok": True}
assert [c["texto"] for c in CATA.get(f"/api/avisos/{aviso['id']}")["comentarios"]] == ["Sí, porfa"]
print("OK: comentarios (quien organiza, borrar el propio, no el ajeno)")

# 6) Buzón y eliminar (quien se unió lo ve cancelado)
bz = BETO.get("/api/buzon")
assert [a["id"] for a in bz["me_uni"]] == [aviso["id"]] and bz["organizo"] == []
assert {a["id"] for a in ANA.get("/api/buzon")["organizo"]} == {aviso["id"], sin_zona["id"]}
assert BETO.post(f"/api/avisos/{aviso['id']}/eliminar", esperado=400)["error"]  # no es suyo
el = ANA.post(f"/api/avisos/{aviso['id']}/eliminar")["aviso"]
assert el["cancelado"] is True and el["estado"] == datos.CANCELADO
cancelado = BETO.get("/api/buzon")["me_uni"][0]
assert cancelado["id"] == aviso["id"] and cancelado["cancelado"] is True and cancelado["cancelado_por"] == "dueño"
print("OK: buzón (me uní / organizo) y eliminar (cancelado en el buzón de quien se unió)")

# 7) Denuncias y filtro mientras se escribe
assert BETO.post(f"/api/avisos/{sin_zona['id']}/denunciar", {"motivo": "spam", "comentario": "Repetido"}) == {"ok": True}
assert BETO.post(f"/api/avisos/{sin_zona['id']}/denunciar", {"motivo": "nada"}, esperado=400)["error"]
assert ANA.post("/api/filtro/revisar", {"texto": "hola weón"})["palabras"]
assert ANA.post("/api/filtro/revisar", {"texto": "hola amigos"})["palabras"] == []
print("OK: denunciar (con motivo válido) y revisar texto con el filtro")

# 8) Lugares: búsqueda y dirección (sin internet: con respuestas falsas del buscador)
lugares.buscador.buscar = lambda q: [lugares.Lugar("Cancha ULagos", "Av. Fuchslocher, Osorno", -40.58, -73.09, tipo="Cancha")] if q else []
lugares.buscador.direccion_de = lambda lat, lng: "Av. Fuchslocher 1305"
assert ANA.get("/api/lugares", params={"q": "cancha"})["lugares"] == [
    {"nombre": "Cancha ULagos", "detalle": "Av. Fuchslocher, Osorno", "lat": -40.58, "lng": -73.09,
     "tipo": "Cancha", "texto": "Cancha ULagos, Av. Fuchslocher, Osorno"}
]
d = ANA.get("/api/direccion", params={"lat": "-40.58", "lng": "-73.09"})
assert d["direccion"] == "Av. Fuchslocher 1305" and d["dentro_de_zona"] is True
assert ANA.get("/api/direccion", params={"lat": "x", "lng": "1"}, esperado=400)


def sin_servicio(q):
    raise lugares.ErrorBusqueda("El buscador de lugares no responde. Intenta en un rato.")


lugares.buscador.buscar = sin_servicio
assert ANA.get("/api/lugares", params={"q": "x"}, esperado=503)["error"].startswith("El buscador")
assert SIN_TOKEN.get("/api/lugares", params={"q": "x"}, esperado=401)
print("OK: lugares y dirección (y 503 si el buscador no responde)")

# 9) Administración: clave, sin cuenta, panel completo
assert ANA.get("/api/admin/estado") == {"hay_clave": True, "es_admin": False}
assert ANA.get("/api/admin/resumen", esperado=403)["error"] == app.MENSAJE_SIN_ADMIN
assert ANA.post("/api/admin/entrar", {"clave": "mala"}, esperado=400)["error"] == "Clave incorrecta."
# entrar SIN haber ingresado con el correo (su correo puede estar en uso en otro celular)
assert ADMIN.get("/api/yo")["ingresado"] is False
assert ADMIN.post("/api/admin/entrar", {"clave": CLAVE}) == {"es_admin": True}
assert ADMIN.get("/api/yo")["es_admin"] is True and datos.es_admin("celular:" + "d" * 32)
cifras = ADMIN.get("/api/admin/resumen")["cifras"]
assert cifras["estudiantes"] == 3 and cifras["avisos_total"] == 2
den = ADMIN.get("/api/admin/denuncias")["denuncias"]
assert [x["aviso"]["id"] for x in den] == [sin_zona["id"]] and den[0]["denuncias"][0]["nombre_motivo"]
assert ADMIN.post(f"/api/admin/denuncias/{sin_zona['id']}/descartar") == {"ok": True}
assert ADMIN.get("/api/admin/denuncias")["denuncias"] == []
regla = ADMIN.post("/api/admin/reglas", {"palabra": "palabrota", "cerca_de": "", "excepto": ""})["regla"]
assert regla["palabra"] == "palabrota" and regla["siempre"] is True
assert ADMIN.post("/api/admin/filtro/probar", {"texto": "una palabrota"})["palabras"] == ["palabrota"]
assert ANA.post("/api/filtro/revisar", {"texto": "una palabrota"})["palabras"] == ["palabrota"]
assert [r["id"] for r in ADMIN.get("/api/admin/reglas")["reglas"]] == [regla["id"]]
assert ADMIN.delete(f"/api/admin/reglas/{regla['id']}") == {"ok": True}
assert ADMIN.get("/api/admin/reglas")["reglas"] == [] and ADMIN.get("/api/admin/reglas")["palabras_base"] > 10
bl = ADMIN.get("/api/admin/bloqueados")
assert bl["dias"] == 30 and any(b["campo"] == "Título" for b in bl["bloqueados"])
assert ADMIN.delete("/api/admin/bloqueados") == {"ok": True} and ADMIN.get("/api/admin/bloqueados")["bloqueados"] == []
print("OK: admin entra con la clave sin cuenta; resumen, denuncias, reglas y bloqueados")

# 10) Admin: correos en uso y liberar (el celular nuevo puede entrar)
correos = {c["correo"]: c for c in ADMIN.get("/api/admin/correos")["correos"]}
assert set(correos) == {"ana.rojas@alumnos.ulagos.cl", "beto@alumnos.ulagos.cl", "cata@alumnos.ulagos.cl"}
assert correos["cata@alumnos.ulagos.cl"]["nombre"] == "Cata" and datetime.fromisoformat(correos["cata@alumnos.ulagos.cl"]["usado"])
assert ADMIN.post("/api/admin/correos/liberar", {"correo": "nadie@alumnos.ulagos.cl"}, esperado=400)["error"]
lib = ADMIN.post("/api/admin/correos/liberar", {"correo": "ana.rojas@alumnos.ulagos.cl"})
assert lib == {"correo": "ana.rojas@alumnos.ulagos.cl", "sesiones_cerradas": 1}
assert ANA.get("/api/yo")["ingresado"] is False
assert OTRO.ingresar("ana.rojas@alumnos.ulagos.cl")["nombre"] == "Ana Rojas"  # ya puede entrar desde otro celular
print("OK: admin ve los correos en uso y libera uno")

# 11) Admin: avisos (todos), eliminar, borrar uno y borrar todos con BORRAR
todos = ADMIN.get("/api/admin/avisos")["avisos"]
assert {a["id"] for a in todos} == {aviso["id"], sin_zona["id"]}
assert next(a for a in todos if a["id"] == aviso["id"])["cancelado"] is True
quitado = ADMIN.post(f"/api/admin/avisos/{sin_zona['id']}/eliminar")["aviso"]
assert quitado["cancelado_por"] == "admin"
assert ADMIN.delete(f"/api/admin/avisos/{aviso['id']}") == {"titulo": "Pichanga en la ULagos"}
assert BETO.get(f"/api/avisos/{aviso['id']}", esperado=404)
assert BETO.get("/api/buzon")["me_uni"] == []  # no deja rastro
assert BETO.post("/api/admin/avisos/borrar-todos", {"confirmacion": "BORRAR"}, esperado=403)
assert ADMIN.post("/api/admin/avisos/borrar-todos", {"confirmacion": "no"}, esperado=400)["error"] == "Escribe BORRAR para confirmar."
assert ADMIN.post("/api/admin/avisos/borrar-todos", {"confirmacion": "borrar"}) == {"borrados": 1}
assert ADMIN.get("/api/admin/avisos")["avisos"] == []
print("OK: admin ve todos los avisos, elimina, borra uno y borra todos (con BORRAR)")

# 12) Admin: la sesión pasa a la cuenta al ingresar; salir; cerrar todas
ADMIN.ingresar("jefa@alumnos.ulagos.cl", "Jefa")
assert ADMIN.get("/api/yo") == {"ingresado": True, "nombre": "Jefa", "es_admin": True}
assert not datos.es_admin("celular:" + "d" * 32)
assert ADMIN.post("/api/admin/salir") == {"ok": True}
assert ADMIN.get("/api/admin/estado")["es_admin"] is False
ADMIN.post("/api/admin/entrar", {"clave": CLAVE})
CATA.post("/api/admin/entrar", {"clave": CLAVE})
assert ADMIN.post("/api/admin/salir-todos")["cerradas"] == 2
assert CATA.get("/api/admin/resumen", esperado=403)
print("OK: la sesión de admin pasa a la cuenta, salir y cerrar todas")

# 13) Pedidos raros: JSON roto
r = requests.post(BASE + "/api/ingreso/codigo", data="{no es json", headers={"Authorization": "Bearer " + "a" * 32}, timeout=10)
assert r.status_code == 400 and r.json() == {"error": "Pedido no válido."}
r = requests.post(BASE + "/api/ingreso/codigo", json=[1, 2], headers={"Authorization": "Bearer " + "a" * 32}, timeout=10)
assert r.status_code == 400
print("OK: JSON roto o que no es un objeto responde 400")

servidor.should_exit = True
print("OK: API completa | BD:", "PostgreSQL" if datos.usa_postgres() else "SQLite")
