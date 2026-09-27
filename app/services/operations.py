import json
import hashlib
from datetime import timedelta
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from app.database import SessionLocal
from app.models import Operation, Article, StoryCluster, Draft
from app.models.draft import DraftStatus
from app.models.article import ArticleStatus
from app.models.operation import log_activity
from app.services.ingestion import IngestionService
from app.services import llm
from app.timeutils import utcnow


def enqueue(db, kind, key):
    operation = Operation(kind=kind, active_key=key, status="queued")
    db.add(operation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Tác vụ tương tự đang chạy. Vui lòng chờ hoàn tất.") from None
    return operation


def fingerprint(articles):
    return hashlib.sha256(json.dumps([(a.id, a.title, a.cleaned_text, a.canonical_url) for a in articles], ensure_ascii=False).encode()).hexdigest()


def editorial_sources(db, cluster_id):
    articles = db.query(Article).filter(Article.story_cluster_id == cluster_id,
        Article.status != ArticleStatus.REJECTED).order_by(Article.id).all()
    cluster = db.get(StoryCluster, cluster_id)
    articles.sort(key=lambda article: (article.id != cluster.primary_article_id,
        -(article.source.priority or 0), article.id))
    return articles


def run_operation(operation_id):
    with SessionLocal() as db:
        changed = db.execute(update(Operation).where(Operation.id == operation_id, Operation.status == "queued")
            .values(status="running", started_at=utcnow())).rowcount
        db.commit()
        if not changed:
            return
        operation = db.get(Operation, operation_id)
        try:
            if operation.kind == "ingest":
                stats = IngestionService(db).run()
                detail = f"Quét {stats['sources_scanned']} nguồn · {stats['new_articles']} tin mới · {stats['duplicates_skipped']} tin trùng · {stats['errors']} lỗi."
                status = "partial" if stats["errors"] else "completed"
            elif operation.kind.startswith("generate:"):
                cluster_id = int(operation.kind.split(":")[1])
                articles = editorial_sources(db, cluster_id)
                if not articles:
                    raise ValueError("Sự kiện không còn bài nguồn.")
                before = fingerprint(articles)
                generated = llm.generate(articles)
                db.expire_all()
                articles = editorial_sources(db, cluster_id)
                if fingerprint(articles) != before:
                    raise ValueError("Nguồn đã thay đổi khi AI đang viết. Hãy tạo lại bản nháp.")
                cluster = db.get(StoryCluster, cluster_id)
                draft = Draft(story_cluster_id=cluster_id, status=DraftStatus.NEEDS_REVIEW,
                    source_label=", ".join(dict.fromkeys(a.source.name for a in articles[:8])),
                    source_urls=json.dumps([a.canonical_url for a in articles[:8]], ensure_ascii=False),
                    **generated.model_dump(exclude={"importance_score", "relevance_score", "confidence_score"}))
                # Append trusted source URLs in application code, not model-produced URLs.
                import re
                draft.facebook_text = re.sub(r"https?://\S+", "", draft.facebook_text).strip()
                draft.facebook_text += "\n\nNguồn:\n" + "\n".join(a.canonical_url for a in articles[:8])
                cluster.importance_score = generated.importance_score
                cluster.relevance_score = generated.relevance_score
                cluster.confidence_score = generated.confidence_score
                cluster.verification_status = "pending"
                db.add(draft)
                db.flush()
                detail, status = f"Đã tạo bản nháp #{draft.id}; cần người biên tập kiểm chứng và duyệt.", "completed"
            else:
                raise ValueError("Tác vụ không hợp lệ.")
            operation.status, operation.detail = status, detail
            log_activity(db, detail)
        except Exception as exc:
            db.rollback()
            operation = db.get(Operation, operation_id)
            operation.status = "failed"
            operation.detail = str(exc)[:400] if type(exc) is ValueError else "Tác vụ thất bại. Kiểm tra cấu hình và nguồn rồi thử lại."
            log_activity(db, operation.detail)
        operation.active_key = None
        operation.completed_at = utcnow()
        db.commit()


def tick():
    from app.config import settings
    from app.models import PublishJob
    from app.models.publish_job import JobStatus
    from app.services.publishing import dispatch
    with SessionLocal() as db:
        # Stale live sends require reconciliation, never automatic retry.
        db.query(PublishJob).filter(PublishJob.status == JobStatus.RUNNING, PublishJob.dry_run.is_(False),
            PublishJob.started_at < utcnow() - timedelta(minutes=10)).update(
            {"status": JobStatus.UNCERTAIN, "last_error": "Tác vụ bị gián đoạn. Cần đối soát Facebook."}, synchronize_session=False)
        db.query(PublishJob).filter(PublishJob.status == JobStatus.RUNNING, PublishJob.dry_run.is_(True),
            PublishJob.started_at < utcnow() - timedelta(minutes=10)).update(
            {"status": JobStatus.PENDING, "last_error": "Đăng thử bị gián đoạn; đã đưa về hàng chờ."}, synchronize_session=False)
        db.commit()
        queued = [row[0] for row in db.query(Operation.id).filter_by(status="queued").all()]
    for operation_id in queued:
        run_operation(operation_id)
    if settings.auto_publish:
        with SessionLocal() as db:
            ids = [row[0] for row in db.query(PublishJob.id).filter(
                PublishJob.status == JobStatus.PENDING, PublishJob.scheduled_at <= utcnow()).all()]
        for job_id in ids:
            with SessionLocal() as db:
                dispatch(db, job_id)


def periodic_scan():
    with SessionLocal() as db:
        try:
            enqueue(db, "ingest", "ingest")
        except ValueError:
            pass
