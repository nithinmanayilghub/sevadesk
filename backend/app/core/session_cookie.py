# The session cookie (AD-5, story 2.2). The cookie holds only a random token; the
# server keeps the session itself. HTTP only: knows nothing about users or modules.
from typing import Annotated

from fastapi import Cookie, Response

# "__Host-": the browser accepts this cookie only if it is Secure, has Path=/ and no Domain.
# So another site under the same parent domain (e.g. *.sslip.io) cannot plant one for us.
SESSION_COOKIE = "__Host-sevadesk_session"

# Set once at log-in and never refreshed, so this is also the longest a session can live.
# The server's idle timeout (7 days) usually ends it first.
MAX_AGE_SECONDS = 30 * 24 * 60 * 60

# Use in a route: `token: SessionTokenCookie = None` reads the cookie (None if missing).
SessionTokenCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]

# The same flags on set and delete; a browser ignores a delete whose flags do not match.
_FLAGS = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}


def set_session_cookie(response: Response, token: str) -> None:
    # httponly: page JavaScript cannot read it, so an injected script cannot steal it.
    # secure: sent only over https (browsers also allow http://localhost).
    # samesite=lax: other sites cannot make the browser send it on their POSTs.
    response.set_cookie(SESSION_COOKIE, token, max_age=MAX_AGE_SECONDS, **_FLAGS)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, **_FLAGS)
