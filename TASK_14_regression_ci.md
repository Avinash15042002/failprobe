# Task 14 — Regression CI (`agentprobe/regression/`)

**Phase:** Month 3
**Module:** `agentprobe/regression/`

---

## Goal

Implement the regression testing engine: statistical tests, test suite runner, baseline snapshotting, and optional Slack alerts. The GitHub Actions workflow (`eval.yml`) uses this to fail PRs when accuracy drops by a statistically significant margin.

---

## Files to Create

```
agentprobe/regression/
├── __init__.py
├── runner.py       ← loads YAML test suite, runs eval, compares to baseline
├── baseline.py     ← snapshot current metrics as baseline JSON
├── stats.py        ← bootstrap CI, McNemar test, p-values
└── alert.py        ← Slack/email webhook on regression
```

---

## `stats.py` — Statistical Tests

```python
def bootstrap_ci(
    data: list[bool | float],
    n_resamples: int = 1000,
    ci: float = 0.95
) -> tuple[float, float]:
    means = [np.mean(np.random.choice(data, len(data), replace=True)) for _ in range(n_resamples)]
    alpha = (1 - ci) / 2
    return (np.quantile(means, alpha), np.quantile(means, 1 - alpha))

def mcnemar_test(
    before: list[bool],
    after: list[bool],
) -> tuple[float, bool]:
    """Returns (p_value, is_significant). Significant if p < 0.05."""
    ...

def is_regression(
    baseline: float,
    current: float,
    ci: tuple[float, float],
    threshold: float = 0.05,
) -> bool:
    """True if current - baseline < -threshold AND CI lower bound < 0."""
    ...
```

**Critical rule:** Never display or trigger a regression alert unless the delta is BOTH above threshold AND statistically significant (p < 0.05). Raw deltas without significance testing are prohibited.

---

## `runner.py` — Test Suite Runner

### YAML format (`probe_tests.yml`)

```yaml
suite_name: "my-agent-eval"
agent_module: "myproject.agent"
agent_function: "run_agent"

thresholds:
  accuracy_drop_max: 0.05      # fail if accuracy drops >5%
  cost_increase_max: 0.20      # fail if cost increases >20%
  latency_p90_max_ms: 5000

cases:
  - id: "basic-weather"
    input: "What's the weather in Delhi?"
    expected_contains: ["Delhi", "temperature"]
    difficulty: "easy"

  - id: "multi-step-booking"
    input: "Book a flight from Delhi to Mumbai on June 15"
    expected_tool_calls: ["search_flights", "check_availability"]
    difficulty: "medium"
```

### Output

```python
@dataclass
class RegressionResult:
    suite_name: str
    passed: bool
    n_cases: int
    n_passed: int
    accuracy: float
    accuracy_ci: tuple[float, float]
    baseline_accuracy: Optional[float]
    accuracy_delta: Optional[float]
    accuracy_delta_significant: bool    # p < 0.05
    avg_cost_usd: float
    cost_delta_pct: Optional[float]
    failure_breakdown: dict[str, int]   # FailureType.value → count
    generated_at: datetime
```

### `--fail-on-regression` flag behaviour

- Exit code `0`: no regression
- Exit code `1`: accuracy drop > threshold AND statistically significant
- Exit code `0` + stderr warning: drop > threshold but NOT significant

---

## `baseline.py` — Baseline Snapshotting

```python
async def save_baseline(name: str, result: RegressionResult) -> None:
    """Saves metrics to RegressionBaseline table in storage."""
    ...

async def load_baseline(name: str) -> Optional[RegressionResult]:
    """Loads the most recent baseline with the given name."""
    ...
```

Default baseline name: `"main"`. Override with `--baseline-name` CLI flag.

---

## `alert.py` — Regression Alert

```python
async def send_slack_alert(
    webhook_url: str,
    result: RegressionResult,
) -> None:
    """POST a Slack webhook message. Only called when regression is detected."""
    ...
```

Slack message format:
```
🚨 AgentProbe Regression Detected
Suite: my-agent-eval
Accuracy: 87.2% → 81.4% (Δ -5.8%, p=0.031)
Cost: $0.0012 → $0.0009 (-25%)
View report: <link>
```

Alert is only sent when regression is confirmed (exit code 1). Not sent for warnings.

---

## GitHub Actions (`eval.yml`)

```yaml
name: AgentProbe Regression CI
on:
  pull_request:
    branches: [main]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --tb=short
      - run: probe run --suite probe_tests.yml --fail-on-regression
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: agentprobe_report.json
```

---

## Month 3 Deliverables

- [ ] Write 20 test cases in `probe_tests.yml` for the demo agent
- [ ] `probe run --suite probe_tests.yml` works end-to-end
- [ ] `probe baseline save --name "v1.0"` snapshots current metrics
- [ ] Re-running after a simulated regression triggers exit code 1
- [ ] GitHub Actions workflow triggers on PR and uploads the eval report artifact

---

## Acceptance Criteria

- [ ] `bootstrap_ci([True]*90 + [False]*10)` → CI close to `(0.83, 0.96)`
- [ ] `mcnemar_test` returns `is_significant=False` when both lists are identical
- [ ] `is_regression(0.90, 0.84, (0.78, 0.89), threshold=0.05)` → `True`
- [ ] `is_regression(0.90, 0.84, (0.80, 0.91), threshold=0.05)` → `False` (CI crosses 0)
- [ ] Tests in `tests/test_regression.py` all pass
