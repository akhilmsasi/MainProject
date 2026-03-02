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

        self.btn_power = tk.Button(root, text="SYSTEM POWER: OFF", bg="red", fg="white", 
                                   command=self.toggle_power, width=25, height=3)
        self.btn_power.pack(pady=20)

        self.btn_manual = tk.Button(root, text="START MANUAL RECORDING", bg="gray", fg="white", 
                                    command=self.manual_record, width=25, height=2, state=tk.DISABLED)
        self.btn_manual.pack(pady=10)

    def toggle_power(self):
        if not self.is_on:
            # Start Services
            p1 = subprocess.Popen(['python', 'recording_service.py'])
            p2 = subprocess.Popen(['python', 'data_monitor.py'])
            self.processes = [p1, p2]
            
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_manual.config(state=tk.NORMAL, bg="blue")
        else:
            # Kill Services
            for p in self.processes:
                p.terminate()
            
            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_manual.config(state=tk.DISABLED, bg="gray")

    def manual_record(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        # Set status=1 and EventType=1 (NORMAL_RECORDING)
        cursor.execute("UPDATE recording_status SET status = 1, EventType = %s", 
                       (int(RecordingState.NORMAL_RECORDING),))
        conn.commit()
        conn.close()
        print("🖱 Manual Record Triggered via GUI")

if __name__ == "__main__":
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()