"""LLM-as-Judge: score an agent run against a rubric.

This module owns the evaluator's LLM-judge concern only (spec §5.5). The public
entry point is :func:`judge_run`, which **always** returns a :class:`JudgeResult`
and never raises — every failure (network, timeout, malformed response) is
caught, logged to stderr, and converted into a result with ``score=0.0``.

Judge-engine routing by model identifier:

* ``"heuristic"`` (the default) → a free, offline, pure-Python judge that makes
  **no LLM or network calls and needs no API key**. Ideal for anyone who wants
  meta-evaluation without paying for a model.
* ``claude*`` → Anthropic SDK.
* anything else (``gpt*``, ``llama*``, ``qwen*``, …) → an **OpenAI-compatible**
  endpoint. With ``ProbeConfig.judge_base_url`` (or ``FAILPROBE_JUDGE_BASE_URL``)
  this points at any local/self-hosted LLM such as Ollama, vLLM, or LM Studio;
  with it unset it uses OpenAI's API. So no provider is ever required.

SDKs are imported lazily inside :func:`_call_llm` so importing this module never
requires API credentials.

Per the layer-ownership rules, this module may read configuration and persist to
storage (writing ``EvalResult`` rows) but must not perform span capture or
failure classification.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from failprobe.config import get_config
from failprobe.models import AgentSpan, ToolCall
from failprobe.storage.db import get_session
from failprobe.storage.models import EvalResult

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
    model: str = "heuristic",
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
        model: Judge engine. ``"heuristic"`` (default) scores offline with no
            LLM; ``claude*`` routes to Anthropic; anything else routes to an
            OpenAI-compatible endpoint (configurable via ``judge_base_url``).

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
    if model == "heuristic":
        parsed = _heuristic_judge(span)
        return JudgeResult(
            run_id=span.run_id,
            score=parsed.score,
            reasoning=parsed.reasoning,
            model_used="heuristic",
            latency_ms=_elapsed_ms(start),
            confidence=parsed.confidence,
        )

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

    ``claude*`` uses the Anthropic async SDK. Every other model uses the OpenAI
    **async SDK pointed at an OpenAI-compatible endpoint** — OpenAI by default,
    or any local/self-hosted server (Ollama, vLLM, LM Studio, …) when
    ``judge_base_url`` / ``FAILPROBE_JUDGE_BASE_URL`` is set. This is what lets
    the judge run on a free local model with no paid API. SDKs are imported
    lazily so this module imports cleanly without credentials installed.

    Args:
        prompt: Fully rendered judge prompt.
        model: Model identifier (``"heuristic"`` is handled before this call).

    Returns:
        The model's raw text response.
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

    # OpenAI-compatible path: OpenAI, or any local/self-hosted endpoint.
    from openai import AsyncOpenAI

    config = get_config()
    base_url = config.judge_base_url or os.environ.get("FAILPROBE_JUDGE_BASE_URL")
    # Local servers (e.g. Ollama) ignore the key but the SDK requires a non-empty
    # value, so fall back to a harmless placeholder.
    api_key = (
        config.judge_api_key
        or os.environ.get("FAILPROBE_JUDGE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "not-needed"
    )
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


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


# --------------------------------------------------------------------------- #
# Heuristic judge — free, offline, no LLM and no API key
# --------------------------------------------------------------------------- #

# Phrases signalling the agent refused or could not help.
_REFUSAL_MARKERS = (
    "i cannot",
    "i can't",
    "i can not",
    "i'm unable",
    "i am unable",
    "i'm not able",
    "i am not able",
    "cannot help",
    "can't help",
    "unable to assist",
    "cannot assist",
    "as an ai",
)
# Phrases signalling an error/exception leaked into the output.
_ERROR_MARKERS = ("traceback (most recent call last)", "exception:", "error:", "stack trace")
# Common words ignored when measuring input/output relevance overlap.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is",
        "are", "was", "were", "be", "with", "what", "which", "how", "do",
        "does", "did", "this", "that", "it", "as", "at", "by", "from", "your",
        "you", "me", "please", "can", "could", "would",
    }
)


def _tokens(text: str) -> set[str]:
    """Return lowercase word tokens of ``text``, dropping stopwords and 1-char tokens."""
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _heuristic_judge(span: AgentSpan) -> _ParsedJudgement:
    """Score a run offline with rule-based text signals — no LLM, no API key.

    A free, deterministic baseline judge: failed runs and empty / error /
    refusal outputs score low; otherwise the score reflects how relevant the
    output is to the input (token overlap). ``confidence`` is moderate to signal
    that this is a heuristic rather than a semantic model. Never raises.
    """
    output = _stringify(span.output).strip()
    lowered = output.lower()

    if span.success is False or span.failure_type:
        reason = span.failure_type or "run marked unsuccessful"
        return _ParsedJudgement(0.15, f"heuristic: failed run ({reason})", 0.6)
    if not output:
        return _ParsedJudgement(0.0, "heuristic: empty output", 0.6)
    if any(marker in lowered for marker in _ERROR_MARKERS):
        return _ParsedJudgement(0.1, "heuristic: output looks like an error", 0.5)
    if any(marker in lowered for marker in _REFUSAL_MARKERS):
        return _ParsedJudgement(0.2, "heuristic: output looks like a refusal", 0.5)

    input_tokens = _tokens(_stringify(span.input))
    output_tokens = _tokens(output)
    overlap = (len(input_tokens & output_tokens) / len(input_tokens)) if input_tokens else 0.5
    length_factor = 1.0 if len(output) >= 8 else 0.6
    score = _clamp((0.55 + 0.35 * overlap) * length_factor)
    return _ParsedJudgement(score, f"heuristic: relevant output (overlap={overlap:.2f})", 0.5)
