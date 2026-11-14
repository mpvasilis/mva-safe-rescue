from __future__ import annotations

import csv
import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).absolute().parent.parent
DESIGN_DIR = REPO_ROOT / "analysis" / "design_power"
SCRIPT = DESIGN_DIR / "simulate_power.py"
ASSUMPTIONS = DESIGN_DIR / "assumptions.tsv"
SCENARIOS = DESIGN_DIR / "power_scenarios.tsv"

ASSUMPTION_COLUMNS = [
    "assumption_id",
    "category",
    "value",
    "unit",
    "status",
    "description",
]

SCENARIO_COLUMNS = [
    "scenario_id",
    "seed",
    "iterations",
    "biological_runs",
    "true_effect_control_sd",
    "minimum_benefit_control_sd",
    "paired_difference_sd_control_sd",
    "cross_comparison_correlation",
    "candidate_level_alpha",
    "critical_t",
    "primary_both_doses_power",
    "mitochondrial_two_endpoints_both_doses_power",
    "all_three_endpoints_both_doses_power",
    "all_benefit_mcse",
    "scope",
]


def _load_module():
    specification = importlib.util.spec_from_file_location("design_power", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        rows = list(reader)
    assert reader.fieldnames is not None
    assert all(None not in row for row in rows), f"ragged TSV: {path}"
    assert all(value is not None for row in rows for value in row.values())
    return reader.fieldnames, rows


def test_committed_simulation_is_deterministic() -> None:
    checked = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr
    assert "Determinism check passed" in checked.stdout


def test_assumption_and_scenario_schemas() -> None:
    assumption_columns, assumption_rows = _read_tsv(ASSUMPTIONS)
    scenario_columns, scenario_rows = _read_tsv(SCENARIOS)
    assert assumption_columns == ASSUMPTION_COLUMNS
    assert scenario_columns == SCENARIO_COLUMNS
    assert len({row["assumption_id"] for row in assumption_rows}) == len(
        assumption_rows
    )
    assert len(scenario_rows) == 72
    assert len({row["scenario_id"] for row in scenario_rows}) == 72
    assert {row["seed"] for row in scenario_rows} == {"20260827"}
    assert {row["iterations"] for row in scenario_rows} == {"12000"}
    assert {row["candidate_level_alpha"] for row in scenario_rows} == {"0.0250"}
    assert {row["scope"] for row in scenario_rows} == {
        "benefit_gates_only_conditional_on_all_safety_vetoes_passing"
    }

    endpoint_rows = [
        row for row in assumption_rows if row["category"] == "endpoint"
    ]
    assert [row["assumption_id"] for row in endpoint_rows] == [
        "primary_endpoint",
        "mitochondrial_endpoint_1",
        "mitochondrial_endpoint_2",
    ]
    assert "AUTHORIZED_CASE_SELECTED_SAC_GENE" in {
        row["value"] for row in assumption_rows
    }
    assert "two_independent_guides_then_orthogonal_confirmation" in {
        row["value"] for row in assumption_rows
    }


def test_power_has_expected_monotonic_sanity() -> None:
    _, rows = _read_tsv(SCENARIOS)
    indexed = {
        (
            float(row["true_effect_control_sd"]),
            float(row["paired_difference_sd_control_sd"]),
            int(row["biological_runs"]),
        ): row
        for row in rows
    }
    metrics = [
        "primary_both_doses_power",
        "mitochondrial_two_endpoints_both_doses_power",
        "all_three_endpoints_both_doses_power",
    ]
    for row in rows:
        for metric in metrics:
            assert 0.0 <= float(row[metric]) <= 1.0
        assert float(row["all_three_endpoints_both_doses_power"]) <= float(
            row["primary_both_doses_power"]
        )
        assert float(row["all_three_endpoints_both_doses_power"]) <= float(
            row["mitochondrial_two_endpoints_both_doses_power"]
        )

    # Common random numbers make the effect and variability comparisons
    # monotone apart from the four-decimal output rounding.
    for paired_sd in (0.8, 1.0, 1.2):
        for runs in (6, 8, 10, 12, 16, 20, 24, 32):
            for metric in metrics:
                by_effect = [
                    float(indexed[(effect, paired_sd, runs)][metric])
                    for effect in (0.4, 0.7, 1.0)
                ]
                assert by_effect == sorted(by_effect)

    for effect in (0.4, 0.7, 1.0):
        for runs in (6, 8, 10, 12, 16, 20, 24, 32):
            for metric in metrics:
                by_variability = [
                    float(indexed[(effect, paired_sd, runs)][metric])
                    for paired_sd in (0.8, 1.0, 1.2)
                ]
                assert by_variability == sorted(by_variability, reverse=True)

    # Monte Carlo estimates need not be stepwise monotone for every added run,
    # but the predeclared endpoints of the run-count sensitivity must improve.
    for effect in (0.4, 0.7, 1.0):
        for paired_sd in (0.8, 1.0, 1.2):
            for metric in metrics:
                assert float(indexed[(effect, paired_sd, 32)][metric]) >= float(
                    indexed[(effect, paired_sd, 6)][metric]
                )


def test_student_t_calibration_and_design_document_consistency() -> None:
    module = _load_module()
    assert abs(module.student_t_quantile(0.975, 5) - 2.5706) < 0.0001
    assert abs(module.student_t_quantile(0.975, 31) - 2.0395) < 0.0001

    design = (REPO_ROOT / "docs" / "CONFIRMATORY_EXPERIMENT_DESIGN.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(design.lower().split())
    assert "day-21 live map2+tubb3+ neuron yield" in normalized
    assert "per 100 starting viable pax6+sox2+ neural progenitors" in normalized
    assert "authorized case-selected sac gene" in normalized
    assert "aavs1-integrated, inducible dcas9-krab" in normalized
    assert "maintained crispri activity" in normalized
    assert "cannot be assumed to transfer unchanged" in normalized
    assert "begins only after the partial-sac perturbation" in normalized
    assert "at least two independently designed" in normalized
    assert "a non-targeting guide alone does not exclude" in normalized
    assert "arimoclomol versus vehicle and elamipretide versus vehicle" in normalized
    assert "ineligible for advancement in this family" in normalized
    assert "exactly two mitochondrial endpoints" in normalized
    assert "only these three endpoints at two doses" in normalized
    assert "cannot create or replace a benefit pass" in normalized
    assert "at both locked doses" in normalized
    assert "noncompensatory veto" in normalized
    assert "candidate-level alpha of 0.025" in normalized
    assert "placeholder primary endpoint" not in normalized
    assert "endpoint `y`" not in normalized
    assert "../analysis/design_power/readme.md" in normalized
