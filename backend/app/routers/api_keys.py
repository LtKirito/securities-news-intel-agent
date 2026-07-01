from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import decrypt_text, encrypt_text
from app.core.senseaudio_client import SenseAudioClient, SenseAudioError
from app.db.database import get_db
from app.db.models import User, UserApiKey
from app.db.schemas import ApiKeyStatus, ApiKeyUpdate
from app.routers.deps import get_current_user

router = APIRouter()


@router.get("/status", response_model=ApiKeyStatus)
def status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ApiKeyStatus:
    item = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).first()
    return ApiKeyStatus(configured=bool(item))


@router.post("", response_model=ApiKeyStatus)
def update_api_key(payload: ApiKeyUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ApiKeyStatus:
    item = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).first()
    encrypted = encrypt_text(payload.api_key)
    if item:
        item.encrypted_key = encrypted
        item.updated_at = datetime.utcnow()
    else:
        item = UserApiKey(user_id=current_user.id, encrypted_key=encrypted)
        db.add(item)
    db.commit()
    return ApiKeyStatus(configured=True)


@router.post("/test")
async def test_api_key(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    item = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=400, detail="API key not configured")
    client = SenseAudioClient(decrypt_text(item.encrypted_key))
    try:
        return {"ok": await client.test_connection()}
    except SenseAudioError as exc:
        raise HTTPException(status_code=502, detail=f"SenseAudio API Key 测试未通过：{exc}") from exc
