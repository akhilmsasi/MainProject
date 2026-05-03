import cv2
import os
import datetime
import time
import collections
import threading
import firebase_admin
from firebase_admin import db, storage
from ai_engine import MultiObjectMotionDetectionEngine

# --- CONFIGURATION ---
# Initialize Firebase
if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://fir-7211b-default-rtdb.firebaseio.com/',
        # Use the URL you just found in the console:
        'storageBucket': 'fir-7211b.firebasestorage.app' 
    })

# Paths
OUTPUT_PATH = r"C:/xampp/htdocs/Videos"
PROTOTXT_PATH = r"C:\Users\ASHNA\Documents\MainProject\MainProject\models\deploy.prototxt"
MODEL_PATH = r"C:\Users\ASHNA\Documents\MainProject\MainProject\models\mobilenet_iter_73000.caffemodel"

# Settings
FPS = 30
BUFFER_SECONDS = 30
RECORD_SECONDS = 30
TOTAL_DURATION = BUFFER_SECONDS + RECORD_SECONDS

def save_and_sync_worker(frames, event_name, event_type, user_id):
    """Saves video locally, uploads to Firebase Storage, and updates DB."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{event_name}_{timestamp}.mp4"
        local_path = os.path.join(OUTPUT_PATH, filename)
        
        # 1. Save Video Locally
        if frames:
            h, w, _ = frames[0].shape
            out = cv2.VideoWriter(local_path, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (w, h))
            for f in frames: out.write(f)
            out.release()
            print(f"✅ Video Saved locally: {local_path}")

        # 2. Setup Firebase
        event_key = f"{event_name}_{timestamp}"
        db_ref = db.reference(f'users/{user_id}/Events/{event_key}')
        
        # Initial DB Status
        db_ref.set({
            "title": event_name,
            "incidentType": int(event_type),
            "upload_progress": 0,
            "fileUploadedStatus": 0,
            "filepath": "Uploading..."
        })

        # 3. Upload to Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(f"Videos/{user_id}/{filename}")
        
        print(f"🚀 Starting Upload: {filename}")
        blob.upload_from_filename(local_path)
        
        # Make public and get URL
        blob.make_public()
        video_url = blob.public_url
        
        # 4. Finalize DB Sync
        db_ref.update({
            "filepath": video_url,
            "fileUploadedStatus": 100,
            "upload_progress": 100
        })
        print(f"✅ Upload Complete. URL: {video_url}")

    except Exception as e:
        print(f"❌ Worker Error: {e}")

def run_service():
    ai_logic = MultiObjectMotionDetectionEngine(PROTOTXT_PATH, MODEL_PATH)
    cap = cv2.VideoCapture(0)
    history_buffer = collections.deque(maxlen=FPS * BUFFER_SECONDS)
    
    is_recording = False
    recording_start_time = 0
    event_frames = []
    current_name, current_type = "", 0

    print("🚀 Monitoring Active...")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            history_buffer.append(frame.copy())
            detections = ai_logic.detect_objects(frame)
            motion_detected = len(detections) > 0
            
            if not is_recording and motion_detected:
                is_recording = True
                recording_start_time = time.time()
                event_frames = list(history_buffer)
                
                obj = detections[0]
                current_name = f"MOTION_{obj['class_name']}"
                current_type = 2
                print(f"🎥 Event Triggered: {current_name}")

            elif is_recording:
                event_frames.append(frame.copy())
                
                if (time.time() - recording_start_time) >= TOTAL_DURATION:
                    threading.Thread(
                        target=save_and_sync_worker,
                        args=(list(event_frames), current_name, current_type, "akhil")
                    ).start()
                    
                    is_recording = False
                    event_frames = []

            cv2.imshow("Secure360 - Live View", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_service()