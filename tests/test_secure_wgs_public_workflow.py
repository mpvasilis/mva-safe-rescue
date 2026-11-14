from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from analysis.secure_wgs.public import build_reconciliation_ledger as ledger
from analysis.secure_wgs.public import run_complementary_workflow as workflow
from analysis.secure_wgs.public import synthetic_end_to_end_smoke as smoke


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "analysis" / "secure_wgs" / "public"
CONFIG_PATH = PUBLIC_ROOT / "complementary_workflow.v1.json"
POLICY_PATH = PUBLIC_ROOT / "reconciliation_policy.v1.json"

EXPECTED_TOOLS = {
    "manta": "1.6.0",
    "delly": "2.3.0",
    "cnvpytor": "1.3.2",
    "annotsv": "3.5.7",
    "exomiser_prioritizer": "14.1.0",
    "samplot": "1.3.0",
    "xtea": "0.1.9",
    "expansionhunter": "5.0.0",
    "gatk": "4.7.0.0",
    "haplocheck": "1.3.3",
    "exomiser": "15.1.0",
    "lirical": "2.4.1",
    "whatshap": "2.8",
}


def _invoke(function: Callable[[list[str]], int], argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = function(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _write_json(path: Path, value: Any) -> bytes:
    raw = workflow._json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _approval(
    path: Path,
    *,
    config_raw: bytes,
    input_raw: bytes,
    asset_raw: bytes,
    approved_minutes: int = -1,
    expires_minutes: int = 30,
    config_hash: str | None = None,
) -> Path:
    now = workflow._utc_now()
    value = {
        "approved_at_utc": workflow._utc_text(now + timedelta(minutes=approved_minutes)),
        "approved_by": "synthetic-test-operator",
        "asset_manifest_sha256": workflow._hash_bytes(asset_raw),
        "config_sha256": config_hash or workflow._hash_bytes(config_raw),
        "expires_at_utc": workflow._utc_text(now + timedelta(minutes=expires_minutes)),
        "input_manifest_sha256": workflow._hash_bytes(input_raw),
        "purpose": "RESEARCH_ONLY",
        "schema": workflow.APPROVAL_SCHEMA,
        "status": "APPROVED",
    }
    _write_json(path, value)
    return path


def _workflow_args(
    command: str,
    environment: dict[str, Any],
    *,
    asset_manifest: Path | None = None,
    approval: Path | None = None,
    receipt_root: Path | None = None,
) -> list[str]:
    result = [
        command,
        "--config",
        str(CONFIG_PATH),
        "--input-manifest",
        str(environment["input_manifest"]),
        "--asset-manifest",
        str(asset_manifest or environment["asset_manifest"]),
        "--json",
    ]
    if command == "run":
        result.extend(
            [
                "--approval-record",
                str(approval or environment["approval"]),
                "--receipt-root",
                str(receipt_root or environment["root"] / "new-run"),
            ]
        )
    return result


def _basic_environment(root: Path) -> dict[str, Any]:
    config, config_raw = workflow.load_and_validate_config(CONFIG_PATH)
    input_manifest, asset_manifest, input_raw, asset_raw = smoke._prepare_synthetic_material(
        root, config
    )
    approval = _approval(
        root / "approval.json",
        config_raw=config_raw,
        input_raw=input_raw,
        asset_raw=asset_raw,
    )
    return {
        "approval": approval,
        "asset_manifest": asset_manifest,
        "asset_raw": asset_raw,
        "config": config,
        "config_raw": config_raw,
        "input_manifest": input_manifest,
        "input_raw": input_raw,
        "root": root,
    }


def _mutated_asset_manifest(
    environment: dict[str, Any],
    root: Path,
    lane_index: int,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[Path, bytes]:
    lane = environment["config"]["lanes"][lane_index]
    role = lane["parameter_role"]
    manifest = json.loads(environment["asset_manifest"].read_text(encoding="utf-8"))
    entry = next(item for item in manifest["assets"] if item["role"] == role)
    parameter = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
    mutate(parameter)
    parameter_path = root / f"{role}.mutated.json"
    _write_json(parameter_path, parameter)
    entry["path"] = str(parameter_path.resolve(strict=True))
    entry["sha256"] = workflow._hash_file(parameter_path)
    manifest_path = root / "asset_manifest.mutated.json"
    raw = _write_json(manifest_path, manifest)
    return manifest_path, raw


@pytest.fixture(scope="session")
def executed_environment(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("secure-wgs-public-workflow")
    environment = _basic_environment(root)
    receipt_root = root / "successful-run"
    original_run = workflow.subprocess.run
    shell_values: list[Any] = []

    def checked_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        shell_values.append(kwargs.get("shell"))
        return original_run(*args, **kwargs)

    original_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(ROOT) + (
        os.pathsep + original_pythonpath if original_pythonpath else ""
    )
    workflow.subprocess.run = checked_run
    try:
        code, stdout, stderr = _invoke(
            workflow.main,
            _workflow_args(
                "run", environment, receipt_root=receipt_root
            ),
        )
    finally:
        workflow.subprocess.run = original_run
        if original_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = original_pythonpath
    assert code == 0, stderr
    run_result = json.loads(stdout)
    assert run_result["status"] == "passed"

    policy, policy_raw = ledger.load_and_validate_policy(POLICY_PATH)
    relation_by_role = {
        relation["receipt_role"]: relation
        for relation in policy["method_version_relations"]
    }
    evidence_root = root / "external-evidence"
    evidence_root.mkdir()
    timestamp = workflow._utc_text(workflow._utc_now())
    entries: list[dict[str, str]] = []
    for role in policy["required_receipt_roles"]:
        generated = receipt_root / "receipts" / f"{role}.json"
        if generated.is_file():
            receipt_path = generated
        else:
            receipt_path = evidence_root / f"{role}.json"
            _write_json(
                receipt_path,
                smoke._make_external_receipt(relation_by_role[role], timestamp),
            )
        entries.append(
            {
                "path": str(receipt_path.resolve(strict=True)),
                "role": role,
                "sha256": workflow._hash_file(receipt_path),
            }
        )
    receipt_manifest = {
        "chromosome_screen_state": "NO_SIGNAL_RESEARCH_ONLY",
        "confidence_change_from_chromosome_screen": 0,
        "human_gate_required": True,
        "phase_inference_requested": False,
        "phase_status": "UNRESOLVED",
        "receipts": entries,
        "schema": ledger.RECEIPT_MANIFEST_SCHEMA,
        "scientific_cutoff_at_utc": timestamp,
        "score_blending_requested": False,
        "score_handling": "SEPARATE_NON_COMMENSURATE",
        "unsupported_phase_evidence_present": False,
    }
    receipt_manifest_path = root / "receipt_manifest.json"
    _write_json(receipt_manifest_path, receipt_manifest)
    ledger_path = root / "ledger.json"
    code, stdout, stderr = _invoke(
        ledger.main,
        [
            "build",
            "--policy",
            str(POLICY_PATH),
            "--receipt-manifest",
            str(receipt_manifest_path),
            "--output",
            str(ledger_path),
            "--json",
        ],
    )
    assert code == 0, stderr
    ledger_result = json.loads(stdout)
    return {
        **environment,
        "ledger_path": ledger_path,
        "ledger_result": ledger_result,
        "policy": policy,
        "policy_raw": policy_raw,
        "receipt_manifest": receipt_manifest,
        "receipt_manifest_path": receipt_manifest_path,
        "receipt_root": receipt_root,
        "run_result": run_result,
        "shell_values": shell_values,
    }


def test_exact_accepted_method_inventory_and_separate_lane_semantics() -> None:
    config, _ = workflow.load_and_validate_config(CONFIG_PATH)
    actual_tools = {tool["tool_id"]: tool["version"] for tool in config["tool_contracts"]}
    assert actual_tools == EXPECTED_TOOLS
    assert len(config["lanes"]) == 21
    lane_ids = [lane["lane_id"] for lane in config["lanes"]]
    assert lane_ids == list(dict.fromkeys(lane_ids))
    assert "exomiser_exome_baseline" in lane_ids
    assert "exomiser_exome_human_sensitivity" in lane_ids
    assert "genomiser_genome_baseline" in lane_ids
    assert "genomiser_genome_human_sensitivity" in lane_ids
    assert "lirical_genotype_default" in lane_ids
    assert "lirical_genotype_strict_sensitivity" in lane_ids
    structural = next(
        lane for lane in config["lanes"] if lane["lane_id"] == "exomiser_combined_structural_primary"
    )
    mobile = next(
        lane for lane in config["lanes"] if lane["lane_id"] == "exomiser_combined_mobile_sensitivity"
    )
    assert "manta_call_manifest" in structural["input_roles"]
    assert "xtea_call_manifest" not in structural["input_roles"]
    assert "xtea_call_manifest" in mobile["input_roles"]
    assert "manta_call_manifest" not in mobile["input_roles"]
    assert not any("verifybam" in tool_id.lower() for tool_id in actual_tools)


def test_config_and_policy_schema_order_graph_are_strict() -> None:
    config, _ = workflow.load_and_validate_config(CONFIG_PATH)
    policy, _ = ledger.load_and_validate_policy(POLICY_PATH)
    assert config["schema"] == "secure-wgs-complementary-workflow/v1"
    assert [lane["order"] for lane in config["lanes"]] == list(range(1, 22))
    assert policy["schema"] == "secure-wgs-reconciliation-policy/v1"
    assert policy["terminal_state"] == "HUMAN_REVIEW_REQUIRED"
    assert len(policy["required_receipt_roles"]) == 23
    assert [item["receipt_role"] for item in policy["method_version_relations"]] == policy[
        "required_receipt_roles"
    ]


def test_duplicate_keys_and_unknown_fields_fail_closed(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="duplicate JSON key"):
        workflow._read_json(duplicate, 1024)

    nonstandard = tmp_path / "nonstandard.json"
    nonstandard.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(workflow.WorkflowError, match="non-standard JSON constant"):
        workflow._read_json(nonstandard, 1024)

    config, _ = workflow.load_and_validate_config(CONFIG_PATH)
    mutated = copy.deepcopy(config)
    mutated["unknown"] = True
    with pytest.raises(workflow.WorkflowError, match="fields are invalid"):
        workflow.validate_config(mutated)

    policy, _ = ledger.load_and_validate_policy(POLICY_PATH)
    policy_mutated = copy.deepcopy(policy)
    policy_mutated["unknown"] = True
    with pytest.raises(workflow.WorkflowError, match="fields are invalid"):
        ledger.validate_policy(policy_mutated)


def test_missing_lane_and_out_of_order_graph_fail_closed() -> None:
    config, _ = workflow.load_and_validate_config(CONFIG_PATH)
    missing = copy.deepcopy(config)
    missing["lanes"].pop()
    with pytest.raises(workflow.WorkflowError):
        workflow.validate_config(missing)
    out_of_order = copy.deepcopy(config)
    out_of_order["lanes"][1]["order"] = 7
    with pytest.raises(workflow.WorkflowError, match="order"):
        workflow.validate_config(out_of_order)


def test_validate_and_plan_are_deterministic_and_invoke_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _basic_environment(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("validate/plan must not invoke subprocesses")

    monkeypatch.setattr(workflow.subprocess, "run", forbidden)
    for command in ("validate", "plan"):
        first = _invoke(workflow.main, _workflow_args(command, environment))
        second = _invoke(workflow.main, _workflow_args(command, environment))
        assert first == second
        assert first[0] == 0
        assert first[2] == ""
        result = json.loads(first[1])
        assert result["lane_count"] == 21
        assert result["tool_count"] == 13
        assert all("path" not in json.dumps(item).lower() for item in result["ordered_plan"])


@pytest.mark.parametrize("missing_kind", ["input", "asset"])
def test_missing_input_or_asset_fails_closed(tmp_path: Path, missing_kind: str) -> None:
    environment = _basic_environment(tmp_path)
    if missing_kind == "input":
        value = json.loads(environment["input_manifest"].read_text(encoding="utf-8"))
        value["roles"].pop()
        path = tmp_path / "input.missing.json"
        _write_json(path, value)
        args = _workflow_args("validate", {**environment, "input_manifest": path})
    else:
        value = json.loads(environment["asset_manifest"].read_text(encoding="utf-8"))
        value["assets"].pop()
        path = tmp_path / "asset.missing.json"
        _write_json(path, value)
        args = _workflow_args("validate", environment, asset_manifest=path)
    code, stdout, stderr = _invoke(workflow.main, args)
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_complementary_status=failed_closed\n"


def test_input_and_asset_digest_mismatch_fail_closed(tmp_path: Path) -> None:
    environment = _basic_environment(tmp_path)
    input_value = json.loads(environment["input_manifest"].read_text(encoding="utf-8"))
    input_value["roles"][0]["sha256"] = "0" * 64
    input_path = tmp_path / "input.bad-digest.json"
    _write_json(input_path, input_value)
    code, _, _ = _invoke(
        workflow.main,
        _workflow_args("validate", {**environment, "input_manifest": input_path}),
    )
    assert code == 2

    asset_value = json.loads(environment["asset_manifest"].read_text(encoding="utf-8"))
    asset_value["assets"][0]["sha256"] = "0" * 64
    asset_path = tmp_path / "asset.bad-digest.json"
    _write_json(asset_path, asset_value)
    code, _, _ = _invoke(
        workflow.main, _workflow_args("validate", environment, asset_manifest=asset_path)
    )
    assert code == 2


def test_successful_fake_run_is_shell_free_and_complete(
    executed_environment: dict[str, Any]
) -> None:
    assert executed_environment["run_result"]["lane_count"] == 21
    assert executed_environment["run_result"]["receipt_count"] == 21
    assert executed_environment["run_result"]["terminal_state"] == "HUMAN_REVIEW_REQUIRED"
    assert executed_environment["shell_values"]
    assert set(executed_environment["shell_values"]) == {False}
    receipt_files = list((executed_environment["receipt_root"] / "receipts").glob("*.json"))
    assert len(receipt_files) == 22


@pytest.mark.parametrize("approval_case", ["missing", "expired", "wrong_hash"])
def test_missing_expired_or_wrong_approval_fails_before_run(
    tmp_path: Path, approval_case: str
) -> None:
    environment = _basic_environment(tmp_path)
    if approval_case == "missing":
        approval_path = tmp_path / "absent-approval.json"
    elif approval_case == "expired":
        approval_path = _approval(
            tmp_path / "expired.json",
            config_raw=environment["config_raw"],
            input_raw=environment["input_raw"],
            asset_raw=environment["asset_raw"],
            approved_minutes=-120,
            expires_minutes=-60,
        )
    else:
        approval_path = _approval(
            tmp_path / "wrong.json",
            config_raw=environment["config_raw"],
            input_raw=environment["input_raw"],
            asset_raw=environment["asset_raw"],
            config_hash="0" * 64,
        )
    code, stdout, stderr = _invoke(
        workflow.main,
        _workflow_args(
            "run",
            environment,
            approval=approval_path,
            receipt_root=tmp_path / f"run-{approval_case}",
        ),
    )
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_complementary_status=failed_closed\n"


def test_repo_contained_and_existing_receipt_roots_fail_closed(
    tmp_path: Path, executed_environment: dict[str, Any]
) -> None:
    environment = _basic_environment(tmp_path)
    forbidden = ROOT / "forbidden-public-workflow-output"
    assert not forbidden.exists()
    code, _, _ = _invoke(
        workflow.main,
        _workflow_args("run", environment, receipt_root=forbidden),
    )
    assert code == 2
    assert not forbidden.exists()

    code, _, _ = _invoke(
        workflow.main,
        _workflow_args(
            "run",
            executed_environment,
            receipt_root=executed_environment["receipt_root"],
        ),
    )
    assert code == 2


def test_symlink_and_unsafe_manifest_paths_fail_closed(tmp_path: Path) -> None:
    environment = _basic_environment(tmp_path)
    manifest = json.loads(environment["input_manifest"].read_text(encoding="utf-8"))
    target = Path(manifest["roles"][0]["path"])
    symlink = tmp_path / "input-link.json"
    try:
        symlink.symlink_to(target)
    except OSError:
        symlink = None
    if symlink is not None:
        mutated = copy.deepcopy(manifest)
        mutated["roles"][0]["path"] = str(symlink)
        path = tmp_path / "input.symlink.json"
        _write_json(path, mutated)
        code, _, _ = _invoke(
            workflow.main,
            _workflow_args("validate", {**environment, "input_manifest": path}),
        )
        assert code == 2

    unsafe_file = tmp_path / "unsafe&role.json"
    unsafe_file.write_text("invented\n", encoding="utf-8")
    mutated = copy.deepcopy(manifest)
    mutated["roles"][0]["path"] = str(unsafe_file.resolve())
    mutated["roles"][0]["sha256"] = workflow._hash_file(unsafe_file)
    path = tmp_path / "input.unsafe.json"
    _write_json(path, mutated)
    code, _, _ = _invoke(
        workflow.main,
        _workflow_args("validate", {**environment, "input_manifest": path}),
    )
    assert code == 2


def test_reparse_attribute_and_posix_symlink_detection() -> None:
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    assert workflow._is_reparse(
        SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=reparse_attribute,
        )
    )
    assert workflow._is_reparse(
        SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
    )
    assert not workflow._is_reparse(
        SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0)
    )


def test_real_directory_symlink_or_reparse_path_fails_closed(tmp_path: Path) -> None:
    external = tmp_path / "external-output"
    external.mkdir()
    (external / "invented-output").write_text("invented\n", encoding="utf-8")
    generated = tmp_path / "generated-output"
    generated.mkdir()
    linked_directory = generated / "linked-directory"
    try:
        linked_directory.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc}")

    with pytest.raises(workflow.WorkflowError, match="symlink|reparse"):
        workflow._reject_symlink_chain(linked_directory / "invented-output")
    with pytest.raises(workflow.WorkflowError, match="symlink|reparse"):
        workflow._ensure_exact_generated_files(generated, set())


def test_shell_metacharacter_parameter_fails_validation(tmp_path: Path) -> None:
    environment = _basic_environment(tmp_path)
    manifest_path, _ = _mutated_asset_manifest(
        environment,
        tmp_path,
        0,
        lambda parameter: parameter["run_arguments"].append("unsafe;argument"),
    )
    code, stdout, stderr = _invoke(
        workflow.main,
        _workflow_args("validate", environment, asset_manifest=manifest_path),
    )
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_complementary_status=failed_closed\n"


def test_tool_version_mismatch_fails_closed(tmp_path: Path) -> None:
    environment = _basic_environment(tmp_path)

    def mutate(parameter: dict[str, Any]) -> None:
        parameter["version_probe_arguments"][-1] = "wrong synthetic version"

    asset_path, asset_raw = _mutated_asset_manifest(environment, tmp_path, 0, mutate)
    approval = _approval(
        tmp_path / "approval.mutated.json",
        config_raw=environment["config_raw"],
        input_raw=environment["input_raw"],
        asset_raw=asset_raw,
    )
    original_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(ROOT)
    try:
        code, stdout, stderr = _invoke(
            workflow.main,
            _workflow_args(
                "run",
                environment,
                asset_manifest=asset_path,
                approval=approval,
                receipt_root=tmp_path / "version-mismatch-run",
            ),
        )
    finally:
        if original_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = original_pythonpath
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_complementary_status=failed_closed\n"


@pytest.mark.parametrize("mode", ["nonzero", "unexpected"])
def test_tool_failure_and_unexpected_output_are_redacted(
    tmp_path: Path, mode: str
) -> None:
    environment = _basic_environment(tmp_path)

    def mutate(parameter: dict[str, Any]) -> None:
        parameter["run_arguments"][-1] = mode

    asset_path, asset_raw = _mutated_asset_manifest(environment, tmp_path, 0, mutate)
    approval = _approval(
        tmp_path / f"approval.{mode}.json",
        config_raw=environment["config_raw"],
        input_raw=environment["input_raw"],
        asset_raw=asset_raw,
    )
    original_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(ROOT)
    try:
        code, stdout, stderr = _invoke(
            workflow.main,
            _workflow_args(
                "run",
                environment,
                asset_manifest=asset_path,
                approval=approval,
                receipt_root=tmp_path / f"{mode}-run",
            ),
        )
    finally:
        if original_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = original_pythonpath
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_complementary_status=failed_closed\n"
    assert "synthetic private detail" not in stderr


def _build_with_manifest(
    manifest: dict[str, Any], tmp_path: Path, name: str
) -> tuple[int, str, str]:
    manifest_path = tmp_path / f"{name}.manifest.json"
    _write_json(manifest_path, manifest)
    return _invoke(
        ledger.main,
        [
            "build",
            "--policy",
            str(POLICY_PATH),
            "--receipt-manifest",
            str(manifest_path),
            "--output",
            str(tmp_path / f"{name}.ledger.json"),
            "--json",
        ],
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("score_blending_requested", True),
        ("phase_inference_requested", True),
        ("unsupported_phase_evidence_present", True),
        ("confidence_change_from_chromosome_screen", 0.1),
        ("human_gate_required", False),
    ],
)
def test_reconciliation_scientific_guardrails_fail_closed(
    executed_environment: dict[str, Any], tmp_path: Path, field: str, value: Any
) -> None:
    manifest = copy.deepcopy(executed_environment["receipt_manifest"])
    manifest[field] = value
    code, stdout, stderr = _build_with_manifest(manifest, tmp_path, field)
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_reconciliation_status=failed_closed\n"


def test_ledger_missing_lineage_version_cutoff_and_digest_fail_closed(
    executed_environment: dict[str, Any], tmp_path: Path
) -> None:
    base = executed_environment["receipt_manifest"]

    for case in ("missing_lineage", "wrong_version"):
        manifest = copy.deepcopy(base)
        entry = manifest["receipts"][1]
        receipt = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
        if case == "missing_lineage":
            receipt.pop("lineage_sha256")
        else:
            receipt["method_version"] = "wrong-version"
        receipt_path = tmp_path / f"{case}.receipt.json"
        _write_json(receipt_path, receipt)
        entry["path"] = str(receipt_path.resolve(strict=True))
        entry["sha256"] = workflow._hash_file(receipt_path)
        code, _, _ = _build_with_manifest(manifest, tmp_path, case)
        assert code == 2

    cutoff_manifest = copy.deepcopy(base)
    cutoff_manifest["scientific_cutoff_at_utc"] = "2000-01-01T00:00:00Z"
    code, _, _ = _build_with_manifest(cutoff_manifest, tmp_path, "bad-cutoff")
    assert code == 2

    digest_manifest = copy.deepcopy(base)
    digest_manifest["receipts"][0]["sha256"] = "0" * 64
    code, _, _ = _build_with_manifest(digest_manifest, tmp_path, "bad-digest")
    assert code == 2


def test_duplicate_receipt_evidence_fails_closed(
    executed_environment: dict[str, Any], tmp_path: Path
) -> None:
    manifest = copy.deepcopy(executed_environment["receipt_manifest"])
    manifest["receipts"][1]["path"] = manifest["receipts"][0]["path"]
    manifest["receipts"][1]["sha256"] = manifest["receipts"][0]["sha256"]
    code, _, _ = _build_with_manifest(manifest, tmp_path, "duplicate")
    assert code == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "negative_screen_confidence_increase",
        "post_cutoff_evidence",
        "duplicate_lineage",
    ],
)
def test_tampered_ledger_guardrails_fail_verification(
    executed_environment: dict[str, Any], tmp_path: Path, mutation: str
) -> None:
    ledger_value = json.loads(
        executed_environment["ledger_path"].read_text(encoding="utf-8")
    )
    if mutation == "negative_screen_confidence_increase":
        ledger_value["confidence_change_from_chromosome_screen"] = 0.1
    elif mutation == "post_cutoff_evidence":
        ledger_value["receipts"][0]["scientific_evidence_at_utc"] = (
            "2999-01-01T00:00:00Z"
        )
    else:
        ledger_value["receipts"][1]["lineage_sha256"] = ledger_value["receipts"][
            0
        ]["lineage_sha256"]
    tampered_path = tmp_path / f"{mutation}.ledger.json"
    tampered_bytes = _write_json(tampered_path, ledger_value)
    policy_hash = workflow._hash_bytes(executed_environment["policy_raw"])
    human = {
        "decided_at_utc": workflow._utc_text(workflow._utc_now()),
        "decided_by": "synthetic-independent-reviewer",
        "decision": "MORE_REVIEW_REQUIRED",
        "decision_reference": "synthetic-review-record",
        "ledger_sha256": workflow._hash_bytes(tampered_bytes),
        "policy_sha256": policy_hash,
        "schema": ledger.HUMAN_DECISION_SCHEMA,
        "scientific_cutoff_at_utc": ledger_value["scientific_cutoff_at_utc"],
        "status": "HUMAN_DECISION_RECORDED",
    }
    human_path = tmp_path / f"{mutation}.human.json"
    _write_json(human_path, human)
    code, stdout, stderr = _invoke(
        ledger.main,
        [
            "verify",
            "--policy",
            str(POLICY_PATH),
            "--ledger",
            str(tampered_path),
            "--human-decision-receipt",
            str(human_path),
            "--json",
        ],
    )
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_reconciliation_status=failed_closed\n"


def test_ledger_build_is_human_gated_and_no_overwrite(
    executed_environment: dict[str, Any]
) -> None:
    ledger_value = json.loads(executed_environment["ledger_path"].read_text(encoding="utf-8"))
    assert ledger_value["terminal_state"] == "HUMAN_REVIEW_REQUIRED"
    assert ledger_value["human_decision_receipt_required"] is True
    assert "decision" not in ledger_value
    before = executed_environment["ledger_path"].read_bytes()
    code, stdout, stderr = _invoke(
        ledger.main,
        [
            "build",
            "--policy",
            str(POLICY_PATH),
            "--receipt-manifest",
            str(executed_environment["receipt_manifest_path"]),
            "--output",
            str(executed_environment["ledger_path"]),
            "--json",
        ],
    )
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_reconciliation_status=failed_closed\n"
    assert executed_environment["ledger_path"].read_bytes() == before


def test_separately_bound_human_decision_verification_is_read_only(
    executed_environment: dict[str, Any], tmp_path: Path
) -> None:
    ledger_bytes = executed_environment["ledger_path"].read_bytes()
    ledger_value = json.loads(ledger_bytes)
    policy_hash = workflow._hash_bytes(executed_environment["policy_raw"])
    human = {
        "decided_at_utc": workflow._utc_text(workflow._utc_now()),
        "decided_by": "synthetic-independent-reviewer",
        "decision": "MORE_REVIEW_REQUIRED",
        "decision_reference": "synthetic-review-record",
        "ledger_sha256": workflow._hash_bytes(ledger_bytes),
        "policy_sha256": policy_hash,
        "schema": ledger.HUMAN_DECISION_SCHEMA,
        "scientific_cutoff_at_utc": ledger_value["scientific_cutoff_at_utc"],
        "status": "HUMAN_DECISION_RECORDED",
    }
    human_path = tmp_path / "human-decision.json"
    human_bytes = _write_json(human_path, human)
    code, stdout, stderr = _invoke(
        ledger.main,
        [
            "verify",
            "--policy",
            str(POLICY_PATH),
            "--ledger",
            str(executed_environment["ledger_path"]),
            "--human-decision-receipt",
            str(human_path),
            "--json",
        ],
    )
    assert code == 0, stderr
    result = json.loads(stdout)
    assert result["decision"] == "MORE_REVIEW_REQUIRED"
    assert executed_environment["ledger_path"].read_bytes() == ledger_bytes
    assert human_path.read_bytes() == human_bytes

    wrong = copy.deepcopy(human)
    wrong["ledger_sha256"] = "0" * 64
    wrong_path = tmp_path / "human-decision.wrong.json"
    _write_json(wrong_path, wrong)
    code, _, _ = _invoke(
        ledger.main,
        [
            "verify",
            "--policy",
            str(POLICY_PATH),
            "--ledger",
            str(executed_environment["ledger_path"]),
            "--human-decision-receipt",
            str(wrong_path),
            "--json",
        ],
    )
    assert code == 2


def test_missing_human_decision_receipt_fails_verification(
    executed_environment: dict[str, Any], tmp_path: Path
) -> None:
    code, stdout, stderr = _invoke(
        ledger.main,
        [
            "verify",
            "--policy",
            str(POLICY_PATH),
            "--ledger",
            str(executed_environment["ledger_path"]),
            "--human-decision-receipt",
            str(tmp_path / "absent.json"),
            "--json",
        ],
    )
    assert code == 2
    assert stdout == ""
    assert stderr == "secure_wgs_reconciliation_status=failed_closed\n"


def test_synthetic_smoke_is_deterministic_and_non_biological() -> None:
    command = [sys.executable, str(PUBLIC_ROOT / "synthetic_end_to_end_smoke.py"), "--json"]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["status"] == "passed"
    assert result["negative_self_test"] == "passed"
    assert result["biological_equivalence_checked"] is False
    assert result["protected_wgs_rerun_performed"] is False
    assert result["ledger_terminal_state"] == "HUMAN_REVIEW_REQUIRED"


def test_committed_contracts_are_privacy_safe() -> None:
    combined = CONFIG_PATH.read_text(encoding="utf-8") + "\n" + POLICY_PATH.read_text(
        encoding="utf-8"
    )
    forbidden = {
        "drive_path": re.compile(r"(?i)\b[a-z]:[\\/]"),
        "absolute_runtime_path": re.compile(
            r"(?:^|\s)/(?!/)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._${}-]+)+"
        ),
        "url": re.compile(r"(?i)\b(?:https?|s3|gs|ssh)://"),
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
        "protected_name": re.compile(r"(?i)\b(?:WGS_[A-Za-z0-9_.-]+|EX[0-9]{5,}|HGW[A-Za-z0-9]{5,})\b"),
    }
    findings = {name: pattern.findall(combined) for name, pattern in forbidden.items()}
    assert findings == {name: [] for name in forbidden}
    assert "identity_qc" not in combined.lower()
