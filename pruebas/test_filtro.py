"""
Prueba el filtro de palabras inapropiadas con textos reales de avisos.

    python pruebas/test_filtro.py

DEBE_TAPAR: lo que no se puede publicar (garabatos, sexual, discriminación,
drogas, violencia), también escrito con trucos.
NO_TAPAR: avisos normales de estudiantes que se parecen a algo malo (lugares,
apellidos, la hora pico, la chupalla, una charla de prevención...).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import filtro  # noqa: E402

DEBE_TAPAR = [
    # --- garabatos, con mayúsculas, tildes y trucos
    "weón", "WEÓN", "Weon", "huevón", "hueón", "güeón", "aweonao", "culiao", "CULIAO", "qlo", "ql",
    "conchetumare", "chuchetumare", "ctm", "csm", "puta", "mierda", "cabrón", "pendejo", "maricón",
    "coño", "pichula", "hijueputa", "gilipollas", "boludo", "fuck", "shit", "bitch", "asshole",
    "w3on", "mi3rd4", "$hit", "@weonao", "cul1ao", "hu3v0n", "put4",
    "weooooon", "ctmmmm", "puuuuta", "culiaaaao", "mieeerda",
    "p.u.t.a", "c u l o", "m-i-e-r-d-a", "C.T.M", "w e o n",
    "weonculiao", "conchetumaaare", "pendejadas", "mierdita", "fuckingggg", "laweonada",
    "concha de tu madre", "chupa pico", "me cago en todo",
    "conxetumare", "xuxa", "qliao", "weona culiá", "la puta madre", "hijo de puta", "saco de wea",
    "ctmre", "lpm", "chúpalo weón", "mamahuevo", "comemierda", "malparido", "pelotudo",
    # --- sexual
    "chúpame el pico", "te chupo el pico", "ven a chupar mi pico", "vamos a culiar", "echemos un polvo",
    "una cachita rica", "hacerte una paja", "vendo pack", "pack hot", "fotos desnuda",
    "busco sexo casual", "sexo gratis", "trío sexual", "quiero tirar contigo", "coger contigo rico",
    "te rompo la raja", "chupa la tula", "mámame los huevos", "onlyfans", "sígueme en only fans",
    "escort", "prepago rica", "orgía en mi casa", "milf", "porno", "tetona", "follar",
    "mándame fotos desnuda", "chupa la polla", "lame mi poto", "maraca culiá", "eres una perra",
    "hija de perra", "eres una maraca", "p1c0 rico",
    # --- discriminación
    "no se aceptan peruanos", "odio a los gays", "veneco", "venecos culiaos", "bolita culiao",
    "indio culiao", "eres un retrasado", "eres autista weón", "pareces down", "maricón", "fleto",
    "camiona", "negros de mierda", "mueran los mapuches", "deporten a los haitianos",
    "los gordos dan asco", "no queremos migrantes", "prohibida la entrada a colombianos",
    "raza superior", "heil hitler", "viva hitler", "soy nazi", "sudaca", "flaite", "marimacho",
    "cara de mongolo", "eres un hueco", "roto culiao", "pinche pendejo",
    # --- drogas
    "vendo marihuana", "fumemos un pito", "jalemos coca", "pegarse unas pepas", "carrete con tusi",
    "tusi", "vendo falopa", "pasta base", "hongos mágicos", "traigan marihuana al carrete",
    "compro cocaína", "lsd en la fiesta", "venta de drogas", "v3nd0 m4r1hu4n4", "armemos un porro",
    "fumar weed", "jalar unas líneas de merca",
    # --- violencia
    "te voy a matar", "te mato", "suicídate", "mátate", "ojalá te mueras", "córtate las venas",
    "te voy a pegar un balazo", "hay que matarlos", "te voy a violar", "kill yourself", "kys",
    "te voy a apuñalar", "s u i c i d a t e",
]

NO_TAPAR = [
    # --- palabras normales que contienen algo malo adentro
    "película", "ridículo", "vehículo", "cálculo", "artículo", "círculo", "computadora", "disputa",
    "reputación", "imputar", "Vergara", "vergüenza", "Putaendo", "Culiacán", "Cabrero", "Chicago",
    "las 5 y pico", "Pico de Orizaba", "Coca-Cola", "hacer cola", "la Polla Chilena", "año nuevo",
    "Concha y Toro", "Playa La Concha", "qué paja", "maracas", "Tula", "Gil", "huevos revueltos",
    "pera", "pero", "perro", "Pta. Arenas", "Scunthorpe", "class", "pass", "assistant", "Mitsubishi",
    "Fukushima", "shiitake", "Pichidangui", "Chupacabras", "Concepción", "Puerto Montt", "mamá",
    "7 vs 7", "fútbol 5 a 5", "4-4-2", "3 x 3", "partido a las 20:30", "U. de Chile", "neón", "peón",
    "Pichanga en la cancha 3, traer polera oscura", "música del siglo XX", "polera talla XXL",
    "xxxxxxxx", "Estudio de cálculo en la biblioteca",
    # --- lugares y apellidos
    "Paseo a Coñaripe", "Surf en Pichilemu", "Viaje a Pucón", "Pichicuy", "Conchalí", "Culiprán",
    "Putú", "Chuchunco", "Peñaflor", "Ñuñoa", "Huechuraba", "Licantén", "Pelluhue", "Futaleufú",
    "María José Concha", "Pedro Pichún", "Ana Colipí", "Luis Huenchullán", "Rosa Painemal",
    "Javiera Catrileo", "Tomás Millapán", "Camila Ñancupil", "la profesora Concha",
    # --- avisos normales que se parecen a algo malo
    "Subida al pico La Campana", "Trekking al Pico Bulnes", "Hora pico en el metro",
    "Pico de gallo para el asado", "Llevar pico y pala para la plantación", "Llegamos a las 8 y pico",
    "Fonda dieciochera: ven con tu chupalla", "Taller de cueca, trae chupalla y pañuelo",
    "Visita a la viña Concha y Toro", "Recolectemos conchas marinas en la playa",
    "Busco a mi perra perdida, se llama Luna", "Paseo con perros y perras del refugio",
    "Se me perdió un pinche del pelo en la biblioteca", "Charla: cultura mongola y Gengis Kan",
    "Charla de prevención de ITS: gonorrea, sífilis y VIH",
    "Clase de historia: la Alemania nazi y el Holocausto",
    "Documental sobre Hitler y la Segunda Guerra Mundial", "Taller de dibujo de desnudo artístico",
    "Vendo pack de apuntes de cálculo", "Six pack de cervezas para el asado", "Pack de bebidas",
    "Traigan pito para arbitrar la pichanga", "Compro coca y papas para la once",
    "Traigan Coca-Cola y hielo", "Torneo de fútbol: el Cholo es un crack", "Es un crack jugando",
    "Juego de bolitas en el patio", "Mi celular está roto", "Se rompió la pelota, está rota",
    "Nuestro bus va retrasado 10 minutos", "Vuelo retrasado, llegamos tarde",
    "Charla sobre neurodiversidad y el espectro autista", "Jornada de inclusión: síndrome de Down",
    "Taller solo para mujeres: defensa personal",
    "Encuentro de estudiantes migrantes y extranjeros", "Feria de comida peruana y venezolana",
    "Charla contra el racismo: el odio hacia los migrantes en redes",
    "Cine foro sobre discriminación a personas gays", "Charla de prevención: efectos de la marihuana",
    "Debate sobre la legalización del cannabis medicinal",
    "Taller de SENDA: prevención del consumo de drogas", "Fiesta sin drogas ni alcohol",
    "Hay que matar el tiempo antes del certamen", "Juego de rol: matar zombies",
    "Torneo de videojuegos: hay que matarlos a todos", "Educación sexual: hablemos de consentimiento",
    "Película 'Sexo, pudor y lágrimas' en el cine club", "Trío de jazz en el casino",
    "Concierto: trío de cuerdas", "Tomemos hierba mate en el parque", "Plantas y hierbas medicinales",
    "La raja la pichanga de ayer", "Estuvo la raja tu carrete", "Qué paja, llueve", "Echar una mano",
    "Polvo de hornear para la torta", "Limpiar el polvo de la sala", "Cachai que mañana hay clases",
    "Cacha la hora", "Asado de fin de semestre: traer carbón", "Fútbol 7: faltan 3, traer canilleras",
    "Estudio de anatomía: aparato reproductor, pene y vagina", "Magna cum laude: titulación",
    "Vamos a tirar penales", "Coger el bus de las 8", "Bolas de nieve en Farellones",
    "La heroína de la película", "Éxtasis de la música barroca: concierto",
    "Busco 3 personas para un trío de pádel", "Tomemos once con pan con palta",
    "Taller de cocina: huevos rellenos", "Junta de estudio de química orgánica",
    "Carrete de bienvenida mechona", "Pichanga mixta, trae tu polera", "Hay que llegar a la meta",
    "Voy a matar ese control de cálculo", "Mañana hay tocata en el centro",
]

no_tapados = [t for t in DEBE_TAPAR if not filtro.contiene(t)]
mal_tapados = [(t, filtro.encontradas(t)) for t in NO_TAPAR if filtro.contiene(t)]
assert not no_tapados, f"no detectó: {no_tapados}"
assert not mal_tapados, f"tachó textos normales: {mal_tapados}"

# encontradas: dice cuáles, tal como se escribieron
assert filtro.encontradas("Pichanga WEÓN, falta uno ctm") == ["WEÓN", "ctm"]
assert filtro.encontradas("vengan p.u.t.a.s") == ["p.u.t.a.s"]
assert filtro.encontradas("weón y Weón") == ["weón"]
assert filtro.encontradas("Todo normal") == [] and filtro.encontradas(None) == []
assert filtro.encontradas("chúpame el pico") == ["chúpame el pico"]
assert filtro.encontradas("vendo marihuana barata") == ["marihuana"]

# quitar: borra la palabra y ordena espacios y comas
casos = {
    "Pichanga weón, falta uno": "Pichanga, falta uno",
    "Traigan la wea de pelota, ctm": "Traigan la de pelota",
    "ctm, vengan a jugar": "vengan a jugar",
    "Partido CTM a las 8": "Partido a las 8",
    "la concha de tu madre que frío": "la que frío",
    "Línea 1 weón\nLínea 2 normal": "Línea 1\nLínea 2 normal",
    "weón": "",
    "Todo normal aquí": "Todo normal aquí",
}
for entrada, esperado in casos.items():
    assert filtro.quitar(entrada) == esperado, (entrada, filtro.quitar(entrada))
assert filtro.quitar("") == "" and filtro.quitar(None) == ""

# Las reglas propias (de la administración) conviven con las de fábrica
filtro.configurar([filtro.Regla(1, "zapallo", ("eres",), ())])
assert filtro.contiene("eres zapallo") and not filtro.contiene("sopa de zapallo")
assert filtro.contiene("chúpame el pico")  # las de fábrica siguen
assert filtro.reglas_actuales()[0].palabra == "zapallo"
filtro.configurar([])
assert not filtro.contiene("eres zapallo") and filtro.contiene("vendo marihuana")

cifras = filtro.cantidad_base()
assert cifras["palabras"] > 500 and cifras["reglas"] > 200 and cifras["frases"] > 50, cifras
print(f"OK: filtro tapa {len(DEBE_TAPAR)} casos y respeta {len(NO_TAPAR)} textos normales "
      f"({cifras['palabras']} palabras, {cifras['frases']} frases, {cifras['reglas']} reglas de contexto)")
