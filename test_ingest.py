"""Manual ingestion CLI. Importing this module has no side effects."""
def main():
    from app.database import SessionLocal
    from app.services.ingestion import IngestionService
    with SessionLocal() as db:
        print(IngestionService(db).run())


if __name__ == "__main__":
    main()
