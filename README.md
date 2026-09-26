# AI Hôm Nay Có Gì? — Newsroom

An AI-assisted newsroom that automatically discovers AI news, removes duplicates, evaluates and verifies stories, creates Vietnamese Facebook posts, generates branded social cards, lets the user review content, schedules posts, and publishes approved posts to a Facebook Page.

## Architecture
- Backend: FastAPI, Python 3.12+
- Database: SQLite (local development), SQLAlchemy ORM, Alembic migrations
- Frontend: Jinja2, HTMX, vanilla CSS

## Installation
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

## Database Setup
```bash
alembic upgrade head
```

## Running the Server
```bash
uvicorn app.main:app --reload
```

## Running Tests
```bash
pytest -v
```

## Configuration
- Add sources to `sources.yaml`
- Update `.env` with Facebook and LLM keys. (Use `FACEBOOK_DRY_RUN=true` to test safely).
