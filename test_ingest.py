from sqlalchemy.orm import sessionmaker
from app.database import engine
from app.services.ingestion import IngestionService

SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()
service = IngestionService(db)
service.registry.sync_with_db(db)
# Limit lookback to 1 hour to make it fast
stats = service.run(lookback_hours=1)

errors_html = f"<li>Lỗi: <strong>{stats['errors']}</strong></li>" if stats['errors'] > 0 else ""
error_header = f" và {stats['errors']} lỗi" if stats['errors'] > 0 else ""

html = f"""
<div class="alert" style="background-color: var(--color-surface); padding: 1.5rem; border-radius: var(--radius); border: 1px solid var(--color-success); box-shadow: var(--shadow); margin-bottom: 2rem;">
    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
        <span style="font-size: 1.5rem; color: var(--color-success);">✓</span>
        <strong style="font-size: 1.1rem; color: var(--color-primary-dark);">Quét tin hoàn tất</strong>
    </div>
    <p style="margin: 0 0 0 2.25rem; color: var(--color-muted);">
        Đã quét {stats['sources_scanned']} nguồn. Có {stats['articles_fetched']} bài được đọc.
        Tìm thấy {stats['new_articles']} tin mới{error_header}.
    </p>
</div>
"""
print(repr(html))
