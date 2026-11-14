"""Privacy-safe local construction of Track 1 submission CSV files."""

from __future__ import annotations

import csv
import json
import math
import os
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any, Final, Iterator, Mapping

from rare_mva.filesystem import is_link_or_reparse

from rare_mva.track1.schema import (
    COLUMNS,
    VALID_FINDING_TYPES,
    Submission,
    ValidationError,
    Variant,
    _validate_variant_fields,
    load_submission,
)

_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {"proband_id", "calibration", "candidates"}
)
_CANDIDATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "variants",
        "raw_epcr",
        "finding_type",
        "notes",
        "read_validated",
        "frequency_status",
        "phase",
    }
)
_VARIANT_KEYS: Final[frozenset[str]] = frozenset({"chrom", "pos", "ref", "alt"})
_PHASES: Final[frozenset[str]] = frozenset(
    {"confirmed_trans", "probable_trans", "unresolved", "cis"}
)
_CHROMOSOME_ORDER: Final[dict[str, int]] = {
    **{f"chr{number}": number for number in range(1, 23)},
    "chrX": 23,
    "chrY": 24,
    "chrM": 25,
}


class BuilderError(ValidationError):
    """A candidate-document or safe-output violation with sanitized messages."""


class _DuplicateJsonKeyError(ValueError):
    """Internal sentinel for a duplicate JSON object key."""


class _InvalidJsonNumberError(ValueError):
    """Internal sentinel for a non-standard JSON numeric constant."""


@dataclass(frozen=True)
class _PreparedCandidate:
    variants: tuple[Variant, ...]
    epcr: Decimal
    epcr_text: str
    finding_type: str
    notes: str


@dataclass(frozen=True)
class _ParentGuard:
    path: Path
    identity: tuple[int, int]
    resolved_path: Path
    directory_fd: int | None = None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError
        result[key] = value
    return result


def _reject_nonstandard_number(_value: str) -> None:
    raise _InvalidJsonNumberError


def _load_document(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(
                handle,
                object_pairs_hook=_unique_object,
                parse_float=Decimal,
                parse_constant=_reject_nonstandard_number,
            )
    except _DuplicateJsonKeyError as exc:
        raise BuilderError("candidate_json.duplicate_key") from exc
    except _InvalidJsonNumberError as exc:
        raise BuilderError("candidate_json.nonstandard_number") from exc
    except json.JSONDecodeError as exc:
        raise BuilderError("candidate_json.invalid_json") from exc
    except ValueError as exc:
        raise BuilderError("candidate_json.invalid_json") from exc
    except (OSError, UnicodeError) as exc:
        raise BuilderError("candidate_json.read_failed") from exc


def _variant_sort_key(variant: Variant) -> tuple[int, int, str, str]:
    return (_CHROMOSOME_ORDER[variant.chrom], variant.pos, variant.ref, variant.alt)


def _valid_utf8(value: str) -> bool:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return True


def _parse_variant(value: Any, label: str, errors: list[str]) -> Variant | None:
    if not isinstance(value, Mapping):
        errors.append(f"{label}.type")
        return None
    if set(value) != _VARIANT_KEYS:
        errors.append(f"{label}.keys")
        return None

    chrom = value["chrom"]
    pos = value["pos"]
    ref = value["ref"]
    alt = value["alt"]
    if not isinstance(chrom, str):
        errors.append(f"{label}.chrom.type")
    elif not _valid_utf8(chrom):
        errors.append(f"{label}.chrom.utf8")
    if isinstance(pos, bool) or not isinstance(pos, int):
        errors.append(f"{label}.pos.type")
    if not isinstance(ref, str):
        errors.append(f"{label}.ref.type")
    elif not _valid_utf8(ref):
        errors.append(f"{label}.ref.utf8")
    if not isinstance(alt, str):
        errors.append(f"{label}.alt.type")
    elif not _valid_utf8(alt):
        errors.append(f"{label}.alt.utf8")
    if (
        not isinstance(chrom, str)
        or isinstance(pos, bool)
        or not isinstance(pos, int)
        or not isinstance(ref, str)
        or not isinstance(alt, str)
    ):
        return None

    schema_errors: list[str] = []
    variant = _validate_variant_fields(
        chrom,
        str(pos),
        ref,
        alt,
        label,
        schema_errors,
    )
    if variant is None:
        errors.append(f"{label}.value")
    return variant


def _parse_epcr(value: Any, label: str, errors: list[str]) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        errors.append(f"{label}.type")
        return None
    epcr = Decimal(value) if isinstance(value, int) else value
    if not epcr.is_finite() or not Decimal("0") < epcr <= Decimal("1"):
        errors.append(f"{label}.range")
        return None
    return epcr


def _prepare_document(raw: Any) -> tuple[str, list[_PreparedCandidate]]:
    if not isinstance(raw, Mapping):
        raise BuilderError("candidate_json.top_level.type")
    if set(raw) != _TOP_LEVEL_KEYS:
        raise BuilderError("candidate_json.top_level.keys")

    errors: list[str] = []
    proband_id = raw["proband_id"]
    if not isinstance(proband_id, str):
        errors.append("candidate_json.proband_id.type")
    elif not _valid_utf8(proband_id):
        errors.append("candidate_json.proband_id.utf8")
    elif not proband_id:
        errors.append("candidate_json.proband_id.empty")
    elif proband_id != proband_id.strip():
        errors.append("candidate_json.proband_id.surrounding_whitespace")

    calibration = raw["calibration"]
    if isinstance(calibration, str) and not _valid_utf8(calibration):
        errors.append("candidate_json.calibration.utf8")
    if calibration != "synthetic_only" or not isinstance(calibration, str):
        errors.append("candidate_json.calibration.value")

    candidates_value = raw["candidates"]
    if not isinstance(candidates_value, list):
        errors.append("candidate_json.candidates.type")
        candidates_value = []
    elif not 1 <= len(candidates_value) <= 10:
        errors.append("candidate_json.candidates.count")

    prepared: list[_PreparedCandidate] = []
    signatures: dict[tuple[Variant, ...], int] = {}
    for input_index, value in enumerate(candidates_value, start=1):
        label = f"candidate[{input_index}]"
        if not isinstance(value, Mapping):
            errors.append(f"{label}.type")
            continue
        if set(value) != _CANDIDATE_KEYS:
            errors.append(f"{label}.keys")
            continue

        candidate_error_count = len(errors)
        variants_value = value["variants"]
        parsed_variants: list[Variant] = []
        if not isinstance(variants_value, list):
            errors.append(f"{label}.variants.type")
        elif not 1 <= len(variants_value) <= 2:
            errors.append(f"{label}.variants.count")
        else:
            for variant_index, variant_value in enumerate(variants_value, start=1):
                variant = _parse_variant(
                    variant_value,
                    f"{label}.variant[{variant_index}]",
                    errors,
                )
                if variant is not None:
                    parsed_variants.append(variant)
            if len(parsed_variants) == 2 and parsed_variants[0] == parsed_variants[1]:
                errors.append(f"{label}.variants.duplicate_member")

        raw_epcr = _parse_epcr(value["raw_epcr"], f"{label}.raw_epcr", errors)

        finding_type = value["finding_type"]
        if isinstance(finding_type, str) and not _valid_utf8(finding_type):
            errors.append(f"{label}.finding_type.utf8")
        if not isinstance(finding_type, str) or finding_type not in VALID_FINDING_TYPES:
            errors.append(f"{label}.finding_type.value")

        notes = value["notes"]
        if not isinstance(notes, str):
            errors.append(f"{label}.notes.type")
        elif not _valid_utf8(notes):
            errors.append(f"{label}.notes.utf8")
        elif "\r" in notes or "\n" in notes:
            errors.append(f"{label}.notes.line_break")

        read_validated = value["read_validated"]
        if not isinstance(read_validated, bool):
            errors.append(f"{label}.read_validated.type")

        frequency_status = value["frequency_status"]
        if isinstance(frequency_status, str) and not _valid_utf8(frequency_status):
            errors.append(f"{label}.frequency_status.utf8")
        if not isinstance(frequency_status, str) or frequency_status not in {
            "known",
            "unknown",
        }:
            errors.append(f"{label}.frequency_status.value")

        phase = value["phase"]
        if isinstance(phase, str) and not _valid_utf8(phase):
            errors.append(f"{label}.phase.utf8")
        variant_count = len(variants_value) if isinstance(variants_value, list) else 0
        if variant_count == 1:
            if phase != "not_applicable" or not isinstance(phase, str):
                errors.append(f"{label}.phase.single")
        elif variant_count == 2:
            if not isinstance(phase, str) or phase not in _PHASES:
                errors.append(f"{label}.phase.compound")
            elif phase == "cis":
                errors.append(f"{label}.phase.cis_not_allowed")

        if len(errors) != candidate_error_count:
            continue

        ordered_variants = tuple(sorted(parsed_variants, key=_variant_sort_key))
        duplicate_index = signatures.get(ordered_variants)
        if duplicate_index is not None:
            errors.append(f"{label}.duplicate_variant_set")
            continue
        signatures[ordered_variants] = input_index

        assert raw_epcr is not None
        assert isinstance(finding_type, str)
        assert isinstance(notes, str)
        assert isinstance(read_validated, bool)
        assert isinstance(frequency_status, str)
        assert isinstance(phase, str)

        capped_epcr = min(raw_epcr, Decimal("0.80"))
        if not read_validated:
            capped_epcr = min(capped_epcr, Decimal("0.75"))
        if frequency_status == "unknown":
            capped_epcr = min(capped_epcr, Decimal("0.50"))
        if len(ordered_variants) == 2 and phase == "unresolved":
            capped_epcr = min(capped_epcr, Decimal("0.55"))

        epcr_text = _format_epcr(capped_epcr)
        stored_epcr = float(epcr_text)
        if not math.isfinite(stored_epcr) or stored_epcr <= 0.0:
            errors.append(f"{label}.raw_epcr.not_float_representable")
            continue

        prepared.append(
            _PreparedCandidate(
                variants=ordered_variants,
                epcr=capped_epcr,
                epcr_text=epcr_text,
                finding_type=finding_type,
                notes=notes,
            )
        )

    if errors:
        raise BuilderError(errors)
    assert isinstance(proband_id, str)
    prepared.sort(key=lambda candidate: Decimal(candidate.epcr_text), reverse=True)
    return proband_id, prepared


def _format_epcr(value: Decimal) -> str:
    """Format an EPCR with at most six significant decimal digits."""

    with localcontext() as context:
        context.rounding = ROUND_HALF_EVEN
        return format(value, ".6g").lower()


def _candidate_row(proband_id: str, candidate: _PreparedCandidate) -> dict[str, Any]:
    first = candidate.variants[0]
    second = candidate.variants[1] if len(candidate.variants) == 2 else None
    return {
        "proband_id": proband_id,
        "chrom_1": first.chrom,
        "pos_1": first.pos,
        "ref_1": first.ref,
        "alt_1": first.alt,
        "chrom_2": second.chrom if second is not None else "",
        "pos_2": second.pos if second is not None else "",
        "ref_2": second.ref if second is not None else "",
        "alt_2": second.alt if second is not None else "",
        "epcr": candidate.epcr_text,
        "finding_type": candidate.finding_type,
        "notes": candidate.notes,
    }


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_link_or_reparse(path: Path) -> bool:
    try:
        return is_link_or_reparse(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as exc:
        raise BuilderError("output.metadata_check_failed") from exc


def _reject_output_links(output_path: Path) -> None:
    current = output_path
    while True:
        if _is_link_or_reparse(current):
            raise BuilderError("output.link_or_reparse")
        if current.parent == current:
            break
        current = current.parent


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _open_windows_directory_guards(parent: Path) -> list[int]:
    """Hold all directory ancestors without delete sharing on Windows."""

    import ctypes
    from ctypes import wintypes

    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    share_read_write = 0x00000001 | 0x00000002
    open_existing = 3
    backup_semantics = 0x02000000
    open_reparse_point = 0x00200000
    invalid_handle = ctypes.c_void_p(-1).value

    ancestors: list[Path] = []
    current = parent
    while True:
        ancestors.append(current)
        if current.parent == current:
            break
        current = current.parent

    handles: list[int] = []
    try:
        for ancestor in reversed(ancestors):
            handle = create_file(
                str(ancestor),
                0,
                share_read_write,
                None,
                open_existing,
                backup_semantics | open_reparse_point,
                None,
            )
            if handle == invalid_handle:
                raise OSError(ctypes.get_last_error(), "directory guard open failed")
            handles.append(handle)
    except OSError:
        for handle in reversed(handles):
            close_handle(handle)
        raise
    return handles


def _close_windows_directory_guards(handles: list[int]) -> None:
    import ctypes
    from ctypes import wintypes

    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    for handle in reversed(handles):
        close_handle(handle)


@contextmanager
def _guard_output_parent(parent: Path) -> Iterator[_ParentGuard]:
    try:
        initial_identity = _identity(parent.stat())
        resolved_parent = parent.resolve(strict=True)
    except OSError as exc:
        raise BuilderError("output.parent_guard_failed") from exc

    windows_handles: list[int] = []
    directory_fd: int | None = None
    try:
        if os.name == "nt":
            try:
                windows_handles = _open_windows_directory_guards(parent)
            except OSError as exc:
                raise BuilderError("output.parent_guard_failed") from exc
        else:
            flags = os.O_RDONLY
            flags |= getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                directory_fd = os.open(parent, flags)
            except OSError as exc:
                raise BuilderError("output.parent_guard_failed") from exc
            if _identity(os.fstat(directory_fd)) != initial_identity:
                raise BuilderError("output.parent_identity_changed")

        guard = _ParentGuard(
            path=parent,
            identity=initial_identity,
            resolved_path=resolved_parent,
            directory_fd=directory_fd,
        )
        _assert_parent_guard(guard)
        yield guard
    finally:
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                pass
        if windows_handles:
            _close_windows_directory_guards(windows_handles)


def _assert_parent_guard(guard: _ParentGuard) -> None:
    try:
        if is_link_or_reparse(guard.path):
            raise BuilderError("output.parent_identity_changed")
        if _identity(guard.path.stat()) != guard.identity:
            raise BuilderError("output.parent_identity_changed")
        if guard.path.resolve(strict=True) != guard.resolved_path:
            raise BuilderError("output.parent_identity_changed")
    except BuilderError:
        raise
    except OSError as exc:
        raise BuilderError("output.parent_identity_changed") from exc


def _assert_outside_public(path: Path, public_root: Path, code: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise BuilderError(code) from exc
    if resolved == public_root or resolved.is_relative_to(public_root):
        raise BuilderError(code)
    return resolved


def _verify_open_temporary(
    descriptor: int,
    path: Path,
    guard: _ParentGuard,
    public_root: Path,
) -> tuple[int, int]:
    try:
        descriptor_identity = _identity(os.fstat(descriptor))
        if is_link_or_reparse(path):
            raise BuilderError("output.temporary_identity_changed")
        if _identity(path.stat()) != descriptor_identity:
            raise BuilderError("output.temporary_identity_changed")
    except BuilderError:
        raise
    except OSError as exc:
        raise BuilderError("output.temporary_identity_changed") from exc
    _assert_parent_guard(guard)
    _assert_outside_public(path, public_root, "output.temporary_inside_public_root")
    if path.parent.resolve(strict=True) != guard.resolved_path:
        raise BuilderError("output.parent_identity_changed")
    return descriptor_identity


def _verify_named_temporary(
    path: Path,
    expected_identity: tuple[int, int],
    guard: _ParentGuard,
    public_root: Path,
) -> None:
    _assert_parent_guard(guard)
    try:
        if is_link_or_reparse(path) or _identity(path.stat()) != expected_identity:
            raise BuilderError("output.temporary_identity_changed")
    except BuilderError:
        raise
    except OSError as exc:
        raise BuilderError("output.temporary_identity_changed") from exc
    _assert_outside_public(path, public_root, "output.temporary_inside_public_root")


def _replace_from_guarded_parent(
    temporary_path: Path,
    destination: Path,
    guard: _ParentGuard,
) -> None:
    if guard.directory_fd is not None:
        os.replace(
            temporary_path.name,
            destination.name,
            src_dir_fd=guard.directory_fd,
            dst_dir_fd=guard.directory_fd,
        )
    else:
        os.replace(temporary_path, destination)


def _cleanup_temporary(path: Path, guard: _ParentGuard | None) -> None:
    if guard is not None and guard.directory_fd is not None:
        try:
            os.unlink(path.name, dir_fd=guard.directory_fd)
        except OSError:
            pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _validate_output_location(
    input_path: Path,
    output_path: Path,
    public_root: Path,
) -> tuple[Path, Path]:
    lexical_output = _lexical_absolute(output_path)
    _reject_output_links(lexical_output)

    parent = lexical_output.parent
    if not parent.exists():
        raise BuilderError("output.parent_missing")
    if not parent.is_dir():
        raise BuilderError("output.parent_not_directory")

    try:
        resolved_output = lexical_output.resolve(strict=False)
        resolved_input = _lexical_absolute(input_path).resolve(strict=False)
        resolved_public_root = _lexical_absolute(public_root).resolve(strict=True)
    except OSError as exc:
        raise BuilderError("output.path_resolution_failed") from exc

    if not resolved_public_root.is_dir():
        raise BuilderError("public_root.not_directory")
    if resolved_output == resolved_public_root or resolved_output.is_relative_to(
        resolved_public_root
    ):
        raise BuilderError("output.inside_public_root")
    if resolved_output == resolved_input:
        raise BuilderError("output.matches_input")
    if lexical_output.exists():
        try:
            mode = lexical_output.stat().st_mode
        except OSError as exc:
            raise BuilderError("output.metadata_check_failed") from exc
        if not stat.S_ISREG(mode):
            raise BuilderError("output.not_regular_file")
    return lexical_output, resolved_public_root


def _write_atomic(
    input_path: Path,
    output_path: Path,
    public_root: Path,
    proband_id: str,
    candidates: list[_PreparedCandidate],
) -> Submission:
    destination, resolved_public_root = _validate_output_location(
        input_path, output_path, public_root
    )
    try:
        with _guard_output_parent(destination.parent) as guard:
            temporary_path: Path | None = None
            descriptor: int | None = None
            try:
                _validate_output_location(input_path, output_path, public_root)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.",
                    suffix=".tmp",
                    dir=destination.parent,
                )
                temporary_path = Path(temporary_name)
                temporary_identity = _verify_open_temporary(
                    descriptor,
                    temporary_path,
                    guard,
                    resolved_public_root,
                )
                try:
                    os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
                except (AttributeError, OSError):
                    pass

                handle = os.fdopen(
                    descriptor, "w", encoding="utf-8", errors="strict", newline=""
                )
                descriptor = None
                with handle:
                    writer = csv.DictWriter(
                        handle, fieldnames=COLUMNS, lineterminator="\n"
                    )
                    writer.writeheader()
                    for candidate in candidates:
                        writer.writerow(_candidate_row(proband_id, candidate))
                    handle.flush()
                    os.fsync(handle.fileno())

                _verify_named_temporary(
                    temporary_path,
                    temporary_identity,
                    guard,
                    resolved_public_root,
                )
                try:
                    submission = load_submission(temporary_path)
                except ValidationError as exc:
                    raise BuilderError("generated_csv.validation_failed") from exc

                _verify_named_temporary(
                    temporary_path,
                    temporary_identity,
                    guard,
                    resolved_public_root,
                )
                _validate_output_location(input_path, output_path, public_root)
                _replace_from_guarded_parent(temporary_path, destination, guard)
                temporary_path = None

                final_destination, _ = _validate_output_location(
                    input_path, output_path, public_root
                )
                try:
                    if _identity(final_destination.stat()) != temporary_identity:
                        raise BuilderError("output.final_identity_changed")
                except BuilderError:
                    raise
                except OSError as exc:
                    raise BuilderError("output.final_identity_changed") from exc
                return submission
            finally:
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                if temporary_path is not None:
                    _cleanup_temporary(temporary_path, guard)
    except BuilderError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise BuilderError("output.write_failed") from exc


def build_track1(
    candidates_path: str | Path,
    output_path: str | Path,
    *,
    public_root: str | Path | None = None,
) -> Submission:
    """Build and validate a Track 1 CSV using a strict local candidate document.

    The output parent must already exist and the output must resolve strictly
    outside ``public_root`` (the current working directory by default).
    """

    candidate_source = Path(candidates_path)
    destination = Path(output_path)
    boundary = Path.cwd() if public_root is None else Path(public_root)
    # Check the destination before reading the candidate document so an unsafe
    # output request cannot cause sensitive local input to be opened.
    _validate_output_location(candidate_source, destination, boundary)
    raw = _load_document(candidate_source)
    proband_id, candidates = _prepare_document(raw)
    return _write_atomic(
        candidate_source,
        destination,
        boundary,
        proband_id,
        candidates,
    )
