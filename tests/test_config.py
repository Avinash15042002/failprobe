"""Tests for the AgentProbe configuration singleton."""

import agentprobe
from agentprobe import ProbeConfig
from agentprobe._internal import configure as internal_configure
from agentprobe._internal import get_config as internal_get_config
from agentprobe.config import configure, get_config


def test_default_instantiation_no_args() -> None:
    """ProbeConfig instantiates with all defaults and no arguments."""
    cfg = ProbeConfig()
    assert cfg.db_url == "sqlite+aiosqlite:///agentprobe.db"
    assert cfg.api_url is None
    assert cfg.judge_model == "claude-haiku-4"
    assert cfg.judge_timeout == 10.0
    assert cfg.loop_threshold == 3
    assert cfg.token_overflow_threshold == 120_000
    assert cfg.emit_console is True
    assert cfg.tags == {}


def test_tags_default_is_independent() -> None:
    """The default tags dict is not shared between instances."""
    a = ProbeConfig()
    b = ProbeConfig()
    a.tags["x"] = 1
    assert b.tags == {}


def test_configure_updates_singleton() -> None:
    """configure() installs a new config that get_config() returns."""
    configure(ProbeConfig(loop_threshold=5))
    assert get_config().loop_threshold == 5


def test_second_configure_overwrites() -> None:
    """A later configure() call overwrites the previous one."""
    configure(ProbeConfig(loop_threshold=5))
    configure(ProbeConfig(loop_threshold=9))
    assert get_config().loop_threshold == 9


def test_public_api_exports() -> None:
    """Top-level package exports ProbeConfig and configure (not get_config).

    Per TASK 07, the public surface is exactly ``probe``, ``ProbeConfig``,
    ``configure``. ``get_config`` is an internal accessor reached via
    ``agentprobe.config`` / ``agentprobe._internal``, not the top-level package.
    """
    assert agentprobe.ProbeConfig is ProbeConfig
    assert agentprobe.configure is configure
    assert not hasattr(agentprobe, "get_config")
    agentprobe.configure(ProbeConfig(judge_timeout=2.5))
    assert get_config().judge_timeout == 2.5


def test_internal_path_shares_singleton() -> None:
    """agentprobe._internal and agentprobe.config operate on one singleton."""
    internal_configure(ProbeConfig(loop_threshold=7))
    assert get_config().loop_threshold == 7
    assert internal_get_config().loop_threshold == 7
