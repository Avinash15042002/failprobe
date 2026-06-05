"""Global configuration for FailProbe.

Holds the :class:`ProbeConfig` dataclass and the process-level singleton that
every other module reads from via :func:`get_config`. Zero configuration works
out of the box; users may override once via :func:`configure`.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProbeConfig:
    """Process-level configuration for FailProbe.

    Every field has a default, so ``ProbeConfig()`` is valid with no arguments
    and represents the canonical zero-config setup.

    Attributes:
        db_url: SQLAlchemy async database URL where spans are persisted.
        api_url: If set, spans are POSTed to a remote API instead of stored
            locally. ``None`` means local storage.
        judge_model: Identifier selecting the meta-eval judge engine. The
            default ``"heuristic"`` is a free, offline, pure-Python judge (no
            LLM, no API key). ``claude*`` routes to the Anthropic SDK; any other
            value routes to an OpenAI-compatible endpoint (OpenAI by default, or
            a local/self-hosted LLM via ``judge_base_url`` — e.g. Ollama).
        judge_base_url: Base URL of an OpenAI-compatible LLM endpoint used for
            non-``claude`` / non-``heuristic`` judges (e.g.
            ``"http://localhost:11434/v1"`` for Ollama). ``None`` uses OpenAI's
            default endpoint. Overridable via ``FAILPROBE_JUDGE_BASE_URL``.
        judge_api_key: API key for the OpenAI-compatible judge endpoint. For
            local servers (Ollama) any non-empty value works. Falls back to
            ``FAILPROBE_JUDGE_API_KEY`` then ``OPENAI_API_KEY``.
        judge_timeout: Maximum seconds to wait for a single judge call.
        loop_threshold: Number of repeated tool calls before ``INFINITE_LOOP``
            fires in the classifier.
        token_overflow_threshold: Token count above which token-overflow
            failures are flagged.
        emit_console: Whether spans are echoed to the console.
        tags: Default tags merged into every recorded run.
    """

    db_url: str = "sqlite+aiosqlite:///failprobe.db"
    api_url: Optional[str] = None
    judge_model: str = "heuristic"
    judge_base_url: Optional[str] = None
    judge_api_key: Optional[str] = None
    judge_timeout: float = 30.0
    loop_threshold: int = 3
    token_overflow_threshold: int = 120_000
    emit_console: bool = True
    tags: dict = field(default_factory=dict)


_config: ProbeConfig = ProbeConfig()


def configure(config: ProbeConfig) -> None:
    """Replace the process-level configuration singleton.

    Call once before using ``@probe``. A later call overwrites the previous
    configuration.

    Args:
        config: The configuration to install as the active singleton.
    """
    global _config
    _config = config


def get_config() -> ProbeConfig:
    """Return the active configuration singleton.

    This is the only supported way for other modules to read configuration;
    do not import ``_config`` directly.

    Returns:
        The currently configured :class:`ProbeConfig`.
    """
    return _config
