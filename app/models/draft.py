from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base

class DraftStatus(str, enum.Enum):
    GENERATED = "generated"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, index=True)
    story_cluster_id = Column(Integer, ForeignKey("story_clusters.id"), nullable=False)
    headline = Column(String, nullable=True)
    hook = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    why_it_matters = Column(Text, nullable=True)
    practical_impact = Column(Text, nullable=True)
    facebook_text = Column(Text, nullable=True)
    source_label = Column(String, nullable=True)
    source_urls = Column(String, nullable=True) # JSON encoded list of URLs
    social_card_path = Column(String, nullable=True)
    status = Column(Enum(DraftStatus), default=DraftStatus.GENERATED, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    story_cluster = relationship("StoryCluster", back_populates="drafts")
    publish_jobs = relationship("PublishJob", back_populates="draft")
    posts = relationship("Post", back_populates="draft")
