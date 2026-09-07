from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import router


app = FastAPI(
    title="AI Delivery Lifecycle",
    description="Agentic AI workflow for software delivery lifecycle.",
    version="0.1.0",
)


app.include_router(router)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse("app/static/index.html")