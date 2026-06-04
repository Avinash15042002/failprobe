"""Evaluator public API: LLM-as-Judge, meta-evaluation, and golden dataset.

Exports the judge entry point, the meta-evaluation runner and report, the
golden-dataset manager, and the low-confidence review flag. Implementation
details (prompt rendering, model routing, serialization, persistence) stay
private to their modules.
"""

from failprobe.evaluator.confidence import CONFIDENCE_THRESHOLD, should_flag_for_review
from failprobe.evaluator.golden_dataset import DEFAULT_GOLDEN_PATH, GoldenDatasetManager
from failprobe.evaluator.judge import JudgeResult, judge_run
from failprobe.evaluator.meta_eval import MetaEvalReport, default_rubric, run_meta_eval

__all__ = [
    "CONFIDENCE_THRESHOLD",
    "DEFAULT_GOLDEN_PATH",
    "GoldenDatasetManager",
    "JudgeResult",
    "MetaEvalReport",
    "default_rubric",
    "judge_run",
    "run_meta_eval",
    "should_flag_for_review",
]
