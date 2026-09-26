from datetime import datetime, timezone
import pytest

from app.services.normalization import normalize_title
from app.services.clustering import DeterministicSimilarityProvider, ClusteringService
from app.models.source import Source, SourceType
from app.models.article import Article
from app.models.story_cluster import StoryCluster

def test_normalize_title():
    # Should lowercase and remove suffix
    assert normalize_title("OpenAI launches GPT-4 - TechCrunch") == "openai launches gpt-4"
    assert normalize_title("OpenAI launches GPT-4 | Wired") == "openai launches gpt-4"
    
    # Should strip punctuation but preserve internal dots/hyphens for versions
    assert normalize_title("OpenAI launches GPT-4.5!") == "openai launches gpt-4.5"
    assert normalize_title("Llama-3 is here, says Meta.") == "llama-3 is here says meta"
    
    # Distinct entities should remain distinct
    assert normalize_title("GPT-7") != normalize_title("GPT-7 Mini")
    
def test_similarity_provider():
    provider = DeterministicSimilarityProvider()
    
    # Same
    t1 = "OpenAI launches GPT-4"
    t2 = "OpenAI launches GPT-4!"
    assert provider.calculate_similarity(t1, t2) == 1.0
    
    # Very similar (Jaccard on words)
    t3 = "OpenAI launches new GPT-4 model"
    # t1 words: openai, launches, gpt-4
    # t3 words: openai, launches, new, gpt-4, model
    # intersection: 3, union: 5 -> 0.6
    score = provider.calculate_similarity(t1, t3)
    assert score == 0.6
    
    # Distinct
    t4 = "Anthropic announces Claude-3"
    assert provider.calculate_similarity(t1, t4) == 0.0
    
    # Version differences
    v1 = "OpenAI launches GPT-4"
    v2 = "OpenAI launches GPT-4.5"
    # intersection: openai, launches (2)
    # union: openai, launches, gpt-4, gpt-4.5 (4)
    # score: 0.5 (below 0.65 threshold)
    assert provider.calculate_similarity(v1, v2) < 0.65

def test_evaluate_primary_article():
    from tests.test_main import TestingSessionLocal
    db_session = TestingSessionLocal()
    cs = ClusteringService(db_session)
    
    # clear old data
    db_session.query(Article).delete()
    db_session.query(StoryCluster).delete()
    db_session.query(Source).delete()
    db_session.commit()
    
    s_official = Source(name="Official", base_url="a", source_type=SourceType.OFFICIAL, priority=1)
    s_high_prio = Source(name="High Prio", base_url="b", source_type=SourceType.PUBLICATION, priority=10)
    s_low_prio = Source(name="Low Prio", base_url="c", source_type=SourceType.COMMUNITY, priority=1)
    
    db_session.add_all([s_official, s_high_prio, s_low_prio])
    db_session.commit()
    
    cluster = StoryCluster(canonical_title="Test Cluster")
    db_session.add(cluster)
    db_session.commit()
    
    a1 = Article(title="Low", canonical_url="1", original_url="1", source_id=s_low_prio.id, story_cluster_id=cluster.id, published_at=datetime(2026,1,1, tzinfo=timezone.utc))
    a2 = Article(title="High", canonical_url="2", original_url="2", source_id=s_high_prio.id, story_cluster_id=cluster.id, published_at=datetime(2026,1,2, tzinfo=timezone.utc))
    a3 = Article(title="Official", canonical_url="3", original_url="3", source_id=s_official.id, story_cluster_id=cluster.id, published_at=datetime(2026,1,3, tzinfo=timezone.utc))
    
    db_session.add_all([a1, a2, a3])
    db_session.commit()
    
    # Should pick Official despite being published last
    cs.evaluate_primary_article(cluster)
    assert cluster.primary_article_id == a3.id
    
    # If we remove official, should pick high prio
    a3.story_cluster_id = None
    db_session.commit()
    cs.evaluate_primary_article(cluster)
    assert cluster.primary_article_id == a2.id
