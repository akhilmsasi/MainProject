import tkinter as tk
import subprocess
from utils import get_db_connection, RecordingState

class Secure360GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure360 Master Control")
        self.root.geometry("400x350")
        
        self.processes = []
        self.is_on = False

        # --- System Power Button ---
        self.btn_power = tk.Button(root, text="SYSTEM POWER: OFF", bg="red", fg="white", 
                                   command=self.toggle_power, width=30, height=3, font=('Arial', 10, 'bold'))
        self.btn_power.pack(pady=20)

        # --- Event Selection Dropdown ---
        tk.Label(root, text="Select Event Type:", font=('Arial', 9)).pack()
        
        # Create a list of names from your RecordingState Enum
        self.event_options = [state.name for state in RecordingState if state.value != 0]
        self.selected_event = tk.StringVar(root)
        self.selected_event.set(self.event_options[0]) # Default to NORMAL_RECORDING

        self.drop_menu = tk.OptionMenu(root, self.selected_event, *self.event_options)
        self.drop_menu.config(width=25, state=tk.DISABLED)
        self.drop_menu.pack(pady=10)

        # --- Recording Toggle Button ---
        self.btn_record = tk.Button(root, text="START RECORDING", bg="gray", fg="white", 
                                    command=self.toggle_manual_record, width=30, height=2, state=tk.DISABLED)
        self.btn_record.pack(pady=20)

        # Start the background sync checker
        self.check_db_status()

    def check_db_status(self):
        """Syncs GUI button state with Database changes (e.g., auto-stop after 60s)."""
        if self.is_on:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM recording_status LIMIT 1")
                result = cursor.fetchone()
                conn.close()

                if result:
                    db_status = result[0]
                    if db_status == 0 and self.btn_record["text"] == "STOP RECORDING":
                        self.btn_record.config(text="START RECORDING", bg="blue")
                        self.drop_menu.config(state=tk.NORMAL) # Re-enable dropdown
            except Exception as e:
                print(f"Sync Error: {e}")

        self.root.after(1000, self.check_db_status)

    def toggle_power(self):
        if not self.is_on:
            self.update_db_status(0, 0)
            p1 = subprocess.Popen(['python', 'recording_service.py'])
            p2 = subprocess.Popen(['python', 'data_monitor.py'])
            self.processes = [p1, p2]
            
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_record.config(state=tk.NORMAL, bg="blue")
            self.drop_menu.config(state=tk.NORMAL)
        else:
            for p in self.processes:
                p.terminate()
            self.update_db_status(0, 0)
            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_record.config(state=tk.DISABLED, bg="gray")
            self.drop_menu.config(state=tk.DISABLED)

    def toggle_manual_record(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM recording_status LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                current_status = result[0]
                if current_status == 0:
                    # Get integer value from Enum based on selected string
                    event_name = self.selected_event.get()
                    event_val = RecordingState[event_name].value
                    
                    cursor.execute("UPDATE recording_status SET status = 1, EventType = %s", (event_val,))
                    self.btn_record.config(text="STOP RECORDING", bg="orange")
                    self.drop_menu.config(state=tk.DISABLED) # Lock dropdown during recording
                else:
                    cursor.execute("UPDATE recording_status SET status = 0")
                    # Button will be reset by check_db_status()
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