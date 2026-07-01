from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import CONFIG_DIR

TEMPLATE_DIR = CONFIG_DIR / "sector_templates"


def list_sector_templates() -> list[dict[str, Any]]:
    templates = [load_sector_template(path.stem) for path in sorted(TEMPLATE_DIR.glob("*.json"))]
    return [template_summary(template) for template in templates]


def get_sector_template(template_id: str) -> dict[str, Any] | None:
    safe_id = Path(template_id).stem
    path = TEMPLATE_DIR / f"{safe_id}.json"
    if not path.exists():
        return None
    return load_sector_template(safe_id)


def load_sector_template(template_id: str) -> dict[str, Any]:
    path = TEMPLATE_DIR / f"{template_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["id"] = template_id
    payload.setdefault("enabled", True)
    payload.setdefault("expanded_keywords", [])
    payload.setdefault("exclude_keywords", [])
    payload.setdefault("related_companies", [])
    payload.setdefault("chain_nodes", [])
    payload.setdefault("verification_metrics", [])
    payload.setdefault("preferred_sources", [])
    payload.setdefault("quality_baseline", {})
    return payload


def template_summary(template: dict[str, Any]) -> dict[str, Any]:
    baseline = template.get("quality_baseline", {}) or {}
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "display_name": template.get("display_name", template.get("name")),
        "status": template.get("status", "curated_standard"),
        "description": template.get("description", ""),
        "keywords_count": len(template.get("keywords", []) or []),
        "companies_count": len(template.get("related_companies", []) or []),
        "quality_baseline": baseline,
    }


def template_to_sector_config(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": template.get("name", ""),
        "enabled": True,
        "keywords": template.get("keywords", []),
        "expanded_keywords": template.get("expanded_keywords", []),
        "exclude_keywords": template.get("exclude_keywords", []),
        "related_companies": template.get("related_companies", []),
        "chain_nodes": template.get("chain_nodes", []),
        "verification_metrics": template.get("verification_metrics", []),
        "profile_status": template.get("status", "curated_standard"),
        "preferred_sources": template.get("preferred_sources", []),
        "quality_baseline": template.get("quality_baseline", {}),
    }
