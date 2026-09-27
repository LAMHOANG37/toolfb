from typing import Protocol
from datetime import timedelta
from app.models.article import Article, ArticleStatus
from app.models.story_cluster import StoryCluster
from app.models.source import SourceType
from app.services.normalization import normalize_title
from app.timeutils import utcnow, aware


class SemanticSimilarityProvider(Protocol):
    def calculate_similarity(self, text1: str, text2: str) -> float: ...


class DeterministicSimilarityProvider:
    def calculate_similarity(self, text1, text2):
        a, b = set(normalize_title(text1).split()), set(normalize_title(text2).split())
        if not a or not b:
            return 0.0
        score = len(a & b) / len(a | b)
        versions = {"mini", "pro", "ultra", "plus", "max", "opus", "sonnet", "haiku"}
        av = {w for w in a if any(c.isdigit() for c in w) or w in versions}
        bv = {w for w in b if any(c.isdigit() for c in w) or w in versions}
        return score * (0.3 if av != bv else 1)


class ClusteringService:
    def __init__(self, db, similarity_provider=None):
        self.db = db
        self.similarity_provider = similarity_provider or DeterministicSimilarityProvider()
        self.similarity_threshold = 0.45

    def evaluate_primary_article(self, cluster):
        self.db.flush()
        articles = self.db.query(Article).filter_by(story_cluster_id=cluster.id).all()
        if not articles:
            cluster.primary_article_id = None
            cluster.summary = None
            return
        def key(article):
            source = article.source
            return (-(source.source_type == SourceType.OFFICIAL), -(source.priority or 0),
                    aware(article.published_at).timestamp() if article.published_at else float("inf"), article.id)
        best = min(articles, key=key)
        cluster.primary_article_id = best.id
        cluster.canonical_title = best.title
        cluster.summary = (best.cleaned_text or "")[:500]

    def cluster_articles(self, new_article_ids):
        articles = self.db.query(Article).filter(Article.id.in_(new_article_ids), Article.story_cluster_id.is_(None)).order_by(Article.id).all()
        clusters = self.db.query(StoryCluster).filter(StoryCluster.created_at >= utcnow() - timedelta(days=7)).all()
        created = 0
        for article in articles:
            ranked = [(self.similarity_provider.calculate_similarity(article.title, c.canonical_title), c) for c in clusters]
            score, match = max(ranked, key=lambda pair: pair[0], default=(0, None))
            if score < self.similarity_threshold or match is None:
                match = StoryCluster(canonical_title=article.title)
                self.db.add(match)
                self.db.flush()
                clusters.append(match)
                created += 1
            article.story_cluster_id = match.id
            article.status = ArticleStatus.NORMALIZED
            self.evaluate_primary_article(match)
        self.db.commit()
        return created
