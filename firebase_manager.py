from utils import db_ref, bucket, RecordingState
import datetime

class FirebaseManager:
    def __init__(self):
        self.status_ref = db_ref.child('recording_status')
        self.incident_ref = db_ref.child('incident_records')

    def update_cloud_status(self, status, event_type, gear):
        """Updates the real-time triggers in Firebase."""
        try:
            self.status_ref.update({
                'status': status,
                'EventType': event_type,
                'gear': gear
            })
            return True
        except Exception as e:
            print(f"☁️ Firebase Status Error: {e}")
            return False

    def upload_incident(self, video_id, local_path, meta_data):
        """Uploads video to Storage and pushes metadata to Realtime DB."""
        try:
            # 1. Upload Video to Storage
            blob = bucket.blob(f"recordings/{video_id}.mp4")
            blob.upload_from_filename(local_path)
            blob.make_public()
            
            # 2. Add Public URL to metadata
            meta_data['videoUrl'] = blob.public_url
            meta_data['cloud_synced_at'] = datetime.datetime.now().isoformat()

            # 3. Push to Realtime Database
            self.incident_ref.child(video_id).set(meta_data)
            print(f"🚀 Firebase: {video_id} is now live in the cloud.")
            return blob.public_url
        except Exception as e:
            print(f"☁️ Firebase Upload Error: {e}")
            return None

    def get_cloud_status(self):
        """One-time fetch of the current cloud status."""
        return self.status_ref.get()