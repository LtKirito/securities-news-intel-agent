import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import decrypt_text
from app.core.senseaudio_client import SenseAudioClient, SenseAudioError
from app.db.database import get_db
from app.db.models import ChatMessage, Report, User, UserApiKey
from app.db.schemas import ChatRequest
from app.routers.deps import get_current_user

router = APIRouter()


@router.post("")
async def chat(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    key = db.query(UserApiKey).filter(UserApiKey.user_id == current_user.id).first()
    if not key:
        raise HTTPException(status_code=400, detail="API key not configured")
    query = db.query(Report).filter(Report.user_id == current_user.id)
    if payload.date:
        query = query.filter(Report.date == payload.date)
    if payload.sector:
        query = query.filter(Report.sector == payload.sector)
    reports = query.order_by(Report.date.desc()).limit(5).all()
    contexts = []
    for report in reports:
        contexts.append(json.loads(Path(report.json_path).read_text(encoding="utf-8")))
    if not contexts:
        raise HTTPException(status_code=404, detail="No reports found for this scope")
    messages = [
        {"role": "system", "content": "你是证券日报问答助手。只能基于用户已生成的日报 JSON 回答，不给买卖建议，不编造未收录信息。返回 JSON：{\"answer\": \"...\"}。"},
        {"role": "user", "content": json.dumps({"question": payload.question, "reports": contexts}, ensure_ascii=False)},
    ]
    client = SenseAudioClient(decrypt_text(key.encrypted_key))
    try:
        result = await client.chat_json(messages)
    except SenseAudioError as exc:
        raise HTTPException(status_code=502, detail=f"日报问答暂不可用：{exc}") from exc
    answer = str(result.get("answer", ""))
    db.add(ChatMessage(user_id=current_user.id, scope_json=payload.model_dump_json(), role="user", content=payload.question))
    db.add(ChatMessage(user_id=current_user.id, scope_json=payload.model_dump_json(), role="assistant", content=answer))
    db.commit()
    return {"answer": answer}
