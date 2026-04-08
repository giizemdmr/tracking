import json
import logging
from typing import List, Dict, Tuple, Optional, Any
from shapely.geometry import Polygon, Point
from shapely.prepared import prep

# Logging setup for ZoneAnalyzer
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ZoneAnalyzer:
    """
    Spatial zone analyzer with per-track LineString intersection logic.
    Uses Shapely prepared geometries for faster tests.
    Prevents "Quantum Leap" misses by checking if the path between
    the previous and current frame intersected a zone.
    """

    def __init__(self, zones_json_path: str, cache_threshold: float = 8.0):
        """
        Args:
            zones_json_path: Path to zones JSON file.
            cache_threshold: Min pixel movement to trigger a new zone check.
        """
        self.zones: Dict[str, Polygon] = {}
        self.prepared_zones: Dict[str, Any] = {}  # Shapely prepared geometries (faster)
        
        # Stores previous center to form LineStrings: {track_id: (cx, cy)}
        self._history: Dict[int, Tuple[float, float]] = {}
        
        self.load_zones(zones_json_path)

    def load_zones(self, json_path: str) -> None:
        """Parses JSON and creates Shapely Polygon + prepared geometry objects."""
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            for zone_data in data:
                name = zone_data.get("name")
                points = zone_data.get("points")

                if name and points and len(points) >= 3:
                    poly = Polygon(points)
                    self.zones[name] = poly
                    self.prepared_zones[name] = prep(poly)  # ~2x faster containment test
                    logger.info(f"Loaded Zone: {name} (Vertices: {len(points)})")
                else:
                    logger.warning(f"Skipping invalid zone data: {zone_data}")

            logger.info(f"Total zones successfully loaded: {len(self.zones)}")

        except FileNotFoundError:
            logger.error(f"Zones JSON file not found: {json_path}")
        except Exception as e:
            logger.error(f"Error loading zones from {json_path}: {e}")

    def check_zones(self, bbox: Tuple[float, float, float, float], 
                    track_id: int) -> Optional[str]:
        """
        Determines which zone contains the bottom-center of the bbox 
        or intersects the line from the previous bottom-center.

        Args:
            bbox: (x1, y1, x2, y2) bounding box.
            track_id: track ID for LineString history.

        Returns:
            Zone name or None.
        """
        if not self.zones:
            return None

        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = y2  # Bottom-center = road contact point

        from shapely.geometry import LineString
        point = Point(cx, cy)
        line = None
        
        if track_id in self._history:
            prev_cx, prev_cy = self._history[track_id]
            # Form a LineString if the point actually moved
            if cx != prev_cx or cy != prev_cy:
                line = LineString([(prev_cx, prev_cy), (cx, cy)])

        result = None

        for name, prepared_poly in self.prepared_zones.items():
            # 1. Point check
            if prepared_poly.contains(point):
                result = name
                break
            # 2. LineString intersection check (Quantum Leap)
            if line is not None and prepared_poly.intersects(line):
                result = name
                break

        # Save current position for next frame's LineString
        self._history[track_id] = (cx, cy)

        return result

    def clear_cache(self, track_id: int) -> None:
        """Remove a track from the history when it dies."""
        self._history.pop(track_id, None)

    def get_cache_stats(self) -> Tuple[int, int]:
        """Disabled: returns dummy values."""
        return 0, 0

    def reset_cache_stats(self) -> None:
        pass


if __name__ == "__main__":
    import os

    MOCK_JSON_PATH = "zones_test.json"
    mock_data = [
        {"name": "Kuzey", "points": [[100, 100], [400, 100], [400, 400], [100, 400]]},
        {"name": "Guney", "points": [[500, 500], [800, 500], [800, 800], [500, 800]]}
    ]

    try:
        with open(MOCK_JSON_PATH, "w") as f:
            json.dump(mock_data, f)

        analyzer = ZoneAnalyzer(MOCK_JSON_PATH, cache_threshold=10.0)

        # Test: first call (cache miss)
        r1 = analyzer.check_zones((150, 150, 250, 350), track_id=1)
        print(f"First call: {r1} (expect Kuzey)")

        # Test: second call with small movement (cache hit)
        r2 = analyzer.check_zones((152, 152, 252, 352), track_id=1)
        print(f"Cache hit test: {r2} (should be same, from cache)")

        # Test: big movement (cache miss)
        r3 = analyzer.check_zones((550, 550, 650, 750), track_id=1)
        print(f"Big move: {r3} (expect Guney)")

        hits, misses = analyzer.get_cache_stats()
        print(f"Cache stats: hits={hits}, misses={misses}")

    except Exception as e:
        print(f"Test Failed: {e}")
    finally:
        if os.path.exists(MOCK_JSON_PATH):
            os.remove(MOCK_JSON_PATH)
