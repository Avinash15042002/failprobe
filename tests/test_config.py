"""Tests for the FailProbe configuration singleton."""

import failprobe
from failprobe import ProbeConfig
from failprobe._internal import configure as internal_configure
from failprobe._internal import get_config as internal_get_config
from failprobe.config import configure, get_config


def test_default_instantiation_no_args() -> None:
    """ProbeConfig instantiates with all defaults and no arguments."""
    cfg = ProbeConfig()
    assert cfg.db_url == "sqlite+aiosqlite:///failprobe.db"
    assert cfg.api_url is None
    assert cfg.judge_model == "heuristic"
    assert cfg.judge_base_url is None
    assert cfg.judge_api_key is None
    assert cfg.judge_timeout == 30.0
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
    ``failprobe.config`` / ``failprobe._internal``, not the top-level package.
    """
    assert failprobe.ProbeConfig is ProbeConfig
    assert failprobe.configure is configure
    assert not hasattr(failprobe, "get_config")
    failprobe.configure(ProbeConfig(judge_timeout=2.5))
    assert get_config().judge_timeout == 2.5


def test_internal_path_shares_singleton() -> None:
    """failprobe._internal and failprobe.config operate on one singleton."""
    internal_configure(ProbeConfig(loop_threshold=7))
    assert get_config().loop_threshold == 7
    assert internal_get_config().loop_threshold == 7
