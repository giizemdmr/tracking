import cv2
import json
import numpy as np
import os

class ZoneDrawer:
    """
    A class to interactively draw regions of interest (ROI) on a video frame.
    Following PalyeTracking architectural standards.
    """
    def __init__(self, video_path: str, frame_index: int = 0):
        self.video_path = video_path
        self.frame_index = frame_index
        self.frame = self._get_specific_frame(frame_index)
        self.display_frame = self.frame.copy()
        
        # State management
        self.zones = {}  # {name: [[x1, y1], [x2, y2], ...]}
        self.current_points = []
        self.window_name = "ZoneDrawer - Interactive O-D Matrix Setup"
        
        # Colors (BGR)
        self.line_color = (0, 255, 0)      # Bright Green
        self.point_color = (0, 0, 255)     # Red
        self.polygon_color = (255, 100, 0) # Blue-ish (will be used with transparency)
        self.text_color = (255, 255, 255)  # White

    def _get_specific_frame(self, index: int):
        """Reads a specific frame from the input video."""
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {self.video_path}")
        
        # Jump to the specified frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            raise ValueError(f"Could not read frame {index} from: {self.video_path}")
        
        return frame

    def mouse_callback(self, event, x, y, flags, param):
        """Standard OpenCV mouse callback for drawing polygons."""
        # Left Click: Add a new point
        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append([x, y])
            print(f"[DEBUG] Point added: ({x}, {y})")

        # Right Click: Close the polygon
        elif event == cv2.EVENT_RBUTTONDOWN:
            if len(self.current_points) >= 3:
                # Ask for zone name in terminal
                zone_name = input("\nEnter name for this zone (e.g., North_Entrance): ").strip()
                if not zone_name:
                    zone_name = f"Zone_{len(self.zones) + 1}"
                
                self.zones[zone_name] = self.current_points
                print(f"[SUCCESS] Zone '{zone_name}' saved with {len(self.current_points)} points.")
                
                # Reset current points for next zone
                self.current_points = []
            else:
                print("[WARNING] A polygon must have at least 3 points to close.")

    def save_zones(self, output_path: str = "config/zones.json"):
        """Saves all defined zones to a JSON file."""
        if not self.zones:
            print("[WARNING] No zones defined. Nothing to save.")
            return

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            # Transform structure to match ZoneAnalyzer expectation
            # ZoneAnalyzer expects: [{"name": "name", "points": [[x1, y1], ...]}, ...]
            formatted_zones = []
            for name, points in self.zones.items():
                formatted_zones.append({
                    "name": name,
                    "points": points
                })
                
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(formatted_zones, f, indent=4)
            print(f"[INFO] Successfully saved {len(self.zones)} zones to {output_path}")
        except Exception as e:
            print(f"[ERROR] Failed to save zones: {e}")

    def _draw_overlay(self):
        """Refreshes the display frame with all annotations."""
        # Start with a fresh copy of the frame
        canvas = self.frame.copy()
        
        # 1. Draw already saved zones
        for name, points in self.zones.items():
            pts = np.array(points, np.int32).reshape((-1, 1, 2))
            
            # Draw semi-transparent fill
            overlay = canvas.copy()
            cv2.fillPoly(overlay, [pts], self.polygon_color)
            cv2.addWeighted(overlay, 0.4, canvas, 0.6, 0, canvas)
            
            # Draw border
            cv2.polylines(canvas, [pts], True, self.line_color, 2)
            
            # Add name label near the center
            m = cv2.moments(pts)
            if m["m00"] != 0:
                cx = int(m["m10"] / m["m00"])
                cy = int(m["m01"] / m["m00"])
                cv2.putText(canvas, name, (cx - 20, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.text_color, 2)

        # 2. Draw current in-progress lines
        if len(self.current_points) > 0:
            for i in range(len(self.current_points)):
                cv2.circle(canvas, tuple(self.current_points[i]), 4, self.point_color, -1)
                if i > 0:
                    cv2.line(canvas, tuple(self.current_points[i-1]), tuple(self.current_points[i]), self.line_color, 2)
        
        return canvas

    def run(self):
        """Executes the main visualization loop."""
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        
        print("\n" + "="*40)
        print(f" ZONE DRAWER - Frame: {self.frame_index}")
        print("="*40)
        print("Controls:")
        print("  - Left Click  : Add Point")
        print("  - Right Click : Close Polygon & Name Zone")
        print("  - 's'         : Save to config/zones.json")
        print("  - 'q'         : Quit")
        print("="*40 + "\n")

        while True:
            self.display_frame = self._draw_overlay()
            cv2.imshow(self.window_name, self.display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            
            # 's' for Save
            if key == ord('s'):
                self.save_zones()
            
            # 'q' for Quit
            elif key == ord('q'):
                break

        cv2.destroyAllWindows()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive Zone Drawing Tool")
    parser.add_argument("--video", type=str, default="data/traffic_video.mp4", help="Path to video")
    parser.add_argument("--frame", type=int, default=0, help="Frame index to start drawing from")
    args = parser.parse_args()
    
    try:
        drawer = ZoneDrawer(args.video, args.frame)
        drawer.run()
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
