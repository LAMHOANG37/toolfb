from sqlalchemy import Column, Integer, String, DateTime, Text
from app.database import Base
from app.timeutils import utcnow


class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    active_key = Column(String, unique=True, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    detail = Column(Text, nullable=True)


class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


def log_activity(db, message):
    db.add(Activity(message=message))
