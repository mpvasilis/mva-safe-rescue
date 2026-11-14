"""Path-only privacy gate for repositories containing public code."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from rare_mva.filesystem import is_link_or_reparse

MAX_PUBLIC_FILE_BYTES: Final[int] = 5 * 1024 * 1024

_SKIPPED_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".rlib",
        ".ruff_cache",
        ".targets",
        ".tox",
        ".venv",
        "__pycache__",
        "env",
        "node_modules",
        "_targets",
        "venv",
    }
)
_RESTRICTED_COMPONENTS: Final[frozenset[str]] = frozenset(
    {
        ".private",
        "clinical",
        "controlled",
        "credentials",
        "data",
        "genomics",
        "patient-data",
        "patient_data",
        "private",
        "raw",
        "secrets",
    }
)
_RESTRICTED_PAIRS: Final[frozenset[tuple[str, str]]] = frozenset(
    {("data", "raw"), ("data", "private")}
)
_PROHIBITED_SUFFIXES: Final[tuple[str, ...]] = (
    ".fastq.gz",
    ".gvcf",
    ".vcf.gz",
    ".fq.gz",
    ".docx",
    ".fastq",
    ".cram",
    ".crai",
    ".vcf",
    ".tbi",
    ".bam",
    ".bai",
    ".bcf",
    ".ped",
    ".fq",
)
_PUBLIC_ASSET_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {"public_data", "public-assets"}
)
_PUBLIC_DOCUMENTATION_NAMES: Final[frozenset[str]] = frozenset(
    {"readme.md", "public_assets.md", "public-assets.md"}
)


@dataclass(frozen=True, order=True)
class PrivacyFinding:
    """One privacy-gate finding containing path metadata only."""

    path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation."""

        return asdict(self)


def _relative_posix(path: Path, root: Path) -> str:
    return PurePosixPath(path.relative_to(root)).as_posix()


def _restricted_reason(relative: Path) -> str | None:
    components = [component.lower() for component in relative.parts]
    for component in components:
        if component in _RESTRICTED_COMPONENTS:
            return f"restricted directory component: {component}"
    for left, right in zip(components, components[1:]):
        if (left, right) in _RESTRICTED_PAIRS:
            return f"restricted directory path: {left}/{right}"
    return None


def _has_documented_public_asset_parent(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    public_index: int | None = None
    for index, component in enumerate(relative_parts[:-1]):
        if component.lower() in _PUBLIC_ASSET_DIRECTORIES:
            public_index = index
            break
    if public_index is None:
        return False
    public_root = root.joinpath(*relative_parts[: public_index + 1])
    try:
        names = {child.name.lower() for child in public_root.iterdir() if child.is_file()}
    except OSError:
        return False
    return bool(names & _PUBLIC_DOCUMENTATION_NAMES)


def scan_paths(root: str | Path) -> list[PrivacyFinding]:
    """Recursively scan path names and file sizes without reading file contents."""

    scan_root = Path(root)
    try:
        root_is_link = is_link_or_reparse(scan_root)
    except FileNotFoundError:
        root_is_link = False
    except OSError:
        return [PrivacyFinding(path=".", reason="could not inspect root metadata")]
    if root_is_link:
        return [
            PrivacyFinding(path=".", reason="symbolic link is not permitted")
        ]
    if not scan_root.exists():
        raise ValueError(f"scan root does not exist: {scan_root}")
    if not scan_root.is_dir():
        raise ValueError(f"scan root must be a directory: {scan_root}")
    scan_root = scan_root.resolve()

    findings: list[PrivacyFinding] = []

    def record_walk_error(error: OSError) -> None:
        error_path = Path(error.filename) if error.filename else scan_root
        try:
            relative_text = _relative_posix(error_path, scan_root)
        except ValueError:
            relative_text = "."
        findings.append(
            PrivacyFinding(
                path=relative_text or ".",
                reason=f"could not traverse directory: {error.__class__.__name__}",
            )
        )

    for current, directory_names, file_names in os.walk(
        scan_root,
        topdown=True,
        onerror=record_walk_error,
        followlinks=False,
    ):
        current_path = Path(current)
        retained_directories: list[str] = []
        for directory_name in sorted(directory_names):
            directory_path = current_path / directory_name
            try:
                directory_is_link = is_link_or_reparse(directory_path)
            except OSError:
                findings.append(
                    PrivacyFinding(
                        path=_relative_posix(directory_path, scan_root),
                        reason="could not inspect path metadata",
                    )
                )
                continue
            if directory_is_link:
                findings.append(
                    PrivacyFinding(
                        path=_relative_posix(directory_path, scan_root),
                        reason="symbolic link is not permitted",
                    )
                )
                continue
            if directory_name.lower() in _SKIPPED_DIRECTORIES:
                continue
            relative = directory_path.relative_to(scan_root)
            reason = _restricted_reason(relative)
            if reason is not None:
                findings.append(
                    PrivacyFinding(
                        path=_relative_posix(directory_path, scan_root), reason=reason
                    )
                )
            else:
                retained_directories.append(directory_name)
        directory_names[:] = retained_directories

        for file_name in sorted(file_names):
            file_path = current_path / file_name
            try:
                file_is_link = is_link_or_reparse(file_path)
            except OSError:
                findings.append(
                    PrivacyFinding(
                        path=_relative_posix(file_path, scan_root),
                        reason="could not inspect path metadata",
                    )
                )
                continue
            if file_is_link:
                findings.append(
                    PrivacyFinding(
                        path=_relative_posix(file_path, scan_root),
                        reason="symbolic link is not permitted",
                    )
                )
                continue
            relative = file_path.relative_to(scan_root)
            reason = _restricted_reason(relative)
            relative_text = _relative_posix(file_path, scan_root)
            if reason is not None:
                findings.append(PrivacyFinding(path=relative_text, reason=reason))
                continue

            lower_name = file_name.lower()
            prohibited_suffix = next(
                (suffix for suffix in _PROHIBITED_SUFFIXES if lower_name.endswith(suffix)),
                None,
            )
            if prohibited_suffix is not None:
                findings.append(
                    PrivacyFinding(
                        path=relative_text,
                        reason=f"prohibited clinical/genomic file extension: {prohibited_suffix}",
                    )
                )
                continue

            try:
                file_size = file_path.stat().st_size
            except OSError as exc:
                findings.append(
                    PrivacyFinding(
                        path=relative_text,
                        reason=f"could not inspect file metadata: {exc.__class__.__name__}",
                    )
                )
                continue
            if file_size > MAX_PUBLIC_FILE_BYTES and not _has_documented_public_asset_parent(
                file_path, scan_root
            ):
                findings.append(
                    PrivacyFinding(
                        path=relative_text,
                        reason=f"file exceeds {MAX_PUBLIC_FILE_BYTES} bytes",
                    )
                )

    return sorted(set(findings))
