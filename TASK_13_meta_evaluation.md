# Task 13 — Meta-Evaluation & Golden Dataset (`agentprobe/evaluator/`)

**Phase:** Month 2
**Module:** `agentprobe/evaluator/meta_eval.py` + `golden_dataset.py` + `confidence.py`

> **The most important feature. Build it properly.**

---

## Goal

Answer: *"How accurate is your LLM judge?"* Score the judge against a human-labelled golden dataset using bootstrapped confidence intervals. The headline number should be displayable as: **"My judge is 91% accurate ±4% on 100 labelled cases."**

---

## Files to Create

```
agentprobe/evaluator/
├── meta_eval.py         ← MetaEvalReport, run_meta_eval()
├── golden_dataset.py    ← GoldenCase, GoldenDatasetManager
└── confidence.py        ← low-confidence flagging for human review
```

---

## `meta_eval.py`

### Output Model

```python
@dataclass
class MetaEvalReport:
    judge_accuracy: float                       # % of golden cases correctly scored
    precision: float
    recall: float
    f1: float
    confidence_interval: tuple[float, float]    # 95% bootstrap CI
    n_cases: int
    n_correct: int
    disagreement_rate: float                    # % where judge ≠ human
    generated_at: datetime
```

### Interface

```python
async def run_meta_eval(
    golden_dataset: list[GoldenCase],
    judge_model: str,
    threshold: float = 0.5,     # score >= threshold = "pass"
) -> MetaEvalReport:
```

### Algorithm

1. For each `GoldenCase`, call `judge_run(case.span, rubric)`
2. Convert `JudgeResult.score >= threshold` → predicted label (bool)
3. Compare against `GoldenCase.human_label`
4. Compute precision, recall, F1 (treating `True` as the positive class)
5. Compute 95% bootstrap CI on accuracy (1000 resamples) using `bootstrap_ci()` from `regression/stats.py`
6. Return `MetaEvalReport`

---

## `golden_dataset.py`

### Interface

```python
class GoldenDatasetManager:
    def load(self, path: str) -> list[GoldenCase]: ...
    def save(self, cases: list[GoldenCase], path: str) -> None: ...
    def add_case(self, case: GoldenCase) -> None: ...
    def get_stats(self) -> dict: ...
    # Returns: { n_cases, pass_rate, difficulty_distribution }
```

### Storage format

JSONL file (one `GoldenCase` JSON per line). Default path: `agentprobe_golden.jsonl` in the working directory.

```jsonl
{"id": "...", "span": {...}, "human_label": true, "human_notes": "clearly correct", "difficulty": "easy", ...}
{"id": "...", "span": {...}, "human_label": false, "human_notes": "wrong city mentioned", "difficulty": "medium", ...}
```

### Month 2 milestone

Build an initial golden dataset of **50 manually labelled cases** using the demo agent. Run the first meta-eval and document the accuracy number in `README.md`.

---

## `confidence.py` — Low-Confidence Flagging

```python
CONFIDENCE_THRESHOLD = 0.6

def flag_for_review(result: JudgeResult) -> bool:
    """
    Returns True if this run should be added to the human review queue.
    Conditions:
    - JudgeResult.confidence < CONFIDENCE_THRESHOLD, OR
    - run was previously judged and new score differs by > 0.3
    """
```

Flagged runs are written to a `review_queue` table (or a JSON sidecar file) and surfaced via `GET /review/queue`.

---

## Acceptance Criteria

- [ ] `run_meta_eval(golden_dataset, model)` correctly computes accuracy, precision, recall, F1
- [ ] A judge that always agrees with humans → `judge_accuracy = 1.0`, CI = `(1.0, 1.0)`
- [ ] A judge at chance level → `judge_accuracy ≈ 0.5`, CI contains 0.5
- [ ] More cases → narrower CI (test this relationship)
- [ ] `GoldenDatasetManager.load()` and `.save()` round-trip a list of cases without data loss
- [ ] `flag_for_review(result)` returns `True` when confidence < 0.6
- [ ] `n_cases < 30` emits a warning in the `MetaEvalReport` (add a `warning: Optional[str]` field)
