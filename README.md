# Join In

Página web para que los estudiantes de la **Universidad de Los Lagos** (Osorno)
publiquen avisos del tipo «nos falta gente» (un partido, un juego de mesa, un
grupo de estudio, una salida) y otros se sumen con un toque desde el celular o
el computador. Se entra una vez con el correo institucional
`@alumnos.ulagos.cl`. Hecha **solo en Python** con [NiceGUI](https://nicegui.io).

Se publica **gratis** con tres servicios:

| Servicio | Para qué | Costo |
|----------|----------|-------|
| **Render** (render.com) | Ejecuta la página y le da un enlace público `https://….onrender.com` | Gratis, sin tarjeta |
| **Neon** (neon.com) | Guarda los avisos (base de datos PostgreSQL) | Gratis, sin tarjeta y sin vencimiento |
| **Brevo** (brevo.com) | Envía el código de 6 dígitos para ingresar | Gratis hasta 300 correos al día |

> ¿Por qué dos? Render gratis borra sus archivos cada vez que la página se
> duerme, así que los avisos se guardan en Neon, que es permanente.

---

## Publicarla en internet (≈15 minutos, mejor desde un computador)

### Paso 1 — Base de datos en Neon

1. Entra a **neon.com** y crea una cuenta (puedes entrar con Google o GitHub).
2. Crea un proyecto:
   - Nombre: `falta-uno`
   - Región: **AWS US East 1 (N. Virginia)** (la misma zona que Render, así es más rápida)
3. En el panel del proyecto, toca **Connect** y copia la *connection string*.
   Empieza con `postgresql://` y termina con algo como `sslmode=require`.
   Guárdala: funciona como una contraseña, no la publiques.

### Paso 2 — Subir el código a GitHub

1. Crea una cuenta en **github.com**.
2. Toca **New repository** → nombre `falta-uno` → **Create repository**.
3. Toca **uploading an existing file** y arrastra **los archivos sueltos**
   (no la carpeta): `app.py`, `datos.py`, `acceso.py`, `filtro.py`,
   `lugares.py`, `requirements.txt`, `render.yaml` y `README.md`. Luego
   **Commit changes**.

   `render.yaml` tiene que quedar en la portada del repositorio, no dentro de
   otra carpeta.

### Paso 3 — Publicar en Render

1. Entra a **render.com** y crea una cuenta **con tu GitHub**.
2. Toca **New** → **Blueprint** y elige el repositorio `falta-uno`.
   Render lee `render.yaml` y ya sabe qué hacer (plan gratuito incluido).
3. Te pedirá **DATABASE_URL**: pega la connection string de Neon.
4. Toca **Deploy Blueprint** y espera unos 3 minutos.
5. Entra al servicio `falta-uno`: arriba aparece el enlace
   **`https://falta-uno-xxxx.onrender.com`**. Ese es el que compartes.

<details>
<summary>Si no te aparece la opción Blueprint</summary>

**New** → **Web Service** → elige el repositorio y completa:

- Language / Runtime: **Python 3**
- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`
- Instance Type: **Free**
- Environment Variables:
  - `DATABASE_URL` = la connection string de Neon
  - `PYTHON_VERSION` = `3.12.11`
</details>

### Paso 4 — La página duerme cuando nadie la usa

Render gratis **duerme la página si pasan 15 minutos sin visitas** y la
**despierta sola cuando alguien entra**. Ese primer ingreso tarda cerca de
1 minuto (Render muestra una pantalla de carga); después todo va normal.
Los avisos no se pierden: están guardados en Neon.

Así la página solo gasta horas gratis de Render mientras alguien la usa, y
queda espacio para otros proyectos en la misma cuenta. Una pestaña abierta
cuenta como alguien usándola, así que mientras haya una abierta, no se duerme.

**Si tenías un despertador en cron-job.org**, desactívalo: entra a
cron-job.org → tu cronjob de esta página → apágalo o bórralo. Si no, la seguirá
despertando cada 10 minutos.

<details>
<summary>¿Y si algún día quieres que no se duerma nunca?</summary>

En Render → servicio `falta-uno` → **Environment** → **Add Environment
Variable**: Key `DESPERTADOR`, Value `si` → **Save**. La página se visitará
sola cada 10 minutos (en **Logs** verás `[despertador] visita a /salud: 200`).
Para que tampoco se quede dormida tras un reinicio de Render, agrega además un
cronjob en cron-job.org a `https://TU-ENLACE.onrender.com/salud` cada 10
minutos (no uses `/robots.txt`: Render responde esa ruta sin despertarla).

Ojo: Render regala 750 horas al mes por cuenta y un mes tiene hasta 744, así
que una página despierta todo el mes las ocupa casi todas.
</details>

La dirección `/salud` no consulta la base de datos, así que si enciendes el
despertador, sus visitas no gastan las horas gratis de Neon. Además, la página guarda
los avisos en memoria y solo vuelve a leer la base de datos cuando alguien
publica o se une.

### Paso 5 — Envío de los códigos por correo (Brevo)

Para entrar, cada estudiante escribe su correo `@alumnos.ulagos.cl` y recibe
un código de 6 dígitos. Render gratis no deja enviar correos por SMTP, así que
la página usa la API de **Brevo** (por internet, como una página más).

**Mientras no lo configures, la página funciona en modo de prueba:** el
código aparece en pantalla, con el aviso «Modo de prueba», en vez de llegar
al correo. Sirve para mostrarla, pero así cualquiera podría entrar con un
correo ajeno: configúralo antes de abrirla a todos.

1. Crea una cuenta gratis en **brevo.com**.
2. **Remitente:** menú de tu cuenta → **Senders, Domains & Dedicated IPs** →
   **Senders** → **Add a sender**. Nombre: `Join In`; correo: uno tuyo (por
   ejemplo tu Gmail). Brevo te manda un código a ese correo para verificarlo.
3. **Clave de la API:** menú de tu cuenta → **SMTP & API** → **API keys** →
   **Generate a new API key** → nombre `join-in` → copia la clave (empieza
   con `xkeysib-`; Brevo la muestra una sola vez). **No la publiques ni la
   mandes por chat:** funciona como una contraseña.
4. **IP de Render:** Brevo bloquea las llamadas desde direcciones IP que no
   conoce. En Render, abre el servicio → **Connect** (arriba a la derecha) →
   pestaña **Outbound** y copia las direcciones. En Brevo → menú de tu cuenta →
   **Security** → **Authorized IPs** → **Authorize IP address** y agrégalas
   (formato *IPv4 range* si vienen con `/`). Si prefieres no hacerlo, en esa
   misma pantalla puedes usar **Deactivate** en la fila **API keys**.
5. En Render → servicio `falta-uno` → **Environment** → **Add Environment
   Variable**, crea dos:
   - `BREVO_API_KEY` = la clave del punto 3
   - `CORREO_REMITENTE` = el correo que verificaste en el punto 2
6. **Save Changes**. Render reinicia la página y desde ahí los códigos llegan
   por correo (el aviso «Modo de prueba» desaparece).

Si en **Logs** aparece `[acceso] Brevo respondió 401`, revisa la clave o el
punto 4; si dice `400`, el remitente no está verificado. Con un remitente
Gmail, Brevo puede cambiar la dirección que se ve y algunos códigos pueden
llegar a **spam** (la página lo advierte); con un dominio propio llegan mejor.

### Paso 6 — Activar tu panel de administración

El panel está en `https://TU-ENLACE.onrender.com/admin`. No aparece en
ningún botón de la página y pide una clave que solo tú conoces.

1. En Render, entra al servicio `falta-uno` → **Environment** →
   **Add Environment Variable**.
2. Key: `CLAVE_ADMIN` · Value: una clave larga que no uses en otro lado
   (por ejemplo, 4 o 5 palabras al azar: `tetera-volcan-azul-mesa-73`).
3. Toca **Save Changes**. Render reinicia la página solo (1 a 3 minutos).
4. Abre `/admin`, escribe la clave y toca **Entrar**. No hace falta haber
   ingresado antes con tu correo: si ya ingresaste, tu cuenta queda como
   administradora; si no, ese navegador. Queda así hasta que toques
   **Cerrar sesión de administración**.

Como `/admin` no exige ingresar con el correo, la administración puede
entrar aunque su propio correo esté en uso en otro navegador, y liberarlo
desde el panel (pestaña **Correos**, con la X junto a cada correo).

La clave nunca se guarda en el código ni en GitHub. Si alguien se equivoca
de clave 5 veces, esa conexión queda bloqueada 15 minutos. Si cambias la
clave, usa **Cerrar la sesión de administración en todos los navegadores**.

Qué hay en el panel:

- **Resumen:** avisos abiertos, publicados, personas unidas, bloqueos,
  avisos eliminados, denuncias por revisar y estudiantes registrados.
- **Denuncias:** los avisos que la gente denunció, con los motivos y
  comentarios. Puedes **eliminar el aviso** o **descartar las denuncias**.
  Con 3 denuncias de personas distintas, el aviso se oculta del tablero
  hasta que lo revises.
- **Palabras:** agrega palabras o frases al filtro **al instante**, sin
  volver a publicar el código. Cada una se filtra *siempre* o *solo en
  contexto inadecuado*: cuando aparece cerca (hasta 3 palabras) de alguna de
  sus palabras de contexto, y nunca dentro de sus excepciones. Ejemplo:
  «pico» con contexto «chupen, mi» y excepciones «y pico, pico de»: bloquea
  "mi pico" pero no "a las 5 y pico" ni "el pico de la montaña". Incluye un
  **probador** para ver si un texto se bloquearía, y la lista base completa.
- **Bloqueados:** lo que el filtro no dejó publicar (fecha, campo, texto y
  palabra detectada). Se guarda 30 días.
- **Avisos:** los últimos 60 avisos, abiertos o no, con la opción de
  eliminar cualquiera. Quienes se habían unido lo ven en su buzón como
  "Cancelado por la administración".
- **Correos:** la lista de correos en uso, con el nombre y el último uso, y
  un buscador. La **X** junto a cada correo lo libera (pregunta antes): se
  cierra su sesión y esa persona puede volver a entrar desde otro navegador
  con un código nuevo. Su cuenta y sus avisos no se borran.

### Paso 7 — Mapa con estilo moderno (recomendado)

Los mapas usan el estilo **Voyager de CARTO** (colores suaves, calles claras
y nítido en celulares) si existe la variable `CARTO_KEY`. Sin ella se usa el
mapa estándar de OpenStreetMap con los colores suavizados: funciona igual,
pero se ve más anticuado y algo borroso en pantallas de celular.

1. Pide una clave gratis en **carto.com/basemaps/apikey**: llega por correo
   al instante y no necesitas crear cuenta. Gratis hasta 5 millones de
   solicitudes de mapa al mes.
2. En Render → servicio `falta-uno` → **Environment** → **Edit** →
   **Add Environment Variable**: Key `CARTO_KEY`, Value: la clave → **Save**.

El crédito «© OpenStreetMap contributors, © CARTO» se muestra en el mapa,
como piden sus condiciones.

### Hacer cambios después

Edita un archivo en GitHub (o súbelo de nuevo) y Render publica la versión
nueva solo, en un par de minutos. Los avisos no se pierden.

---

## Cómo funciona

0. **Ingresar (una sola vez):** se escribe el correo `@alumnos.ulagos.cl`,
   llega un código de 6 dígitos (vale 10 minutos, 5 intentos) y se escribe
   el nombre que verán los demás. El correo **nunca se muestra**. No hay
   contraseña. Desde ese navegador se entra directo durante un año, sin
   volver a pedir código.
   - **Un correo, un navegador:** si otra persona intenta entrar con un
     correo que ya está en uso en otro navegador, la página le avisa que
     **el correo ya está en uso** y no le envía el código.
   - **Para cambiar de navegador,** se toca el botón con las iniciales
     (arriba a la derecha) → **Cerrar sesión**, y se entra desde el nuevo.
   - **Si se perdió el navegador** (celular nuevo, cookies borradas o una
     ventana de incógnito que se cerró), la administración **libera el
     correo** desde `/admin` → **Correos**: ahí ve los correos en uso y
     toca la **X** del que quiere liberar. Por eso la
     página pide no ingresar en incógnito.
   - Si alguien comparte el enlace de un aviso, quien lo abre ingresa y
     vuelve directo a ese aviso.
1. Toca el botón **+** y completa el aviso: título, categoría, lugar, fecha,
   hora, cuántos son, cuántos necesitan, detalles y si dura **24 o 48 horas**.
   El aviso muestra «Organiza» con tu nombre registrado.
   - **Lugar:** se escribe el nombre (ej. «Cancha del liceo»). Opcional:
     **Marcar en el mapa** abre un selector a pantalla completa, como en las
     apps de delivery: el pin queda fijo al centro y se mueve el mapa debajo
     (o se toca un punto). Arriba hay un buscador de lugares de Osorno (con
     ícono y tipo: cancha, café, parque…) y abajo a la derecha, **mi
     ubicación** y el zoom. Se confirma con **Usar este punto**. El formulario
     muestra una vista previa con la dirección aproximada; si «Lugar» estaba
     vacío, se escribe solo. El mapa no deja irse a otras regiones, y «Cómo
     llegar» lleva directo al punto.
   - **Valor por persona:** «Gratis ($0)» o «Tiene costo». El monto solo
     acepta números en pesos (2000 o 2.000), muestra cómo se verá
     («$2.000 por persona») y tiene un tope de **$80.000**.
2. El aviso aparece para todos en el tablero. Las páginas abiertas se
   actualizan solas.
3. Otra persona toca **Unirme** y queda anotada con su nombre registrado:
   **un solo toque**. Ve el resumen completo (lugar, hora, detalles) y el
   evento se guarda en su **buzón**. Si tocó por error, **Deshacer**.
4. En el **tablero**, el aviso desaparece cuando se completan los cupos,
   cuando termina su plazo de 24/48 h o cuando llega la hora del evento.
5. El botón **Buzón** (arriba a la derecha, con un contador) abre `/buzon`:
   - **Me uní:** los eventos a los que te uniste, con todos los detalles.
     Se quitan solos 3 horas después de que empieza cada evento.
   - **Mis avisos:** los que publicaste, con quiénes se unieron. Siguen ahí
     **aunque se llenen**, hasta que termina su plazo de 24 o 48 horas.
6. Quien se unió puede tocar **Salirme del evento** (en el tablero, en la
   página del aviso o en su buzón) hasta que empieza el evento. Su cupo queda
   libre y, si el aviso sigue dentro de su plazo, **vuelve a aparecer en el
   tablero** para que otra persona lo tome.
7. Quien publicó un aviso puede **eliminarlo** (botón «Eliminar aviso» en el
   tablero, en su buzón, en la página del aviso y justo después de publicarlo).
   Sale del tablero y de su buzón. A quienes ya se habían unido les queda en
   el buzón marcado como **Cancelado**, para que se enteren, con un botón para
   quitarlo.
8. Cada aviso tiene su propia página (`/aviso/<número>`) para compartir el
   enlace por WhatsApp. Al publicar se muestra ese enlace.
   - **📍 Cómo llegar:** abre las indicaciones de Google Maps hasta el lugar
     (en el celular, en la app). Si el aviso tiene el punto marcado, la página
     del aviso también muestra un mapa.
   - **💬 Comentarios:** preguntas cortas como "¿se paga la cancha?" (hasta
     200 caracteres, con el filtro de palabras). Cada uno puede borrar los
     suyos; la administración, cualquiera.
   - **🚩 Denunciar:** quien vea un aviso inapropiado lo puede denunciar una
     vez, eligiendo un motivo. Le llega a la administración.
9. **Filtro de palabras inapropiadas** (`filtro.py`): si el título, el lugar,
   los detalles, un comentario o el nombre (al registrarse) tienen groserías,
   insultos u ofensas, el campo se
   marca en rojo mientras se escribe y al publicar se dice exactamente qué
   palabra cambiar; no se publica hasta corregirla. Detecta trucos como
   `w3on`, `p.u.t.a`, `weooon` o `ctm`, y cuida no tachar palabras normales
   como "película", "Vergara" o "Putaendo". Si algo antiguo quedó guardado con
   una de esas palabras, se muestra sin ella. Ningún filtro es perfecto: puedes
   agregar palabras al instante (y con contexto) desde el panel `/admin`, o
   cambiar la lista base al comienzo de `filtro.py`.

**¿Cómo sabe la página quién es quién?** A cada navegador le da un
identificador al azar en una cookie. Al ingresar con el código, ese navegador
queda unido a la cuenta del estudiante. Por eso el buzón va con el correo: si
cierra sesión y entra desde otro navegador, lo encuentra igual. Lo que un navegador había hecho
antes de que existiera el ingreso (avisos, uniones, comentarios) pasa a la
cuenta la primera vez que entra.

Si dos personas tocan «Unirme» al mismo tiempo por el último cupo, solo una lo
consigue (la base de datos bloquea el aviso mientras anota a cada persona).
Tampoco se puede unir dos veces la misma persona, ni quien publicó el aviso.

---

## Probar cambios en tu computador (opcional)

Con Python 3.10 o superior:

```bash
pip install -r requirements.txt
python app.py
```

Se abre `http://localhost:8080`. Sin `DATABASE_URL`, los datos se guardan
en un archivo local `avisos.db`, aparte de los de internet. Sin
`BREVO_API_KEY`, el código para ingresar aparece en pantalla (modo de prueba).

## Archivos

Cada archivo tiene una de las clases del diagrama del informe, con una sola
instancia que usa la página:

| Archivo            | Clase | Qué tiene |
|--------------------|-------|-----------|
| `app.py`           | `Interfaz` | Las páginas, tarjetas y formularios. Aquí se cambia el diseño. |
| `acceso.py`        | `Acceso` | Ingreso con correo institucional: código, nombre y sesiones (máx. 2). |
| `datos.py`         | `GestorAvisos`, `Administracion` | Las reglas (cupos, plazos, validaciones), el panel /admin y la base de datos. |
| `filtro.py`        | `FiltroPalabras` | El filtro de palabras inapropiadas y sus listas. |
| `lugares.py`       | `BuscadorLugares` | El buscador de lugares de Osorno (OpenStreetMap: Photon y Nominatim). |
| `requirements.txt` | Las librerías que instala Render. |
| `render.yaml`      | Las instrucciones para que Render publique la página gratis. |

Ajustes rápidos: zona horaria (`ZONA_HORARIA`) y categorías (`CATEGORIAS`) en
`datos.py`; colores (`COLOR_PRINCIPAL`, `TINTA`, `AMARILLO`, `FONDO`, y uno por
categoría en `COLORES`), íconos (`ICONOS`) y toda la apariencia (`ESTILOS`, que
se adapta sola a celular y computador) en `app.py`;
ciudad del mapa y del buscador (`NOMBRE_ZONA`, `CENTRO`, `ZONA`) en `lugares.py`.

## Sobre el buscador de lugares

Usa servicios gratuitos de OpenStreetMap, sin claves: **Photon**
(photon.komoot.io) y, si falla, **Nominatim** (nominatim.openstreetmap.org).
Nominatim tiene una política de uso que hay que respetar
(https://operations.osmfoundation.org/policies/nominatim/): solo búsquedas
que la persona pide (no autocompletar), máximo 1 por segundo, identificarse y
dar crédito a OpenStreetMap. `lugares.py` lo cumple: consulta solo al tocar
«Buscar» o al tocar el mapa (y en ese caso espera a que la persona deje de
tocar), espera 1 segundo entre consultas, recuerda lo ya consultado y muestra
«© OpenStreetMap». Sirve para un uso moderado; con muchísimos usuarios
habría que usar un servicio propio o de pago.

**Solo Osorno:** los servicios reciben el recuadro de Osorno (en Nominatim con
`viewbox` + `bounded=1`, que limita los resultados a ese recuadro) y además se
descarta cualquier resultado que caiga fuera. El mapa tiene `maxBounds` y un
zoom mínimo, así que no se puede arrastrar ni alejar a otras regiones. Para
cambiar de ciudad basta con editar `CENTRO` y `ZONA` en `lugares.py`.
