import mediapipe as mp
import cv2

class FaceDetectionEngine:
    def __init__(self, model_path):
        # Initialize MediaPipe Task API
        BaseOptions = mp.tasks.BaseOptions
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = FaceDetectorOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.IMAGE
        )
        self.detector = FaceDetector.create_from_options(options)
        print("🤖 AI Engine: Face Detector Initialized.")

    def check_for_face(self, frame, threshold=0.8):
        """Returns (True/False, detection_result)"""
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = self.detector.detect(mp_image)
        
        face_found = False
        if result and result.detections:
            for det in result.detections:
                if det.categories[0].score > threshold:
                    face_found = True
                    break
        return face_found, result