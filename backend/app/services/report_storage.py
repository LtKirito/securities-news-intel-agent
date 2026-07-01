import json
from pathlib import Path

from app.core.config import DATA_DIR


class ReportStorage:
    def user_report_root(self, user_id: str | int, date: str) -> Path:
        return DATA_DIR / "users" / str(user_id) / "reports" / date

    def run_artifacts_dir(self, user_id: str | int, date: str) -> Path:
        path = self.user_report_root(user_id, date) / "run" / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def sector_dir(self, user_id: str | int, date: str, sector: str) -> Path:
        safe_sector = sector.replace("/", "_").replace("\\", "_")
        path = self.user_report_root(user_id, date) / safe_sector
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_artifact(self, user_id: str | int, date: str, name: str, payload: dict) -> Path:
        path = self.run_artifacts_dir(user_id, date) / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_sector_json(self, user_id: str | int, date: str, sector: str, name: str, payload: dict) -> Path:
        path = self.sector_dir(user_id, date, sector) / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def save_sector_html(self, user_id: str | int, date: str, sector: str, html: str) -> Path:
        path = self.sector_dir(user_id, date, sector) / "report.html"
        path.write_text(html, encoding="utf-8")
        return path
