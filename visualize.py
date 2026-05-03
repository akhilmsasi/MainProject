import cv2
import numpy as np

# Configuration
TEXT_COLOR = (255, 0, 0)  # Red
FONT_SIZE = 0.6
FONT_THICKNESS = 2

def visualize(image, detections) -> np.ndarray:
    """
    Draws bounding boxes and labels on the image.
    Args:
        image: The input RGB image.
        detections: A list of dicts: [{'class_name': str, 'confidence': float, 'box': (x1, y1, x2, y2)}]
    Returns:
        Image with bounding boxes.
    """
    annotated_image = image.copy()

    for det in detections:
        # Extract box coordinates (x1, y1, x2, y2)
        start_x, start_y, end_x, end_y = det['box']
        
        # Draw bounding box
        cv2.rectangle(annotated_image, (start_x, start_y), (end_x, end_y), TEXT_COLOR, 2)

        # Draw label and score
        label = f"{det['class_name']} ({det['confidence']:.2f})"
        
        # Position text just above the box
        text_y = start_y - 10 if start_y - 10 > 10 else start_y + 20
        cv2.putText(annotated_image, label, (start_x, text_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, FONT_SIZE, TEXT_COLOR, FONT_THICKNESS)

    return annotated_image