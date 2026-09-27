import logging
from app.models.source import Source
from app.models.article import Article
from app.collectors.source_registry import SourceRegistry
from app.collectors.rss import RssCollector
from app.collectors.webpage import WebpageCollector
from app.services.normalization import normalize_url, generate_article_hash
from app.services.clustering import ClusteringService
from app.timeutils import utcnow

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, db):
        self.db = db
        self.registry = SourceRegistry()
        self.clustering_service = ClusteringService(db)

    def run(self, lookback_hours=36):
        source_ids = [s.id for s in self.registry.get_active_sources(self.db)]
        stats = dict(sources_scanned=len(source_ids), articles_fetched=0, new_articles=0,
                     duplicates_skipped=0, errors=0, clusters_created=0)
        for source_id in source_ids:
            added = duplicates = 0
            try:
                source = self.db.get(Source, source_id)
                collector_cls = RssCollector if source.strategy == "rss" else WebpageCollector
                collector = collector_cls(source.name, source.base_url, source.feed_url)
                extracted = collector.fetch(lookback_hours=lookback_hours)
                stats["articles_fetched"] += len(extracted)
                for item in extracted:
                    url = normalize_url(item.canonical_url)
                    digest = generate_article_hash(url, item.title)
                    if self.db.query(Article.id).filter((Article.canonical_url == url) | (Article.original_url == item.original_url) | (Article.content_hash == digest)).first():
                        duplicates += 1
                        continue
                    self.db.add(Article(source_id=source.id, title=item.title, original_url=item.original_url,
                        canonical_url=url, content_hash=digest, author=item.author, published_at=item.published_at,
                        raw_text=item.raw_text, cleaned_text=item.raw_text))
                    self.db.flush()
                    added += 1
                source.last_success_at = utcnow()
                source.last_error_message = None
                self.db.commit()
                stats["new_articles"] += added
                stats["duplicates_skipped"] += duplicates
            except Exception:
                self.db.rollback()
                stats["errors"] += 1
                source = self.db.get(Source, source_id)
                source.last_error_at = utcnow()
                source.last_error_message = "Không thu thập được nguồn. Kiểm tra URL, RSS và kết nối rồi quét lại."
                self.db.commit()
                logger.warning("Source %s ingestion failed", source_id)
        # Recover orphaned articles from any earlier interrupted clustering run.
        ids = [r[0] for r in self.db.query(Article.id).filter(Article.story_cluster_id.is_(None)).all()]
        if ids:
            stats["clusters_created"] = self.clustering_service.cluster_articles(ids)
        return stats
