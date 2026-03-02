import tkinter as tk
import subprocess
from utils import get_db_connection, RecordingState

class Secure360GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure360 Master Control")
        self.root.geometry("300x250")
        
        self.processes = []
        self.is_on = False

        # --- System Power Button ---
        self.btn_power = tk.Button(root, text="SYSTEM POWER: OFF", bg="red", fg="white", 
                                   command=self.toggle_power, width=25, height=3, font=('Arial', 10, 'bold'))
        self.btn_power.pack(pady=20)

        # --- Manual Record Toggle Button ---
        self.btn_manual = tk.Button(root, text="START MANUAL RECORDING", bg="gray", fg="white", 
                                    command=self.toggle_manual_record, width=25, height=2, state=tk.DISABLED)
        self.btn_manual.pack(pady=10)

        # Start the background checker
        self.check_db_status()

    def check_db_status(self):
        """Periodically checks the DB to keep the GUI buttons in sync with the recorder."""
        if self.is_on:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM recording_status LIMIT 1")
                result = cursor.fetchone()
                conn.close()

                if result:
                    db_status = result[0]
                    # If DB is 0 but button says STOP, sync it back
                    if db_status == 0 and self.btn_manual["text"] == "STOP RECORDING":
                        self.btn_manual.config(text="START MANUAL RECORDING", bg="blue")
                        print("🔄 GUI synced: Recording finished (60s limit reached).")
                    # If DB is 1 but button says START, sync it forward
                    elif db_status == 1 and self.btn_manual["text"] == "START MANUAL RECORDING":
                        self.btn_manual.config(text="STOP RECORDING", bg="orange")
            except Exception as e:
                print(f"Sync Error: {e}")

        # Check again in 1000ms (1 second)
        self.root.after(1000, self.check_db_status)

    def toggle_power(self):
        if not self.is_on:
            self.update_db_status(0, 0)
            p1 = subprocess.Popen(['python', 'recording_service.py'])
            p2 = subprocess.Popen(['python', 'data_monitor.py'])
            self.processes = [p1, p2]
            
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_manual.config(state=tk.NORMAL, bg="blue", text="START MANUAL RECORDING")
        else:
            for p in self.processes:
                p.terminate()
            
            self.update_db_status(0, 0)
            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_manual.config(state=tk.DISABLED, bg="gray")

    def toggle_manual_record(self):
        """Toggles status between 1 and 0 in the DB."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM recording_status LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                current_status = result[0]
                if current_status == 0:
                    cursor.execute("UPDATE recording_status SET status = 1, EventType = %s", 
                                   (int(RecordingState.NORMAL_RECORDING),))
                else:
                    cursor.execute("UPDATE recording_status SET status = 0")
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"GUI Toggle Error: {e}")

    def update_db_status(self, status, event_type):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE recording_status SET status = %s, EventType = %s", (status, event_type))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB Reset Error: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()