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

### Hacer cambios después

Edita un archivo en GitHub (o súbelo de nuevo) y Render publica la versión
nueva solo, en un par de minutos. Los avisos no se pierden.

---

## Cómo funciona

1. Toca el botón **+** y completa el aviso: título, categoría, lugar, fecha,
   hora, cuántos son, cuántos necesitan, detalles y si dura **24 o 48 horas**.
   Quien publica **no necesita escribir su nombre**.
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
7. Cada aviso tiene su propia página (`/aviso/<número>`) para compartir el
   enlace por WhatsApp. Al publicar se muestra ese enlace.

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
| `requirements.txt` | Las librerías que instala Render. |
| `render.yaml`      | Las instrucciones para que Render publique la página gratis. |

Ajustes rápidos: zona horaria (`ZONA_HORARIA`) y categorías (`CATEGORIAS`) en
`datos.py`; colores (`COLOR_PRINCIPAL`, `FONDO`) e íconos (`ICONOS`) en `app.py`.
