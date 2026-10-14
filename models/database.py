import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
from models.firebase_config import firebase_credential_source

load_dotenv()

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(firebase_credential_source())
    firebase_admin.initialize_app(cred)

bd = firestore.client()
