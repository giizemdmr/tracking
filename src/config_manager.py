import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple

def get_time_of_day(video_path: Optional[str]) -> Optional[str]:
    """
    Videodaki zamani dosya adinin sonundaki sira numarasindan (sequence ID) veya
    bulundugu klasor isminden ceker.
    Geri donus degerleri: 'sabah', 'ogle', 'aksam'
    """
    if not video_path:
        return None
        
    # 1. Yol (Klasör) kontrolü: Path içerisinde 'sabah', 'ogle', 'öğle', 'aksam', 'akşam' geçiyor mu?
    path_lower = video_path.lower().replace("\\", "/")
    parts_in_path = path_lower.split("/")
    for part in parts_in_path:
        if "sabah" in part:
            return "sabah"
        elif "ogle" in part or "öğle" in part:
            return "ogle"
        elif "aksam" in part or "akşam" in part:
            return "aksam"
            
    # 2. Dosya adı (Sequence ID) kontrolü:
    basename = os.path.basename(video_path)
    name, _ = os.path.splitext(basename)
    parts = name.split('_')
    for part in reversed(parts):
        # 'rapor' gibi son ekleri atlamak icin sadece rakam iceren kismi temizleyip alalim
        part_clean = ''.join(c for c in part if c.isdigit())
        if part_clean:
            try:
                seq_num = int(part_clean)
                if seq_num <= 10:
                    return "sabah"
                elif seq_num <= 15:
                    return "ogle"
                else:
                    return "aksam"
            except ValueError:
                pass
    return None

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
    def lines_file(self) -> str:
        base_path = self._config.pipeline.lines_file or "config/lines.json"
        
        # Eger lines_file config/lines.json disinda ozel bir dosya ise,
        # hicbir zaman-dilimi eki yapmadan dogrudan bu ozel cizgi dosyasini dondur.
        if base_path != "config/lines.json":
            return base_path
            
        video_path = self.video_path
        if video_path:
            # 1. Öncelik: Video ile aynı klasörde bir json dosyası var mı diye bak
            video_dir = os.path.dirname(video_path)
            if video_dir:
                import glob
                local_json_files = glob.glob(os.path.join(video_dir, "*.json"))
                # Sadece disk kök dizini (C:\, D:\ vb.) değilse veya dosya adında "line"/"gate" geçiyorsa alalım
                is_root = not os.path.splitdrive(video_dir)[1].strip("\\/")
                valid_files = []
                for jf in local_json_files:
                    jf_name = os.path.basename(jf).lower()
                    if "line" in jf_name or "gate" in jf_name:
                        valid_files.append(jf)
                    elif not is_root:
                        valid_files.append(jf)
                
                if valid_files:
                    # En uygun json'ı seç (adında 'line' geçeni veya ilkini)
                    chosen_json = None
                    for jf in valid_files:
                        if "line" in os.path.basename(jf).lower():
                            chosen_json = jf
                            break
                    if not chosen_json:
                        chosen_json = valid_files[0]
                    return chosen_json.replace("\\", "/")

        # 2. Öncelik: Zaman dilimine göre config klasöründen eşleştir
        time_of_day = get_time_of_day(video_path)
        if time_of_day:
            dir_name, file_name = os.path.split(base_path)
            name, ext = os.path.splitext(file_name)
            if time_of_day == "sabah":
                # Eger 'lines_sabah.json' gibi ozel bir dosya varsa onu kullan, yoksa ana 'lines.json'a don
                sabah_path = os.path.join(dir_name, f"{name}_sabah{ext}").replace("\\", "/")
                if os.path.exists(sabah_path):
                    return sabah_path
                return base_path
            return os.path.join(dir_name, f"{name}_{time_of_day}{ext}").replace("\\", "/")
        return base_path
    
    @property
    def zone_file(self) -> str:
        base_path = self._config.pipeline.zone_file or "config/zone.json"
        if base_path != "config/zone.json":
            return base_path
            
        video_path = self.video_path
        if video_path:
            video_dir = os.path.dirname(video_path)
            if video_dir:
                import glob
                local_json_files = glob.glob(os.path.join(video_dir, "*.json"))
                is_root = not os.path.splitdrive(video_dir)[1].strip("\\/")
                valid_files = []
                for jf in local_json_files:
                    jf_name = os.path.basename(jf).lower()
                    if "zone" in jf_name or "roi" in jf_name:
                        valid_files.append(jf)
                    elif not is_root:
                        valid_files.append(jf)
                
                for jf in valid_files:
                    jf_lower = os.path.basename(jf).lower()
                    if "zone" in jf_lower or "roi" in jf_lower:
                        return jf.replace("\\", "/")
        return base_path
    
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
