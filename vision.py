"""Offline YuNet face detection. No identity recognition or face embeddings."""
from pathlib import Path

MODEL_NAME = 'OpenCV YuNet'
MODEL_PATH = Path(__file__).parent / 'models' / 'face_detection_yunet_2023mar.onnx'


class FaceDetector:
    name = MODEL_NAME

    def __init__(self, model_path=MODEL_PATH):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        if not Path(model_path).is_file():
            raise FileNotFoundError(f'Face model missing: {model_path}. Restore the bundled models directory.')
        self.detector = cv2.FaceDetectorYN.create(str(model_path), '', (320, 320), 0.8, 0.3, 1000)

    def detect(self, jpeg):
        cv2, np = self.cv2, self.np
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Invalid JPEG')
        h, w = image.shape[:2]
        if min(h, w) < 32:
            return []
        # Bound CPU work while retaining enough detail for close-up faces.
        scale = min(1.0, 640 / w, 480 / h)
        if scale < 1:
            image = cv2.resize(image, (max(32, round(w * scale)), max(32, round(h * scale))))
        h, w = image.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(image)
        if faces is None:
            return []
        boxes = []
        for face in faces:
            x, y, bw, bh = map(float, face[:4])
            left, top = max(0.0, x), max(0.0, y)
            right, bottom = min(float(w), x + bw), min(float(h), y + bh)
            if right <= left or bottom <= top:
                continue
            boxes.append({'label': 'face', 'score': round(float(face[-1]), 3),
                          'box': [round(left / w, 4), round(top / h, 4),
                                  round((right - left) / w, 4), round((bottom - top) / h, 4)]})
        return boxes[:20]
