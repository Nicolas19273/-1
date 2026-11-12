# Falta Uno ⚽

Página web para publicar avisos del tipo «nos falta gente» (un partido, un juego
de mesa, una salida) y que cualquier persona se una desde su celular o
computador, con WiFi o con datos. Hecha **solo en Python** con
[NiceGUI](https://nicegui.io).

Se publica **gratis** con dos servicios:

| Servicio | Para qué | Costo |
|----------|----------|-------|
| **Render** (render.com) | Ejecuta la página y le da un enlace público `https://….onrender.com` | Gratis, sin tarjeta |
| **Neon** (neon.com) | Guarda los avisos (base de datos PostgreSQL) | Gratis, sin tarjeta y sin vencimiento |

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
   (no la carpeta): `app.py`, `datos.py`, `requirements.txt`, `render.yaml`
   y `README.md`. Luego **Commit changes**.

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

### Paso 4 — Que la página no se duerma

Render gratis **duerme la página si pasan 15 minutos sin visitas**, y
despertarla toma cerca de 1 minuto. Para evitarlo hay dos capas:

1. **Automática (ya viene en `app.py`):** mientras está despierta, la página
   se visita sola cada 10 minutos. No tienes que hacer nada.
2. **Despertador externo (hazlo una vez, 3 minutos):** si por algo Render la
   duerme igual (un reinicio o mantenimiento), la capa 1 no puede despertarla,
   porque la página ya está dormida. Para eso:
   - Crea una cuenta gratis en **cron-job.org**.
   - Toca **Create cronjob**.
   - Title: `Falta Uno`
   - URL: `https://TU-ENLACE.onrender.com/salud` (tu enlace + `/salud`)
   - Execution schedule: **Every 10 minutes**
   - Guarda con **Create**.

   No uses `/robots.txt` como dirección: cuando la página está dormida,
   Render responde esa ruta por su cuenta y no la despierta.

Para comprobar que funciona: en Render, abre el servicio → **Logs**. Cada 10
minutos debería aparecer `[despertador] visita a /salud: 200`.

**Importante:** Render regala 750 horas al mes por cuenta, y un mes tiene
hasta 744. Alcanzan para **una** página despierta todo el mes, así que no
crees otros servicios gratis en la misma cuenta de Render. Si se acaban las
horas, Render apaga la página hasta el mes siguiente.

La dirección `/salud` no consulta la base de datos, así que las visitas del
despertador tampoco gastan las horas gratis de Neon. Además, la página guarda
los avisos en memoria y solo vuelve a leer la base de datos cuando alguien
publica o se une.

### Paso 5 — Activar tu panel de administración

El panel está en `https://TU-ENLACE.onrender.com/admin`. No aparece en
ningún botón de la página y pide una clave que solo tú conoces.

1. En Render, entra al servicio `falta-uno` → **Environment** →
   **Add Environment Variable**.
2. Key: `CLAVE_ADMIN` · Value: una clave larga que no uses en otro lado
   (por ejemplo, 4 o 5 palabras al azar: `tetera-volcan-azul-mesa-73`).
3. Toca **Save Changes**. Render reinicia la página solo (1 a 3 minutos).
4. Abre `/admin`, escribe la clave y toca **Entrar**. Ese navegador queda
   como administrador hasta que toques **Cerrar sesión de administración**.

La clave nunca se guarda en el código ni en GitHub. Si alguien se equivoca
de clave 5 veces, esa conexión queda bloqueada 15 minutos. Si cambias la
clave, usa **Cerrar la sesión de administración en todos los navegadores**.

Qué hay en el panel:

- **Resumen:** avisos abiertos, publicados, personas unidas, bloqueos,
  avisos eliminados y denuncias por revisar.
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

### Paso 6 — Mapa con estilo moderno (recomendado)

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

1. Toca el botón **+** y completa el aviso: título, categoría, lugar, fecha,
   hora, cuántos son, cuántos necesitan, detalles y si dura **24 o 48 horas**.
   Quien publica **no necesita escribir su nombre**.
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
3. Otra persona toca **Unirme**, escribe su nombre y queda anotada. Al
   confirmar ve el resumen completo (lugar, hora, detalles) y el evento se
   guarda en su **buzón**. La próxima vez su nombre ya aparece escrito.
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
   los detalles o el nombre tienen groserías, insultos u ofensas, el campo se
   marca en rojo mientras se escribe y al publicar se dice exactamente qué
   palabra cambiar; no se publica hasta corregirla. Detecta trucos como
   `w3on`, `p.u.t.a`, `weooon` o `ctm`, y cuida no tachar palabras normales
   como "película", "Vergara" o "Putaendo". Si algo antiguo quedó guardado con
   una de esas palabras, se muestra sin ella. Ningún filtro es perfecto: puedes
   agregar palabras al instante (y con contexto) desde el panel `/admin`, o
   cambiar la lista base al comienzo de `filtro.py`.

**¿Cómo sabe la página quién es quién, sin cuentas?** A cada navegador le da
un identificador al azar guardado en una cookie que dura un año. Por eso el
buzón es de *ese* navegador: si alguien entra desde otro teléfono, en modo
incógnito o borra las cookies, empieza con un buzón vacío.

Si dos personas tocan «Unirme» al mismo tiempo por el último cupo, solo una lo
consigue (la base de datos bloquea el aviso mientras anota a cada persona).
Tampoco se puede unir dos veces el mismo navegador, ni quien publicó el aviso.

---

## Probar cambios en tu computador (opcional)

Con Python 3.10 o superior:

```bash
pip install -r requirements.txt
python app.py
```

Se abre `http://localhost:8080`. Sin `DATABASE_URL`, los datos se guardan
en un archivo local `avisos.db`, aparte de los de internet.

## Archivos

| Archivo            | Qué tiene |
|--------------------|-----------|
| `app.py`           | La interfaz: páginas, tarjetas, formularios. Aquí se cambia el diseño. |
| `datos.py`         | Las reglas (cupos, plazos, validaciones) y la base de datos. |
| `filtro.py`        | El filtro de palabras inapropiadas y sus listas. |
| `lugares.py`       | El buscador de lugares de Osorno (OpenStreetMap: Photon y Nominatim). |
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
