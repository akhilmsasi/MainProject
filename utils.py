import mysql.connector
import os
from enum import IntEnum

class RecordingState(IntEnum):
    NO_RECORDING = 0
    NORMAL_RECORDING = 1
    FACE_DETECTION = 2
    HONK_EVENT = 3
    HARD_BRAKING = 4
    ALARM = 5

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "secure360"
}

OUTPUT_PATH = r"C:/xampp/htdocs/Videos"
os.makedirs(OUTPUT_PATH, exist_ok=True)

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)