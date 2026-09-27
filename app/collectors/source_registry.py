import yaml
from app.config import ROOT
from app.models.source import Source, SourceType
from app.services.fetching import validate_url


class SourceRegistry:
    def __init__(self, config_path=None):
        self.config_path = config_path or ROOT / "sources.yaml"

    def load_sources_from_yaml(self):
        with open(self.config_path, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data.get("sources", [])

    def sync_with_db(self, db):
        for item in self.load_sources_from_yaml():
            validate_url(item["base_url"])
            strategy = item.get("strategy", "rss")
            if strategy not in {"rss", "webpage"}:
                raise ValueError("Chiến lược nguồn không hợp lệ.")
            if strategy == "rss":
                validate_url(item.get("feed_url", ""))
            source = db.query(Source).filter_by(name=item["name"]).first()
            if source is None:
                source = Source(name=item["name"])
                db.add(source)
            source.base_url = item["base_url"]
            source.feed_url = item.get("feed_url") or None
            source.source_type = SourceType(item.get("type", "community"))
            source.priority = int(item.get("priority", 5))
            source.active = bool(item.get("active", True))
            source.strategy = strategy
        db.commit()

    def get_active_sources(self, db):
        return db.query(Source).filter(Source.active.is_(True)).order_by(Source.priority.desc(), Source.id).all()
