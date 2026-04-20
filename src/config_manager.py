import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple

@dataclass
class YoloConfig:
    input_size: Optional[int] = None
    use_half: Optional[bool] = None
    confidence_threshold: Optional[float] = None
    nms_iou: Optional[float] = None

@dataclass
class TrackingConfig:
    kalman_drop_height_ratio: Optional[float] = None
    kalman_rescue_conf: Optional[float] = None
    stale_buffer: Optional[int] = None
    zone_entry_frames: Optional[int] = None
    zone_change_frames: Optional[int] = None
    min_route_zone_duration: Optional[int] = None
    class_vote_threshold: Optional[float] = 0.75

@dataclass
class PipelineConfig:
    video_path: Optional[str] = None
    model_path: Optional[str] = None
    regions_file: Optional[str] = None
    lines_file: Optional[str] = None
    zone_file: Optional[str] = None
    excel_filename: Optional[str] = None
    vid_stride: Optional[int] = None
    queue_timeout: Optional[float] = None
    display_scale: Optional[float] = None
    headless_mode: Optional[bool] = None

@dataclass
class AppConfig:
    yolo: YoloConfig = field(default_factory=YoloConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    colors: Dict[str, Tuple[int, int, int]] = field(default_factory=dict)

class ConfigManager:
    """Singleton Config Manager for loading and parsing all pipeline parameters."""
    _instance = None
    _config: Optional[AppConfig] = None
    _config_path = "config/pipeline_config.yaml"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self._config = AppConfig()
        if not os.path.exists(self._config_path):
            print(f"[WARNING] {self._config_path} bulunamadi. Varsayilan ayarlar kullaniliyor.")
            return

        with open(self._config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

        if "yolo" in yaml_data:
            self._config.yolo = YoloConfig(**yaml_data["yolo"])
        if "tracking" in yaml_data:
            self._config.tracking = TrackingConfig(**yaml_data["tracking"])
        if "pipeline" in yaml_data:
            self._config.pipeline = PipelineConfig(**yaml_data["pipeline"])
            
        if "colors" in yaml_data:
            self._config.colors = {k: tuple(v) for k, v in yaml_data["colors"].items()}
            
        print(f"[INFO] Global Config basariyla yuklendi: {self._config_path}")

    @property
    def yolo(self) -> YoloConfig:
        return self._config.yolo

    @property
    def tracking(self) -> TrackingConfig:
        return self._config.tracking

    @property
    def pipeline(self) -> PipelineConfig:
        return self._config.pipeline
        
    # --- Backwards compatibility properties (for main.py / reporting.py references) ---
    @property
    def video_path(self) -> str: return self._config.pipeline.video_path
    
    @property
    def model_path(self) -> str: return self._config.pipeline.model_path
    
    @property
    def regions_file(self) -> str: return self._config.pipeline.regions_file
    
    @property
    def lines_file(self) -> str: return self._config.pipeline.lines_file
    
    @property
    def zone_file(self) -> str: return self._config.pipeline.zone_file
    
    @property
    def excel_filename(self) -> str: return self._config.pipeline.excel_filename
    
    @property
    def display_scale(self) -> float: return self._config.pipeline.display_scale
    
    @property
    def confidence_threshold(self) -> float: return self._config.yolo.confidence_threshold
    
    @property
    def zone_entry_frames(self) -> int: return self._config.tracking.zone_entry_frames
    
    @property
    def zone_change_frames(self) -> int: return self._config.tracking.zone_change_frames
    
    @property
    def min_route_zone_duration(self) -> int: return self._config.tracking.min_route_zone_duration
    
    @property
    def class_vote_threshold(self) -> float: return self._config.tracking.class_vote_threshold

    def get_vehicle_color(self, vehicle_type: str) -> tuple:
        """Arac tipine gore BGR renk dondurur. (Kucuk/buyuk harf duyarsiz)"""
        v_type_lower = vehicle_type.lower()
        if not self._config.colors:
            return (200, 200, 200)
            
        for key, color in self._config.colors.items():
            if key in v_type_lower:
                return color
        return self._config.colors.get("arac", (200, 200, 200))

    def reload(self):
        """Disaridan manuel olarak konfigürasyonu tekrar yuklemek icin."""
        self._load_config()

# Coktan baslatilmis global singleton objesi
config_manager = ConfigManager()
