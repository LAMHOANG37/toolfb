import pytest
from fastapi.testclient import TestClient
from app.main import app
from tests.conftest import csrf


def test_auth_required(factory):
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/news", follow_redirects=False).status_code == 303
        assert client.post("/api/ingest", follow_redirects=False).status_code == 303
        assert client.get("/openapi.json", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("url", ["/", "/news", "/events", "/drafts", "/schedule", "/sources", "/settings"])
def test_pages(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert 'name="csrf_token"' in response.text


def test_csrf_enforced(client):
    assert client.post("/sources/import").status_code == 403


def test_login_throttle(factory):
    with TestClient(app) as client:
        token = csrf(client.get("/login"))
        for _ in range(5):
            assert client.post("/login", data={"username": "admin", "password": "wrong", "csrf_token": token}).status_code == 401
        assert client.post("/login", data={"username": "admin", "password": "wrong", "csrf_token": token}).status_code == 429


def test_logout(client):
    client.post("/logout", data={"csrf_token": client.csrf})
    assert client.get("/news", follow_redirects=False).status_code == 303


def test_article_and_event_pages(client, seed):
    _, cluster, article = seed
    assert client.get(f"/news/{article.id}").status_code == 200
    response = client.get(f"/events/{cluster.id}")
    assert response.status_code == 200
    assert article.canonical_url in response.text
    assert "Chưa có nguồn chính" not in response.text


def test_errors_and_pagination(client):
    assert client.get("/news/99999").status_code == 404
    assert client.get("/news?page=0").status_code == 422
    assert client.get("/news?status=invalid").status_code == 400
    assert client.get("/news?q=missing&page=1").status_code == 200


def test_xss_escaped(client, seed, db):
    seed[2].title = '<script>alert("x")</script>'
    db.commit()
    response = client.get("/news")
    assert '<script>alert("x")</script>' not in response.text
    assert "&lt;script&gt;" in response.text
