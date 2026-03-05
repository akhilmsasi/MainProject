import traceback
import utils

print('DB config:', utils.DB_CONFIG)

try:
    print('\nCalling initialize_database()...')
    utils.initialize_database()
    print('initialize_database completed')
except Exception as e:
    print('initialize_database ERROR:', e)
    traceback.print_exc()

try:
    # fetch first username
    conn = utils.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username FROM Userdetails LIMIT 1')
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        print('No users found in Userdetails')
    else:
        username = row[0]
        print('Found username:', username)
        print('Calling update_user_recording_status for', username)
        ok = utils.update_user_recording_status(username, status=1, event_type=1, gear=1)
        print('update_user_recording_status returned:', ok)
except Exception as e:
    print('Error during test update:', e)
    traceback.print_exc()

# Also dump any rows in user_recording_status
try:
    conn = utils.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username, status, EventType, gear, updated_at FROM user_recording_status')
    rows = cursor.fetchall()
    print('\nuser_recording_status rows:')
    for r in rows:
        print(r)
    cursor.close()
    conn.close()
except Exception as e:
    print('Error listing user_recording_status:', e)
    traceback.print_exc()

# Print firebase value for the user
try:
    if row:
        fb_val = utils.db_ref.child('users').child(str(username)).child('recording_status').get()
        print('\nFirebase recording_status for', username, fb_val)
except Exception as e:
    print('Firebase read error:', e)
    traceback.print_exc()
