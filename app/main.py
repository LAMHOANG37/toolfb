from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

from app.config import settings
from app.api import routes_dashboard, routes_articles

app = FastAPI(
    title="AI Hôm Nay Có Gì? — Newsroom",
    description="Admin dashboard and backend for automated newsroom.",
    version="0.1.0",
)

# Ensure static directory exists
os.makedirs("app/static/css", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(routes_dashboard.router)
app.include_router(routes_articles.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.app_env}
