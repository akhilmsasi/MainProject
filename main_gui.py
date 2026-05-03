import tkinter as tk
import subprocess
import datetime
import sys
import os

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
        self.root.geometry("400x650")
        
        self.fm = FirebaseManager()
        self.processes = []
        self.is_on = False

        # --- 1. Firebase Connection Status Indicator ---
        self.status_frame = tk.Frame(root, bg="#f0f0f0")
        self.status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_fb_status = tk.Label(self.status_frame, text="FIREBASE: DISCONNECTED", 
                                      fg="red", font=('Arial', 8, 'bold'))
        self.lbl_fb_status.pack(side=tk.LEFT)

        # --- Camera-On / Recording Indicator (GUI only, not burned into saved video) ---
        self._cam_dot_visible = True          # tracks blink state
        self._cam_blink_job = None            # holds the scheduled after() id
        self._recording_poll_job = None       # holds the recording-status poll job
        self._last_poll_status = None         # last known recording status (True/False)

        # Small canvas to draw the pulsing dot
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

        # --- 5. Recording Toggle ---
        self.btn_record = tk.Button(root, text="START RECORDING", bg="gray", fg="white", 
                                    command=self.toggle_manual_record, width=30, height=2, state=tk.DISABLED)
        self.btn_record.pack(pady=20)

        # --- 6. Test Firebase Connection Button ---
        self.btn_test = tk.Button(root, text="SEND SAMPLE DATA TO CLOUD", bg="#e1e1e1", 
                                  command=self.test_firebase_connection, width=30)
        self.btn_test.pack(pady=10)

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

        # --- 7. User Details Section (from XAMPP MySQL 'videodatabase') ---
        tk.Label(root, text="User Details (from DB):", font=('Arial', 9, 'bold')).pack(pady=(15, 0))
        self.user_frame = tk.Frame(root)
        self.user_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        # Columns follow the schema in user_registration.php (secure360.Userdetails)
        self.user_tree = ttk.Treeview(
            self.user_frame,
            columns=("username", "name", "address", "email", "contact", "alt_contact", "vehicleNumber", "vehicleModel", "vehicleColor", "created"),
            show="headings",
            height=6
        )
        self.user_tree.heading("username", text="Username")
        self.user_tree.heading("name", text="Name")
        self.user_tree.heading("address", text="Address")
        self.user_tree.heading("email", text="Email")
        self.user_tree.heading("contact", text="Contact")
        self.user_tree.heading("alt_contact", text="Alt Contact")
        self.user_tree.heading("vehicleNumber", text="Vehicle No.")
        self.user_tree.heading("vehicleModel", text="Model")
        self.user_tree.heading("vehicleColor", text="Color")
        self.user_tree.heading("created", text="Created")

        self.user_tree.column("username", width=110, anchor='w')
        self.user_tree.column("name", width=130, anchor='w')
        self.user_tree.column("address", width=200, anchor='w')
        self.user_tree.column("email", width=160, anchor='w')
        self.user_tree.column("contact", width=100, anchor='w')
        self.user_tree.column("alt_contact", width=100, anchor='w')
        self.user_tree.column("vehicleNumber", width=100, anchor='w')
        self.user_tree.column("vehicleModel", width=100, anchor='w')
        self.user_tree.column("vehicleColor", width=80, anchor='w')
        self.user_tree.column("created", width=140, anchor='w')

        self.user_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(self.user_frame, orient="vertical", command=self.user_tree.yview)
        self.user_tree.configure(yscroll=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.btn_refresh_users = tk.Button(root, text="Refresh Users", command=self.refresh_user_details, width=30)
        self.btn_refresh_users.pack(pady=5)

        self.btn_sync_status = tk.Button(root, text="Sync RecordingStatus → Firebase", command=self.sync_recording_status, width=30)
        self.btn_sync_status.pack(pady=5)

        # Quick test button to force a per-user SQL+Firebase update (helps debug local DB updates)
        self.btn_test_sql = tk.Button(root, text="Test SQL Update (single user)", command=self.test_sql_update, width=30)
        self.btn_test_sql.pack(pady=5)

        # Ensure DB tables exist so updates won't fail due to missing tables
        try:
            initialize_database()
        except Exception as e:
            print(f"Warning: initialize_database() failed at startup: {e}")

        # Run initial check
        self._firebase_was_online = False
        self.check_cloud_connection()
        # Load user details once at startup
        self.refresh_user_details()
        # Load initial checkbox statuses
        self.load_event_statuses()
        # Start the always-running recording-status poll
        self._poll_recording_status()

    def load_event_statuses(self):
        """Read event statuses from the DB and update checkboxes in real-time."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT Eventtype, Eventstatus FROM event_status WHERE Eventtype IN (2, 3, 4, 5)")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            for row in rows:
                ev_type = row['Eventtype']
                ev_status = row['Eventstatus']
                if ev_type == 2 and self.chk_var2.get() != ev_status:
                    self.chk_var2.set(ev_status)
                elif ev_type == 3 and self.chk_var3.get() != ev_status:
                    self.chk_var3.set(ev_status)
                elif ev_type == 4 and self.chk_var4.get() != ev_status:
                    self.chk_var4.set(ev_status)
                elif ev_type == 5 and self.chk_var5.get() != ev_status:
                    self.chk_var5.set(ev_status)
        except Exception as e:
            print(f"Error loading event statuses: {e}")
        
        # Schedule the next poll in 2 seconds
        self.root.after(2000, self.load_event_statuses)

    def toggle_event_status(self, event_type, variable):
        """Update DB when a checkbox is clicked."""
        new_val = variable.get()
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE event_status SET Eventstatus = %s WHERE Eventtype = %s", (new_val, event_type))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"Updated event {event_type} status to {new_val}")
        except Exception as e:
            print(f"Error updating event status: {e}")
            messagebox.showerror("DB Error", f"Failed to update event {event_type}: {e}")
            # Revert checkbox if DB update fails
            variable.set(1 - new_val)

    def check_cloud_connection(self):
        """Pings Firebase to check connectivity."""
        try:
            # Admin SDK cannot read the client-only '.info/connected' path.
            # Do a lightweight read of a small known key to check connectivity instead.
            _ = db_ref.child('connection_test').get()
            # If no exception was raised, we consider the DB reachable.
            self.lbl_fb_status.config(text="FIREBASE: ONLINE", fg="green")
            now_online = True
        except Exception as e:
            # Print the exception to console for easier debugging
            print("Firebase connectivity check error:", e)
            self.lbl_fb_status.config(text="FIREBASE: OFFLINE", fg="red")
            now_online = False
        
        # If we just transitioned from offline -> online, perform syncs
        if now_online and not getattr(self, '_firebase_was_online', False):
            print('Firebase came online — syncing SQL recording status to RTDB...')
            # Sync global recording_status into RTDB root
            try:
                sync_recording_status_sql_to_firebase(propagate_to_users=False)
            except Exception as e:
                print('Error during recording_status sync:', e)
            # Optionally also ensure per-user nodes exist (non-destructive)
            try:
                sync_user_recording_status_to_firebase()
            except Exception as e:
                print('Error during per-user recording_status sync:', e)

        # Save current state and re-check every 5 seconds
        self._firebase_was_online = now_online
        self.root.after(5000, self.check_cloud_connection)

    def test_firebase_connection(self):
        """Sends a single piece of sample data to verify Firebase works."""
        sample_data = {
            "test_message": "Hello from Secure360 GUI",
            "last_test_time": str(datetime.datetime.now())
        }
        try:
            db_ref.child('connection_test').set(sample_data)
            messagebox.showinfo("Success", "Sample data sent to Firebase Successfully!")
            self.lbl_fb_status.config(text="FIREBASE: ONLINE", fg="green")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect: {e}")

    def fetch_user_details(self):
        """Fetch rows from the XAMPP MySQL `videodatabase.Userdetails` table."""
        try:
            # Use central DB config from utils.get_db_connection() which points to `secure360` by default
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            # Query fields according to user_registration.php table schema
            cursor.execute("SELECT username, name, address, email, contactNumber, altContactNumber, vehicleNumber, vehicleModel, vehicleColor, created_at FROM Userdetails")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return rows
        except Exception as e:
            print("Error fetching user details:", e)
            # Show a user-visible error only once per failure
            try:
                messagebox.showerror("DB Error", f"Unable to fetch Userdetails: {e}")
            except:
                pass
            return []

    def sync_recording_status(self):
        """Call the utils helper to sync SQL users into Firebase under users/{username}/recording_status."""
        try:
            sync_user_recording_status_to_firebase()
            messagebox.showinfo("Sync Complete", "User recording_status nodes have been synced to Firebase.")
        except Exception as e:
            messagebox.showerror("Sync Error", f"Failed to sync recording_status: {e}")

    def test_sql_update(self):
        """Helper invoked by a GUI button to run update_user_recording_status for the first user and show results."""
        try:
            rows = self.fetch_user_details()
            if not rows:
                messagebox.showwarning("No users", "No users found in Userdetails to test.")
                return
            username = rows[0].get('username')
            if not username:
                messagebox.showwarning("No username", "First user has no username.")
                return
            # Run an example update: toggle status=1 for test
            sql_ok, fb_ok = update_user_recording_status(username, status=1, event_type=1, gear=self.gear_options[self.selected_gear.get()])
            msg = f"Test update for {username}: SQL={'OK' if sql_ok else 'FAIL'}, Firebase={'OK' if fb_ok else 'FAIL'}"
            print(msg)
            messagebox.showinfo("Test SQL Update", msg)
        except Exception as e:
            print(f"Test SQL Update Error: {e}")
            messagebox.showerror("Test Error", f"Error during test update: {e}")

    def refresh_user_details(self):
        """Reload the user-details Treeview with fresh data."""
        rows = self.fetch_user_details()
        # Clear existing
        for item in self.user_tree.get_children():
            self.user_tree.delete(item)
        # Insert new rows
        for r in rows:
            self.user_tree.insert(
                "",
                "end",
                values=(
                    r.get('username'),
                    r.get('name'),
                    r.get('address'),
                    r.get('email'),
                    r.get('contactNumber'),
                    r.get('altContactNumber'),
                    r.get('vehicleNumber'),
                    r.get('vehicleModel'),
                    r.get('vehicleColor'),
                    str(r.get('created_at'))
                )
            )

    def update_gear(self, selection):
        if not self.is_on: return
        gear_val = self.gear_options[selection]
        # Update Firebase via Manager
        username = self.get_selected_username()
        if not username:
            messagebox.showwarning("No user selected", "Please select a user from the list to update gear.")
            return
        # Update per-user recording_status gear
        try:
            sql_ok, fb_ok = update_user_recording_status(username, status=None, event_type=None, gear=gear_val)
            if not sql_ok:
                messagebox.showwarning("SQL Update", f"Failed to update local DB for {username}")
            if not fb_ok:
                messagebox.showwarning("Firebase Update", f"Failed to update Firebase for {username}")
        except Exception as e:
            print(f"Failed to update gear for {username}: {e}")
        print(f" Gear Update: {selection} for user {username}")

    # ------------------------------------------------------------------ #
    #  Recording-status poll — drives button label + cam indicator       #
    # ------------------------------------------------------------------ #
    def _poll_recording_status(self):
        """Read recording_status from MySQL every 2 s. Always reschedules itself."""
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
            except Exception as e:
                print(f"[RecordingPoll] DB error: {e}")

            # Update button
            if is_recording:
                self.btn_record.config(text="STOP RECORDING", bg="orange")
            else:
                self.btn_record.config(text="START RECORDING", bg="blue")
        else:
            # System off — force everything grey
            is_recording = False

        # Always apply indicator state (no diff guard)
        if is_recording:
            self._cam_label.config(text="● REC ON", fg="#ff0000")
            self._cam_canvas.itemconfig(self._cam_dot, fill="#ff2222")
            if self._cam_blink_job is None:
                self._blink_cam_dot()
        else:
            if self._cam_blink_job is not None:
                self.root.after_cancel(self._cam_blink_job)
                self._cam_blink_job = None
            self._cam_canvas.itemconfig(self._cam_dot, fill="#888888")
            self._cam_label.config(text="● REC OFF", fg="#888888")

        self._last_poll_status = is_recording
        # Always reschedule — never stops
        self.root.after(2000, self._poll_recording_status)

    # ------------------------------------------------------------------ #
    #  Camera indicator blink loop                                        #
    # ------------------------------------------------------------------ #
    def _blink_cam_dot(self):
        """Alternate dot between bright/dark red every 500 ms while recording."""
        if not self._last_poll_status:
            self._cam_blink_job = None
            return
        colour = "#ff2222" if self._cam_dot_visible else "#991111"
        self._cam_canvas.itemconfig(self._cam_dot, fill=colour)
        self._cam_dot_visible = not self._cam_dot_visible
        self._cam_blink_job = self.root.after(500, self._blink_cam_dot)

    # ------------------------------------------------------------------ #

    def toggle_power(self):
        if not self.is_on:
            initialize_database()
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_record.config(state=tk.NORMAL, bg="blue")
            self.event_menu.config(state=tk.NORMAL)
            self.gear_menu.config(state=tk.NORMAL)
            # Start services
            script_dir = os.path.dirname(os.path.abspath(__file__))
            p1 = subprocess.Popen([sys.executable, os.path.join(script_dir, 'recording_service.py')])
            p2 = subprocess.Popen([sys.executable, os.path.join(script_dir, 'data_monitor.py')])
            self.processes = [p1, p2]
            # Poll already runs continuously; reset state so first tick applies
            self._last_poll_status = False
        else:
            # --- Graceful shutdown ---
            # 1. Signal recording_service to exit cleanly (closes the cv2 window itself)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            stop_flag = os.path.join(script_dir, ".stop_recording")
            try:
                open(stop_flag, 'w').close()
            except Exception as e:
                print(f"Warning: could not write stop flag: {e}")

            # 2. Give it up to 1.5 s to exit on its own, then force-kill as fallback
            def _finish_shutdown(procs):
                import time
                time.sleep(1.5)
                for p in procs:
                    if p.poll() is None:   # still running
                        p.terminate()

            import threading
            threading.Thread(target=_finish_shutdown, args=(list(self.processes),), daemon=True).start()

            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_record.config(state=tk.DISABLED, bg="gray")
            self.event_menu.config(state=tk.DISABLED)
            self.gear_menu.config(state=tk.DISABLED)
            # Reset state; next poll tick (always running) will grey out the indicator
            self._last_poll_status = False

    # Note: database initialization is provided by `initialize_database` imported from `utils`.

    def toggle_manual_record(self):
        try:
            username = self.get_selected_username()
            if not username:
                messagebox.showwarning("No user selected", "Please select a user from the list to start/stop recording.")
                return

            # Read per-user recording status
            current_status = db_ref.child('users').child(username).child('recording_status').child('status').get()
            if current_status == 0 or current_status is None:
                event_val = RecordingState[self.selected_event.get()].value
                sql_ok, fb_ok = update_user_recording_status(username, status=1, event_type=event_val, gear=self.gear_options[self.selected_gear.get()])
                if not sql_ok:
                    messagebox.showwarning("SQL Update", f"Failed to update local DB for {username}")
                if not fb_ok:
                    messagebox.showwarning("Firebase Update", f"Failed to update Firebase for {username}")
                self.btn_record.config(text="STOP RECORDING", bg="orange")
            else:
                sql_ok, fb_ok = update_user_recording_status(username, status=0, event_type=0, gear=self.gear_options[self.selected_gear.get()])
                if not sql_ok:
                    messagebox.showwarning("SQL Update", f"Failed to update local DB for {username}")
                if not fb_ok:
                    messagebox.showwarning("Firebase Update", f"Failed to update Firebase for {username}")
                self.btn_record.config(text="START RECORDING", bg="blue")
        except Exception as e:
            print(f"Toggle Error: {e}")

    def get_selected_username(self):
        try:
            sel = self.user_tree.selection()
            if not sel:
                # No selection: take the first row in the tree if present
                children = self.user_tree.get_children()
                if children:
                    first = children[0]
                    vals = self.user_tree.item(first, 'values')
                    return vals[0]
                # As a fallback, attempt to fetch from DB and return the first username
                rows = self.fetch_user_details()
                if rows:
                    return rows[0].get('username')
                return None
            item = sel[0]
            vals = self.user_tree.item(item, 'values')
            # username is the first column
            return vals[0]
        except Exception as e:
            print(f"Error getting selected username: {e}")
            return None

if __name__ == "__main__":
    import tkinter.messagebox
    import datetime
    
    # Initialize DB (if needed) and resume any pending uploads immediately on startup
    initialize_database()
    resume_pending_uploads()
    
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()