"""Add clearly labelled demo articles. Never delete existing content."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import SessionLocal
from app.models import Source, Article
from app.models.source import SourceType
from app.services.clustering import ClusteringService
from app.timeutils import utcnow


def run():
    with SessionLocal() as db:
        source = db.query(Source).filter_by(name="DEMO · Nguồn minh họa").first()
        if not source:
            source = Source(name="DEMO · Nguồn minh họa", base_url="https://example.com",
                source_type=SourceType.COMMUNITY, active=False, strategy="webpage")
            db.add(source)
            db.flush()
        titles = [
            "[DEMO] Trợ lý AI hỗ trợ tổng hợp tài liệu cho nhóm làm việc",
            "[DEMO] Bộ công cụ mã nguồn mở giúp đánh giá câu trả lời AI",
            "[DEMO] Nghiên cứu cách đối chiếu nguồn khi biên tập tin công nghệ",
        ]
        ids = []
        for index, title in enumerate(titles):
            url = f"https://example.com/newsroom-demo/{index}"
            if db.query(Article.id).filter_by(original_url=url).first():
                continue
            article = Article(source_id=source.id, original_url=url, canonical_url=url, title=title,
                cleaned_text="DỮ LIỆU MINH HỌA, KHÔNG PHẢI TIN THẬT. Bài này dùng để thử biên tập, tạo ảnh và đăng thử. Không xuất bản nội dung này lên Facebook.",
                published_at=utcnow())
            db.add(article)
            db.flush()
            ids.append(article.id)
        db.commit()
        if ids:
            ClusteringService(db).cluster_articles(ids)
        print(f"Added {len(ids)} labelled demo articles; existing data preserved.")


if __name__ == "__main__":
    run()
