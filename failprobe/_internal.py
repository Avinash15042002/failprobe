"""Internal access points for FailProbe's configuration singleton.

Re-exports :func:`configure` and :func:`get_config` from
:mod:`failprobe.config` so they can be imported from a stable internal path.
"""

from failprobe.config import configure, get_config

__all__ = ["configure", "get_config"]
