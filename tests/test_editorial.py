from datetime import timedelta
from app.models import Draft, PublishJob, Post
from app.models.draft import DraftStatus
from app.models.publish_job import JobStatus
from app.timeutils import utcnow


def submit(client, url, **data):
    return client.post(url, data={"csrf_token": client.csrf, **data})


def test_manual_draft_workflow(client, seed, db):
    cluster = seed[1]
    response = submit(client, f"/events/{cluster.id}/manual")
    assert response.status_code == 200
    draft = db.query(Draft).one()
    assert draft.status == DraftStatus.NEEDS_REVIEW
    response = submit(client, f"/drafts/{draft.id}/save", revision=draft.revision,
        headline="Tiêu đề tiếng Việt", facebook_text="Bài viết từ nguồn đã kiểm tra.", verification_notes="Đã kiểm tra nguồn gốc.")
    assert response.status_code == 200
    db.refresh(draft)
    response = submit(client, f"/drafts/{draft.id}/card", revision=draft.revision)
    assert response.status_code == 200
    db.refresh(draft)
    assert draft.social_card_path
    assert client.get("/cards/" + draft.social_card_path).headers["content-type"] == "image/png"
    response = submit(client, f"/drafts/{draft.id}/approve", revision=draft.revision, verified="yes")
    assert response.status_code == 200
    db.refresh(draft)
    assert draft.status == DraftStatus.APPROVED
    response = submit(client, f"/drafts/{draft.id}/schedule", revision=draft.revision,
        scheduled_at=utcnow().isoformat())
    assert response.status_code == 200
    job = db.query(PublishJob).one()
    response = submit(client, f"/schedule/{job.id}/run")
    assert response.status_code == 200
    db.refresh(job)
    db.refresh(draft)
    assert job.status == JobStatus.SIMULATED
    assert draft.status == DraftStatus.APPROVED
    assert db.query(Post).count() == 0


def test_stale_editor_cannot_overwrite(client, db, draft):
    first = submit(client, f"/drafts/{draft.id}/save", revision=1, headline="First", facebook_text="First text")
    second = submit(client, f"/drafts/{draft.id}/save", revision=1, headline="Stale", facebook_text="Stale text")
    assert first.status_code == 200
    assert second.status_code == 400
    db.refresh(draft)
    assert draft.headline == "First"


def test_approve_requires_evidence_and_checkbox(client, db, draft):
    assert submit(client, f"/drafts/{draft.id}/approve", revision=1).status_code == 400
    draft.verification_notes = ""
    db.commit()
    assert submit(client, f"/drafts/{draft.id}/approve", revision=1, verified="yes").status_code == 400


def test_edit_invalidates_approval_and_card(client, db, draft):
    draft.status = DraftStatus.APPROVED
    draft.social_card_path = "old.png"
    draft.approved_at = utcnow()
    db.commit()
    assert submit(client, f"/drafts/{draft.id}/save", revision=1, headline="Updated", facebook_text="Updated").status_code == 200
    db.refresh(draft)
    assert draft.status == DraftStatus.NEEDS_REVIEW and draft.social_card_path is None and draft.approved_at is None


def test_scheduled_draft_locked_and_cancel_reopens(client, db, draft):
    from app.services.publishing import schedule
    draft.status = DraftStatus.APPROVED
    db.commit()
    job = schedule(db, draft, utcnow() + timedelta(hours=1), draft.revision)
    db.refresh(draft)
    assert submit(client, f"/drafts/{draft.id}/save", revision=draft.revision, headline="Bad", facebook_text="Changed").status_code == 400
    assert submit(client, f"/schedule/{job.id}/cancel").status_code == 200
    db.refresh(draft)
    assert draft.status == DraftStatus.APPROVED


def test_cannot_schedule_unapproved(client, draft):
    assert submit(client, f"/drafts/{draft.id}/schedule", revision=draft.revision,
        scheduled_at=utcnow().isoformat()).status_code == 400


def test_source_save_and_disabled_persistence(client, db):
    from app.models import Source
    response = submit(client, "/sources/save", name="My source", base_url="https://example.com",
        feed_url="https://example.com/rss", strategy="rss", source_type="official", priority=9)
    assert response.status_code == 200
    source = db.query(Source).filter_by(name="My source").one()
    assert not source.active
    assert source.source_type.value == "official"


def test_source_local_urls_rejected(client):
    response = submit(client, "/sources/save", name="Bad", base_url="http://127.0.0.1",
        strategy="webpage", source_type="community", priority=1)
    assert response.status_code == 400
