import yaml
from sqlalchemy.orm import Session
from app.models.source import Source, SourceType

class SourceRegistry:
    def __init__(self, config_path: str = "sources.yaml"):
        self.config_path = config_path

    def load_sources_from_yaml(self) -> list[dict]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("sources", [])
        except FileNotFoundError:
            return []

    def sync_with_db(self, db: Session):
        yaml_sources = self.load_sources_from_yaml()
        
        for s in yaml_sources:
            # Check if source exists
            db_source = db.query(Source).filter(Source.name == s["name"]).first()
            if not db_source:
                db_source = Source(
                    name=s["name"],
                    base_url=s["base_url"],
                    feed_url=s.get("feed_url"),
                    source_type=SourceType(s.get("type", "community")),
                    priority=s.get("priority", 5),
                    active=True
                )
                db.add(db_source)
            else:
                db_source.base_url = s["base_url"]
                db_source.feed_url = s.get("feed_url")
                db_source.source_type = SourceType(s.get("type", "community"))
                db_source.priority = s.get("priority", 5)
        
        db.commit()

    def get_active_sources(self, db: Session) -> list[Source]:
        return db.query(Source).filter(Source.active == True).all()
