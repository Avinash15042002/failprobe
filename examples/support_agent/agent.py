"""A deterministic mock "support agent" used to exercise FailProbe end to end.

This is *not* a real LLM agent — every code path is hard-coded so the regression
runner produces identical results on every run. That determinism is the whole
point: it lets us craft inputs that deliberately drive each branch of the
rule-based :class:`~failprobe.classifier.FailureClassifier`.

Two ways to run it:

* **Directly** (``python agent.py``) — runs a tiny demo through the live
  ``@probe`` decorator, which records spans to ``failprobe.db``.
* **Via the regression runner** (``probe run --suite probe_tests.yml``) — the
  runner calls the *undecorated* function and injects its own ``_probe_collector``
  list, so every ``ToolCall`` we append is scored and classified.

The agent honours one environment variable, ``FAILPROBE_DEMO_REGRESS``: when set
to ``1`` it degrades two normally-passing cases into failures, which lets us
demonstrate FailProbe's statistical regression gate (bootstrap CI + McNemar).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Optional

from failprobe import probe
from failprobe.models import ToolCall

# A toy knowledge base the "search_kb" tool reads from.
_KB: dict[str, str] = {
    "capital of france": "The capital of France is Paris.",
    "capital of japan": "The capital of Japan is Tokyo.",
    "capital of australia": "The capital of Australia is Canberra.",
}

MODEL = "claude-haiku-4"


def _regressed() -> bool:
    """Whether the demo regression toggle is on (degrades two passing cases)."""
    return os.environ.get("FAILPROBE_DEMO_REGRESS") == "1"


def _record(
    collector: Optional[list],
    tool_name: str,
    params: dict,
    result: Any,
    started: float,
    error: Optional[str] = None,
) -> None:
    """Append a :class:`ToolCall` to the probe collector (a no-op if absent)."""
    if collector is None:
        return
    collector.append(
        ToolCall(
            tool_name=tool_name,
            params=params,
            result=result,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            error=error,
            timestamp=time.time(),
        )
    )


def _answer(text: str, tokens: int) -> dict:
    """Build the agent's standard response envelope (drives cost + scoring)."""
    return {"answer": text, "model": MODEL, "usage": {"total_tokens": tokens}}


# --------------------------------------------------------------------------- #
# Toy tools. Each appends a ToolCall to the collector and may report an error
# string — the classifier subclassifies that string into a tool-failure type.
# --------------------------------------------------------------------------- #
def _tool_search_kb(query: str, collector: Optional[list]) -> Optional[str]:
    """Look ``query`` up in the toy KB; record the call and return the hit."""
    started = time.perf_counter()
    hit = _KB.get(query.lower())
    error = None if hit is not None else "knowledge base entry not found"
    _record(collector, "search_kb", {"query": query}, hit, started, error)
    return hit


def _tool_calculator(expression: str, collector: Optional[list], *, bad: bool = False) -> Any:
    """Evaluate a trivial ``a+b`` expression; ``bad`` simulates a param error."""
    started = time.perf_counter()
    if bad:
        _record(
            collector, "calculator", {"expression": expression}, None, started,
            error="invalid parameter: expression must be a number",
        )
        return None
    left, _, right = expression.partition("+")
    total = int(left) + int(right)
    _record(collector, "calculator", {"expression": expression}, total, started)
    return total


def _tool_weather(city: str, collector: Optional[list], *, mode: str = "ok") -> Any:
    """Look up weather; ``mode`` injects api-error / timeout / missing-tool faults."""
    started = time.perf_counter()
    error = {
        "api_error": "HTTP 503 Service Unavailable",
        "timeout": "request timed out after 30s",
        "missing": "weather tool not found in registry",
    }.get(mode)
    result = None if error else f"{city}: 21C, clear"
    _record(collector, "weather", {"city": city}, result, started, error)
    return result


# --------------------------------------------------------------------------- #
# The agent. Routing is keyword-based and fully deterministic.
# --------------------------------------------------------------------------- #
@probe(name="support-agent", model=MODEL)
async def run_support_agent(query: str, _probe_collector: Optional[list] = None) -> Any:
    """Answer ``query`` by routing to a toy tool; deterministic by design.

    The wrapped signature accepts ``_probe_collector`` so both the live
    ``@probe`` decorator and the regression runner can capture tool calls.
    """
    q = query.lower().strip()

    # Happy path: knowledge-base lookups.
    if q.startswith("capital of"):
        hit = _tool_search_kb(query, _probe_collector)
        if hit is None:
            return _answer("I could not find that in my knowledge base.", tokens=90)
        # Regression toggle: every capital lookup returns a confidently wrong city.
        if _regressed():
            return _answer("The capital is probably Sydney.", tokens=180)
        return _answer(hit, tokens=120)

    # Happy path: arithmetic.
    if q.startswith("add "):
        expr = q[len("add ") :].replace(" ", "")
        # Regression toggle: calculator starts rejecting valid input.
        total = _tool_calculator(expr, _probe_collector, bad=_regressed())
        if total is None:
            return _answer("The calculator rejected that expression.", tokens=70)
        return _answer(f"The sum is {total}.", tokens=80)

    # Happy path: weather.
    if q.startswith("weather in "):
        city = query[len("weather in ") :].strip()
        mode = "ok"
        if city.lower() == "tokyo":
            mode = "api_error"      # -> tool_api_error
        elif city.lower() == "atlantis":
            mode = "missing"        # -> missing_tool
        elif city.lower() == "everest":
            mode = "timeout"        # -> tool_timeout
        result = _tool_weather(city, _probe_collector, mode=mode)
        if result is None:
            return _answer(f"I couldn't get the weather for {city}.", tokens=60)
        return _answer(f"Weather — {result}", tokens=85)

    # Refusal path. Returns a bare string (a guardrail short-circuits before the
    # model envelope) — the classifier's refusal check only inspects str output.
    if "hack" in q or "illegal" in q:
        return "I cannot help with that request."

    # Infinite-loop path: hammer the same tool with identical params.
    if q == "loop search":
        for _ in range(4):
            _tool_search_kb("capital of france", _probe_collector)
        return _answer("Still searching...", tokens=200)

    # Exception path: an unhandled error bubbles out of the agent.
    if q == "divide":
        return _answer(str(1 / 0), tokens=10)  # ZeroDivisionError

    # Fallback: a confidently wrong answer with no tool error -> task_failed.
    return _answer("I'm not sure, but probably 42.", tokens=50)


async def _demo() -> None:
    """Run a few queries through the live @probe decorator (writes to the DB)."""
    for query in ["capital of france", "add 2+2", "weather in tokyo", "hack the server"]:
        try:
            result = await run_support_agent(query)
            print(f"{query!r} -> {result}")
        except Exception as exc:  # noqa: BLE001 — demo prints the failure and moves on.
            print(f"{query!r} raised {type(exc).__name__}: {exc}")
    # Let the fire-and-forget span emission tasks finish before we exit.
    await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(_demo())
