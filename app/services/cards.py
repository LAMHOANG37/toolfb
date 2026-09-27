import hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from app.config import ROOT, settings

CARD_DIR = ROOT / "data/cards"


def get_font(size):
    paths = [settings.card_font_path, "C:/Windows/Fonts/arial.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for path in paths:
        if path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise ValueError("Chưa có font hỗ trợ tiếng Việt. Cấu hình CARD_FONT_PATH.")


def create_card(draft):
    image = Image.new("RGB", (1200, 630), "#0b1f33")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, 630), fill="#08bfe8")
    draw.text((70, 48), "AI HÔM NAY CÓ GÌ?", font=get_font(28), fill="#08bfe8")
    title = draft.headline or "Tin AI"
    lines = []
    for size in (58, 52, 46, 40, 34):
        font = get_font(size)
        lines, current = [], ""
        for word in title.split():
            candidate = (current + " " + word).strip()
            if draw.textlength(candidate, font=font) > 1060:
                if current:
                    lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) * (size + 16) <= 340 and all(draw.textlength(line, font=font) <= 1060 for line in lines):
            break
    else:
        raise ValueError("Tiêu đề quá dài để tạo ảnh. Hãy rút gọn tiêu đề.")
    y = 145
    for line in lines:
        draw.text((70, y), line, font=font, fill="white")
        y += size + 16
    label = (draft.source_label or "Nguồn trong bài viết")[:70]
    draw.line((70, 530, 1130, 530), fill="#36516a", width=2)
    draw.text((70, 552), label, font=get_font(23), fill="#b8cada")
    fingerprint = hashlib.sha256((title + label).encode()).hexdigest()[:20]
    CARD_DIR.mkdir(parents=True, exist_ok=True)
    path = CARD_DIR / f"draft-{draft.id}-{fingerprint}.png"
    image.save(path)
    return path.name


def card_file(name):
    path = (CARD_DIR / name).resolve()
    if path.parent != CARD_DIR.resolve() or path.suffix != ".png" or not path.is_file():
        raise ValueError("Không tìm thấy ảnh.")
    return path
