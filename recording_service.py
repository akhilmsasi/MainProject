import cv2
import collections
import datetime
import time
import os
import random
import mediapipe as mp
from face_detection.visualize import visualize
from utils import get_db_connection, RecordingState, OUTPUT_PATH, TVM_LOCATIONS

def save_video(frames, event_type_val):
    if not frames: 
        print("⚠️ No frames to save.")
        return
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT gear FROM recording_status LIMIT 1")
        row = cursor.fetchone()
        current_gear = row['gear'] if row else 0

        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        event_name = RecordingState(event_type_val).name
        video_id = f"{event_name}_{timestamp}"
        filename = os.path.join(OUTPUT_PATH, f"{video_id}.mp4")
        
        h, w, _ = frames[0].shape
        out = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*'mp4v'), 20.0, (w, h))
        for f in frames: 
            out.write(f)
        out.release()
        print(f"DEBUG: Video file created at {filename}")

        loc_data = random.choice(TVM_LOCATIONS)
        lat, lng, place, road = loc_data[0], loc_data[1], loc_data[2], loc_data[3]
        speed = random.randint(40, 90)

        sql = """INSERT INTO incidentrecords 
                 (id, incident_date, incident_time, title, locationLat, locationLong, 
                  fileUploadedStatus, placeCityName, roadName, vehicleSpeed, 
                  incidentType, gear, filepath, created_at) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        values = (video_id, now.date(), now.strftime("%H:%M:%S"), event_name, 
                  lat, lng, 0, place, road, speed, event_type_val, 
                  current_gear, filename, now)
        
        cursor.execute(sql, values)
        conn.commit()
        print(f"✅ SUCCESS: Incident {video_id} logged at {place}")
        conn.close()
    except Exception as e:
        print(f"❌ CRITICAL ERROR in save_video: {e}")

def reset_db_status():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE recording_status SET status = 0, EventType = 0")
        conn.commit()
        conn.close()
        print("🔄 Database Reset: Status=0, Event=0")
    except Exception as e:
        print(f"Reset Error: {e}")

def run_recorder():
    # Initialize MediaPipe Face Detector
    BaseOptions = mp.tasks.BaseOptions
    FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
    FaceDetector = mp.tasks.vision.FaceDetector
    VisionRunningMode = mp.tasks.vision.RunningMode

    # The model path based on the structure provided
    model_path = os.path.join(os.path.dirname(__file__), 'face_detection', 'blaze_face_short_range.tflite')
    
    options = FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.IMAGE
    )
    detector = FaceDetector.create_from_options(options)
    
    cap = cv2.VideoCapture(0)
    prev_frame_time = 0
    target_fps = 20.0
    pre_buffer_limit = int(30 * target_fps)
    total_limit = int(60 * target_fps)
    
    pre_buffer = collections.deque(maxlen=pre_buffer_limit)
    active_frames = []
    is_recording = False
    current_event = 0
    face_detection_active = False

    print("📹 Recorder Service: ACTIVE.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

        # --- FIX: Define h and w here ---
        h, w, _ = frame.shape 

        new_frame_time = time.time()
        fps_val = 1 / (new_frame_time - prev_frame_time) if (new_frame_time - prev_frame_time) > 0 else 0
        prev_frame_time = new_frame_time

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, EventType FROM recording_status LIMIT 1")
            row = cursor.fetchone()
            conn.close()

            db_status = row['status'] if row else 0
            event_type = row['EventType'] if row else 0

            if db_status == 1 and not is_recording:
                print(f"🔴 RECORDING TRIGGERED! Event: {RecordingState(event_type).name}")
                is_recording = True
                current_event = event_type
                active_frames = list(pre_buffer)

            elif is_recording and (db_status == 0 or len(active_frames) >= total_limit):
                save_video(active_frames, current_event)
                is_recording = False
                active_frames = []
                reset_db_status()

            # --- Check face detection toggle from event_status table ---
            cursor.execute("SELECT Eventstatus FROM event_status WHERE Eventtype = 2 LIMIT 1")
            face_row = cursor.fetchone()
            if face_row:
                # PhpMyAdmin sometimes returns 1/0 for INT fields
                face_detection_active = bool(face_row['Eventstatus'])
            else:
               face_detection_active = False

        except Exception as e:
            print(f"DB Loop Error: {e}")

        clean_frame = frame.copy()
        if is_recording:
            active_frames.append(clean_frame)
        else:
            pre_buffer.append(clean_frame)

        display_frame = frame.copy()
        cv2.putText(display_frame, f"FPS: {int(fps_val)}", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        # --- Apply Face Detection if active ---
        if face_detection_active:
            # Convert frame to mp.Image format
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=display_frame)
            detection_result = detector.detect(mp_image)
            # Visualize bounding boxes and keypoints on the image
            display_frame = visualize(display_frame, detection_result)
        
        if is_recording:
            # Now 'w' is defined correctly
            cv2.circle(display_frame, (w - 30, 30), 10, (0, 0, 255), -1)

        cv2.imshow("Secure360 - Live Monitor", display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_recorder()