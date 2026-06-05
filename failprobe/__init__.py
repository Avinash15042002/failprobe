"""FailProbe — failure classification and meta-evaluation for LLM agents."""

from failprobe.config import ProbeConfig, configure
from failprobe.decorator import probe

__version__ = "0.3.0"

__all__ = ["probe", "ProbeConfig", "configure"]
