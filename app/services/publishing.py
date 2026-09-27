"""Publish immutable, approved snapshots; never automatically retry an ambiguous send."""
import hashlib
import re
from datetime import timedelta
import httpx
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from app.config import settings
from app.models import Draft, PublishJob, Post
from app.models.draft import DraftStatus
from app.models.publish_job import JobStatus
from app.models.operation import log_activity
from app.services.cards import card_file
from app.timeutils import utcnow, aware


def facebook_configured():
    return bool(re.fullmatch(r"\d+", settings.facebook_page_id) and
                re.fullmatch(r"v\d+\.\d+", settings.facebook_graph_api_version) and
                settings.facebook_page_access_token.get_secret_value())


def schedule(db, draft, when, revision):
    if aware(when) < utcnow() - timedelta(seconds=30):
        raise ValueError("Thời gian đăng phải ở hiện tại hoặc tương lai.")
    if not settings.facebook_dry_run and not facebook_configured():
        raise ValueError("Chưa cấu hình đủ Page ID, token và phiên bản Graph API.")
    changed = db.execute(update(Draft).where(Draft.id == draft.id, Draft.status == DraftStatus.APPROVED,
        Draft.revision == revision).values(status=DraftStatus.SCHEDULED, revision=Draft.revision + 1)).rowcount
    if not changed:
        db.rollback()
        raise ValueError("Chỉ lên lịch bản đã duyệt, còn đúng phiên bản. Hãy tải lại.")
    db.refresh(draft)
    if db.query(Post.id).filter_by(draft_id=draft.id).first():
        db.rollback()
        raise ValueError("Bản nháp này đã đăng.")
    body = (draft.facebook_text or "").strip()
    if not body:
        db.rollback()
        raise ValueError("Bài viết chưa có nội dung.")
    image_bytes = card_file(draft.social_card_path).read_bytes() if draft.social_card_path else b""
    digest = hashlib.sha256(settings.facebook_page_id.encode() + b"\0" + body.encode() + b"\0" + image_bytes).hexdigest()
    job = PublishJob(draft_id=draft.id, scheduled_at=when, active_key=f"draft:{draft.id}",
        active_content=None if settings.facebook_dry_run else digest, content_hash=digest,
        payload_text=body, card_path=draft.social_card_path, dry_run=settings.facebook_dry_run,
        page_id=settings.facebook_page_id)
    db.add(job)
    log_activity(db, f"Lên lịch bản nháp #{draft.id} ({'đăng thử' if job.dry_run else 'đăng thật'}).")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Bản nháp hoặc nội dung này đã có lịch đăng.") from None
    return job


def mark_success(db, job, post_id):
    job.status = JobStatus.SUCCESSFUL
    job.completed_at = utcnow()
    job.last_error = None
    job.active_key = None
    # active_content remains reserved for successful live posts.
    job.draft.status = DraftStatus.PUBLISHED
    db.add(Post(draft_id=job.draft_id, facebook_post_id=post_id,
                facebook_url=f"https://www.facebook.com/{post_id}", content_hash=job.content_hash))
    log_activity(db, f"Đã đăng Facebook bản nháp #{job.draft_id}.")
    db.commit()


def dispatch(db, job_id, client=None):
    claimed = db.execute(update(PublishJob).where(PublishJob.id == job_id,
        PublishJob.status == JobStatus.PENDING, PublishJob.scheduled_at <= utcnow())
        .values(status=JobStatus.RUNNING, started_at=utcnow(), attempts=PublishJob.attempts + 1)
        .execution_options(synchronize_session=False)).rowcount
    db.commit()
    if not claimed:
        return False
    job = db.get(PublishJob, job_id)
    db.refresh(job)
    try:
        if job.draft.status != DraftStatus.SCHEDULED or not job.payload_text:
            raise ValueError("Bản nháp không còn hợp lệ để đăng.")
        if job.dry_run:
            job.status = JobStatus.SIMULATED
            job.active_key = None
            job.completed_at = utcnow()
            job.draft.status = DraftStatus.APPROVED
            log_activity(db, f"Đăng thử bản nháp #{job.draft_id} thành công; không gửi Facebook.")
            db.commit()
            return True
        if settings.facebook_dry_run or not facebook_configured() or job.page_id != settings.facebook_page_id:
            raise ValueError("Cấu hình Facebook đã thay đổi hoặc đang ở chế độ đăng thử.")
        if db.query(Post.id).filter((Post.content_hash == job.content_hash) | (Post.draft_id == job.draft_id)).first():
            raise ValueError("Đã có bài đăng cho nội dung hoặc bản nháp này.")
        image_bytes = card_file(job.card_path).read_bytes() if job.card_path else b""
        digest = hashlib.sha256(job.page_id.encode() + b"\0" + job.payload_text.encode() + b"\0" + image_bytes).hexdigest()
        if digest != job.content_hash:
            raise ValueError("Ảnh/nội dung đã thay đổi sau khi duyệt; hãy hủy và lên lịch lại.")
    except (ValueError, OSError) as exc:
        job.status = JobStatus.FAILED
        job.last_error = str(exc)
        db.commit()
        return False
    owned = client is None
    client = client or httpx.Client(timeout=45)
    try:
        url = f"https://graph.facebook.com/{settings.facebook_graph_api_version}/{job.page_id}"
        headers = {"Authorization": f"Bearer {settings.facebook_page_access_token.get_secret_value()}"}
        if job.card_path:
            response = client.post(url + "/photos", headers=headers,
                data={"message": job.payload_text}, files={"source": ("card.png", image_bytes, "image/png")})
        else:
            response = client.post(url + "/feed", headers=headers, data={"message": job.payload_text})
        if 400 <= response.status_code < 500:
            # An explicit API rejection is safe to retry manually after correcting configuration.
            job.status = JobStatus.FAILED
            job.last_error = f"Facebook từ chối HTTP {response.status_code}. Kiểm tra quyền/token và Page."
            db.commit()
            return False
        response.raise_for_status()
        data = response.json()
        post_id = data.get("post_id") if job.card_path else data.get("id")
        if not post_id:
            raise ValueError("Không nhận được ID bài đăng.")
        mark_success(db, job, str(post_id))
        return True
    except Exception:
        # Timeout, 5xx, malformed success, or local failure AFTER sending: it may already be published.
        db.rollback()
        job = db.get(PublishJob, job_id)
        if job.status != JobStatus.SUCCESSFUL:
            job.status = JobStatus.UNCERTAIN
            job.last_error = "Kết quả gửi chưa rõ. Kiểm tra Facebook Page trước khi xử lý; không tự gửi lại."
            db.commit()
        return False
    finally:
        if owned:
            client.close()


def cancel(db, job):
    changed = db.execute(update(PublishJob).where(PublishJob.id == job.id,
        PublishJob.status.in_([JobStatus.PENDING, JobStatus.FAILED]))
        .values(status=JobStatus.CANCELLED, active_key=None, active_content=None, completed_at=utcnow())).rowcount
    if not changed:
        db.rollback()
        raise ValueError("Không thể hủy tác vụ đang gửi hoặc chưa rõ kết quả.")
    db.refresh(job)
    job.draft.status = DraftStatus.APPROVED
    log_activity(db, f"Hủy lịch #{job.id}.")
    db.commit()


def reconcile(db, job, post_id, client=None):
    if job.status != JobStatus.UNCERTAIN:
        raise ValueError("Chỉ đối soát tác vụ chưa rõ kết quả.")
    if not re.fullmatch(re.escape(job.page_id or "") + r"_\d+", post_id):
        raise ValueError("Nhập ID bài đăng dạng PAGE_ID_POST_ID của đúng Page.")
    owned = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.get(f"https://graph.facebook.com/{settings.facebook_graph_api_version}/{post_id}",
            headers={"Authorization": f"Bearer {settings.facebook_page_access_token.get_secret_value()}"},
            params={"fields": "id,message"})
        response.raise_for_status()
        data = response.json()
        if data.get("message", "").strip() != job.payload_text.strip():
            raise ValueError("Nội dung Facebook không khớp bản đã lên lịch.")
        mark_success(db, job, post_id)
    except httpx.HTTPError:
        raise ValueError("Không đọc được bài Facebook để đối soát.") from None
    finally:
        if owned:
            client.close()
