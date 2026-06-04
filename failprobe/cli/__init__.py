"""FailProbe command-line interface.

Exposes the Typer ``app`` referenced by the ``probe`` console-script entry point
(``pyproject.toml``: ``probe = "failprobe.cli.main:app"``). Implementation of
the individual commands lives in :mod:`failprobe.cli.main`.
"""

from failprobe.cli.main import app

__all__ = ["app"]
