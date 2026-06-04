"""Regression alerting via Slack incoming webhooks.

Called only when a regression is *confirmed* (the runner is about to exit 1) —
never for the "above threshold but not significant" warning case. If no webhook
URL is configured the alert is skipped with a logged warning, so alerting is
strictly best-effort and never blocks or fails CI.

The webhook URL is conventionally passed from the ``AGENTPROBE_SLACK_WEBHOOK``
environment variable.
"""

import logging

import httpx

from agentprobe.regression.runner import RegressionResult

logger = logging.getLogger("agentprobe")

_HTTP_TIMEOUT_S = 10.0


def _format_message(result: RegressionResult) -> str:
    """Render the Slack message body for a confirmed regression."""
    lines = ["🚨 AgentProbe Regression Detected", f"Suite: {result.suite_name}"]

    if result.baseline_accuracy is not None and result.accuracy_delta is not None:
        sig = "significant" if result.accuracy_delta_significant else "not significant"
        lines.append(
            f"Accuracy: {result.baseline_accuracy:.1%} → {result.accuracy:.1%} "
            f"(Δ {result.accuracy_delta:+.1%}, {sig})"
        )
    else:
        lines.append(f"Accuracy: {result.accuracy:.1%}")

    if result.cost_delta_pct is not None:
        lines.append(f"Avg cost: ${result.avg_cost_usd:.4f} ({result.cost_delta_pct:+.0%})")

    if result.failure_breakdown:
        breakdown = ", ".join(
            f"{name}={count}" for name, count in sorted(result.failure_breakdown.items())
        )
        lines.append(f"Failures: {breakdown}")

    return "\n".join(lines)


async def send_slack_alert(webhook_url: str, result: RegressionResult) -> None:
    """POST a Slack message describing a confirmed regression.

    Skips silently (with a logged warning) when ``webhook_url`` is empty, so an
    unconfigured ``AGENTPROBE_SLACK_WEBHOOK`` never breaks the run. Any HTTP error
    is logged and swallowed — alerting must never fail the build.

    Args:
        webhook_url: Slack incoming-webhook URL (typically from
            ``AGENTPROBE_SLACK_WEBHOOK``).
        result: The confirmed-regression result to describe.
    """
    if not webhook_url:
        logger.warning("AGENTPROBE_SLACK_WEBHOOK not set; skipping regression alert.")
        return

    payload = {"text": _format_message(result)}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.error("Failed to send Slack regression alert", exc_info=True)
