import math
from fastapi import APIRouter, Depends, Request, Form, Query, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models import Article, StoryCluster, Source, Draft, Operation
from app.models.article import ArticleStatus
from app.models.draft import DraftStatus
from app.models.operation import log_activity
from app.services.clustering import ClusteringService
from app.services.operations import enqueue, run_operation
from app.web import render, redirect

router = APIRouter()


def get_cluster(db, cluster_id):
    cluster = db.get(StoryCluster, cluster_id)
    if not cluster:
        raise HTTPException(404, "Không tìm thấy sự kiện.")
    return cluster


def check_group_editable(db, *clusters):
    for cluster in clusters:
        if db.query(Draft.id).filter_by(story_cluster_id=cluster.id).first():
            raise ValueError("Sự kiện đã có bản nháp. Giữ nguyên nguồn để bảo toàn nội dung biên tập.")
        if db.query(Operation.id).filter(Operation.active_key == f"generate:{cluster.id}").first():
            raise ValueError("AI đang xử lý sự kiện. Hãy chờ hoàn tất.")


@router.get("/articles")
def old_articles():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/events", status_code=307)


@router.get("/news")
def news(request: Request, q: str = "", source_id: str = "", status: str = "",
         page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    query = db.query(Article).options(joinedload(Article.source))
    if q:
        query = query.filter(Article.title.contains(q, autoescape=True))
    if source_id:
        source_id = int(source_id)
        query = query.filter_by(source_id=source_id)
    if status:
        query = query.filter_by(status=ArticleStatus(status))
    total = query.count()
    return render(request, "news.html", articles=query.order_by(Article.fetched_at.desc(), Article.id.desc()).offset((page - 1) * 20).limit(20).all(),
        sources=db.query(Source).order_by(Source.name).all(), q=q, source_id=source_id, status=status,
        page=page, pages=max(1, math.ceil(total / 20)), total=total)


@router.get("/news/{article_id}")
def article_detail(request: Request, article_id: int, db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Không tìm thấy bài.")
    return render(request, "article_detail.html", article=article)


@router.post("/news/{article_id}/status")
def article_status(request: Request, article_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(404, "Không tìm thấy bài.")
    article.status = ArticleStatus(status)
    db.commit()
    return redirect(request, f"/news/{article_id}", "Đã cập nhật trạng thái bài.")


@router.get("/events")
def list_clusters(request: Request, q: str = "", page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    query = db.query(StoryCluster)
    if q:
        query = query.filter(StoryCluster.canonical_title.contains(q, autoescape=True))
    total = query.count()
    return render(request, "events.html", clusters=query.order_by(StoryCluster.id.desc()).offset((page - 1) * 20).limit(20).all(),
        q=q, page=page, pages=max(1, math.ceil(total / 20)), total=total)


@router.get("/events/{cluster_id}")
def event_detail(request: Request, cluster_id: int, db: Session = Depends(get_db)):
    cluster = get_cluster(db, cluster_id)
    return render(request, "event_detail.html", cluster=cluster,
        primary=db.get(Article, cluster.primary_article_id) if cluster.primary_article_id else None,
        targets=db.query(StoryCluster).filter(StoryCluster.id != cluster_id).order_by(StoryCluster.id.desc()).limit(300).all())


@router.post("/api/clusters/merge")
def merge_clusters(request: Request, source_id: int = Form(...), target_id: int = Form(...), db: Session = Depends(get_db)):
    if source_id == target_id:
        raise ValueError("Không thể gộp sự kiện vào chính nó.")
    source, target = get_cluster(db, source_id), get_cluster(db, target_id)
    check_group_editable(db, source, target)
    source.primary_article_id = None
    for article in list(source.articles):
        article.story_cluster = target
    db.flush()
    db.delete(source)
    ClusteringService(db).evaluate_primary_article(target)
    log_activity(db, f"Gộp sự kiện #{source_id} vào #{target_id}.")
    db.commit()
    return redirect(request, f"/events/{target_id}", "Đã gộp sự kiện.")


@router.post("/api/clusters/{cluster_id}/move_article")
def move_article(request: Request, cluster_id: int, article_id: int = Form(...),
                 new_cluster_id: int = Form(...), db: Session = Depends(get_db)):
    source = get_cluster(db, cluster_id)
    article = db.get(Article, article_id)
    if not article or article.story_cluster_id != cluster_id:
        raise ValueError("Bài không thuộc sự kiện này.")
    target = get_cluster(db, new_cluster_id)
    if target.id == source.id:
        raise ValueError("Bài đã thuộc sự kiện đích.")
    check_group_editable(db, source, target)
    article.story_cluster = target
    service = ClusteringService(db)
    service.evaluate_primary_article(source)
    service.evaluate_primary_article(target)
    if not db.query(Article.id).filter_by(story_cluster_id=source.id).first():
        db.delete(source)
    log_activity(db, f"Chuyển bài #{article_id} sang sự kiện #{target.id}.")
    db.commit()
    return redirect(request, f"/events/{target.id}", "Đã chuyển bài.")


@router.post("/events/{cluster_id}/primary")
def choose_primary(request: Request, cluster_id: int, article_id: int = Form(...), db: Session = Depends(get_db)):
    cluster = get_cluster(db, cluster_id)
    check_group_editable(db, cluster)
    article = db.get(Article, article_id)
    if not article or article.story_cluster_id != cluster_id:
        raise ValueError("Nguồn không thuộc sự kiện.")
    cluster.primary_article_id = article.id
    cluster.canonical_title = article.title
    cluster.summary = (article.cleaned_text or "")[:500]
    db.commit()
    return redirect(request, f"/events/{cluster_id}", "Đã chọn bài đại diện.")


@router.post("/events/{cluster_id}/generate")
def generate_draft(request: Request, cluster_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    get_cluster(db, cluster_id)
    operation = enqueue(db, f"generate:{cluster_id}", f"generate:{cluster_id}")
    background.add_task(run_operation, operation.id)
    return redirect(request, f"/drafts?operation={operation.id}", "AI đang soạn bản nháp từ các nguồn của sự kiện.")


@router.post("/events/{cluster_id}/manual")
def manual_draft(request: Request, cluster_id: int, db: Session = Depends(get_db)):
    import json
    cluster = get_cluster(db, cluster_id)
    articles = [a for a in cluster.articles if a.status != ArticleStatus.REJECTED]
    if not articles:
        raise ValueError("Sự kiện chưa có nguồn.")
    draft = Draft(story_cluster_id=cluster_id, headline=cluster.canonical_title[:180],
        status=DraftStatus.NEEDS_REVIEW, facebook_text="",
        source_label=", ".join(dict.fromkeys(a.source.name for a in articles)),
        source_urls=json.dumps([a.canonical_url for a in articles], ensure_ascii=False))
    db.add(draft)
    db.commit()
    return redirect(request, f"/drafts/{draft.id}", "Đã tạo bản nháp để viết thủ công.")
