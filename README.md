# Join In

**App de Android** para que los estudiantes de la **Universidad de Los Lagos**
(Osorno) publiquen avisos del tipo «nos falta gente» (un partido, un juego de
mesa, un grupo de estudio, una salida) y otros se sumen con un toque. Se entra
una vez con el correo institucional `@alumnos.ulagos.cl`.

Hecha **completa en Python**: la app con [Flet](https://flet.dev) y el
servidor con Starlette.

**Descargar la app:**
**https://github.com/Nicolas19273/-1/releases/latest/download/join-in.apk**
(siempre baja la versión más nueva; para celulares antiguos hay una versión de
32 bits en Releases; más detalles en `app_movil/README.md`).

Funciona **gratis** con estos servicios:

| Servicio | Para qué | Costo |
|----------|----------|-------|
| **GitHub** (github.com) | Guarda el código, prueba todo y arma el APK de la app | Gratis |
| **Render** (render.com) | Ejecuta el servidor al que se conecta la app (`https://falta-uno.onrender.com`) | Gratis, sin tarjeta |
| **Neon** (neon.com) | Guarda los avisos (base de datos PostgreSQL) | Gratis, sin tarjeta y sin vencimiento |
| **Brevo** (brevo.com) | Envía el código de 6 dígitos para ingresar | Gratis hasta 300 correos al día |

> ¿Por qué Render y Neon? Render gratis borra sus archivos cada vez que el
> servidor se duerme, así que los avisos se guardan en Neon, que es permanente.

---

## Cómo está armado

```
Celular (app Join In, Python + Flet)
   │  pedidos HTTPS con JSON, con el token del celular
   ▼
Render: app.py (API)  ──►  acceso.py · datos.py · filtro.py · lugares.py
                                │
                                ▼
                         Neon (PostgreSQL)
```

- La **app** (`app_movil/`) dibuja las pantallas y le pide todo al servidor.
  La primera vez crea un **token al azar** y lo guarda en el celular: así el
  servidor sabe que es el mismo celular (como una cookie, pero de la app).
- El **servidor** (`app.py`) ya no muestra páginas: responde en JSON en
  `/api/...`. Si alguien abre el enlace antiguo en el navegador, ve dónde
  descargar la app.
- Cada vez que se sube un cambio a GitHub, **GitHub Actions** prueba el
  servidor y la app, arma el APK y lo publica en **Releases**
  (`.github/workflows/app.yml`). Render publica el servidor nuevo solo.

---

## Publicar el servidor (≈15 minutos, mejor desde un computador)

### Paso 1 — Base de datos en Neon

1. Entra a **neon.com** y crea una cuenta (puedes entrar con Google o GitHub).
2. Crea un proyecto:
   - Nombre: `falta-uno`
   - Región: **AWS US East 1 (N. Virginia)** (la misma zona que Render, así es más rápida)
3. En el panel del proyecto, toca **Connect** y copia la *connection string*.
   Empieza con `postgresql://` y termina con algo como `sslmode=require`.
   Guárdala: funciona como una contraseña, no la publiques.

### Paso 2 — Publicar en Render

1. Entra a **render.com** y crea una cuenta **con tu GitHub**.
2. Toca **New** → **Blueprint** y elige este repositorio.
   Render lee `render.yaml` y ya sabe qué hacer (plan gratuito incluido).
3. Te pedirá **DATABASE_URL**: pega la connection string de Neon.
4. Toca **Deploy Blueprint** y espera unos 3 minutos.
5. El servidor queda en `https://falta-uno.onrender.com` (es la dirección que
   usa la app, en `app_movil/src/joinin/cliente.py`).

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

### Paso 3 — El servidor duerme cuando nadie lo usa

Render gratis **duerme el servidor si pasan 15 minutos sin uso** y lo
**despierta solo** con el primer pedido. Por eso, la primera vez del día la
app muestra «Conectando con Join In…» hasta un minuto; después va normal. Los
avisos no se pierden: están en Neon. Mientras la app está abierta, se
actualiza cada 20 segundos, así que el servidor no se duerme.

<details>
<summary>¿Y si quieres que no se duerma nunca?</summary>

En Render → servicio `falta-uno` → **Environment** → **Add Environment
Variable**: Key `DESPERTADOR`, Value `si` → **Save**. El servidor se visitará
solo cada 10 minutos (en **Logs** verás `[despertador] visita a /salud: 200`).
Para que tampoco se quede dormido tras un reinicio de Render, agrega además un
cronjob en cron-job.org a `https://falta-uno.onrender.com/salud` cada 10
minutos.

Ojo: Render regala 750 horas al mes por cuenta y un mes tiene hasta 744, así
que un servidor despierto todo el mes las ocupa casi todas.
</details>

`/salud` no consulta la base de datos, así que esas visitas no gastan las
horas gratis de Neon. El servidor además guarda los avisos en memoria y solo
vuelve a leer la base de datos cuando alguien publica o se une.

### Paso 4 — Envío de los códigos por correo (Brevo)

Para entrar, cada estudiante escribe su correo `@alumnos.ulagos.cl` y recibe
un código de 6 dígitos. Render gratis no deja enviar correos por SMTP, así que
el servidor usa la API de **Brevo**.

**Mientras no lo configures, todo funciona en modo de prueba:** la app
muestra el código en pantalla, con el aviso «Modo de prueba», en vez de
enviarlo al correo. Sirve para mostrarla, pero así cualquiera podría entrar
con un correo ajeno: configúralo antes de abrirla a todos.

1. Crea una cuenta gratis en **brevo.com**.
2. **Remitente:** menú de tu cuenta → **Senders, Domains & Dedicated IPs** →
   **Senders** → **Add a sender**. Nombre: `Join In`; correo: uno tuyo.
   Brevo te manda un código a ese correo para verificarlo.
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
6. **Save Changes**. Render reinicia el servidor y desde ahí los códigos
   llegan por correo (el aviso «Modo de prueba» desaparece de la app).

Si en **Logs** aparece `[acceso] Brevo respondió 401`, revisa la clave o el
punto 4; si dice `400`, el remitente no está verificado. Con un remitente
Gmail algunos códigos pueden llegar a **spam**; con un dominio propio llegan
mejor.

### Paso 5 — Activar la administración

1. En Render, entra al servicio `falta-uno` → **Environment** →
   **Add Environment Variable**.
2. Key: `CLAVE_ADMIN` · Value: una clave larga que no uses en otro lado
   (por ejemplo, 4 o 5 palabras al azar).
3. Toca **Save Changes**. Render reinicia el servidor solo (1 a 3 minutos).
4. En la app, toca **Administración** (abajo en la pantalla de ingreso, o en
   el menú de tu cuenta, arriba a la derecha del tablero), escribe la clave y
   toca **Entrar**. No hace falta haber ingresado con tu correo: si ya
   ingresaste, tu cuenta queda como administradora; si no, ese celular. Queda
   así hasta que toques **Salir de administración**.

Como la administración no exige ingresar con el correo, puedes entrar aunque
tu propio correo esté en uso en otro celular, y liberarlo desde **Correos en
uso**.

La clave nunca se guarda en el código ni en GitHub. Si alguien se equivoca
de clave 5 veces, queda bloqueado 15 minutos. Si cambias la clave, usa
**Cerrar la administración en todos los celulares**.

Qué hay en la administración:

- **Cifras:** avisos abiertos, publicados, personas unidas, bloqueos,
  avisos eliminados y avisos con denuncias (últimos 7 días), más el total de
  avisos y de estudiantes registrados.
- **Denuncias:** los avisos que la gente denunció, con los motivos y
  comentarios. Puedes **eliminar el aviso** o **descartar las denuncias**.
  Con 3 denuncias de personas distintas, el aviso se oculta del tablero
  hasta que lo revises.
- **Palabras del filtro:** agrega palabras o frases al filtro **al instante**.
  Cada una se filtra *siempre* o *solo en contexto inadecuado*: cuando
  aparece cerca (hasta 3 palabras) de alguna de sus palabras de contexto, y
  nunca dentro de sus excepciones. Ejemplo: «pico» con contexto «chupen, mi»
  y excepciones «y pico, pico de»: bloquea "mi pico" pero no "a las 5 y pico".
  Incluye un **probador** para ver si un texto se bloquearía.
- **Bloqueados:** lo que el filtro no dejó publicar (fecha, campo, texto y
  palabra detectada). Se guarda 30 días.
- **Todos los avisos:** del más nuevo al más antiguo, con filtros (abiertos,
  eliminados, terminados):
  - **Eliminar** (solo los abiertos): sale del tablero y quienes se habían
    unido lo ven en su buzón como "Cancelado por la administración".
  - **Borrar para siempre** (cualquiera): se quita de la base de datos con
    sus inscritos, comentarios y denuncias, sin dejar rastro.
  - **Borrar todos los avisos** deja el tablero vacío; pide escribir
    BORRAR para confirmar. Los estudiantes y sus correos no se tocan.
- **Correos en uso:** la lista de correos con el nombre y el último uso, y un
  buscador. La **X** junto a cada correo lo libera (pregunta antes): se
  cierra su sesión y esa persona puede volver a entrar desde otro celular con
  un código nuevo. Su cuenta y sus avisos no se borran.

### Paso 6 — Firma del APK (recomendado)

Para que cada versión nueva de la app se instale **encima** de la anterior
(sin desinstalar), todos los APK tienen que ir firmados con la misma clave.
Se guardan dos secretos en GitHub → este repositorio → **Settings** →
**Secrets and variables** → **Actions** → **New repository secret**:
`ANDROID_KEYSTORE_BASE64` y `ANDROID_KEYSTORE_PASSWORD`. Sin ellos el APK se
arma igual, pero con una clave distinta cada vez. Detalles en
`app_movil/README.md`.

### Hacer cambios después

Edita un archivo en GitHub (o súbelo de nuevo). Render publica el servidor
nuevo solo y GitHub Actions arma y publica un APK nuevo en unos 15 minutos.
Los avisos no se pierden.

---

## Cómo funciona la app

0. **Ingresar (una sola vez):** se escribe el correo `@alumnos.ulagos.cl`,
   llega un código de 6 dígitos (vale 10 minutos, 5 intentos) y, la primera
   vez, se escribe el nombre que verán los demás. El correo **nunca se
   muestra**. No hay contraseña. Después, ese celular entra directo.
   - **Un correo, un celular:** si alguien intenta entrar con un correo que
     ya está en uso en otro celular, la app le avisa que **el correo ya está
     en uso** y no le envía el código.
   - **Para cambiar de celular,** se toca el ícono de la cuenta (arriba a la
     derecha del tablero) → **Cerrar sesión**, y se entra desde el nuevo.
   - **Si se perdió el celular** (o se desinstaló la app), la administración
     **libera el correo** desde **Correos en uso**.
1. **Tablero:** los avisos abiertos, con filtros por categoría (se deslizan
   de lado). Cada tarjeta muestra la categoría, el valor, cuándo, dónde,
   cuántos faltan (con una barra de cupos) y cuánto le queda abierto. Se
   actualiza solo cada 20 segundos, o al deslizar la pantalla hacia abajo.
   Si hay una versión nueva de la app, el tablero lo avisa con un botón para
   descargarla (la versión instalada aparece en el menú de la cuenta).
2. **Crear aviso** (botón amarillo): categoría, título, cuántos son y cuántos
   necesitan en total (con vista previa de los cupos), lugar, fecha y hora,
   valor por persona y si el aviso dura **24 o 48 horas**.
   - **Lugar:** se escribe el nombre (ej. «Cancha del liceo»). Opcional:
     **Buscar el lugar en el mapa** busca canchas, plazas o calles de Osorno
     y guarda el punto exacto para el botón «Cómo llegar».
   - **Valor por persona:** «Gratis ($0)» o «Tiene costo». El monto solo
     acepta números en pesos (2000 o 2.000), muestra cómo se verá
     («$2.000 por persona») y tiene un tope de **$80.000**.
   - El aviso muestra «Organiza» con tu nombre registrado.
3. **El aviso:** datos, cupos, quiénes se unieron y detalles.
   - **Unirme** anota con un toque; **Salirme** libera el cupo hasta que
     empieza el evento (si el aviso sigue en plazo, vuelve al tablero).
   - **Cómo llegar** abre Google Maps con las indicaciones.
   - **Invitar** (o el ícono de compartir) abre el menú del celular para
     mandar el aviso por WhatsApp u otra app, con el enlace para bajar Join In.
     Al publicar un aviso también aparece **Compartir**.
   - **Comentarios:** preguntas cortas como "¿se paga la cancha?" (con el
     filtro de palabras). Cada uno puede borrar los suyos; la
     administración, cualquiera.
   - **Denunciar:** quien vea un aviso inapropiado lo puede denunciar una
     vez, eligiendo un motivo. Le llega a la administración.
   - Quien lo publicó puede **eliminarlo**: sale del tablero y a quienes se
     habían unido les queda en el buzón como **Cancelado**.
4. En el **tablero**, el aviso desaparece cuando se completan los cupos,
   cuando termina su plazo de 24/48 h o cuando llega la hora del evento.
5. **Mi buzón** (ícono arriba a la derecha):
   - **Me uní:** los eventos a los que te uniste y cómo van. Se quitan solos
     3 horas después de que empieza cada evento.
   - **Organizo:** los que publicaste, con quiénes se unieron. Siguen ahí
     **aunque se llenen**, hasta que termina su plazo de 24 o 48 horas.
6. **Filtro de palabras inapropiadas** (`filtro.py`): si el título, el lugar,
   los detalles, un comentario o el nombre tienen groserías, insultos u
   ofensas, la app lo marca en rojo al salir del campo y el servidor no lo
   publica hasta corregirlo, diciendo qué palabra cambiar. Detecta trucos
   como `w3on`, `p.u.t.a`, `weooon` o `ctm`, y cuida no tachar palabras
   normales como "película", "Vergara" o "Putaendo".

Si dos personas tocan «Unirme» al mismo tiempo por el último cupo, solo una lo
consigue (la base de datos bloquea el aviso mientras anota a cada persona).
Tampoco se puede unir dos veces la misma persona, ni quien publicó el aviso.

---

## Probar en tu computador (opcional)

Con Python 3.12:

```bash
pip install -r requirements.txt requests certifi "flet[all]>=1.1,<2"
python pruebas/test_api.py            # prueba el servidor
python app_movil/pruebas/test_app.py  # prueba la app tocando sus pantallas
```

Para usar la app en una ventana contra un servidor local:

```bash
python app.py                                                   # servidor en http://localhost:8080
JOIN_IN_SERVIDOR=http://127.0.0.1:8080 flet run app_movil/src   # la app
```

Sin `DATABASE_URL`, los datos se guardan en un archivo local `avisos.db`. Sin
`BREVO_API_KEY`, el código para ingresar aparece en la app (modo de prueba).

## Archivos

| Archivo | Clase | Qué tiene |
|---------|-------|-----------|
| `app.py` | `API` | El servidor: recibe los pedidos de la app y responde en JSON. |
| `acceso.py` | `Acceso` | Ingreso con correo institucional: código, nombre y sesiones (un correo, un celular). |
| `datos.py` | `GestorAvisos`, `Administracion` | Las reglas (cupos, plazos, validaciones), la administración y la base de datos. |
| `filtro.py` | `FiltroPalabras` | El filtro de palabras inapropiadas y sus listas. |
| `lugares.py` | `BuscadorLugares` | El buscador de lugares de Osorno (OpenStreetMap: Photon y Nominatim). |
| `app_movil/` | `AppJoinIn`, `ClienteAPI`, pantallas | La app de Android (ver `app_movil/README.md`). |
| `pruebas/` | | Prueba de la API del servidor. |
| `requirements.txt` | | Las librerías que instala Render. |
| `render.yaml` | | Las instrucciones para que Render publique el servidor gratis. |
| `.github/workflows/app.yml` | | Prueba todo, arma el APK y lo publica. |

Ajustes rápidos: zona horaria (`ZONA_HORARIA`) y categorías (`CATEGORIAS`) en
`datos.py`; colores e íconos por categoría en `app_movil/src/joinin/estilo.py`;
ciudad del buscador (`NOMBRE_ZONA`, `CENTRO`, `ZONA`) en `lugares.py`.

## Sobre el buscador de lugares

Usa servicios gratuitos de OpenStreetMap, sin claves: **Photon**
(photon.komoot.io) y, si falla, **Nominatim** (nominatim.openstreetmap.org).
Nominatim tiene una política de uso que hay que respetar
(https://operations.osmfoundation.org/policies/nominatim/): solo búsquedas
que la persona pide (no autocompletar), máximo 1 por segundo, identificarse y
dar crédito a OpenStreetMap. `lugares.py` lo cumple: consulta solo cuando la
persona toca «Buscar», espera 1 segundo entre consultas, recuerda lo ya
consultado, y la app muestra «Datos de mapas © OpenStreetMap». Sirve para un
uso moderado; con muchísimos usuarios habría que usar un servicio propio o de
pago.

**Solo Osorno:** los servicios reciben el recuadro de Osorno y además se
descarta cualquier resultado que caiga fuera. Para cambiar de ciudad basta con
editar `CENTRO` y `ZONA` en `lugares.py`.
