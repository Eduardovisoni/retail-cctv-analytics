# retail-cctv-analytics

Visualización en tiempo real de cámaras analógicas conectadas a un DVR Hikvision, vía RTSP con Python y OpenCV. Base para detección de personas con YOLO (en desarrollo).

## Hardware probado

- **DVR:** Hikvision DS-7108HGHI-M1 (Turbo HD, 8 canales, salida RTSP por Ethernet)
- **Cámaras:** Hikvision DS-2CE16D0T-LPFS — analógicas (HDTVI/NTSC), conectadas por coaxial BNC al DVR
- **Stream:** H.264 o H.265, 704×480 (4CIF)

Las cámaras analógicas no tienen IP propia: el DVR actúa como puente y expone un stream RTSP por cámara.

## Instalación

```bash
git clone https://github.com/Eduardovisoni/retail-cctv-analytics.git
cd retail-cctv-analytics
pip install -r requirements.txt
```

Luego copia `config.example.py` como `config.py` y coloca la IP, usuario y contraseña reales de tu DVR. `config.py` está en `.gitignore`, así las credenciales nunca se suben al repositorio.

No necesitas instalar FFmpeg aparte: `opencv-python` trae su propio FFmpeg integrado.

## Uso

**Una sola cámara** (edita `CHANNEL` en el script):

```bash
python test_dvr.py
```

**Todas las cámaras en mosaico** (edita la lista `CAMERAS` y `USE_SUBSTREAM`):

```bash
python view_all.py
```

Ambos se cierran con la tecla `q`.

## Cómo funciona la conexión RTSP

El formato de URL de los DVR Hikvision es:

```
rtsp://USUARIO:CONTRASEÑA@IP_DVR:554/Streaming/Channels/<N><MM>
```

- `N` = número de cámara (1–8)
- `MM` = `01` stream principal (máxima calidad) o `02` substream (más liviano)

Ejemplos: `101` = cámara 1 principal, `102` = cámara 1 substream, `201` = cámara 2 principal.

Detalles de implementación importantes:

- **Transporte TCP forzado.** Por defecto FFmpeg usa UDP para RTSP, y la pérdida de paquetes corrompe el video H.264/H.265. La variable de entorno `OPENCV_FFMPEG_CAPTURE_OPTIONS = "rtsp_transport;tcp"` lo fuerza a TCP, y **debe definirse antes de `import cv2`** — si se define después, OpenCV la ignora silenciosamente.
- **Un hilo por cámara** (`view_all.py`). `VideoCapture.read()` es bloqueante; con un hilo por stream, una cámara caída no congela a las demás. Cada hilo reconecta solo si el stream se corta.
- **Buffer mínimo** (`CAP_PROP_BUFFERSIZE = 1`) para ver video en tiempo real sin retraso acumulado.

## Configuración obligatoria del DVR (leer antes de usar)

Sin estos ajustes, la conexión RTSP se establece pero el video **no se puede decodificar**:

1. **Desactivar la encriptación de stream de Hik-Connect.**
   `Menú → Red → Acceso a plataforma (Hik-Connect)` → desmarcar **"Encriptación de flujo/transmisión"**.
   Si está activa, el DVR cifra el contenido del video con el código de verificación del equipo y ningún reproductor externo (OpenCV, FFmpeg, VLC) podrá decodificarlo. Este es el error más difícil de diagnosticar porque la conexión funciona y los datos llegan — pero llegan cifrados.

2. **Desactivar H.264+** (`Menú → Grabar → Parámetro`, por cámara).
   Es un códec semi-propietario de Hikvision que los decodificadores estándar no manejan bien.

3. **Codificación de video:** H.264 y H.265 funcionan ambos. El cambio de códec se aplica al instante (no requiere reiniciar el DVR).

## Errores comunes y qué significan

| Error en consola | Causa probable | Solución |
|---|---|---|
| `non-existing PPS X referenced` (X aleatorio: 2, 5, 23...) | Bitstream corrupto: encriptación de stream activa, o pérdida de paquetes por UDP | Desactivar encriptación; forzar TCP |
| `crop values invalid`, `PPS id out of range`, `Skipping invalid undecodable NALU` | Encriptación de stream activa (el decodificador parsea bytes cifrados) | Desactivar encriptación en Hik-Connect |
| `decode_slice_header error`, `no frame!`, `A non-intra slice in an IDR NAL unit` | Consecuencia de lo anterior: sin cabeceras válidas no se decodifica ningún frame | Igual que arriba |
| Pantalla verde | El decodificador entrega buffers vacíos (decodificación fallida) | Igual que arriba |
| TCP "no tiene efecto" | `OPENCV_FFMPEG_CAPTURE_OPTIONS` definida después de `import cv2` | Definirla en la primera línea del script |

**Pista que engaña:** que el audio "llegue" no prueba que el stream esté sano. El audio G.711 no tiene estructura que validar, así que "decodifica" hasta basura cifrada sin reportar errores.

## Diagnóstico rápido

Antes de tocar el código de Python, prueba el stream con FFmpeg directamente:

```bash
ffplay -rtsp_transport tcp "rtsp://USUARIO:CONTRASEÑA@IP_DVR:554/Streaming/Channels/101"
ffprobe -rtsp_transport tcp "rtsp://USUARIO:CONTRASEÑA@IP_DVR:554/Streaming/Channels/101"
```

`ffprobe` debe mostrar una línea como `Stream #0:0: Video: hevc (Main), yuv420p(tv), 704x480`. Si `ffplay` no puede mostrar el video, Python tampoco va a poder: el problema está en el DVR, no en el código.

## Roadmap

- [ ] Detección de personas con YOLO sobre los streams
- [ ] Alertas / conteo por zona
