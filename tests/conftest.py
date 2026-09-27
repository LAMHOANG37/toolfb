import os
os.environ["SECRET_KEY"] = "test-only-session-secret-not-for-production-123456"
os.environ["ADMIN_PASSWORD"] = "test-only-password-123"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["AUTO_PUBLISH"] = "false"

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import Base, get_db
from app.config import settings
from app.models import Source, Article, StoryCluster, Draft
from app.models.source import SourceType
from app.models.draft import DraftStatus
from app.timeutils import utcnow


def csrf(response):
    node = BeautifulSoup(response.text, "html.parser").select_one('input[name="csrf_token"]')
    assert node is not None, response.text
    return node["value"]


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "test.db"), connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr("app.main.SessionLocal", factory)
    monkeypatch.setattr("app.services.operations.SessionLocal", factory)
    monkeypatch.setattr("app.api.routes_editor.SessionLocal", factory)
    import app.services.cards as cards
    monkeypatch.setattr(cards, "CARD_DIR", tmp_path / "cards")
    from app.security import _attempts
    _attempts.clear()
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def db(factory):
    with factory() as session:
        yield session


@pytest.fixture
def client(factory):
    with TestClient(app) as client:
        login = client.get("/login")
        response = client.post("/login", data={"username": settings.admin_username,
            "password": settings.admin_password.get_secret_value(), "csrf_token": csrf(login)})
        assert response.status_code == 200
        client.csrf = csrf(response)
        yield client


@pytest.fixture
def seed(db):
    source = Source(name="Test official", base_url="https://example.com", feed_url="https://example.com/rss",
        source_type=SourceType.OFFICIAL, strategy="rss", priority=10)
    cluster = StoryCluster(canonical_title="Một sự kiện AI")
    db.add_all([source, cluster])
    db.flush()
    article = Article(source_id=source.id, story_cluster_id=cluster.id, title="Một sự kiện AI",
        original_url="https://example.com/ai", canonical_url="https://example.com/ai",
        cleaned_text="Một thông báo AI với dữ kiện nguồn đủ dài để biên tập.", published_at=utcnow())
    db.add(article)
    db.flush()
    cluster.primary_article_id = article.id
    db.commit()
    return source, cluster, article


@pytest.fixture
def draft(db, seed):
    source, cluster, article = seed
    draft = Draft(story_cluster_id=cluster.id, headline="AI mới: điều cần biết",
        facebook_text="Nội dung đã đối chiếu nguồn.", verification_notes="Đã xem thông báo chính thức.",
        source_label=source.name, source_urls='["https://example.com/ai"]', status=DraftStatus.NEEDS_REVIEW)
    db.add(draft)
    db.commit()
    return draft
