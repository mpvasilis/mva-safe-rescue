"""Synthetic-only tests for the local Track 1 candidate builder."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest

from rare_mva.cli import main
from rare_mva.track1.builder import BuilderError, build_track1
from rare_mva.track1.schema import COLUMNS, load_submission

FIXTURES = Path(__file__).parent / "fixtures"


def _variant(position: int, chrom: str = "chr1") -> dict[str, Any]:
    return {"chrom": chrom, "pos": position, "ref": "A", "alt": "T"}


def _candidate(
    position: int = 10101,
    *,
    variants: list[dict[str, Any]] | None = None,
    raw_epcr: Any = 0.9,
    read_validated: Any = True,
    frequency_status: Any = "known",
    phase: Any = "not_applicable",
    notes: Any = "SYNTHETIC ONLY",
) -> dict[str, Any]:
    return {
        "variants": variants if variants is not None else [_variant(position)],
        "raw_epcr": raw_epcr,
        "finding_type": "primary",
        "notes": notes,
        "read_validated": read_validated,
        "frequency_status": frequency_status,
        "phase": phase,
    }


def _document(candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "proband_id": "SYNTHETIC_BUILDER_TEST",
        "calibration": "synthetic_only",
        "candidates": candidates if candidates is not None else [_candidate()],
    }


def _layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    public_root = tmp_path / "public_checkout"
    public_root.mkdir()
    local_root = tmp_path / "local_workspace"
    local_root.mkdir()
    source = public_root / "synthetic_candidates.json"
    output = local_root / "synthetic_submission.csv"
    return public_root, source, output


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _build(
    tmp_path: Path, document: dict[str, Any]
) -> tuple[Path, list[dict[str, str]]]:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, document)
    build_track1(source, output, public_root=public_root)
    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return output, rows


def test_fixture_builds_exact_header_and_passes_existing_validator(
    tmp_path: Path,
) -> None:
    local_root = tmp_path / "local_workspace"
    local_root.mkdir()
    output = local_root / "submission.csv"
    submission = build_track1(
        FIXTURES / "valid_candidates.json",
        output,
        public_root=Path.cwd(),
    )
    assert output.read_text(encoding="utf-8").splitlines()[0] == ",".join(COLUMNS)
    assert submission == load_submission(output)
    assert len(submission.candidates) == 2


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (_candidate(raw_epcr=0.95), 0.80),
        (_candidate(raw_epcr=0.79, read_validated=False), 0.75),
        (_candidate(raw_epcr=0.79, frequency_status="unknown"), 0.50),
        (
            _candidate(
                variants=[_variant(10101), _variant(20202, "chr2")],
                raw_epcr=0.79,
                phase="unresolved",
            ),
            0.55,
        ),
        (
            _candidate(
                variants=[_variant(10101), _variant(20202, "chr2")],
                raw_epcr=0.79,
                phase="confirmed_trans",
            ),
            0.79,
        ),
        (
            _candidate(
                variants=[_variant(10101), _variant(20202, "chr2")],
                raw_epcr=0.79,
                phase="probable_trans",
            ),
            0.79,
        ),
        (
            _candidate(
                variants=[_variant(10101), _variant(20202, "chr2")],
                raw_epcr=0.99,
                read_validated=False,
                frequency_status="unknown",
                phase="unresolved",
            ),
            0.50,
        ),
    ],
)
def test_provisional_caps_and_precedence(
    tmp_path: Path, candidate: dict[str, Any], expected: float
) -> None:
    output, _ = _build(tmp_path, _document([candidate]))
    assert load_submission(output).candidates[0].epcr == pytest.approx(expected)


def test_epcr_has_deterministic_six_significant_digit_serialization(
    tmp_path: Path,
) -> None:
    _, rows = _build(tmp_path, _document([_candidate(raw_epcr=0.123456789)]))
    assert rows[0]["epcr"] == "0.123457"


def test_stable_sort_preserves_input_order_when_caps_tie(tmp_path: Path) -> None:
    _, rows = _build(
        tmp_path,
        _document(
            [
                _candidate(position=30303, raw_epcr=0.93),
                _candidate(position=10101, raw_epcr=0.94),
                _candidate(position=20202, raw_epcr=0.70),
            ]
        ),
    )
    assert [row["pos_1"] for row in rows] == ["30303", "10101", "20202"]
    assert [row["epcr"] for row in rows] == ["0.80", "0.80", "0.7"]


def test_serialized_epcr_ties_preserve_input_order(tmp_path: Path) -> None:
    _, rows = _build(
        tmp_path,
        _document(
            [
                _candidate(position=10101, raw_epcr=0.12345641),
                _candidate(position=20202, raw_epcr=0.12345649),
            ]
        ),
    )
    assert [row["pos_1"] for row in rows] == ["10101", "20202"]
    assert [row["epcr"] for row in rows] == ["0.123456", "0.123456"]


def test_epcr_must_remain_positive_in_existing_float_validator(
    tmp_path: Path,
) -> None:
    public_root, source, output = _layout(tmp_path)
    source.write_text(
        json.dumps(_document()).replace('"raw_epcr": 0.9', '"raw_epcr": 1e-324'),
        encoding="utf-8",
    )
    with pytest.raises(BuilderError, match="raw_epcr.not_float_representable"):
        build_track1(source, output, public_root=public_root)
    assert not output.exists()


def test_compound_variants_are_written_in_genomic_order(tmp_path: Path) -> None:
    _, rows = _build(
        tmp_path,
        _document(
            [
                _candidate(
                    variants=[_variant(90909, "chrM"), _variant(80808, "chr2")],
                    phase="confirmed_trans",
                )
            ]
        ),
    )
    assert (rows[0]["chrom_1"], rows[0]["pos_1"]) == ("chr2", "80808")
    assert (rows[0]["chrom_2"], rows[0]["pos_2"]) == ("chrM", "90909")


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda value: value.update({"extra": True}), "top_level.keys"),
        (lambda value: value.update({"proband_id": " SYNTHETIC "}), "surrounding_whitespace"),
        (lambda value: value.update({"calibration": "uncalibrated"}), "calibration.value"),
        (lambda value: value.update({"candidates": []}), "candidates.count"),
        (lambda value: value["candidates"][0].update({"extra": True}), "candidate[1].keys"),
        (lambda value: value["candidates"][0].update({"raw_epcr": True}), "raw_epcr.type"),
        (lambda value: value["candidates"][0].update({"raw_epcr": 0}), "raw_epcr.range"),
        (lambda value: value["candidates"][0].update({"read_validated": 1}), "read_validated.type"),
        (lambda value: value["candidates"][0]["variants"][0].update({"extra": 1}), "variant[1].keys"),
        (lambda value: value["candidates"][0]["variants"][0].update({"pos": True}), "pos.type"),
    ],
)
def test_strict_document_keys_and_types(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], Any],
    code: str,
) -> None:
    public_root, source, output = _layout(tmp_path)
    value = deepcopy(_document())
    mutate(value)
    _write_json(source, value)
    with pytest.raises(BuilderError) as caught:
        build_track1(source, output, public_root=public_root)
    assert any(code in message for message in caught.value.messages)
    assert not output.exists()


@pytest.mark.parametrize("count", [0, 3])
def test_variant_count_is_one_or_two(tmp_path: Path, count: int) -> None:
    candidate = _candidate(variants=[_variant(10000 + index) for index in range(count)])
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document([candidate]))
    with pytest.raises(BuilderError, match="variants.count"):
        build_track1(source, output, public_root=public_root)


def test_duplicate_compound_member_is_rejected(tmp_path: Path) -> None:
    repeated = _variant(10101)
    candidate = _candidate(
        variants=[repeated, deepcopy(repeated)],
        phase="confirmed_trans",
    )
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document([candidate]))
    with pytest.raises(BuilderError, match="duplicate_member"):
        build_track1(source, output, public_root=public_root)


def test_duplicate_candidate_set_ignores_compound_input_order(tmp_path: Path) -> None:
    left = _variant(10101)
    right = _variant(20202, "chr2")
    candidates = [
        _candidate(variants=[left, right], phase="confirmed_trans"),
        _candidate(variants=[deepcopy(right), deepcopy(left)], phase="probable_trans"),
    ]
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document(candidates))
    with pytest.raises(BuilderError, match="duplicate_variant_set"):
        build_track1(source, output, public_root=public_root)


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (
            _candidate(
                variants=[_variant(10101), _variant(20202, "chr2")],
                phase="cis",
            ),
            "cis_not_allowed",
        ),
        (_candidate(notes="SYNTHETIC\nONLY"), "notes.line_break"),
        (_candidate(phase="unresolved"), "phase.single"),
    ],
)
def test_phase_and_note_rules(
    tmp_path: Path, candidate: dict[str, Any], code: str
) -> None:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document([candidate]))
    with pytest.raises(BuilderError, match=code):
        build_track1(source, output, public_root=public_root)


def test_duplicate_json_key_and_nonstandard_number_are_rejected(tmp_path: Path) -> None:
    public_root, source, output = _layout(tmp_path)
    source.write_text(
        '{"proband_id":"SYNTHETIC","proband_id":"SYNTHETIC_2",'
        '"calibration":"synthetic_only","candidates":[]}',
        encoding="utf-8",
    )
    with pytest.raises(BuilderError, match="duplicate_key"):
        build_track1(source, output, public_root=public_root)

    source.write_text(
        '{"proband_id":"SYNTHETIC","calibration":"synthetic_only",'
        '"candidates":[{"variants":[],"raw_epcr":NaN}]}',
        encoding="utf-8",
    )
    with pytest.raises(BuilderError, match="nonstandard_number"):
        build_track1(source, output, public_root=public_root)


def test_output_inside_or_equal_public_root_is_refused_before_input_read(
    tmp_path: Path,
) -> None:
    public_root = tmp_path / "public_checkout"
    public_root.mkdir()
    missing_source = public_root / "missing.json"
    for destination in (public_root, public_root / "output.csv"):
        with pytest.raises(BuilderError, match="inside_public_root"):
            build_track1(missing_source, destination, public_root=public_root)


def test_output_parent_must_already_exist(tmp_path: Path) -> None:
    public_root = tmp_path / "public_checkout"
    public_root.mkdir()
    source = public_root / "synthetic.json"
    _write_json(source, _document())
    output = tmp_path / "missing_parent" / "output.csv"
    with pytest.raises(BuilderError, match="parent_missing"):
        build_track1(source, output, public_root=public_root)
    assert not output.parent.exists()


def test_output_symlink_or_symlinked_ancestor_is_refused(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document())
    target = tmp_path_factory.mktemp("synthetic_output_target") / "submission.csv"
    target.write_text("SYNTHETIC PLACEHOLDER", encoding="utf-8")
    link = output.parent / "linked.csv"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create file symlinks: {exc}")
    with pytest.raises(BuilderError, match="link_or_reparse"):
        build_track1(source, link, public_root=public_root)

    ancestor_target = tmp_path_factory.mktemp("synthetic_ancestor_target")
    ancestor_link = tmp_path / "linked_parent"
    ancestor_link.symlink_to(ancestor_target, target_is_directory=True)
    with pytest.raises(BuilderError, match="link_or_reparse"):
        build_track1(
            source,
            ancestor_link / "submission.csv",
            public_root=public_root,
        )


def test_existing_regular_output_is_atomically_replaced(tmp_path: Path) -> None:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document())
    output.write_text("SYNTHETIC OLD CONTENT", encoding="utf-8")
    build_track1(source, output, public_root=public_root)
    assert output.read_text(encoding="utf-8").startswith("proband_id,")
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_atomic_failure_preserves_output_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document())
    output.write_text("SYNTHETIC OLD CONTENT", encoding="utf-8")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("SYNTHETIC REPLACE FAILURE")

    monkeypatch.setattr("rare_mva.track1.builder.os.replace", fail_replace)
    with pytest.raises(BuilderError, match="output.write_failed"):
        build_track1(source, output, public_root=public_root)
    assert output.read_text(encoding="utf-8") == "SYNTHETIC OLD CONTENT"
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))


def test_parent_swap_after_validation_writes_no_candidate_content_to_public_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root, source, output = _layout(tmp_path)
    _write_json(source, _document())
    output.write_text("SYNTHETIC OLD CONTENT", encoding="utf-8")
    public_sink = public_root / "race_sink"
    public_sink.mkdir()
    original_parent = output.parent
    moved_parent = tmp_path / "moved_local_workspace"
    original_mkstemp = __import__("tempfile").mkstemp
    swap_succeeded = False

    def racing_mkstemp(*, prefix: str, suffix: str, dir: Path) -> tuple[int, str]:
        nonlocal swap_succeeded
        try:
            original_parent.rename(moved_parent)
            try:
                original_parent.symlink_to(public_sink, target_is_directory=True)
            except OSError:
                moved_parent.rename(original_parent)
                raise
            swap_succeeded = True
        except OSError as exc:
            raise OSError("SYNTHETIC PARENT SWAP BLOCKED") from exc
        return original_mkstemp(prefix=prefix, suffix=suffix, dir=dir)

    monkeypatch.setattr("rare_mva.track1.builder.tempfile.mkstemp", racing_mkstemp)
    with pytest.raises(BuilderError):
        build_track1(source, output, public_root=public_root)

    assert list(public_sink.iterdir()) == []
    if swap_succeeded:
        original_parent.rmdir()
        moved_parent.rename(original_parent)
    assert output.read_text(encoding="utf-8") == "SYNTHETIC OLD CONTENT"
    assert not list(original_parent.glob(f".{output.name}.*.tmp"))


def test_build_cli_success_and_quiet_do_not_leak_sensitive_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public_root, source, output = _layout(tmp_path)
    value = _document()
    value["proband_id"] = "SYNTHETIC_SECRET_IDENTIFIER"
    value["candidates"][0]["notes"] = "SYNTHETIC SECRET NOTE"
    _write_json(source, value)

    assert main(
        [
            "build-track1",
            str(source),
            str(output),
            "--public-root",
            str(public_root),
        ]
    ) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "candidate_count": 1}
    assert "IDENTIFIER" not in captured.out
    assert "10101" not in captured.out
    assert str(output.resolve()) not in captured.out
    assert captured.err == ""

    assert main(
        [
            "build-track1",
            str(source),
            str(output),
            "--public-root",
            str(public_root),
            "--quiet",
        ]
    ) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_build_cli_error_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    public_root, source, output = _layout(tmp_path)
    value = _document()
    value["proband_id"] = "SYNTHETIC_SECRET_IDENTIFIER"
    value["candidates"][0]["notes"] = "SYNTHETIC SECRET NOTE\nSECOND LINE"
    _write_json(source, value)
    assert main(
        [
            "build-track1",
            str(source),
            str(output),
            "--public-root",
            str(public_root),
        ]
    ) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error"] == "build_failed"
    for forbidden in (
        "SYNTHETIC_SECRET_IDENTIFIER",
        "SYNTHETIC SECRET NOTE",
        "10101",
        str(output.resolve()),
    ):
        assert forbidden not in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("field", ["proband_id", "notes"])
def test_cli_subprocess_rejects_unpaired_surrogate_as_json_without_leakage(
    tmp_path: Path,
    field: str,
) -> None:
    public_root, source, output = _layout(tmp_path)
    value = _document()
    if field == "proband_id":
        value["proband_id"] = "SYNTHETIC_LEAK\ud800IDENTIFIER"
    else:
        value["candidates"][0]["notes"] = "SYNTHETIC_LEAK\ud800NOTE"
    _write_json(source, value)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rare_mva",
            "build-track1",
            str(source),
            str(output),
            "--public-root",
            str(public_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["error"] == "build_failed"
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "SYNTHETIC_LEAK" not in result.stderr
    assert "10101" not in result.stderr
    assert str(source.resolve()) not in result.stderr
    assert str(output.resolve()) not in result.stderr
