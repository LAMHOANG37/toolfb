from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SIMULATED = "simulated"
    UNCERTAIN = "uncertain"

class PublishJob(Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        Index("uq_job_active_key", "active_key", unique=True),
        Index("uq_job_active_content", "active_content", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    attempts = Column(Integer, default=0)
    last_error = Column(String, nullable=True)
    active_key = Column(String, nullable=True)
    active_content = Column(String, nullable=True)
    page_id = Column(String, nullable=True)
    payload_text = Column(Text, nullable=True)
    card_path = Column(String, nullable=True)
    content_hash = Column(String, nullable=True, index=True)
    dry_run = Column(Boolean, nullable=False, default=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    draft = relationship("Draft", back_populates="publish_jobs")
