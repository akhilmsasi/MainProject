import tkinter as tk
import subprocess
import datetime
import sys
import os
import uuid  # Added for RandomID generation

# Check and install requirements if needed
try:
    import firebase_admin
    import mysql.connector
except ImportError:
    print("Required packages not found. Installing requirements...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    install_script = os.path.join(script_dir, 'setup', 'install.py')
    if os.path.exists(install_script):
        try:
            subprocess.check_call([sys.executable, install_script])
        except subprocess.CalledProcessError as e:
            print(f"Failed to install requirements: {e}")
            sys.exit(1)

from tkinter import messagebox, ttk
from utils import (
    db_ref,
    RecordingState,
    initialize_database,
    get_db_connection,
    sync_user_recording_status_to_firebase,
    sync_recording_status_sql_to_firebase,
    write_user_recording_status,
    update_user_recording_status,
    resume_pending_uploads,
)
from firebase_manager import FirebaseManager
from firebase_admin import db

class Secure360GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure360 Cloud & SQL Control")
        self.root.geometry("400x750")
        
        self.fm = FirebaseManager()
        self.processes = []
        self.is_on = False

        # --- 1. Firebase Connection Status Indicator ---
        self.status_frame = tk.Frame(root, bg="#f0f0f0")
        self.status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_fb_status = tk.Label(self.status_frame, text="FIREBASE: DISCONNECTED", 
                                     fg="red", font=('Arial', 8, 'bold'))
        self.lbl_fb_status.pack(side=tk.LEFT)

        self._cam_dot_visible = True          
        self._cam_blink_job = None            
        self._recording_poll_job = None       
        self._last_poll_status = None         

        self._cam_canvas = tk.Canvas(self.status_frame, width=14, height=14,
                                     bg="#f0f0f0", highlightthickness=0)
        self._cam_canvas.pack(side=tk.RIGHT, padx=(0, 2), pady=2)
        self._cam_dot = self._cam_canvas.create_oval(2, 2, 12, 12, fill="#888888", outline="")

        self._cam_label = tk.Label(self.status_frame, text="● CAM OFF",
                                   fg="#888888", bg="#f0f0f0", font=('Arial', 8, 'bold'))
        self._cam_label.pack(side=tk.RIGHT, padx=(4, 0))
        
        # --- 2. System Power Button ---
        self.btn_power = tk.Button(root, text="SYSTEM POWER: OFF", bg="red", fg="white", 
                                   command=self.toggle_power, width=30, height=3, font=('Arial', 10, 'bold'))
        self.btn_power.pack(pady=10)

        # --- 3. Gear Selection ---
        tk.Label(root, text="Select Gear Status:", font=('Arial', 9, 'bold')).pack()
        self.gear_options = {"Park": 0, "Drive": 1}
        self.selected_gear = tk.StringVar(root)
        self.selected_gear.set("Park")
        self.gear_menu = tk.OptionMenu(root, self.selected_gear, *self.gear_options.keys(), command=self.update_gear)
        self.gear_menu.config(width=25, state=tk.DISABLED)
        self.gear_menu.pack(pady=5)

        # --- 4. Event Selection ---
        tk.Label(root, text="Select Event Type:", font=('Arial', 9, 'bold')).pack(pady=(15, 0))
        self.event_options = [state.name for state in RecordingState if state.value != 0]
        self.selected_event = tk.StringVar(root)
        self.selected_event.set(self.event_options[0])
        self.event_menu = tk.OptionMenu(root, self.selected_event, *self.event_options)
        self.event_menu.config(width=25, state=tk.DISABLED)
        self.event_menu.pack(pady=5)

        # --- 4.5: Crash Position Dropdown ---
        tk.Label(root, text="Select Crash Position:", font=('Arial', 9, 'bold')).pack(pady=(10, 0))
        self.crash_pos_options = ["Near", "Far"]
        self.selected_crash_pos = tk.StringVar(root)
        self.selected_crash_pos.set("Near")
        self.crash_pos_menu = tk.OptionMenu(root, self.selected_crash_pos, *self.crash_pos_options)
        self.crash_pos_menu.config(width=25, state=tk.DISABLED)
        self.crash_pos_menu.pack(pady=5)

        # --- 4.6: Send Crash Button ---
        self.btn_send_crash = tk.Button(root, text="SEND CRASH", bg="#d9534f", fg="white",
                                       font=('Arial', 9, 'bold'), width=30, height=2,
                                       command=self.send_crash_action, state=tk.DISABLED)
        self.btn_send_crash.pack(pady=10)

        # --- 5. Recording Toggle ---
        self.btn_record = tk.Button(root, text="START RECORDING", bg="gray", fg="white", 
                                    command=self.toggle_manual_record, width=30, height=2, state=tk.DISABLED)
        self.btn_record.pack(pady=10)

        # --- 6. Test Firebase Connection Button ---
        self.btn_test = tk.Button(root, text="SEND SAMPLE DATA TO CLOUD", bg="#e1e1e1", 
                                  command=self.test_firebase_connection, width=30)
        self.btn_test.pack(pady=5)

        # --- 6.5 Event Status Checkboxes ---
        self.checkbox_frame = tk.Frame(root)
        self.checkbox_frame.pack(pady=5)
        
        self.chk_var2 = tk.IntVar()
        self.chk2 = tk.Checkbutton(self.checkbox_frame, text="FACE DETECTION", variable=self.chk_var2, command=lambda: self.toggle_event_status(2, self.chk_var2))
        self.chk2.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        
        self.chk_var3 = tk.IntVar()
        self.chk3 = tk.Checkbutton(self.checkbox_frame, text="HONK EVENT", variable=self.chk_var3, command=lambda: self.toggle_event_status(3, self.chk_var3))
        self.chk3.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        self.chk_var4 = tk.IntVar()
        self.chk4 = tk.Checkbutton(self.checkbox_frame, text="HARD BRAKING", variable=self.chk_var4, command=lambda: self.toggle_event_status(4, self.chk_var4))
        self.chk4.grid(row=1, column=0, padx=5, pady=2, sticky="w")
        
        self.chk_var5 = tk.IntVar()
        self.chk5 = tk.Checkbutton(self.checkbox_frame, text="ALARM SYSTEM", variable=self.chk_var5, command=lambda: self.toggle_event_status(5, self.chk_var5))
        self.chk5.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        # --- 7. User Details Section ---
        tk.Label(root, text="User Details (from DB):", font=('Arial', 9, 'bold')).pack(pady=(15, 0))
        self.user_frame = tk.Frame(root)
        self.user_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        self.user_tree = ttk.Treeview(
            self.user_frame,
            columns=("username", "name", "address", "email", "contact", "alt_contact", "vehicleNumber", "vehicleModel", "vehicleColor", "created"),
            show="headings",
            height=4
        )
        self.user_tree.heading("username", text="Username")
        self.user_tree.heading("name", text="Name")
        self.user_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scroll = ttk.Scrollbar(self.user_frame, orient="vertical", command=self.user_tree.yview)
        self.user_tree.configure(yscroll=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_refresh_users = tk.Button(root, text="Refresh Users", command=self.refresh_user_details, width=30)
        self.btn_refresh_users.pack(pady=2)

        # Startup logic
        try:
            initialize_database()
        except Exception as e:
            print(f"Warning: initialize_database() failed: {e}")

        self._firebase_was_online = False
        self.check_cloud_connection()
        self.refresh_user_details()
        self.load_event_statuses()
        self._poll_recording_status()

    # --- NEW: Send Crash logic ---
    def send_crash_action(self):
        """Action for the Send Crash button: Logs location and triggers system recording."""
        username = self.get_selected_username()
        if not username:
            messagebox.showwarning("No Selection", "Please select a user from the list.")
            return
        
        pos = self.selected_crash_pos.get()
        # Set coordinates based on CET College
        if pos == "Near":
            lat, lon = 8.5485, 76.9015
        else:
            lat, lon = 8.4875, 76.9486

        try:
            # 1. Standard procedure: Update SQL/Firebase user status (Event type 6 = Crash)
            update_user_recording_status(
                username, 
                status=1, 
                event_type=6, 
                gear=self.gear_options[self.selected_gear.get()]
            )
            
            # 2. Specific CrashEvents logging
            random_id = str(uuid.uuid4())[:8]
            crash_data = {
                "lat": lat,
                "long": lon,
                "username": username,
                "timestamp": str(datetime.datetime.now())
            }
            
            # Write to "CrashEvents"->RandomID
            db_ref.child('CrashEvents').child(random_id).set(crash_data)

            print(f"CRASH SENT: {username} | ID: {random_id} | {pos} ({lat}, {lon})")
            messagebox.showinfo("Success", f"Crash event {random_id} logged at {pos} position.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send crash: {e}")

    def toggle_power(self):
        if not self.is_on:
            initialize_database()
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_record.config(state=tk.NORMAL, bg="blue")
            self.event_menu.config(state=tk.NORMAL)
            self.gear_menu.config(state=tk.NORMAL)
            self.crash_pos_menu.config(state=tk.NORMAL)
            self.btn_send_crash.config(state=tk.NORMAL)
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            p1 = subprocess.Popen([sys.executable, os.path.join(script_dir, 'recording_service.py')])
            p2 = subprocess.Popen([sys.executable, os.path.join(script_dir, 'data_monitor.py')])
            self.processes = [p1, p2]
            self._last_poll_status = False
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stop_flag = os.path.join(script_dir, ".stop_recording")
            try: open(stop_flag, 'w').close()
            except: pass

            def _finish_shutdown(procs):
                import time
                time.sleep(1.5)
                for p in procs:
                    if p.poll() is None: p.terminate()

            import threading
            threading.Thread(target=_finish_shutdown, args=(list(self.processes),), daemon=True).start()

            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_record.config(state=tk.DISABLED, bg="gray")
            self.event_menu.config(state=tk.DISABLED)
            self.gear_menu.config(state=tk.DISABLED)
            self.crash_pos_menu.config(state=tk.DISABLED)
            self.btn_send_crash.config(state=tk.DISABLED)
            self._last_poll_status = False

    def load_event_statuses(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT Eventtype, Eventstatus FROM event_status WHERE Eventtype IN (2, 3, 4, 5)")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            for row in rows:
                ev_type, ev_status = row['Eventtype'], row['Eventstatus']
                if ev_type == 2: self.chk_var2.set(ev_status)
                elif ev_type == 3: self.chk_var3.set(ev_status)
                elif ev_type == 4: self.chk_var4.set(ev_status)
                elif ev_type == 5: self.chk_var5.set(ev_status)
        except: pass
        self.root.after(2000, self.load_event_statuses)

    def toggle_event_status(self, event_type, variable):
        new_val = variable.get()
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE event_status SET Eventstatus = %s WHERE Eventtype = %s", (new_val, event_type))
            conn.commit()
            cursor.close()
            conn.close()
        except: variable.set(1 - new_val)

    def check_cloud_connection(self):
        try:
            db_ref.child('connection_test').get()
            self.lbl_fb_status.config(text="FIREBASE: ONLINE", fg="green")
            now_online = True
        except:
            self.lbl_fb_status.config(text="FIREBASE: OFFLINE", fg="red")
            now_online = False
        self._firebase_was_online = now_online
        self.root.after(5000, self.check_cloud_connection)

    def test_firebase_connection(self):
        try:
            db_ref.child('connection_test').set({"test": "ok", "time": str(datetime.datetime.now())})
            messagebox.showinfo("Success", "Sample data sent!")
        except Exception as e: messagebox.showerror("Error", str(e))

    def fetch_user_details(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT username, name, address, email, contactNumber, altContactNumber, vehicleNumber, vehicleModel, vehicleColor, created_at FROM Userdetails")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return rows
        except: return []

    def refresh_user_details(self):
        rows = self.fetch_user_details()
        for item in self.user_tree.get_children(): self.user_tree.delete(item)
        for r in rows:
            self.user_tree.insert("", "end", values=(r.get('username'), r.get('name'), r.get('address'), r.get('email'), r.get('contactNumber'), r.get('altContactNumber'), r.get('vehicleNumber'), r.get('vehicleModel'), r.get('vehicleColor'), str(r.get('created_at'))))

    def update_gear(self, selection):
        if not self.is_on: return
        username = self.get_selected_username()
        if username: update_user_recording_status(username, gear=self.gear_options[selection])

    def _poll_recording_status(self):
        is_recording = False
        if self.is_on:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT status FROM recording_status LIMIT 1")
                row = cursor.fetchone()
                cursor.close()
                conn.close()
                is_recording = bool(row and int(row[0]) == 1)
            except: pass
        if is_recording:
            self.btn_record.config(text="STOP RECORDING", bg="orange")
            self._cam_label.config(text="● REC ON", fg="#ff0000")
            if self._cam_blink_job is None: self._blink_cam_dot()
        else:
            if self._cam_blink_job: self.root.after_cancel(self._cam_blink_job); self._cam_blink_job = None
            self.btn_record.config(text="START RECORDING", bg="blue")
            self._cam_label.config(text="● REC OFF", fg="#888888")
            self._cam_canvas.itemconfig(self._cam_dot, fill="#888888")
        self._last_poll_status = is_recording
        self.root.after(2000, self._poll_recording_status)

    def _blink_cam_dot(self):
        if not self._last_poll_status: return
        colour = "#ff2222" if self._cam_dot_visible else "#991111"
        self._cam_canvas.itemconfig(self._cam_dot, fill=colour)
        self._cam_dot_visible = not self._cam_dot_visible
        self._cam_blink_job = self.root.after(500, self._blink_cam_dot)

    def toggle_manual_record(self):
        username = self.get_selected_username()
        if not username: return
        try:
            current = db_ref.child('users').child(username).child('recording_status').child('status').get()
            new_status = 1 if (current == 0 or current is None) else 0
            ev = RecordingState[self.selected_event.get()].value if new_status == 1 else 0
            update_user_recording_status(username, status=new_status, event_type=ev, gear=self.gear_options[self.selected_gear.get()])
        except: pass

    def get_selected_username(self):
        try:
            sel = self.user_tree.selection()
            if sel: return self.user_tree.item(sel[0], 'values')[0]
            children = self.user_tree.get_children()
            if children: return self.user_tree.item(children[0], 'values')[0]
        except: return None

if __name__ == "__main__":
    initialize_database()
    resume_pending_uploads()
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()