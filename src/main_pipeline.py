import os
import cv2
import json
import time
import logging
import numpy as np
from collections import defaultdict
from engine.video_processor import VisionEngine
from engine.zone_analyzer import ZoneAnalyzer
from tracking.state_memory import StateMemory
from tracking.lifecycle_exporter import LifecycleExporter

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- VISUALIZATION ---
CLASS_COLORS = {
    0: (0, 200, 200),     # Yaya
    1: (0, 255, 0),       # Bisiklet
    2: (0, 165, 255),     # Motosiklet
    3: (255, 100, 50),    # Otomobil
    4: (255, 0, 255),     # Otobus
    5: (0, 0, 255),       # Agir_tasit
    6: (255, 255, 0),     # Panelvan
    7: (200, 150, 0),     # Minibus
    8: (50, 200, 200),    # Kamyonet
}

CLASS_NAMES = {
    0: "Yaya", 1: "Bisiklet", 2: "Motosiklet", 3: "Otomobil",
    4: "Otobus", 5: "Agir_tasit", 6: "Panelvan", 7: "Minibus", 8: "Kamyonet"
}

ZONE_COLOR = (150, 255, 255)  # Light yellow


# ============================================================
# O-D STATS TRACKER
# ============================================================
class ODStats:
    """Tracks completed O-D trips for live display."""
    
    def __init__(self):
        self.od_counts = defaultdict(lambda: defaultdict(int))
        self._reported = set()
    
    def record_trip(self, track_id, origin, destination, class_name):
        """Record a completed O-D trip. Each track_id only counted once."""
        if track_id in self._reported:
            return
        if origin == "Unknown" or destination == "Unknown":
            return
        self.od_counts[(origin, destination)][class_name] += 1
        self._reported.add(track_id)
    
    def get_total(self):
        return sum(sum(c.values()) for c in self.od_counts.values())


# ============================================================
# PROFILER
# ============================================================
class FrameProfiler:
    """Accumulates per-stage timing over N frames, then reports."""
    
    def __init__(self, report_interval=100):
        self.interval = report_interval
        self.reset()
    
    def reset(self):
        self.inference_ms = 0.0
        self.tracking_ms = 0.0
        self.display_ms = 0.0
        self.total_ms = 0.0
        self.frame_count = 0
    
    def add(self, inference_ms, tracking_ms, display_ms, total_ms):
        self.inference_ms += inference_ms
        self.tracking_ms += tracking_ms
        self.display_ms += display_ms
        self.total_ms += total_ms
        self.frame_count += 1
    
    def should_report(self):
        return self.frame_count >= self.interval
    
    def report(self, frame_id, fps, zone_hits=0, zone_misses=0):
        n = max(self.frame_count, 1)
        logger.info(
            f"[PROFILER] Frame {frame_id} | FPS: {fps:.1f} | "
            f"Inference: {self.inference_ms/n:.1f}ms/f | "
            f"Track+Zone: {self.tracking_ms/n:.1f}ms/f | "
            f"Display: {self.display_ms/n:.1f}ms/f | "
            f"Total: {self.total_ms/n:.1f}ms/f | "
            f"ZoneCache hit/miss: {zone_hits}/{zone_misses}"
        )
        self.reset()


# ============================================================
# DRAWING FUNCTIONS
# ============================================================
def load_zone_polygons(zones_json_path):
    zones = []
    try:
        with open(zones_json_path, 'r') as f:
            data = json.load(f)
        for zone in data:
            pts = np.array(zone["points"], dtype=np.int32)
            zones.append((zone["name"], pts))
    except Exception:
        pass
    return zones


def build_zone_overlay(zone_cache, frame_shape):
    """Pre-compute zone overlay once at init."""
    h, w = frame_shape[:2]
    overlay = np.zeros((h, w, 3), dtype=np.uint8)
    mask = np.zeros((h, w), dtype=np.uint8)
    for name, pts in zone_cache:
        cv2.fillPoly(overlay, [pts], ZONE_COLOR)
        cv2.fillPoly(mask, [pts], 255)
    return overlay, mask


def draw_zones_fast(frame, zone_overlay, zone_mask, zone_cache):
    """Blend pre-computed zone overlay — no per-frame fillPoly."""
    zone_area = zone_mask > 0
    frame[zone_area] = cv2.addWeighted(
        frame, 0.85, zone_overlay, 0.15, 0
    )[zone_area]
    for name, pts in zone_cache:
        cv2.polylines(frame, [pts], True, ZONE_COLOR, 1)
        centroid = pts.mean(axis=0).astype(int)
        cv2.putText(frame, f"Z{name}", (centroid[0] - 15, centroid[1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return frame


def draw_detections(frame, detections):
    """Draw bboxes colored by vehicle type. No O-D labels under boxes."""
    for det in detections:
        track_id = det["track_id"]
        class_id = det["class_id"]
        conf = det["conf"]
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        color = CLASS_COLORS.get(class_id, (200, 200, 200))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)

        class_name = CLASS_NAMES.get(class_id, f"C{class_id}")
        label = f"ID:{track_id} {class_name} {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        cx = (x1 + x2) // 2
        cv2.circle(frame, (cx, y2), 3, (0, 0, 255), -1)
    return frame


def draw_hud(frame, frame_id, num_detections, num_tracks, fps):
    """Top bar with FPS and stats."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
    info = f"Frame: {frame_id}  |  Det: {num_detections}  |  Tracks: {num_tracks}  |  FPS: {fps:.1f}"
    cv2.putText(frame, info, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 1)
    cv2.putText(frame, "Q:Quit P:Pause", (w - 170, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
    return frame


def draw_od_panel(frame, od_stats):
    """Live O-D statistics panel on right side."""
    h, w = frame.shape[:2]
    panel_w = 300
    panel_x = w - panel_w - 10

    routes = []
    for (origin, dest), class_counts in sorted(od_stats.od_counts.items()):
        for cls_name, count in sorted(class_counts.items()):
            routes.append((origin, dest, cls_name, count))

    if not routes:
        return frame

    line_h = 20
    panel_h = 50 + len(routes) * line_h + 30
    panel_y = 46

    overlay = frame.copy()
    cv2.rectangle(overlay, (panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    cv2.putText(frame, "O-D Istatistik (Canli)", (panel_x + 10, panel_y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    y = panel_y + 40
    cv2.putText(frame, "Rota", (panel_x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
    cv2.putText(frame, "Tur", (panel_x + 100, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
    cv2.putText(frame, "Adet", (panel_x + 230, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

    for origin, dest, cls_name, count in routes:
        y += line_h
        cv2.putText(frame, f"Z{origin}->Z{dest}", (panel_x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        cv2.putText(frame, cls_name, (panel_x + 100, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
        cv2.putText(frame, str(count), (panel_x + 240, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 150), 1)

    y += line_h + 5
    cv2.line(frame, (panel_x + 10, y - 10), (panel_x + panel_w - 10, y - 10), (100, 100, 100), 1)
    cv2.putText(frame, f"Toplam Gecis: {od_stats.get_total()}", (panel_x + 10, y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return frame


# ============================================================
# MAIN PIPELINE
# ============================================================
def main():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    VIDEO_PATH = os.path.join(PROJECT_ROOT, "data", "traffic_video.mp4")
    MODEL_PATH = os.path.join(PROJECT_ROOT, "models", "yolov8.engine")
    ZONES_JSON = os.path.join(PROJECT_ROOT, "config", "zones.json")
    REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "traffic_report.csv")
    TRACKER_CONFIG = os.path.join(PROJECT_ROOT, "config", "botsort_traffic.yaml")

    DISPLAY_WIDTH = 1024
    DISPLAY_SKIP = 3
    # STALE_BUFFER must be > BoT-SORT track_buffer (90) * vid_stride (2) 
    # to avoid killing tracks that the tracker might still recover after occlusions.
    STALE_BUFFER = 200

    os.makedirs(os.path.join(PROJECT_ROOT, "reports"), exist_ok=True)

    try:
        logger.info("Initializing Pipeline Components...")

        engine = VisionEngine(model_path=MODEL_PATH, video_path=VIDEO_PATH, tracker_config=TRACKER_CONFIG)
        memory = StateMemory(min_confidence=0.65)
        od_stats = ODStats()
        profiler = FrameProfiler(report_interval=100)

        if not os.path.exists(ZONES_JSON):
            logger.warning(f"Zones config not found: {ZONES_JSON}")
            zones = None
            zone_cache = []
        else:
            zones = ZoneAnalyzer(zones_json_path=ZONES_JSON, cache_threshold=8.0)
            zone_cache = load_zone_polygons(ZONES_JSON)

        exporter = LifecycleExporter(memory_instance=memory, output_path=REPORT_PATH, fps=25.0)

        # Pre-calculate display dimensions
        cap_temp = cv2.VideoCapture(VIDEO_PATH)
        ret, tmp = cap_temp.read()
        if ret:
            orig_h, orig_w = tmp.shape[:2]
            display_h = int(orig_h * DISPLAY_WIDTH / orig_w)
        else:
            display_h = 720
        cap_temp.release()

        # Pre-compute zone overlay
        zone_overlay, zone_mask = None, None
        if zone_cache and ret:
            zone_overlay, zone_mask = build_zone_overlay(zone_cache, (orig_h, orig_w))

        logger.info(f"Pipeline Ready. DISPLAY_SKIP={DISPLAY_SKIP} | STALE_BUFFER={STALE_BUFFER}")

        paused = False
        loop_fps = 0.0
        effective_fps = 0.0
        frame_times = []
        VID_STRIDE = 2

        # === MAIN LOOP ===
        # vid_stride=2 means process every 2nd frame. Doubles FPS.
        for frame_data in engine.process_video(vid_stride=VID_STRIDE):
            t_loop_start = time.perf_counter()

            frame_id = frame_data["frame_id"]
            frame = frame_data["frame"]
            detections = frame_data["detections"]
            inference_ms = frame_data["inference_ms"]

            # --- STAGE 2: TRACKING + ZONE ANALYSIS ---
            t_track_start = time.perf_counter()

            for det in detections:
                track_id = det["track_id"]
                class_id = det["class_id"]
                conf = det["conf"]
                bbox = det["bbox"]

                # Zone check with spatial caching
                if zones:
                    current_zone = zones.check_zones(bbox, track_id=track_id)
                    if current_zone:
                        memory.update_zone(track_id, current_zone)

                memory.update_track(
                    frame_id=frame_id,
                    track_id=track_id,
                    class_id=class_id,
                    conf=conf,
                    bbox=bbox
                )

            # --- STALE TRACK REMOVAL (strict buffer) ---
            # Capture O-D stats BEFORE deletion
            stale_ids = memory.get_stale_tracks(frame_id, buffer=STALE_BUFFER)
            for sid in stale_ids:
                if sid in memory.tracks:
                    td = memory.tracks[sid]
                    final_cls = memory.get_final_class(sid)
                    cls_name = CLASS_NAMES.get(final_cls, "?")
                    od_stats.record_trip(sid, td["origin"], td["destination"], cls_name)
                    # Clean zone cache for dead track
                    if zones:
                        zones.clear_cache(sid)

            exporter.process_stale_tracks(current_frame=frame_id, buffer=STALE_BUFFER)

            tracking_ms = (time.perf_counter() - t_track_start) * 1000.0

            # --- STAGE 3: VISUALIZATION ---
            t_display_start = time.perf_counter()

            if frame_id % DISPLAY_SKIP == 0:
                if zone_overlay is not None:
                    frame = draw_zones_fast(frame, zone_overlay, zone_mask, zone_cache)
                frame = draw_detections(frame, detections)
                frame = draw_hud(frame, frame_id, len(detections), len(memory.tracks), effective_fps)
                frame = draw_od_panel(frame, od_stats)
                display = cv2.resize(frame, (DISPLAY_WIDTH, display_h))
                cv2.imshow("Traffic Tracking Pipeline", display)

            display_ms = (time.perf_counter() - t_display_start) * 1000.0
            total_ms = (time.perf_counter() - t_loop_start) * 1000.0

            # --- FPS ---
            t_now = time.perf_counter()
            frame_times.append(t_now)
            if len(frame_times) > 30:
                frame_times.pop(0)
            if len(frame_times) >= 2:
                loop_fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
                effective_fps = loop_fps * VID_STRIDE

            # --- PROFILER ---
            profiler.add(inference_ms, tracking_ms, display_ms, total_ms)
            if profiler.should_report():
                z_hits, z_misses = (0, 0)
                if zones:
                    z_hits, z_misses = zones.get_cache_stats()
                    zones.reset_cache_stats()
                profiler.report(frame_id, effective_fps, z_hits, z_misses)

            # --- KEY HANDLING ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                logger.info("User pressed Q - stopping.")
                break
            elif key == ord('p'):
                paused = not paused
                while paused:
                    k = cv2.waitKey(100) & 0xFF
                    if k == ord('p'):
                        paused = False
                    elif k == ord('q'):
                        paused = False
                        key = ord('q')
                        break
                if key == ord('q'):
                    break

        # === FINALIZATION ===
        cv2.destroyAllWindows()
        logger.info("Video ended. Flushing remaining tracks...")

        # Capture O-D for remaining active tracks
        for tid in list(memory.tracks.keys()):
            td = memory.tracks[tid]
            final_cls = memory.get_final_class(tid)
            cls_name = CLASS_NAMES.get(final_cls, "?")
            od_stats.record_trip(tid, td["origin"], td["destination"], cls_name)

        exporter.flush_all_tracks()

        # Final summary
        logger.info("=" * 50)
        logger.info("FINAL O-D SUMMARY")
        logger.info("=" * 50)
        for (origin, dest), class_counts in sorted(od_stats.od_counts.items()):
            for cls_name, count in sorted(class_counts.items()):
                logger.info(f"  Z{origin} -> Z{dest}: {cls_name} x{count}")
        logger.info(f"Total completed trips: {od_stats.get_total()}")
        logger.info(f"Total exported tracks: {exporter.total_exported}")
        logger.info(f"Report: {REPORT_PATH}")

    except Exception as e:
        cv2.destroyAllWindows()
        logger.error(f"Pipeline execution failed: {e}")
        raise


if __name__ == "__main__":
    main()
