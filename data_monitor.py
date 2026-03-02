import time
from utils import get_db_connection, RecordingState

def run_monitor():
    print("🔍 Data Monitor Service Active. Watching for database changes......")
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT status, EventType FROM recording_status")
            row = cursor.fetchone()
            conn.close()

            if row and row['status'] == 1:
                print(f"🔔 Monitor detected status=1 for {RecordingState(row['EventType']).name}")
            
        except Exception as e:
            print(f"Monitor Error: {e}")
        time.sleep(2) # Check every 2 seconds to save CPU

if __name__ == "__main__":
    run_monitor()