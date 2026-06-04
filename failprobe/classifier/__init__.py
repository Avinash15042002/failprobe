"""Rule-based failure classification for FailProbe.

Public API for the classifier layer. Implementation lives in submodules;
only the names listed in ``__all__`` are part of the supported interface.
"""

from failprobe.classifier.classifier import FailureClassifier
from failprobe.classifier.taxonomy import FAILURE_DESCRIPTIONS, FailureType

__all__ = ["FailureType", "FAILURE_DESCRIPTIONS", "FailureClassifier"]
