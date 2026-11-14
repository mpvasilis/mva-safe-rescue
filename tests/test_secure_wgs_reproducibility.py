from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from analysis.secure_wgs import synthetic_contract_smoke as smoke


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "analysis" / "secure_wgs" / "public_workflow_contract.json"
SMOKE_PATH = ROOT / "analysis" / "secure_wgs" / "synthetic_contract_smoke.py"
MAP_PATH = ROOT / "docs" / "TRACK1_REPRODUCIBILITY_MAP.md"

EXPECTED_STAGE_IDS = [
    "contract_preflight",
    "protected_input_manifest",
    "secure_transfer",
    "alignment_and_small_variants",
    "complementary_variant_and_phenotype_analysis",
    "chromosome_research_screen",
    "evidence_reconciliation",
    "submission_validation",
    "cleanup_verification",
]


def _load() -> tuple[dict[str, object], bytes]:
    return smoke.load_contract(CONTRACT_PATH)


def _run_cli(contract_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SMOKE_PATH),
            "--contract",
            str(contract_path),
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_contract_schema_ordering_and_connected_synthetic_graph() -> None:
    contract, _ = _load()
    smoke.validate_contract(contract, ROOT)

    assert contract["schema"] == smoke.CONTRACT_SCHEMA
    stages = contract["stages"]
    assert [stage["order"] for stage in stages] == list(range(1, 10))
    assert [stage["stage_id"] for stage in stages] == EXPECTED_STAGE_IDS

    first = smoke.build_synthetic_role_graph(contract)
    second = smoke.build_synthetic_role_graph(contract)
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", str(first["graph_sha256"]))
    assert first["materialized_role_count"] >= len(contract["terminal_roles"])


def test_contract_distinguishes_public_heavyweight_and_human_gated_stages() -> None:
    contract, _ = _load()
    stages = {stage["stage_id"]: stage for stage in contract["stages"]}

    assert stages["contract_preflight"]["execution_class"] == "public-local"
    assert (
        stages["alignment_and_small_variants"]["execution_class"]
        == "containerized-heavyweight-protected"
    )
    assert stages["evidence_reconciliation"]["execution_class"] == "human-gated-protected"
    assert stages["complementary_variant_and_phenotype_analysis"]["public_entrypoint"] is None
    assert stages["evidence_reconciliation"]["public_entrypoint"] is None
    assert all(stage["evidence_receipt_role"] in stage["output_roles"] for stage in stages.values())


def test_cli_success_is_deterministic_and_negative_self_test_passes() -> None:
    first = _run_cli(CONTRACT_PATH, "--self-test", "--json")
    second = _run_cli(CONTRACT_PATH, "--self-test", "--json")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["status"] == "passed"
    assert result["negative_self_test"] == "passed"
    assert result["stage_count"] == 9
    assert result["public_entrypoint_count"] == 7
    assert result["documentation_only_stage_count"] == 2


def test_cli_fails_closed_for_disconnected_role_mutation(tmp_path: Path) -> None:
    contract, _ = _load()
    mutated = copy.deepcopy(contract)
    mutated["stages"][3]["input_roles"].append("missing_synthetic_role")
    invalid_path = tmp_path / "invalid-contract.json"
    invalid_path.write_text(
        json.dumps(mutated, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )

    result = _run_cli(invalid_path, "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "secure_wgs_contract_status=failed_closed\n"


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    invalid_path = tmp_path / "duplicate.json"
    invalid_path.write_text(
        '{"schema":"secure-wgs-public-workflow-contract/v1","schema":"duplicate"}',
        encoding="utf-8",
    )

    with pytest.raises(smoke.ContractError, match="duplicate JSON key"):
        smoke.load_contract(invalid_path)
    result = _run_cli(invalid_path, "--json")
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "secure_wgs_contract_status=failed_closed\n"


def test_every_declared_public_entrypoint_exists_inside_repository() -> None:
    contract, _ = _load()
    root = ROOT.resolve(strict=True)
    for stage in contract["stages"]:
        entrypoint = stage["public_entrypoint"]
        if entrypoint is None:
            assert stage["public_entrypoint_reason"]
            continue
        resolved = smoke.resolve_public_entrypoint(entrypoint, ROOT)
        assert resolved.is_file()
        assert resolved.is_relative_to(root)
        assert stage["public_entrypoint_reason"] is None


@pytest.mark.parametrize(
    "unsafe_entrypoint",
    [
        "../outside.py",
        "/outside.py",
        "analysis\\secure_wgs\\orchestrator.py",
    ],
)
def test_public_entrypoint_escape_paths_fail_closed(unsafe_entrypoint: str) -> None:
    contract, _ = _load()
    mutated = copy.deepcopy(contract)
    mutated["stages"][0]["public_entrypoint"] = unsafe_entrypoint
    with pytest.raises(smoke.ContractError):
        smoke.validate_contract(mutated, ROOT)


def test_public_contract_and_map_have_no_obvious_private_identifiers_or_endpoints() -> None:
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
    map_text = MAP_PATH.read_text(encoding="utf-8")
    combined = contract_text + "\n" + map_text

    forbidden = {
        "drive_path": re.compile(r"(?i)\b[a-z]:[\\/]"),
        "absolute_posix_path": re.compile(
            r"(?:^|\s)/(?!/)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._${}-]+)+"
        ),
        "user_profile": re.compile(r"(?i)\b(?:users|home)[\\/][a-z0-9._-]+"),
        "service_url": re.compile(r"(?i)\b(?:https?|s3|gs|ssh)://"),
        "credential_value": re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*[^\s,;]+"
        ),
        "provider_token": re.compile(r"(?i)\b(?:hf_[a-z0-9]{12,}|akia[0-9a-z]{12,})\b"),
        "coordinate": re.compile(
            r"\b(?:chr)?(?:[0-9]{1,2}|X|Y|M|MT):[0-9][0-9,]*(?:[-:][0-9][0-9,]*)?\b"
        ),
        "allele": re.compile(r"\b[ACGTN]+>[ACGTN]+\b", re.IGNORECASE),
        "transcript": re.compile(r"\b(?:NM|NR|ENST)_?[0-9]+(?:\.[0-9]+)?\b", re.IGNORECASE),
        "subject_alias": re.compile(r"(?i)\b(?:sample|proband|patient)[_-]?[0-9]+\b"),
        "official_source_name": re.compile(r"(?i)\bWGS_[A-Za-z0-9_.-]+"),
        "instance_address": re.compile(
            r"(?i)\b(?:host|address|endpoint|instance)\s*[:=]?\s*(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
        ),
    }
    findings = {name: pattern.findall(combined) for name, pattern in forbidden.items()}
    assert findings == {name: [] for name in forbidden}

    # The validator applies the same value-level privacy gate to the parsed contract.
    contract, _ = _load()
    smoke.validate_contract(contract, ROOT)


def test_documentation_references_resolve_and_quickstart_is_truthful() -> None:
    text = MAP_PATH.read_text(encoding="utf-8")
    linked_paths = re.findall(r"\[[^]]+\]\(([^)]+)\)", text)
    assert linked_paths
    for linked_path in linked_paths:
        assert not re.match(r"[a-z]+://", linked_path, re.IGNORECASE)
        assert (MAP_PATH.parent / linked_path).resolve(strict=True).is_file()

    referenced_repo_paths = [
        "analysis/secure_wgs/public_workflow_contract.json",
        "analysis/secure_wgs/synthetic_contract_smoke.py",
        "analysis/secure_wgs/orchestrator.py",
        "analysis/secure_wgs/remote/fetch_signed_plan.py",
        "analysis/secure_wgs/remote/run_parabricks_deepvariant.sh",
        "analysis/secure_wgs/mosaic_aneuploidy_scan.py",
        "analysis/secure_wgs/remote/run_mosaic_aneuploidy_scan.sh",
        "analysis/secure_wgs/cleanup_verify.py",
        "src/rare_mva/cli.py",
        "tests/test_secure_wgs.py",
        "tests/test_mosaic_aneuploidy_scan.py",
        "tests/test_secure_wgs_reproducibility.py",
    ]
    for repo_path in referenced_repo_paths:
        assert repo_path in text
        assert (ROOT / repo_path).is_file()

    normalized = " ".join(text.split())
    assert (
        "The synthetic smoke validates orchestration/contracts, not biological "
        "equivalence or the 85-GB rerun."
    ) in normalized
    for entrypoint in (
        "analysis/secure_wgs/public/run_complementary_workflow.py",
        "analysis/secure_wgs/public/build_reconciliation_ledger.py",
        "analysis/secure_wgs/public/synthetic_end_to_end_smoke.py",
    ):
        assert entrypoint in text
        assert (ROOT / entrypoint).is_file()
    assert "not a biological rerun" in normalized
    assert "never uploads or submits" in text


def test_secure_wgs_readme_links_to_judge_map_and_contract() -> None:
    readme = ROOT / "analysis" / "secure_wgs" / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "../../docs/TRACK1_REPRODUCIBILITY_MAP.md" in text
    assert "public_workflow_contract.json" in text
    assert (readme.parent / "../../docs/TRACK1_REPRODUCIBILITY_MAP.md").resolve(strict=True) == MAP_PATH
