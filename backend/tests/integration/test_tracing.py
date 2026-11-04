# Integration tests: one request to /hello makes one trace (FastAPI span + Postgres span).
import re

from opentelemetry.trace import SpanKind


def _is_postgres(span) -> bool:
    # Older and newer OpenTelemetry naming rules use different attribute names.
    attrs = span.attributes or {}
    return "postgresql" in (attrs.get("db.system"), attrs.get("db.system.name"))


def test_hello_makes_one_trace_with_sql_span(client, spans):
    spans.clear()
    response = client.get("/api/v1/hello")
    assert response.status_code == 200
    finished = spans.finished()
    server = [s for s in finished if s.kind == SpanKind.SERVER]
    sql = [s for s in finished if _is_postgres(s)]
    assert len(server) == 1
    assert sql, "expected at least one Postgres span"
    assert all(s.context.trace_id == server[0].context.trace_id for s in sql)


def test_response_has_request_id_header(client):
    response = client.get("/api/v1/hello")
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_incoming_traceparent_is_continued(client, spans):
    # This is the header Caddy sends: version-traceid-parentspanid-flags.
    spans.clear()
    trace_hex = "0af7651916cd43dd8448eb211c80319c"
    client.get("/api/v1/hello", headers={"traceparent": f"00-{trace_hex}-b7ad6b7169203331-01"})
    assert any(format(s.context.trace_id, "032x") == trace_hex for s in spans.finished())
