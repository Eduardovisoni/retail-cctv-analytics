import os

# IMPORTANTE: definir ANTES de importar cv2 para que FFmpeg use TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import math
import threading
import time

import cv2
import numpy as np

from config import DVR_IP, DVR_PASSWORD, DVR_USER, RTSP_PORT

# Numeros de camara conectados al DVR (1 a 8)
CAMERAS = [1, 2, 3, 4, 5, 6, 7, 8]

# True = substream (N02): mas liviano, recomendado para mosaico y YOLO.
# False = stream principal (N01): mas calidad, mas CPU por camara.
USE_SUBSTREAM = True

# Tamano de cada celda del mosaico y columnas de la cuadricula
# (440x300 conserva la proporcion 704x480; 4 columnas -> mosaico de 1760x600)
TILE_W, TILE_H = 440, 300
GRID_COLS = 4

RECONNECT_DELAY = 3  # segundos entre reintentos de conexion
STALE_AFTER = 5      # segundos sin frames nuevos para marcar "sin senal"

WINDOW_NAME = "DVR - Todas las camaras"


def stream_url(camera: int) -> str:
    stream = "02" if USE_SUBSTREAM else "01"
    return (
        f"rtsp://{DVR_USER}:{DVR_PASSWORD}@{DVR_IP}:{RTSP_PORT}"
        f"/Streaming/Channels/{camera}{stream}"
    )


class CameraReader(threading.Thread):
    """Lee una camara en su propio hilo y conserva siempre el ultimo frame.

    Cada VideoCapture bloquea en read(), por eso una camara caida no debe
    congelar a las demas: cada una vive en su propio hilo.
    """

    def __init__(self, camera: int):
        super().__init__(daemon=True)
        self.camera = camera
        self.frame = None
        self.last_frame_time = 0.0
        self.lock = threading.Lock()

    def run(self):
        while True:
            cap = cv2.VideoCapture(stream_url(self.camera), cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                with self.lock:
                    self.frame = frame
                    self.last_frame_time = time.time()
            cap.release()
            time.sleep(RECONNECT_DELAY)

    def get_tile(self) -> np.ndarray:
        with self.lock:
            frame = self.frame
            age = time.time() - self.last_frame_time
        if frame is None or age > STALE_AFTER:
            # Celda negra con aviso cuando la camara no entrega frames
            tile = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
            cv2.putText(tile, f"Camara {self.camera}: sin senal",
                        (20, TILE_H // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)
            return tile
        tile = cv2.resize(frame, (TILE_W, TILE_H))
        cv2.putText(tile, f"Camara {self.camera}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        return tile


def main() -> None:
    readers = [CameraReader(cam) for cam in CAMERAS]
    for reader in readers:
        reader.start()

    rows = math.ceil(len(readers) / GRID_COLS)
    print(f"Mosaico de {len(readers)} camaras ({rows}x{GRID_COLS}). "
          "Presiona 'q' para salir.")

    # Ventana redimensionable: con el escalado de Windows (>100%) el mosaico
    # a tamano fijo puede salirse de la pantalla; asi se ajusta o maximiza
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(WINDOW_NAME, 1408, 480)

    while True:
        tiles = [reader.get_tile() for reader in readers]
        # Rellena con celdas negras para completar la cuadricula
        while len(tiles) < rows * GRID_COLS:
            tiles.append(np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8))

        grid_rows = [
            np.hstack(tiles[i * GRID_COLS:(i + 1) * GRID_COLS])
            for i in range(rows)
        ]
        grid = np.vstack(grid_rows)

        cv2.imshow(WINDOW_NAME, grid)
        if cv2.waitKey(30) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
