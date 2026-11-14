from copy import deepcopy
from decimal import Decimal

from analysis.benchmarks.rank_audit import audit
from analysis.benchmarks.run import cases, track2


def test_fixed_benchmark_has_balanced_unique_truth_and_deterministic_cases():
    sample = list(cases(10))
    assert sample == list(cases(10))
    assert len(sample) == 40
    for _, _, rows, truth in sample:
        assert len(rows) == 10
        assert sum(r["variants"] == truth for r in rows) == 1
        assert len({r["variants"] for r in rows}) == 10
    assert sum(len(truth) == 2 for _, _, _, truth in sample) == 20


def test_comparison_includes_true_positive_and_rejects_incomplete_or_harmful_evidence():
    rows = track2()
    assert len(rows) == 9
    assert [r["scenario"] for r in rows if r["safe_rescue_advance"]] == ["SYNTHETIC_all_pass"]
    harm = next(r for r in rows if r["scenario"] == "SYNTHETIC_confirmed_clone_harm")
    assert harm["illustrative_additive_advance"]
    assert harm["safe_rescue_reason"] == "CONFIRMED_SAFETY_VETO"


def test_audit_reports_rank_reversal_without_mutating_evidence_or_exposing_identifiers():
    def row(pos, score, frequency):
        return {"variants": [{"chrom": "chr1", "pos": pos, "ref": "A", "alt": "C"}],
                "raw_epcr": Decimal(score), "finding_type": "primary", "notes": "SYNTHETIC_PRIVATE_NOTE",
                "read_validated": True, "frequency_status": frequency, "phase": "not_applicable"}
    document = {"proband_id": "SYNTHETIC_PRIVATE_ID", "calibration": "synthetic_only",
                "candidates": [row(1000, "0.9", "unknown"), row(1010, "0.7", "known")]}
    before = deepcopy(document)
    result = audit(document)
    assert result["rank_changed_count"] == 2
    assert result["rows"][0]["input_row"] == 2
    assert result["rows"][1]["final_epcr"] == "0.50"
    assert result["review_required"]
    assert document == before
    rendered = str(result)
    for private in ("SYNTHETIC_PRIVATE", "chr1", "1000", "1010", "variants", "proband_id"):
        assert private not in rendered
