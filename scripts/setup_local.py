"""Create a private local configuration without overwriting existing secrets."""
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    destination = ROOT / ".env"
    if destination.exists():
        print(".env already exists; leaving it unchanged.")
        return
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    text = text.replace("ADMIN_PASSWORD=", "ADMIN_PASSWORD=" + secrets.token_urlsafe(18), 1)
    text = text.replace("SECRET_KEY=", "SECRET_KEY=" + secrets.token_urlsafe(48), 1)
    destination.write_text(text, encoding="utf-8")
    print("Created .env. Open it locally to read ADMIN_PASSWORD. Username: admin.")
    print("Keep .env private. No AI key or Facebook token has been configured.")


if __name__ == "__main__":
    main()
