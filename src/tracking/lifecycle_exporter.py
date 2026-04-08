import csv
import logging
import os
from datetime import datetime
from typing import Dict, Any

# Logging setup for LifecycleExporter
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LifecycleExporter:
    """
    Handles the reporting of tracked objects once their lifecycle ends.
    
    STRICT RULE: A track is ONLY reported and deleted when:
    - current_frame - last_seen_frame > buffer (buffer must be >= track_buffer)
    - OR video has ended (flush mode)
    """

    CLASS_MAP = {
        0: "Yaya", 1: "Bisiklet", 2: "Motosiklet", 3: "Otomobil",
        4: "Otobus", 5: "Agir_tasit", 6: "Panelvan", 7: "Minibus", 8: "Kamyonet"
    }

    def __init__(self, memory_instance: Any, output_path: str, fps: float = 25.0):
        self.memory = memory_instance
        self.output_path = output_path
        self.fps = fps
        self.initialized = False
        self.total_exported = 0

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    def _initialize_csv(self):
        """Creates CSV file with header."""
        header = [
            "Track_ID", "Vehicle_Type", "Total_Confidence",
            "Start_Frame", "End_Frame", "Duration_Frames", "Duration_Seconds",
            "First_BBox", "Last_BBox", "Origin", "Destination", "Zone_History"
        ]
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)
        self.initialized = True
        logger.info(f"Initialized CSV report at {self.output_path}")

    def process_stale_tracks(self, current_frame: int, buffer: int = 90):
        """
        Reports and removes tracks that haven't been seen for > buffer frames.
        STRICT: gap must EXCEED buffer, not just equal it.
        """
        stale_ids = self.memory.get_stale_tracks(current_frame, buffer)
        for track_id in stale_ids:
            self._export_and_delete(track_id)

    def flush_all_tracks(self):
        """Force-export all remaining active tracks (called at video end)."""
        active_ids = list(self.memory.tracks.keys())
        for track_id in active_ids:
            self._export_and_delete(track_id)
        logger.info(f"Flushed {len(active_ids)} remaining tracks at video end.")

    def _export_and_delete(self, track_id: int):
        """
        Exports a single track to CSV and deletes from memory.
        Returns the track data dict before deletion (for O-D stats).
        """
        if track_id not in self.memory.tracks:
            return None

        if not self.initialized:
            self._initialize_csv()

        track_data = self.memory.tracks[track_id]
        final_class_id = self.memory.get_final_class(track_id)
        vehicle_type = self.CLASS_MAP.get(final_class_id, f"Unknown({final_class_id})")

        total_conf = sum(track_data["class_scores"].values())
        start_f = track_data["start_frame"]
        end_f = track_data["last_seen_frame"]
        duration_frames = end_f - start_f + 1
        duration_seconds = round(duration_frames / self.fps, 2)

        origin = track_data["origin"]
        destination = track_data["destination"]
        touched_zones = track_data.get("touched_zones", set())

        # --- GÖREV 3: Çoklu Temas (Touched Zones) ve Çıkış Belirleme ---
        # Eğer origin belliyse ve origin harici başka poligonlara da temas edilmişse:
        if origin != "Unknown" and len(touched_zones - {origin}) > 0:
            # Kronolojik olarak en son temas dilen / Origin'den farklı bölgeyi bul
            for z in reversed(track_data.get("zone_history", [])):
                if z != origin and z in touched_zones:
                    destination = z
                    break

        row = [
            track_id,
            vehicle_type,
            round(total_conf, 4),
            start_f,
            end_f,
            duration_frames,
            duration_seconds,
            str(track_data["first_bbox"]),
            str(track_data["last_bbox"]),
            origin,
            destination,
            "->".join(track_data.get("zone_history", []))
        ]

        try:
            with open(self.output_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)

            self.total_exported += 1
            
            # Capture summary before deletion
            summary = {
                "track_id": track_id,
                "vehicle_type": vehicle_type,
                "origin": origin,
                "destination": destination,
                "final_class_id": final_class_id
            }
            
            self.memory.delete_track(track_id)
            logger.info(f"Exported Track {track_id}: {vehicle_type} | "
                        f"O:Z{track_data['origin']} D:Z{track_data['destination']} | "
                        f"Frames: {start_f}-{end_f} ({duration_seconds}s)")
            return summary

        except Exception as e:
            logger.error(f"Failed to write report for track {track_id}: {e}")
            return None


if __name__ == "__main__":
    from state_memory import StateMemory

    mock_memory = StateMemory()
    mock_memory.update_track(1, 101, 3, 0.95, [100, 100, 200, 200])
    mock_memory.update_zone(101, "1")
    mock_memory.update_track(100, 101, 3, 0.98, [500, 500, 600, 600])
    mock_memory.update_zone(101, "5")

    exporter = LifecycleExporter(mock_memory, "reports/test_report.csv", fps=25.0)

    # Should NOT be stale at frame 190 (gap = 90, needs > 90)
    exporter.process_stale_tracks(current_frame=190, buffer=90)
    print(f"Track 101 still in memory: {101 in mock_memory.tracks}")

    # SHOULD be stale at frame 191 (gap = 91 > 90)
    exporter.process_stale_tracks(current_frame=191, buffer=90)
    print(f"Track 101 removed: {101 not in mock_memory.tracks}")
