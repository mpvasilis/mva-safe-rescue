#!/usr/bin/env python3
"""Deterministic public-only power sensitivity for the Safe Rescue design.

The simulation operates on independent run-level, treatment-minus-vehicle
differences.  It intentionally contains no patient, variant, or gated data and
uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_ASSUMPTIONS = HERE / "assumptions.tsv"
DEFAULT_OUTPUT = HERE / "power_scenarios.tsv"

ASSUMPTION_COLUMNS = [
    "assumption_id",
    "category",
    "value",
    "unit",
    "status",
    "description",
]

OUTPUT_COLUMNS = [
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

REQUIRED_ASSUMPTIONS = {
    "seed",
    "iterations",
    "biological_runs_grid",
    "true_effect_grid",
    "paired_difference_sd_grid",
    "minimum_benefit",
    "familywise_alpha",
    "candidate_family_size",
    "cross_comparison_correlation",
}


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    seed: int
    iterations: int
    biological_runs: int
    true_effect: float
    minimum_benefit: float
    paired_sd: float
    correlation: float
    candidate_alpha: float
    critical_t: float
    primary_power: float
    mitochondrial_power: float
    all_benefit_power: float
    all_benefit_mcse: float

    def as_row(self) -> dict[str, str]:
        return {
            "scenario_id": self.scenario_id,
            "seed": str(self.seed),
            "iterations": str(self.iterations),
            "biological_runs": str(self.biological_runs),
            "true_effect_control_sd": _format_number(self.true_effect, 2),
            "minimum_benefit_control_sd": _format_number(
                self.minimum_benefit, 2
            ),
            "paired_difference_sd_control_sd": _format_number(self.paired_sd, 2),
            "cross_comparison_correlation": _format_number(self.correlation, 2),
            "candidate_level_alpha": _format_number(self.candidate_alpha, 4),
            "critical_t": _format_number(self.critical_t, 4),
            "primary_both_doses_power": _format_number(self.primary_power, 4),
            "mitochondrial_two_endpoints_both_doses_power": _format_number(
                self.mitochondrial_power, 4
            ),
            "all_three_endpoints_both_doses_power": _format_number(
                self.all_benefit_power, 4
            ),
            "all_benefit_mcse": _format_number(self.all_benefit_mcse, 4),
            "scope": "benefit_gates_only_conditional_on_all_safety_vetoes_passing",
        }


def _format_number(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def read_assumptions(path: Path = DEFAULT_ASSUMPTIONS) -> dict[str, str]:
    """Read and validate the transparent assumption table."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        if reader.fieldnames != ASSUMPTION_COLUMNS:
            raise ValueError(
                f"Unexpected assumptions schema: {reader.fieldnames!r}; "
                f"expected {ASSUMPTION_COLUMNS!r}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError("Assumptions table is empty")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Assumptions table is ragged")
    identifiers = [row["assumption_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Assumption identifiers must be unique")
    values = {row["assumption_id"]: row["value"] for row in rows}
    missing = REQUIRED_ASSUMPTIONS - values.keys()
    if missing:
        raise ValueError(f"Missing required assumptions: {sorted(missing)}")
    return values


def _parse_float_grid(value: str) -> list[float]:
    parsed = [float(item) for item in value.split("|")]
    if not parsed or any(not math.isfinite(item) for item in parsed):
        raise ValueError(f"Invalid numeric grid: {value!r}")
    return parsed


def _parse_int_grid(value: str) -> list[int]:
    parsed = [int(item) for item in value.split("|")]
    if not parsed or any(item < 3 for item in parsed):
        raise ValueError("Every biological run count must be an integer >= 3")
    return parsed


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """Evaluate the incomplete-beta continued fraction (Numerical Recipes)."""
    max_iterations = 300
    epsilon = 3.0e-14
    tiny = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    result = d
    for iteration in range(1, max_iterations + 1):
        even = 2 * iteration
        numerator = iteration * (b - iteration) * x / (
            (qam + even) * (a + even)
        )
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        result *= d * c

        numerator = -(a + iteration) * (qab + iteration) * x / (
            (a + even) * (qap + even)
        )
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) <= epsilon:
            return result
    raise ArithmeticError("Incomplete-beta continued fraction did not converge")


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if not 0.0 <= x <= 1.0:
        raise ValueError("x must be in [0, 1]")
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    factor = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return factor * _beta_continued_fraction(a, b, x) / a
    return 1.0 - factor * _beta_continued_fraction(b, a, 1.0 - x) / b


def student_t_cdf(value: float, degrees_freedom: int) -> float:
    """CDF of Student's t, implemented without third-party dependencies."""
    if degrees_freedom <= 0:
        raise ValueError("degrees_freedom must be positive")
    if value == 0.0:
        return 0.5
    x = degrees_freedom / (degrees_freedom + value * value)
    tail_twice = _regularized_incomplete_beta(
        degrees_freedom / 2.0, 0.5, x
    )
    if value > 0.0:
        return 1.0 - 0.5 * tail_twice
    return 0.5 * tail_twice


def student_t_quantile(probability: float, degrees_freedom: int) -> float:
    """Invert the Student-t CDF by deterministic bisection."""
    if not 0.5 < probability < 1.0:
        raise ValueError("This implementation expects 0.5 < probability < 1")
    lower = 0.0
    upper = 1.0
    while student_t_cdf(upper, degrees_freedom) < probability:
        upper *= 2.0
        if upper > 1.0e6:
            raise ArithmeticError("Could not bracket Student-t quantile")
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if student_t_cdf(midpoint, degrees_freedom) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _passes_margin(
    total: float,
    total_squares: float,
    count: int,
    minimum_benefit: float,
    critical_t: float,
) -> bool:
    mean = total / count
    variance = (total_squares - count * mean * mean) / (count - 1)
    variance = max(variance, 0.0)
    if variance == 0.0:
        return mean > minimum_benefit
    statistic = (mean - minimum_benefit) / math.sqrt(variance / count)
    return statistic > critical_t


def simulate(assumptions: dict[str, str]) -> list[ScenarioResult]:
    """Run the fixed-seed sensitivity grid using common random numbers."""
    seed = int(assumptions["seed"])
    iterations = int(assumptions["iterations"])
    run_grid = _parse_int_grid(assumptions["biological_runs_grid"])
    effect_grid = _parse_float_grid(assumptions["true_effect_grid"])
    sd_grid = _parse_float_grid(assumptions["paired_difference_sd_grid"])
    minimum_benefit = float(assumptions["minimum_benefit"])
    familywise_alpha = float(assumptions["familywise_alpha"])
    candidate_family_size = int(assumptions["candidate_family_size"])
    correlation = float(assumptions["cross_comparison_correlation"])

    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if run_grid != sorted(set(run_grid)):
        raise ValueError("biological_runs_grid must be strictly increasing and unique")
    if any(effect <= minimum_benefit for effect in effect_grid):
        raise ValueError("Every true effect must exceed the provisional benefit margin")
    if any(sd <= 0.0 for sd in sd_grid):
        raise ValueError("Every paired-difference SD must be positive")
    if not 0.0 < familywise_alpha < 0.5:
        raise ValueError("familywise_alpha must be in (0, 0.5)")
    if candidate_family_size <= 0:
        raise ValueError("candidate_family_size must be positive")
    if not 0.0 <= correlation < 1.0:
        raise ValueError("cross_comparison_correlation must be in [0, 1)")

    candidate_alpha = familywise_alpha / candidate_family_size
    critical_by_n = {
        count: student_t_quantile(1.0 - candidate_alpha, count - 1)
        for count in run_grid
    }
    maximum_runs = max(run_grid)
    checkpoints = set(run_grid)
    sqrt_correlation = math.sqrt(correlation)
    sqrt_independent = math.sqrt(1.0 - correlation)

    # Six co-required comparisons: primary at two doses, followed by each of
    # exactly two mitochondrial endpoints at the same two doses.
    noise_snapshots: dict[int, list[tuple[list[float], list[float]]]] = {
        count: [] for count in run_grid
    }
    generator = random.Random(seed)
    for _ in range(iterations):
        totals = [0.0] * 6
        total_squares = [0.0] * 6
        for run_index in range(1, maximum_runs + 1):
            shared_response = generator.gauss(0.0, 1.0)
            for comparison in range(6):
                noise = (
                    sqrt_correlation * shared_response
                    + sqrt_independent * generator.gauss(0.0, 1.0)
                )
                totals[comparison] += noise
                total_squares[comparison] += noise * noise
            if run_index in checkpoints:
                noise_snapshots[run_index].append(
                    (totals.copy(), total_squares.copy())
                )

    results: list[ScenarioResult] = []
    for true_effect in effect_grid:
        for paired_sd in sd_grid:
            for count in run_grid:
                critical_t = critical_by_n[count]
                primary_success = 0
                mitochondrial_success = 0
                all_success = 0
                for noise_totals, noise_squares in noise_snapshots[count]:
                    # Affine transformation from standardized noise to each
                    # scenario avoids rerandomization and makes effect/SD
                    # sensitivity comparisons directly auditable.
                    transformed_totals = [
                        count * true_effect + paired_sd * total
                        for total in noise_totals
                    ]
                    transformed_squares = [
                        count * true_effect * true_effect
                        + 2.0 * true_effect * paired_sd * total
                        + paired_sd * paired_sd * squares
                        for total, squares in zip(noise_totals, noise_squares)
                    ]
                    passes = [
                        _passes_margin(
                            transformed_totals[index],
                            transformed_squares[index],
                            count,
                            minimum_benefit,
                            critical_t,
                        )
                        for index in range(6)
                    ]
                    primary_pass = all(passes[:2])
                    mitochondrial_pass = all(passes[2:])
                    primary_success += primary_pass
                    mitochondrial_success += mitochondrial_pass
                    all_success += primary_pass and mitochondrial_pass

                primary_power = primary_success / iterations
                mitochondrial_power = mitochondrial_success / iterations
                all_benefit_power = all_success / iterations
                mcse = math.sqrt(
                    all_benefit_power * (1.0 - all_benefit_power) / iterations
                )
                scenario_id = (
                    f"effect_{true_effect:.2f}_sd_{paired_sd:.2f}_n_{count:02d}"
                )
                results.append(
                    ScenarioResult(
                        scenario_id=scenario_id,
                        seed=seed,
                        iterations=iterations,
                        biological_runs=count,
                        true_effect=true_effect,
                        minimum_benefit=minimum_benefit,
                        paired_sd=paired_sd,
                        correlation=correlation,
                        candidate_alpha=candidate_alpha,
                        critical_t=critical_t,
                        primary_power=primary_power,
                        mitochondrial_power=mitochondrial_power,
                        all_benefit_power=all_benefit_power,
                        all_benefit_mcse=mcse,
                    )
                )
    return results


def render_tsv(results: list[ScenarioResult]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=OUTPUT_COLUMNS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(result.as_row() for result in results)
    return buffer.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the committed output exactly matches regeneration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    assumptions = read_assumptions(arguments.assumptions)
    rendered = render_tsv(simulate(assumptions))
    if arguments.check:
        if not arguments.output.exists():
            print(f"Missing output: {arguments.output}", file=sys.stderr)
            return 1
        current = arguments.output.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"Determinism check failed: regenerate {arguments.output}",
                file=sys.stderr,
            )
            return 1
        print(f"Determinism check passed: {arguments.output}")
        return 0

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered, encoding="utf-8", newline="")
    print(f"Wrote {len(rendered.splitlines()) - 1} scenarios to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
