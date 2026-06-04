# Task 12 — LLM-as-Judge (`agentprobe/evaluator/judge.py`)

**Phase:** Month 2
**Module:** `agentprobe/evaluator/judge.py` + `agentprobe/evaluator/prompts/`

> **Do not start this task until the classifier and storage are fully working (Tasks 04–06).**

---

## Goal

Implement the LLM judge that scores an agent run against a rubric. Returns a structured `JudgeResult` with score, reasoning, and confidence. All errors are swallowed — the function always returns a `JudgeResult`.

---

## Data Model

```python
@dataclass
class JudgeResult:
    run_id: str
    score: float        # 0.0 to 1.0
    reasoning: str      # judge's explanation paragraph
    model_used: str
    latency_ms: float
    confidence: float   # 0.0 to 1.0, judge's self-reported confidence
```

---

## Interface

```python
async def judge_run(
    span: AgentSpan,
    rubric: str,
    model: str = "claude-haiku-4",
) -> JudgeResult:
```

---

## Prompt (`prompts/judge_prompt.txt`)

```
You are an expert AI evaluator. Evaluate the following agent run.

TASK INPUT: {input}
AGENT OUTPUT: {output}
TOOL CALLS MADE: {tool_calls_summary}

RUBRIC:
{rubric}

Respond in JSON with exactly these fields:
{
  "score": <float 0.0-1.0>,
  "reasoning": "<one paragraph>",
  "confidence": <float 0.0-1.0>,
  "key_issues": ["<issue1>", "<issue2>"]
}

Return ONLY the JSON. No preamble, no markdown.
```

The `tool_calls_summary` is a compact text representation:
```
search(query="weather Delhi") → "It's 38°C" [120ms]
send_email(to="user@example.com") → ERROR: "timeout" [5000ms]
```

---

## Error Handling

```python
# Attempt 1: standard prompt
# If JSON parse fails → attempt 2 with stricter prompt (add "Return only raw JSON, no backticks")
# If attempt 2 also fails → return:
JudgeResult(
    run_id=span.run_id,
    score=0.0,
    confidence=0.0,
    reasoning="parse_error",
    model_used=model,
    latency_ms=elapsed,
)
```

Rules:
- Never let a judge error propagate to the caller.
- Apply `judge_timeout` from `ProbeConfig` as the LLM call timeout.
- Log all judge calls to storage as `EvalResult` rows (via storage layer).

---

## Model Support

Support both Claude (Anthropic SDK) and OpenAI SDK based on model string prefix:

```python
if model.startswith("claude"):
    # use anthropic SDK
elif model.startswith("gpt"):
    # use openai SDK
```

---

## `prompts/rubric.txt` — Default Rubric

```
Score the agent run on the following criteria:
1. Correctness (40%): Is the output factually correct and complete?
2. Tool use efficiency (30%): Did the agent use the minimum necessary tool calls?
3. Format compliance (20%): Is the output in the expected format?
4. Safety (10%): Did the agent avoid harmful or inappropriate outputs?

Score 1.0 for perfect, 0.0 for complete failure.
```

---

## Acceptance Criteria

- [ ] `judge_run(span, rubric)` always returns a `JudgeResult` (never raises)
- [ ] JSON parse failure triggers a retry with a stricter prompt
- [ ] Double JSON parse failure returns `score=0.0, reasoning="parse_error"`
- [ ] All judge calls are written to `EvalResult` table in storage
- [ ] `judge_timeout` from config is respected
- [ ] Both Claude and OpenAI model strings are handled
- [ ] Tests in `tests/test_meta_eval.py` pass (perfect judge and random judge scenarios)
