import logging
from abc import ABC, abstractmethod
from typing import List, Protocol
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.article import Article
from app.models.story_cluster import StoryCluster
from app.models.source import Source, SourceType
from app.services.normalization import normalize_title

logger = logging.getLogger(__name__)

class SemanticSimilarityProvider(Protocol):
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Returns a similarity score between 0.0 and 1.0.
        """
        ...

class DeterministicSimilarityProvider:
    """
    A lightweight matching provider using word-level Jaccard index
    on normalized titles, with penalties for version/model mismatches.
    """
    def calculate_similarity(self, text1: str, text2: str) -> float:
        t1 = normalize_title(text1)
        t2 = normalize_title(text2)
        
        if not t1 or not t2:
            return 0.0
            
        set1 = set(t1.split())
        set2 = set(t2.split())
        
        if not set1 or not set2:
            return 0.0
            
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        
        score = len(intersection) / len(union)
        
        # Penalize if one has a version-like word (digit or specific keyword) missing in the other
        version_keywords = {'mini', 'pro', 'ultra', 'plus', 'max', 'opus', 'sonnet', 'haiku'}
        
        def get_versions(word_set):
            return {w for w in word_set if any(c.isdigit() for c in w) or w in version_keywords}
            
        v1 = get_versions(set1)
        v2 = get_versions(set2)
        
        # If there are versions present but they don't match exactly, heavily penalize
        if v1 != v2:
            score *= 0.3
            
        return score

class ClusteringService:
    def __init__(self, db: Session, similarity_provider: SemanticSimilarityProvider = None):
        self.db = db
        self.similarity_provider = similarity_provider or DeterministicSimilarityProvider()
        # threshold
        self.similarity_threshold = 0.45  

    def get_source_score(self, article: Article) -> int:
        """
        Calculates a score for how 'good' a source is, to decide the primary article.
        Higher is better.
        """
        score = 0
        if not article.source:
            return score
            
        # Official sources get a huge bump
        if article.source.source_type == SourceType.OFFICIAL:
            score += 1000
            
        # Priority mapping
        score += (article.source.priority or 0) * 10
        
        # Earliest time is better. We subtract hours since 2024 to make it positive
        if article.published_at:
            delta = article.published_at - datetime(2024, 1, 1, tzinfo=timezone.utc)
            # Actually, oldest (first to publish) is best for credibility, 
            # wait, maybe we want the most recent? The prompt: "then earliest credible article".
            # So negative timestamp is better (smaller timestamp = higher score relative to others).
            # But let's just use a simple approach: if two have same priority, pick earliest.
            pass
            
        return score

    def evaluate_primary_article(self, cluster: StoryCluster):
        """
        Re-evaluates and sets the primary_article_id for a cluster
        based on all articles currently in it.
        """
        articles = self.db.query(Article).filter(Article.story_cluster_id == cluster.id).all()
        if not articles:
            return
            
        # Sort by: Official type -> Source priority -> published_at (earliest)
        def sort_key(a: Article):
            is_official = 0
            if a.source and a.source.source_type == SourceType.OFFICIAL:
                is_official = 1
                
            priority = a.source.priority if a.source and a.source.priority else 0
            
            # For published_at, we want earliest, so smaller timestamp is better.
            # In Python sorting, tuples sort element by element.
            # We negate the first two so larger values come first.
            ts = a.published_at.timestamp() if a.published_at else float('inf')
            
            return (-is_official, -priority, ts)
            
        sorted_articles = sorted(articles, key=sort_key)
        best_article = sorted_articles[0]
        
        cluster.primary_article_id = best_article.id
        cluster.canonical_title = best_article.title
        cluster.summary = best_article.cleaned_text[:500] if best_article.cleaned_text else None

    def cluster_articles(self, new_article_ids: List[int]) -> int:
        """
        Takes a list of new Article IDs and assigns them to StoryClusters.
        Returns the number of new clusters created.
        """
        new_clusters_count = 0
        clusters_updated = set()
        
        articles = self.db.query(Article).filter(Article.id.in_(new_article_ids)).all()
        
        # We only consider recent clusters to match against to avoid unbounded growth
        # e.g., clusters created in the last 7 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_clusters = self.db.query(StoryCluster).filter(StoryCluster.created_at >= cutoff).all()
        
        for article in articles:
            if article.story_cluster_id is not None:
                continue # Already clustered
                
            best_match_cluster = None
            best_score = 0.0
            
            for cluster in recent_clusters:
                # Compare article title with cluster's canonical title
                score = self.similarity_provider.calculate_similarity(article.title, cluster.canonical_title)
                
                if score >= self.similarity_threshold and score > best_score:
                    best_score = score
                    best_match_cluster = cluster
                    
            if best_match_cluster:
                # Add to existing cluster
                article.story_cluster_id = best_match_cluster.id
                clusters_updated.add(best_match_cluster)
            else:
                # Create new cluster
                new_cluster = StoryCluster(
                    canonical_title=article.title,
                    summary=article.cleaned_text[:500] if article.cleaned_text else None,
                    primary_article_id=article.id
                )
                self.db.add(new_cluster)
                self.db.commit() # Commit to get ID
                
                article.story_cluster_id = new_cluster.id
                self.db.commit()
                
                recent_clusters.append(new_cluster)
                new_clusters_count += 1
                
        # Re-evaluate primary article for any clusters that received new articles
        for cluster in clusters_updated:
            self.evaluate_primary_article(cluster)
            
        self.db.commit()
                
        return new_clusters_count
