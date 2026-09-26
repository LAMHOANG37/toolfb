import feedparser
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from time import mktime
import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, ExtractedArticle

class RssFetchError(Exception):
    """Exception raised when an RSS feed cannot be fetched."""
    pass

class RssCollector(BaseCollector):
    def fetch(self, lookback_hours: int = 36) -> List[ExtractedArticle]:
        if not self.feed_url:
            return []
            
        try:
            with httpx.Client(timeout=10.0, headers={'User-Agent': 'AI-Newsroom-Bot/1.0'}) as client:
                response = client.get(self.feed_url)
                response.raise_for_status()
                feed_content = response.content
        except httpx.RequestError as e:
            raise RssFetchError(f"Network error fetching {self.feed_url}: {str(e)}")
        except httpx.HTTPStatusError as e:
            raise RssFetchError(f"HTTP error {e.response.status_code} fetching {self.feed_url}")
            
        parsed_feed = feedparser.parse(feed_content)
        
        # Check if feedparser reported a structural error
        if parsed_feed.bozo and not parsed_feed.entries:
            raise RssFetchError(f"Failed to parse RSS feed from {self.feed_url}: {str(parsed_feed.bozo_exception)}")
            
        articles = []
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
        
        for entry in parsed_feed.entries:
            # Parse published time
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_at = datetime.fromtimestamp(mktime(entry.published_parsed))
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_at = datetime.fromtimestamp(mktime(entry.updated_parsed))
                
            if published_at and published_at < cutoff_time:
                continue
                
            # Try to get content
            raw_text = ""
            if hasattr(entry, 'content'):
                raw_text = entry.content[0].value
            elif hasattr(entry, 'summary'):
                raw_text = entry.summary
                
            # Strip HTML tags
            soup = BeautifulSoup(raw_text, "html.parser")
            clean_text = soup.get_text(separator='\n', strip=True)
            
            author = getattr(entry, 'author', None)
            
            # Use link as original url, some feeds use id
            original_url = getattr(entry, 'link', getattr(entry, 'id', None))
            
            # Extract summary
            summary = ""
            if hasattr(entry, 'summary'):
                summary = BeautifulSoup(entry.summary, "html.parser").get_text(separator='\n', strip=True)
            
            if original_url and clean_text:
                articles.append(
                    ExtractedArticle(
                        title=getattr(entry, 'title', ''),
                        original_url=original_url,
                        canonical_url=original_url, # Will be handled by normalization layer later
                        author=author,
                        published_at=published_at,
                        summary=summary,
                        raw_text=clean_text,
                        source_name=getattr(self, 'source_name', None)
                    )
                )
                
        return articles
