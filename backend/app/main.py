from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import PROJECT_ROOT
from app.db.database import Base, engine
from app.routers import api_keys, auth, chat, configs, reports, sector_templates

app = FastAPI(title="Securities Daily Intel System", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["api-keys"])
app.include_router(configs.router, prefix="/api/configs", tags=["configs"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(sector_templates.router, prefix="/api/sector-templates", tags=["sector-templates"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/api")
def api_root():
    return {"service": "Securities Daily Intel API", "version": "0.1.0", "docs": "/docs"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        requested = FRONTEND_DIST / full_path
        if full_path and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
