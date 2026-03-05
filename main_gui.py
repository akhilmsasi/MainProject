import tkinter as tk
import subprocess
import datetime
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
)
from firebase_manager import FirebaseManager
from firebase_admin import db

class Secure360GUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Secure360 Cloud & SQL Control")
        self.root.geometry("400x550")
        
        self.fm = FirebaseManager()
        self.processes = []
        self.is_on = False

        # --- 1. Firebase Connection Status Indicator ---
        self.status_frame = tk.Frame(root, bg="#f0f0f0")
        self.status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_fb_status = tk.Label(self.status_frame, text="FIREBASE: DISCONNECTED", 
                                      fg="red", font=('Arial', 8, 'bold'))
        self.lbl_fb_status.pack(side=tk.LEFT)
        
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
        print(f"⚙️ Gear Update: {selection} for user {username}")

    def toggle_power(self):
        if not self.is_on:
            initialize_database()
            self.is_on = True
            self.btn_power.config(text="SYSTEM POWER: ON", bg="green")
            self.btn_record.config(state=tk.NORMAL, bg="blue")
            self.event_menu.config(state=tk.NORMAL)
            self.gear_menu.config(state=tk.NORMAL)
            # Start services
            p1 = subprocess.Popen(['python', 'recording_service.py'])
            p2 = subprocess.Popen(['python', 'data_monitor.py'])
            self.processes = [p1, p2]
        else:
            for p in self.processes: p.terminate()
            self.is_on = False
            self.btn_power.config(text="SYSTEM POWER: OFF", bg="red")
            self.btn_record.config(state=tk.DISABLED, bg="gray")
            self.event_menu.config(state=tk.DISABLED)
            self.gear_menu.config(state=tk.DISABLED)

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
    root = tk.Tk()
    app = Secure360GUI(root)
    root.mainloop()