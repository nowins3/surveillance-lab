"""Runs the real detector when optional dependencies are installed."""
import importlib.util
import unittest
from unittest.mock import Mock

@unittest.skipUnless(importlib.util.find_spec('cv2'), 'Optional OpenCV dependency is not installed')
class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vision import FaceDetector
        cls.detector=FaceDetector()
    def test_blank_frame(self):
        d=self.detector
        ok,jpeg=d.cv2.imencode('.jpg',d.np.zeros((540,960,3),dtype=d.np.uint8))
        self.assertTrue(ok)
        self.assertEqual(d.detect(jpeg.tobytes()),[])
    def test_small_frame(self):
        d=self.detector
        _,jpeg=d.cv2.imencode('.jpg',d.np.zeros((64,64,3),dtype=d.np.uint8))
        self.assertEqual(d.detect(jpeg.tobytes()),[])
    def test_invalid_frame(self):
        with self.assertRaises(ValueError):self.detector.detect(b'not a jpeg')
    def test_tiny_frame(self):
        d=self.detector
        _,jpeg=d.cv2.imencode('.jpg',d.np.zeros((16,16,3),dtype=d.np.uint8))
        self.assertEqual(d.detect(jpeg.tobytes()),[])
    def test_face_boxes_are_clipped_normalized_and_serializable(self):
        import json
        from vision import FaceDetector
        d=FaceDetector()
        # YuNet can return a face rectangle extending beyond a frame edge.
        d.detector=Mock()
        d.detector.detect.return_value=(1,d.np.array([
            [-10,-5,60,45,0,0,0,0,0,0,0,0,0,0,.95],
            [200,200,10,10,0,0,0,0,0,0,0,0,0,0,.9]
        ],dtype=d.np.float32))
        _,jpeg=d.cv2.imencode('.jpg',d.np.zeros((100,100,3),dtype=d.np.uint8))
        boxes=d.detect(jpeg.tobytes())
        self.assertEqual(boxes,[{'label':'face','score':.95,'box':[0,0,.5,.4]}])
        json.dumps(boxes)
        d.detector.setInputSize.assert_called_once_with((100,100))
