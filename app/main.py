import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes.auth import router as auth_router
from app.api.routes.repositories import router as repositories_router
from app.ai.models import get_model_status
from app.api.routes.chat import router as chat_router
from app.api.routes.analysis import router as analysis_router

logging.basicConfig(level=logging.INFO)

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(repositories_router)
app.include_router(chat_router)
app.include_router(analysis_router)


@app.get("/api/models/status")
async def models_status() -> dict:
    return await get_model_status()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
