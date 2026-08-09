from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api.routes import router
from app.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=f"{settings.brand_name} / {settings.brand_name_en}：证据驱动的科研解释工作台 API。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def redact_secret_validation_errors(
    request: Request,
    exc: RequestValidationError,
):
    """Do not echo a submitted credential in Pydantic's validation detail."""

    if request.url.path == "/api/v1/settings/api-keys":
        return JSONResponse(
            status_code=422,
            content={"detail": "API Key 请求格式无效；请提供至少一个合法槽位。"},
        )
    return await request_validation_exception_handler(request, exc)

frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
# Keep the older /static URLs working for anyone who has bookmarked the first
# version of the interface.  The new frontend uses relative asset URLs so the
# exact same files can be served by FastAPI locally and as a static GitHub
# Pages artifact under a repository subpath.
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
# This mount is intentionally registered after the API router: /api/v1/*
# continues to be handled by FastAPI, while /, /app.js, /styles.css and
# /runtime-config.js resolve relative to the frontend directory.
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
