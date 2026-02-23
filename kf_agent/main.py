"""客服软件操控服务 - FastAPI 入口。"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.staticfiles import StaticFiles

from kf_agent.config import get_settings
from kf_agent.api.routes import customer_service, config_editor, editor_tools

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 静态资源目录（包内 static，安装后随包一起）
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.platforms_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="客服软件操控 API",
    description="打开/关闭多平台客服软件，支持千牛、小红书、抖音等；流程与按钮可配置。",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )

app.include_router(customer_service.router, prefix="/customer_service", tags=["customer_service"])
app.include_router(config_editor.router, prefix="/config", tags=["config"])
app.include_router(editor_tools.router, prefix="/config", tags=["config"])


@app.get("/editor", include_in_schema=False)
async def editor_page():
    """流程编辑器单页入口。"""
    path = STATIC_DIR / "editor" / "index.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="editor not found")
    return FileResponse(path)


@app.get("/health")
async def health():
    return {"status": "ok"}


def run() -> None:
    """命令行入口：读取配置并启动 uvicorn。"""
    settings = get_settings()
    uvicorn.run(
        "kf_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
