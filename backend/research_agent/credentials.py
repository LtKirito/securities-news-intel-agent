from __future__ import annotations

from app.core.security import decrypt_text
from app.db.database import SessionLocal
from app.db.models import UserApiKey


def load_user_senseaudio_key(user_id: str) -> str:
    db = SessionLocal()
    try:
        item = db.query(UserApiKey).filter(UserApiKey.user_id == int(user_id)).first()
        if not item:
            return ""
        return decrypt_text(item.encrypted_key)
    finally:
        db.close()
