import cv2
import collections
import datetime
import time
import os
from utils import get_db_connection, RecordingState, OUTPUT_PATH

def run_recorder():
    cap = cv2.VideoCapture(0)
    fps = 20.0  # Adjust based on your actual webcam speed
    pre_buffer_limit = int(30 * fps)
    total_limit = int(60 * fps)
    
    pre_buffer = collections.deque(maxlen=pre_buffer_limit)
    active_frames = []
    is_recording = False
    current_event = 0

    print("📹 Recorder Service: Buffering 30s. No ID check active.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        try:
            # Direct access to columns without WHERE id=1
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, EventType FROM recording_status LIMIT 1")
            row = cursor.fetchone()
            conn.close()

            db_status = row['status'] if row else 0
            event_type = row['EventType'] if row else 0

            # --- START TRIGGER ---
            if db_status == 1 and not is_recording:
                print("🔴 Start signal detected. Merging 30s buffer...")
                is_recording = True
                current_event = event_type
                active_frames = list(pre_buffer) # Copy past 30s

            # --- STOP TRIGGER (Manual or Auto-limit) ---
            elif is_recording and (db_status == 0 or len(active_frames) >= total_limit):
                print(f"⏹ Saving {len(active_frames) / fps:.1f}s of video...")
                save_video(active_frames, current_event)
                
                # Reset
                is_recording = False
                active_frames = []
                reset_db_status() # Force status back to 0 if it was a time limit

        except Exception as e:
            print(f"Recorder DB Error: {e}")

        # Frame Logic
        if is_recording:
            active_frames.append(frame)
        else:
            pre_buffer.append(frame)

        # Show feed with status indicator
        if is_recording:
            cv2.putText(frame, "RECORDING", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        
        cv2.imshow("Secure360 - Recording Service", frame)
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
    for f in frames: out.write(f)
    out.release()
    print(f"✅ File Saved: {filename}")

def reset_db_status():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE recording_status SET status = 0")
        conn.commit()
        conn.close()
    except: pass

if __name__ == "__main__":
    run_recorder()