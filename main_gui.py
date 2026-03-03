import tkinter as tk
import subprocess
from utils import get_db_connection, RecordingState, initialize_database

class Secure360GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure360 Master Control")
        self.root.geometry("400x450")
        
        self.processes = []
        self.is_on = False

        # --- System Power Button ---
        self.btn_power = tk.Button(root, text="SYSTEM POWER: OFF", bg="red", fg="white", 
                                   command=self.toggle_power, width=30, height=3, font=('Arial', 10, 'bold'))
        self.btn_power.pack(pady=20)

        # --- Gear Selection Dropdown ---
        tk.Label(root, text="Select Gear Status:", font=('Arial', 9, 'bold')).pack()
        self.gear_options = {"Park": 0, "Drive": 1}
        self.selected_gear = tk.StringVar(root)
        self.selected_gear.set("Park")

        self.gear_menu = tk.OptionMenu(root, self.selected_gear, *self.gear_options.keys(), command=self.update_gear_in_db)
        self.gear_menu.config(width=25, state=tk.DISABLED)
        self.gear_menu.pack(pady=5)

        # --- Event Selection Dropdown ---
        tk.Label(root, text="Select Event Type:", font=('Arial', 9, 'bold')).pack(pady=(15, 0))
        self.event_options = [state.name for state in RecordingState if state.value != 0]
        self.selected_event = tk.StringVar(root)
        self.selected_event.set(self.event_options[0])

        self.event_menu = tk.OptionMenu(root, self.selected_event, *self.event_options)
        self.event_menu.config(width=25, state=tk.DISABLED)
        self.event_menu.pack(pady=5)

        # --- Recording Toggle Button ---
        self.btn_record = tk.Button(root, text="START RECORDING", bg="gray", fg="white", 
                                    command=self.toggle_manual_record, width=30, height=2, state=tk.DISABLED)
        self.btn_record.pack(pady=25)

        self.check_db_status()

    def update_gear_in_db(self, selection):
        """Updates the gear column in the database immediately when changed."""
        if not self.is_on: return
        gear_val = self.gear_options[selection]
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Assuming your table has a 'gear' column
            cursor.execute("UPDATE recording_status SET gear = %s", (gear_val,))
            conn.commit()
            #conn.close()
            print(f"⚙️ Gear shifted to: {selection} ({gear_val})")
        except Exception as e:
            print(f"Gear Update Error: {e}")

    def toggle_power(self):
        if not self.is_on:
            initialize_database()
            self.update_db_status(0, 0, 0) # status, event, gear
            p1 = subprocess.Popen(['python', 'recording_service.py'])
            p2 = subprocess.Popen(['python', 'data_monitor.py'])
            self.processes = [p1, p2]
            
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_record.config(state=tk.NORMAL, bg="blue")
            self.event_menu.config(state=tk.NORMAL)
            self.gear_menu.config(state=tk.NORMAL)
        else:
            for p in self.processes:
                p.terminate()
            self.update_db_status(0, 0, 0)
            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_record.config(state=tk.DISABLED, bg="gray")
            self.event_menu.config(state=tk.DISABLED)
            self.gear_menu.config(state=tk.DISABLED)

    def toggle_manual_record(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM recording_status LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                if result[0] == 0:
                    event_val = RecordingState[self.selected_event.get()].value
                    cursor.execute("UPDATE recording_status SET status = 1, EventType = %s", (event_val,))
                    self.btn_record.config(text="STOP RECORDING", bg="orange")
                else:
                    cursor.execute("UPDATE recording_status SET status = 0")
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"GUI Toggle Error: {e}")

    def check_db_status(self):
        if self.is_on:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM recording_status LIMIT 1")
                result = cursor.fetchone()
                conn.close()

                if result and result[0] == 0 and self.btn_record["text"] == "STOP RECORDING":
                    self.btn_record.config(text="START RECORDING", bg="blue")
            except: pass
        self.root.after(1000, self.check_db_status)

    def update_db_status(self, status, event, gear):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE recording_status SET status=%s, EventType=%s, gear=%s", (status, event, gear))
            conn.commit()
            conn.close()
        except: pass

if __name__ == "__main__":
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()