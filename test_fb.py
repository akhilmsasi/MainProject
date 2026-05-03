import traceback
import firebase_admin
from firebase_admin import credentials, db

try:
    cred = credentials.Certificate('serviceAccountKey.json')
    app = firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://fir-7211b-default-rtdb.firebaseio.com/',
        'storageBucket': 'fir-7211b.appspot.com'
    })
    print('App initialized:', app.name)
    val = db.reference('/').get()
    print('DB root:', val)
except Exception as e:
    traceback.print_exc()
