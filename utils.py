import mysql.connector
import os
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
bucket = storage.bucket()

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