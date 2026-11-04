# Text checks on infra/demo/: the demo stack runs CI's images, keeps its data, and lets Neon sleep.
import re
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
DEMO_DIR = Path(__file__).resolve().parents[3] / "infra" / "demo"
COMPOSE = DEMO_DIR / "docker-compose.yml"
SECRET_KEYS = ("DEMO_DOMAIN", "DATABASE_URL", "OTLP_EXPORT_ENDPOINT", "OTLP_EXPORT_AUTH")


def _text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def _services_part() -> str:
    return _text().split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]


def _services() -> set[str]:
    return set(re.findall(r"^  ([\w-]+):\n", _services_part(), re.M))


def _service_block(name: str) -> str:
    """Return the text of one service: from '  <name>:' to the next service (or end of section)."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", _services_part(), re.S | re.M)
    assert match, f"service '{name}' not found in demo compose"
    return match.group(1)


def _anchor_block(name: str) -> str:
    """Return the text of a top-level block like 'x-backend: &backend'."""
    match = re.search(rf"^{name}:.*?\n(.*?)(?=^\S)", _text(), re.S | re.M)
    assert match, f"top-level block '{name}' not found in demo compose"
    return match.group(1)


# Behaviour: the demo never builds; it runs the exact images CI pushed for one commit.
def test_demo_runs_only_ghcr_images_by_tag():
    text = _text()
    assert "build:" not in text
    assert "ghcr.io/nithinmanayilghub/sevadesk-backend:${IMAGE_TAG:?" in text
    assert "ghcr.io/nithinmanayilghub/sevadesk-frontend:${IMAGE_TAG:?" in text


# Behaviour: Postgres is Neon, outside the VM, so there is no database container.
def test_demo_has_no_database_container():
    assert _services() == {"caddy", "frontend", "backend", "worker", "valkey", "otel-collector"}


# Behaviour: Valkey writes every change to disk (AOF), so queued jobs survive a restart.
def test_demo_valkey_keeps_jobs_across_restarts():
    block = _service_block("valkey")
    assert '"--appendonly", "yes"' in block
    assert "valkey_data:/data" in block


# Behaviour: Caddy keeps its TLS certificates on a volume, so a restart does not ask for new ones.
def test_demo_caddy_keeps_its_certificates():
    assert "caddy_data:/data" in _service_block("caddy")


# Behaviour: no healthcheck calls /api/health (it queries Postgres), so Neon can sleep (AR-22).
def test_demo_healthchecks_never_touch_the_database():
    assert "/api/health" not in _text()


# Behaviour: every container comes back after a crash or a VM reboot.
def test_every_demo_service_restarts_after_a_reboot():
    assert "restart: unless-stopped" in _anchor_block("x-backend")
    for name in _services():
        block = _service_block(name)
        assert "restart: unless-stopped" in block or "<<: *backend" in block, name


# Behaviour: only an example env file is in git, with every secret left empty.
def test_demo_secrets_are_not_committed():
    example = (DEMO_DIR / ".env.example").read_text(encoding="utf-8")
    for key in SECRET_KEYS:
        assert re.search(rf"^{key}=$", example, re.M), key
    assert not (DEMO_DIR / ".env").exists()
