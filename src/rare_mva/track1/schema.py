"""Strict input schemas for Track 1 submissions and ground truth."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping

COLUMNS: Final[tuple[str, ...]] = (
    "proband_id",
    "chrom_1",
    "pos_1",
    "ref_1",
    "alt_1",
    "chrom_2",
    "pos_2",
    "ref_2",
    "alt_2",
    "epcr",
    "finding_type",
    "notes",
)

VALID_CHROMOSOMES: Final[frozenset[str]] = frozenset(
    [*(f"chr{number}" for number in range(1, 23)), "chrX", "chrY", "chrM"]
)
VALID_FINDING_TYPES: Final[frozenset[str]] = frozenset({"primary", "secondary"})
_ALLELE_RE: Final[re.Pattern[str]] = re.compile(r"[ACGTN]+")
_POSITION_RE: Final[re.Pattern[str]] = re.compile(r"[0-9]+")
_EPCR_RE: Final[re.Pattern[str]] = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?"
)


class ValidationError(ValueError):
    """Raised when a submission or ground-truth document violates its contract."""

    def __init__(self, messages: list[str] | tuple[str, ...] | str) -> None:
        if isinstance(messages, str):
            normalized = (messages,)
        else:
            normalized = tuple(messages)
        self.messages = normalized
        super().__init__("; ".join(normalized))


@dataclass(frozen=True, order=True)
class Variant:
    """A normalized genomic variant used by the public-compatible scorer."""

    chrom: str
    pos: int
    ref: str
    alt: str


@dataclass(frozen=True)
class Candidate:
    """One ranked candidate containing one or two variants."""

    variants: tuple[Variant, ...]
    epcr: float
    finding_type: str
    notes: str


@dataclass(frozen=True)
class Submission:
    """A validated Track 1 submission for exactly one proband."""

    proband_id: str
    candidates: tuple[Candidate, ...]


GroundTruth = dict[str, tuple[Variant, ...]]


def _read_csv_rows(path: Path) -> list[list[str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValidationError(f"could not read submission CSV: {exc}") from exc


def _parse_position(value: str, label: str, errors: list[str]) -> int | None:
    if not _POSITION_RE.fullmatch(value):
        errors.append(f"{label} must be a positive integer")
        return None
    position = int(value)
    if position <= 0:
        errors.append(f"{label} must be a positive integer")
        return None
    return position


def _validate_variant_fields(
    chrom: str,
    pos: str,
    ref: str,
    alt: str,
    label: str,
    errors: list[str],
) -> Variant | None:
    valid = True
    if chrom not in VALID_CHROMOSOMES:
        errors.append(f"{label}.chrom must be one of chr1..chr22, chrX, chrY, chrM")
        valid = False
    parsed_position = _parse_position(pos, f"{label}.pos", errors)
    if parsed_position is None:
        valid = False
    if not _ALLELE_RE.fullmatch(ref):
        errors.append(f"{label}.ref must contain only uppercase A/C/G/T/N")
        valid = False
    if not _ALLELE_RE.fullmatch(alt):
        errors.append(f"{label}.alt must contain only uppercase A/C/G/T/N")
        valid = False
    if not valid or parsed_position is None:
        return None
    return Variant(chrom=chrom, pos=parsed_position, ref=ref, alt=alt)


def _parse_epcr(value: str, label: str, errors: list[str]) -> float | None:
    if not _EPCR_RE.fullmatch(value):
        errors.append(f"{label} must be numeric in (0, 1]")
        return None
    try:
        epcr = float(value)
    except ValueError:
        errors.append(f"{label} must be numeric in (0, 1]")
        return None
    if not math.isfinite(epcr) or not 0.0 < epcr <= 1.0:
        errors.append(f"{label} must be numeric in (0, 1]")
        return None
    return epcr


def load_submission(path: str | Path) -> Submission:
    """Read and strictly validate a Track 1 CSV submission.

    All validation errors found after the header is accepted are reported together.
    Values are stripped of surrounding whitespace before field validation.
    """

    csv_path = Path(path)
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise ValidationError("submission CSV is empty; expected the exact Track 1 header")
    if tuple(rows[0]) != COLUMNS:
        expected = ",".join(COLUMNS)
        actual = ",".join(rows[0])
        raise ValidationError(
            f"header must exactly match the required ordered columns; "
            f"expected '{expected}', got '{actual}'"
        )

    data_rows = rows[1:]
    if not 1 <= len(data_rows) <= 10:
        raise ValidationError("submission must contain between 1 and 10 candidate rows")

    errors: list[str] = []
    candidates: list[Candidate] = []
    proband_ids: list[str] = []
    candidate_signatures: dict[tuple[Variant, ...], int] = {}

    for row_index, raw_row in enumerate(data_rows, start=2):
        label = f"row {row_index}"
        if len(raw_row) != len(COLUMNS):
            errors.append(
                f"{label} must contain exactly {len(COLUMNS)} fields; got {len(raw_row)}"
            )
            continue

        values = [value.strip() for value in raw_row]
        row = dict(zip(COLUMNS, values, strict=True))
        proband_id = row["proband_id"]
        if not proband_id:
            errors.append(f"{label}.proband_id must be nonempty")
        else:
            proband_ids.append(proband_id)

        first = _validate_variant_fields(
            row["chrom_1"],
            row["pos_1"],
            row["ref_1"],
            row["alt_1"],
            f"{label}.variant_1",
            errors,
        )

        second_values = (row["chrom_2"], row["pos_2"], row["ref_2"], row["alt_2"])
        populated_second = sum(bool(value) for value in second_values)
        second: Variant | None = None
        if populated_second not in (0, 4):
            errors.append(f"{label}.variant_2 fields must be either all blank or all populated")
        elif populated_second == 4:
            second = _validate_variant_fields(
                *second_values,
                f"{label}.variant_2",
                errors,
            )

        epcr = _parse_epcr(row["epcr"], f"{label}.epcr", errors)
        finding_type = row["finding_type"]
        if finding_type not in VALID_FINDING_TYPES:
            errors.append(f"{label}.finding_type must be 'primary' or 'secondary'")

        if first is not None and populated_second in (0, 4) and (
            populated_second == 0 or second is not None
        ):
            variants = (first,) if second is None else (first, second)
            if second is not None and first == second:
                errors.append(
                    f"{label}.variant_2 must differ from variant_1"
                )
            else:
                signature = tuple(sorted(variants))
                duplicate_row = candidate_signatures.get(signature)
                if duplicate_row is not None:
                    errors.append(
                        f"{label} duplicates the complete candidate variant set "
                        f"from row {duplicate_row}"
                    )
                else:
                    candidate_signatures[signature] = row_index

                if epcr is not None and finding_type in VALID_FINDING_TYPES:
                    candidates.append(
                        Candidate(
                            variants=variants,
                            epcr=epcr,
                            finding_type=finding_type,
                            notes=row["notes"],
                        )
                    )

    unique_probands = set(proband_ids)
    if len(unique_probands) > 1:
        errors.append("all candidate rows must use one shared proband_id")

    # Compare valid EPCR values in physical row order, independent of other errors.
    epcr_values: list[tuple[int, float]] = []
    for row_index, raw_row in enumerate(data_rows, start=2):
        if len(raw_row) != len(COLUMNS):
            continue
        value = raw_row[COLUMNS.index("epcr")].strip()
        parsed = _parse_epcr(value, f"row {row_index}.epcr", [])
        if parsed is not None:
            epcr_values.append((row_index, parsed))
    for (previous_row, previous), (current_row, current) in zip(
        epcr_values, epcr_values[1:]
    ):
        if current > previous:
            errors.append(
                f"row {current_row}.epcr must not exceed row {previous_row}.epcr; "
                "candidates must be in descending EPCR order"
            )

    if errors:
        raise ValidationError(errors)

    # The nonempty/shared checks guarantee this when validation succeeds.
    return Submission(proband_id=proband_ids[0], candidates=tuple(candidates))


def _validate_truth_variant(value: Any, label: str, errors: list[str]) -> Variant | None:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object with chrom, pos, ref, alt")
        return None
    expected_keys = {"chrom", "pos", "ref", "alt"}
    if set(value) != expected_keys:
        errors.append(f"{label} must contain exactly chrom, pos, ref, alt")
        return None
    chrom = value["chrom"]
    pos = value["pos"]
    ref = value["ref"]
    alt = value["alt"]
    if not isinstance(chrom, str) or not isinstance(ref, str) or not isinstance(alt, str):
        errors.append(f"{label}.chrom/ref/alt must be strings")
        return None
    if isinstance(pos, bool) or not isinstance(pos, int):
        errors.append(f"{label}.pos must be a positive integer")
        return None
    return _validate_variant_fields(chrom, str(pos), ref, alt, label, errors)


class _DuplicateJsonKeyError(ValueError):
    """Internal sentinel raised for any duplicate JSON object key."""


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting duplicate keys at every depth."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError("ground-truth JSON contains a duplicate object key")
        result[key] = value
    return result


def load_ground_truth(path: str | Path) -> GroundTruth:
    """Read and validate a JSON object mapping proband IDs to 1–2 variants."""

    truth_path = Path(path)
    try:
        with truth_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle, object_pairs_hook=_unique_json_object)
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateJsonKeyError) as exc:
        raise ValidationError(f"could not read ground-truth JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValidationError("ground truth must be a JSON object mapping proband IDs to variants")

    errors: list[str] = []
    result: GroundTruth = {}
    for proband_id, variants_value in raw.items():
        label = f"ground_truth[{proband_id!r}]"
        if not isinstance(proband_id, str) or not proband_id.strip():
            errors.append("ground-truth proband IDs must be nonempty strings")
            continue
        if proband_id != proband_id.strip():
            errors.append(
                "ground-truth proband IDs must not have leading or trailing whitespace"
            )
            continue
        if not isinstance(variants_value, list) or not 1 <= len(variants_value) <= 2:
            errors.append(f"{label} must be a list containing one or two variants")
            continue
        variants: list[Variant] = []
        for index, variant_value in enumerate(variants_value, start=1):
            variant = _validate_truth_variant(
                variant_value, f"{label}[{index}]", errors
            )
            if variant is not None:
                variants.append(variant)
        if len(variants) == len(variants_value):
            if len(set(variants)) != len(variants):
                errors.append(f"{label} must not contain duplicate variants")
            else:
                result[proband_id] = tuple(variants)

    if errors:
        raise ValidationError(errors)
    return result
