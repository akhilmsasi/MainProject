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
    TVM_LOCATIONS,
    resume_pending_uploads
)

# Configuration
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "blaze_face_short_range.tflite")
FPS = 30
BUFFER_DURATION = 30

# Sentinel file written by the GUI to request a graceful shutdown
STOP_FLAG = os.path.join(os.path.dirname(__file__), ".stop_recording")

def _set_db_recording_status(status, event_type=0):
    """Write recording state to MySQL so the GUI poll can read it."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE recording_status SET status=%s, EventType=%s",
            (int(status), int(event_type))
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[RecordingService] DB status update failed: {e}")

def is_event_enabled(event_type):
    """
    Checks the 'event_status' table. 
    Uses rollback() to ensure it sees live changes from the GUI/PHPMyAdmin.
    For normal and crash events, always return True.
    """
    try:
        # Always active for normal and crash events
        if event_type in [1, 3]:  # Assuming 1 = Normal, 3 = Crash
            return True

        conn = get_db_connection()
        # CRITICAL: Forces the connection to see external updates
        conn.rollback() 
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT Eventstatus FROM event_status WHERE Eventtype = %s", (int(event_type),))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row is not None and row['Eventstatus'] == 1
    except Exception as e:
        print(f"[RecordingService] Feature gate check failed: {e}")
        return False

def save_and_sync_worker(frames, event_name, event_type, username):
    """Background task to save MP4, update SQL, and start Firebase upload."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        record_id = f"{event_name}_{timestamp}"
        local_path = os.path.join(OUTPUT_PATH, f"{record_id}.mp4")
        
        h, w, _ = frames[0].shape
        out = cv2.VideoWriter(local_path, cv2.VideoWriter_fourcc(*'mp4v'), FPS, (w, h))
        for f in frames: out.write(f)
        out.release()

        # Log the file path to verify it was saved correctly
        if os.path.exists(local_path):
            print(f"✅ File saved successfully: {local_path}")
        else:
            print(f"❌ File not found after saving: {local_path}")
            return
        
        import random
        loc = random.choice(TVM_LOCATIONS)
        # Extract only the filename from the local_path
        video_filename = os.path.basename(local_path)
        insert_incident_record(
            record_id=record_id, incident_dt=datetime.datetime.now(),
            title=f"Alert: {event_name}", locationLat=loc[0], locationLong=loc[1],
            placeCityName=loc[2], roadName=loc[3], 
            vehicleSpeed=random.uniform(20, 50),
            incidentType=int(event_type), gear=0, 
            filepath=video_filename, username=username
        )
        print(f"✅ Event Saved & Synced: {record_id}")

        # Start uploading to Firebase immediately
        threading.Thread(target=upload_video_to_cloud, args=(record_id, local_path, username), daemon=True).start()
        print(f"🚀 Upload started for {record_id}")
    except Exception as e:
        print(f"❌ Worker Error: {e}")

def run_service(username="akhil"):
    # Clear any stale stop flag from a previous session
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)

    # Resume any pending uploads
    resume_pending_uploads()
    
    # Initialize the AI logic
    ai_logic = FaceDetectionEngine(MODEL_PATH)
    
    cap = cv2.VideoCapture(0)
    history_buffer = collections.deque(maxlen=FPS * BUFFER_DURATION)
    
    is_recording = False
    event_start_time = 0
    event_frames = []
    current_name, current_type = "", 0

    # --- Camera-on overlay state ---
    _frame_count = 0
    _dot_bright = True

    # Reset recording status
    _set_db_recording_status(0, 0)

    print(f"🚀 Secure360 Service Running for {username}...")

    try:
        while cap.isOpened():
            if os.path.exists(STOP_FLAG):
                os.remove(STOP_FLAG)
                print("🛑 Shutdown requested.")
                break

            ret, frame = cap.read()
            if not ret: break

            # 1. Constant AI Monitoring
            face_detected, detection_result = ai_logic.check_for_face(frame)
            
            # 2. Visualization
            annotated_frame = visualize(frame, detection_result)
            history_buffer.append(annotated_frame.copy())

            if not is_recording:
                # 3. Fresh check for DB triggers (Honk/Brake/Alarm)
                db_trigger = False
                manual_event_type = 0
                try:
                    conn = get_db_connection()
                    conn.rollback() # Ensure we see fresh manual triggers
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT status, EventType FROM recording_status LIMIT 1")
                    row = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    if row and row['status'] == 1:
                        db_trigger = True
                        manual_event_type = row['EventType']
                except: pass

                # --- DYNAMIC FEATURE GATING ---
                
                # Case 1: Face Detection Logic
                if face_detected:
                    # Always monitor, but only record if DB says enabled (Type 2)
                    if is_event_enabled(2):
                        is_recording = True
                        current_type = 2
                        current_name = "AI_FACE_DETECT"
                
                # Case 2: Manual Trigger Logic (Types 3, 4, 5)
                elif db_trigger:
                    # Only record if the triggered event is enabled in DB
                    if is_event_enabled(manual_event_type):
                        is_recording = True
                        current_type = manual_event_type
                        current_name = RecordingState(current_type).name
                    else:
                        print(f"⚠️ Trigger {manual_event_type} ignored: Feature is disabled in DB.")
                        _set_db_recording_status(0, 0) # Clear the trigger

                if is_recording:
                    event_start_time = time.time()
                    print(f"🔔 RECORDING INITIATED: {current_name}")
                    _set_db_recording_status(1, current_type)
                    event_frames = list(history_buffer)
            
            else:
                event_frames.append(annotated_frame.copy())

                if time.time() - event_start_time >= BUFFER_DURATION:
                    threading.Thread(
                        target=save_and_sync_worker,
                        args=(list(event_frames), current_name, current_type, username)
                    ).start()
                    is_recording = False
                    _set_db_recording_status(0, 0)

            # ── Camera-on overlay ──
            display_frame = annotated_frame.copy()
            h_f, w_f = display_frame.shape[:2]
            dot_cx, dot_cy, dot_r = w_f - 18, 18, 8
            font, font_scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1

            if is_recording:
                _frame_count += 1
                if _frame_count % 15 == 0: _dot_bright = not _dot_bright
                dot_color = (0, 30, 220) if _dot_bright else (0, 10, 120)
                label, text_color = "REC LIVE", dot_color
            else:
                _frame_count, _dot_bright = 0, True
                dot_color, label, text_color = (0, 180, 0), "CAM ON", (0, 180, 0)

            cv2.circle(display_frame, (dot_cx, dot_cy), dot_r + 3, (20, 20, 20), -1)
            cv2.circle(display_frame, (dot_cx, dot_cy), dot_r, dot_color, -1)
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, thickness)
            tx, ty = dot_cx - dot_r - tw - 6, dot_cy + th // 2
            cv2.rectangle(display_frame, (tx - 3, ty - th - 3), (tx + tw + 3, ty + 3), (30, 30, 30), -1)
            cv2.putText(display_frame, label, (tx, ty), font, font_scale, text_color, thickness, cv2.LINE_AA)

            cv2.imshow("Secure360 Monitor", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_service("akhil")