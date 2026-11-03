# Unit test: the exporter wrapper masks span attributes and event attributes before export.
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.telemetry import MaskingSpanExporter


def test_span_attributes_and_events_are_masked():
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(MaskingSpanExporter(memory)))
    tracer = provider.get_tracer("test")

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
