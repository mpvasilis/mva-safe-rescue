#!/usr/bin/env python3
"""Deterministic, research-only chromosome mosaic-aneuploidy screen.

The program intentionally emits chromosome/block aggregates only.  VCF records
are streamed from bcftools twice and are never written to disk.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


AUTOSOMES = tuple(f"chr{i}" for i in range(1, 23))
ONE_MB = 1_000_000
TEN_MB = 10_000_000
MAD_SCALE = 1.4826
MIN_CALLABLE_FRACTION = 0.80
MIN_GENERATED_FRACTION = 0.60
MIN_RETAINED_BASES = 20_000_000
MIN_BAF_SITES = 10_000
MIN_BAF_BLOCK_SITES = 500
MIN_BAF_BLOCKS = 3
MIN_COMPARATOR_AUTOSOMES = 18
MIN_DEPTH_BLOCK_EFFECT = 0.03
MIN_BAF_BLOCK_EFFECT = 0.005
MIN_CNV_RATIO_EFFECT = 0.005

DEPTH_STRONG = (0.08, 4.0, 0.75)
DEPTH_SUGGESTIVE = (0.05, 3.0, 0.65)
BAF_STRONG = (0.010, 4.0, 0.70)
BAF_SUGGESTIVE = (0.006, 3.0, 0.60)


class AnalysisError(RuntimeError):
    """A validation or analysis failure that must fail closed."""


def _median(values: Sequence[float]) -> float:
    if not values:
        raise AnalysisError("empty statistic")
    return float(statistics.median(values))


def _mad(values: Sequence[float], center: float | None = None) -> float:
    if not values:
        raise AnalysisError("empty statistic")
    if center is None:
        center = _median(values)
    return _median([abs(value - center) for value in values])


def _quantile(values: Sequence[float], fraction: float) -> float:
    """Linear, type-7-style quantile implemented without scientific packages."""
    if not values or not 0.0 <= fraction <= 1.0:
        raise AnalysisError("invalid quantile")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _canonical_autosome(value: str) -> str | None:
    text = value.strip()
    if text.lower().startswith("chr"):
        text = text[3:]
    if text.isdigit() and 1 <= int(text) <= 22 and str(int(text)) == text:
        return f"chr{int(text)}"
    return None


def _fmt(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "NA"
        return f"{value:.8f}"
    return str(value)


def _at_least(value: float, threshold: float) -> bool:
    return value >= threshold or math.isclose(value, threshold, rel_tol=0.0, abs_tol=1e-12)


@dataclass(frozen=True)
class DepthBin:
    chrom: str
    start: int
    end: int
    depth: float
    callable_fraction: float


@dataclass
class BafAccumulator:
    dps: list[int]
    bafs: list[float]

    @classmethod
    def empty(cls) -> "BafAccumulator":
        return cls([], [])

    def add(self, dp: int, baf: float) -> None:
        self.dps.append(dp)
        self.bafs.append(baf)

    def summary(self) -> dict[str, float | int | None]:
        deviations = [abs(value - 0.5) for value in self.bafs]
        return {
            "site_count": len(self.bafs),
            "mean_dp": sum(self.dps) / len(self.dps) if self.dps else None,
            "mean_baf": sum(self.bafs) / len(self.bafs) if self.bafs else None,
            "median_abs_dev": _median(deviations) if deviations else None,
            "q90_abs_dev": _quantile(deviations, 0.90) if deviations else None,
        }


def load_fai(path: Path) -> tuple[dict[str, int], dict[str, str]]:
    lengths: dict[str, int] = {}
    source_names: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for line in handle:
                fields = line.rstrip("\r\n").split("\t")
                if len(fields) < 2:
                    raise AnalysisError("malformed FAI")
                canonical = _canonical_autosome(fields[0])
                if canonical is None:
                    continue
                if canonical in lengths:
                    raise AnalysisError("ambiguous autosome naming")
                length = int(fields[1])
                if length <= 0:
                    raise AnalysisError("invalid contig length")
                lengths[canonical] = length
                source_names[canonical] = fields[0]
    except (OSError, ValueError) as exc:
        raise AnalysisError("could not read FAI") from exc
    if set(lengths) != set(AUTOSOMES):
        raise AnalysisError("FAI must contain exactly one representation of every autosome")
    return lengths, source_names


def _expected_windows(length: int) -> list[tuple[int, int]]:
    windows = []
    for start in range(0, length, ONE_MB):
        end = min(start + ONE_MB, length)
        if end - start >= ONE_MB // 2:
            windows.append((start, end))
    return windows


def load_depth(path: Path, lengths: dict[str, int]) -> dict[str, list[DepthBin]]:
    bins: dict[str, list[DepthBin]] = {chrom: [] for chrom in AUTOSOMES}
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"chrom", "start", "end", "depth_sum", "callable_bases_ge10"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise AnalysisError("depth table header mismatch")
            observed: dict[str, set[tuple[int, int]]] = defaultdict(set)
            for row in reader:
                canonical = _canonical_autosome(row["chrom"])
                if canonical is None:
                    continue
                start = int(row["start"])
                end = int(row["end"])
                depth_sum = float(row["depth_sum"])
                callable_bases = int(row["callable_bases_ge10"])
                if (
                    start < 0
                    or end <= start
                    or end > lengths[canonical]
                    or not math.isfinite(depth_sum)
                    or depth_sum < 0
                    or callable_bases < 0
                    or callable_bases > end - start
                    or (start, end) in observed[canonical]
                ):
                    raise AnalysisError("invalid depth row")
                observed[canonical].add((start, end))
                width = end - start
                # The primary depth is mean aligned depth over the physical bin;
                # callable_bases_ge10 is a separate completeness filter.
                bins[canonical].append(
                    DepthBin(
                        canonical,
                        start,
                        end,
                        depth_sum / width,
                        callable_bases / width,
                    )
                )
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, AnalysisError):
            raise
        raise AnalysisError("could not read depth table") from exc
    for chrom in AUTOSOMES:
        expected = set(_expected_windows(lengths[chrom]))
        actual = {(item.start, item.end) for item in bins[chrom]}
        if actual != expected:
            raise AnalysisError("depth windows do not match FAI")
        bins[chrom].sort(key=lambda item: item.start)
    return bins


def summarize_depth(
    bins: dict[str, list[DepthBin]],
) -> tuple[dict[str, dict[str, object]], dict[tuple[str, int], dict[str, object]]]:
    chrom_stats: dict[str, dict[str, object]] = {}
    retained_by_chrom: dict[str, list[DepthBin]] = {}
    for chrom in AUTOSOMES:
        generated = bins[chrom]
        callable_bins = [item for item in generated if item.callable_fraction >= MIN_CALLABLE_FRACTION]
        retained: list[DepthBin] = []
        outlier_floor = outlier_ceiling = None
        if callable_bins:
            depths = [item.depth for item in callable_bins]
            center = _median(depths)
            radius = max(5.0 * MAD_SCALE * _mad(depths, center), 0.25 * center)
            outlier_floor, outlier_ceiling = center - radius, center + radius
            retained = [item for item in callable_bins if outlier_floor <= item.depth <= outlier_ceiling]
        retained_by_chrom[chrom] = retained
        retained_bases = sum(item.end - item.start for item in retained)
        complete = (
            bool(generated)
            and len(retained) / len(generated) >= MIN_GENERATED_FRACTION
            and retained_bases >= MIN_RETAINED_BASES
        )
        chrom_stats[chrom] = {
            "depth_generated_bins": len(generated),
            "depth_callable_bins": len(callable_bins),
            "depth_retained_bins": len(retained),
            "depth_retained_bases": retained_bases,
            "depth_complete": complete,
            "depth_median": _median([item.depth for item in retained]) if retained else None,
            "depth_outlier_floor": outlier_floor,
            "depth_outlier_ceiling": outlier_ceiling,
        }

    complete_medians = {
        chrom: float(stats["depth_median"])
        for chrom, stats in chrom_stats.items()
        if stats["depth_complete"] and stats["depth_median"] is not None
    }
    raw_deltas: dict[str, float] = {}
    for chrom, value in complete_medians.items():
        others = [other for name, other in complete_medians.items() if name != chrom]
        if len(others) < MIN_COMPARATOR_AUTOSOMES or _median(others) <= 0:
            chrom_stats[chrom]["depth_complete"] = False
            continue
        baseline = _median(others)
        ratio = value / baseline
        chrom_stats[chrom]["depth_baseline"] = baseline
        chrom_stats[chrom]["depth_ratio"] = ratio
        chrom_stats[chrom]["depth_ratio_delta"] = ratio - 1.0
        raw_deltas[chrom] = ratio - 1.0

    block_stats: dict[tuple[str, int], dict[str, object]] = {}
    for chrom in AUTOSOMES:
        stats = chrom_stats[chrom]
        if not stats["depth_complete"] or chrom not in raw_deltas:
            stats.update(depth_robust_sigma=None, depth_z=None, depth_block_concordance=None)
            continue
        other_deltas = [value for name, value in raw_deltas.items() if name != chrom]
        sigma = max(MAD_SCALE * _mad(other_deltas), 0.02) if other_deltas else 0.02
        delta = raw_deltas[chrom]
        stats["depth_robust_sigma"] = sigma
        stats["depth_z"] = delta / sigma
        grouped: dict[int, list[DepthBin]] = defaultdict(list)
        for item in retained_by_chrom[chrom]:
            grouped[item.start // TEN_MB].append(item)
        directions: list[bool] = []
        for block_index, items in sorted(grouped.items()):
            retained_bases = sum(item.end - item.start for item in items)
            eligible = len(items) >= 5 and retained_bases >= 5_000_000
            ratio = _median([item.depth for item in items]) / float(stats["depth_baseline"])
            block_delta = ratio - 1.0
            concordant = (
                eligible
                and delta != 0
                and block_delta * delta > 0
                and _at_least(abs(block_delta), MIN_DEPTH_BLOCK_EFFECT)
            )
            if eligible:
                directions.append(concordant)
            block_stats[(chrom, block_index)] = {
                "depth_bin_count": len(items),
                "depth_retained_bases": retained_bases,
                "depth_ratio": ratio,
                "depth_ratio_delta": block_delta,
                "depth_direction_concordant": concordant if eligible else None,
                "depth_block_eligible": eligible,
            }
        stats["depth_block_concordance"] = (
            sum(directions) / len(directions) if directions else None
        )
    return chrom_stats, block_stats


def _run_bcftools_lines(command: list[str]) -> Iterator[str]:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise AnalysisError("bcftools unavailable") from exc
    assert process.stdout is not None
    try:
        for line in process.stdout:
            yield line.rstrip("\r\n")
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise AnalysisError("bcftools query failed")


def verify_single_sample(bcftools: str, vcf: Path) -> None:
    samples = [line for line in _run_bcftools_lines([bcftools, "query", "-l", str(vcf)]) if line]
    if len(samples) != 1:
        raise AnalysisError("VCF must contain exactly one sample")


def _parse_vcf_fields(line: str) -> tuple[str, int, str, int, int, list[int]] | None:
    fields = line.split("\t")
    if len(fields) != 6:
        raise AnalysisError("unexpected bcftools query output")
    chrom = _canonical_autosome(fields[0])
    if chrom is None:
        return None
    try:
        pos = int(fields[1])
        gt = fields[2].replace("|", "/")
        gt = "/".join(sorted(gt.split("/")))
        gq = int(fields[3]) if fields[3] != "." else -1
        dp = int(fields[4]) if fields[4] != "." else -1
        ad = [] if fields[5] == "." else [int(value) for value in fields[5].split(",")]
    except ValueError as exc:
        raise AnalysisError("malformed VCF sample field") from exc
    return chrom, pos, gt, gq, dp, ad


def _bcftools_query_command(bcftools: str, vcf: Path) -> list[str]:
    return [
        bcftools,
        "query",
        "-f",
        r"%CHROM\t%POS\t[%GT\t%GQ\t%DP\t%AD]\n",
        str(vcf),
    ]


def collect_baf(
    bcftools: str, vcf: Path
) -> tuple[dict[str, BafAccumulator], dict[tuple[str, int], BafAccumulator], float, int]:
    # Pass one estimates only the predeclared high-depth cap.  No site data are
    # materialized; only eligible heterozygote DP values are retained in memory.
    het_dps: list[int] = []
    for line in _run_bcftools_lines(_bcftools_query_command(bcftools, vcf)):
        parsed = _parse_vcf_fields(line)
        if parsed is None:
            continue
        _, _, gt, gq, dp, _ = parsed
        if gt == "0/1" and gq >= 30 and dp >= 10:
            het_dps.append(dp)
    if not het_dps:
        upper = 200.0
    else:
        center = _median(het_dps)
        upper = min(200.0, center + 6.0 * MAD_SCALE * _mad(het_dps, center))

    chromosomes = {chrom: BafAccumulator.empty() for chrom in AUTOSOMES}
    blocks: dict[tuple[str, int], BafAccumulator] = defaultdict(BafAccumulator.empty)
    accepted = 0
    # Pass two applies all filters and immediately reduces each record into
    # chromosome/10-Mb statistics; raw queried text is never persisted.
    for line in _run_bcftools_lines(_bcftools_query_command(bcftools, vcf)):
        parsed = _parse_vcf_fields(line)
        if parsed is None:
            continue
        chrom, pos, gt, gq, dp, ad = parsed
        if gt != "0/1" or gq < 30 or dp < 10 or dp > upper or len(ad) != 2:
            continue
        if min(ad) < 3 or sum(ad) < 10 or not 0.8 <= sum(ad) / dp <= 1.2:
            continue
        baf = ad[1] / sum(ad)
        if not 0.05 <= baf <= 0.95:
            continue
        chromosomes[chrom].add(dp, baf)
        blocks[(chrom, (pos - 1) // TEN_MB)].add(dp, baf)
        accepted += 1
    return chromosomes, blocks, upper, accepted


def summarize_baf(
    chromosomes: dict[str, BafAccumulator],
    blocks: dict[tuple[str, int], BafAccumulator],
) -> tuple[dict[str, dict[str, object]], dict[tuple[str, int], dict[str, object]]]:
    chrom_stats: dict[str, dict[str, object]] = {}
    block_stats: dict[tuple[str, int], dict[str, object]] = {}
    q90s: dict[str, float] = {}
    eligible_block_count: dict[str, int] = defaultdict(int)
    for key, accumulator in sorted(blocks.items()):
        summary = accumulator.summary()
        eligible = int(summary["site_count"]) >= MIN_BAF_BLOCK_SITES
        if eligible:
            eligible_block_count[key[0]] += 1
        block_stats[key] = {
            "baf_site_count": summary["site_count"],
            "baf_mean_dp": summary["mean_dp"],
            "baf_mean": summary["mean_baf"],
            "baf_median_abs_dev": summary["median_abs_dev"],
            "baf_q90_abs_dev": summary["q90_abs_dev"],
            "baf_block_eligible": eligible,
        }
    for chrom in AUTOSOMES:
        summary = chromosomes[chrom].summary()
        complete = (
            int(summary["site_count"]) >= MIN_BAF_SITES
            and eligible_block_count[chrom] >= MIN_BAF_BLOCKS
        )
        chrom_stats[chrom] = {
            "baf_site_count": summary["site_count"],
            "baf_mean_dp": summary["mean_dp"],
            "baf_mean": summary["mean_baf"],
            "baf_median_abs_dev": summary["median_abs_dev"],
            "baf_q90_abs_dev": summary["q90_abs_dev"],
            "baf_eligible_blocks": eligible_block_count[chrom],
            "baf_complete": complete,
        }
        if complete and summary["q90_abs_dev"] is not None:
            q90s[chrom] = float(summary["q90_abs_dev"])

    for chrom in AUTOSOMES:
        stats = chrom_stats[chrom]
        if chrom not in q90s:
            stats.update(
                baf_q90_baseline=None,
                baf_q90_delta_vs_baseline=None,
                baf_q90_robust_sigma=None,
                baf_q90_z=None,
                baf_block_concordance=None,
            )
            continue
        others = [value for name, value in q90s.items() if name != chrom]
        comparator_names = {name for name in q90s if name != chrom}
        if len(others) < MIN_COMPARATOR_AUTOSOMES:
            stats["baf_complete"] = False
            stats.update(
                baf_q90_baseline=None,
                baf_q90_delta_vs_baseline=None,
                baf_q90_robust_sigma=None,
                baf_q90_z=None,
                baf_block_concordance=None,
            )
            continue
        baseline = _median(others)
        delta = q90s[chrom] - baseline
        sigma = max(MAD_SCALE * _mad(others), 0.003)
        comparator_block_q90s = [
            float(block["baf_q90_abs_dev"])
            for (block_chrom, _), block in block_stats.items()
            if block_chrom in comparator_names
            and block["baf_block_eligible"]
            and block["baf_q90_abs_dev"] is not None
        ]
        if not comparator_block_q90s:
            stats["baf_complete"] = False
            continue
        block_baseline = _median(comparator_block_q90s)
        directions: list[bool] = []
        for (block_chrom, _), block in block_stats.items():
            if block_chrom != chrom or not block["baf_block_eligible"]:
                continue
            block_delta = float(block["baf_q90_abs_dev"]) - block_baseline
            concordant = (
                delta != 0
                and block_delta * delta > 0
                and _at_least(abs(block_delta), MIN_BAF_BLOCK_EFFECT)
            )
            block["baf_q90_delta_vs_baseline"] = block_delta
            block["baf_q90_eligible_block_baseline"] = block_baseline
            block["baf_direction_concordant"] = concordant
            directions.append(concordant)
        stats.update(
            baf_q90_baseline=baseline,
            baf_q90_delta_vs_baseline=delta,
            baf_q90_robust_sigma=sigma,
            baf_q90_z=delta / sigma,
            baf_block_concordance=sum(directions) / len(directions) if directions else None,
        )
    return chrom_stats, block_stats


def load_cnvpytor(path: Path, lengths: dict[str, int]) -> dict[str, dict[str, object]]:
    ratios: dict[str, list[float]] = {chrom: [] for chrom in AUTOSOMES}
    coordinates: dict[str, set[tuple[int, int]]] = defaultdict(set)
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"chrom", "start", "end", "ratio"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise AnalysisError("CNVpytor table header mismatch")
            for row in reader:
                chrom = _canonical_autosome(row["chrom"])
                if chrom is None:
                    raise AnalysisError("CNVpytor table contains a noncanonical contig")
                start, end, ratio = int(row["start"]), int(row["end"]), float(row["ratio"])
                expected_end = min(start + 100_000, lengths[chrom])
                if (
                    start < 0
                    or start % 100_000 != 0
                    or start >= lengths[chrom]
                    or end != expected_end
                    or (start, end) in coordinates[chrom]
                    or not math.isfinite(ratio)
                    or ratio <= 0
                ):
                    raise AnalysisError("invalid CNVpytor row")
                coordinates[chrom].add((start, end))
                ratios[chrom].append(ratio)
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, AnalysisError):
            raise
        raise AnalysisError("could not read CNVpytor table") from exc
    result: dict[str, dict[str, object]] = {}
    for chrom in AUTOSOMES:
        median_ratio = _median(ratios[chrom]) if ratios[chrom] else None
        expected_bins = math.ceil(lengths[chrom] / 100_000)
        represented_bases = sum(end - start for start, end in coordinates[chrom])
        complete = (
            len(ratios[chrom]) / expected_bins >= MIN_GENERATED_FRACTION
            and represented_bases >= MIN_RETAINED_BASES
        )
        if median_ratio is None:
            direction = "missing"
        elif _at_least(median_ratio - 1.0, MIN_CNV_RATIO_EFFECT):
            direction = "gain"
        elif _at_least(1.0 - median_ratio, MIN_CNV_RATIO_EFFECT):
            direction = "loss"
        else:
            direction = "neutral"
        result[chrom] = {
            "cnvpytor_bin_count": len(ratios[chrom]),
            "cnvpytor_expected_bins": expected_bins,
            "cnvpytor_represented_bases": represented_bases,
            "cnvpytor_median_ratio": median_ratio,
            "cnvpytor_direction": direction,
            "cnvpytor_complete": complete,
        }
    return result


def evidence_level(
    effect: float | None,
    z: float | None,
    concordance: float | None,
    strong: tuple[float, float, float],
    suggestive: tuple[float, float, float],
    *,
    absolute_effect: bool,
) -> str:
    """Apply inclusive prespecified boundaries; exposed for boundary tests."""
    if effect is None or z is None or concordance is None:
        return "incomplete"
    observed_effect = abs(effect) if absolute_effect else effect
    observed_z = abs(z) if absolute_effect else z
    if all(_at_least(value, threshold) for value, threshold in zip(
        (observed_effect, observed_z, concordance), strong
    )):
        return "strong"
    if all(_at_least(value, threshold) for value, threshold in zip(
        (observed_effect, observed_z, concordance), suggestive
    )):
        return "suggestive"
    return "none"


def _classify(
    depth: dict[str, object], baf: dict[str, object], cnv: dict[str, object]
) -> tuple[str, str, str, str]:
    if not depth["depth_complete"] or not baf["baf_complete"] or not cnv["cnvpytor_complete"]:
        return "INDETERMINATE", "required_lane_incomplete", "incomplete", "incomplete"
    depth_level = evidence_level(
        depth.get("depth_ratio_delta"), depth.get("depth_z"), depth.get("depth_block_concordance"),
        DEPTH_STRONG, DEPTH_SUGGESTIVE, absolute_effect=True,
    )
    baf_level = evidence_level(
        baf.get("baf_q90_delta_vs_baseline"), baf.get("baf_q90_z"), baf.get("baf_block_concordance"),
        BAF_STRONG, BAF_SUGGESTIVE, absolute_effect=False,
    )
    depth_delta = float(depth.get("depth_ratio_delta") or 0.0)
    expected_direction = "gain" if depth_delta > 0 else "loss" if depth_delta < 0 else "neutral"
    cnv_direction = str(cnv["cnvpytor_direction"])
    cnv_agrees = expected_direction != "neutral" and cnv_direction == expected_direction
    concordant = (
        (depth_level == "strong" and baf_level in {"strong", "suggestive"})
        or (baf_level == "strong" and depth_level == "suggestive")
    )
    if concordant:
        if cnv_agrees:
            return "CONCORDANT_RESEARCH_SIGNAL", "depth_baf_and_cnvpytor_direction_agree", depth_level, baf_level
        return "INDETERMINATE", "cnvpytor_direction_disagrees", depth_level, baf_level
    if depth_level in {"strong", "suggestive"} and baf_level == "none":
        reason = (
            "depth_only_with_cnvpytor_direction_support"
            if cnv_agrees
            else "depth_only_with_cnvpytor_direction_disagreement_or_neutrality"
        )
        return "DISCORDANT_DEPTH_ONLY", reason, depth_level, baf_level
    if baf_level in {"strong", "suggestive"} and depth_level == "none":
        reason = (
            "baf_only_possible_cnloh_or_bias_with_cnvpytor_direction_support"
            if cnv_agrees
            else "baf_only_possible_cnloh_or_bias_without_cnvpytor_direction_support"
        )
        return "DISCORDANT_BAF_ONLY_POSSIBLE_CNLOH_OR_BIAS", reason, depth_level, baf_level
    return "NO_SIGNAL_AT_PRESPECIFIED_THRESHOLD", "prespecified_thresholds_not_met", depth_level, baf_level


def _write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _fmt(row.get(field)) for field in fieldnames})
    os.replace(temporary, path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
        handle.write("\n")
    os.replace(temporary, path)


def analyze(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    if output_dir.exists() and (not output_dir.is_dir() or output_dir.is_symlink()):
        raise AnalysisError("invalid output directory")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_names = ("chromosome_summary.tsv", "block_summary.tsv", "methods.json", "runtime.json")
    if any((output_dir / name).exists() for name in output_names):
        raise AnalysisError("refusing to overwrite analysis output")
    declared = [Path(args.depth_tsv), Path(args.baf_vcf), Path(args.fai), Path(args.cnvpytor_rd_tsv)]
    if any(not path.is_file() or path.is_symlink() for path in declared):
        raise AnalysisError("declared input missing or unsafe")

    lengths, _ = load_fai(Path(args.fai))
    depth, depth_blocks = summarize_depth(load_depth(Path(args.depth_tsv), lengths))
    verify_single_sample(args.bcftools, Path(args.baf_vcf))
    baf_acc, baf_block_acc, dp_upper, accepted_sites = collect_baf(args.bcftools, Path(args.baf_vcf))
    baf, baf_blocks = summarize_baf(baf_acc, baf_block_acc)
    cnv = load_cnvpytor(Path(args.cnvpytor_rd_tsv), lengths)

    chromosome_rows: list[dict[str, object]] = []
    for chrom in AUTOSOMES:
        classification, reason, depth_level, baf_level = _classify(depth[chrom], baf[chrom], cnv[chrom])
        chromosome_rows.append({
            "chromosome": chrom,
            **depth[chrom],
            **baf[chrom],
            **cnv[chrom],
            "depth_evidence": depth_level,
            "baf_evidence": baf_level,
            "classification": classification,
            "classification_reason": reason,
        })
    chromosome_fields = [
        "chromosome", "depth_generated_bins", "depth_callable_bins", "depth_retained_bins",
        "depth_retained_bases", "depth_complete", "depth_median", "depth_baseline", "depth_ratio",
        "depth_ratio_delta", "depth_robust_sigma", "depth_z", "depth_block_concordance",
        "baf_site_count", "baf_mean_dp", "baf_mean", "baf_median_abs_dev", "baf_q90_abs_dev",
        "baf_q90_baseline", "baf_q90_delta_vs_baseline", "baf_q90_robust_sigma", "baf_q90_z",
        "baf_eligible_blocks", "baf_block_concordance", "baf_complete", "cnvpytor_bin_count",
        "cnvpytor_median_ratio", "cnvpytor_direction", "cnvpytor_complete", "depth_evidence",
        "cnvpytor_expected_bins", "cnvpytor_represented_bases", "baf_evidence", "classification", "classification_reason",
    ]

    block_rows: list[dict[str, object]] = []
    for chrom in AUTOSOMES:
        indices = sorted({index for c, index in depth_blocks if c == chrom} | {index for c, index in baf_blocks if c == chrom})
        for index in indices:
            block_rows.append({
                "chromosome": chrom,
                "block_start": index * TEN_MB,
                "block_end": min((index + 1) * TEN_MB, lengths[chrom]),
                **depth_blocks.get((chrom, index), {}),
                **baf_blocks.get((chrom, index), {}),
            })
    block_fields = [
        "chromosome", "block_start", "block_end", "depth_bin_count", "depth_retained_bases",
        "depth_ratio", "depth_ratio_delta", "depth_block_eligible", "depth_direction_concordant",
        "baf_site_count", "baf_mean_dp", "baf_mean", "baf_median_abs_dev", "baf_q90_abs_dev",
        "baf_q90_delta_vs_baseline", "baf_q90_eligible_block_baseline", "baf_block_eligible", "baf_direction_concordant",
    ]

    methods = {
        "schema": "mosaic-aneuploidy-research-screen/v1",
        "seed": args.seed,
        "autosomes": list(AUTOSOMES),
        "depth": {
            "bin_size_bases": ONE_MB,
            "block_size_bases": TEN_MB,
            "callable_definition": "bases with depth >=10 after MAPQ>=20 and excluded SAM flags 3844",
            "minimum_callable_fraction": MIN_CALLABLE_FRACTION,
            "minimum_generated_bin_fraction": MIN_GENERATED_FRACTION,
            "minimum_retained_bases": MIN_RETAINED_BASES,
            "localized_outlier_rule": "chromosome median +/- max(5*1.4826*MAD,0.25*median)",
            "sigma_floor": 0.02,
            "minimum_absolute_block_ratio_delta": MIN_DEPTH_BLOCK_EFFECT,
            "minimum_comparator_autosomes": MIN_COMPARATOR_AUTOSOMES,
        },
        "baf": {
            "vcf_queries": 2,
            "selection_conditioning": "The VCF is conditioned on heterozygous calls; empirical Q90 absolute BAF deviation is used instead of binomial-noise-corrected V/S, which can be underdispersed and clip to zero.",
            "genotype": "exactly 0/1 after separator/order normalization",
            "filters": {"gq_min": 30, "dp_min": 10, "dp_upper": dp_upper, "ad_each_min": 3, "ad_sum_min": 10, "ad_sum_dp_ratio": [0.8, 1.2], "baf_range": [0.05, 0.95]},
            "decision_statistic": "Q90(abs(ADalt/ADsum-0.5))",
            "minimum_sites_per_chromosome": MIN_BAF_SITES,
            "minimum_sites_per_block": MIN_BAF_BLOCK_SITES,
            "minimum_blocks": MIN_BAF_BLOCKS,
            "sigma_floor": 0.003,
            "minimum_absolute_block_q90_delta": MIN_BAF_BLOCK_EFFECT,
            "minimum_comparator_autosomes": MIN_COMPARATOR_AUTOSOMES,
            "balance_filter": False,
        },
        "thresholds": {
            "depth_strong": {"absolute_ratio_delta": 0.08, "absolute_z": 4.0, "concordance": 0.75},
            "depth_suggestive": {"absolute_ratio_delta": 0.05, "absolute_z": 3.0, "concordance": 0.65},
            "baf_strong": {"q90_delta": 0.010, "z": 4.0, "concordance": 0.70},
            "baf_suggestive": {"q90_delta": 0.006, "z": 3.0, "concordance": 0.60},
        },
        "cnvpytor": {"bin_size_bases": 100_000, "gc_corrected": True, "strict_mask": True, "minimum_bin_fraction": MIN_GENERATED_FRACTION, "minimum_represented_bases": MIN_RETAINED_BASES, "neutral_band_absolute_delta_lt": MIN_CNV_RATIO_EFFECT, "direction_agreement_required_for_promotion": True},
        "excluded_contigs": ["chrX", "chrY", "chrM/MT", "alternate/noncanonical"],
        "limitations": [
            "Research-only and non-diagnostic.",
            "Bulk blood WGS can miss low-fraction, balanced, or tissue-specific mosaic variegated aneuploidy.",
            "This screen cannot resolve variant phase.",
            "Cytogenetic and clinically validated orthogonal testing are required for confirmation.",
        ],
    }
    runtime = {
        "schema": "mosaic-aneuploidy-runtime/v1",
        "status": "complete_research_only",
        "seed": args.seed,
        "vcf_query_passes": 2,
        "accepted_baf_sites": accepted_sites,
        "chromosomes_reported": len(AUTOSOMES),
        "timestamps_omitted_for_determinism": True,
        "input_paths_recorded": False,
    }
    _write_tsv(output_dir / "chromosome_summary.tsv", chromosome_fields, chromosome_rows)
    _write_tsv(output_dir / "block_summary.tsv", block_fields, block_rows)
    _write_json(output_dir / "methods.json", methods)
    _write_json(output_dir / "runtime.json", runtime)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research-only chromosome mosaic-aneuploidy screen")
    parser.add_argument("--depth-tsv", required=True)
    parser.add_argument("--baf-vcf", required=True)
    parser.add_argument("--fai", required=True)
    parser.add_argument("--cnvpytor-rd-tsv", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sample-label", default="case")
    parser.add_argument("--bcftools", default="bcftools")
    parser.add_argument("--seed", type=int, default=20260829)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        analyze(args)
    except (AnalysisError, OSError, ValueError):
        print("mosaic_aneuploidy_status=failed_closed", file=sys.stderr)
        return 2
    print("mosaic_aneuploidy_status=complete_research_only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
