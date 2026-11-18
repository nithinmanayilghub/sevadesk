# Text checks on the OpenTelemetry Collector config (story 2.5). The invite page path holds a
# secret token (/invite/<token>). Caddy puts that path into each span's name and "url.path",
# and Caddy cannot turn that off. So the collector rewrites the token BEFORE any span leaves
# our machine. CI copies this same file to the demo server, so one rule covers both stacks.
# (Plain text checks, like test_demo_compose.py: no YAML library needed.)
import re
from pathlib import Path

# backend/tests/unit/<this file> -> parents[3] is the repo root.
CONFIG = Path(__file__).resolve().parents[3] / "infra" / "compose" / "otel-collector.yaml"
RULE = "transform/hide_invite_token"


def _text() -> str:
    return CONFIG.read_text(encoding="utf-8")


def test_the_rule_rewrites_the_path_and_the_span_name():
    text = _text()
    assert f"  {RULE}:" in text
    assert 'replace_pattern(attributes["url.path"], "^/invite/[^/]+", "/invite/:token")' in text
    assert 'replace_pattern(name, "/invite/[^/ ]+", "/invite/:token")' in text


def test_every_trace_passes_the_rule_first():
    # First in the traces pipeline: no other step handles a span before it is cleaned.
    traces = re.search(r"    traces:\s*\n(.*?)\n    \w+:", _text(), re.S)
    assert traces, "no traces pipeline"
    assert re.search(rf"processors: \[{re.escape(RULE)}, batch\]", traces.group(1))
