"""Runs the real detector when optional dependencies are installed."""
import importlib.util
import unittest

@unittest.skipUnless(importlib.util.find_spec('cv2'), 'Optional OpenCV dependency is not installed')
class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vision import PersonDetector
        cls.detector=PersonDetector()
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
