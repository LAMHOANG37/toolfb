import hashlib
import secrets
import time
from collections import defaultdict
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from app.config import settings

router = APIRouter()
_attempts = defaultdict(list)


def credential_stamp():
    return hashlib.sha256(settings.admin_password.get_secret_value().encode()).hexdigest()


async def security_middleware(request, call_next):
    public = request.url.path in {"/login", "/health"} or request.url.path.startswith("/static/")
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    signed_in = request.session.get("user") == settings.admin_username and request.session.get("credential_stamp") == credential_stamp()
    if not public and not signed_in:
        return RedirectResponse("/login", status_code=303)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        body = await request.body()
        if len(body) > 131072:
            return JSONResponse({"detail": "Dữ liệu quá lớn."}, status_code=413)
        form = await request.form()
        token = request.headers.get("X-CSRF-Token") or form.get("csrf_token", "")
        if not isinstance(token, str) or not secrets.compare_digest(token, request.session["csrf"]):
            return JSONResponse({"detail": "Phiên không hợp lệ. Tải lại trang."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store" if not request.url.path.startswith("/static/") else "public, max-age=3600"
    return response


@router.get("/login")
def login_page(request: Request):
    from app.web import render
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    from app.web import render
    host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if len(_attempts) > 1000:
        _attempts.clear()
    _attempts[host] = [t for t in _attempts[host] if now - t < 300]
    if len(_attempts[host]) >= 5:
        return render(request, "login.html", error="Thử lại sau 5 phút.", status_code=429)
    valid = secrets.compare_digest(username.encode(), settings.admin_username.encode())
    valid &= secrets.compare_digest(password.encode(), settings.admin_password.get_secret_value().encode())
    if not valid or not settings.admin_password.get_secret_value():
        _attempts[host].append(now)
        return render(request, "login.html", error="Tên đăng nhập hoặc mật khẩu không đúng.", status_code=401)
    _attempts.pop(host, None)
    request.session.clear()
    request.session.update(user=settings.admin_username, credential_stamp=credential_stamp(), csrf=secrets.token_urlsafe(32))
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
