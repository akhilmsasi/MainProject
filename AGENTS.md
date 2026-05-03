# Secure360 Agent Notes

## Purpose
This file gives agents a concise, shared understanding of the Secure360 repository. Keep it updated with notable findings.

## Project Summary
Secure360 is a Python desktop control panel plus background services for video capture, AI face detection, and incident logging. It integrates a local MySQL database (XAMPP) with Firebase Realtime Database and Storage to sync recording status and upload incident videos with progress.

## Core Entry Points
- main_gui.py: Tkinter control panel. Starts/stops services, toggles events, syncs status, and shows Userdetails from MySQL.
- recording_service.py: Webcam capture loop with rolling buffer and AI trigger; saves event clips and writes incidents.
- data_monitor.py: Simple polling monitor for recording_status changes in MySQL.

## Key Modules
- ai_engine.py: MediaPipe face detection wrapper (blaze_face_short_range.tflite).
- firebase_manager.py: Uploads video to Firebase Storage and writes metadata to RTDB.
- utils.py: Central config (DB_CONFIG, OUTPUT_PATH), DB schema creation, SQL<->Firebase sync helpers, and upload progress tracking.
- visualize.py: Draws detection boxes/keypoints on frames.

## Data Flow (High Level)
1. GUI toggles status or event type -> writes to MySQL and Firebase per-user recording_status.
2. recording_service.py polls MySQL recording_status and also checks AI face detection.
3. When triggered, it saves a buffered clip, writes incidentrecords in MySQL, and pushes event metadata to Firebase.
4. Background upload streams the video to Firebase Storage and updates progress in RTDB and SQL.

## Storage and Schemas
- MySQL database: secure360
  - Userdetails
  - incidentrecords
  - event_status
  - recording_status (single-row global status)
  - user_recording_status (per-user mirror)
- Firebase RTDB paths:
  - /users/{username}/recording_status
  - /users/{username}/Events/{record_id}
  - /connection_test
- Firebase Storage bucket configured in utils.py

## Setup Notes
- Dependencies in setup/requirements.txt; install via setup/install.py.
- Requires a webcam, MySQL (XAMPP) running, and valid Firebase serviceAccountKey.json.
- MODEL_PATH points to models/blaze_face_short_range.tflite.
- OUTPUT_PATH defaults to C:/xampp/htdocs/Videos.

## Debug/Utility Scripts
- debug_update.py: Exercises DB init and per-user recording_status update.
- debug_firebase_test.py, test_fb.py: Firebase connectivity checks.

## Agent Instructions
- If you discover new behavior, config, or risk, add a brief bullet under Agent Notes.
- Keep updates concise (1-3 bullets) and include file names when relevant.
- Avoid duplicating existing bullets unless behavior changed.

## Agent Notes
- (Add new findings to this file and always keep this file update to date with the current status of the project, but do not spam this file with too much information.)
