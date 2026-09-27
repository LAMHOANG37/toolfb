from app.services.normalization import normalize_title
from app.services.clustering import DeterministicSimilarityProvider, ClusteringService
from app.models import Source, Article, StoryCluster
from app.models.source import SourceType
from app.timeutils import utcnow


def test_title_and_versions():
    assert normalize_title("OpenAI launches GPT-4 | Wired") == "openai launches gpt-4"
    assert normalize_title("OpenAI launches GPT-4.5!") == "openai launches gpt-4.5"
    provider = DeterministicSimilarityProvider()
    assert provider.calculate_similarity("OpenAI launches GPT-4", "OpenAI launches new GPT-4 model") == 0.6
    assert provider.calculate_similarity("OpenAI launches GPT-4", "OpenAI launches GPT-4.5") < 0.45


def test_new_high_priority_article_becomes_primary(db, seed):
    source, cluster, first = seed
    source.source_type = SourceType.PUBLICATION
    second_source = Source(name="Better", base_url="https://better.example", source_type=SourceType.OFFICIAL, priority=1)
    db.add(second_source)
    db.flush()
    second = Article(source_id=second_source.id, title=first.title, original_url="https://better.example/ai",
        canonical_url="https://better.example/ai", cleaned_text="Better", published_at=utcnow())
    db.add(second)
    db.commit()
    assert ClusteringService(db).cluster_articles([second.id]) == 0
    db.refresh(cluster)
    assert cluster.primary_article_id == second.id


def test_merge_preserves_articles(client, db, seed):
    _, first, article = seed
    target = StoryCluster(canonical_title="Target")
    db.add(target)
    db.commit()
    first_id = first.id
    response = client.post("/api/clusters/merge", data={"csrf_token": client.csrf, "source_id": first.id, "target_id": target.id})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(StoryCluster, first_id) is None
    assert db.get(Article, article.id).story_cluster_id == target.id
    assert db.get(StoryCluster, target.id).primary_article_id == article.id


def test_merge_self_rejected(client, seed):
    cluster = seed[1]
    assert client.post("/api/clusters/merge", data={"csrf_token": client.csrf, "source_id": cluster.id, "target_id": cluster.id}).status_code == 400


def test_move_last_article_clears_old_group(client, db, seed):
    _, old, article = seed
    target = StoryCluster(canonical_title="Target")
    db.add(target)
    db.commit()
    old_id = old.id
    response = client.post(f"/api/clusters/{old.id}/move_article",
        data={"csrf_token": client.csrf, "article_id": article.id, "new_cluster_id": target.id})
    assert response.status_code == 200
    db.expire_all()
    assert db.get(StoryCluster, old_id) is None
    assert db.get(Article, article.id).story_cluster_id == target.id


def test_group_with_draft_is_protected(client, db, draft):
    target = StoryCluster(canonical_title="Target")
    db.add(target)
    db.commit()
    response = client.post("/api/clusters/merge", data={"csrf_token": client.csrf,
        "source_id": draft.story_cluster_id, "target_id": target.id})
    assert response.status_code == 400
