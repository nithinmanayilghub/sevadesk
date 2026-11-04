# Unit tests: the exporter wrapper masks span attributes, events, and error text before export.
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.telemetry import MaskingSpanExporter


@pytest.fixture
def traced():
    # A local tracer whose spans go through the masking exporter into memory.
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(MaskingSpanExporter(memory)))
    return provider.get_tracer("test"), memory


def test_span_attributes_and_events_are_masked(traced):
    tracer, memory = traced
    with tracer.start_as_current_span("work") as span:
        span.set_attribute("note", "call 9876543210")
        span.set_attribute("address", "12 MG Road")
        span.set_attribute("seats", 2)
        span.add_event("error", {"msg": "+91 98765 43210"})

    exported = memory.get_finished_spans()[0]
    assert exported.name == "work"
    assert exported.attributes["note"] == "call [PHONE]"
    assert exported.attributes["address"] == "[MASKED]"
    assert exported.attributes["seats"] == 2
    assert exported.events[0].name == "error"
    assert exported.events[0].attributes["msg"] == "[PHONE]"


def test_error_status_and_exception_are_masked(traced):
    # An error inside a span: the SDK records it as an event AND as the span's status text.
    tracer, memory = traced
    with pytest.raises(ValueError), tracer.start_as_current_span("work"):
        raise ValueError("bad phone 9876543210")

    exported = memory.get_finished_spans()[0]
    assert exported.status.description == "ValueError: bad phone [PHONE]"
    assert exported.events[0].attributes["exception.message"] == "bad phone [PHONE]"
    assert "9876543210" not in exported.events[0].attributes["exception.stacktrace"]
