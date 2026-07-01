import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import SectorConfig, User
from app.db.schemas import SectorConfigIn
from app.routers.deps import get_current_user

router = APIRouter()


@router.get("/sectors")
def list_sectors(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(SectorConfig).filter(SectorConfig.user_id == current_user.id).all()
    return [{"id": row.id, **json.loads(row.config_json)} for row in rows]


@router.post("/sectors")
def upsert_sector(payload: SectorConfigIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = db.query(SectorConfig).filter(SectorConfig.user_id == current_user.id, SectorConfig.name == payload.name).first()
    data = payload.model_dump()
    if row:
        row.enabled = payload.enabled
        row.config_json = json.dumps(data, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
    else:
        row = SectorConfig(user_id=current_user.id, name=payload.name, enabled=payload.enabled, config_json=json.dumps(data, ensure_ascii=False))
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, **data}
