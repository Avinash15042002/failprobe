"""AgentProbe command-line interface.

Exposes the Typer ``app`` referenced by the ``probe`` console-script entry point
(``pyproject.toml``: ``probe = "agentprobe.cli.main:app"``). Implementation of
the individual commands lives in :mod:`agentprobe.cli.main`.
"""

from agentprobe.cli.main import app

__all__ = ["app"]
