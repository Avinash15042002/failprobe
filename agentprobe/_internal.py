"""Internal access points for AgentProbe's configuration singleton.

Re-exports :func:`configure` and :func:`get_config` from
:mod:`agentprobe.config` so they can be imported from a stable internal path.
"""

from agentprobe.config import configure, get_config

__all__ = ["configure", "get_config"]
