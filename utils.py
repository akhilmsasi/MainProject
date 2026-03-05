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