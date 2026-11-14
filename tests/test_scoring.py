"""Synthetic-only tests for public-compatible Track 1 scoring."""

from __future__ import annotations

import pytest

from rare_mva.track1.schema import Candidate, Submission, Variant
from rare_mva.track1.scoring import score_submission


OFFICIAL_SPACE_HEAD_COMMIT = "d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d"
OFFICIAL_EVALUATION_LAST_MODIFIED_COMMIT = (
    "37e25dceda63ecec7c5b2ebeffd1ea0052ad886e"
)
OFFICIAL_EVALUATION_CANONICAL_SHA256 = (
    "6d18b581e65a45e1ccc120071d588e740c2e42e983ff50704c60a40232b19180"
)


def _variant(number: int) -> Variant:
    return Variant(chrom="chr1", pos=number, ref="A", alt="T")


def _candidate(
    *variants: Variant, epcr: float, finding_type: str = "primary"
) -> Candidate:
    return Candidate(
        variants=tuple(variants),
        epcr=epcr,
        finding_type=finding_type,
        notes="SYNTHETIC ONLY",
    )


@pytest.mark.parametrize(
    ("rank", "expected_points"),
    [(1, 100.0), (2, 50.0), (3, 50.0), (4, 25.0), (5, 25.0), (6, 10.0), (10, 10.0)],
)
def test_full_score_each_tier_family(rank: int, expected_points: float) -> None:
    truth = (_variant(999),)
    candidates = [
        _candidate(_variant(index), epcr=1.0 - index / 100)
        for index in range(1, 11)
    ]
    candidates[rank - 1] = _candidate(truth[0], epcr=1.0 - rank / 100)
    submission = Submission("SYNTHETIC_SCORE", tuple(candidates))

    result = score_submission(submission, truth)

    assert result.rank_points == expected_points
    assert result.full_match_rank == rank
    assert result.partial_match_rank is None


def test_partial_used_only_when_full_match_absent() -> None:
    first, second = _variant(101), _variant(202)
    no_full = Submission(
        "SYNTHETIC_PARTIAL",
        (
            _candidate(_variant(1), epcr=0.9),
            _candidate(first, _variant(2), epcr=0.8),
            _candidate(second, _variant(3), epcr=0.7),
        ),
    )
    partial = score_submission(no_full, (first, second))
    assert partial.rank_points == 25.0
    assert partial.partial_match_rank == 2
    assert partial.full_match_rank is None

    with_full = Submission(
        "SYNTHETIC_PARTIAL",
        no_full.candidates + (_candidate(first, second, epcr=0.6),),
    )
    full = score_submission(with_full, (first, second))
    assert full.rank_points == 25.0
    assert full.full_match_rank == 4
    assert full.partial_match_rank is None


def test_one_variant_truth_has_no_partial() -> None:
    truth = (_variant(101),)
    submission = Submission(
        "SYNTHETIC_NO_PARTIAL",
        (_candidate(truth[0], _variant(999), epcr=0.9),),
    )
    result = score_submission(submission, truth)
    assert result.rank_points == 0.0
    assert result.full_match_rank is None
    assert result.partial_match_rank is None


def test_compound_full_match_is_order_insensitive() -> None:
    first, second = _variant(101), _variant(202)
    submission = Submission(
        "SYNTHETIC_ORDER",
        (_candidate(second, first, epcr=0.9),),
    )
    result = score_submission(submission, (first, second))
    assert result.rank_points == 100.0
    assert result.full_match_rank == 1
    assert result.fmax == 1.0


def test_scorer_rejects_compound_candidate_with_duplicate_variants() -> None:
    repeated = _variant(101)
    submission = Submission(
        "SYNTHETIC_DUPLICATE_COMPOUND",
        (_candidate(repeated, repeated, epcr=0.9),),
    )
    with pytest.raises(ValueError, match="two different variants"):
        score_submission(submission, (repeated, _variant(202)))


def test_stable_epcr_tie_ranking() -> None:
    truth = (_variant(202),)
    submission = Submission(
        "SYNTHETIC_TIE",
        (
            _candidate(_variant(101), epcr=0.9),
            _candidate(truth[0], epcr=0.9),
        ),
    )
    assert score_submission(submission, truth).full_match_rank == 2


def test_fmax_deduplicates_variants_at_each_threshold() -> None:
    first, second, wrong = _variant(101), _variant(202), _variant(303)
    submission = Submission(
        "SYNTHETIC_FMAX",
        (
            _candidate(first, epcr=0.9),
            _candidate(first, wrong, epcr=0.8),
            _candidate(second, epcr=0.7),
        ),
    )
    result = score_submission(submission, (first, second))
    assert result.fmax == pytest.approx(0.8)
    assert result.f_max_threshold == pytest.approx(0.7)
    assert result.n_predictions_at_f_max == 3
    assert 0.0 <= result.fmax <= 1.0


def test_finding_type_is_informational_in_public_evaluator_compatibility() -> None:
    """The organizer evaluator currently scores secondary rows like primary rows."""

    truth = (_variant(202),)
    submission = Submission(
        "SYNTHETIC_FINDING_TYPE",
        (
            _candidate(_variant(101), epcr=0.9, finding_type="secondary"),
            _candidate(truth[0], epcr=0.8, finding_type="primary"),
        ),
    )

    result = score_submission(submission, truth)

    assert result.full_match_rank == 2
    assert result.rank_points == 50.0
    assert result.fmax == pytest.approx(2.0 / 3.0)
    assert result.f_max_threshold == pytest.approx(0.8)
    assert result.n_predictions_at_f_max == 2


def test_pinned_official_scorer_compound_parity() -> None:
    """Fixed synthetic parity case for the pinned public organizer evaluator."""

    assert len(OFFICIAL_SPACE_HEAD_COMMIT) == 40
    assert len(OFFICIAL_EVALUATION_LAST_MODIFIED_COMMIT) == 40
    assert len(OFFICIAL_EVALUATION_CANONICAL_SHA256) == 64
    first, second = _variant(101), _variant(202)
    submission = Submission(
        "SYNTHETIC_OFFICIAL_PARITY",
        (
            _candidate(_variant(1), epcr=0.99),
            _candidate(first, second, epcr=0.90),
            _candidate(_variant(3), epcr=0.50, finding_type="secondary"),
        ),
    )

    result = score_submission(submission, (first, second))

    assert result.rank_points == 50.0
    assert result.full_match_rank == 2
    assert result.partial_match_rank is None
    assert result.fmax == pytest.approx(0.8)
    assert result.f_max_threshold == pytest.approx(0.90)
    assert result.n_predictions_at_f_max == 2
