import json
import httpx
import pytest
from pydantic import SecretStr
from app.config import settings
from app.services.llm import generate, GeneratedDraft
from app.services.operations import enqueue, run_operation
from app.models import Draft, Operation
from app.models.draft import DraftStatus


PAYLOAD = dict(headline="Tiêu đề AI", hook="Mở bài", summary="Tóm tắt có nguồn",
    why_it_matters="Lý do", practical_impact="Ứng dụng", facebook_text="Nội dung tiếng Việt",
    verification_notes="Cần đối chiếu thông báo gốc.", importance_score=70, relevance_score=80, confidence_score=60)


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_provider_contract(seed, monkeypatch, provider):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-key"))
    def send(request):
        body = json.loads(request.read())
        if provider == "openai":
            assert body["text"]["format"]["strict"] is True
            assert body["store"] is False
            return httpx.Response(200, json={"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(PAYLOAD)}]}]})
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(PAYLOAD)}]}}]})
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        assert generate([seed[2]], client).headline == PAYLOAD["headline"]


def test_missing_config_is_clear(seed, monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "")
    with pytest.raises(ValueError, match="LLM_MODEL"):
        generate([seed[2]])


def test_ai_operation_creates_reviewable_draft(db, seed, monkeypatch):
    monkeypatch.setattr("app.services.llm.generate", lambda articles: GeneratedDraft(**PAYLOAD))
    op = enqueue(db, f"generate:{seed[1].id}", f"generate:{seed[1].id}")
    run_operation(op.id)
    db.expire_all()
    draft = db.query(Draft).one()
    assert draft.status == DraftStatus.NEEDS_REVIEW
    assert "https://example.com/ai" in draft.facebook_text
    assert draft.verification_notes
    assert db.get(Operation, op.id).status == "completed"
    assert not db.get(Operation, op.id).active_key


def test_operation_failure_releases_lock(db, seed, monkeypatch):
    def fail(articles):
        raise ValueError("Missing configuration")
    monkeypatch.setattr("app.services.llm.generate", fail)
    op = enqueue(db, f"generate:{seed[1].id}", f"generate:{seed[1].id}")
    with pytest.raises(ValueError):
        enqueue(db, f"generate:{seed[1].id}", f"generate:{seed[1].id}")
    run_operation(op.id)
    db.expire_all()
    assert db.get(Operation, op.id).status == "failed"
    assert not db.get(Operation, op.id).active_key
