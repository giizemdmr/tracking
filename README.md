# Traffic OD Tracking Pipeline (Virtual Gates & BoT-SORT)

Bu proje, Vast.ai / Linux GPU sunucularında veya yerel bilgisayarlarda yüksek performansla çalışmak üzere tasarlanmış, YOLOv8 ve BoT-SORT tabanlı bir **Trafik Origin-Destination (Başlangıç-Bitiş)** takip ve raporlama aracıdır.

Sistem eski "Alan (Zone)" mantığından çıkartılıp **Virtual Line (Sanal Kapı)** mantığına geçirilmiştir. Araçlar Shapely motoruyla çizgileri kestikleri anda tespit edilir, 20-frame (1 sn) flickering korumasına alınır ve ekrandan çıktıklarında Excel dosyasına O-D rotaları basılır.

## Kullanılan Test Videosu
Orijinal test videosunu indirmek için:
👉 [Google Drive Video Linki](https://drive.google.com/file/d/1wEsuJAP7rF9ocwTb-SAlmxspjvq9d-zy/view?usp=sharing)

## Linux (Vast.ai) Kurulumu

Projeyi sunucuya çektikten sonra test videonuzu ana dizine atın. Modelinizin **`yolov8.engine`** versiyonu farklı GPU mimarisinden ötürü LINUX'ta ÇALIŞMAZ. Bu klasöre mutlaka **`yolov8.pt`** dosyanızı ekleyin ve aşağıdaki komutları tek tek çalıştırın:

```bash
# Kurulum izinlerini ver ve bash dosyasini calistir
chmod +x setup_server.sh
./setup_server.sh

# Linux GPU'nuz (Ozel Cihaziniz) icin YOLO Engine Uretimi yapin (Cok Onemlidir!)
yolo export model=models/yolov8.pt format=engine half=True

# PIPELINE'I BASLATIN
python main.py
```

## Kapı Çizimi Aracı (Virtual Gate Setup)
Eğer kapıları (çizgileri) değiştirmek isterseniz `lines.json` dosyasını interaktif bir arayüzle sıfırdan oluşturabilirsiniz:
```bash
python src/line_drawer.py
```
* **Sol Tık:** Nokta Ekle (Çoklu kırıklı çizgi destekler)
* **Sağ Tık:** Son noktayı geri al (Undo)
* **Enter:** Çizgiyi bitirip İsim Ver
* **s:** JSON'a kaydet.

## Raporlama
`main.py` çalıştıktan sonra terminalin altında **SPEED (FPS)** ve **Tamamlanan Geçiş** canlı izleme penceresi çalışacaktır. Video sonunda `deneme5.csv` (veya config'te belirttiğiniz isim) dosyanıza başarıyla bütün Origin -> Destination Excel analiziniz basılacaktır.
