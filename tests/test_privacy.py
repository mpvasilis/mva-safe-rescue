"""Path-only privacy-gate tests using synthetic temporary files."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Iterator

import pytest

from rare_mva.privacy import MAX_PUBLIC_FILE_BYTES, PrivacyFinding, scan_paths


@pytest.mark.parametrize(
    "name",
    [
        "synthetic.vcf",
        "synthetic.vcf.gz",
        "synthetic.tbi",
        "synthetic.fastq",
        "synthetic.fastq.gz",
        "synthetic.fq",
        "synthetic.fq.gz",
        "synthetic.bam",
        "synthetic.bai",
        "synthetic.cram",
        "synthetic.crai",
        "synthetic.bcf",
        "synthetic.gvcf",
        "synthetic.ped",
        "synthetic.docx",
    ],
)
def test_prohibited_extensions_detected(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes(b"")
    findings = scan_paths(tmp_path)
    assert [finding.path for finding in findings] == [name]
    assert "prohibited" in findings[0].reason


@pytest.mark.parametrize(
    "relative",
    [
        Path("data/raw"),
        Path("data/private"),
        Path("private"),
        Path("controlled"),
        Path(".private"),
        Path("clinical"),
        Path("genomics"),
        Path("patient-data"),
        Path("patient_data"),
        Path("raw"),
        Path("secrets"),
        Path("credentials"),
        Path("data"),
    ],
)
def test_restricted_directory_detected_and_not_traversed(
    tmp_path: Path, relative: Path
) -> None:
    restricted = tmp_path / relative
    restricted.mkdir(parents=True)
    (restricted / "synthetic.txt").write_text("SYNTHETIC", encoding="utf-8")
    findings = scan_paths(tmp_path)
    assert len(findings) == 1
    expected_path = "data" if relative.parts[0] == "data" else relative.as_posix()
    assert findings[0].path == expected_path
    assert "restricted directory" in findings[0].reason


def test_large_file_detected(tmp_path: Path) -> None:
    large = tmp_path / "synthetic-large.bin"
    with large.open("wb") as handle:
        handle.seek(MAX_PUBLIC_FILE_BYTES)
        handle.write(b"0")
    findings = scan_paths(tmp_path)
    assert [finding.path for finding in findings] == ["synthetic-large.bin"]
    assert "exceeds" in findings[0].reason


def test_documented_public_asset_and_clean_synthetic_path(tmp_path: Path) -> None:
    public = tmp_path / "public_data"
    public.mkdir()
    (public / "README.md").write_text(
        "SYNTHETIC PUBLIC ASSET DOCUMENTATION", encoding="utf-8"
    )
    (public / "tiny-synthetic.csv").write_text(
        "kind,value\nSYNTHETIC,1\n", encoding="utf-8"
    )
    large = public / "documented-synthetic.bin"
    with large.open("wb") as handle:
        handle.seek(MAX_PUBLIC_FILE_BYTES)
        handle.write(b"0")
    assert scan_paths(tmp_path) == []


def test_virtualenvs_and_caches_are_skipped(tmp_path: Path) -> None:
    hidden = tmp_path / ".venv"
    hidden.mkdir()
    (hidden / "synthetic.vcf").write_bytes(b"")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "synthetic.bam").write_bytes(b"")
    r_library = tmp_path / ".Rlib"
    r_library.mkdir()
    (r_library / "synthetic.vcf").write_bytes(b"")
    targets = tmp_path / ".targets"
    targets.mkdir()
    (targets / "synthetic.bam").write_bytes(b"")
    underscore_targets = tmp_path / "_targets"
    underscore_targets.mkdir()
    (underscore_targets / "synthetic.bam").write_bytes(b"")
    assert scan_paths(tmp_path) == []


@pytest.mark.parametrize("name", [".Rlib", ".targets", "_targets"])
def test_generated_r_cache_symlink_is_flagged_before_skip(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
    name: str,
) -> None:
    outside = tmp_path_factory.mktemp(f"outside_{name.removeprefix('.')}")
    (outside / "synthetic.txt").write_text("SYNTHETIC", encoding="utf-8")
    link = tmp_path / name
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create directory symlinks: {exc}")

    assert scan_paths(tmp_path) == [
        PrivacyFinding(path=name, reason="symbolic link is not permitted")
    ]


def test_file_symlink_is_flagged_and_not_followed(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside_file_symlink")
    target = outside / "synthetic-target.txt"
    target.write_text("SYNTHETIC", encoding="utf-8")
    link = tmp_path / "synthetic-link.txt"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create file symlinks: {exc}")

    findings = scan_paths(tmp_path)
    assert findings == [
        PrivacyFinding(
            path="synthetic-link.txt", reason="symbolic link is not permitted"
        )
    ]


def test_directory_symlink_is_flagged_even_with_skipped_name(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside_directory_symlink")
    (outside / "synthetic.txt").write_text("SYNTHETIC", encoding="utf-8")
    link = tmp_path / ".venv"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create directory symlinks: {exc}")

    findings = scan_paths(tmp_path)
    assert len(findings) == 1
    assert findings[0].path == ".venv"
    assert findings[0].reason == "symbolic link is not permitted"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_windows_junction_is_flagged_before_skipped_directory_check(
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    outside = tmp_path_factory.mktemp("outside_junction")
    (outside / "synthetic.txt").write_text("SYNTHETIC", encoding="utf-8")
    junction = tmp_path / ".venv"
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not junction.exists():
        pytest.skip("Windows junction creation is unavailable")

    try:
        assert scan_paths(tmp_path) == [
            PrivacyFinding(
                path=".venv",
                reason="symbolic link is not permitted",
            )
        ]
    finally:
        junction.rmdir()


def test_traversal_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = tmp_path / "blocked"

    def failing_walk(
        root: Path,
        *,
        topdown: bool,
        onerror: Callable[[OSError], None],
        followlinks: bool,
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        assert root == tmp_path.resolve()
        assert topdown is True
        assert followlinks is False
        error = PermissionError(13, "SYNTHETIC ACCESS DENIED", str(blocked))
        onerror(error)
        return iter(())

    monkeypatch.setattr("rare_mva.privacy.os.walk", failing_walk)
    assert scan_paths(tmp_path) == [
        PrivacyFinding(
            path="blocked",
            reason="could not traverse directory: PermissionError",
        )
    ]


def test_missing_or_file_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        scan_paths(tmp_path / "missing")
    file_path = tmp_path / "synthetic.txt"
    file_path.write_text("SYNTHETIC", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        scan_paths(file_path)
