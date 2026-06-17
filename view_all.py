import os

# IMPORTANTE: definir ANTES de importar cv2 para que FFmpeg use TCP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

import math
import threading
import time
from queue import Queue, Empty

import cv2
import numpy as np
from ultralytics import YOLO

from config import DVR_IP, DVR_PASSWORD, DVR_USER, RTSP_PORT

# Camaras activas
CAMERAS = [6, 7]

# True = substream (N02): mas liviano, recomendado para mosaico y YOLO.
# False = stream principal (N01): mas calidad, mas CPU por camara.
USE_SUBSTREAM = True

# Tamano de cada celda del mosaico y columnas de la cuadricula
TILE_W, TILE_H = 440, 300
GRID_COLS = 2

RECONNECT_DELAY = 3   # segundos entre reintentos de conexion
STALE_AFTER = 5       # segundos sin frames nuevos para marcar "sin senal"

DETECT_EVERY = 1      # correr inferencia en cada frame
DETECTION_CONF = 0.4  # confianza minima para mostrar una deteccion

WINDOW_NAME = "DVR - Deteccion de personas"


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
        self.detections = []  # lista de (x1, y1, x2, y2, conf) en coords de tile
        self.lock = threading.Lock()
        self.detection_queue: Queue = Queue(maxsize=2)  # cola propia por camara
        self._frame_count = 0

    def run(self):
        while True:
            cap = cv2.VideoCapture(stream_url(self.camera), cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            while cap.isOpened():
                ok, frame = cap.read()
                if not ok:
                    break
                self._frame_count += 1
                with self.lock:
                    self.frame = frame
                    self.last_frame_time = time.time()
                # enviar tile al worker de deteccion cada N frames
                if self._frame_count % DETECT_EVERY == 0:
                    tile = cv2.resize(frame, (TILE_W, TILE_H))
                    try:
                        self.detection_queue.put_nowait(tile)
                    except Exception:
                        pass  # cola llena: se descarta este frame
            cap.release()
            time.sleep(RECONNECT_DELAY)

    def update_detections(self, boxes: list):
        with self.lock:
            self.detections = boxes

    def get_tile(self) -> np.ndarray:
        with self.lock:
            frame = self.frame
            age = time.time() - self.last_frame_time
            detections = list(self.detections)

        if frame is None or age > STALE_AFTER:
            tile = np.zeros((TILE_H, TILE_W, 3), dtype=np.uint8)
            cv2.putText(tile, f"Camara {self.camera}: sin senal",
                        (20, TILE_H // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 0, 255), 2)
            return tile

        tile = cv2.resize(frame, (TILE_W, TILE_H))

        for (x1, y1, x2, y2, conf) in detections:
            cv2.rectangle(tile, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(tile, f"persona {conf:.0%}", (x1, max(y1 - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        cv2.putText(tile, f"Camara {self.camera}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        return tile


class DetectionWorker(threading.Thread):
    """Hilo YOLO dedicado a una sola camara — ambas corren inferencia en paralelo."""

    def __init__(self, model: YOLO, reader: "CameraReader"):
        super().__init__(daemon=True)
        self._model = model
        self._reader = reader

    def run(self):
        while True:
            try:
                tile = self._reader.detection_queue.get(timeout=1)
            except Empty:
                continue

            results = self._model(tile, classes=[0], conf=DETECTION_CONF, verbose=False)[0]
            boxes = [
                (int(box.xyxy[0][0]), int(box.xyxy[0][1]),
                 int(box.xyxy[0][2]), int(box.xyxy[0][3]),
                 float(box.conf[0]))
                for box in results.boxes
            ]
            self._reader.update_detections(boxes)


def main() -> None:
    print("Cargando modelo YOLO (yolov8n)...")
    model = YOLO("yolov8n.pt")
    print("Modelo listo.")

    readers = [CameraReader(cam) for cam in CAMERAS]

    for reader in readers:
        DetectionWorker(model, reader).start()
        reader.start()

    rows = math.ceil(len(readers) / GRID_COLS)
    print(f"Mosaico de {len(readers)} camaras ({rows}x{GRID_COLS}). "
          "Presiona 'q' para salir.")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(WINDOW_NAME, TILE_W * GRID_COLS, TILE_H * rows)

    while True:
        tiles = [reader.get_tile() for reader in readers]
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
