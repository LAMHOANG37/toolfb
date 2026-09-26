from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class ExtractedArticle(BaseModel):
    title: str
    original_url: str
    canonical_url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    raw_text: Optional[str] = None
    source_name: Optional[str] = None  

class BaseCollector(ABC):
    def __init__(self, source_name: str, base_url: str, feed_url: Optional[str] = None):
        self.source_name = source_name
        self.base_url = base_url
        self.feed_url = feed_url

    @abstractmethod
    def fetch(self, lookback_hours: int = 36) -> List[ExtractedArticle]:
        """
        Fetch new articles from the source within the lookback window.
        Returns a list of ExtractedArticle.
        """
        pass
