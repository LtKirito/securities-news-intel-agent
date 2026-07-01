from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiKeyUpdate(BaseModel):
    api_key: str = Field(min_length=8)


class ApiKeyStatus(BaseModel):
    configured: bool


class SectorConfigIn(BaseModel):
    name: str
    enabled: bool = True
    keywords: list[str] = []
    expanded_keywords: list[str] = []
    exclude_keywords: list[str] = []
    related_companies: list[str] = []
    chain_nodes: list[str] = []
    verification_metrics: list[str] = []


class ReportGenerateRequest(BaseModel):
    date: str
    sectors: list[str]
    date_window: str = ""
    manual_links: list[str] = []
    collection_modes: list[str] = ["automatic_search", "manual_links"]
    use_mock: bool = False
    runtime_sector_config: SectorConfigIn | None = None
    save_config: bool = False
    source_preferences: dict = {}
    rating_overlay: dict = {}
    allow_limited_confidence_report: bool = True
    allow_commercial_fallback: bool = False
    relax_quality_gate: bool = False


class ChatRequest(BaseModel):
    question: str
    date: str | None = None
    sector: str | None = None
