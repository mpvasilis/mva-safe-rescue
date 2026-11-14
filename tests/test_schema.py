"""Synthetic-only tests for the strict Track 1 schemas."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from rare_mva.track1.schema import COLUMNS, ValidationError, load_ground_truth, load_submission

FIXTURES = Path(__file__).parent / "fixtures"


def _reviewed_truth_variant(proband_id: str, index: int = 0) -> dict[str, object]:
    reviewed = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))
    return reviewed[proband_id][index]


def _variant_json(variant: dict[str, object]) -> str:
    return json.dumps(variant, separators=(",", ":"), sort_keys=True)


def _valid_row(**changes: str) -> dict[str, str]:
    row = {
        "proband_id": "SYNTHETIC_TEST_PROBAND",
        "chrom_1": "chr1",
        "pos_1": "111",
        "ref_1": "A",
        "alt_1": "T",
        "chrom_2": "",
        "pos_2": "",
        "ref_2": "",
        "alt_2": "",
        "epcr": "0.9",
        "finding_type": "primary",
        "notes": "SYNTHETIC ONLY",
    }
    row.update(changes)
    return row


def _write_submission(
    tmp_path: Path,
    rows: list[dict[str, str]],
    *,
    columns: tuple[str, ...] = COLUMNS,
) -> Path:
    path = tmp_path / "synthetic_submission.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_valid_single_fixture() -> None:
    submission = load_submission(FIXTURES / "valid_single.csv")
    assert submission.proband_id == "SYNTHETIC_PROBAND_SINGLE"
    assert len(submission.candidates) == 1
    assert len(submission.candidates[0].variants) == 1


def test_valid_compound_fixture() -> None:
    submission = load_submission(FIXTURES / "valid_compound.csv")
    assert submission.proband_id == "SYNTHETIC_PROBAND_COMPOUND"
    assert len(submission.candidates) == 3
    assert len(submission.candidates[1].variants) == 2


def test_exact_header_and_order_required(tmp_path: Path) -> None:
    reordered = (COLUMNS[1], COLUMNS[0], *COLUMNS[2:])
    path = _write_submission(tmp_path, [_valid_row()], columns=reordered)
    with pytest.raises(ValidationError, match="header must exactly match"):
        load_submission(path)


@pytest.mark.parametrize("row_count", [0, 11])
def test_row_limits(tmp_path: Path, row_count: int) -> None:
    rows = [
        _valid_row(
            pos_1=str(1000 + index),
            epcr=str(1.0 - index / 100),
        )
        for index in range(row_count)
    ]
    path = _write_submission(tmp_path, rows)
    with pytest.raises(ValidationError, match="between 1 and 10"):
        load_submission(path)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"chrom_1": "1"}, "chrom must be one of"),
        ({"pos_1": "0"}, "pos must be a positive integer"),
        ({"pos_1": "1.5"}, "pos must be a positive integer"),
        ({"ref_1": "a"}, "ref must contain only uppercase"),
        ({"alt_1": "A-"}, "alt must contain only uppercase"),
        ({"epcr": "0"}, "epcr must be numeric in"),
        ({"epcr": "1.01"}, "epcr must be numeric in"),
        ({"epcr": "nan"}, "epcr must be numeric in"),
        ({"epcr": "0.9_0"}, "epcr must be numeric in"),
    ],
)
def test_bad_variant_and_epcr_fields(
    tmp_path: Path, changes: dict[str, str], message: str
) -> None:
    path = _write_submission(tmp_path, [_valid_row(**changes)])
    with pytest.raises(ValidationError, match=message):
        load_submission(path)


def test_partial_variant_two_rejected(tmp_path: Path) -> None:
    path = _write_submission(tmp_path, [_valid_row(chrom_2="chr2")])
    with pytest.raises(ValidationError, match="either all blank or all populated"):
        load_submission(path)


def test_compound_candidate_must_use_two_different_variants(tmp_path: Path) -> None:
    path = _write_submission(
        tmp_path,
        [
            _valid_row(
                chrom_2="chr1",
                pos_2="111",
                ref_2="A",
                alt_2="T",
            )
        ],
    )
    with pytest.raises(ValidationError, match="variant_2 must differ from variant_1"):
        load_submission(path)


def test_duplicate_candidate_rejected_even_if_compound_order_is_swapped(
    tmp_path: Path,
) -> None:
    first = _valid_row(
        chrom_1="chr1",
        pos_1="111",
        ref_1="A",
        alt_1="T",
        chrom_2="chr2",
        pos_2="222",
        ref_2="G",
        alt_2="C",
        epcr="0.9",
    )
    swapped = _valid_row(
        chrom_1="chr2",
        pos_1="222",
        ref_1="G",
        alt_1="C",
        chrom_2="chr1",
        pos_2="111",
        ref_2="A",
        alt_2="T",
        epcr="0.8",
        notes="DIFFERENT SYNTHETIC NOTE",
    )
    path = _write_submission(tmp_path, [first, swapped])
    with pytest.raises(ValidationError, match="duplicates the complete candidate"):
        load_submission(path)


def test_mixed_probands_rejected(tmp_path: Path) -> None:
    rows = [
        _valid_row(pos_1="111", epcr="0.9"),
        _valid_row(
            proband_id="SYNTHETIC_OTHER_PROBAND", pos_1="222", epcr="0.8"
        ),
    ]
    path = _write_submission(tmp_path, rows)
    with pytest.raises(ValidationError, match="one shared proband_id"):
        load_submission(path)


def test_invalid_finding_type_rejected(tmp_path: Path) -> None:
    path = _write_submission(tmp_path, [_valid_row(finding_type="tertiary")])
    with pytest.raises(ValidationError, match="primary.*secondary"):
        load_submission(path)


def test_unsorted_epcr_rejected_but_ties_are_allowed(tmp_path: Path) -> None:
    unsorted = _write_submission(
        tmp_path,
        [
            _valid_row(pos_1="111", epcr="0.8"),
            _valid_row(pos_1="222", epcr="0.9"),
        ],
    )
    with pytest.raises(ValidationError, match="descending EPCR order"):
        load_submission(unsorted)

    tied_path = tmp_path / "tied"
    tied_path.mkdir()
    tied = _write_submission(
        tied_path,
        [
            _valid_row(pos_1="111", epcr="0.9"),
            _valid_row(pos_1="222", epcr="0.9"),
        ],
    )
    assert len(load_submission(tied).candidates) == 2


def test_standard_scientific_epcr_is_allowed(tmp_path: Path) -> None:
    path = _write_submission(tmp_path, [_valid_row(epcr="9.1e-1")])
    assert load_submission(path).candidates[0].epcr == pytest.approx(0.91)


def test_ground_truth_schema(tmp_path: Path) -> None:
    truth = load_ground_truth(FIXTURES / "ground_truth.json")
    assert set(truth) == {
        "SYNTHETIC_PROBAND_SINGLE",
        "SYNTHETIC_PROBAND_COMPOUND",
    }

    invalid = tmp_path / "invalid_truth.json"
    invalid.write_text(
        json.dumps(
            {
                "SYNTHETIC_BAD": [
                    {"chrom": "chr99", "pos": 1, "ref": "a", "alt": "T"}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_ground_truth(invalid)


def test_ground_truth_proband_id_whitespace_rejected(tmp_path: Path) -> None:
    path = tmp_path / "whitespace_truth.json"
    path.write_text(
        json.dumps(
            {
                " SYNTHETIC_BAD ": [
                    _reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE")
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="leading or trailing whitespace"):
        load_ground_truth(path)


@pytest.mark.parametrize(
    "contents",
    [
        (
            '{"SYNTHETIC_DUP": ['
            + _variant_json(_reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE"))
            + '], "SYNTHETIC_DUP": ['
            + _variant_json(_reviewed_truth_variant("SYNTHETIC_PROBAND_COMPOUND"))
            + "]}"
        ),
        (
            '{"SYNTHETIC_NESTED_DUP": [{"chrom": '
            + json.dumps(_reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE")["chrom"])
            + ', "chrom": '
            + json.dumps(_reviewed_truth_variant("SYNTHETIC_PROBAND_COMPOUND")["chrom"])
            + ', "pos": '
            + json.dumps(_reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE")["pos"])
            + ', "ref": '
            + json.dumps(_reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE")["ref"])
            + ', "alt": '
            + json.dumps(_reviewed_truth_variant("SYNTHETIC_PROBAND_SINGLE")["alt"])
            + "}]}"
        ),
    ],
)
def test_ground_truth_duplicate_json_keys_rejected(
    tmp_path: Path, contents: str
) -> None:
    path = tmp_path / "duplicate_keys.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValidationError, match="duplicate object key"):
        load_ground_truth(path)
