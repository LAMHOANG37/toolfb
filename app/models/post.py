from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (Index("uq_post_content_hash", "content_hash", unique=True),)

    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"), nullable=False)
    facebook_post_id = Column(String, unique=True, index=True, nullable=False)
    facebook_url = Column(String, nullable=True)
    content_hash = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    draft = relationship("Draft", back_populates="posts")
