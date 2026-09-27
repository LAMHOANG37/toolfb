from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import ROOT, settings
from app.database import SessionLocal
from app.models import Source, Operation
from app.collectors.source_registry import SourceRegistry
from app.services.operations import tick, periodic_scan
from app.security import router as auth_router, security_middleware
from app.api import routes_dashboard, routes_articles, routes_editor
from app.web import render
from app.timeutils import utcnow


@asynccontextmanager
async def lifespan(app):
    if len(settings.secret_key.get_secret_value()) < 32 or len(settings.admin_password.get_secret_value()) < 12:
        raise RuntimeError("Run scripts/setup_local.py or configure SECRET_KEY (32+ chars) and ADMIN_PASSWORD (12+ chars).")
    if settings.app_env == "production" and not settings.cookie_secure:
        raise RuntimeError("Production requires HTTPS and COOKIE_SECURE=true.")
    with SessionLocal() as db:
        if not db.query(Source.id).first():
            SourceRegistry().sync_with_db(db)
        db.query(Operation).filter_by(status="running").update(
            {"status": "failed", "active_key": None, "detail": "Tác vụ bị gián đoạn khi máy chủ dừng. Có thể thử lại.", "completed_at": utcnow()})
        db.commit()
    scheduler = BackgroundScheduler(timezone="UTC")
    if settings.scheduler_enabled:
        scheduler.add_job(tick, "interval", seconds=15, max_instances=1, coalesce=True)
        if settings.scan_interval_minutes:
            scheduler.add_job(periodic_scan, "interval", minutes=settings.scan_interval_minutes, max_instances=1, coalesce=True)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=True)


app = FastAPI(title="AI Hôm Nay Có Gì? — Newsroom", version="0.2.0", lifespan=lifespan)
app.middleware("http")(security_middleware)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key.get_secret_value() or "unconfigured-startup-will-fail",
    same_site="strict", https_only=settings.cookie_secure, max_age=8*3600)
app.mount("/static", StaticFiles(directory=str(ROOT / "app/static")), name="static")
app.include_router(auth_router)
app.include_router(routes_dashboard.router)
app.include_router(routes_articles.router)
app.include_router(routes_editor.router)


@app.exception_handler(ValueError)
async def invalid_value(request: Request, exc: ValueError):
    return render(request, "error.html", status_code=400, error=str(exc))


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return render(request, "error.html", status_code=422, error="Dữ liệu gửi chưa hợp lệ. Kiểm tra các trường bắt buộc.")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return render(request, "error.html", status_code=exc.status_code, error=str(exc.detail))


@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.app_env}
