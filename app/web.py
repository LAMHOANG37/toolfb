from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from app.config import ROOT, settings
from app.timeutils import localtime

templates = Jinja2Templates(directory=str(ROOT / "app/templates"))
templates.env.filters["localtime"] = localtime
LABELS = {
    "discovered": "Mới", "normalized": "Đã gom nhóm", "accepted": "Đã chọn", "rejected": "Từ chối",
    "generated": "Bản nháp", "needs_review": "Chờ duyệt", "approved": "Đã duyệt",
    "scheduled": "Đã lên lịch", "published": "Đã đăng", "pending": "Chờ xử lý",
    "running": "Đang chạy", "successful": "Thành công", "failed": "Có lỗi",
    "cancelled": "Đã hủy", "simulated": "Đã đăng thử", "uncertain": "Cần đối soát",
    "queued": "Đang chờ", "completed": "Hoàn tất", "partial": "Hoàn tất một phần",
    "official": "Chính thức", "publication": "Báo chí", "community": "Cộng đồng",
}
templates.env.filters["label"] = lambda value: LABELS.get(getattr(value, "value", value), value)


def render(request, name, status_code=200, **context):
    return templates.TemplateResponse(request=request, name=name, status_code=status_code,
        context={"request": request, "settings": settings, "flash": request.session.pop("flash", None), **context})


def redirect(request, url, message=None):
    if message:
        request.session["flash"] = message
    return RedirectResponse(url, status_code=303)
