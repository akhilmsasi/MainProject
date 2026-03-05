import mysql.connector
import os
import threading
from enum import IntEnum
import firebase_admin
from firebase_admin import credentials, db, storage

# 1. Define the Enum
class RecordingState(IntEnum):
    NO_RECORDING = 0
    NORMAL_RECORDING = 1
    FACE_DETECTION = 2
    HONK_EVENT = 3
    HARD_BRAKING = 4
    ALARM = 5

try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://fir-7211b-default-rtdb.firebaseio.com/',
        'storageBucket': 'fir-7211b.appspot.com'
    })
except Exception as e:
    print(f"Firebase Init Error: {e}")

# --- THE MISSING VARIABLES ---
db_ref = db.reference('/')
# Configure bucket name explicitly so we can detect missing/incorrect bucket errors early.
BUCKET_NAME = 'fir-7211b.firebasestorage.app'
try:
    bucket = storage.bucket(BUCKET_NAME)
except Exception as e:
    bucket = None
    print(f"Warning: could not access storage bucket '{BUCKET_NAME}': {e}")

# 2. Define the Locations
TVM_LOCATIONS = [
    [8.4889, 76.9440, "East Fort", "MG Road"],
    [8.5464, 76.9063, "Lulu Mall", "NH 66 Bypass"],
    [8.5241, 76.9366, "Pattom", "MC Road"],
    [8.5581, 76.8814, "Technopark Phase 1", "Kazhakkoottam Road"],
    [8.4731, 76.9191, "Shangumugham Beach", "Airport Road"],
    [8.5068, 76.9554, "Vazhuthacaud", "Museum-Bakery Road"],
    [8.5834, 76.8653, "Sainik School", "Kazhakkootam-Kilimanoor Road"],
    [8.4842, 76.9512, "Thampanoor", "Station Road"],
    [8.5300, 76.9200, "Medical College", "Cosmopolitan Hospital Road"],
    [8.4981, 76.9654, "Jagathy", "Thycaud-Jagathy Road"],
    [8.5600, 76.8400, "Kadinamkulam", "Coastal Road"],
    [8.5110, 76.9380, "Palayam", "University College Road"],
    [8.5200, 77.0100, "Vattiyoorkavu", "Central Polytechnic Road"],
    [8.4500, 76.9800, "Vizhinjam Port", "Harbour Road"],
    [8.6000, 76.9200, "Vembayam", "Main Central Road"]
]

# 3. Define Config
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "secure360"
}

OUTPUT_PATH = r"C:/xampp/htdocs/Videos"
os.makedirs(OUTPUT_PATH, exist_ok=True)

# 4. Database Functions
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def initialize_database():
    """Creates the database and tables if they do not exist."""
    try:
        # Connect without DB selected to create it
        temp_config = DB_CONFIG.copy()
        db_name = temp_config.pop("database")
        conn = mysql.connector.connect(**temp_config)
        cursor = conn.cursor()
        
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        cursor.execute(f"USE {db_name}")

        # Incident Records Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidentrecords (
                id VARCHAR(100) PRIMARY KEY,
                incident_date DATE,
                incident_time TIME,
                title VARCHAR(255),
                locationLat DOUBLE DEFAULT 0.0,
                locationLong DOUBLE DEFAULT 0.0,
                fileUploadedStatus INT DEFAULT 0,
                upload_progress INT DEFAULT 0,
                placeCityName VARCHAR(100),
                roadName VARCHAR(100),
                vehicleSpeed FLOAT DEFAULT 0.0,
                incidentType INT DEFAULT 0,
                gear INT DEFAULT 0,
                filepath VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Event Status Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_status (
                Eventtype INT DEFAULT 0,
                Eventstatus INT DEFAULT 0
            )
        """)

        # Recording Status Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recording_status (
                status INT DEFAULT 0,
                EventType INT DEFAULT 0,
                gear INT DEFAULT 0
            )
        """)

        # Per-user recording status (stores per-username status mirrored to Firebase)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_recording_status (
                username VARCHAR(100) PRIMARY KEY,
                status INT DEFAULT 0,
                EventType INT DEFAULT 0,
                gear INT DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Insert initial rows if empty
        default_events = [2, 3, 4, 5, 6]
        for event_type in default_events:
            cursor.execute("SELECT COUNT(*) FROM event_status WHERE Eventtype = %s", (event_type,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO event_status (Eventtype, Eventstatus) VALUES (%s, 0)", (event_type,))
                print(f"➕ Added default EventType {event_type} to event_status")


        cursor.execute("SELECT COUNT(*) FROM recording_status")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO recording_status (status, EventType, gear) VALUES (0, 0, 0)")

        conn.commit()
        conn.close()
        print("✅ Database initialization complete.")
    except Exception as e:
        print(f"❌ Database Setup Error: {e}")


def sync_user_recording_status_to_firebase():
    """Ensure each user in the SQL `Userdetails` table has a `recording_status`
    node under `/users/{username}/recording_status` in the Firebase RTDB.

    Behavior / Assumptions:
    - Reads `username` from `Userdetails` in the configured database (secure360).
    - If a user's `/users/{username}/recording_status` node does not exist, this
      function initializes it to the default: {status:0, EventType:0, gear:0}.
    - If the node already exists, it is left unchanged.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM Userdetails")
        rows = cursor.fetchall()
        usernames = [r[0] for r in rows if r and r[0]]
        cursor.close()
        conn.close()

        for uname in usernames:
            try:
                user_ref = db_ref.child('users').child(str(uname))
                status_ref = user_ref.child('recording_status')
                # only initialize if not present
                if not status_ref.get():
                    status_ref.set({"status": 0, "EventType": 0, "gear": 0})
                    print(f"Initialized recording_status for user: {uname}")
                else:
                    print(f"recording_status already present for user: {uname}")
            except Exception as e:
                print(f"Failed to sync user {uname}: {e}")
        print("✅ User recording_status sync complete.")
    except Exception as e:
        print(f"❌ Error while syncing user recording_status to Firebase: {e}")


def write_user_recording_status(username, status=0, event_type=0, gear=0):
    """Write a recording_status object under /users/{username}/recording_status in RTDB."""
    try:
        if not username:
            raise ValueError("username is required")
        # Build partial payload only for the keys that are not None.
        payload = {}
        if status is not None:
            payload['status'] = int(status)
        if event_type is not None:
            payload['EventType'] = int(event_type)
        if gear is not None:
            payload['gear'] = int(gear)

        if not payload:
            # Nothing to update
            print(f"No recording_status fields provided to update for {username}.")
            return True

        # Use update() so we don't overwrite other fields unintentionally
        db_ref.child('users').child(str(username)).child('recording_status').update(payload)
        print(f"Updated recording_status for {username}: {payload}")
        return True
    except Exception as e:
        print(f"Failed to write recording_status for {username}: {e}")
        return False


def update_user_recording_status(username, status=None, event_type=None, gear=None):
    """Update recording status in the SQL `recording_status` table and in Firebase for a user.

    Behavior:
    - Reads the single-row `recording_status` table to get existing values.
    - Updates that table with any provided fields (status/EventType/gear).
    - Writes the computed values to `/users/{username}/recording_status` in Firebase.

    Returns (sql_ok: bool, firebase_ok: bool).
    """
    if not username:
        print("update_user_recording_status: username required")
        return (False, False)

    sql_ok = False
    firebase_ok = False

    # Safe defaults
    existing_status = 0
    existing_event = 0
    existing_gear = 0

    # Read existing (single-row) recording_status
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, EventType, gear FROM recording_status LIMIT 1")
        row = cursor.fetchone()
        if row:
            existing_status = row.get('status') if row.get('status') is not None else 0
            existing_event = row.get('EventType') if row.get('EventType') is not None else 0
            existing_gear = row.get('gear') if row.get('gear') is not None else 0
    except Exception as e:
        print(f"Warning: could not read existing SQL recording_status: {e}")
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Compute new values (prefer provided values)
    try:
        new_status = int(status) if status is not None else int(existing_status)
    except Exception:
        new_status = int(existing_status)
    try:
        new_event = int(event_type) if event_type is not None else int(existing_event)
    except Exception:
        new_event = int(existing_event)
    try:
        new_gear = int(gear) if gear is not None else int(existing_gear)
    except Exception:
        new_gear = int(existing_gear)

    # Write back to the single-row recording_status table
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Ensure at least one row exists; if not, insert
        cursor.execute("SELECT COUNT(*) FROM recording_status")
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute(
                "INSERT INTO recording_status (status, EventType, gear) VALUES (%s, %s, %s)",
                (new_status, new_event, new_gear)
            )
        else:
            cursor.execute(
                "UPDATE recording_status SET status = %s, EventType = %s, gear = %s",
                (new_status, new_event, new_gear)
            )
        conn.commit()
        sql_ok = True
        print(f"Updated SQL recording_status: status={new_status}, EventType={new_event}, gear={new_gear}")
    except Exception as e:
        print(f"Failed to update SQL recording_status: {e}")
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    # Update Firebase per-user recording_status
    try:
        payload = {'status': new_status, 'EventType': new_event, 'gear': new_gear}
        db_ref.child('users').child(str(username)).child('recording_status').update(payload)
        firebase_ok = True
        print(f"Updated Firebase recording_status for {username}: {payload}")
    except Exception as e:
        print(f"Failed to update Firebase recording_status for {username}: {e}")

    return (sql_ok, firebase_ok)


def sync_recording_status_sql_to_firebase(propagate_to_users=False):
    """Sync the local SQL `recording_status` (single-row) into Firebase.

    - Reads the first row from `recording_status` table (status, EventType, gear).
    - Writes it to the RTDB at `/recording_status`.
    - If propagate_to_users=True, also applies the same status to every
      `/users/{username}/recording_status` node (creates if missing).
    Returns True on success, False on failure.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, EventType, gear FROM recording_status LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            print("No recording_status row found in SQL. Skipping sync.")
            return False

        status_val, event_val, gear_val = row[0], row[1], row[2]
        payload = {"status": int(status_val or 0), "EventType": int(event_val or 0), "gear": int(gear_val or 0)}

        # Do NOT write a top-level /recording_status node — only write under users/{username}/recording_status
        if propagate_to_users:
            # fetch usernames and propagate
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT username FROM Userdetails")
                rows = cursor.fetchall()
                cursor.close()
                conn.close()

                usernames = [r[0] for r in rows if r and r[0]]
                for uname in usernames:
                    try:
                        user_ref = db_ref.child('users').child(str(uname)).child('recording_status')
                        user_ref.set(payload)
                        print(f"Propagated recording_status to user {uname}")
                    except Exception as e:
                        print(f"Failed to propagate to {uname}: {e}")
            except Exception as e:
                print(f"Failed to fetch usernames for propagation: {e}")

        else:
            print("sync_recording_status_sql_to_firebase completed — no per-user propagation requested.")

        return True
    except Exception as e:
        print(f"Error syncing recording_status from SQL to Firebase: {e}")
        return False


def insert_incident_record(record_id, incident_dt, title, locationLat=0.0, locationLong=0.0,
                           fileUploadedStatus=0, placeCityName=None, roadName=None,
                           vehicleSpeed=0.0, incidentType=0, gear=0, filepath=None, username=None):
    """Insert a row into `incidentrecords`.

    Parameters:
    - record_id: unique id for the incident (string)
    - incident_dt: a datetime.datetime object representing the incident timestamp
    - title: short title/string for the incident
    - locationLat/locationLong: floats
    - fileUploadedStatus: int flag
    - placeCityName/roadName: optional strings
    - vehicleSpeed: float
    - incidentType: int
    - gear: int
    - filepath: path to the saved video file

    Returns True on success, False on failure.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        sql = ("INSERT INTO incidentrecords (id, incident_date, incident_time, title, locationLat, locationLong, "
               "fileUploadedStatus, placeCityName, roadName, vehicleSpeed, incidentType, gear, filepath, created_at) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

        incident_date = incident_dt.date() if hasattr(incident_dt, 'date') else incident_dt
        incident_time = incident_dt.strftime("%H:%M:%S") if hasattr(incident_dt, 'strftime') else None

        values = (
            str(record_id),
            incident_date,
            incident_time,
            title,
            float(locationLat) if locationLat is not None else 0.0,
            float(locationLong) if locationLong is not None else 0.0,
            int(fileUploadedStatus),
            placeCityName,
            roadName,
            float(vehicleSpeed) if vehicleSpeed is not None else 0.0,
            int(incidentType) if incidentType is not None else 0,
            int(gear) if gear is not None else 0,
            filepath,
            incident_dt
        )

        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ insert_incident_record: inserted {record_id}")
        # Build payload to push to Firebase asynchronously
        try:
            payload = {
                'id': str(record_id),
                'incident_date': str(incident_date),
                'incident_time': incident_time,
                'title': title,
                'locationLat': float(locationLat) if locationLat is not None else 0.0,
                'locationLong': float(locationLong) if locationLong is not None else 0.0,
                'fileUploadedStatus': int(fileUploadedStatus),
                'placeCityName': placeCityName,
                'roadName': roadName,
                'vehicleSpeed': float(vehicleSpeed) if vehicleSpeed is not None else 0.0,
                'incidentType': int(incidentType) if incidentType is not None else 0,
                'gear': int(gear) if gear is not None else 0,
                'filepath': "Null",
                'created_at': str(incident_dt),
                'upload_progress': 0,
                'fileUploadedStatus': int(fileUploadedStatus)
            }

            def _push_worker(uname, rid, pl, local_filepath):
                try:
                    u = uname
                    # If username not provided, pick the first username from Userdetails
                    if not u:
                        try:
                            c = get_db_connection()
                            cur = c.cursor()
                            cur.execute("SELECT username FROM Userdetails LIMIT 1")
                            r = cur.fetchone()
                            cur.close()
                            c.close()
                            if r and r[0]:
                                u = r[0]
                        except Exception as e:
                            print(f"Warning: could not fetch default username for Firebase push: {e}")

                    if not u:
                        print(f"No username available, skipping Firebase push for event {rid}")
                        return

                    # Path: /users/{username}/Events/{record_id}
                    event_ref = db_ref.child('users').child(str(u)).child('Events').child(str(rid))
                    event_ref.set(pl)
                    print(f"✅ Pushed event {rid} to Firebase under users/{u}/Events/{rid}")

                    # If a local filepath was provided, start upload in a separate thread/function
                    if local_filepath:
                        def _upload_worker(path, e_ref, rid_inner, uname_inner):
                            try:
                                # Ensure file exists
                                if not os.path.isfile(path):
                                    print(f"Upload worker: file not found {path}")
                                    try:
                                        e_ref.update({'upload_progress': 0, 'fileUploadedStatus': -1})
                                    except Exception:
                                        pass
                                    # update SQL to indicate failure
                                    # mark SQL row as failed (file missing)
                                    update_incident_upload_status(rid_inner, progress=0, status=-1)
                                    return

                                total_size = os.path.getsize(path)
                                bytes_sent = 0
                                # Use a smaller chunk size to allow finer-grained progress updates
                                chunk_size = 64 * 1024  # 64KB

                                # Destination in storage: Videos/{username}/{record_id}.<ext>
                                if not bucket:
                                    print(f"Upload worker: storage bucket not available, skipping upload for {rid_inner}")
                                    try:
                                        e_ref.update({'upload_progress': 0, 'fileUploadedStatus': -1})
                                    except Exception:
                                        pass
                                    # update SQL to indicate failure due to missing bucket
                                    # mark SQL row as failed (no bucket)
                                    update_incident_upload_status(rid_inner, progress=0, status=-1)
                                    return

                                dest_path = f"Videos/{uname_inner}/{rid_inner}" + os.path.splitext(path)[1]
                                blob = bucket.blob(dest_path)

                                # Try streaming write to storage so we can update progress per chunk.
                                try:
                                    with open(path, 'rb') as f_in:
                                        # Open a writeable file-like object to blob (resumable)
                                        with blob.open("wb") as f_out:
                                            last_progress = -1
                                            while True:
                                                chunk = f_in.read(chunk_size)
                                                if not chunk:
                                                    break
                                                f_out.write(chunk)
                                                bytes_sent += len(chunk)
                                                # Compute percentage and ensure we only update when percentage changes
                                                progress = int((bytes_sent / total_size) * 100)
                                                if progress != last_progress:
                                                    last_progress = progress
                                                    # Print progress locally and update RTDB
                                                    try:
                                                        print(f"Upload progress for {rid_inner}: {progress}%")
                                                    except Exception:
                                                        pass
                                                    try:
                                                        e_ref.update({'upload_progress': progress, 'fileUploadedStatus': 1})
                                                    except Exception as ue:
                                                        print(f"RTDB progress update failed for {rid_inner}: {ue}")
                                                    # update SQL with progress
                                                    # update SQL with progress
                                                    try:
                                                        update_incident_upload_status(rid_inner, progress=progress, status=1)
                                                    except Exception as sqle:
                                                        print(f"SQL progress update failed for {rid_inner}: {sqle}")

                                    # Make blob publicly accessible (optional) and get URL
                                    try:
                                        blob.make_public()
                                        storage_url = blob.public_url
                                    except Exception:
                                        storage_url = f"gs://{bucket.name}/{dest_path}"

                                    # Final update: set filepath to storage url, progress 100 and status 2
                                    def _rt_update_with_retry(ref_obj, payload, retries=3):
                                        import time
                                        attempt = 0
                                        while attempt < retries:
                                            try:
                                                ref_obj.update(payload)
                                                return True
                                            except Exception as eup:
                                                attempt += 1
                                                print(f"RTDB final update attempt {attempt} failed for {rid_inner}: {eup}")
                                                time.sleep(1)
                                        return False

                                    final_payload = {'upload_progress': 100, 'fileUploadedStatus': 2, 'filepath': storage_url}
                                    ok_update = _rt_update_with_retry(e_ref, final_payload, retries=3)
                                    if not ok_update:
                                        print(f"Warning: final RTDB update failed for {rid_inner} after retries")
                                    # update SQL final status
                                    try:
                                        update_incident_upload_status(rid_inner, progress=100, status=2, filepath=storage_url)
                                    except Exception as sqle:
                                        print(f"SQL final update failed for {rid_inner}: {sqle}")

                                    print(f"✅ Upload complete for {rid_inner} -> {storage_url}")
                                except Exception as ex_stream:
                                    # Fall back to a single upload and mark as complete on success
                                    try:
                                        blob.upload_from_filename(path)
                                        try:
                                            blob.make_public()
                                            storage_url = blob.public_url
                                        except Exception:
                                            storage_url = f"gs://{bucket.name}/{dest_path}"
                                        # Final update with retry
                                        final_payload = {'upload_progress': 100, 'fileUploadedStatus': 2, 'filepath': storage_url}
                                        ok_update = _rt_update_with_retry(e_ref, final_payload, retries=3)
                                        if not ok_update:
                                            print(f"Warning: final RTDB update failed for {rid_inner} after fallback upload")
                                        # update SQL final status after fallback
                                        try:
                                            update_incident_upload_status(rid_inner, progress=100, status=2, filepath=storage_url)
                                        except Exception as sqle:
                                            print(f"SQL final update failed for {rid_inner} after fallback: {sqle}")

                                        print(f"✅ Upload (fallback) complete for {rid_inner} -> {storage_url}")
                                    except Exception as ex_upload:
                                        print(f"Upload failed for {rid_inner}: {ex_upload}")
                                        try:
                                            e_ref.update({'fileUploadedStatus': -1})
                                        except Exception as eu:
                                            print(f"Failed to set failure status in RTDB for {rid_inner}: {eu}")
                                        try:
                                            update_incident_upload_status(rid_inner, status=-1)
                                        except Exception as sqle:
                                            print(f"SQL failure status update failed for {rid_inner}: {sqle}")
                            except Exception as e:
                                print(f"Uploader exception for {rid_inner}: {e}")

                        upl_thread = threading.Thread(target=_upload_worker, args=(local_filepath, event_ref, rid, u), daemon=True)
                        upl_thread.start()
                except Exception as e:
                    print(f"Failed to push event {rid} to Firebase: {e}")

            # Start background thread to push to Firebase
            t = threading.Thread(target=_push_worker, args=(username, record_id, payload, filepath), daemon=True)
            t.start()
        except Exception as e:
            print(f"Warning: could not start Firebase push thread: {e}")

        return True
    except Exception as e:
        print(f"❌ insert_incident_record error: {e}")
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return False


def update_incident_upload_status(record_id, progress=None, status=None, filepath=None):
    """Update upload status/filepath for an incident row in SQL.

    Notes:
    - Some installations don't have an `upload_progress` column. To be compatible
      we map progress values into the existing `fileUploadedStatus` column so
      the database is updated regardless of whether `upload_progress` exists.
    - If both `status` and `progress` are provided, `status` takes precedence
      because it represents an explicit fileUploadedStatus value.

    Parameters:
    - progress: integer 0..100 (will be written into `fileUploadedStatus` when
      the DB lacks a dedicated progress column)
    - status: int to set fileUploadedStatus (e.g., 0 initial, 1 uploading, 2 done, -1 failed)
    - filepath: storage URL string to set filepath

    Returns number of affected rows (0 if none).
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        parts = []
        vals = []
        # Map `progress` into the `fileUploadedStatus` column so older schemas
        # without `upload_progress` receive progress updates. If `progress` is
        # provided we prefer it (it contains the percent). Otherwise fall back
        # to the explicit `status` parameter.
        if progress is not None:
            # store the numeric progress into fileUploadedStatus for compatibility
            parts.append("fileUploadedStatus=%s")
            vals.append(int(progress))
        elif status is not None:
            parts.append("fileUploadedStatus=%s")
            vals.append(int(status))
        if filepath is not None:
            parts.append("filepath=%s")
            vals.append(filepath)

        if not parts:
            cur.close()
            conn.close()
            return 0

        sql = f"UPDATE incidentrecords SET {', '.join(parts)} WHERE id=%s"
        vals.append(str(record_id))
        cur.execute(sql, tuple(vals))
        affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        if affected == 0:
            print(f"update_incident_upload_status: affected 0 rows for id={record_id}")
        return affected
    except Exception as e:
        print(f"update_incident_upload_status error for {record_id}: {e}")
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return 0


def check_storage_access():
    """Diagnostic helper: attempts to resolve and access possible storage buckets.

    Prints which bucket names were tried and whether they appear accessible.
    Run this from your environment to collect evidence about why uploads fail.
    """
    print("=== Storage access diagnostic ===")
    candidates = []
    # candidate from configured constant
    try:
        candidates.append(BUCKET_NAME)
    except NameError:
        pass

    # try to read project_id from serviceAccountKey.json
    proj = None
    try:
        import json
        with open('serviceAccountKey.json', 'r') as f:
            data = json.load(f)
            proj = data.get('project_id')
            if proj:
                candidates.append(f"{proj}.appspot.com")
                candidates.append(f"{proj}.firebasestorage.app")
                candidates.append(f"{proj}.firebaseapp.com")
    except Exception as e:
        print(f"Could not read serviceAccountKey.json: {e}")

    # include the default (no-name) attempt
    tried = set()
    for c in [None] + candidates:
        try:
            if c in tried:
                continue
            tried.add(c)
            if c is None:
                print("Trying default storage.bucket() (no name)...")
                b = None
                try:
                    b = storage.bucket()
                except Exception as ie:
                    print(f"  -> storage.bucket() error: {ie}")
                    continue
            else:
                print(f"Trying storage.bucket('{c}')...")
                try:
                    b = storage.bucket(c)
                except Exception as ie:
                    print(f"  -> storage.bucket('{c}') error: {ie}")
                    continue

            # Quick check: try to get bucket name and optionally check existence
            try:
                name = getattr(b, 'name', None)
                print(f"  -> bucket object obtained, name={name}")
            except Exception as e:
                print(f"  -> obtained bucket object but reading name failed: {e}")

            # Try a simple operation that requires access: list blobs (limited)
            try:
                blobs = list(b.list_blobs(max_results=1))
                print(f"  -> list_blobs OK (found {len(blobs)} blobs)")
            except Exception as e:
                print(f"  -> list_blobs failed (likely permission or not found): {e}")

        except Exception as outer_e:
            print(f"Diagnostic attempt failed for candidate {c}: {outer_e}")

    print("=== End diagnostic ===")


def sync_firebase_events_once():
    """One-time sync: read /users/*/Events/* from RTDB and persist upload_progress/fileUploadedStatus/filepath to SQL.

    Use this when you want to reconcile RTDB -> MySQL (for example if updates may come from other processes).
    Returns the number of events processed.
    """
    processed = 0
    try:
        users = db_ref.child('users').get() or {}
        # users is a dict: { username: { Events: { event_id: {upload_progress:.., fileUploadedStatus:.., filepath:..}, ...}, ...}, ...}
        for uname, udata in (users.items() if isinstance(users, dict) else []):
            try:
                events = udata.get('Events') if isinstance(udata, dict) else None
                if not events:
                    continue
                for event_id, ev in (events.items() if isinstance(events, dict) else []):
                    try:
                        if not ev or not isinstance(ev, dict):
                            continue
                        progress = ev.get('upload_progress')
                        status = ev.get('fileUploadedStatus')
                        filepath = ev.get('filepath')
                        # Only update when any of the fields are present
                        if progress is None and status is None and filepath is None:
                            continue
                        update_incident_upload_status(event_id, progress=progress, status=status, filepath=filepath)
                        processed += 1
                    except Exception as e:
                        print(f"sync_firebase_events_once: failed to update event {event_id}: {e}")
            except Exception as e:
                print(f"sync_firebase_events_once: failed for user {uname}: {e}")
        print(f"sync_firebase_events_once: processed {processed} events")
    except Exception as e:
        print(f"sync_firebase_events_once: top-level error: {e}")
    return processed


def start_background_firebase_to_sql_sync(poll_interval=30):
    """Start a daemon thread that periodically syncs RTDB events into MySQL.

    poll_interval: seconds between scans.
    Returns the Thread object.
    """
    def _loop():
        print(f"Firebase->SQL sync thread started, polling every {poll_interval}s")
        while True:
            try:
                sync_firebase_events_once()
            except Exception as e:
                print(f"Background sync error: {e}")
            try:
                import time
                time.sleep(poll_interval)
            except Exception:
                break

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t