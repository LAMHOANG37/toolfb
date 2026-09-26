from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from app.database import get_db
from app.models.article import Article
from app.models.story_cluster import StoryCluster
from app.models.source import Source
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/articles")
def list_clusters(
    request: Request, 
    db: Session = Depends(get_db)
):
    # Query story clusters, loading their articles and primary article source
    clusters = (
        db.query(StoryCluster)
        .options(
            joinedload(StoryCluster.articles).joinedload(Article.source)
        )
        .order_by(desc(StoryCluster.created_at))
        .limit(50)
        .all()
    )
    
    context = {
        "request": request,
        "clusters": clusters
    }
    return templates.TemplateResponse(
        request=request, name="articles.html", context=context
    )

@router.post("/api/clusters/merge")
def merge_clusters(request: Request, source_id: int, target_id: int, db: Session = Depends(get_db)):
    source_cluster = db.query(StoryCluster).filter(StoryCluster.id == source_id).first()
    target_cluster = db.query(StoryCluster).filter(StoryCluster.id == target_id).first()
    
    if not source_cluster or not target_cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
        
    for article in source_cluster.articles:
        article.story_cluster_id = target_cluster.id
        
    db.delete(source_cluster)
    
    # Re-evaluate primary article for target cluster
    from app.services.clustering import ClusteringService
    cs = ClusteringService(db)
    
    db.commit() # commit the moves first
    cs.evaluate_primary_article(target_cluster)
    db.commit()
    
    return {"status": "success"}

@router.post("/api/clusters/{cluster_id}/move_article")
def move_article(request: Request, cluster_id: int, article_id: int, new_cluster_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
        
    old_cluster = db.query(StoryCluster).filter(StoryCluster.id == article.story_cluster_id).first()
    target_cluster = db.query(StoryCluster).filter(StoryCluster.id == new_cluster_id).first()
    
    if not target_cluster:
        raise HTTPException(status_code=404, detail="Target cluster not found")
        
    article.story_cluster_id = target_cluster.id
    
    from app.services.clustering import ClusteringService
    cs = ClusteringService(db)
    db.commit()
    
    if old_cluster:
        cs.evaluate_primary_article(old_cluster)
    cs.evaluate_primary_article(target_cluster)
    db.commit()
    
    return {"status": "success"}
