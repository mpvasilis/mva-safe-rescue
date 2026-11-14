"""Reproduce the prespecified public, invented decision-policy stress test."""
from __future__ import annotations

import csv
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rare_mva.track1.builder import _prepare_document
from rare_mva.track1.schema import Candidate, Submission, Variant
from rare_mva.track1.scoring import score_submission
from rare_mva.track2.decision import BENEFITS, SAFETY, QUALIFICATION, evaluate

HERE = Path(__file__).resolve().parent
REGIMES = {"informative_review": (0.05, 0.55), "uninformative_review": (0.30, 0.30),
           "adverse_review": (0.70, 0.10), "unresolved_true_pairs": (0.10, 0.25)}
METHODS = ("variant_surrogate", "phenotype_surrogate", "production_caps",
           "caps_without_frequency", "caps_without_phase", "caps_without_read_review")


def cases(n_per_regime: int = 600):
    rng = random.Random(20260909)
    for regime, (true_error, decoy_error) in REGIMES.items():
        for case in range(n_per_regime):
            truth_index = rng.randrange(10)
            rows = []
            for index in range(10):
                true = index == truth_index
                paired = case % 2 == 1
                variants = tuple(Variant("chr1", 1000 + index * 10 + j, "A", "C") for j in range(2 if paired else 1))
                variant_score = rng.betavariate(*( (5, 2) if true else (2, 5)))
                phenotype = rng.betavariate(*( (3, 2) if true else (2, 3)))
                score = (variant_score + phenotype) / 2
                error = true_error if true else decoy_error
                read_validated = rng.random() >= error
                frequency = "unknown" if rng.random() < error else "known"
                phase_error = (0.90 if true else 0.20) if regime == "unresolved_true_pairs" else error
                phase = ("unresolved" if rng.random() < phase_error else "confirmed_trans") if paired else "not_applicable"
                rows.append({"variants": variants, "variant_score": variant_score, "score": score,
                             "read_validated": read_validated, "frequency_status": frequency, "phase": phase})
            yield regime, f"SYNTHETIC_{regime}_{case:04d}", rows, rows[truth_index]["variants"]


def submission(case_id: str, rows: list[dict], method: str) -> Submission:
    if method in {"variant_surrogate", "phenotype_surrogate"}:
        key = "variant_score" if method == "variant_surrogate" else "score"
        return Submission(case_id, tuple(Candidate(r["variants"], round(r[key], 6), "primary", "SYNTHETIC") for r in rows))
    candidates = []
    for row in rows:
        phase = row["phase"]
        if method == "caps_without_phase" and phase == "unresolved":
            phase = "confirmed_trans"  # Only an explicit synthetic ablation.
        candidates.append({"variants": [asdict(v) for v in row["variants"]], "raw_epcr": Decimal(str(row["score"])),
                           "finding_type": "primary", "notes": "SYNTHETIC", "phase": phase,
                           "read_validated": True if method == "caps_without_read_review" else row["read_validated"],
                           "frequency_status": "known" if method == "caps_without_frequency" else row["frequency_status"]})
    identifier, prepared = _prepare_document({"proband_id": case_id, "calibration": "synthetic_only", "candidates": candidates})
    return Submission(identifier, tuple(Candidate(c.variants, float(c.epcr_text), c.finding_type, c.notes) for c in prepared))


def track1(n_per_regime: int = 600) -> tuple[list[dict], list[dict], float]:
    groups = {(regime, method): [] for regime in REGIMES for method in METHODS}
    paired_counts = {r: {"improved": 0, "regressed": 0, "unchanged": 0} for r in REGIMES}
    started = time.perf_counter()
    for regime, case_id, rows, truth in cases(n_per_regime):
        outcomes = {}
        for method in METHODS:
            sub = submission(case_id, rows, method)
            score = score_submission(sub, truth)
            predicted = {v for c in sub.candidates if c.epcr >= 0.60 for v in c.variants}
            tp = len(predicted & set(truth)); fp = len(predicted - set(truth)); fn = len(set(truth) - predicted)
            row = {"top1": int(score.full_match_rank == 1), "top3": int(score.full_match_rank is not None and score.full_match_rank <= 3),
                   "rank_points": score.rank_points, "fmax": score.fmax, "tp": tp, "fp": fp, "fn": fn,
                   "abstained": int(not predicted)}
            groups[(regime, method)].append(row); outcomes[method] = row["top1"]
        delta = outcomes["production_caps"] - outcomes["phenotype_surrogate"]
        paired_counts[regime]["improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"] += 1
    elapsed = time.perf_counter() - started
    summaries = []
    for (regime, method), rows in groups.items():
        total = {key: sum(row[key] for row in rows) for key in rows[0]}
        n = len(rows)
        summaries.append({"regime": regime, "method": method, "cases": n,
            "top1_recovery": total["top1"] / n, "top3_recovery": total["top3"] / n,
            "mean_rank_points": total["rank_points"] / n, "mean_fmax": total["fmax"] / n,
            "threshold": 0.60, "precision_at_threshold": total["tp"] / (total["tp"] + total["fp"]) if total["tp"] + total["fp"] else None,
            "recall_at_threshold": total["tp"] / (total["tp"] + total["fn"]),
            "false_positive_variants": total["fp"], "abstention_rate": total["abstained"] / n})
    return summaries, [{"regime": r, **values} for r, values in paired_counts.items()], elapsed


def track2() -> list[dict]:
    scenarios = [
        ("SYNTHETIC_all_pass", {}, {}, {}, True),
        ("SYNTHETIC_one_dose_failure", {BENEFITS[1]: "fail"}, {}, {}, True),
        ("SYNTHETIC_unmeasured_neurons", {BENEFITS[0]: "not_measured", BENEFITS[1]: "not_measured"}, {}, {}, True),
        ("SYNTHETIC_confirmed_clone_harm", {}, {"abnormal_clone_persistence": "fail"}, {}, True),
        ("SYNTHETIC_indeterminate_safety", {}, {"invasion": "indeterminate"}, {}, True),
        ("SYNTHETIC_case_mismatch", {}, {}, {"case_mechanism_fit": "fail"}, True),
        ("SYNTHETIC_confirmation_conflict", {}, {}, {"orthogonal_confirmation": "fail"}, True),
        ("SYNTHETIC_ineligible_control", {}, {}, {}, False),
        ("SYNTHETIC_no_measured_support", dict.fromkeys(BENEFITS, "not_measured"), dict.fromkeys(SAFETY, "not_measured"), dict.fromkeys(QUALIFICATION, "not_measured"), True),
    ]
    rows = []
    for name, b, s, q, eligible in scenarios:
        benefits = {**dict.fromkeys(BENEFITS, "pass"), **b}
        safety = {**dict.fromkeys(SAFETY, "pass"), **s}
        qualification = {**dict.fromkeys(QUALIFICATION, "pass"), **q}
        decision = evaluate(benefits, safety, qualification, advancement_candidate=eligible)
        benefit_fraction = sum(v == "pass" for v in benefits.values()) / len(BENEFITS)
        safety_fraction = sum(v == "pass" for v in safety.values()) / len(SAFETY)
        rows.append({"scenario": name, "any_biochemical_pass": any(benefits[k] == "pass" for k in BENEFITS if not k.startswith("neuron")),
            "illustrative_additive_advance": 0.8 * benefit_fraction + 0.2 * safety_fraction >= 0.75,
            "safe_rescue_advance": decision.advance, "safe_rescue_reason": decision.reason,
            "blocking_checks": ";".join(decision.blocking_checks)})
    return rows


def write_tsv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    out = HERE / "release"; out.mkdir(exist_ok=True)
    results, paired, seconds = track1()
    write_tsv(out / "track1_policy_comparison.tsv", results)
    write_tsv(out / "track1_paired_changes.tsv", paired)
    write_tsv(out / "track2_decision_comparison.tsv", track2())
    summary = {"scope": "SYNTHETIC_POLICY_STRESS_TEST_NOT_FULL_WGS_BENCHMARK", "seed": 20260909,
               "cases": 2400, "regimes": 4, "methods": len(METHODS), "wall_seconds": seconds,
               "clinical_accuracy_estimate": False, "official_challenge_score": False,
               "production_builder_used": True, "production_scorer_used": True,
               "protocol_sha256": hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
