# Join In para Android

La app de Join In, hecha completa en Python con [Flet](https://flet.dev).
Habla con el servidor de Render (`app.py` de la raíz), que guarda los datos en Neon.

## Descargar e instalar

1. En el celular Android, abre
   **https://github.com/Nicolas19273/-1/releases/latest/download/join-in.apk**
   (siempre baja la versión más nueva).
2. Abre el archivo descargado y toca **Instalar**. Si Android lo pide, permite
   «instalar apps de esta fuente» para el navegador.
3. Entra con tu correo `@alumnos.ulagos.cl` y el código que te llega.

La primera vez del día la app puede tardar hasta un minuto en conectar: el plan
gratis de Render duerme el servidor cuando nadie lo usa.

## Cómo se arma el APK

No hace falta instalar nada en el computador. Cada vez que se sube un cambio,
GitHub Actions (`.github/workflows/app.yml`):

1. prueba el servidor (`pruebas/test_api.py`),
2. prueba la app tocando sus pantallas con Flet real contra un servidor local
   (`app_movil/pruebas/test_app.py`),
3. arma el APK con `flet build apk`,
4. en `main`, lo publica en **Releases**.

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
