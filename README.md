# AgentProbe

Failure classification and meta-evaluation for LLM agents.

Quickstart coming soon.

## Meta-Evaluation

AgentProbe's headline feature answers *"how accurate is your LLM judge?"* by
scoring it against a human-labelled **golden dataset** and reporting a
bootstrapped confidence interval — so you can state the result honestly, e.g.
*"my judge is 91% accurate ±4% on 100 labelled cases."*

### Building the initial golden dataset (manual milestone)

> **Status:** not yet run. Requires `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`)
> and human labelling — the steps below are reproducible; the accuracy number is
> a placeholder until the first real run.

1. Run your `@probe`-decorated demo agent enough times to collect ~50 spans.
2. For each run flagged into the review queue (judge confidence `< 0.6` or an
   ambiguous score in `[0.4, 0.6]`), open `/review` and label it pass/fail.
   Each label is appended to `agentprobe_golden.jsonl`.
   (CLI/API equivalent: `POST /review/{run_id}` with `{"label": ..., "notes": ...}`.)
3. Continue until the dataset reaches **50 manually labelled cases**.
4. Run the first meta-evaluation:

   ```bash
   probe meta-eval --golden agentprobe_golden.jsonl   # CLI (TASK 15)
   # or: GET /eval/judge-accuracy
   ```

5. Record the headline number here.

| Metric | Value |
|---|---|
| Judge accuracy | _TBD — pending first run_ |
| 95% CI | _TBD_ |
| Cases (n) | _TBD_ |

> Honesty rules (enforced in `meta_eval.py`): with `n < 10` the CI is skipped
> (`warning="too_few_cases"`); with `n < 30` it is computed but flagged
> (`warning="ci_may_be_unreliable"`).
