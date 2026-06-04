"""Tests for the ``@probe`` decorator (``agentprobe/decorator.py``).

Verifies transparency (return value and exceptions pass through unchanged),
non-blocking fire-and-forget emission via ``asyncio.create_task``, internal
error isolation, opt-in ``_probe_collector`` injection, span classification
before emission, and field capture (duration, tokens, model, tags).

The real ``_emit_span`` is a TASK 08 stub that raises ``NotImplementedError``;
the ``emitted`` fixture patches it with an async recorder so tests can assert on
the emitted span without triggering the stub in a fire-and-forget task.
"""

import asyncio

import pytest

from agentprobe import probe
from agentprobe.classifier.taxonomy import FailureType
from agentprobe.models import ToolCall


@pytest.fixture
def emitted(monkeypatch):
    """Replace ``_emit_span`` with an async recorder; yield the captured list."""
    spans: list = []

    async def fake_emit(span) -> None:
        spans.append(span)

    monkeypatch.setattr("agentprobe.decorator._emit_span", fake_emit)
    return spans


# --------------------------------------------------------------------------- #
# Transparency
# --------------------------------------------------------------------------- #
async def test_return_value_unchanged(emitted) -> None:
    """The wrapped function's return value reaches the caller unchanged."""

    @probe(name="echo")
    async def run(q: str) -> str:
        return q.upper()

    assert await run("hello") == "HELLO"


async def test_preserves_function_metadata() -> None:
    """``functools.wraps`` keeps the wrapped name and docstring."""

    @probe(name="meta")
    async def run(q: str) -> str:
        """Original docstring."""
        return q

    assert run.__name__ == "run"
    assert run.__doc__ == "Original docstring."


async def test_reraises_original_exception(emitted) -> None:
    """A raising agent re-raises its original exception to the caller."""

    @probe(name="boom")
    async def run(q: str) -> str:
        raise ValueError("something broke")

    with pytest.raises(ValueError, match="something broke"):
        await run("hello")


# --------------------------------------------------------------------------- #
# Non-blocking / fire-and-forget emission
# --------------------------------------------------------------------------- #
async def test_emission_is_fire_and_forget(emitted) -> None:
    """Emission is scheduled via create_task, not awaited inside the wrapper."""

    @probe(name="async")
    async def run(q: str) -> str:
        return q

    await run("x")
    # The task has been scheduled but not yet run — proof it was not awaited.
    assert emitted == []
    # Yield control so the scheduled emit task runs.
    await asyncio.sleep(0)
    assert len(emitted) == 1
    assert emitted[0].agent_name == "async"


# --------------------------------------------------------------------------- #
# Internal error isolation
# --------------------------------------------------------------------------- #
async def test_internal_error_does_not_propagate(monkeypatch, emitted) -> None:
    """A crash inside AgentProbe's recording path never reaches the caller."""

    def boom(span):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr("agentprobe.decorator._CLASSIFIER.classify", boom)

    @probe(name="resilient")
    async def run(q: str) -> str:
        return "ok"

    assert await run("x") == "ok"
    assert emitted == []  # emission never reached, but no crash


async def test_internal_error_still_reraises_user_exception(monkeypatch, emitted) -> None:
    """An internal error must not mask the agent's own exception."""

    def boom(span):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr("agentprobe.decorator._CLASSIFIER.classify", boom)

    @probe(name="resilient")
    async def run(q: str) -> str:
        raise ValueError("user failure")

    with pytest.raises(ValueError, match="user failure"):
        await run("x")


# --------------------------------------------------------------------------- #
# _probe_collector injection (opt-in)
# --------------------------------------------------------------------------- #
async def test_collector_injected_when_param_present(emitted) -> None:
    """A function declaring ``_probe_collector`` receives a fresh list to fill."""
    tc = ToolCall(
        tool_name="get_weather",
        params={"city": "Delhi"},
        result="sunny",
        duration_ms=12.0,
        error=None,
        timestamp=0.0,
    )

    @probe(name="weather")
    async def run(q: str, _probe_collector: list = None) -> str:
        _probe_collector.append(tc)
        return "done"

    await run("weather?")
    await asyncio.sleep(0)
    assert emitted[0].tool_calls == [tc]


async def test_collector_not_injected_when_param_absent(emitted) -> None:
    """A function without the param is called without the extra kwarg."""

    @probe(name="plain")
    async def run(q: str) -> str:
        return "done"

    assert await run("x") == "done"
    await asyncio.sleep(0)
    assert emitted[0].tool_calls == []


# --------------------------------------------------------------------------- #
# Span capture & classification
# --------------------------------------------------------------------------- #
async def test_duration_recorded_on_success(emitted) -> None:
    """``duration_ms`` is recorded on a successful run."""

    @probe(name="ok")
    async def run(q: str) -> str:
        return q

    await run("x")
    await asyncio.sleep(0)
    assert emitted[0].duration_ms >= 0.0
    assert emitted[0].success is True
    assert emitted[0].failure_type is None


async def test_failure_classified_before_emit(emitted) -> None:
    """A raising run is recorded as a classified EXCEPTION with a duration."""

    @probe(name="crash")
    async def run(q: str) -> str:
        raise ValueError("x")

    with pytest.raises(ValueError):
        await run("x")
    await asyncio.sleep(0)
    span = emitted[0]
    assert span.success is False
    assert span.duration_ms >= 0.0
    assert span.exception is not None
    assert span.failure_type == FailureType.EXCEPTION.value
    assert span.failure_msg


async def test_tokens_and_model_autodetected(emitted) -> None:
    """Tokens and model are extracted from a dict return value."""

    @probe(name="usage")
    async def run(q: str) -> dict:
        return {"usage": {"total_tokens": 42}, "model": "gpt-x"}

    await run("x")
    await asyncio.sleep(0)
    assert emitted[0].tokens_used == 42
    assert emitted[0].model == "gpt-x"


async def test_explicit_model_overrides_autodetect(emitted) -> None:
    """The explicit ``model`` kwarg wins over auto-detection."""

    @probe(name="usage", model="claude-haiku-4")
    async def run(q: str) -> dict:
        return {"model": "ignored"}

    await run("x")
    await asyncio.sleep(0)
    assert emitted[0].model == "claude-haiku-4"


async def test_tags_merged_into_metadata(emitted) -> None:
    """Per-call ``tags`` are stored in the span's metadata."""

    @probe(name="tagged", tags={"env": "test"})
    async def run(q: str) -> str:
        return "ok"

    await run("x")
    await asyncio.sleep(0)
    assert emitted[0].metadata.get("env") == "test"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def test_public_exports() -> None:
    """The package exports exactly ``probe``, ``ProbeConfig``, ``configure``."""
    import agentprobe

    assert set(agentprobe.__all__) == {"probe", "ProbeConfig", "configure"}
    assert callable(agentprobe.probe)
