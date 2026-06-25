from ultralytics import YOLO
model = YOLO('model/best.pt')
print("Model Names:", model.names)
