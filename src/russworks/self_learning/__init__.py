"""Self-learning recommendation layer exports."""

from russworks.self_learning.engine import SelfLearningEngine, build_self_learning_report
from russworks.self_learning.models import (
    LearningInsight,
    LearningObservation,
    LearningRecommendation,
    LearningRecommendationType,
    LearningSummary,
    SelfLearningReport,
)

__all__ = [
    "LearningInsight",
    "LearningObservation",
    "LearningRecommendation",
    "LearningRecommendationType",
    "LearningSummary",
    "SelfLearningEngine",
    "SelfLearningReport",
    "build_self_learning_report",
]
