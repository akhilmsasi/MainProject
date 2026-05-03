import cv2
import numpy as np
import os

class MultiObjectMotionDetectionEngine:
    def __init__(self, prototxt_path, model_path):
        if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
            raise FileNotFoundError("Model files not found.")
            
        self.net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
        # Background subtractor
        self.backSub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=20, detectShadows=True)
        
        self.class_names = ["background", "aeroplane", "bicycle", "bird", "boat", "bottle", 
                            "bus", "car", "cat", "chair", "cow", "diningtable", "dog", 
                            "horse", "motorbike", "person", "pottedplant", "sheep", "sofa", 
                            "train", "tvmonitor"]

    def detect_objects(self, frame, conf_threshold=0.5, motion_threshold=0.05):
        (h, w) = frame.shape[:2]
        fgMask = self.backSub.apply(frame)
        _, fgMask = cv2.threshold(fgMask, 200, 255, cv2.THRESH_BINARY)
        
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()

        results = []
        for i in range(detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > conf_threshold:
                idx = int(detections[0, 0, i, 1])
                box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (startX, startY, endX, endY) = box.astype("int")
                
                # Check for motion in this box
                roi = fgMask[startY:endY, startX:endX]
                if roi.size > 0:
                    motion_ratio = cv2.countNonZero(roi) / roi.size
                    if motion_ratio > motion_threshold:
                        results.append({'class_name': self.class_names[idx], 'box': (startX, startY, endX, endY)})
        return results