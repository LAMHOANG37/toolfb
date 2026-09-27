from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Article, StoryCluster, Draft, PublishJob, Post, Source, Operation, Activity
from app.models.draft import DraftStatus
from app.models.publish_job import JobStatus
from app.services.operations import enqueue, run_operation
from app.web import render, redirect
from app.timeutils import utcnow
from app.config import settings
from zoneinfo import ZoneInfo

router = APIRouter()


@router.get("/")
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    today = utcnow().astimezone(ZoneInfo(settings.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
    stats = {
        "Tin đã thu thập": db.query(Article).count(),
        "Sự kiện": db.query(StoryCluster).count(),
        "Chờ duyệt": db.query(Draft).filter(Draft.status.in_([DraftStatus.GENERATED, DraftStatus.NEEDS_REVIEW])).count(),
        "Chờ đăng": db.query(PublishJob).filter_by(status=JobStatus.PENDING).count(),
        "Đã đăng hôm nay": db.query(Post).filter(Post.published_at >= today).count(),
    }
    return render(request, "dashboard.html", stats=stats,
        articles=db.query(Article).order_by(Article.fetched_at.desc()).limit(6).all(),
        drafts=db.query(Draft).filter(Draft.status.in_([DraftStatus.GENERATED, DraftStatus.NEEDS_REVIEW])).order_by(Draft.id.desc()).limit(5).all(),
        sources=db.query(Source).order_by(Source.priority.desc()).limit(6).all(),
        operations=db.query(Operation).order_by(Operation.id.desc()).limit(8).all(),
        activities=db.query(Activity).order_by(Activity.id.desc()).limit(8).all(),
        attention=db.query(PublishJob).filter(PublishJob.status.in_([JobStatus.FAILED, JobStatus.UNCERTAIN])).count())


@router.post("/api/ingest")
def trigger_ingestion(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    operation = enqueue(db, "ingest", "ingest")
    background.add_task(run_operation, operation.id)
    return redirect(request, f"/?operation={operation.id}", "Đã bắt đầu quét tin. Kết quả tự cập nhật khi hoàn tất.")


@router.get("/api/operations/{operation_id}")
def operation_status(operation_id: int, db: Session = Depends(get_db)):
    operation = db.get(Operation, operation_id)
    if not operation:
        raise HTTPException(404, "Không tìm thấy tác vụ.")
    return {"id": operation.id, "status": operation.status, "detail": operation.detail}


@router.get("/settings")
def settings_page(request: Request):
    from app.services.publishing import facebook_configured
    return render(request, "settings.html", facebook_ready=facebook_configured(),
        llm_ready=bool(settings.llm_model and (settings.openai_api_key.get_secret_value() if settings.llm_provider == "openai" else settings.gemini_api_key.get_secret_value())))
