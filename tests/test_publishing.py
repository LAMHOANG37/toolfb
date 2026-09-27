from datetime import timedelta
import httpx
import pytest
from pydantic import SecretStr
from app.config import settings
from app.models import Draft, Post, PublishJob
from app.models.draft import DraftStatus
from app.models.publish_job import JobStatus
from app.services.publishing import schedule, dispatch, reconcile
from app.timeutils import utcnow


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "facebook_dry_run", False)
    monkeypatch.setattr(settings, "facebook_page_id", "123")
    monkeypatch.setattr(settings, "facebook_graph_api_version", "v25.0")
    monkeypatch.setattr(settings, "facebook_page_access_token", SecretStr("unit-test-token"))


def approved(db, draft):
    draft.status = DraftStatus.APPROVED
    db.commit()
    return schedule(db, draft, utcnow(), draft.revision)


def test_dry_run_never_calls_facebook(db, draft):
    job = approved(db, draft)
    def forbidden(request):
        pytest.fail("Dry run must not call any external service")
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        assert dispatch(db, job.id, client)
    assert job.status == JobStatus.SIMULATED
    assert db.query(Post).count() == 0


def test_success_and_double_dispatch(db, draft, live):
    job = approved(db, draft)
    calls = []
    def send(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer unit-test-token"
        assert request.url.path.endswith("/123/feed")
        return httpx.Response(200, json={"id": "123_456"})
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        assert dispatch(db, job.id, client)
        assert not dispatch(db, job.id, client)
    assert len(calls) == 1
    assert db.query(Post).count() == 1
    assert draft.status == DraftStatus.PUBLISHED


@pytest.mark.parametrize("outcome", ["timeout", "server_error", "malformed"])
def test_uncertain_never_retried_automatically(db, draft, live, outcome):
    job = approved(db, draft)
    calls = []
    def send(request):
        calls.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout("unknown outcome", request=request)
        return httpx.Response(503 if outcome == "server_error" else 200, json={})
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        assert not dispatch(db, job.id, client)
        assert not dispatch(db, job.id, client)
    assert job.status == JobStatus.UNCERTAIN
    assert job.active_key and job.active_content
    assert len(calls) == 1


def test_explicit_rejection_is_failed(db, draft, live):
    job = approved(db, draft)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": {"message": "private token details"}}))) as client:
        assert not dispatch(db, job.id, client)
    assert job.status == JobStatus.FAILED
    assert "private token details" not in job.last_error


def test_duplicate_live_content_is_reserved(db, draft, live):
    approved(db, draft)
    duplicate = Draft(story_cluster_id=draft.story_cluster_id, facebook_text=draft.facebook_text,
        status=DraftStatus.APPROVED)
    db.add(duplicate)
    db.commit()
    with pytest.raises(ValueError, match="đã có lịch"):
        schedule(db, duplicate, utcnow(), duplicate.revision)
    assert db.query(PublishJob).count() == 1


def test_same_draft_cannot_schedule_twice(db, draft):
    approved(db, draft)
    with pytest.raises(ValueError):
        schedule(db, draft, utcnow(), draft.revision)
    assert db.query(PublishJob).count() == 1


def test_future_job_not_dispatched(db, draft):
    draft.status = DraftStatus.APPROVED
    db.commit()
    job = schedule(db, draft, utcnow() + timedelta(hours=1), draft.revision)
    assert not dispatch(db, job.id)
    assert job.status == JobStatus.PENDING


def test_mode_change_never_escalates_dry_run(db, draft, live, monkeypatch):
    monkeypatch.setattr(settings, "facebook_dry_run", True)
    job = approved(db, draft)
    monkeypatch.setattr(settings, "facebook_dry_run", False)
    assert dispatch(db, job.id)
    assert job.status == JobStatus.SIMULATED
    assert db.query(Post).count() == 0


def test_reconcile_checks_page_and_exact_message(db, draft, live):
    job = approved(db, draft)
    job.status = JobStatus.UNCERTAIN
    db.commit()
    with pytest.raises(ValueError):
        reconcile(db, job, "999_456")
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"id": "123_456", "message": "wrong"}))) as client:
        with pytest.raises(ValueError):
            reconcile(db, job, "123_456", client)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"id": "123_456", "message": job.payload_text}))) as client:
        reconcile(db, job, "123_456", client)
    assert job.status == JobStatus.SUCCESSFUL
    assert db.query(Post).count() == 1


def test_image_payload_and_snapshot_tamper(db, draft, live):
    from app.services.cards import create_card, card_file
    draft.social_card_path = create_card(draft)
    job = approved(db, draft)
    card_file(job.card_path).write_bytes(b"tampered")
    assert not dispatch(db, job.id)
    assert job.status == JobStatus.FAILED
    assert "đã thay đổi" in job.last_error


def test_photo_publication_uses_post_id(db, draft, live):
    from app.services.cards import create_card
    draft.social_card_path = create_card(draft)
    job = approved(db, draft)
    def send(request):
        assert request.url.path.endswith("/photos")
        assert b'image/png' in request.read()
        return httpx.Response(200, json={"id": "photo-id", "post_id": "123_456"})
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        assert dispatch(db, job.id, client)
    assert db.query(Post).one().facebook_post_id == "123_456"
