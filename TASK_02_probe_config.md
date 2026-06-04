# Task 02 — `ProbeConfig` Dataclass (`agentprobe/config.py`)

**Phase:** Month 1, Week 4
**Module:** `agentprobe/config.py`

---

## Goal

Implement the global configuration singleton that every other module reads from. Zero config must work out of the box; users can optionally override via `agentprobe.configure(ProbeConfig(...))`.

---

## Implementation

### `agentprobe/config.py`

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ProbeConfig:
    db_url: str = "sqlite+aiosqlite:///agentprobe.db"
    api_url: Optional[str] = None        # if set, spans are POSTed to remote API
    judge_model: str = "claude-haiku-4"
    judge_timeout: float = 10.0          # seconds per judge call
    loop_threshold: int = 3              # repeated calls before INFINITE_LOOP fires
    token_overflow_threshold: int = 120_000
    emit_console: bool = True
    tags: dict = field(default_factory=dict)  # default tags added to every run
```

### `agentprobe/__init__.py` additions

```python
_config: ProbeConfig = ProbeConfig()

def configure(config: ProbeConfig) -> None:
    global _config
    _config = config

def get_config() -> ProbeConfig:
    return _config
```

---

## Rules

- `ProbeConfig` is a **process-level singleton**. Call `configure()` once before using `@probe`.
- All defaults must work with zero user configuration — no env vars, no files required.
- Env var overrides are optional convenience (handled separately in Task 14); the dataclass defaults are canonical.
- `get_config()` is the only way other modules should access the config — no direct import of `_config`.

---

## Public API export

Add to `agentprobe/__init__.py`:

```python
from agentprobe.config import ProbeConfig
from agentprobe._internal import configure, get_config
```

---

## Acceptance Criteria

- [ ] `from agentprobe import ProbeConfig` works
- [ ] `ProbeConfig()` instantiates with all defaults, no arguments needed
- [ ] `agentprobe.configure(ProbeConfig(loop_threshold=5))` updates the singleton
- [ ] `agentprobe.get_config().loop_threshold` returns `5` after the above
- [ ] A second `configure()` call overwrites the previous config
