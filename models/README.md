# YuNet face detector

`face_detection_yunet_2023mar.onnx` is the pretrained YuNet face-detection model from [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/face_detection_yunet), bundled for offline inference. It detects face locations; the app does not compute face embeddings or identify people.

- Upstream commit: `48b10fa505aeb51fbd127fc60a5c660040e823b7`
- Model SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`
- License: MIT, reproduced in `YuNet-LICENSE.txt`.
- Detection API: [OpenCV FaceDetectorYN](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html).

The detector filters scores below 0.8 and suppresses overlapping boxes with a 0.3 NMS threshold. Model scores describe detection, not identity or wrongdoing.
