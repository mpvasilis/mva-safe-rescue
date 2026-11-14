from __future__ import annotations

import gzip
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from analysis.secure_wgs import cleanup_verify, orchestrator


PINNED_REVISION = "1" * 40
SYNTHETIC_TOKEN = "synthetic-token-never-print"


def _write_fastq(path: Path, sequence: str = "ACGT") -> None:
    with gzip.open(path, "wt", encoding="ascii", newline="\n") as handle:
        handle.write(f"@synthetic\n{sequence}\n+\n{'I' * len(sequence)}\n")


def _outside_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(orchestrator, "REPO_ROOT", tmp_path / "public-repo-sentinel")
    monkeypatch.setattr(cleanup_verify, "REPO_ROOT", tmp_path / "public-repo-sentinel")


def _metadata() -> list[dict]:
    return [
        {
            "path": "synthetic_lane_R1.fastq.gz",
            "size_bytes": 101,
            "sha256": "a" * 64,
        },
        {
            "path": "synthetic_lane_R2.fastq.gz",
            "size_bytes": 102,
            "sha256": "b" * 64,
        },
        {
            "path": "nested/synthetic_second_1.fq.gz",
            "size_bytes": 103,
            "sha256": "c" * 64,
        },
        {
            "path": "nested/synthetic_second_2.fq.gz",
            "size_bytes": 104,
            "sha256": "d" * 64,
        },
    ]


def test_local_prepare_pairs_and_generically_names_fastqs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _outside_repo(monkeypatch, tmp_path)
    source = tmp_path / "private-source"
    source.mkdir()
    _write_fastq(source / "subject_alpha_R1.fastq.gz")
    _write_fastq(source / "subject_alpha_R2.fastq.gz")
    manifest_path = tmp_path / "private-control" / "manifest.json"

    payload = orchestrator.prepare_manifest(input_dir=source, manifest_path=manifest_path)

    assert payload["pair_count"] == 1
    assert [item["staged_name"] for item in payload["pairs"][0]["files"]] == [
        "SAMPLE01_L001_R1.fastq.gz",
        "SAMPLE01_L001_R2.fastq.gz",
    ]
    assert payload["ready_for_transfer"] is True
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["classification"].startswith(
        "CONTROLLED_PRIVATE"
    )


def test_incomplete_pair_fails_without_cli_filename_disclosure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _outside_repo(monkeypatch, tmp_path)
    source = tmp_path / "private-source"
    source.mkdir()
    sensitive_name = "never_echo_this_R1.fastq.gz"
    _write_fastq(source / sensitive_name)

    result = orchestrator.main(
        [
            "prepare",
            "--input-dir",
            str(source),
            "--manifest",
            str(tmp_path / "private-control" / "manifest.json"),
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert captured.err.strip() == "secure_wgs_status=failed_closed"
    assert sensitive_name not in captured.err


def test_prepare_hf_uses_cached_token_and_only_emits_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _outside_repo(monkeypatch, tmp_path)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.get_token = lambda: SYNTHETIC_TOKEN

    class FakeApi:
        def dataset_info(self, repo_id, *, revision, files_metadata, token):
            assert repo_id == orchestrator.HF_REPO_ID
            assert revision == "main"
            assert files_metadata is True
            assert token == SYNTHETIC_TOKEN
            siblings = []
            for item in _metadata():
                lfs = types.SimpleNamespace(
                    sha256=item["sha256"], size=item["size_bytes"]
                )
                siblings.append(
                    types.SimpleNamespace(
                        rfilename=item["path"], size=item["size_bytes"], lfs=lfs
                    )
                )
            siblings.append(types.SimpleNamespace(rfilename="README.md", size=10, lfs=None))
            return types.SimpleNamespace(sha=PINNED_REVISION, siblings=siblings)

    fake_hub.HfApi = FakeApi
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    manifest_path = tmp_path / "private-control" / "hf-manifest.json"

    result = orchestrator.main(
        ["prepare-hf", "--manifest", str(manifest_path), "--revision", "main"]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "pair_count": 2,
        "ready_for_transfer": True,
        "status": "ok",
    }
    assert SYNTHETIC_TOKEN not in captured.out
    assert "synthetic_lane" not in captured.out
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_revision"] == PINNED_REVISION
    assert payload["token_persisted"] is False
    assert payload["materialization"] == "hugging-face-metadata-only"
    assert [pair["lane_id"] for pair in payload["pairs"]] == ["L001", "L002"]


def test_prepare_hf_rejects_missing_lfs_digest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _outside_repo(monkeypatch, tmp_path)

    def incomplete_metadata(revision: str, token: str):
        records = _metadata()
        records[0] = {**records[0], "sha256": None}
        return records, PINNED_REVISION

    with pytest.raises(orchestrator.SecureWgsError):
        orchestrator.prepare_hf_manifest(
            manifest_path=tmp_path / "private-control" / "manifest.json",
            token=SYNTHETIC_TOKEN,
            metadata_fetcher=incomplete_metadata,
        )


def test_signed_plan_is_pinned_expiring_and_never_persists_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _outside_repo(monkeypatch, tmp_path)
    manifest_path = tmp_path / "private-control" / "manifest.json"
    orchestrator.prepare_hf_manifest(
        manifest_path=manifest_path,
        token=SYNTHETIC_TOKEN,
        metadata_fetcher=lambda revision, token: (_metadata(), PINNED_REVISION),
    )
    seen: list[tuple[str, str]] = []
    expiry = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    def resolver(url: str, token: str) -> str:
        seen.append((url, token))
        return f"https://signed.example.invalid/object?Expires={expiry}"

    plan_path = tmp_path / "private-control" / "signed-plan.json"
    payload = orchestrator.create_signed_transfer_plan(
        manifest_path=manifest_path,
        output_path=plan_path,
        token=SYNTHETIC_TOKEN,
        resolver=resolver,
    )

    serialized = plan_path.read_text(encoding="utf-8")
    assert payload["source"]["revision"] == PINNED_REVISION
    assert payload["token_persisted"] is False
    assert payload["file_count"] == 4
    assert all(token == SYNTHETIC_TOKEN for _, token in seen)
    assert all(f"/resolve/{PINNED_REVISION}/" in url for url, _ in seen)
    assert SYNTHETIC_TOKEN not in serialized


def test_manifest_and_attestation_paths_inside_repo_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(orchestrator.SecureWgsError):
        orchestrator.validate_private_output(
            orchestrator.REPO_ROOT / "analysis" / "secure_wgs" / "forbidden.json"
        )


def test_cleanup_verifier_passes_only_when_everything_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _outside_repo(monkeypatch, tmp_path)
    attestation = tmp_path / "private-audit" / "cleanup.json"
    payload = cleanup_verify.verify_cleanup(
        expected_deleted_paths=[tmp_path / "already-gone"],
        instance_id=101,
        volume_ids=[202],
        attestation_path=attestation,
        instances_payload=[{"id": 999}],
        volumes_payload={"volumes": [{"id": 998}]},
    )
    assert payload["passed"] is True

    with pytest.raises(orchestrator.SecureWgsError):
        cleanup_verify.verify_cleanup(
            expected_deleted_paths=[tmp_path / "already-gone"],
            instance_id=101,
            volume_ids=[],
            attestation_path=tmp_path / "private-audit" / "failed.json",
            instances_payload=[{"id": 101}],
            volumes_payload=[],
        )


def test_remote_scripts_keep_fixed_method_and_hard_gates() -> None:
    root = Path(__file__).resolve().parents[1] / "analysis" / "secure_wgs" / "remote"
    runner = (root / "run_parabricks_deepvariant.sh").read_text(encoding="utf-8")
    smoke = (root / "public_smoke_test.sh").read_text(encoding="utf-8")
    assert 'EXPECTED_PARABRICKS_VERSION="4.7.1-1"' in runner
    assert 'APPROVED_PARABRICKS_IMAGE_DIGEST="sha256:REPLACE_WITH_VERIFIED_64_HEX"' in runner
    assert '"${PARABRICKS_IMAGE_DIGEST}" == "${APPROVED_PARABRICKS_IMAGE_DIGEST}"' in runner
    assert 'REFERENCE_ACCESSION="GCA_000001405.15"' in runner
    assert 'REFERENCE_ARCHIVE_MD5="a08035b6a6e31780e96a34008ff21bd6"' in runner
    assert "--gvcf" in runner
    assert "PROCESSOR_TERMS_APPROVED" in runner
    assert "no_training_or_own_use" in runner
    assert "PUBLIC_BUNDLE_SHA256" in smoke
    assert "trap - ERR" in runner and "trap - ERR" in smoke
