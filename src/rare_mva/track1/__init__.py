"""Track 1 submission validation and public-compatible scoring."""

from rare_mva.track1.builder import BuilderError, build_track1
from rare_mva.track1.schema import (
    Candidate,
    GroundTruth,
    Submission,
    ValidationError,
    Variant,
    load_ground_truth,
    load_submission,
)
from rare_mva.track1.scoring import ScoreResult, score_submission

__all__ = [
    "Candidate",
    "BuilderError",
    "GroundTruth",
    "ScoreResult",
    "Submission",
    "ValidationError",
    "Variant",
    "build_track1",
    "load_ground_truth",
    "load_submission",
    "score_submission",
]
