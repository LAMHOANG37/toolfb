from datetime import timedelta
from email.utils import format_datetime
from app.models import Source, Article
from app.models.source import SourceType
from app.collectors.base import ExtractedArticle
from app.collectors.rss import RssCollector
from app.services.ingestion import IngestionService
from app.collectors.source_registry import SourceRegistry
from app.timeutils import utcnow, aware


def test_rss_utc_and_cutoff(monkeypatch):
    stamp = utcnow().replace(microsecond=0)
    xml = f'<rss version="2.0"><channel><title>News</title><item><title>New AI</title><link>https://example.com/new</link><description>Text</description><pubDate>{format_datetime(stamp)}</pubDate></item><item><title>Old</title><link>https://example.com/old</link><pubDate>{format_datetime(stamp-timedelta(days=3))}</pubDate></item></channel></rss>'
    monkeypatch.setattr("app.collectors.rss.fetch_bytes", lambda url: xml.encode())
    articles = RssCollector("Test", "https://example.com", "https://example.com/rss").fetch()
    assert len(articles) == 1
    assert articles[0].published_at == stamp


def test_ingestion_idempotence_and_recovery(db, seed, monkeypatch):
    source, cluster, existing = seed
    existing.story_cluster_id = None
    cluster.primary_article_id = None
    db.commit()
    monkeypatch.setattr(RssCollector, "fetch", lambda self, **kw: [
        ExtractedArticle(title="New unique topic", original_url="https://example.com/new?utm_source=x",
            canonical_url="https://example.com/new?utm_source=x", raw_text="Actual text")])
    service = IngestionService(db)
    first = service.run()
    second = service.run()
    assert first["new_articles"] == 1
    assert second["new_articles"] == 0
    assert second["duplicates_skipped"] == 1
    db.refresh(existing)
    assert existing.story_cluster_id is not None


def test_source_error_does_not_stop_next_source(db, monkeypatch):
    for name in ["Bad", "Good"]:
        db.add(Source(name=name, base_url="https://example.com", feed_url="https://example.com/rss",
            source_type=SourceType.OFFICIAL, strategy="rss"))
    db.commit()
    def fetch(self, **kw):
        if self.source_name == "Bad":
            raise ValueError("boom")
        return [ExtractedArticle(title="Good", original_url="https://example.com/good", canonical_url="https://example.com/good")]
    monkeypatch.setattr(RssCollector, "fetch", fetch)
    result = IngestionService(db).run()
    assert result["errors"] == 1 and result["new_articles"] == 1
    assert db.query(Source).filter_by(name="Bad").one().last_error_message


def test_yaml_honors_active_type_strategy(db, tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text('sources:\n  - name: Official\n    base_url: https://example.com\n    strategy: webpage\n    type: official\n    active: false\n', encoding="utf-8")
    SourceRegistry(config).sync_with_db(db)
    source = db.query(Source).one()
    assert not source.active
    assert source.source_type == SourceType.OFFICIAL
    assert source.strategy == "webpage"
