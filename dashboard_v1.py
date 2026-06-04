"""AgentProbe Streamlit dashboard (v1, temporary).

A single-file Streamlit app that visualises run history and failure breakdowns
by polling the local AgentProbe REST API. This is the Month 1 throwaway; it will
be removed once the Next.js dashboard (Task 11) ships. It performs no direct
database access — every datum comes from the HTTP API.

Run with::

    uvicorn api.main:app          # in one terminal
    streamlit run dashboard_v1.py # in another
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
import pandas as pd
import streamlit as st

API_BASE = "http://localhost:8000"
_TIMEOUT_SECONDS = 5.0


class APIUnreachable(Exception):
    """Raised when the AgentProbe API cannot be reached or returns an error."""


@st.cache_data(ttl=5)
def _get(path: str) -> dict:
    """GET ``path`` from the API and return its parsed JSON body.

    Results are cached for 5 seconds so the dashboard refreshes roughly every
    five seconds without hammering the API. Connection and HTTP errors are
    re-raised as :class:`APIUnreachable` so callers can render a friendly
    message instead of a traceback.
    """
    try:
        response = httpx.get(f"{API_BASE}{path}", timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise APIUnreachable(str(exc)) from exc


def _runs_query(agent_name: str, status: str, limit: int = 100) -> str:
    """Build the ``/runs`` query path from the sidebar filter selections."""
    params: dict[str, object] = {"limit": limit}
    if agent_name.strip():
        params["agent_name"] = agent_name.strip()
    if status == "Pass":
        params["success"] = "true"
    elif status == "Fail":
        params["success"] = "false"
    return f"/runs?{urlencode(params)}"


def _run_history_section(runs: list[dict]) -> None:
    """Render Section 1: the run history table."""
    st.subheader("Run History")
    if not runs:
        st.info("No runs recorded yet.")
        return
    table = [
        {
            "agent_name": run["agent_name"],
            "status": "✓" if run["success"] else "✗",
            "failure_type": run["failure_type"] or "",
            "duration_ms": round(run["duration_ms"], 1),
            "tokens_used": run["tokens_used"],
            "created_at": run["created_at"],
        }
        for run in runs
    ]
    st.dataframe(pd.DataFrame(table), hide_index=True)


def _failure_breakdown_section(taxonomy: dict) -> None:
    """Render Section 2: the failure-type bar chart and top-3 metric cards."""
    st.subheader("Failure Breakdown")
    breakdown: dict[str, dict] = taxonomy["breakdown"]
    nonzero = {key: info for key, info in breakdown.items() if info["count"] > 0}
    if not nonzero:
        st.info("No failures recorded yet.")
        return

    ranked = sorted(nonzero.items(), key=lambda item: item[1]["count"], reverse=True)
    chart_df = pd.DataFrame(
        {"count": [info["count"] for _, info in ranked]},
        index=[name for name, _ in ranked],
    )
    st.bar_chart(chart_df)

    columns = st.columns(3)
    for column, (failure_type, info) in zip(columns, ranked[:3]):
        column.metric(
            label=failure_type,
            value=info["count"],
            help=f"{info['pct']}% of failures — {info['description']}",
        )


def _run_detail_section(runs: list[dict], breakdown: dict[str, dict]) -> None:
    """Render Section 3: the expandable detail view for a selected run."""
    with st.expander("Run Detail", expanded=False):
        if not runs:
            st.info("No runs to inspect.")
            return

        labels = {f"{run['agent_name']} — {run['id']}": run["id"] for run in runs}
        choice = st.selectbox("Select a run", options=list(labels))
        run_id = labels[choice]

        try:
            detail = _get(f"/runs/{run_id}")
        except APIUnreachable:
            st.error(f"API not reachable at {API_BASE}")
            return

        run = detail["run"]
        if run["success"]:
            st.success("✓ Success")
        else:
            failure_type = run["failure_type"] or "unknown"
            st.error(f"✗ {failure_type}")
            explanation = breakdown.get(failure_type, {}).get("description", "")
            if explanation:
                st.caption(explanation)

        st.markdown("**Input**")
        st.text(run["input_text"])
        st.markdown("**Output**")
        st.text(run["output_text"] or "")

        st.markdown("**Tool Calls**")
        tool_calls = detail["tool_calls"]
        if not tool_calls:
            st.caption("No tool calls for this run.")
            return
        tc_table = [
            {
                "tool_name": call["tool_name"],
                "params": json.dumps(call["params"]),
                "result": call["result"],
                "error": call["error"],
            }
            for call in tool_calls
        ]
        st.dataframe(pd.DataFrame(tc_table), hide_index=True)


def main() -> None:
    """Compose the dashboard: sidebar filters plus the three sections."""
    st.set_page_config(page_title="AgentProbe — Run Monitor", layout="wide")
    st.title("AgentProbe — Run Monitor")

    st.sidebar.header("Filters")
    agent_name = st.sidebar.text_input("Agent name", value="")
    status = st.sidebar.selectbox("Status", options=["All", "Pass", "Fail"])

    try:
        runs_payload = _get(_runs_query(agent_name, status))
        taxonomy = _get("/failures/taxonomy")
    except APIUnreachable:
        st.error(f"API not reachable at {API_BASE}")
        st.stop()

    runs = runs_payload["runs"]
    _run_history_section(runs)
    _failure_breakdown_section(taxonomy)
    _run_detail_section(runs, taxonomy["breakdown"])


main()
