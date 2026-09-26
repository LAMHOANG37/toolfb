import httpx
import pytest
from app.services.ingestion import IngestionService
from app.models.article import Article
from app.models.source import Source
from tests.test_main import TestingSessionLocal, engine, Base

# Ensure models are loaded before create_all
from app.models.source import Source
from app.models.article import Article
from app.models.story_cluster import StoryCluster
from app.models.draft import Draft
from app.models.post import Post
from app.models.publish_job import PublishJob

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

class MockResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code
        
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Error", request=None, response=self)

MOCK_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Mock AI News</title>
    <item>
      <title>GPT-5 Announced</title>
      <link>https://example.com/gpt5?utm_source=test</link>
      <description>OpenAI announces GPT-5.</description>
      <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

class MockHttpxClient:
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    def get(self, url, *args, **kwargs):
        if "error" in url:
            raise httpx.RequestError("Mock network error")
        return MockResponse(MOCK_RSS_XML)

def test_ingestion_service(monkeypatch):
    monkeypatch.setattr("httpx.Client", MockHttpxClient)
    
    db = TestingSessionLocal()
    try:
        # Clear tables for test isolation
        db.query(Article).delete()
        db.query(StoryCluster).delete()
        db.query(Source).delete()
        db.commit()
        
        s1 = Source(name="Valid Source", base_url="https://valid.com", feed_url="https://valid.com/rss", source_type="official")
        s2 = Source(name="Error Source", base_url="https://error.com", feed_url="https://error.com/rss", source_type="official")
        db.add_all([s1, s2])
        db.commit()
        
        service = IngestionService(db)
        
        # Test 1: First run
        stats = service.run(lookback_hours=999999)
        
        assert stats["sources_scanned"] == 2
        assert stats["articles_fetched"] == 1 # only 1 valid source returns 1 item
        assert stats["new_articles"] == 1
        assert stats["errors"] == 1
        
        # Verify article was stored and normalized
        articles = db.query(Article).all()
        assert len(articles) == 1
        assert articles[0].title == "GPT-5 Announced"
        assert articles[0].original_url == "https://example.com/gpt5?utm_source=test"
        assert articles[0].canonical_url == "https://example.com/gpt5" # Normalized!
        assert articles[0].status.value.lower() == "discovered"
        
        # Verify source isolation / health
        sources = db.query(Source).order_by(Source.name).all()
        err_source = [s for s in sources if s.name == "Error Source"][0]
        val_source = [s for s in sources if s.name == "Valid Source"][0]
        
        assert err_source.last_error_at is not None
        assert err_source.last_error_message is not None
        assert val_source.last_success_at is not None
        
        # Test 2: Duplicate prevention
        stats_2 = service.run(lookback_hours=999999)
        assert stats_2["new_articles"] == 0
        assert stats_2["duplicates_skipped"] == 1
        
    finally:
        db.close()
