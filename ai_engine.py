import cv2
import numpy as np

class MultiObjectMotionDetectionEngine:
    def __init__(self, prototxt_path, model_path):
        # Load the Caffe model
        self.net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
        # Class names for MobileNet SSD
        self.class_names = [
            "background", "aeroplane", "bicycle", "bird", "boat", "bottle", 
            "bus", "car", "cat", "chair", "cow", "diningtable", "dog", 
            "horse", "motorbike", "person", "pottedplant", "sheep", "sofa", 
            "train", "tvmonitor"
        ]
        print("🤖 AI Engine: Multi-Object Detector Initialized.")

    def detect_objects(self, frame, conf_threshold=0.5):
        """Processes the frame and returns a list of detected objects."""
        (h, w) = frame.shape[:2]
        
        # Preprocess frame for MobileNet SSD (300x300)
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()

        results = []
        # Loop over the detections
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            
            # Filter by confidence
            if confidence > conf_threshold:
                idx = int(detections[0, 0, i, 1])
                
                # Get bounding box coordinates
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")
                
                # Create result dictionary
                results.append({
                    'class_name': self.class_names[idx] if idx < len(self.class_names) else "unknown",
                    'confidence': float(confidence),
                    'box': (int(startX), int(startY), int(endX), int(endY))
                })
        
        return results