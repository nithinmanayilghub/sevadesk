# Guard: app code uses only OpenTelemetry for observability, so the tool changes by config alone.
import ast
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Third-party packages the app may import. Observability goes through "opentelemetry" only.
ALLOWED = {
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "redis",
    "saq",
    "starlette",
    "opentelemetry",
}


def disallowed_imports(source: str) -> set[str]:
    """Top-level packages imported by source that are not stdlib, not our app, and not allowed."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top not in sys.stdlib_module_names and top != "app" and top not in ALLOWED:
                found.add(top)
    return found


def test_detector_flags_a_vendor_sdk():
    assert disallowed_imports("import sentry_sdk\nfrom opentelemetry import trace") == {"sentry_sdk"}


def test_app_uses_only_opentelemetry_for_observability():
    files = list(APP_DIR.rglob("*.py"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert disallowed_imports(text) == set(), path
        assert "grafana.net" not in text, path
