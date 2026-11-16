# Text checks on both Caddyfiles (story 2.5): the invite page path holds a secret token,
# so Caddy must give it a FIXED span name. Every other request keeps "<method> <path>".
import re
from pathlib import Path

import pytest

# backend/tests/unit/<this file> -> parents[3] is the repo root.
INFRA = Path(__file__).resolve().parents[3] / "infra"
CADDYFILES = [INFRA / "compose" / "Caddyfile", INFRA / "demo" / "Caddyfile"]
PATH_SPAN = 'span "{http.request.method} {http.request.uri.path}"'


def _tracing_blocks(text: str) -> dict[str, str]:
    """Each 'tracing <matcher> { ... }' block, keyed by its matcher ('' when there is none)."""
    # A block ends at its own closing line ("\t}"), not at the braces inside "{http.request...}".
    pattern = r"tracing\s*(@\w+)?\s*\{\r?\n(.*?)\r?\n\t\}"
    return {m.group(1) or "": m.group(2) for m in re.finditer(pattern, text, re.S)}


@pytest.mark.parametrize("caddyfile", CADDYFILES, ids=lambda p: p.parent.name)
def test_invite_page_spans_never_hold_the_token(caddyfile):
    text = caddyfile.read_text(encoding="utf-8")
    blocks = _tracing_blocks(text)
    assert "@invite path /invite/*" in text
    assert 'span "GET /invite/{token}"' in blocks["@invite"]
    # The path-named span only for requests that are NOT the invite page.
    assert "@not_invite not path /invite/*" in text
    assert PATH_SPAN in blocks["@not_invite"]
    assert set(blocks) == {"@invite", "@not_invite"}, "no tracing block without a matcher"
