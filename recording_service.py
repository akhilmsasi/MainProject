import cv2
import collections
import datetime
import time
import os
from utils import get_db_connection, RecordingState, OUTPUT_PATH

def save_buffer(frames, event_type_val):
    if not frames: return
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    label = RecordingState(event_type_val).name
    filename = os.path.join(OUTPUT_PATH, f"{label}_{timestamp}.mp4")
    
    h, w, _ = frames[0].shape
    out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h))
    for f in frames: out.write(f)
    out.release()
    print(f"💾 Video Saved: {filename}")

def run_recorder():
    cap = cv2.VideoCapture(0)
    # 20 FPS * 30 Seconds = 600 frames
    buffer = collections.deque(maxlen=600) 
    
    print("📹 Recording Service Active. Buffering...")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        
        buffer.append(frame)

        # Check DB to see if we need to dump the buffer to a file
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, EventType FROM recording_status")
            row = cursor.fetchone()
            
            if row and row['status'] == 1:
                print(f"🚨 Record Triggered! Event: {RecordingState(row['EventType']).name}")
                save_buffer(list(buffer), row['EventType'])
                
                # RESET status so we don't record the same 30s over and over
                cursor.execute("UPDATE recording_status SET status = 0")
                conn.commit()
            
            conn.close()
        except Exception as e:
            print(f"Recorder DB Error: {e}")

        cv2.imshow("Secure360 Buffer (Live)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_recorder()