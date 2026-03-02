import mysql.connector
import os
from enum import IntEnum

# 1. Define the Enum
class RecordingState(IntEnum):
    NO_RECORDING = 0
    NORMAL_RECORDING = 1
    FACE_DETECTION = 2
    HONK_EVENT = 3
    HARD_BRAKING = 4
    ALARM = 5

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

# 4. Define the Function
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)