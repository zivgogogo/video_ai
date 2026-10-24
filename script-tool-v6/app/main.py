from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import STORAGE_DIR, UPLOADS_DIR, CACHE_DIR, TEXT_STORE_DIR, MEDIA_DIR, WORKBENCH_DIR
from app.db import init_db

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    for d in [STORAGE_DIR, UPLOADS_DIR, CACHE_DIR, TEXT_STORE_DIR, MEDIA_DIR,
              WORKBENCH_DIR, WORKBENCH_DIR / "images", WORKBENCH_DIR / "videos"]:
        d.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="AI Script Tool", version="0.1.0", lifespan=lifespan)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
app.state.templates = templates

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

from app.routes.pages import router as pages_router
from app.routes.api import router as api_router
from app.routes.chat import router as chat_router
from app.routes.media import router as media_router
from app.routes.workbench import router as workbench_router
app.include_router(pages_router)
app.include_router(api_router)
app.include_router(chat_router)
app.include_router(media_router)
app.include_router(workbench_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
