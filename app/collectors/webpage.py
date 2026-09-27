from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from app.collectors.base import BaseCollector, ExtractedArticle
from app.services.fetching import fetch_bytes, validate_url
from app.timeutils import utcnow, aware


class WebpageCollector(BaseCollector):
    def fetch(self, lookback_hours=36):
        soup = BeautifulSoup(fetch_bytes(self.base_url), "html.parser")
        links = []
        for node in soup.select("a[href]"):
            url = urljoin(self.base_url, node["href"]).split("#")[0]
            if urlparse(url).netloc == urlparse(self.base_url).netloc and url != self.base_url and len(node.get_text(strip=True)) > 15 and url not in links:
                links.append(url)
        articles = []
        for url in links[:12]:
            try:
                page = BeautifulSoup(fetch_bytes(url), "html.parser")
                body = page.select_one("article") or page.select_one("main")
                title = page.select_one("h1")
                stamp = page.select_one('meta[property="article:published_time"]') or page.select_one("time[datetime]")
                if not body or not title or not stamp:
                    continue  # Never invent a publication time or article body.
                published = aware(datetime.fromisoformat((stamp.get("content") or stamp.get("datetime")).replace("Z", "+00:00")))
                if not utcnow() - timedelta(hours=lookback_hours) <= published <= utcnow() + timedelta(minutes=10):
                    continue
                text = "\n".join(p.get_text(" ", strip=True) for p in body.select("p"))
                if len(text) < 100:
                    continue
                canonical = page.select_one('link[rel="canonical"]')
                canonical_url = urljoin(url, canonical["href"]) if canonical and canonical.get("href") else url
                validate_url(canonical_url)
                articles.append(ExtractedArticle(title=title.get_text(" ", strip=True), original_url=url,
                    canonical_url=canonical_url, raw_text=text, published_at=published, source_name=self.source_name))
            except (ValueError, KeyError):
                continue
        return articles
