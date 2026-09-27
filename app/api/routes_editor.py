import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import update
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.config import settings
from app.models import Draft, PublishJob, Source, Post
from app.models.draft import DraftStatus
from app.models.publish_job import JobStatus
from app.models.source import SourceType
from app.models.operation import log_activity
from app.services.cards import create_card, card_file
from app.services.fetching import validate_url
from app.services import publishing
from app.collectors.source_registry import SourceRegistry
from app.timeutils import utcnow
from app.web import render, redirect

router = APIRouter()


def get_draft(db, draft_id):
    draft = db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(404, "Không tìm thấy bản nháp.")
    return draft


def change_draft(db, draft_id, revision, values, allowed=None):
    allowed = allowed or [DraftStatus.GENERATED, DraftStatus.NEEDS_REVIEW, DraftStatus.APPROVED, DraftStatus.REJECTED]
    changed = db.execute(update(Draft).where(Draft.id == draft_id, Draft.revision == revision, Draft.status.in_(allowed))
        .values(**values, revision=Draft.revision + 1)).rowcount
    if not changed:
        db.rollback()
        raise ValueError("Bản nháp đã thay đổi hoặc đang lên lịch/đã đăng. Tải lại trang trước khi sửa.")


@router.get("/drafts")
def drafts(request: Request, status: str = "", q: str = "", page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    query = db.query(Draft)
    if status:
        query = query.filter_by(status=DraftStatus(status))
    if q:
        query = query.filter(Draft.headline.contains(q, autoescape=True))
    total = query.count()
    return render(request, "drafts.html", drafts=query.order_by(Draft.id.desc()).offset((page-1)*20).limit(20).all(),
        page=page, pages=max(1, math.ceil(total/20)), status=status, q=q, total=total)


@router.get("/drafts/{draft_id}")
def draft_detail(request: Request, draft_id: int, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    return render(request, "draft_detail.html", draft=draft, urls=json.loads(draft.source_urls or "[]"))


@router.post("/drafts/{draft_id}/save")
def save_draft(request: Request, draft_id: int, revision: int = Form(...), headline: str = Form(...),
               facebook_text: str = Form(...), verification_notes: str = Form(""), db: Session = Depends(get_db)):
    if not headline.strip() or len(headline) > 180 or not facebook_text.strip() or len(facebook_text) > 12000 or len(verification_notes) > 5000:
        raise ValueError("Tiêu đề tối đa 180 ký tự; nội dung 1–12.000 ký tự; ghi chú tối đa 5.000 ký tự.")
    change_draft(db, draft_id, revision, dict(headline=headline.strip(), facebook_text=facebook_text.strip(),
        verification_notes=verification_notes.strip(), status=DraftStatus.NEEDS_REVIEW, approved_at=None, social_card_path=None))
    log_activity(db, f"Lưu bản nháp #{draft_id}; cần duyệt lại nội dung và ảnh.")
    db.commit()
    return redirect(request, f"/drafts/{draft_id}", "Đã lưu. Ảnh cũ và phê duyệt cũ được gỡ để tránh đăng sai nội dung.")


@router.post("/drafts/{draft_id}/card")
def generate_card(request: Request, draft_id: int, revision: int = Form(...), db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    if draft.revision != revision or draft.status in {DraftStatus.SCHEDULED, DraftStatus.PUBLISHED}:
        raise ValueError("Bản nháp đã thay đổi hoặc bị khóa.")
    path = create_card(draft)
    change_draft(db, draft_id, revision, dict(social_card_path=path, status=DraftStatus.NEEDS_REVIEW, approved_at=None))
    db.commit()
    return redirect(request, f"/drafts/{draft_id}", "Đã tạo ảnh. Kiểm tra ảnh trước khi duyệt.")


@router.get("/cards/{name}")
def card(name: str):
    return FileResponse(card_file(name), media_type="image/png")


@router.post("/drafts/{draft_id}/approve")
def approve(request: Request, draft_id: int, revision: int = Form(...), verified: str = Form(""), db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id)
    if verified != "yes" or not (draft.facebook_text or "").strip() or not (draft.verification_notes or "").strip():
        raise ValueError("Cần nội dung, ghi chú kiểm chứng và xác nhận đã kiểm tra nguồn.")
    change_draft(db, draft_id, revision, dict(status=DraftStatus.APPROVED, approved_at=utcnow()),
        [DraftStatus.GENERATED, DraftStatus.NEEDS_REVIEW])
    draft.story_cluster.verification_status = "editor_reviewed"
    log_activity(db, f"Biên tập viên duyệt bản nháp #{draft_id}.")
    db.commit()
    return redirect(request, f"/drafts/{draft_id}", "Đã duyệt. Bạn có thể lên lịch đăng.")


@router.post("/drafts/{draft_id}/reject")
def reject(request: Request, draft_id: int, revision: int = Form(...), db: Session = Depends(get_db)):
    change_draft(db, draft_id, revision, dict(status=DraftStatus.REJECTED, approved_at=None))
    log_activity(db, f"Từ chối bản nháp #{draft_id}.")
    db.commit()
    return redirect(request, f"/drafts/{draft_id}", "Đã từ chối bản nháp.")


@router.post("/drafts/{draft_id}/schedule")
def schedule(request: Request, draft_id: int, revision: int = Form(...), scheduled_at: str = Form(...), db: Session = Depends(get_db)):
    when = datetime.fromisoformat(scheduled_at)
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo(settings.timezone))
    when = when.astimezone(ZoneInfo("UTC"))
    publishing.schedule(db, get_draft(db, draft_id), when, revision)
    return redirect(request, "/schedule", "Đã lưu lịch và chốt nội dung đăng.")


@router.get("/schedule")
def schedule_page(request: Request, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    total = db.query(PublishJob).count()
    return render(request, "schedule.html", jobs=db.query(PublishJob).order_by(PublishJob.id.desc()).offset((page-1)*20).limit(20).all(),
        posts={p.draft_id: p for p in db.query(Post).all()}, page=page, pages=max(1, math.ceil(total/20)))


def dispatch_background(job_id):
    with SessionLocal() as db:
        publishing.dispatch(db, job_id)


@router.post("/schedule/{job_id}/run")
def run_job(request: Request, job_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if not job or job.status != JobStatus.PENDING:
        raise ValueError("Tác vụ không ở trạng thái chờ.")
    from app.timeutils import aware
    if aware(job.scheduled_at) > utcnow():
        raise ValueError("Chưa đến giờ đăng.")
    background.add_task(dispatch_background, job_id)
    return redirect(request, "/schedule", "Đã yêu cầu xử lý lịch đăng. Tải lại để xem kết quả.")


@router.post("/schedule/{job_id}/cancel")
def cancel_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy lịch đăng.")
    publishing.cancel(db, job)
    return redirect(request, "/schedule", "Đã hủy lịch đăng.")


@router.post("/schedule/{job_id}/retry")
def retry_job(request: Request, job_id: int, db: Session = Depends(get_db)):
    changed = db.execute(update(PublishJob).where(PublishJob.id == job_id, PublishJob.status == JobStatus.FAILED,
        PublishJob.attempts < 3).values(status=JobStatus.PENDING, scheduled_at=utcnow(), last_error=None)).rowcount
    if not changed:
        db.rollback()
        raise ValueError("Chỉ thử lại tác vụ bị từ chối rõ ràng, tối đa 3 lần.")
    log_activity(db, f"Yêu cầu thử lại lịch #{job_id}.")
    db.commit()
    return redirect(request, "/schedule", "Đã đưa tác vụ về hàng chờ.")


@router.post("/schedule/{job_id}/reconcile")
def reconcile_job(request: Request, job_id: int, post_id: str = Form(...), db: Session = Depends(get_db)):
    job = db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy lịch đăng.")
    publishing.reconcile(db, job, post_id.strip())
    return redirect(request, "/schedule", "Đã đối soát bài đăng thành công.")


@router.post("/schedule/{job_id}/confirm-absent")
def confirm_absent(request: Request, job_id: int, confirmed: str = Form(""), db: Session = Depends(get_db)):
    if confirmed != "yes":
        raise ValueError("Cần kiểm tra trực tiếp Page và xác nhận bài chưa được đăng.")
    changed = db.execute(update(PublishJob).where(PublishJob.id == job_id, PublishJob.status == JobStatus.UNCERTAIN)
        .values(status=JobStatus.FAILED, last_error="Biên tập viên xác nhận chưa có bài trên Page.")).rowcount
    if not changed:
        db.rollback()
        raise ValueError("Tác vụ không cần đối soát.")
    log_activity(db, f"Biên tập viên xác nhận lịch #{job_id} chưa đăng trên Page.")
    db.commit()
    return redirect(request, "/schedule", "Đã ghi nhận xác nhận. Có thể thử lại hoặc hủy lịch.")


@router.get("/sources")
def sources(request: Request, db: Session = Depends(get_db)):
    return render(request, "sources.html", sources=db.query(Source).order_by(Source.priority.desc(), Source.name).all())


@router.post("/sources/save")
def save_source(request: Request, name: str = Form(...), base_url: str = Form(...), feed_url: str = Form(""),
                strategy: str = Form(...), source_type: str = Form(...), priority: int = Form(5),
                active: str = Form(""), source_id: int = Form(0), db: Session = Depends(get_db)):
    if not name.strip() or len(name) > 100 or strategy not in {"rss", "webpage"} or not 0 <= priority <= 10:
        raise ValueError("Nguồn chưa hợp lệ; ưu tiên từ 0 đến 10.")
    validate_url(base_url)
    if strategy == "rss":
        validate_url(feed_url)
    source = db.get(Source, source_id) if source_id else Source()
    if source is None:
        raise HTTPException(404, "Không tìm thấy nguồn.")
    if db.query(Source.id).filter(Source.name == name.strip(), Source.id != source_id).first():
        raise ValueError("Tên nguồn đã tồn tại.")
    source.name, source.base_url, source.feed_url = name.strip(), base_url.strip(), feed_url.strip() or None
    source.strategy, source.source_type = strategy, SourceType(source_type)
    source.priority, source.active = priority, active == "yes"
    db.add(source)
    log_activity(db, f"Cập nhật nguồn {source.name}.")
    db.commit()
    return redirect(request, "/sources", "Đã lưu nguồn. Lượt quét tiếp theo sẽ dùng cấu hình này.")


@router.post("/sources/import")
def import_sources(request: Request, db: Session = Depends(get_db)):
    SourceRegistry().sync_with_db(db)
    return redirect(request, "/sources", "Đã nhập cấu hình YAML; nguồn cùng tên được cập nhật.")
