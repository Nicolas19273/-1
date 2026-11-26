"""
filtro_listas.py — Las listas del filtro de palabras inapropiadas de Join In.

Están aparte de filtro.py (que tiene el «motor») para que se puedan leer y
editar sin tocar el código que las aplica. Hay cuatro tipos de entradas:

  * PALABRAS   se tapan siempre que aparecen como palabra entera.
  * PEDAZOS    se tapan aunque estén pegados a otras palabras ("weonculiao").
               Solo van aquí trozos que NO aparecen dentro de palabras normales.
  * FRASES     se tapan cuando aparecen juntas y en ese orden.
  * REGLAS_BASE  palabras que solo son inapropiadas en cierto contexto:
               «pico» en "chupa el pico" sí, pero no en "las 5 y pico";
               «marihuana» junto a "vendo" sí, pero no en una charla de prevención.

  PERMITIDAS: palabras normales que se parecen a una grosería al normalizarlas
  (por ejemplo, "chupalla", el sombrero, se parece a "chupala").

Fuentes consultadas para armarlas (noviembre de 2026): listas públicas de
palabras ofensivas en español (LDNOOBW, words/cuss, Thoughtrights/malapropos,
washyourmouthoutwithsoap), notas de prensa chilena sobre garabatos e insultos
homofóbicos y xenófobos, y el artículo «Nombres populares y clasificación de
las drogas de abuso ilícitas en Chile» (Rev Med Chile 2019). Se revisó cada
palabra a mano: de esas listas se dejaron afuera las que en Chile son normales
(copa, cola, compañero, polvo, cachar, choro, gomas, paja...).

Cuidado al agregar: todo se compara ya «normalizado» (sin tildes, en
minúsculas, con números por letras: 4→a, 3→e, 0→o, 1→i). Escribe cada palabra
con o sin tildes; da lo mismo. No pongas palabras con 3 letras iguales seguidas.
"""

from __future__ import annotations

# =========================================================================== #
# PALABRAS: se tapan siempre (palabra entera)
# =========================================================================== #

# Garabatos chilenos y sus variantes de escritura (w/hu/gu, ch/x, c/k/q)
GARABATOS_CHILENOS = """
weon weona weones weonas weonao weonaos weonaa weonada weonadas weonazo weonazos weoncito weoncita
weonsito weonsita weonear weoneando weoniando wn wna wns wnes
huevon huevona huevones huevonas hueon hueona hueones hueonas hueonazo guevon guevona guevones
gueon gueona gueones webon webona webones wevon wevona wevones wueon wueona
aweonao aweonaa aweonaos aweonado aweonada aweonados aweonadas aweona aweonas aweonarse aweonando
ahuevonao ahuevonado ahuevonada ahueonao ahueonado ahueonada ahueonados
wea weas weado weada weada huea hueas huevada huevadas
culiao culiaos culia culias culiada culiadas culiado culiados culiaa culiaas culiar culear culiando
culeando culiamos culeamos culiaron culearon culiarse culearse culiandose culiame culeame culeado
culeada culeados culeadas culero culera culeros culeras culito culitos culo culos culon culona
culones culonas culazo
ql qlo qla qls qlos qlas qlia qlias qliao qliaos qlao qlaos qliado kliao kuliao kulia kliado
conchetumare conchetumadre conchatumadre conchatumare conchesumadre conchesumare conchasumadre
conchasumare conchetumares conxetumare conxatumare conchetuma conshetumare conchemadre
chuchetumare chuchetumadre chuchatumadre chuchatumare chuchesumadre chuchesumare xuxetumare xuxa
xuxas chucha chuchas
ctm csm ctmr csmr ctmre chtm lpm lptm hdp hdlgp ptm ptmr ptmre mrd mrda
hijueputa hijueputas hijoeputa hijoputa hijaputa hijodeputa hijadeputa hijosdeputa jueputa joputa
hijueperra
puta putas puto putos putita putitas putito putitos puton putona putones putonas putear puteada
puteadas puteando puteo putero puteros puteria puterio putada putadas putisima putisimo putamadre
mierda mierdas mierdero mierdoso mierdosa mierdita
cagar cagada cagadas cagado cagados cagon cagona cagones cagando cago cagas caga cagan cague
cagaste cagaron cagadero cagazo cagarse cagarla cagao
cabron cabrona cabrones cabronas cabronazo carajo carajos coño coños
joder jodido jodida jodidos jodidas jodete joderse jodan jodienda
verga vergas vergon vergudo vergazo vergota vergueo
pendejo pendeja pendejos pendejas pendejada pendejadas
cojones cojon cojudo cojuda cojudos cojudas
"""

# Insultos (también de otros países de habla hispana)
INSULTOS = """
mongolico mongolica mongolicos mongolicas mogolico mogolica mogolicos mogolicas
subnormal subnormales tarado tarada tarados taradas imbecil imbeciles idiota idiotas
estupido estupida estupidos estupidas cretino cretina cretinos cretinas
pelotudo pelotuda pelotudos pelotudas boludo boluda boludos boludas
gilipollas gilipolla gilipollez gilipolleces malparido malparida malparidos malparidas
chingar chingada chingado chingados chingadera chingaderas chinga chingon chingona chingadazo
mamon mamona mamones mamonas mamada mamadas mamahuevo mamaguevo mamahuevos mamavergas mamaverga
chupala chupalo chupamela chupamelo chupapico chupapicos chupapija chupavergas chupaverga
chupapollas chupapenes chupapinga lameculos lameculo soplapollas comepollas comemierda comemierdas
puñeta puñetas puñetero puñetera
zorra zorras zorron zorrona zorrita zorritas
pichula pichulas pichulon pichulita
pajero pajera pajeros pajeras pajearse pajeando pajeandose pajazo
"""

# Términos sexuales vulgares o explícitos
SEXUALES = """
follar follando follada follado follamos follaron follador folladora follame follarte follarme
garchar garchando garche garcha singar singando fornicar fornicando
teta tetas tetona tetonas tetudo tetuda tetudas
orgia orgias bukkake gangbang milf milfs dildo dildos swinger swingers
porno porn nudes nude pornhub xvideos xnxx redtube onlyfans onlyfan
prostituta prostitutas prostituto prostitutos escort escorts scort scorts cafiche cafiches
violarte violarla violarlo violarlas violarlos
"""

# Ofensas por orientación sexual, origen, etnia, clase o discapacidad.
# (Las palabras de identidad —gay, lesbiana, trans, mapuche, peruano...— NO
# están: solo los insultos. Ver también la regla de exclusión más abajo.)
DISCRIMINACION = """
maraco maracos maraquito maricon maricones maricona mariconas mariconazo maricueca maricuecas
marica maricas mariposon mariposones marimacho marimachos machorra machorras camiona camionas
fleto fletos fletito colipato colipatos colipata joto jotos trolo trolos bujarron bujarra
travelo travelos bollera bolleras tortillera tortilleras sidoso sidosa
flaite flaites cuma cumas sudaca sudacas veneco venecos veneca venecas perucho peruchos perucha
peruchas peruca perucas negrata negratas
"""

# Violencia contra uno mismo u otros (las frases están en FRASES)
VIOLENCIA = """
suicidate suicidense matate matense ahorcate ahorquense muerete muéranse
"""

# Inglés
INGLES = """
fuck fucks fucking fuckin fucker fuckers fucked fck fk fuk fukin fuking motherfucker motherfuckers
wtf stfu shit shits shitty bullshit bitch bitches bitchy asshole assholes ass dumbass jackass
cunt cunts pussy pussies dick dicks dickhead dickheads cocksucker bastard bastards slut sluts whore
whores nigger niggers nigga niggas faggot faggots fag fags retard retarded twat wanker wankers kys
boobs tits titties horny blowjob blowjobs handjob cumshot thot skank douche douchebag tranny
trannies spic spics beaner beaners chink chinks kike kikes wetback wetbacks dyke dykes arsehole
bollocks rapist rapists
"""

PALABRAS = "\n".join([GARABATOS_CHILENOS, INSULTOS, SEXUALES, DISCRIMINACION, VIOLENCIA, INGLES])

# =========================================================================== #
# PEDAZOS: se tapan aunque estén pegados a otras palabras
# =========================================================================== #

PEDAZOS = """
conchetu conchatu conchesu conchasu conxetu conxatu chuchetu chuchatu chuchesu xuxetu
hijueput hijodeput hijadeput hijoput putamadr culiao culiado culiaos qliao qliado qlao
aweon ahueona ahuevona maricon pendej mierd weon hueon huevon gilipoll mamahuev mamaguev
chupapic chupapij chupaverg chupapoll soplapoll lameculo comepoll motherf fuck nigger nigga faggot
"""

# =========================================================================== #
# FRASES: se tapan cuando aparecen juntas, en este orden
# =========================================================================== #

FRASES = [
    # garabatos
    "concha de tu madre", "concha e tu madre", "concha tu madre", "concha su madre",
    "concha de tu hermana", "concha de la lora", "la puta madre", "hijo de puta", "hija de puta",
    "chupa pico", "chupen pico", "chupa la", "chupame la", "chupame el", "me la chupai",
    "me la chupas", "me la chupan", "pal pico", "me cago en", "saco de wea", "saco e wea",
    # sexual
    "hacerse una paja", "hacerte una paja", "hacerme una paja", "hacerle una paja", "paja rusa",
    "correrse una paja", "correrte una paja", "corrersela", "echar un polvo", "echarse un polvo",
    "echarnos un polvo", "echar una cacha", "echarse una cacha", "echarnos una cacha",
    "echar una cachita", "remojar el cochayuyo", "mojar el bizcocho", "mojar la brocha",
    "sexo oral", "sexo anal", "sexo casual", "sexo grupal", "sexo gratis", "sexo duro",
    "busco sexo", "quiero sexo", "trio sexual", "fiesta swinger", "intercambio de parejas",
    "only fans", "pack hot", "fotos desnuda", "fotos desnudo", "fotos desnudas", "fotos hot",
    # violencia y amenazas
    "te voy a matar", "los voy a matar", "las voy a matar", "la voy a matar", "lo voy a matar",
    "te mato", "los mato", "te voy a violar", "te voy a pegar un balazo", "te voy a apuñalar",
    "te voy a apunalar",
    "ojala te mueras", "ojala se mueran", "que se mueran todos", "muerte a los", "muerte a las",
    "cortate las venas", "tirate de un puente", "tirate de un edificio", "mejor matate",
    "kill yourself", "go kill yourself",
    # odio
    "raza superior", "raza inferior", "seres inferiores", "sieg heil", "heil hitler",
    "white power", "poder blanco", "limpieza etnica",
]

# =========================================================================== #
# PERMITIDAS: palabras normales que se parecen a una grosería
# =========================================================================== #

PERMITIDAS = """
chupalla chupallas
"""

# =========================================================================== #
# REGLAS_BASE: palabras que se tapan solo en cierto contexto
# =========================================================================== #
#
# Cada regla: (palabras, cerca_de, excepto, salvo)
#   * palabras:  una o varias formas («pico picos»), o una lista de frases.
#   * cerca_de:  se tapan si alguna de estas aparece a 3 palabras o menos.
#                Vacío = siempre (útil con «salvo»).
#   * excepto:   frases que contienen la palabra y donde nunca se tapa ("y pico").
#   * salvo:     si alguna de estas aparece en cualquier parte del texto, no se
#                tapa (una charla de prevención, una clase de historia...).

# --- Sexual -------------------------------------------------------------------

VERBOS_SEXUALES = [
    "chupa", "chupame", "chupen", "chupar", "chuparte", "chupo", "chupai", "chupas", "chupalo",
    "mama", "mamame", "mamar", "mamen", "lame", "lameme", "lamer", "lamen",
    "come", "comete", "comer", "como", "meter", "meto", "mete", "meterte", "metertelo",
    "sobar", "soba", "sobame", "tocar", "tocame", "toca", "muestra", "muestrame", "mostrar",
    "ensename", "culiar", "culear", "follar", "coger", "tirar", "rico", "rica", "grande", "parado",
    "duro", "mojada", "mojado", "caliente",
]
SALVO_EDUCACION = [
    "educacion", "educativo", "charla", "taller", "salud", "prevencion", "its", "ets", "vih",
    "consentimiento", "biologia", "anatomia", "medicina", "clase", "seminario", "diversidad",
    "genero", "ginecologia", "urologia", "cancer", "pelicula", "cine", "libro", "obra", "teatro",
    "literatura", "arte",
]

REGLAS_SEXUALES = [
    ("pico picos", ["chupa", "chupen", "chupame", "chupar", "chupo", "chupai", "mama", "mamame",
                    "mamar", "comete", "coman", "sobame", "soba", "mi", "tu", "su", "pal",
                    "parado", "rico"],
     ["y pico", "hora pico", "horas pico", "pico de", "pico y pala", "pico y placa", "pico de gallo",
      "pico del", "el pico mas alto", "un pico de", "picos de"], []),
    ("pirula tula", ["chupa", "chupame", "chupar", "mama", "mamame", "mamar", "lame", "lameme",
                     "sobame", "soba", "mi", "tu", "su", "parada", "parado"], [], []),
    ("raja", ["romper", "rompo", "rompa", "rompe", "partir", "parto", "meter", "meto", "mete",
              "chupa", "chupame", "lame", "lameme", "culiar", "mojada"], [], []),
    ("poto potito", ["chupa", "chupame", "lame", "lameme", "meter", "meto", "mete", "culiar",
                     "culear", "romper", "rompo", "entregar", "entrega", "dar el", "rico",
                     "rica", "sabroso", "mostrar", "muestra", "muestrame"], [], []),
    ("polla pollas", ["chupa", "chupame", "chupar", "chupen", "mamar", "mamame", "comete", "come",
                      "comeme", "meter", "meto", "lame", "lameme"],
     ["polla chilena", "polla gol"], []),
    ("concha conchita", ["mama", "madre", "hermana", "vieja", "abuela", "rica", "chupa",
                         "chupame", "lame", "lameme", "mojada", "meter", "meto", "peluda"],
     ["concha y toro", "concha acustica", "concha marina", "conchas marinas", "concha de mar"],
     []),
    ("cuca cuquita chocha chochito", ["rica", "chupa", "lame", "lameme", "mojada", "meter",
                                      "meto", "muestra", "muestrame"], [], []),
    ("huevos hueas bolas cocos", ["chupa", "chupame", "chupen", "chupar", "lame", "lameme",
                                  "lamer", "rasca", "rascame", "sobame", "soba", "mama", "mamame"],
     [], []),
    ("pene penes vagina vaginas clitoris testiculos senos pezones", VERBOS_SEXUALES,
     [], SALVO_EDUCACION),
    ("paja pajita", ["hacerse", "hacerte", "hacerme", "hacerle", "corrersela", "corrérsela",
                     "correrse", "correrte", "rusa"], ["paja de", "paja y", "techo de paja"], []),
    ("pete petes petazo", ["chupa", "chupame", "hazme", "mamada", "rico", "rica"], [], []),
    ("cacha cachita", ["echar", "echarse", "echarnos", "echemos", "rica", "rico", "contigo"],
     [], []),
    ("polvo polvito polvazo", ["echar", "echarse", "echarnos", "echemos", "eche", "rico",
                               "contigo", "tirar"],
     ["polvo de", "polvo en", "polvos de"], []),
    ("tirar tirarte tirarme tirarnos tiramos tiremos", ["contigo", "conmigo", "culo", "rico",
                                                        "rica", "sexo", "caliente", "cama",
                                                        "toda la noche", "duro", "condon"],
     [], []),
    ("coger cogerte cogerla cogerlo cogernos cogeme cogemos cogimos", ["contigo", "conmigo",
                                                                        "culo", "rico", "rica",
                                                                        "sexo", "caliente",
                                                                        "cama", "duro",
                                                                        "toda la noche"], [], []),
    ("sexo", ["busco", "buscamos", "quiero", "queremos", "tener", "tengamos", "casual", "gratis",
              "rico", "duro", "oral", "anal", "grupal", "contigo", "conmigo", "hot", "fotos",
              "video", "videos", "pack", "trio", "ahora", "hoy"], [], SALVO_EDUCACION),
    ("anal", ["sexo", "coger", "culiar", "culear", "meter", "rico", "duro", "porno", "video"], [],
     SALVO_EDUCACION),
    ("trio trios", ["sexual", "sexo", "cama", "caliente", "hot", "rico"], ["trio de"], []),
    ("desnuda desnudo desnudas desnudos", ["fotos", "foto", "video", "videos", "manda", "mandame",
                                           "pasa", "pasame", "vendo", "envia", "enviame", "pack",
                                           "quiero", "muestra", "muestrame"],
     [], ["arte", "dibujo", "pintura", "modelo", "escultura", "museo", "fotografia artistica"]),
    # «vendo pack» (fotos íntimas) sí; «vendo pack de apuntes» no
    ("pack packs", ["vendo", "venta", "compro", "pasa", "pasen", "manda", "mandame",
                    "intercambio"], ["pack de", "six pack"], []),
    ("pack packs", ["hot", "nudes", "caliente", "rico", "rica", "desnuda", "desnudo", "intimo",
                    "intimas", "intimos"], [], []),
    ("pornografia pornografica pornografico pornograficos", ["ver", "videos", "video", "vendo",
                                                             "gratis", "compartir", "pack",
                                                             "fotos", "mirar", "pasar"],
     [], SALVO_EDUCACION + ["adiccion", "efectos"]),
    ("prepago prepagos", ["chica", "chicas", "mina", "minas", "nena", "nenas", "servicio",
                          "servicios", "atencion", "atiendo", "contacto", "escort", "rica",
                          "caliente"], [], []),
    ("maraca maracas", ["eres", "esa", "esas", "vieja", "culia", "culiada", "puta", "sucia",
                        "barata", "mama", "hermana", "polola", "tu mama", "tu hermana"],
     ["tocar maracas", "toca maracas", "toca las maracas"], []),
    ("perra perras", ["eres", "maldita", "malditas", "puta", "sucia", "zorra", "hija de",
                      "culia", "culiada", "flaite", "callate", "conchetumare", "weona"], [], []),
    ("violar", ["te", "voy", "vamos", "quiero", "hay que", "merece", "merecen", "ojala"],
     ["violar la ley", "violar las reglas", "violar los derechos", "violar la norma",
      "violar el reglamento", "violar la privacidad", "violar la confianza"], []),
]

# --- Discriminación -----------------------------------------------------------

DESPRECIO = ["eres", "pareces", "tan", "weon", "culiao", "cara de", "callate", "puro", "pura",
             "por ser"]

GRUPOS = """
negros negras negro negra morenos peruanos peruanas peruano peruana bolivianos bolivianas
venezolanos venezolanas colombianos colombianas haitianos haitianas dominicanos dominicanas
argentinos argentinas ecuatorianos chinos chinas asiaticos migrantes inmigrantes extranjeros
extranjeras gays gay lesbianas lesbiana trans homosexuales homosexual bisexuales travestis
mapuches mapuche indigenas aymaras judios judias musulmanes evangelicos catolicos ateos
mujeres hombres gordos gordas gordo gorda discapacitados discapacitadas pobres viejos viejas
gitanos gitanas cholos mujer
"""
# Frases de rechazo u odio que, junto a un grupo, vuelven discriminatorio el texto
# ("no se aceptan peruanos", "odio a los gays"). Ojo: «solo para mujeres» NO está
# (un taller solo para mujeres es válido).
EXCLUSION = [
    "no se aceptan", "no aceptamos", "no queremos", "no se admiten", "no admitimos",
    "no pueden venir", "no pueden participar", "no pueden entrar", "no vengan",
    "prohibido el ingreso", "prohibida la entrada", "prohibido el paso", "solo chilenos",
    "mueran", "maten", "matemos", "matar a", "odio a", "odio los", "odio las", "odio al",
    "odiamos", "asco", "asquerosos", "asquerosas", "dan asco", "son basura", "son una basura",
    "son una plaga", "son plaga", "lacra", "lacras", "escoria", "infestado", "infestada",
    "devuelvanse", "vuelvan a su pais", "deporten", "deportar a", "expulsar a", "expulsen",
    "cochinos", "cochinas", "delincuentes", "ladrones", "exterminar", "erradicar",
]
SALVO_DEBATE = [
    "charla", "taller", "conversatorio", "seminario", "foro", "debate", "contra el", "contra la",
    "prevenir", "combatir", "discriminacion", "derechos", "inclusion", "diversidad",
    "prevencion", "violencia de genero", "xenofobia", "racismo", "homofobia",
]

REGLAS_DISCRIMINACION = [
    (GRUPOS, EXCLUSION, [], SALVO_DEBATE),
    ("hueco huecos", ["eres", "ese", "esos", "tan", "por", "puro", "weon", "culiao", "callate",
                      "maricon", "maraco", "te gusta"],
     ["un hueco en", "un hueco de", "hueco en", "hueco de", "huecos en"], []),
    ("roto rota rotos rotas", DESPRECIO + ["flaite", "cuma", "ese", "esa", "esos", "esas"],
     ["esta roto", "esta rota", "estan rotos", "se rompio"], []),
    ("cholo chola cholos cholas bolita bolitas", ["culiao", "culia", "de mierda", "cochino",
                                                  "cochina", "sucio", "sucia", "asqueroso",
                                                  "asquerosa", "eres un", "eres una",
                                                  "pareces"], [], []),
    ("indio india indios indias", DESPRECIO + ["salvaje", "salvajes", "pata rajada"],
     ["indio pacifico", "oceano indico"], []),
    ("macaco macacos simio simios mono monos", ["eres", "pareces", "negro", "negra", "negros",
                                                "callate", "cara de", "sucio"],
     ["mono de peluche", "monos animados"], []),
    ("retrasado retrasada retrasados retrasadas retardado retardada retardados retardadas",
     DESPRECIO + ["mental", "mentales"],
     ["vuelo retrasado", "bus retrasado", "pago retrasado", "esta retrasado", "va retrasado"], []),
    ("autista autistas", DESPRECIO,
     [], ["espectro", "tea", "inclusion", "neurodiversidad", "charla", "taller", "apoyo"]),
    ("down", DESPRECIO, ["sindrome de down"], []),
    ("mongolo mongola mongolos mongolas anormal anormales tullido tullidos", DESPRECIO, [], []),
    ("gonorrea gonorreas", ["eres", "ese", "esa", "tan", "malparido", "hijueputa", "parce",
                            "pirobo", "callate", "pedazo de", "que"], [], SALVO_EDUCACION),
    ("pinche pinches", ["wey", "guey", "pendejo", "pendeja", "cabron", "puto", "puta", "vieja",
                        "naco", "naca", "idiota", "mierda"], [], []),
    ("nazi nazis hitler", ["viva", "heil", "sieg", "orgullo", "soy", "somos", "raza", "blanca",
                           "superior", "mueran", "arriba", "tenia razon", "volvera", "88"],
     [], ["historia", "holocausto", "segunda guerra", "museo", "documental", "libro", "pelicula",
          "clase", "charla", "memoria"]),
    (["supremacia blanca"], [], [], ["historia", "charla", "clase", "libro", "documental",
                                     "contra", "racismo", "seminario"]),
]

# --- Drogas: se tapan junto a vender, comprar o consumir ----------------------
#
# Las palabras claramente de drogas van con muchos verbos (incluso «fiesta»);
# las que también tienen otro sentido (pito = silbato, coca = Coca-Cola, crack =
# buen jugador, hierba mate...) solo con verbos que no dejan dudas.

VERBOS_DROGA = [
    "vendo", "vende", "venden", "vendemos", "venta", "compro", "compra", "compramos", "comprar",
    "fumar", "fumemos", "fumamos", "fumo", "fumando", "fumarnos", "fumarse", "jalar", "jale",
    "jalamos", "jalemos", "jalando", "pegarse", "pegarnos", "pegamos", "pegate", "tomar",
    "tomarnos", "tomarse", "consumir", "consumamos", "probar", "probemos", "traigo", "traer",
    "traigan", "llevo", "lleven", "prender", "prendamos", "armar", "armemos", "volarse",
    "volarnos", "volaos", "volados", "volao", "drogarse", "drogarnos", "dealer", "gramo",
    "gramos", "delivery", "stock", "carrete", "fiesta",
]
VERBOS_FUMAR = [
    "fumar", "fumemos", "fumamos", "fumo", "fumando", "fumarse", "fumarnos", "prender",
    "prendamos", "prendemos", "armar", "armemos", "pegarse", "pegarnos", "volarse", "volarnos",
    "volao", "volados", "volaos", "vendo", "compro", "venta", "dealer", "gramo", "gramos",
    "papelillo", "papelillos", "moler", "pipa",
]
VERBOS_JALAR = [
    "jalar", "jale", "jalamos", "jalemos", "jalando", "jalarse", "jalarnos", "pase", "pases",
    "linea", "lineas", "gramo", "gramos", "dealer", "volao", "volados",
]
SALVO_PREVENCION = [
    "prevencion", "prevenir", "charla", "taller", "adiccion", "adicciones", "rehabilitacion",
    "tratamiento", "salud", "senda", "seminario", "conferencia", "investigacion", "estudio",
    "catedra", "ponencia", "dejar", "sin drogas", "no consumir", "libre de", "riesgos",
    "efectos", "farmacologia", "toxicologia", "legalizacion", "ley", "politicas", "debate",
    "medicinal", "medicinales",
]

REGLAS_DROGAS = [
    ("marihuana marihuanas mariguana marijuana cannabis cocaina mdma lsd ketamina keta "
     "metanfetamina ghb popper poppers", VERBOS_DROGA, [], SALVO_PREVENCION),
    ("pito pitos hierba weed porro porros cogollo cogollos faso fasos canuto canutos huiro hachis "
     "hash cripy creepy crack", VERBOS_FUMAR,
     ["hierba mate", "hierbas medicinales", "pito de", "un pito para"], SALVO_PREVENCION),
    ("coca perico merca", VERBOS_JALAR, ["coca cola", "hoja de coca", "hojas de coca"],
     SALVO_PREVENCION),
    ("extasis pepa pepas heroina", ["tomar", "tomarse", "tomarnos", "pegarse", "pegarnos",
                                    "inyectar", "inyectarse", "pincharse", "vendo", "compro",
                                    "dealer", "gramo", "gramos", "pastilla", "pastillas",
                                    "fumar", "jalar"],
     ["pepas de", "pepa de"], SALVO_PREVENCION),
    (["pasta base", "hongos alucinogenos", "hongos magicos", "hongo magico"], [], [],
     SALVO_PREVENCION),
    ("falopa tusi tussi tuci tripi tripis", [], [], SALVO_PREVENCION),  # casi siempre son drogas
    ("droga drogas", VERBOS_DROGA, [], SALVO_PREVENCION),
]

# --- Violencia ------------------------------------------------------------------

SALVO_JUEGO = ["juego", "juegos", "videojuego", "videojuegos", "zombie", "zombies", "zombis",
               "partida", "rol", "pelicula", "torneo", "gamer", "consola", "free fire", "fortnite",
               "counter", "lol"]

REGLAS_VIOLENCIA = [
    ("matar", ["te", "los", "las", "voy a", "vamos a", "hay que", "quiero", "merece", "merecen",
               "a todos", "a todas", "ojala"],
     ["matar el tiempo", "matar la sed", "matar el hambre", "matar zombies", "matar zombis",
      "matar dos pajaros", "matar la mosca", "matar ese control", "matar el control",
      "matar la prueba", "matar esa prueba", "matar el examen", "matar ese examen",
      "matar el certamen", "matar ese certamen", "matar la pega"], SALVO_JUEGO),
    ("matarte matarlos matarlas matarla matarlo", ["voy", "vamos", "hay que", "quiero", "ojala",
                                                   "deberian", "voy a", "te"], [], SALVO_JUEGO),
    ("balazo balazos balear baleo plomazo", ["te", "los", "las", "voy", "vamos", "pegar", "pego",
                                             "meter", "meto", "hay que", "ojala"], [], []),
    ("apuñalar apuñalarte apunalar apunalarte acuchillar acuchillarte cuchillazo", ["te", "los", "las", "voy",
                                                                 "vamos", "hay que", "ojala"],
     [], []),
]

REGLAS_BASE = REGLAS_SEXUALES + REGLAS_DISCRIMINACION + REGLAS_DROGAS + REGLAS_VIOLENCIA
