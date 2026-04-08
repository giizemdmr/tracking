import os
import cv2
import logging
import time
import threading
import queue
from typing import List, Dict, Generator, Optional, Any

# Logging setup for VisionEngine
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FrameReader(threading.Thread):
    """
    Async frame reader thread. Reads video frames into a queue
    so that I/O is pipelined with GPU inference.
    """

    def __init__(self, video_path: str, frame_queue: queue.Queue, max_queue_size: int = 64):
        super().__init__(daemon=True)
        self.video_path = video_path
        self.frame_queue = frame_queue
        self._stop_event = threading.Event()

    def run(self):
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            logger.error(f"FrameReader: Could not open {self.video_path}")
            self.frame_queue.put(None)  # Sentinel
            return

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break
            try:
                self.frame_queue.put(frame, timeout=5.0)
            except queue.Full:
                logger.warning("FrameReader: Queue full, dropping frame")
                continue

        cap.release()
        self.frame_queue.put(None)  # Sentinel: end of stream

    def stop(self):
        self._stop_event.set()


class VisionEngine:
    """
    VisionEngine: Core detection + tracking unit with async I/O.
    Separates video reading (I/O bound) from inference (GPU bound)
    using a threaded frame buffer.
    """

    def __init__(self, model_path: str, video_path: str, tracker_config: str = "botsort.yaml"):
        try:
            import numpy as np
            from ultralytics import YOLO

            self.model = YOLO(model_path, task='detect')

            if hasattr(self.model, 'overrides'):
                self.model.overrides['model'] = model_path

            # WARM-UP: Single dummy inference to initialize TensorRT context
            _ = self.model.predict(np.zeros((1024, 1024, 3), dtype=np.uint8), imgsz=1024, half=True, verbose=False)

            self.video_path = video_path
            self.tracker_config = os.path.abspath(tracker_config) if tracker_config else "botsort.yaml"

            logger.info(f"TensorRT Engine Ready (1024px FP16): {model_path}")
            logger.info(f"Active processing device configured to: {self.model.device}")
            logger.info(f"Video path set to: {video_path}")
        except Exception as e:
            logger.error(f"Failed to initialize engine: {e}")
            raise

    def process_video(self, vid_stride: int = 2) -> Generator[Dict[str, Any], None, None]:
        """
        Processes video with async frame reading.
        vid_stride: Process only every Nth frame (e.g. 2 means 2x speed).
        Yields dict with: frame_id, frame, detections, inference_ms
        """
        # --- ASYNC FRAME BUFFER ---
        frame_queue = queue.Queue(maxsize=64)
        reader = FrameReader(self.video_path, frame_queue)
        reader.start()

        frame_count = 0
        processed_count = 0

        try:
            while True:
                frame = frame_queue.get(timeout=10.0)
                if frame is None:  # End of stream sentinel
                    break

                frame_count += 1

                # Skip frame if stride condition is not met
                if frame_count % vid_stride != 0:
                    continue

                processed_count += 1
                
                # --- INFERENCE + TRACKING (timed) ---
                t_start = time.perf_counter()

                results = self.model.track(
                    source=frame,
                    persist=True,
                    tracker=self.tracker_config,
                    imgsz=1024,
                    half=True,
                    device=0,
                    verbose=False
                )

                inference_ms = (time.perf_counter() - t_start) * 1000.0

                # --- EXTRACT DETECTIONS ---
                detections = []

                if results and results[0].boxes is not None:
                    boxes = results[0].boxes

                    if boxes.id is not None:
                        for i in range(len(boxes)):
                            track_id = boxes.id[i].item() if boxes.id is not None else None
                            conf = float(boxes.conf[i].item())

                            if track_id is not None and conf > 0.30:
                                detections.append({
                                    "track_id": int(track_id),
                                    "class_id": int(boxes.cls[i].item()),
                                    "conf": round(conf, 4),
                                    "bbox": [round(x, 2) for x in boxes.xyxy[i].tolist()]
                                })

                yield {
                    "frame_id": frame_count,
                    "frame": frame,
                    "detections": detections,
                    "inference_ms": inference_ms
                }

        except queue.Empty:
            logger.warning("Frame queue timed out — reader may have stalled.")
        except Exception as e:
            logger.error(f"Error during video processing: {e}")
        finally:
            reader.stop()
            reader.join(timeout=3.0)
            logger.info(f"Processing ended. Total frames processed: {frame_count}")


if __name__ == "__main__":
    TEST_MODEL = "models/yolov8n.engine"
    TEST_VIDEO = "data/traffic_sample.mp4"
    TEST_TRACKER = "config/botsort_traffic.yaml"

    try:
        engine = VisionEngine(
            model_path=TEST_MODEL,
            video_path=TEST_VIDEO,
            tracker_config=TEST_TRACKER
        )

        print(f"--- VisionEngine Test Started ---")
        for frame_data in engine.process_video():
            if frame_data["detections"]:
                print(f"Frame {frame_data['frame_id']} | Objects: {len(frame_data['detections'])} | Inference: {frame_data['inference_ms']:.1f}ms")
            else:
                print(f"Frame {frame_data['frame_id']} | No objects | Inference: {frame_data['inference_ms']:.1f}ms")

    except Exception as e:
        print(f"Test Failed: {e}")
