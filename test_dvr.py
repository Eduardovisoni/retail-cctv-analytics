import os

# IMPORTANTE: esta variable debe definirse ANTES de importar cv2,
# de lo contrario el FFmpeg interno de OpenCV la ignora y usa UDP
# (paquetes perdidos -> errores de PPS / decode_slice_header)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import cv2

from config import DVR_IP, DVR_PASSWORD, DVR_USER, RTSP_PORT

# 101 = camara 1 stream principal, 102 = camara 1 substream.
# Patron general: N01 / N02 donde N es el numero de camara (1-8).
CHANNEL = "101"

URL = (
    f"rtsp://{DVR_USER}:{DVR_PASSWORD}@{DVR_IP}:{RTSP_PORT}"
    f"/Streaming/Channels/{CHANNEL}"
)

# Lecturas fallidas consecutivas antes de reconectar (~1 segundo a 30 fps)
MAX_CONSECUTIVE_FAILURES = 30


def open_stream() -> cv2.VideoCapture:
    cap = cv2.VideoCapture(URL, cv2.CAP_FFMPEG)
    # Buffer minimo para video en tiempo real, sin retraso acumulado
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def main() -> None:
    cap = open_stream()
    if not cap.isOpened():
        print(f"No se pudo abrir el stream: {URL}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Conectado: {width}x{height} @ {fps:.1f} fps. Presiona 'q' para cerrar.")

    failures = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                print("Stream cortado, reconectando...")
                cap.release()
                cap = open_stream()
                failures = 0
            continue

        failures = 0
        cv2.imshow(f"DVR - Canal {CHANNEL}", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
