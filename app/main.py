from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="AI Delivery Lifecycle",
    description="Agentic AI workflow for software delivery lifecycle.",
    version="0.1.0",
)


app.include_router(router)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")