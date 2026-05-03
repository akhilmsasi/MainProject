import cv2

def visualize(image, detections) -> cv2.Mat:
    annotated_image = image.copy()
    for det in detections:
        start_x, start_y, end_x, end_y = det['box']
        cv2.rectangle(annotated_image, (start_x, start_y), (end_x, end_y), (0, 255, 0), 2)
        label = f"{det['class_name']} ({det['confidence']:.2f})"
        cv2.putText(annotated_image, label, (start_x, start_y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return annotated_image