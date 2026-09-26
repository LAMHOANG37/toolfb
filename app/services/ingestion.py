import logging
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.source import Source
from app.models.article import Article, ArticleStatus
from app.collectors.source_registry import SourceRegistry
from app.collectors.rss import RssCollector, RssFetchError
from app.collectors.webpage import WebpageCollector
from app.services.normalization import normalize_url, generate_article_hash
from app.services.clustering import ClusteringService

logger = logging.getLogger(__name__)

class IngestionService:
    def __init__(self, db: Session):
        self.db = db
        self.registry = SourceRegistry()
        self.clustering_service = ClusteringService(self.db)

    def run(self, lookback_hours: int = 36) -> Dict[str, Any]:
        """
        Runs the ingestion pipeline for all active sources.
        Returns a dictionary with execution statistics.
        """
        sources = self.registry.get_active_sources(self.db)
        
        stats = {
            "sources_scanned": len(sources),
            "articles_fetched": 0,
            "new_articles": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "clusters_created": 0
        }
        
        seen_urls = set()
        new_article_ids = []
        
        for source in sources:
            try:
                # Determine strategy
                if source.feed_url:
                    collector = RssCollector(source.name, source.base_url, source.feed_url)
                else:
                    collector = WebpageCollector(source.name, source.base_url)

                extracted_articles = collector.fetch(lookback_hours=lookback_hours)
                stats["articles_fetched"] += len(extracted_articles)
                
                for ext in extracted_articles:
                    # Normalize URL
                    norm_url = normalize_url(ext.canonical_url)
                    if not norm_url:
                        norm_url = ext.canonical_url
                        
                    if norm_url in seen_urls:
                        stats["duplicates_skipped"] += 1
                        continue
                        
                    # Generate hash for exact duplicate detection
                    content_hash = generate_article_hash(norm_url, ext.title)
                        
                    # Check if we already have this exact article (by canonical URL or hash)
                    exists = self.db.query(Article).filter(
                        (Article.canonical_url == norm_url) | 
                        (Article.content_hash == content_hash)
                    ).first()
                    
                    if exists:
                        stats["duplicates_skipped"] += 1
                        seen_urls.add(norm_url)
                        continue
                    
                    new_article = Article(
                        source_id=source.id,
                        original_url=ext.original_url,
                        canonical_url=norm_url,
                        title=ext.title,
                        author=ext.author,
                        published_at=ext.published_at,
                        raw_text=ext.raw_text,
                        cleaned_text=ext.raw_text,
                        content_hash=content_hash,
                        status=ArticleStatus.DISCOVERED
                    )
                    self.db.add(new_article)
                    self.db.flush() # flush to get the ID
                    new_article_ids.append(new_article.id)
                    
                    stats["new_articles"] += 1
                    seen_urls.add(norm_url)
                    
                # Commit per source so partial failures don't drop everything
                source.last_success_at = func.now()
                self.db.commit()
                
            except Exception as e:
                logger.error(f"Error ingesting source {source.name}: {e}")
                stats["errors"] += 1
                source.last_error_at = func.now()
                source.last_error_message = str(e)
                self.db.commit() # Save the error state
                
        # Cluster the newly added articles
        if new_article_ids:
            stats["clusters_created"] = self.clustering_service.cluster_articles(new_article_ids)
            
        return stats
