"""Evaluate the qualitative Safe Rescue contract without averaging away harm.

Input statuses must come from a separately reviewed, prospectively calibrated
experiment. This module neither calculates confidence intervals nor supplies
clinical thresholds. It is a research decision contract only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

BENEFITS = tuple(f"{endpoint}_dose_{dose}" for endpoint in
                 ("neuron_yield", "atp_linked_ocr", "tmrm_per_mito_mass") for dose in (1, 2))
SAFETY = ("chromosome_errors", "abnormal_clone_persistence", "aneuploid_selectivity",
          "malignant_fitness", "invasion", "chemotherapy_resistance")
QUALIFICATION = ("case_mechanism_fit", "two_guide_model", "assay_controls", "orthogonal_confirmation")
STATUSES = frozenset({"pass", "fail", "indeterminate", "not_measured"})


@dataclass(frozen=True)
class Decision:
    advance: bool
    reason: str
    blocking_checks: tuple[str, ...]


def evaluate(benefits: Mapping[str, str], safety: Mapping[str, str],
             qualification: Mapping[str, str], *, advancement_candidate: bool) -> Decision:
    """Return a veto-preserving preclinical decision with every blocker visible.

Safety 'fail' means independently adjudicated harm under the frozen rule, not
a confidence interval crossing an uncertainty margin. Missing or indeterminate
safety blocks advancement without asserting that harm occurred. Each safety
status must cover every applicable exposure, model and component in SRE01-16.
"""
    if type(advancement_candidate) is not bool:
        raise ValueError("candidate eligibility must be boolean")
    all_status: dict[str, str] = {}
    for values, expected in ((benefits, BENEFITS), (safety, SAFETY), (qualification, QUALIFICATION)):
        if set(values) != set(expected):
            raise ValueError("every configured check is required and unknown checks are rejected")
        if any(not isinstance(value, str) or value not in STATUSES for value in values.values()):
            raise ValueError("invalid evidence status")
        all_status.update(values)
    blockers = tuple(key for key in (*QUALIFICATION, *BENEFITS, *SAFETY) if all_status[key] != "pass")
    if not advancement_candidate:
        return Decision(False, "CONTROL_NOT_ELIGIBLE", blockers)
    if any(safety[key] == "fail" for key in SAFETY):
        return Decision(False, "CONFIRMED_SAFETY_VETO", blockers)
    if any(qualification[key] == "fail" for key in QUALIFICATION):
        return Decision(False, "QUALIFICATION_FAILED", blockers)
    if any(benefits[key] == "fail" for key in BENEFITS):
        return Decision(False, "BENEFIT_FAILED", blockers)
    if blockers:
        return Decision(False, "INDETERMINATE_NO_ADVANCE", blockers)
    return Decision(True, "PRECLINICAL_CONFIRMATION_ELIGIBLE", ())
