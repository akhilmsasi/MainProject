import cv2
import collections
import datetime
import time
import os
from utils import get_db_connection, RecordingState, OUTPUT_PATH

def run_recorder():
    cap = cv2.VideoCapture(0)
    
    # FPS Calculation variables
    prev_frame_time = 0
    new_frame_time = 0
    
    # Buffering Logic
    target_fps = 20.0 
    pre_buffer_limit = int(30 * target_fps)
    total_limit = int(60 * target_fps)
    
    pre_buffer = collections.deque(maxlen=pre_buffer_limit)
    active_frames = []
    is_recording = False
    current_event = 0

    print("📹 Recorder Service: Buffering 30s. Auto-reset enabled.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        # 1. Calculate FPS for display only
        new_frame_time = time.time()
        fps_display = 1 / (new_frame_time - prev_frame_time) if (new_frame_time - prev_frame_time) > 0 else 0
        prev_frame_time = new_frame_time
        fps_text = f"FPS: {int(fps_display)}"

        # 2. Database Status Check
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, EventType FROM recording_status LIMIT 1")
            row = cursor.fetchone()
            conn.close()

            db_status = row['status'] if row else 0
            event_type = row['EventType'] if row else 0

            # --- START TRIGGER ---
            if db_status == 1 and not is_recording:
                print(f"🔴 Trigger Detected! Event: {RecordingState(event_type).name}")
                is_recording = True
                current_event = event_type
                active_frames = list(pre_buffer) 

            # --- STOP/SAVE TRIGGER (Manual Stop or 60s Limit) ---
            elif is_recording and (db_status == 0 or len(active_frames) >= total_limit):
                reason = "Manual Stop" if db_status == 0 else "60s Time Limit Reached"
                print(f"⏹ Saving Video ({reason}). Total Frames: {len(active_frames)}")
                
                save_video(active_frames, current_event)
                
                # IMPORTANT: Reset everything back to 0 in DB and Local State
                is_recording = False
                active_frames = []
                reset_db_full() 

        except Exception as e:
            print(f"DB Error: {e}")

        # 3. Frame Management (Save CLEAN frames)
        clean_frame = frame.copy()
        if is_recording:
            active_frames.append(clean_frame)
        else:
            pre_buffer.append(clean_frame)

        # 4. UI Display (FPS Overlay on Preview Only)
        display_frame = frame.copy()
        cv2.putText(display_frame, fps_text, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        cv2.imshow("Secure360 - Live Monitor", display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

def save_video(frames, event_type):
    if not frames: return
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    label = RecordingState(event_type).name
    filename = os.path.join(OUTPUT_PATH, f"{label}_{timestamp}.mp4")
    
    h, w, _ = frames[0].shape
    out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h))
    for f in frames: 
        out.write(f)
    out.release()
    print(f"✅ Saved: {filename}")

def reset_db_full():
    """Sets both status=0 and EventType=0 in the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # No WHERE id=1 needed as per your requirement
        cursor.execute("UPDATE recording_status SET status = 0, EventType = 0")
        conn.commit()
        conn.close()
        print("🔄 Database Reset: Status=0, Event=0")
    except Exception as e:
        print(f"❌ Failed to reset DB: {e}")

if __name__ == "__main__":
    run_recorder()