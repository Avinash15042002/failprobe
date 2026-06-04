"""LLM-as-Judge: score an agent run against a rubric.

This module owns the evaluator's LLM-judge concern only (spec §5.5). The public
entry point is :func:`judge_run`, which **always** returns a :class:`JudgeResult`
and never raises — every failure (network, timeout, malformed response) is
caught, logged to stderr, and converted into a result with ``score=0.0``.

Model routing is by string prefix: ``claude*`` → Anthropic SDK, ``gpt*`` →
OpenAI SDK. Both SDKs are imported lazily inside :func:`_call_llm` so importing
this module never requires API credentials.

Per the layer-ownership rules, this module may read configuration and persist to
storage (writing ``EvalResult`` rows) but must not perform span capture or
failure classification.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agentprobe.config import get_config
from agentprobe.models import AgentSpan, ToolCall
from agentprobe.storage.db import get_session
from agentprobe.storage.models import EvalResult

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Appended to the prompt on the single retry that follows a JSON parse failure.
_STRICTER_SUFFIX = "\n\nReturn only raw JSON, no backticks."

# Anthropic's Messages API requires an explicit output token budget.
_MAX_TOKENS = 1024


@dataclass
class JudgeResult:
    """Structured outcome of judging a single agent run.

    ``score`` and ``confidence`` are both in ``[0.0, 1.0]``. On any judge
    failure, ``score`` and ``confidence`` are ``0.0`` and ``reasoning`` is a
    short machine-readable token (``"parse_error"`` or ``"judge_error"``).
    """

    run_id: str
    score: float
    reasoning: str
    model_used: str
    latency_ms: float
    confidence: float


@dataclass
class _ParsedJudgement:
    """Validated fields extracted from a judge's JSON response."""

    score: float
    reasoning: str
    confidence: float


async def judge_run(
    span: AgentSpan,
    rubric: str,
    model: str = "claude-haiku-4",
) -> JudgeResult:
    """Judge an agent run against ``rubric`` using ``model``.

    Builds the judge prompt from the span, calls the routed LLM with a timeout
    of :attr:`ProbeConfig.judge_timeout`, parses the JSON response, and persists
    the outcome as an ``EvalResult`` row. On a JSON parse failure the call is
    retried once with a stricter prompt; a second failure yields a
    ``reasoning="parse_error"`` result. Any other error yields a
    ``reasoning="judge_error"`` result.

    This function never raises — it always returns a :class:`JudgeResult`.

    Args:
        span: The agent run to evaluate.
        rubric: The scoring rubric text injected into the prompt.
        model: Model identifier; ``claude*`` routes to Anthropic, ``gpt*`` to
            OpenAI.

    Returns:
        A :class:`JudgeResult` for ``span.run_id``.
    """
    start = time.perf_counter()
    try:
        result = await _evaluate(span, rubric, model, start)
    except Exception:  # noqa: BLE001 — judge must never propagate errors
        logger.error("unexpected error in judge_run for run %s", span.run_id, exc_info=True)
        result = JudgeResult(
            run_id=span.run_id,
            score=0.0,
            reasoning="judge_error",
            model_used=model,
            latency_ms=_elapsed_ms(start),
            confidence=0.0,
        )
    await _write_eval_result(result)
    return result


async def _evaluate(span: AgentSpan, rubric: str, model: str, start: float) -> JudgeResult:
    """Run the up-to-two-attempt judge loop and return a :class:`JudgeResult`.

    Attempt 1 uses the base prompt; on a JSON parse failure, attempt 2 uses the
    stricter prompt. Returns ``judge_error`` on an LLM/transport failure and
    ``parse_error`` when both attempts fail to parse.
    """
    config = get_config()
    base_prompt = _build_prompt(span, rubric)

    for attempt in (1, 2):
        prompt = base_prompt if attempt == 1 else base_prompt + _STRICTER_SUFFIX
        try:
            raw = await asyncio.wait_for(_call_llm(prompt, model), timeout=config.judge_timeout)
        except Exception:  # noqa: BLE001 — timeout/transport errors must not propagate
            logger.error("judge LLM call failed for run %s", span.run_id, exc_info=True)
            return _failure_result(span.run_id, "judge_error", model, start)

        try:
            parsed = _parse_judge_json(raw)
        except (ValueError, TypeError):
            if attempt == 1:
                logger.warning(
                    "judge JSON parse failed for run %s; retrying with stricter prompt",
                    span.run_id,
                )
                continue
            logger.error("judge JSON parse failed twice for run %s", span.run_id)
            return _failure_result(span.run_id, "parse_error", model, start)

        return JudgeResult(
            run_id=span.run_id,
            score=parsed.score,
            reasoning=parsed.reasoning,
            model_used=model,
            latency_ms=_elapsed_ms(start),
            confidence=parsed.confidence,
        )

    # Defensive: the loop above always returns within its two attempts.
    return _failure_result(span.run_id, "judge_error", model, start)


async def _call_llm(prompt: str, model: str) -> str:
    """Send ``prompt`` to the LLM selected by ``model`` and return its text.

    Routing is by prefix: ``claude*`` uses the Anthropic async SDK, ``gpt*`` the
    OpenAI async SDK. SDKs are imported lazily so this module imports cleanly
    without credentials installed.

    Args:
        prompt: Fully rendered judge prompt.
        model: Model identifier.

    Returns:
        The model's raw text response.

    Raises:
        ValueError: If ``model`` matches neither supported prefix.
    """
    if model.startswith("claude"):
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic()
        message = await client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )

    if model.startswith("gpt"):
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    raise ValueError(f"Unsupported judge model: {model!r}")


async def _write_eval_result(result: JudgeResult) -> None:
    """Persist ``result`` as an ``EvalResult`` row, swallowing any storage error.

    Storage failures are logged and suppressed so that persistence problems
    never break the judge's never-raise contract.
    """
    try:
        async with get_session() as session:
            session.add(
                EvalResult(
                    run_id=result.run_id,
                    judge_model=result.model_used,
                    score=result.score,
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — persistence must not break the judge
        logger.error("failed to persist EvalResult for run %s", result.run_id, exc_info=True)


def _build_prompt(span: AgentSpan, rubric: str) -> str:
    """Render the judge prompt template with the span's fields and ``rubric``.

    Substitution uses ``str.replace`` (not ``str.format``) because the template
    contains a literal JSON example with braces that ``format`` would misparse.
    """
    template = _load_template()
    return (
        template.replace("{input}", _stringify(span.input))
        .replace("{output}", _stringify(span.output))
        .replace("{tool_calls_summary}", _summarize_tool_calls(span.tool_calls))
        .replace("{rubric}", rubric)
    )


@lru_cache(maxsize=1)
def _load_template() -> str:
    """Load and cache the judge prompt template from ``prompts/``."""
    return (_PROMPTS_DIR / "judge_prompt.txt").read_text(encoding="utf-8")


def _summarize_tool_calls(tool_calls: list[ToolCall]) -> str:
    """Render tool calls as a compact one-line-per-call summary.

    Each line follows ``name(k="v") → result [Nms]``; failed calls render the
    error as ``ERROR: "<msg>"``. Returns ``"(no tool calls)"`` when empty.
    """
    if not tool_calls:
        return "(no tool calls)"

    lines: list[str] = []
    for call in tool_calls:
        params = ", ".join(f"{key}={_fmt(value)}" for key, value in call.params.items())
        if call.error is not None:
            outcome = f"ERROR: {_fmt(call.error)}"
        else:
            outcome = _fmt(call.result)
        lines.append(f"{call.tool_name}({params}) → {outcome} [{int(call.duration_ms)}ms]")
    return "\n".join(lines)


def _parse_judge_json(raw: str) -> _ParsedJudgement:
    """Parse and validate a judge JSON response into a :class:`_ParsedJudgement`.

    Tolerates surrounding markdown code fences. Raises ``ValueError`` or
    ``TypeError`` (caught by the caller as a parse failure) when the text is not
    a JSON object, is missing required fields, or has non-numeric scores.
    """
    data = json.loads(_strip_code_fences(raw.strip()))
    if not isinstance(data, dict):
        raise ValueError("judge response is not a JSON object")
    if not {"score", "reasoning", "confidence"} <= data.keys():
        raise ValueError("judge response missing required fields")
    return _ParsedJudgement(
        score=_clamp(float(data["score"])),
        reasoning=str(data["reasoning"]),
        confidence=_clamp(float(data["confidence"])),
    )


def _strip_code_fences(text: str) -> str:
    """Strip a single surrounding markdown code fence, if present."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _fmt(value: object) -> str:
    """Render a tool param/result value, preferring JSON, falling back to str."""
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return str(value)


def _stringify(value: object) -> str:
    """Coerce an arbitrary span input/output payload to a prompt-safe string."""
    return value if isinstance(value, str) else _fmt(value)


def _clamp(value: float) -> float:
    """Clamp a numeric score into the inclusive ``[0.0, 1.0]`` range."""
    return max(0.0, min(1.0, value))


def _elapsed_ms(start: float) -> float:
    """Return milliseconds elapsed since the ``perf_counter`` value ``start``."""
    return (time.perf_counter() - start) * 1000.0


def _failure_result(run_id: str, reasoning: str, model: str, start: float) -> JudgeResult:
    """Build a zero-score :class:`JudgeResult` for a failed judge attempt."""
    return JudgeResult(
        run_id=run_id,
        score=0.0,
        reasoning=reasoning,
        model_used=model,
        latency_ms=_elapsed_ms(start),
        confidence=0.0,
    )
