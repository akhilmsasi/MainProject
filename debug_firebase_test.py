import utils
import firebase_admin
from firebase_admin import db
import traceback

print('firebase apps =', getattr(firebase_admin, '_apps', None))
try:
    val = utils.db_ref.child('connection_test').get()
    print("connection_test value (or None if unset) =", val)
except Exception as e:
    print('DB GET ERROR:', e)
    traceback.print_exc()
