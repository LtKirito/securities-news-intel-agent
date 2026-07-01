from fastapi import APIRouter, Depends, HTTPException

from app.db.models import User
from app.routers.deps import get_current_user
from app.services.sector_templates import get_sector_template, list_sector_templates

router = APIRouter()


@router.get("")
def list_templates(current_user: User = Depends(get_current_user)) -> list[dict]:
    return list_sector_templates()


@router.get("/{template_id}")
def get_template(template_id: str, current_user: User = Depends(get_current_user)) -> dict:
    template = get_sector_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Sector template not found")
    return template
