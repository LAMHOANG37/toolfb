from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.config import settings


def utcnow():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def localtime(value):
    return aware(value).astimezone(ZoneInfo(settings.timezone)).strftime("%d/%m/%Y %H:%M") if value else "—"
