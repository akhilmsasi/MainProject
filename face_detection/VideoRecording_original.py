import cv2
import mediapipe as mp
import collections
import time
import datetime
import os
import threading
from visualize import visualize  # your helper script

# ================= CONFIGURATION =================
OUTPUT_PATH = r"C:/xampp/htdocs/Videos"
MODEL_PATH = r"C:/Users/ASHNA/Documents/Ashna/Project Report/ProjectWork/Backend_code/blaze_face_short_range.tflite"

FPS = 30
BUFFER_DURATION = 30
BUFFER_SIZE = FPS * BUFFER_DURATION
QUEUE_LIMIT = 5
CONFIDENCE_THRESHOLD = 0.8   # Only trigger if confidence > 80%

os.makedirs(OUTPUT_PATH, exist_ok=True)

# ================= GLOBALS =================
stop_requested = threading.Event()   # thread-safe flag

# ================= HELPERS =================
def save_video_worker(frames, filename, fps=30):
    if not frames:
        return
    h, w, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, (w, h))
    for f in frames:
        out.write(f)
    out.release()
    print(f"\n[Background] ✅ Saved video: {os.path.basename(filename)}")

# ================= FACE DETECTION RECORDING =================
def face_detection_video():
    stop_requested.clear()  # reset flag

    BaseOptions = mp.tasks.BaseOptions
    FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
    FaceDetector = mp.tasks.vision.FaceDetector
    VisionRunningMode = mp.tasks.vision.RunningMode

    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.IMAGE
    )
    detector = FaceDetector.create_from_options(options)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_buffer = collections.deque(maxlen=BUFFER_SIZE)
    video_queue = collections.deque(maxlen=QUEUE_LIMIT)

    is_recording_event = False
    event_start_time = None
    event_frames = []
    last_background_save = time.time()

    print("System Started.")
    print("Recording will auto-trigger when a face is detected.")
    print("Press 'q' or 'ESC' to quit manually.")

    try:
        while cap.isOpened() and not stop_requested.is_set():
            loop_start = time.time()

            success, raw_frame = cap.read()
            if not success:
                continue

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=raw_frame)
            detection_result = detector.detect(mp_image)
            annotated_frame = visualize(raw_frame, detection_result)

            frame_buffer.append(annotated_frame)

            # Background segment every 30s
            if not is_recording_event and (time.time() - last_background_save >= BUFFER_DURATION):
                frames_to_save = list(frame_buffer)
                video_queue.append(frames_to_save)
                last_background_save = time.time()
                print(f"[Queue] Added background segment. Queue size={len(video_queue)}")

            # Trigger event recording only if a face is detected with high confidence
            if detection_result and detection_result.detections:
                for detection in detection_result.detections:
                    if detection.categories:
                        for category in detection.categories:
                            if category.score > CONFIDENCE_THRESHOLD:
                                if not is_recording_event:
                                    is_recording_event = True
                                    event_start_time = time.time()
                                    event_frames = []
                                    print("\n🔴 FACE DETECTED! Recording next 30s...")

            # Continue event recording until 30s
            if is_recording_event:
                event_frames.append(annotated_frame)
                if time.time() - event_start_time >= BUFFER_DURATION:
                    print("📢 Event capture finished. Processing...")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    merged_filename = os.path.join(OUTPUT_PATH, f"FINAL_RECORDING_{timestamp}.mp4")
                    if video_queue:
                        last_segment = video_queue[-1]
                        merged_frames = last_segment + event_frames
                        save_video_worker(merged_frames, merged_filename, FPS)
                    else:
                        save_video_worker(event_frames, merged_filename, FPS)
                    is_recording_event = False
                    event_frames = []

            # Display & Controls
            cv2.imshow("Dashcam + Face Detect", annotated_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                break

            # FPS governor
            elapsed = time.time() - loop_start
            target = 1.0 / FPS
            if elapsed < target:
                time.sleep(target - elapsed)

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Recording stopped.")

# ================= MAIN =================
if __name__ == "__main__":
    face_detection_video()
    