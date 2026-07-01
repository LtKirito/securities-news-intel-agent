from pathlib import Path

from app.core.config import CONFIG_DIR, PROJECT_ROOT, SCHEMAS_DIR, TEMPLATES_DIR


class AgentLoader:
    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root
        self.skills_root = project_root / "skills"

    def read_text(self, relative_path: str) -> str:
        path = self.project_root / relative_path
        return path.read_text(encoding="utf-8")

    def load_skill(self, skill_name: str) -> str:
        return (self.skills_root / skill_name / "SKILL.md").read_text(encoding="utf-8")

    def load_pipeline_skill(self) -> str:
        return self.load_skill("securities-daily-intel-pipeline")

    def load_schema(self, schema_name: str) -> str:
        return (SCHEMAS_DIR / schema_name).read_text(encoding="utf-8")

    def load_config(self, config_name: str) -> str:
        return (CONFIG_DIR / config_name).read_text(encoding="utf-8")

    def load_template(self, template_name: str) -> str:
        return (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")

    def load_base_context(self) -> dict[str, str]:
        return {
            "rules": self.read_text("RULES.md"),
            "project_memory": self.read_text("MEMORY.md"),
            "topics": self.load_config("topics.json"),
            "sources": self.load_config("sources.json"),
            "rating_rules": self.load_config("rating_rules.json"),
            "output_schema": self.load_config("output_schema.json"),
        }

    def snapshot_skills(self) -> dict[str, str]:
        names = [
            "securities-daily-intel-pipeline",
            "securities-source-research",
            "securities-news-dedup",
            "securities-priority-rating",
            "securities-trend-analysis",
            "securities-report-format",
        ]
        return {name: self.load_skill(name) for name in names}
