import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def get_db():
    global _db
    if _db is None:
        if not firebase_admin._apps:
            import base64
            service_account = os.environ["FIREBASE_SERVICE_ACCOUNT"]
            # Support both plain JSON and base64-encoded JSON
            try:
                cred_dict = json.loads(service_account)
            except json.JSONDecodeError:
                cred_dict = json.loads(base64.b64decode(service_account).decode())
            # Fix private key newlines in case of shell escaping
            if "private_key" in cred_dict:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


def get_subscribers():
    db = get_db()
    docs = db.collection("subscribers").stream()
    return [doc.to_dict() for doc in docs]


def save_subscriber(data: dict):
    db = get_db()
    db.collection("subscribers").add(data)


def is_circular_seen(circular_id: str) -> bool:
    db = get_db()
    doc = db.collection("seen_circulars").document(circular_id).get()
    return doc.exists


def mark_circular_seen(circular_id: str, data: dict):
    db = get_db()
    db.collection("seen_circulars").document(circular_id).set(data)
