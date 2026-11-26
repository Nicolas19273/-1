#!/usr/bin/env bash
# Instala el APK en un emulador de Android y lo prueba de verdad:
#
#   1. Abre la app: tiene que llegar a una pantalla conocida, sin errores de Python.
#   2. Recorrido: con un servidor local con datos de ejemplo, la app recorre todas
#      sus pantallas y se guarda una foto de cada una (también en el registro).
#   3. «Actualizar»: baja el APK publicado y abre el instalador de Android.
#
#   bash app_movil/pruebas/emulador.sh join-in.apk salida [ingreso]
#
# Con «ingreso» exige que el paso 1 llegue a la pantalla de ingreso (o sea, que el
# servidor de Render ya responda como API). Sin eso, también sirve «Sin conexión».
set -uo pipefail

APK=${1:-join-in.apk}
SALIDA=${2:-emulador}
EXIGIR=${3:-}
PAQUETE=com.joinin.app
CARPETA_APP="/sdcard/Android/data/$PAQUETE/files"
PUERTO=8765
mkdir -p "$SALIDA"

# Guarda una foto de la pantalla y la deja en el registro (achicada, en base64).
foto() {
  local nombre=$1
  adb exec-out screencap -p > "$SALIDA/$nombre.png"
  python3 - "$SALIDA/$nombre.png" <<'PY' || true
import base64, io, sys
from PIL import Image
imagen = Image.open(sys.argv[1]).convert("RGB")
imagen.thumbnail((540, 1200))
datos = io.BytesIO()
imagen.save(datos, "JPEG", quality=72)
print(f"--- foto {sys.argv[1].rsplit('/', 1)[-1][:-4]} ---")
print(base64.b64encode(datos.getvalue()).decode())
print("--- fin ---")
PY
}

textos() {
  grep -o -E '(text|content-desc)="[^"]+"' "$1" 2>/dev/null | sed 's/^/  /' | head -40
}

adb wait-for-device
adb install -r "$APK" || { echo "::error::No se pudo instalar el APK"; exit 1; }

# --------------------------------------------------------------------------- 1
adb logcat -c
adb shell monkey -p "$PAQUETE" -c android.intent.category.LAUNCHER 1 >/dev/null
pantalla=""
for i in $(seq 1 48); do  # hasta 4 minutos: Python se prepara y Render puede estar dormido
  sleep 5
  if adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; then
    adb shell cat /sdcard/ui.xml > "$SALIDA/ui.xml" 2>/dev/null
    if grep -q "Ingresa con tu correo" "$SALIDA/ui.xml"; then pantalla="ingreso"; break; fi
    if grep -q "Sin conexión" "$SALIDA/ui.xml"; then pantalla="sin_conexion"; break; fi
  fi
done
foto ingreso
adb logcat -d > "$SALIDA/logcat.txt"
echo "Textos en pantalla:"; textos "$SALIDA/ui.xml"
echo "Pantalla reconocida: ${pantalla:-ninguna}"
if grep -n -E "Traceback|PythonException" "$SALIDA/logcat.txt"; then
  echo "::error::La app tuvo un error de Python (ver logcat.txt)"; exit 1
fi
if [ -z "$pantalla" ]; then
  echo "::error::La app no llegó a ninguna pantalla conocida en 4 minutos"; exit 1
fi
if [ "$EXIGIR" = "ingreso" ] && [ "$pantalla" != "ingreso" ]; then
  echo "::error::La app no llegó al ingreso: el servidor no respondió como API"; exit 1
fi
echo "OK: la app arranca en Android y muestra «$pantalla»"

# --------------------------------------------------------------------------- 2
echo "Recorrido por las pantallas…"
rm -f avisos.db
env -u DATABASE_URL -u BREVO_API_KEY PORT=$PUERTO CLAVE_ADMIN=clave-recorrido \
  python3 app.py > "$SALIDA/servidor.log" 2>&1 &
for i in $(seq 1 60); do curl -s -o /dev/null "http://127.0.0.1:$PUERTO/salud" && break; sleep 0.5; done
python3 app_movil/pruebas/sembrar.py "http://127.0.0.1:$PUERTO" clave-recorrido "http://10.0.2.2:$PUERTO" \
  > "$SALIDA/recorrido.json" || { echo "::error::No se pudieron sembrar los datos"; exit 1; }
adb shell am force-stop "$PAQUETE"
adb shell mkdir -p "$CARPETA_APP"
adb push "$SALIDA/recorrido.json" "$CARPETA_APP/recorrido.json" >/dev/null
adb logcat -c
adb shell monkey -p "$PAQUETE" -c android.intent.category.LAUNCHER 1 >/dev/null
fotos=0
for nombre in tablero aviso aviso_unirse crear crear_abajo buzon admin admin_avisos; do
  listo=""
  for i in $(seq 1 90); do
    if adb logcat -d | grep -q "\[recorrido\] $nombre"; then listo="si"; break; fi
    if adb logcat -d | grep -q "\[recorrido\] error"; then break; fi
    sleep 1
  done
  if [ -n "$listo" ]; then foto "$nombre"; fotos=$((fotos + 1)); else break; fi
done
adb logcat -d > "$SALIDA/logcat_recorrido.txt"
grep -h "\[recorrido\]" "$SALIDA/logcat_recorrido.txt" | sed 's/^.*\[recorrido\]/  [recorrido]/' | head -20
if grep -n -E "Traceback" "$SALIDA/logcat_recorrido.txt"; then
  echo "::error::Error de Python durante el recorrido (ver logcat_recorrido.txt)"; exit 1
fi
if [ "$fotos" -lt 8 ]; then
  echo "::error::El recorrido no llegó a todas las pantallas ($fotos de 8)"; exit 1
fi
echo "OK: recorrido completo ($fotos pantallas)"
adb shell am force-stop "$PAQUETE"

# --------------------------------------------------------------------------- 3
# «Actualizar» de verdad: con el archivo de prueba en su carpeta, la app baja el
# APK publicado con el DownloadManager y abre el instalador de Android. Basta con
# que aparezca el instalador (no se instala nada).
echo "Prueba del actualizador…"
adb shell appops set "$PAQUETE" REQUEST_INSTALL_PACKAGES allow
adb shell touch "$CARPETA_APP/prueba-actualizar"
adb logcat -c
adb shell monkey -p "$PAQUETE" -c android.intent.category.LAUNCHER 1 >/dev/null

instalador=""
for i in $(seq 1 60); do  # hasta 5 minutos: baja unos 55 MB
  sleep 5
  if adb shell uiautomator dump /sdcard/ui2.xml >/dev/null 2>&1; then
    adb shell cat /sdcard/ui2.xml > "$SALIDA/ui_actualizar.xml" 2>/dev/null
    if grep -q "packageinstaller" "$SALIDA/ui_actualizar.xml"; then instalador="si"; break; fi
    if grep -q "Un permiso, solo la primera vez" "$SALIDA/ui_actualizar.xml"; then break; fi
    if grep -q "No se pudo bajar la actualización" "$SALIDA/ui_actualizar.xml"; then break; fi
  fi
done
adb logcat -d > "$SALIDA/logcat_actualizar.txt"
echo "Textos en pantalla:"; textos "$SALIDA/ui_actualizar.xml"
grep -h "\[actualizar\]" "$SALIDA/logcat_actualizar.txt" | tail -5
if grep -n -E "Traceback" "$SALIDA/logcat_actualizar.txt"; then
  echo "::error::La app tuvo un error de Python al actualizar (ver logcat_actualizar.txt)"; exit 1
fi
if [ -z "$instalador" ]; then
  echo "::error::«Actualizar» no llegó al instalador de Android"; exit 1
fi
echo "OK: «Actualizar» baja el APK y abre el instalador de Android"
