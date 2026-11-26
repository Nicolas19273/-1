#!/usr/bin/env bash
# Instala el APK en un emulador de Android, abre la app y revisa que arranque:
# que Python corra, que se dibuje la primera pantalla y que no haya errores.
#
#   bash app_movil/pruebas/emulador.sh join-in.apk salida [ingreso]
#
# Con «ingreso» exige llegar a la pantalla de ingreso (o sea, que el servidor
# de Render ya responda como API). Sin eso, también sirve «Sin conexión».
set -uo pipefail

APK=${1:-join-in.apk}
SALIDA=${2:-emulador}
EXIGIR=${3:-}
PAQUETE=com.joinin.app
mkdir -p "$SALIDA"

adb wait-for-device
adb install -r "$APK" || { echo "::error::No se pudo instalar el APK"; exit 1; }
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

adb exec-out screencap -p > "$SALIDA/pantalla.png"
adb logcat -d > "$SALIDA/logcat.txt"
# Una vista chica de la pantalla, legible desde el registro de la ejecución.
if command -v ffmpeg >/dev/null; then
  ffmpeg -loglevel error -y -i "$SALIDA/pantalla.png" -vf scale=360:-1 -q:v 7 "$SALIDA/pantalla.jpg"
elif command -v magick >/dev/null; then
  magick "$SALIDA/pantalla.png" -resize 360x -quality 70 "$SALIDA/pantalla.jpg"
elif python3 -c "import PIL" 2>/dev/null; then
  python3 - "$SALIDA" <<'PY'
import sys
from PIL import Image
carpeta = sys.argv[1]
imagen = Image.open(f"{carpeta}/pantalla.png").convert("RGB")
imagen.thumbnail((360, 900))
imagen.save(f"{carpeta}/pantalla.jpg", quality=70)
PY
fi
if [ -s "$SALIDA/pantalla.jpg" ]; then
  echo "--- pantalla.jpg (base64) ---"; base64 -w0 "$SALIDA/pantalla.jpg"; echo; echo "--- fin ---"
elif [ -s "$SALIDA/pantalla.png" ]; then
  echo "--- pantalla.png (base64) ---"; base64 -w0 "$SALIDA/pantalla.png"; echo; echo "--- fin ---"
fi

echo "Textos en pantalla:"
grep -o -E '(text|content-desc)="[^"]+"' "$SALIDA/ui.xml" 2>/dev/null | sed 's/^/  /' | head -40
echo "Pantalla reconocida: ${pantalla:-ninguna}"

if grep -n -E "Traceback|Error de Python|PythonException" "$SALIDA/logcat.txt"; then
  echo "::error::La app tuvo un error de Python (ver logcat.txt)"
  exit 1
fi
if [ -z "$pantalla" ]; then
  echo "::error::La app no llegó a ninguna pantalla conocida en 4 minutos"
  exit 1
fi
if [ "$EXIGIR" = "ingreso" ] && [ "$pantalla" != "ingreso" ]; then
  echo "::error::La app no llegó al ingreso: el servidor no respondió como API"
  exit 1
fi
echo "OK: la app arranca en Android y muestra «$pantalla»"
