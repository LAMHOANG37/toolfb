import os
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.source import Source, SourceType
from app.models.article import Article, ArticleStatus
from app.models.story_cluster import StoryCluster
from app.services.clustering import ClusteringService

def run():
    db = SessionLocal()
    
    # Clear existing data
    db.query(Article).delete()
    db.query(StoryCluster).delete()
    db.query(Source).delete()
    db.commit()
    
    # Create sources
    s1 = Source(name="OpenAI Official", base_url="openai.com", source_type=SourceType.OFFICIAL, priority=1, active=True)
    s2 = Source(name="TechCrunch", base_url="techcrunch.com", source_type=SourceType.PUBLICATION, priority=10, active=True)
    s3 = Source(name="The Verge", base_url="theverge.com", source_type=SourceType.PUBLICATION, priority=10, active=True)
    
    # Try to add, or just use existing
    for s in [s1, s2, s3]:
        existing = db.query(Source).filter_by(name=s.name).first()
        if not existing:
            db.add(s)
            
    db.commit()
    
    # Refetch
    s1 = db.query(Source).filter_by(name="OpenAI Official").first()
    s2 = db.query(Source).filter_by(name="TechCrunch").first()
    s3 = db.query(Source).filter_by(name="The Verge").first()
    
    articles_data = [
        # Story 1: GPT-5 Launch
        ("OpenAI launches Model X", s1, "http://a.com/1"),
        ("OpenAI unveils new Model X", s2, "http://b.com/1"),
        ("OpenAI releases Model X", s3, "http://c.com/1"),
        
        # Story 2: Llama-4 announced
        ("Meta announces Llama-4 open source model", s2, "http://b.com/2"),
        ("Meta introduces Llama-4", s3, "http://c.com/2"),
        ("Llama-4 is here, says Meta", s1, "http://a.com/2"), # Pretend OpenAI reported it for variety
        
        # Story 3: Anthropic Claude 4
        ("Anthropic releases Claude 4 Opus", s2, "http://b.com/3"),
        ("Claude 4 Opus released by Anthropic", s3, "http://c.com/3"),
        ("Anthropic launches Claude 4", s1, "http://a.com/3"),
        
        # Story 4: Midjourney v7
        ("Midjourney v7 brings photo realism", s2, "http://b.com/4"),
        ("Midjourney v7 is incredibly realistic", s3, "http://c.com/4"),
        ("New Midjourney v7 model released", s1, "http://a.com/4"),
        
        # Story 5: Apple Intelligence
        ("Apple Intelligence launches in iOS 18", s2, "http://b.com/5"),
        ("Apple Intelligence debuts today", s3, "http://c.com/5"),
        ("Apple rolls out Apple Intelligence features", s1, "http://a.com/5")
    ]
    
    # Insert articles
    new_ids = []
    for title, source, url in articles_data:
        # Avoid dupes if run multiple times
        if not db.query(Article).filter_by(canonical_url=url).first():
            a = Article(
                title=title,
                source_id=source.id,
                canonical_url=url,
                original_url=url,
                status=ArticleStatus.DISCOVERED,
                published_at=datetime.now(timezone.utc)
            )
            db.add(a)
            db.flush()
            new_ids.append(a.id)
            
    db.commit()
    
    if new_ids:
        print(f"Inserted {len(new_ids)} new articles. Running clustering...")
        cs = ClusteringService(db)
        clusters_created = cs.cluster_articles(new_ids)
        print(f"Clustering complete. Created {clusters_created} clusters.")
    else:
        print("No new articles to insert.")
        
if __name__ == "__main__":
    run()
