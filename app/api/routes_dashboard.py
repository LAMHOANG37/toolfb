from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
import yaml

from app.database import get_db
from app.models.article import Article
from app.models.story_cluster import StoryCluster
from app.models.draft import Draft
from app.models.publish_job import PublishJob
from app.services.ingestion import IngestionService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Fetch recent articles for 'Tin đáng chú ý'
    recent_articles = db.query(Article).order_by(Article.published_at.desc()).limit(5).all()
    top_stories = []
    for art in recent_articles:
        if art.published_at:
            time_diff = datetime.now(timezone.utc) - art.published_at.replace(tzinfo=timezone.utc)
            minutes = int(time_diff.total_seconds() / 60)
            if minutes < 60:
                time_ago = f"{minutes} phút trước"
            elif minutes < 1440:
                time_ago = f"{minutes // 60} giờ trước"
            else:
                time_ago = f"{minutes // 1440} ngày trước"
        else:
            time_ago = "Vừa xong"
            
        top_stories.append({
            "id": art.id,
            "source": getattr(art.source, 'name', 'Unknown Source') if art.source else 'Unknown Source',
            "time_ago": time_ago,
            "title": art.title,
            "related_count": "1", # Future: implement clustering relations count
            "status": "Mới" if art.status == 'DISCOVERED' else "Đã phân tích"
        })

    # Fetch sources status
    try:
        with open("sources.yaml", "r", encoding="utf-8") as f:
            sources_config = yaml.safe_load(f)
            sources = sources_config.get("sources", [])
    except Exception:
        sources = []
        
    source_statuses = []
    for s in sources[:5]: # Show top 5 sources
        source_statuses.append({
            "name": s.get("name", "Unknown"),
            "status": "Hoạt động"
        })
        
    last_scan_time = datetime.now().strftime("%H:%M") # In real app, query latest ingestion job log
    
    context = {
        "request": request,
        "articles_collected": db.query(func.count(Article.id)).scalar(),
        "new_articles": db.query(func.count(Article.id)).filter(Article.status == 'DISCOVERED').scalar(),
        "story_clusters": db.query(func.count(StoryCluster.id)).scalar(),
        "drafts_awaiting_review": db.query(func.count(Draft.id)).filter(Draft.status == 'pending_review').scalar(),
        "scheduled_posts": db.query(func.count(PublishJob.id)).filter(PublishJob.status == 'pending').scalar(),
        "published_today": db.query(func.count(PublishJob.id)).filter(PublishJob.status == 'successful', PublishJob.scheduled_at >= today_start).scalar(),
        "errors_count": db.query(func.count(PublishJob.id)).filter(PublishJob.status == 'failed').scalar(),
        
        "top_stories": top_stories,
        "review_queue": [],
        "source_statuses": source_statuses,
        "last_scan_time": last_scan_time,
        "recent_activity": []
    }
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context=context
    )

@router.post("/api/ingest")
def trigger_ingestion(request: Request, db: Session = Depends(get_db)):
    service = IngestionService(db)
    # Sync first to ensure we have latest from yaml
    service.registry.sync_with_db(db)
    stats = service.run(lookback_hours=36)
    
    errors_html = f"<li>Lỗi: <strong>{stats['errors']}</strong></li>" if stats['errors'] > 0 else ""
    error_header = f" và {stats['errors']} lỗi" if stats['errors'] > 0 else ""
    
    html = (
        '<div class="alert" style="background-color: var(--color-surface); padding: 1.5rem; border-radius: var(--radius); border: 1px solid var(--color-success); box-shadow: var(--shadow); margin-bottom: 2rem;">'
        '<div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">'
        '<span style="font-size: 1.5rem; color: var(--color-success);">✓</span>'
        '<strong style="font-size: 1.1rem; color: var(--color-primary-dark);">Quét tin hoàn tất</strong>'
        '</div>'
        '<p style="margin: 0 0 0 2.25rem; color: var(--color-muted);">'
        f'Đã quét {stats["sources_scanned"]} nguồn. Có {stats["articles_fetched"]} bài được đọc. '
        f'Tìm thấy {stats["new_articles"]} tin mới{error_header}.'
        '</p>'
        '</div>'
    )
    return HTMLResponse(content=html)
