import json
from dataclasses import dataclass

from jsonschema import Draft7Validator

from app.services.agent_loader import AgentLoader


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


class SchemaValidator:
    def __init__(self, loader: AgentLoader | None = None):
        self.loader = loader or AgentLoader()

    def validate(self, schema_name: str, payload: dict) -> ValidationResult:
        schema = json.loads(self.loader.load_schema(schema_name))
        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        if not errors:
            return ValidationResult(valid=True, errors=[])
        messages = []
        for error in errors:
            path = ".".join(str(item) for item in error.path) or "$"
            messages.append(f"{path}: {error.message}")
        return ValidationResult(valid=False, errors=messages)
