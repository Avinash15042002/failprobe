"""Rule-based failure classification for AgentProbe.

Public API for the classifier layer. Implementation lives in submodules;
only the names listed in ``__all__`` are part of the supported interface.
"""

from agentprobe.classifier.classifier import FailureClassifier
from agentprobe.classifier.taxonomy import FAILURE_DESCRIPTIONS, FailureType

__all__ = ["FailureType", "FAILURE_DESCRIPTIONS", "FailureClassifier"]
