"""AgentProbe — failure classification and meta-evaluation for LLM agents."""

from agentprobe.config import ProbeConfig, configure
from agentprobe.decorator import probe

__version__ = "0.1.0"

__all__ = ["probe", "ProbeConfig", "configure"]
