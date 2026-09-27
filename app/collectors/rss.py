import calendar
from datetime import datetime, timezone, timedelta
import feedparser
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector, ExtractedArticle
from app.services.fetching import fetch_bytes, validate_url
from app.timeutils import utcnow


class RssFetchError(Exception):
    pass


class RssCollector(BaseCollector):
    def fetch(self, lookback_hours=36):
        if not self.feed_url:
            raise RssFetchError("Nguồn RSS chưa có feed URL.")
        try:
            feed = feedparser.parse(fetch_bytes(self.feed_url))
        except Exception as exc:
            raise RssFetchError("Không tải được RSS; kiểm tra URL/kết nối.") from exc
        if feed.bozo and not feed.entries:
            raise RssFetchError("Nội dung không phải RSS hợp lệ.")
        cutoff = utcnow() - timedelta(hours=lookback_hours)
        result = []
        for entry in feed.entries[:500]:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            published = datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) if stamp else None
            if published and (published < cutoff or published > utcnow() + timedelta(minutes=10)):
                continue
            url = entry.get("link") or entry.get("id")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue
            try:
                validate_url(url)
            except ValueError:
                continue
            content = entry.get("content") or []
            raw = content[0].get("value", "") if content else entry.get("summary", "")
            text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
            result.append(ExtractedArticle(title=title, original_url=url, canonical_url=url,
                published_at=published, author=entry.get("author"), raw_text=text,
                source_name=self.source_name))
        return result
