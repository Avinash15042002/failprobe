"""A deterministic demo weather/booking agent for the regression suite.

This is the ``agent_module`` referenced by ``probe_tests.yml``. Unlike
``tests/demo_agent.py`` (which runs an event loop at import time), this module
has **no import-time side effects** so the regression runner can import it
safely with ``importlib.import_module``.

The agent is intentionally rule-based and deterministic: identical input always
produces identical output and the same tool-call sequence. That determinism is
what lets the suite be a stable regression baseline — re-running it against its
own baseline must show zero change.

Tool calls are recorded through the ``@probe`` decorator's opt-in
``_probe_collector`` parameter, so the runner (and the dashboard) can inspect
which tools the agent invoked.
"""

import time
from typing import Any, Optional

from agentprobe import probe
from agentprobe.models import ToolCall

# Tiny canned knowledge bases — enough to make the demo answers concrete.
_WEATHER = {
    "delhi": "32°C and sunny",
    "mumbai": "29°C and humid",
    "london": "14°C and rainy",
    "tokyo": "21°C and clear",
}
_KNOWN_CITIES = set(_WEATHER) | {"paris", "new york", "san francisco"}


def _record(
    collector: Optional[list],
    tool_name: str,
    params: dict,
    result: Any,
    error: Optional[str] = None,
) -> None:
    """Append a :class:`ToolCall` to the probe collector when one is present."""
    if collector is None:
        return
    collector.append(
        ToolCall(
            tool_name=tool_name,
            params=params,
            result=result,
            duration_ms=0.0,
            error=error,
            timestamp=time.time(),
        )
    )


def _extract_city(query: str) -> str:
    """Return the first known city mentioned in ``query``, else ``"unknown"``."""
    lowered = query.lower()
    for city in _KNOWN_CITIES:
        if city in lowered:
            return city
    return "unknown"


@probe(name="weather-booking-agent")
async def run_agent(query: str, _probe_collector: Optional[list] = None) -> str:
    """Answer a weather or travel-booking query and record the tools used.

    Routing is keyword-based and deterministic:

    * weather questions  → ``get_weather``
    * flight bookings    → ``search_flights`` then ``check_availability``
    * hotel bookings     → ``book_hotel``
    * anything else      → a refusal (no tool call), which the suite uses as the
      "wrong tool / adversarial" negative path.

    Args:
        query: The natural-language user request.
        _probe_collector: Injected by ``@probe`` when present; receives the
            :class:`ToolCall` records for this run.

    Returns:
        A natural-language answer string.
    """
    q = query.lower()

    if "weather" in q or "temperature" in q:
        city = _extract_city(query)
        report = _WEATHER.get(city)
        if report is None:
            _record(
                _probe_collector,
                "get_weather",
                {"city": city},
                None,
                error="unknown_city",
            )
            return f"I don't have weather data for {city}."
        _record(_probe_collector, "get_weather", {"city": city}, report)
        return f"The weather in {city.title()} is {report} (temperature included)."

    if "flight" in q or ("book" in q and "to" in q and "hotel" not in q):
        _record(
            _probe_collector,
            "search_flights",
            {"query": query},
            ["AI-202", "AI-440"],
        )
        _record(
            _probe_collector,
            "check_availability",
            {"flight": "AI-202"},
            "available",
        )
        return "Found flights AI-202 and AI-440; AI-202 is available to book."

    if "hotel" in q:
        city = _extract_city(query)
        _record(_probe_collector, "book_hotel", {"city": city}, "confirmed")
        return f"Booked a hotel in {city.title()}; confirmation sent."

    # No tool fits — refuse rather than hallucinate a tool call.
    return "I can only help with weather and travel bookings."
