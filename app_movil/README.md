# Join In para Android

La app de Join In, hecha completa en Python con [Flet](https://flet.dev).
Habla con el servidor de Render (`app.py` de la raíz), que guarda los datos en Neon.

## Descargar e instalar

1. En el celular Android, abre
   **https://github.com/Nicolas19273/-1/releases/latest/download/join-in.apk**
   (siempre baja la versión más nueva).
2. Abre el archivo descargado y toca **Instalar**. Si Android lo pide, permite
   «instalar apps de esta fuente» para el navegador.
   - Si tu celular es antiguo o muy básico y dice que no se puede instalar,
     baja **join-in-32bits.apk** desde
     https://github.com/Nicolas19273/-1/releases/latest
3. Entra con tu correo `@alumnos.ulagos.cl` y el código que te llega.

La primera vez del día la app puede tardar hasta un minuto en conectar: el plan
gratis de Render duerme el servidor cuando nadie lo usa.

## Actualizar

No hace falta volver a GitHub ni desinstalar. Cuando hay una versión nueva, el
tablero muestra **Actualización disponible** → **Actualizar**: la app baja la
versión nueva (con su avance en pantalla) y Android pregunta «¿Quieres
actualizar esta app?» → **Actualizar**. Se mantienen la sesión y los avisos.

- La primera vez, Android pide permiso para que Join In instale su
  actualización («Permitir de esta fuente»). La app lo explica y abre el ajuste.
- También se puede buscar a mano: menú de la cuenta → **Buscar actualizaciones**.
- Funciona solo si todas las versiones van firmadas con la misma clave (ver
  «Firma del APK» más abajo). Sin eso, Android no deja instalar encima.

Por dentro (`src/joinin/actualizar.py`): la app compara su versión con la
última de Releases, baja el APK con el DownloadManager de Android y abre el
instalador del sistema (con pyjnius). Fuera de Android abre el enlace.

## Cómo se arma el APK

No hace falta instalar nada en el computador. Cada vez que se sube un cambio,
GitHub Actions (`.github/workflows/app.yml`):

1. prueba el servidor (`pruebas/test_api.py`),
2. prueba la app tocando sus pantallas con Flet real contra un servidor local
   (`app_movil/pruebas/test_app.py`),
3. arma el APK con `flet build apk --split-per-abi` (uno por tipo de
   procesador, más livianos que uno para todos),
4. instala el APK en un emulador de Android, lo abre y revisa que llegue a
   una pantalla sin errores, y que **Actualizar** baje el APK y abra el
   instalador de Android (`app_movil/pruebas/emulador.sh`),
5. en `main`, publica en **Releases** `join-in.apk` (celulares de 64 bits,
   casi todos) y `join-in-32bits.apk` (celulares antiguos).

### Firma del APK (para poder actualizar sin desinstalar)

Android solo instala una versión nueva encima de la anterior si las dos están
firmadas con la misma clave. Para eso el repositorio necesita dos secretos en
**Settings → Secrets and variables → Actions → New repository secret**:

| Nombre | Valor |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | el archivo `join-in.jks` en base64 |
| `ANDROID_KEYSTORE_PASSWORD` | la clave de ese archivo |

Sin ellos el APK se arma igual, pero con una clave de prueba distinta cada vez.

## Partes

```
app_movil/
  pyproject.toml          nombre, versión y dependencias (flet, certifi, tzdata)
  src/main.py             punto de entrada: ft.run(iniciar_app)
  src/assets/icon.png     ícono de la app
  src/joinin/
    app.py                AppJoinIn: sesión del celular, navegación y pedidos
    cliente.py            ClienteAPI: habla con el servidor (urllib + JSON)
    formato.py            textos de fechas, cupos y precios
    estilo.py             colores e íconos por categoría
    componentes.py        tarjetas, chips, botones
    pantallas/            inicio, ingreso, tablero, aviso, crear, buzón, admin
  pruebas/test_app.py     prueba de punta a punta
```

## Probar en el computador

```bash
pip install "flet[all]>=1.1,<2" -r ../requirements.txt requests certifi
python pruebas/test_app.py                  # prueba completa
JOIN_IN_SERVIDOR=http://127.0.0.1:8000 flet run src   # la app en una ventana
```
