from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

class StoryCluster(Base):
    __tablename__ = "story_clusters"

    id = Column(Integer, primary_key=True, index=True)
    canonical_title = Column(String, nullable=False)
    summary = Column(String, nullable=True)
    topic = Column(String, nullable=True)
    importance_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    verification_status = Column(String, default="pending")
    primary_article_id = Column(Integer, ForeignKey("articles.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # One-to-Many
    articles = relationship("Article", back_populates="story_cluster", foreign_keys="[Article.story_cluster_id]")
    # A cluster can have one active draft
    drafts = relationship("Draft", back_populates="story_cluster")
