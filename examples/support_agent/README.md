# FailProbe example — deterministic support agent

A self-contained test harness that exercises FailProbe end to end **without any
LLM or API key**. `agent.py` is a mock "support agent" whose routing is fully
deterministic, so every run produces identical results — which lets the suite
deliberately drive each branch of the rule-based failure classifier.

## Files

- `agent.py` — the mock agent, instrumented with `@probe`. Tools append
  `ToolCall`s to `_probe_collector`; different inputs trigger different failures.
- `probe_tests.yml` — the regression suite (13 cases). 6 currently pass; 7
  intentionally fail, one per classifier branch.

## Setup (once)

```powershell
# From the repo root, with the project venv active:
pip install -e .
```

## Run the suite

```powershell
probe run --suite examples/support_agent/probe_tests.yml
```

Expected: 6/13 pass (46.2%) and a failure breakdown covering `tool_api_error`,
`missing_tool`, `tool_timeout`, `infinite_loop`, `refused`, `exception`, and
`task_failed`.

## Demonstrate the regression gate

```powershell
# 1. Snapshot the current (healthy) state as the "main" baseline.
probe baseline save --name main --suite examples/support_agent/probe_tests.yml

# 2. Degrade the agent and run with the gate on.
$env:FAILPROBE_DEMO_REGRESS = "1"
probe run --suite examples/support_agent/probe_tests.yml --fail-on-regression
```

The second run flips all 6 passing cases to failing. Because the drop (−46.2%)
exceeds `accuracy_drop_max` (5%) **and** McNemar's test is significant, the
build fails with **exit code 1**. The `FAILPROBE_DEMO_REGRESS` toggle is purely
a demo device for forcing a reproducible, statistically significant regression.

> Note on `refused`: the classifier's refusal check only inspects **string**
> output, so the guardrail path in `agent.py` returns a bare string rather than
> the usual dict envelope. Dict-wrapped refusals fall through to `task_failed`.

## Run the live decorator path

```powershell
python examples/support_agent/agent.py
```

Runs a few queries through `@probe` directly, recording spans to `failprobe.db`.
Start the API + dashboard (`probe dashboard`) to browse them, then
`probe report` to summarise recent runs.
