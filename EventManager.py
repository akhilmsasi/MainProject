import cv2
import collections
import time
import datetime
import os
import mysql.connector

# ================= CONFIGURATION =================
OUTPUT_PATH = r"C:/xampp/htdocs/Videos"
FPS = 30
BUFFER_DURATION = 30   # seconds
BUFFER_SIZE = FPS * BUFFER_DURATION

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",          # change if needed
    "password": "",          # set your MySQL password
    "database": "secure360"
}

os.makedirs(OUTPUT_PATH, exist_ok=True)

# ================= HELPERS =================
def save_video(frames, filename, fps=30):
    if not frames:
        return
    h, w, _ = frames[0].shape
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, (w, h))
    for f in frames:
        out.write(f)
    out.release()
    print(f"\n✅ Saved video: {os.path.basename(filename)}")
     # Upload file path to DB
    insert_incident(filename)
def get_recording_status():
    """Check the recording_status table for status value."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM recording_status WHERE id = 1 LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        if result:
            return int(result[0])
        return 0
    except Exception as e:
        print("DB Error:", e)
        return 0

def insert_incident(filepath):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Example values for other fields
        incident_id = "INC_" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        incident_date = datetime.date.today()
        incident_time = datetime.datetime.now().strftime("%H:%M:%S")
        title = "Video Recording Event"
        city = "Thiruvananthapuram"
        road = "Unknown Road"

        query = """
        INSERT INTO incidentrecords 
        (id, incident_date, incident_time, title, placeCityName, roadName, filepath) 
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        values = (incident_id, incident_date, incident_time, title, city, road, filepath)

        cursor.execute(query, values)
        conn.commit()
        conn.close()

        print("✅ Incident record inserted with video path:", filepath)

    except Exception as e:
        print("❌ DB Insert Error:", e)

# ================= MAIN RECORDING LOOP =================
def recording_loop():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    is_recording = False
    event_frames = []
    event_start_time = None

    print("System Started.")
    print("Recording will start when MySQL status=1.")
    print("Recording will stop when MySQL status=0.")
    print("Press 'q' or 'ESC' to quit manually.")

    try:
        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                continue

            status = get_recording_status()

            if status == 1 and not is_recording:
                is_recording = True
                event_start_time = time.time()
                event_frames = []
                print("\n🔴 Recording started because status=1...")

            if status == 0 and is_recording:
                print("⏹ Recording stopped because status=0.")
                if event_frames:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = os.path.join(OUTPUT_PATH, f"RECORDING_{timestamp}.mp4")
                    save_video(event_frames, filename, FPS)
                is_recording = False
                event_frames = []

            if is_recording:
                event_frames.append(frame)
                if time.time() - event_start_time >= BUFFER_DURATION:
                    print("📢 Recording finished (time limit). Saving...")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    filename = os.path.join(OUTPUT_PATH, f"RECORDING_{timestamp}.mp4")
                    save_video(event_frames, filename, FPS)
                    is_recording = False
                    event_frames = []

            cv2.imshow("MySQL Controlled Recording", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord('q'):
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Recording stopped.")
        
# ================= RUN =================
if __name__ == "__main__":
    recording_loop()