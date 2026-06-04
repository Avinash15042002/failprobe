"""Regression layer public API.

Exposes the statistical primitives, baseline persistence, the suite runner, and
Slack alerting. This layer owns statistics, the CI runner, and baselines — it
never captures spans or runs evaluations (those belong to other layers).
"""

from agentprobe.regression.alert import send_slack_alert
from agentprobe.regression.baseline import (
    DEFAULT_BASELINE_NAME,
    list_baselines,
    load_baseline,
    save_baseline,
)
from agentprobe.regression.runner import (
    COST_PER_1K_TOKENS,
    RegressionResult,
    run_suite,
    snapshot_baseline,
    write_report,
)
from agentprobe.regression.stats import bootstrap_ci, is_regression, mcnemar_test

__all__ = [
    "COST_PER_1K_TOKENS",
    "DEFAULT_BASELINE_NAME",
    "RegressionResult",
    "bootstrap_ci",
    "is_regression",
    "list_baselines",
    "load_baseline",
    "mcnemar_test",
    "run_suite",
    "save_baseline",
    "send_slack_alert",
    "snapshot_baseline",
    "write_report",
]
