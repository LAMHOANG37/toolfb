from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
import enum

from app.database import Base

class SourceType(str, enum.Enum):
    OFFICIAL = "official"
    PUBLICATION = "publication"
    COMMUNITY = "community"

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    base_url = Column(String, nullable=False)
    feed_url = Column(String, nullable=True)
    source_type = Column(Enum(SourceType), nullable=False)
    priority = Column(Integer, default=5)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    last_error_message = Column(String, nullable=True)
