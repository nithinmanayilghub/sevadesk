# Checks the session dependency commits BEFORE the response is sent (AD-15).
from app.core.db import get_session
from app.core.hello_router import router


def test_hello_session_dependency_uses_function_scope():
    # scope="function" makes the commit run before the response goes out,
    # so a failed commit becomes an error response, not a silent loss.
    route = next(r for r in router.routes if getattr(r, "path", None) == "/api/v1/hello")
    session_dep = next(d for d in route.dependant.dependencies if d.call is get_session)
    assert session_dep.scope == "function"
