"""Optional offline OpenCV HOG person detector. No identity recognition."""
import time

class PersonDetector:
    def __init__(self):
        import cv2
        import numpy as np
        self.cv2, self.np = cv2, np
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, jpeg):
        cv2, np = self.cv2, self.np
        image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Invalid JPEG')
        h, w = image.shape[:2]
        # Keep processing bounded; HOG works best on upright, full-body people.
        scale = min(1, 480 / w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)))
        h, w = image.shape[:2]
        if h < 128 or w < 64:
            return []
        rects, weights = self.hog.detectMultiScale(image, winStride=(8, 8), padding=(8, 8), scale=1.08)
        return [{'label': 'person', 'score': round(float(weight), 3),
                 'box': [round(x/w, 4), round(y/h, 4), round(bw/w, 4), round(bh/h, 4)]}
                for (x, y, bw, bh), weight in zip(rects, weights) if float(weight) >= 0.4][:20]
