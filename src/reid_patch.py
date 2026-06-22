import numpy as np
import cv2
import onnxruntime
import ultralytics.trackers.bot_sort as bot_sort
import torch

class CustomONNXReID:
    """Custom ReID class that runs our ONNX Vehicle ReID model and monkey-patches Ultralytics."""
    def __init__(self, model_path: str):
        # We initialize the ONNX model here
        self.session = onnxruntime.InferenceSession(
            model_path,
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
        )
        self.input_name = self.session.get_inputs()[0].name
        # osnet_ain_x1_0_vehicle_reid_optimized expects 208x208
        self.input_shape = (208, 208)

    def __call__(self, img: np.ndarray, dets: np.ndarray) -> list[np.ndarray]:
        """
        Extract embeddings for detected objects.
        img: np.ndarray of shape (H, W, 3) BGR
        dets: np.ndarray of shape (N, 6) or (N, 4) where [:, :4] are xyxy bounding boxes
        """
        feats = []
        if len(dets) == 0:
            return feats

        image_height, image_width = img.shape[:2]

        for det in dets:
            x1, y1, x2, y2 = map(int, det[:4])
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(image_width - 1, x2)
            y2 = min(image_height - 1, y2)
            
            crop = img[y1:y2, x1:x2]
            
            if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0:
                # If invalid crop, return empty features vector
                feats.append(np.ones(512, dtype=np.float32) * 1e-5)
                continue
                
            # Preprocess to match vehicle-reid-0001 expected inputs
            input_image = cv2.resize(crop, (self.input_shape[1], self.input_shape[0]))
            input_image = cv2.cvtColor(input_image, cv2.COLOR_BGR2RGB)
            input_image = input_image.transpose(2, 0, 1)
            input_image = input_image.astype('float32')
            input_image = np.expand_dims(input_image, axis=0)
            
            # Run inference
            result = self.session.run(None, {self.input_name: input_image})
            feat = np.array(result[0][0])
            feats.append(feat)
            
        return feats

# MONKEY PATCH: We replace the ReID class in Ultralytics' bot_sort module with our custom class!
bot_sort.ReID = CustomONNXReID
