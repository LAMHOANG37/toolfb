from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base

class ArticleStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    NORMALIZED = "normalized"
    DUPLICATE = "duplicate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    original_url = Column(String, unique=True, index=True, nullable=False)
    canonical_url = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    author = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    raw_text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    language = Column(String, default="en")
    content_hash = Column(String, index=True, nullable=True)
    status = Column(Enum(ArticleStatus), default=ArticleStatus.DISCOVERED, nullable=False)
    
    # StoryCluster is Many-to-One
    story_cluster_id = Column(Integer, ForeignKey("story_clusters.id"), nullable=True)

    source = relationship("Source")
    story_cluster = relationship("StoryCluster", back_populates="articles", foreign_keys=[story_cluster_id])
