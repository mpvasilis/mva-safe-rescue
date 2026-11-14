#!/usr/bin/env python3
"""Exercise public Stage-5/Stage-7 contracts with invented role markers only.

This smoke validates orchestration, execution contracts, provenance, and
failure policy.  It does not test biological equivalence, external-tool
correctness, or a protected WGS rerun.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from analysis.secure_wgs.public import (
    COMPLEMENTARY_WORKFLOW_SCHEMA,
    RECONCILIATION_POLICY_SCHEMA,
)
from analysis.secure_wgs.public.build_reconciliation_ledger import (
    EVIDENCE_RECEIPT_SCHEMA,
    RECEIPT_MANIFEST_SCHEMA,
    load_and_validate_policy,
    main as reconciliation_main,
)
from analysis.secure_wgs.public.run_complementary_workflow import (
    APPROVAL_SCHEMA,
    ASSET_MANIFEST_SCHEMA,
    INPUT_MANIFEST_SCHEMA,
    PARAMETER_SCHEMA,
    REPO_ROOT,
    WorkflowError,
    _hash_bytes,
    _hash_file,
    _json_bytes,
    _utc_now,
    _utc_text,
    compute_lineage_sha256,
    load_and_validate_config,
    main as workflow_main,
)


RESULT_SCHEMA = "secure-wgs-synthetic-end-to-end-result/v1"
CONFIG_PATH = Path(__file__).with_name("complementary_workflow.v1.json")
POLICY_PATH = Path(__file__).with_name("reconciliation_policy.v1.json")


def _write_json(path: Path, value: Mapping[str, Any]) -> bytes:
    raw = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _fake_tool_version(value: str) -> int:
    if not value or len(value) > 160 or any(ord(char) < 32 for char in value):
        return 2
    print(value)
    return 0


def _fake_tool_run(contract_path: Path, mode: str) -> int:
    if mode == "nonzero":
        print("synthetic private detail must remain redacted", file=sys.stderr)
        return 17
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("schema") != "secure-wgs-private-lane-runtime/v1":
            return 2
        lane_id = contract["lane_id"]
        outputs = contract["output_paths"]
        if not isinstance(outputs, dict) or not outputs:
            return 2
        for role, path_text in outputs.items():
            path = Path(path_text)
            path.write_text(
                json.dumps(
                    {
                        "kind": "invented_role_marker",
                        "lane_id": lane_id,
                        "role": role,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
        if mode == "unexpected":
            (contract_path.parent / "unexpected.private").write_text(
                "invented\n", encoding="utf-8"
            )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 2
    return 0


def _invoke_main(function: Any, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = function(argv)
    return result, stdout.getvalue(), stderr.getvalue()


def _prepare_synthetic_material(
    root: Path, config: Mapping[str, Any]
) -> tuple[Path, Path, bytes, bytes]:
    input_entries: list[dict[str, Any]] = []
    input_root = root / "inputs"
    input_root.mkdir()
    for role in config["source_roles"]:
        path = input_root / f"{role}.json"
        path.write_text(
            json.dumps(
                {"kind": "invented_input_role", "role": role},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        input_entries.append(
            {"path": str(path.resolve()), "role": role, "sha256": _hash_file(path)}
        )
    input_manifest_path = root / "input_manifest.json"
    input_raw = _write_json(
        input_manifest_path,
        {"roles": input_entries, "schema": INPUT_MANIFEST_SCHEMA},
    )

    lane_by_parameter = {lane["parameter_role"]: lane for lane in config["lanes"]}
    tool_by_id = {tool["tool_id"]: tool for tool in config["tool_contracts"]}
    asset_root = root / "assets"
    asset_root.mkdir()
    asset_entries: list[dict[str, Any]] = []
    # A project-local virtual environment is repository material and must not be
    # accepted as an external executable asset.  Bind the synthetic tool to the
    # base interpreter so the smoke exercises the same outside-repository
    # boundary required of real runtime assets.
    base_executable = getattr(sys, "_base_executable", None) or sys.executable
    python_path = Path(base_executable).resolve(strict=True)
    python_hash = _hash_file(python_path)
    for asset in config["asset_contracts"]:
        role = asset["role"]
        if asset["kind"] == "executable":
            path = python_path
            digest = python_hash
        elif role in lane_by_parameter:
            lane = lane_by_parameter[role]
            tool = tool_by_id[lane["tool_id"]]
            path = asset_root / f"{role}.json"
            parameter = {
                "lane_id": lane["lane_id"],
                "run_arguments": [
                    "-m",
                    "analysis.secure_wgs.public.synthetic_end_to_end_smoke",
                    "--fake-tool-run",
                    "{runtime:lane_contract}",
                    "normal",
                ],
                "schema": PARAMETER_SCHEMA,
                "tool_id": lane["tool_id"],
                "version_probe_arguments": [
                    "-m",
                    "analysis.secure_wgs.public.synthetic_end_to_end_smoke",
                    "--fake-tool-version",
                    tool["version_match"],
                ],
            }
            _write_json(path, parameter)
            digest = _hash_file(path)
        else:
            path = asset_root / f"{role}.json"
            path.write_text(
                json.dumps(
                    {"kind": "invented_external_asset_role", "role": role},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            digest = _hash_file(path)
        asset_entries.append(
            {
                "licence_acknowledged": True,
                "path": str(path),
                "role": role,
                "sha256": digest,
                "version": asset["version"],
            }
        )
    asset_manifest_path = root / "asset_manifest.json"
    asset_raw = _write_json(
        asset_manifest_path,
        {"assets": asset_entries, "schema": ASSET_MANIFEST_SCHEMA},
    )
    return input_manifest_path, asset_manifest_path, input_raw, asset_raw


def _make_external_receipt(
    relation: Mapping[str, Any], timestamp: str
) -> dict[str, Any]:
    seed = relation["receipt_role"].encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    receipt = {
        "asset_contract_sha256": hashlib.sha256(b"invented-assets").hexdigest(),
        "asset_digests": {"invented_asset_role": digest},
        "completed_at_utc": timestamp,
        "config_sha256": hashlib.sha256(b"invented-config").hexdigest(),
        "input_contract_sha256": hashlib.sha256(b"invented-inputs").hexdigest(),
        "input_digests": {"invented_input_role": digest},
        "lane_id": relation["method_id"],
        "lineage_sha256": "0" * 64,
        "method_id": relation["method_id"],
        "method_version": relation["method_version"],
        "output_digests": {"invented_output_role": digest},
        "receipt_role": relation["receipt_role"],
        "schema": EVIDENCE_RECEIPT_SCHEMA,
        "scientific_evidence_at_utc": timestamp,
        "started_at_utc": timestamp,
        "status": relation["allowed_states"][0],
    }
    receipt["lineage_sha256"] = compute_lineage_sha256(receipt)
    return receipt


def run_smoke(config_path: Path, policy_path: Path) -> dict[str, Any]:
    config, config_raw = load_and_validate_config(config_path)
    policy, policy_raw = load_and_validate_policy(policy_path)
    if config["schema"] != COMPLEMENTARY_WORKFLOW_SCHEMA:
        raise WorkflowError("unexpected complementary schema")
    if policy["schema"] != RECONCILIATION_POLICY_SCHEMA:
        raise WorkflowError("unexpected reconciliation schema")

    with tempfile.TemporaryDirectory(prefix="secure-wgs-public-smoke-") as temporary:
        root = Path(temporary).resolve(strict=True)
        input_manifest, asset_manifest, input_raw, asset_raw = _prepare_synthetic_material(
            root, config
        )
        common = [
            "--config",
            str(config_path.resolve(strict=True)),
            "--input-manifest",
            str(input_manifest),
            "--asset-manifest",
            str(asset_manifest),
            "--json",
        ]

        validate_code, validate_out, validate_err = _invoke_main(
            workflow_main, ["validate", *common]
        )
        plan_code, plan_out, plan_err = _invoke_main(workflow_main, ["plan", *common])
        if validate_code != 0 or plan_code != 0 or validate_err or plan_err:
            raise WorkflowError("synthetic validate or plan failed")
        validate_result = json.loads(validate_out)
        plan_result = json.loads(plan_out)

        bad_asset = json.loads(asset_manifest.read_text(encoding="utf-8"))
        bad_asset["assets"][0]["version"] = "invalid-version"
        bad_asset_path = root / "asset_manifest.invalid.json"
        _write_json(bad_asset_path, bad_asset)
        negative_common = [
            "validate",
            "--config",
            str(config_path.resolve(strict=True)),
            "--input-manifest",
            str(input_manifest),
            "--asset-manifest",
            str(bad_asset_path),
            "--json",
        ]
        negative_code, negative_out, negative_err = _invoke_main(
            workflow_main, negative_common
        )
        if (
            negative_code != 2
            or negative_out
            or negative_err != "secure_wgs_complementary_status=failed_closed\n"
        ):
            raise WorkflowError("negative self-test did not fail closed")

        now = _utc_now()
        approval = {
            "approved_at_utc": _utc_text(now - timedelta(minutes=1)),
            "approved_by": "synthetic-smoke-operator",
            "asset_manifest_sha256": _hash_bytes(asset_raw),
            "config_sha256": _hash_bytes(config_raw),
            "expires_at_utc": _utc_text(now + timedelta(minutes=30)),
            "input_manifest_sha256": _hash_bytes(input_raw),
            "purpose": "RESEARCH_ONLY",
            "schema": APPROVAL_SCHEMA,
            "status": "APPROVED",
        }
        approval_path = root / "approval.json"
        _write_json(approval_path, approval)
        run_root = root / "run"
        original_pythonpath = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(REPO_ROOT) + (
            os.pathsep + original_pythonpath if original_pythonpath else ""
        )
        try:
            run_code, run_out, run_err = _invoke_main(
                workflow_main,
                [
                    "run",
                    *common,
                    "--approval-record",
                    str(approval_path),
                    "--receipt-root",
                    str(run_root),
                ],
            )
        finally:
            if original_pythonpath is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = original_pythonpath
        if run_code != 0 or run_err:
            raise WorkflowError("synthetic run failed")
        run_result = json.loads(run_out)

        relation_by_role = {
            relation["receipt_role"]: relation
            for relation in policy["method_version_relations"]
        }
        evidence_root = root / "evidence"
        evidence_root.mkdir()
        timestamp = _utc_text(_utc_now())
        receipt_entries: list[dict[str, str]] = []
        for role in policy["required_receipt_roles"]:
            generated = run_root / "receipts" / f"{role}.json"
            if generated.is_file():
                receipt_path = generated
            else:
                receipt_path = evidence_root / f"{role}.json"
                _write_json(
                    receipt_path,
                    _make_external_receipt(relation_by_role[role], timestamp),
                )
            receipt_entries.append(
                {
                    "path": str(receipt_path.resolve(strict=True)),
                    "role": role,
                    "sha256": _hash_file(receipt_path),
                }
            )
        receipt_manifest_path = root / "receipt_manifest.json"
        _write_json(
            receipt_manifest_path,
            {
                "chromosome_screen_state": "NO_SIGNAL_RESEARCH_ONLY",
                "confidence_change_from_chromosome_screen": 0,
                "human_gate_required": True,
                "phase_inference_requested": False,
                "phase_status": "UNRESOLVED",
                "receipts": receipt_entries,
                "schema": RECEIPT_MANIFEST_SCHEMA,
                "scientific_cutoff_at_utc": timestamp,
                "score_blending_requested": False,
                "score_handling": "SEPARATE_NON_COMMENSURATE",
                "unsupported_phase_evidence_present": False,
            },
        )
        ledger_path = root / "reconciliation_ledger.json"
        build_code, build_out, build_err = _invoke_main(
            reconciliation_main,
            [
                "build",
                "--policy",
                str(policy_path.resolve(strict=True)),
                "--receipt-manifest",
                str(receipt_manifest_path),
                "--output",
                str(ledger_path),
                "--json",
            ],
        )
        if build_code != 0 or build_err:
            raise WorkflowError("synthetic reconciliation build failed")
        build_result = json.loads(build_out)

    method_inventory = [
        {
            "method_id": relation["method_id"],
            "method_version": relation["method_version"],
            "receipt_role": relation["receipt_role"],
        }
        for relation in policy["method_version_relations"]
    ]
    return {
        "biological_equivalence_checked": False,
        "config_sha256": _hash_bytes(config_raw),
        "lane_count": validate_result["lane_count"],
        "ledger_terminal_state": build_result["terminal_state"],
        "method_inventory_sha256": hashlib.sha256(
            json.dumps(
                method_inventory, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
        "negative_self_test": "passed",
        "plan_lane_count": plan_result["lane_count"],
        "policy_sha256": _hash_bytes(policy_raw),
        "protected_wgs_rerun_performed": False,
        "receipt_count": build_result["receipt_count"],
        "result_schema": RESULT_SCHEMA,
        "run_lane_count": run_result["lane_count"],
        "status": "passed",
        "tool_count": validate_result["tool_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a role-only public Stage-5/Stage-7 synthetic smoke."
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "--fake-tool-version":
        return _fake_tool_version(arguments[1] if len(arguments) == 2 else "")
    if arguments and arguments[0] == "--fake-tool-run":
        if len(arguments) != 3:
            return 2
        return _fake_tool_run(Path(arguments[1]), arguments[2])
    args = build_parser().parse_args(arguments)
    try:
        result = run_smoke(args.config, args.policy)
    except (WorkflowError, OSError, ValueError, json.JSONDecodeError):
        print("secure_wgs_synthetic_end_to_end_status=failed_closed", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "secure_wgs_synthetic_end_to_end_status=passed "
            f"lanes={result['lane_count']} receipts={result['receipt_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
