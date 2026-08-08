from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")
