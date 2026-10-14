import os
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

load_dotenv()

try:
    firebase_admin.get_app()
except ValueError:
    credential_path = os.getenv(
        "FIREBASE_CREDENTIALS_PATH",
        str(Path(__file__).resolve().parents[1] / "firebase-key.json"),
    )
    cred = credentials.Certificate(credential_path)
    firebase_admin.initialize_app(cred)

bd = firestore.client()
