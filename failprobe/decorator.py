"""The ``@probe`` decorator — FailProbe's primary user-facing API.

``probe`` wraps an ``async`` agent function and, around each call, captures an
:class:`~failprobe.models.AgentSpan`, classifies any failure with the
rule-based :class:`~failprobe.classifier.FailureClassifier`, and emits the span
fire-and-forget via :func:`asyncio.create_task`.

Two hard constraints govern this module (spec §5.1, Rule 2):

* **Transparency.** The wrapped function's return value and exception reach the
  caller unchanged. On failure the original exception is re-raised after the
  span is recorded.
* **Never block, never crash.** Span emission is always scheduled with
  ``asyncio.create_task`` and never awaited. Any error inside FailProbe's own
  recording path is logged via ``logger.error(exc_info=True)`` and swallowed —
  it must never propagate to the caller.
"""

import asyncio
import functools
import inspect
import logging
import time
import traceback
import uuid
from typing import Any, Callable, Optional

from failprobe.classifier.classifier import FailureClassifier
from failprobe.config import get_config
from failprobe.models import AgentSpan
from failprobe.tracer import _emit_span

logger = logging.getLogger("failprobe")

# The classifier is stateless and synchronous; one shared instance suffices.
_CLASSIFIER = FailureClassifier()

# The opt-in parameter the decorator injects a fresh ToolCall list into.
_COLLECTOR_PARAM = "_probe_collector"


def _accepts_collector(func: Callable) -> bool:
    """Return whether ``func`` declares the opt-in ``_probe_collector`` param."""
    try:
        return _COLLECTOR_PARAM in inspect.signature(func).parameters
    except (TypeError, ValueError):
        # Builtins / C functions may expose no inspectable signature.
        return False


def _extract_tokens(output: Any) -> Optional[int]:
    """Extract a token count from ``output`` when it is a dict with ``usage``.

    Supports the two common shapes: ``{"usage": <int>}`` and
    ``{"usage": {"total_tokens": <int>}}``. Anything else yields ``None``.
    """
    if isinstance(output, dict) and "usage" in output:
        usage = output["usage"]
        if isinstance(usage, int):
            return usage
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            return usage["total_tokens"]
    return None


def _detect_model(explicit: Optional[str], output: Any) -> Optional[str]:
    """Resolve the model name: the explicit ``@probe`` kwarg wins, else auto-detect.

    Auto-detection inspects the return value for a ``"model"`` dict key or a
    ``.model`` attribute (string-valued). Returns ``None`` when nothing matches.
    """
    if explicit is not None:
        return explicit
    if isinstance(output, dict) and isinstance(output.get("model"), str):
        return output["model"]
    attr = getattr(output, "model", None)
    if isinstance(attr, str):
        return attr
    return None


def probe(
    name: str,
    expected_output: Any = None,
    timeout: Optional[float] = None,
    model: Optional[str] = None,
    tags: Optional[dict] = None,
) -> Callable:
    """Wrap an ``async`` agent function with transparent failure capture.

    The returned decorator records an :class:`AgentSpan` for every call,
    classifies failures, and emits the span fire-and-forget. The wrapped
    function's signature, return value, and raised exceptions are preserved
    exactly.

    Args:
        name: Logical agent name recorded as ``AgentSpan.agent_name``.
        expected_output: Reference output for later LLM-judge evaluation.
            Accepted now; consumed by the evaluator in a future task.
        timeout: Intended wall-clock budget in seconds. Accepted now; timeout
            enforcement is a future task.
        model: Model identifier to record; when ``None`` the decorator attempts
            to auto-detect it from the return value.
        tags: Per-call tags merged into ``AgentSpan.metadata`` on top of the
            process-level ``ProbeConfig.tags`` defaults.

    Returns:
        A decorator that wraps an ``async`` function, preserving its behaviour.
    """
    # expected_output and timeout are part of the public signature (spec §5.1)
    # but are not acted upon in this task.
    _ = expected_output  # TODO: future task — passed to the LLM judge.
    _ = timeout  # TODO: future task — wall-clock timeout enforcement.

    def decorator(func: Callable) -> Callable:
        injects_collector = _accepts_collector(func)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. Generate run_id.
            run_id = str(uuid.uuid4())
            # 2. Record start time.
            start = time.perf_counter()

            # 3. Inject a fresh collector iff the function opts in.
            collector: list = []
            if injects_collector:
                kwargs[_COLLECTOR_PARAM] = collector

            output: Any = None
            raised: Optional[BaseException] = None
            exception_str: Optional[str] = None
            success = True

            # 4. Call the wrapped function inside try/except.
            try:
                output = await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — recorded, then re-raised below.
                success = False
                exception_str = traceback.format_exc()
                raised = exc

            # 5. Record end time → duration_ms (always, even on failure).
            duration_ms = (time.perf_counter() - start) * 1000.0

            # 6-8. Build span, classify, emit — fully isolated so an FailProbe
            #       internal error can never reach the caller (Rule 2).
            try:
                recorded_kwargs = {
                    k: v for k, v in kwargs.items() if k != _COLLECTOR_PARAM
                }
                span = AgentSpan(
                    run_id=run_id,
                    agent_name=name,
                    input={"args": args, "kwargs": recorded_kwargs},
                    output=output,
                    duration_ms=duration_ms,
                    tool_calls=collector,
                    tokens_used=_extract_tokens(output),
                    model=_detect_model(model, output),
                    success=success,
                    exception=exception_str,
                    metadata={**get_config().tags, **(tags or {})},
                )

                # 7. Synchronous classification — no await.
                failure_type, explanation = _CLASSIFIER.classify(span)
                if failure_type is not None:
                    span.failure_type = failure_type.value
                    span.failure_msg = explanation

                # 8. Fire-and-forget emission — never await.
                asyncio.create_task(_emit_span(span))
            except Exception:  # noqa: BLE001 — FailProbe must never crash the agent.
                logger.error(
                    "FailProbe internal error while recording span", exc_info=True
                )

            # 9. Transparent pass-through: re-raise original exception, else return.
            if raised is not None:
                raise raised
            return output

        return wrapper

    return decorator
