# The CSRF guard (AD-5, story 2.2, D4).
#
# CSRF ("cross-site request forgery"): a page on evil.example makes your browser send a
# POST to us. The browser adds your session cookie, so without a guard we would obey.
# The browser also adds an Origin header naming the site that started the request, and
# a page cannot change it. So every state-changing request must carry OUR origin.
#
# "Ours" = the Host the request was sent to. Caddy and the AWS ALB pass Host through
# unchanged; no proxy in front of the backend may rewrite it.
from urllib.parse import urlsplit

from fastapi import FastAPI, Request

from app.core.errors import error_response

# Methods that may change data. GET and HEAD never change data (AD-5), so they need no check.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if not origin or not host:
        return False  # no Origin (curl, scripts) or no Host: refuse
    # urlsplit("https://shop.in:8443").netloc == "shop.in:8443". "null" gives "" and fails.
    return urlsplit(origin).netloc.lower() == host.lower()


def add_origin_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        # Runs before routing, so a refused request reaches no route and changes nothing.
        if request.method in UNSAFE_METHODS and not _same_origin(request):
            return error_response(403, "origin_refused", "This request was refused.")
        return await call_next(request)
