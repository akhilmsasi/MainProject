import cv2
import collections
import time
import datetime
import os
import threading
from ai_engine import FaceDetectionEngine  # <--- IMPORTING YOUR AI LOGIC
from visualize import visualize
from utils import (
    get_db_connection, 
    OUTPUT_PATH, 
    insert_incident_record,
    RecordingState,
    TVM_LOCATIONS
)

# Configuration
MODEL_PATH = r"C:/Users/ASHNA/Documents/Ashna/Project Report/ProjectWork/Backend_code/blaze_face_short_range.tflite"
FPS = 30
BUFFER_DURATION = 30 

def save_and_sync_worker(frames, event_name, event_type, username):
    """Background task to save MP4 and update SQL/Firebase."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        record_id = f"{event_name}_{timestamp}"
        local_path = os.path.join(OUTPUT_PATH, f"{record_id}.mp4")
        
        h, w, _ = frames[0].shape
        out = cv2.VideoWriter(local_path, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (w, h))
        for f in frames: out.write(f)
        out.release()
        
        import random
        loc = random.choice(TVM_LOCATIONS)
        insert_incident_record(
            record_id=record_id, incident_dt=datetime.datetime.now(),
            title=f"Alert: {event_name}", locationLat=loc[0], locationLong=loc[1],
            placeCityName=loc[2], roadName=loc[3], 
            vehicleSpeed=random.uniform(20, 50),
            incidentType=int(event_type), gear=0, 
            filepath=local_path, username=username
        )
        print(f"✅ Event Saved & Synced: {record_id}")
    except Exception as e:
        print(f"❌ Worker Error: {e}")

def run_service(username="akhil"):
    # Initialize the AI from the other file
    ai_logic = FaceDetectionEngine(MODEL_PATH)
    
    cap = cv2.VideoCapture(0)
    history_buffer = collections.deque(maxlen=FPS * BUFFER_DURATION)
    
    is_recording = False
    event_start_time = 0
    event_frames = []
    current_name, current_type = "", 0

    print(f"🚀 Service Running for {username}...")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret: break

            # 1. Use the AI Logic from ai_engine.py
            face_detected, detection_result = ai_logic.check_for_face(frame)
            
            # 2. Add boxes (visualize)
            annotated_frame = visualize(frame, detection_result)
            history_buffer.append(annotated_frame.copy())

            if not is_recording:
                # Check DB for manual trigger
                db_trigger = False
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT status, EventType FROM recording_status LIMIT 1")
                    row = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    if row and row['status'] == 1:
                        db_trigger = True
                        current_type = row['EventType']
                        current_name = RecordingState(current_type).name
                except: pass

                if face_detected or db_trigger:
                    is_recording = True
                    event_start_time = time.time()
                    if face_detected:
                        current_name, current_type = "AI_FACE_DETECT", 2
                    
                    print(f"🔔 TRIGGER: {current_name}")
                    # Capture the "Past" 30 seconds
                    event_frames = list(history_buffer)
            else:
                # Capture the "Future" 30 seconds
                event_frames.append(annotated_frame.copy())
                
                if time.time() - event_start_time >= BUFFER_DURATION:
                    # Save the full 60s video (buffered past + captured future)
                    threading.Thread(
                        target=save_and_sync_worker, 
                        args=(list(event_frames), current_name, current_type, username)
                    ).start()
                    is_recording = False

            cv2.imshow("Secure360 Monitor", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_service("akhil")