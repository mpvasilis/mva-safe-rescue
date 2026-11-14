from __future__ import annotations

import csv
import json
import math
import os
import stat
import sys
from pathlib import Path

import pytest

from analysis.secure_wgs import mosaic_aneuploidy_scan as scan


def _write_fai(path: Path, length: int = 20_000_000) -> None:
    path.write_text(
        "".join(f"chr{number}\t{length}\t0\t0\t0\n" for number in range(1, 23)),
        encoding="utf-8",
    )


def _write_depth(path: Path, *, signal: bool = False) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["chrom", "start", "end", "depth_sum", "callable_bases_ge10"])
        for number in range(1, 23):
            depth = 32.4 if signal and number == 1 else 30.0
            for start in range(0, 20_000_000, 1_000_000):
                writer.writerow([f"chr{number}", start, start + 1_000_000, int(depth * 1_000_000), 900_000])


def _write_cnvpytor(
    path: Path, *, signal: bool = False, base_ratio: float = 1.0
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["chrom", "start", "end", "ratio"])
        for number in range(1, 23):
            for start in range(0, 20_000_000, 100_000):
                writer.writerow([f"chr{number}", start, start + 100_000, 1.08 if signal and number == 1 else base_ratio])


def _write_fake_bcftools(directory: Path, *, signal: bool = False, samples: int = 1) -> Path:
    records = directory / "records.tsv"
    with records.open("w", encoding="utf-8", newline="") as handle:
        for number in range(1, 23):
            for block in range(4):
                for offset in range(3):
                    pos = block * 10_000_000 + 100 + offset
                    ad = "47,53" if signal and number == 1 else "49,51"
                    handle.write(f"chr{number}\t{pos}\t0|1\t40\t100\t{ad}\n")
    sample_file = directory / "samples.txt"
    sample_file.write_text("".join(f"synthetic{index}\n" for index in range(samples)), encoding="utf-8")
    program = directory / "fake_bcftools.py"
    program.write_text(
        "import pathlib, sys\n"
        "base = pathlib.Path(__file__).parent\n"
        "name = 'samples.txt' if '-l' in sys.argv else 'records.tsv'\n"
        "sys.stdout.write((base / name).read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        launcher = directory / "bcftools.cmd"
        launcher.write_text(f'@"{sys.executable}" "{program}" %*\r\n', encoding="utf-8")
    else:
        launcher = directory / "bcftools"
        launcher.write_text(f"#!{sys.executable}\nexec(open({str(program)!r}).read())\n", encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


def _run_synthetic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    signal: bool,
    output_name: str,
    samples: int = 1,
    sample_label: str = "case",
) -> tuple[int, Path]:
    # Keep CLI integration fixtures compact while exercising the exact filters,
    # baselines, thresholds, two-query stream, and output serialization.
    monkeypatch.setattr(scan, "MIN_BAF_SITES", 12)
    monkeypatch.setattr(scan, "MIN_BAF_BLOCK_SITES", 3)
    fai = tmp_path / "reference.fai"
    depth = tmp_path / "depth.tsv"
    cnv = tmp_path / "cnv.tsv"
    vcf = tmp_path / "synthetic.vcf.gz"
    _write_fai(fai)
    _write_depth(depth, signal=signal)
    _write_cnvpytor(cnv, signal=signal)
    vcf.write_bytes(b"synthetic-placeholder")
    bcftools = _write_fake_bcftools(tmp_path, signal=signal, samples=samples)
    output = tmp_path / output_name
    result = scan.main(
        [
            "--depth-tsv", str(depth),
            "--baf-vcf", str(vcf),
            "--fai", str(fai),
            "--cnvpytor-rd-tsv", str(cnv),
            "--output-dir", str(output),
            "--bcftools", str(bcftools),
            "--sample-label", sample_label,
        ]
    )
    return result, output


def _chromosome_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["chromosome"]: row for row in csv.DictReader(handle, delimiter="\t")}


def test_neutral_synthetic_case_and_deterministic_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_a, output_a = _run_synthetic(tmp_path, monkeypatch, signal=False, output_name="result-a")
    assert result_a == 0
    rows = _chromosome_rows(output_a / "chromosome_summary.tsv")
    assert set(rows) == set(scan.AUTOSOMES)
    assert {row["classification"] for row in rows.values()} == {"NO_SIGNAL_AT_PRESPECIFIED_THRESHOLD"}
    assert json.loads((output_a / "runtime.json").read_text(encoding="utf-8"))["vcf_query_passes"] == 2

    # Recreate the fake executable directory separately, then compare only the
    # four declared analyzer outputs byte-for-byte.
    second = tmp_path / "second"
    second.mkdir()
    result_b, output_b = _run_synthetic(second, monkeypatch, signal=False, output_name="result-b")
    assert result_b == 0
    for name in ("chromosome_summary.tsv", "block_summary.tsv", "methods.json", "runtime.json"):
        assert (output_a / name).read_bytes() == (output_b / name).read_bytes()


def test_concordant_synthetic_trisomy_like_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, output = _run_synthetic(tmp_path, monkeypatch, signal=True, output_name="result")
    assert result == 0
    rows = _chromosome_rows(output / "chromosome_summary.tsv")
    assert rows["chr1"]["depth_evidence"] == "strong"
    assert rows["chr1"]["baf_evidence"] == "strong"
    assert rows["chr1"]["cnvpytor_direction"] == "gain"
    assert rows["chr1"]["classification"] == "CONCORDANT_RESEARCH_SIGNAL"
    assert all(rows[f"chr{number}"]["classification"] == "NO_SIGNAL_AT_PRESPECIFIED_THRESHOLD" for number in range(2, 23))


def test_empirical_baf_spread_detects_conditioned_underdispersion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scan, "MIN_BAF_SITES", 9)
    monkeypatch.setattr(scan, "MIN_BAF_BLOCK_SITES", 3)
    chromosomes = {chrom: scan.BafAccumulator.empty() for chrom in scan.AUTOSOMES}
    blocks: dict[tuple[str, int], scan.BafAccumulator] = {}
    for chrom in scan.AUTOSOMES:
        ad_alt = 53 if chrom == "chr1" else 51
        baf = ad_alt / 100
        for block in range(3):
            accumulator = scan.BafAccumulator.empty()
            for _ in range(3):
                chromosomes[chrom].add(100, baf)
                accumulator.add(100, baf)
            blocks[(chrom, block)] = accumulator
    summaries, _ = scan.summarize_baf(chromosomes, blocks)
    # For n=100, both deviations have (A-n/2)^2-n/4 < 0 and the old V/S
    # statistic would clip to zero. Empirical Q90 correctly separates chr1.
    assert (53 - 50) ** 2 - 25 < 0
    assert summaries["chr1"]["baf_q90_delta_vs_baseline"] == pytest.approx(0.02)
    assert summaries["chr1"]["baf_q90_z"] > 4
    assert "V" not in summaries["chr1"] and "S" not in summaries["chr1"]


def test_exact_threshold_boundaries_are_inclusive() -> None:
    assert scan.evidence_level(0.08, -4.0, 0.75, scan.DEPTH_STRONG, scan.DEPTH_SUGGESTIVE, absolute_effect=True) == "strong"
    assert scan.evidence_level(0.010, 4.0, 0.70, scan.BAF_STRONG, scan.BAF_SUGGESTIVE, absolute_effect=False) == "strong"
    assert scan.evidence_level(0.05, 3.0, 0.65, scan.DEPTH_STRONG, scan.DEPTH_SUGGESTIVE, absolute_effect=True) == "suggestive"
    assert scan.evidence_level(0.006, 3.0, 0.60, scan.BAF_STRONG, scan.BAF_SUGGESTIVE, absolute_effect=False) == "suggestive"
    assert scan.evidence_level(0.079999, 4.0, 0.75, scan.DEPTH_STRONG, scan.DEPTH_SUGGESTIVE, absolute_effect=True) == "suggestive"


def test_malformed_or_insufficient_data_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fai = tmp_path / "reference.fai"
    _write_fai(fai)
    depth = tmp_path / "bad-depth.tsv"
    depth.write_text("chrom\tstart\nchr1\t0\n", encoding="utf-8")
    cnv = tmp_path / "cnv.tsv"
    _write_cnvpytor(cnv)
    vcf = tmp_path / "synthetic.vcf.gz"
    vcf.write_bytes(b"placeholder")
    bcftools = _write_fake_bcftools(tmp_path)
    output = tmp_path / "output"
    result = scan.main([
        "--depth-tsv", str(depth), "--baf-vcf", str(vcf), "--fai", str(fai),
        "--cnvpytor-rd-tsv", str(cnv), "--output-dir", str(output), "--bcftools", str(bcftools),
    ])
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err.strip() == "mosaic_aneuploidy_status=failed_closed"
    assert not output.exists() or not list(output.iterdir())


def test_vcf_single_sample_check_uses_fake_bcftools_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = _run_synthetic(tmp_path, monkeypatch, signal=False, output_name="output", samples=2)
    assert result == 2
    assert capsys.readouterr().err.strip() == "mosaic_aneuploidy_status=failed_closed"
    assert not (output / "chromosome_summary.tsv").exists()


def test_tiny_depth_and_baf_block_effects_do_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth_bins = {}
    for chrom in scan.AUTOSOMES:
        values = [30.0] * 20
        if chrom == "chr1":
            values = [30.87] * 10 + [33.0] * 10
        depth_bins[chrom] = [
            scan.DepthBin(chrom, index * 1_000_000, (index + 1) * 1_000_000, value, 0.9)
            for index, value in enumerate(values)
        ]
    depth, depth_blocks = scan.summarize_depth(depth_bins)
    assert depth_blocks[("chr1", 0)]["depth_ratio_delta"] == pytest.approx(0.029)
    assert depth_blocks[("chr1", 0)]["depth_direction_concordant"] is False
    assert depth["chr1"]["depth_block_concordance"] == pytest.approx(0.5)
    assert scan.evidence_level(
        depth["chr1"]["depth_ratio_delta"], depth["chr1"]["depth_z"],
        depth["chr1"]["depth_block_concordance"], scan.DEPTH_STRONG,
        scan.DEPTH_SUGGESTIVE, absolute_effect=True,
    ) == "none"

    monkeypatch.setattr(scan, "MIN_BAF_SITES", 12)
    monkeypatch.setattr(scan, "MIN_BAF_BLOCK_SITES", 3)
    chromosomes = {chrom: scan.BafAccumulator.empty() for chrom in scan.AUTOSOMES}
    baf_blocks = {}
    for chrom in scan.AUTOSOMES:
        for block_index in range(4):
            deviation = 0.01
            if chrom == "chr1":
                deviation = 0.014 if block_index < 3 else 0.03
            accumulator = scan.BafAccumulator.empty()
            for _ in range(3):
                chromosomes[chrom].add(100, 0.5 + deviation)
                accumulator.add(100, 0.5 + deviation)
            baf_blocks[(chrom, block_index)] = accumulator
    baf, summarized_blocks = scan.summarize_baf(chromosomes, baf_blocks)
    assert summarized_blocks[("chr1", 0)]["baf_q90_delta_vs_baseline"] == pytest.approx(0.004)
    # Same-sign differences below 0.005 do not count; only the single
    # sufficiently broadened block is concordant.
    assert summarized_blocks[("chr1", 0)]["baf_direction_concordant"] is False
    assert baf["chr1"]["baf_block_concordance"] == pytest.approx(0.25)
    assert scan.evidence_level(
        baf["chr1"]["baf_q90_delta_vs_baseline"], baf["chr1"]["baf_q90_z"],
        baf["chr1"]["baf_block_concordance"], scan.BAF_STRONG,
        scan.BAF_SUGGESTIVE, absolute_effect=False,
    ) == "none"


def test_cnvpytor_validation_sparse_duplicate_bounds_and_neutral_band(tmp_path: Path) -> None:
    fai = tmp_path / "reference.fai"
    _write_fai(fai)
    lengths, _ = scan.load_fai(fai)
    sparse = tmp_path / "sparse.tsv"
    with sparse.open("w", encoding="utf-8", newline="") as handle:
        handle.write("chrom\tstart\tend\tratio\n")
        for number in range(1, 23):
            handle.write(f"chr{number}\t0\t100000\t1.0\n")
    assert all(not row["cnvpytor_complete"] for row in scan.load_cnvpytor(sparse, lengths).values())

    duplicate = tmp_path / "duplicate.tsv"
    duplicate.write_text(
        "chrom\tstart\tend\tratio\nchr1\t0\t100000\t1.0\nchr1\t0\t100000\t1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(scan.AnalysisError):
        scan.load_cnvpytor(duplicate, lengths)
    out_of_bounds = tmp_path / "out.tsv"
    out_of_bounds.write_text(
        "chrom\tstart\tend\tratio\nchr1\t20000000\t20100000\t1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(scan.AnalysisError):
        scan.load_cnvpytor(out_of_bounds, lengths)

    neutral = tmp_path / "neutral.tsv"
    _write_cnvpytor(neutral, base_ratio=1.0049)
    neutral_rows = scan.load_cnvpytor(neutral, lengths)
    assert neutral_rows["chr1"]["cnvpytor_complete"] is True
    assert neutral_rows["chr1"]["cnvpytor_direction"] == "neutral"


def test_leave_one_out_requires_eighteen_complete_comparators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depth_bins = {}
    for index, chrom in enumerate(scan.AUTOSOMES):
        depth_bins[chrom] = [] if index >= 18 else [
            scan.DepthBin(chrom, bin_index * 1_000_000, (bin_index + 1) * 1_000_000, 30.0, 0.9)
            for bin_index in range(20)
        ]
    depth, _ = scan.summarize_depth(depth_bins)
    assert all(not depth[f"chr{number}"]["depth_complete"] for number in range(1, 19))

    monkeypatch.setattr(scan, "MIN_BAF_SITES", 9)
    monkeypatch.setattr(scan, "MIN_BAF_BLOCK_SITES", 3)
    chromosomes = {chrom: scan.BafAccumulator.empty() for chrom in scan.AUTOSOMES}
    blocks = {}
    for chrom in scan.AUTOSOMES[:18]:
        for block_index in range(3):
            accumulator = scan.BafAccumulator.empty()
            for _ in range(3):
                chromosomes[chrom].add(100, 0.51)
                accumulator.add(100, 0.51)
            blocks[(chrom, block_index)] = accumulator
    baf, _ = scan.summarize_baf(chromosomes, blocks)
    assert all(not baf[f"chr{number}"]["baf_complete"] for number in range(1, 19))


def test_exact_discordant_labels_and_cnvpytor_reasoning() -> None:
    base_depth = {"depth_complete": True, "depth_ratio_delta": 0.08, "depth_z": 4.0, "depth_block_concordance": 0.75}
    base_baf = {"baf_complete": True, "baf_q90_delta_vs_baseline": 0.0, "baf_q90_z": 0.0, "baf_block_concordance": 0.0}
    gain = {"cnvpytor_complete": True, "cnvpytor_direction": "gain"}
    label, reason, _, _ = scan._classify(base_depth, base_baf, gain)
    assert label == "DISCORDANT_DEPTH_ONLY"
    assert "support" in reason
    baf_only = {**base_baf, "baf_q90_delta_vs_baseline": 0.012, "baf_q90_z": 4.0, "baf_block_concordance": 0.70}
    no_depth = {**base_depth, "depth_ratio_delta": 0.0, "depth_z": 0.0, "depth_block_concordance": 0.0}
    label, reason, _, _ = scan._classify(no_depth, baf_only, gain)
    assert label == "DISCORDANT_BAF_ONLY_POSSIBLE_CNLOH_OR_BIAS"
    assert "without_cnvpytor_direction_support" in reason


def test_outputs_never_serialize_sample_label_or_input_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "PRIVATE_SAMPLE_LABEL_987"
    result, output = _run_synthetic(
        tmp_path, monkeypatch, signal=False, output_name="result", sample_label=secret
    )
    assert result == 0
    private_fragments = {secret, str(tmp_path), str(tmp_path).replace("\\", "/")}
    for name in ("chromosome_summary.tsv", "block_summary.tsv", "methods.json", "runtime.json"):
        text = (output / name).read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in private_fragments)


def test_runner_is_read_only_version_pinned_and_uses_logical_checksums() -> None:
    runner = (
        Path(__file__).resolve().parents[1]
        / "analysis" / "secure_wgs" / "remote" / "run_mosaic_aneuploidy_scan.sh"
    ).read_text(encoding="utf-8")
    assert "set -Eeuo pipefail" in runner and "umask 077" in runner
    assert "samtools bedcov -Q 20 -G 3844 -d 10" in runner
    assert "bcftools index --stats" in runner and "bcftools index --check" not in runner
    assert "samtools 1.13" in runner and "bcftools 1.13" in runner and 'version == "1.3.2"' in runner
    assert "--cnvpytor-pythonpath" in runner
    assert "IO(pytor_path, ro=True)" in runner
    assert "signal_flags = FLAG_GC_CORR | FLAG_USEMASK" in runner
    assert "normal_gc_raw = io.rd_normal_level(100000, FLAG_GC_CORR)" in runner
    assert "normal_combined_raw = io.rd_normal_level(100000, signal_flags)" in runner
    assert 'io.get_signal(name, 100000, "RD", signal_flags)' in runner
    assert "value/normal_gc" in runner
    assert '"normalization_flag": "FLAG_GC_CORR"' in runner
    assert '"signal_flags": "FLAG_GC_CORR|FLAG_USEMASK"' in runner
    assert 'cnvpytor_normalization["post_read_sha256_matched"] = True' in runner
    assert "Root(" not in runner and "calculate_histograms" not in runner
    assert '[[ "$(sha256_of "${cnvpytor_pyt}")" == "${cnvpytor_before_sha256}" ]]' in runner
    assert "inputs.sha256" in runner and "CHECKSUMS.sha256" in runner
    assert 'printf \'%s  %s\\n\' "$(sha256_of "${bam}")" bam' in runner
    assert "sha256sum chromosome_summary.tsv methods.json runtime.json inputs.sha256" in runner
    assert 'find "${output_dir}" -maxdepth' not in runner
    assert "bcftools query" not in runner  # analyzer streams both queries itself


def _normal_level_diagnostic(
    gc: tuple[float, float], combined: tuple[float, ...]
) -> str:
    normal_gc, spread_gc = map(float, gc)
    assert math.isfinite(normal_gc) and normal_gc > 0
    assert math.isfinite(spread_gc) and spread_gc >= 0
    if not combined:
        return "zero_or_missing_allowed"
    normal_combined = float(combined[0])
    assert math.isfinite(normal_combined) and normal_combined >= 0
    spread_combined = float(combined[1]) if len(combined) > 1 else None
    if normal_combined == 0:
        return "zero_or_missing_allowed"
    assert spread_combined is not None and math.isfinite(spread_combined)
    assert math.isclose(normal_combined, normal_gc, rel_tol=1e-9, abs_tol=1e-6)
    assert math.isclose(spread_combined, spread_gc, rel_tol=1e-9, abs_tol=1e-6)
    return "matched"


def test_cnvpytor_normal_level_diagnostic_zero_equal_and_disagreement() -> None:
    gc = (32012.859108995246, 4112.25)
    assert _normal_level_diagnostic(gc, ()) == "zero_or_missing_allowed"
    assert _normal_level_diagnostic(gc, (0.0, 0.0)) == "zero_or_missing_allowed"
    assert _normal_level_diagnostic(gc, gc) == "matched"
    with pytest.raises(AssertionError):
        _normal_level_diagnostic(gc, (32080.629026033115, 4112.25))
    with pytest.raises(AssertionError):
        _normal_level_diagnostic(gc, (gc[0], gc[1] + 0.01))
