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
    # Clear any stale stop flag from a previous session
    if os.path.exists(STOP_FLAG):
        os.remove(STOP_FLAG)

    # Resume any pending uploads
    resume_pending_uploads()
    
    # Initialize the AI from the other file
    ai_logic = FaceDetectionEngine(MODEL_PATH)
    
    cap = cv2.VideoCapture(0)
    history_buffer = collections.deque(maxlen=FPS * BUFFER_DURATION)
    
    is_recording = False
    event_start_time = 0
    event_frames = []
    current_name, current_type = "", 0

    # --- Camera-on overlay state (display only, never saved) ---
    _frame_count = 0          # used to pulse the indicator dot
    _dot_bright = True        # toggles between bright/dark red

    # Reset any stale recording status left from a previous session
    _set_db_recording_status(0, 0)

    print(f"🚀 Service Running for {username}...")

    try:
        while cap.isOpened():
            # Graceful shutdown: GUI wrote the stop flag → exit cleanly
            if os.path.exists(STOP_FLAG):
                os.remove(STOP_FLAG)
                print("🛑 Stop flag detected — shutting down recording service.")
                break

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
                    # Tell the GUI we are now recording
                    _set_db_recording_status(1, current_type)
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
                    # Tell the GUI recording has finished
                    _set_db_recording_status(0, 0)

            # ── Camera-on overlay (display copy only – NOT saved to video) ──
            display_frame = annotated_frame.copy()

            h_f, w_f = display_frame.shape[:2]
            dot_cx, dot_cy = w_f - 18, 18
            dot_r = 8
            font       = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.45
            thickness  = 1

            if is_recording:
                # Pulsing red dot + "REC LIVE"
                _frame_count += 1
                if _frame_count % 15 == 0:
                    _dot_bright = not _dot_bright
                dot_color  = (0, 30, 220) if _dot_bright else (0, 10, 120)  # BGR red
                label      = "REC LIVE"
                text_color = dot_color
            else:
                # Static green dot + "CAM ON"
                _frame_count = 0
                _dot_bright  = True
                dot_color  = (0, 180, 0)   # BGR green
                label      = "CAM ON"
                text_color = dot_color

            # Glow ring behind dot
            cv2.circle(display_frame, (dot_cx, dot_cy), dot_r + 3, (20, 20, 20), -1)
            # Main dot
            cv2.circle(display_frame, (dot_cx, dot_cy), dot_r, dot_color, -1)

            # Label with dark background pill
            (tw, th), _ = cv2.getTextSize(label, font, font_scale, thickness)
            tx = dot_cx - dot_r - tw - 6
            ty = dot_cy + th // 2
            cv2.rectangle(display_frame,
                          (tx - 3, ty - th - 3),
                          (tx + tw + 3, ty + 3),
                          (30, 30, 30), -1)
            cv2.putText(display_frame, label, (tx, ty), font, font_scale, text_color, thickness, cv2.LINE_AA)
            # ── end overlay ──

            cv2.imshow("Secure360 Monitor", display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_service("akhil")