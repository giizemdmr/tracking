import logging
from collections import deque
from typing import Dict, Deque, List, Optional, Any, Tuple

# Logging setup for StateMemory
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StateMemory:
    """
    Memory manager for vehicle lifecycle, classification voting, and O-D tracking.
    
    CRITICAL RULES:
    - last_seen_frame is ALWAYS updated on every detection (regardless of confidence)
    - class_scores are only updated for detections above min_confidence
    - origin = first zone (LOCKED forever)
    - destination = latest zone different from origin (continuously updated)
    """

    # Yörünge (Trajectory) Hafızası Parametreleri
    TRAJECTORY_MAXLEN: int = 30       # Her track için tutulacak max bottom-center noktası
    STALE_BUFFER_DEFAULT: int = 200   # Bu kadar frame kaybolursa trajectory temizlenir

    def __init__(self, min_confidence: float = 0.65):
        self.min_confidence = min_confidence
        # Structure: {
        #   track_id: {
        #     "start_frame": int,
        #     "last_seen_frame": int,
        #     "first_bbox": list,
        #     "last_bbox": list,
        #     "class_scores": {class_id: float},
        #     "origin": str,       # LOCKED after first zone assignment
        #     "destination": str,   # Continuously updated to latest different zone
        #     "zone_history": list  # All zone contacts in order
        #   }
        # }
        self.tracks: Dict[int, Dict[str, Any]] = {}
        
        # Yörünge Hafızası: {track_id: deque([(cx, cy), ...], maxlen=30)}
        self.trajectory_history: Dict[int, Deque[Tuple[int, int]]] = {}
        
        logger.info(f"StateMemory initialized with min_confidence={min_confidence}, trajectory_maxlen={self.TRAJECTORY_MAXLEN}")

    def update_track(self, frame_id: int, track_id: int, class_id: int, conf: float, bbox: List[float]) -> None:
        """
        Updates track data. 
        CRITICAL: last_seen_frame is ALWAYS updated (even for low confidence).
        Class voting only happens above min_confidence threshold.
        Trajectory (bottom-center) is ALWAYS appended.
        """
        if track_id not in self.tracks:
            # Initialize new track
            self.tracks[track_id] = {
                "start_frame": frame_id,
                "last_seen_frame": frame_id,
                "first_bbox": bbox,
                "last_bbox": bbox,
                "class_scores": {},
                "origin": "Unknown",
                "destination": "Unknown",
                "zone_history": [],
                "touched_zones": set()
            }
            # Always count first detection for voting regardless of confidence
            self.tracks[track_id]["class_scores"][class_id] = conf
            
            # Yörünge hafızası başlat
            self.trajectory_history[track_id] = deque(maxlen=self.TRAJECTORY_MAXLEN)
        else:
            track = self.tracks[track_id]
            # ALWAYS update liveness — this prevents premature stale detection
            track["last_seen_frame"] = frame_id
            track["last_bbox"] = bbox

            # Only update classification voting for high-confidence detections
            if conf >= self.min_confidence:
                scores = track["class_scores"]
                scores[class_id] = scores.get(class_id, 0.0) + conf
        
        # --- Yörünge (Trajectory) Güncelleme ---
        # Bottom-center noktası: (cx, y2)
        x1, y1, x2, y2 = bbox[0], bbox[1], bbox[2], bbox[3]
        cx = int((x1 + x2) / 2)
        cy = int(y2)  # Alt-orta (araç tekerlek hizası)
        self.trajectory_history[track_id].append((cx, cy))

    def update_zone(self, track_id: int, zone_name: str) -> None:
        """
        Updates O-D based on zone contact.
        
        RULES:
        - Origin: First zone encountered → LOCKED FOREVER
        - Destination: Latest zone that is DIFFERENT from origin → continuously updated
        """
        if track_id not in self.tracks:
            return

        track = self.tracks[track_id]

        # Record in zone history and set
        track["touched_zones"].add(zone_name)
        history = track["zone_history"]
        if not history or history[-1] != zone_name:
            history.append(zone_name)

        # ORIGIN: First zone → LOCK
        if track["origin"] == "Unknown":
            track["origin"] = zone_name
            logger.debug(f"Track {track_id} ORIGIN LOCKED: Z{zone_name}")
            return  # Don't set destination on same frame as origin

        # DESTINATION: Latest zone different from origin → continuously update
        if zone_name != track["origin"]:
            track["destination"] = zone_name

    def get_final_class(self, track_id: int) -> Optional[int]:
        """Determines most likely class via accumulated confidence voting."""
        if track_id not in self.tracks:
            return None
        class_scores = self.tracks[track_id]["class_scores"]
        if not class_scores:
            return None
        return max(class_scores, key=class_scores.get)

    def get_stale_tracks(self, current_frame: int, buffer: int = 90) -> List[int]:
        """
        Returns track IDs not seen for more than `buffer` frames.
        STRICT: Only returns tracks where gap EXCEEDS the buffer.
        """
        stale_ids = []
        for track_id, data in self.tracks.items():
            gap = current_frame - data["last_seen_frame"]
            if gap > buffer:
                stale_ids.append(track_id)
        return stale_ids

    def delete_track(self, track_id: int) -> bool:
        """Removes a track and its trajectory from memory."""
        if track_id in self.tracks:
            del self.tracks[track_id]
            self.trajectory_history.pop(track_id, None)
            return True
        return False

    def get_trajectory(self, track_id: int) -> List[Tuple[int, int]]:
        """Returns the trajectory history for a given track as a list of (cx, cy) points."""
        if track_id in self.trajectory_history:
            return list(self.trajectory_history[track_id])
        return []

    def cleanup_stale_trajectories(self, current_frame: int, buffer: int = 200) -> List[int]:
        """
        200 frame boyunca görülmeyen araçların yörünge hafızasını temizler.
        Returns: Temizlenen track_id listesi.
        """
        cleaned = []
        stale_ids = self.get_stale_tracks(current_frame, buffer)
        for track_id in stale_ids:
            if track_id in self.trajectory_history:
                del self.trajectory_history[track_id]
                cleaned.append(track_id)
        return cleaned

    def get_track_summary(self, track_id: int) -> Optional[Dict]:
        """Get a snapshot of track data for reporting."""
        if track_id not in self.tracks:
            return None
        td = self.tracks[track_id]
        return {
            "origin": td["origin"],
            "destination": td["destination"],
            "zone_history": list(td["zone_history"]),
            "touched_zones": list(td["touched_zones"]),
            "start_frame": td["start_frame"],
            "last_seen_frame": td["last_seen_frame"],
            "final_class": self.get_final_class(track_id),
            "trajectory": self.get_trajectory(track_id)
        }


if __name__ == "__main__":
    memory = StateMemory(min_confidence=0.65)

    # Simulate track lifecycle
    memory.update_track(frame_id=1, track_id=42, class_id=3, conf=0.85, bbox=[10, 10, 50, 50])
    memory.update_zone(42, "1")  # First zone → ORIGIN LOCKED

    memory.update_track(frame_id=50, track_id=42, class_id=3, conf=0.40, bbox=[100, 100, 150, 150])
    # Low conf but last_seen_frame STILL updates to 50

    memory.update_zone(42, "3")  # Different zone → DESTINATION set
    memory.update_zone(42, "5")  # Another zone → DESTINATION updated to 5

    print(f"Track 42: {memory.tracks[42]}")
    print(f"Origin should be '1': {memory.tracks[42]['origin']}")
    print(f"Destination should be '5': {memory.tracks[42]['destination']}")
    print(f"last_seen_frame should be 50: {memory.tracks[42]['last_seen_frame']}")
    print(f"Final Class: {memory.get_final_class(42)}")

    # Stale check: at frame 140, gap = 140-50 = 90 → NOT stale (needs > 90)
    print(f"Stale at frame 140 (gap=90): {memory.get_stale_tracks(140, buffer=90)}")
    # At frame 141, gap = 91 → STALE
    print(f"Stale at frame 141 (gap=91): {memory.get_stale_tracks(141, buffer=90)}")

    # --- Trajectory Tests ---
    print(f"\n--- Trajectory Tests ---")
    traj = memory.get_trajectory(42)
    print(f"Track 42 trajectory ({len(traj)} pts): {traj}")
    # Beklenen: 2 nokta — bbox [10,10,50,50] → (30, 50), bbox [100,100,150,150] → (125, 150)
    assert traj == [(30, 50), (125, 150)], f"FAIL: {traj}"
    print("Trajectory assertion PASSED")

    # Simulate many updates to test maxlen=30
    for i in range(40):
        memory.update_track(frame_id=100+i, track_id=42, class_id=3, conf=0.90,
                           bbox=[i*10, i*10, i*10+40, i*10+40])
    traj2 = memory.get_trajectory(42)
    print(f"After 42 total updates, trajectory length: {len(traj2)} (maxlen={memory.TRAJECTORY_MAXLEN})")
    assert len(traj2) == memory.TRAJECTORY_MAXLEN, f"FAIL: expected {memory.TRAJECTORY_MAXLEN}, got {len(traj2)}"
    print("Maxlen assertion PASSED")

    # Stale trajectory cleanup
    cleaned = memory.cleanup_stale_trajectories(current_frame=500, buffer=200)
    print(f"Cleaned stale trajectories: {cleaned}")
    print(f"Track 42 trajectory after cleanup: {memory.get_trajectory(42)}")
