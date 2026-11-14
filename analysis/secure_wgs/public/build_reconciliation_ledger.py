#!/usr/bin/env python3
"""Build or verify a deterministic, human-gated reconciliation ledger.

The builder validates provenance and scientific guardrails only.  It never
selects findings, assigns pathogenicity, infers phase, blends model scores,
changes confidence, or authors a human decision receipt.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from analysis.secure_wgs.public import RECONCILIATION_POLICY_SCHEMA
from analysis.secure_wgs.public.run_complementary_workflow import (
    LANE_RECEIPT_KEYS,
    LANE_RECEIPT_SCHEMA,
    MAX_MANIFEST_BYTES,
    REPO_ROOT,
    SHA256_PATTERN,
    UTC_PATTERN,
    WorkflowError,
    _atomic_no_overwrite,
    _canonical_hash,
    _exact_keys,
    _hash_bytes,
    _hash_file,
    _identifier,
    _identifier_list,
    _is_within,
    _json_bytes,
    _parse_utc,
    _privacy_check,
    _read_json,
    _reject_symlink_chain,
    _safe_existing_file,
    _sha256_text,
    _text,
    _text_list,
    _utc_now,
    compute_lineage_sha256,
)


EVIDENCE_RECEIPT_SCHEMA = "secure-wgs-evidence-receipt/v1"
RECEIPT_MANIFEST_SCHEMA = "secure-wgs-receipt-manifest/v1"
LEDGER_SCHEMA = "secure-wgs-reconciliation-ledger/v1"
HUMAN_DECISION_SCHEMA = "secure-wgs-human-decision-receipt/v1"
RESULT_SCHEMA = "secure-wgs-reconciliation-operation-result/v1"
MAX_POLICY_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_LEDGER_BYTES = 2 * 1024 * 1024
MAX_HUMAN_RECEIPT_BYTES = 256 * 1024

POLICY_KEYS = {
    "schema",
    "policy_id",
    "terminal_state",
    "required_receipt_roles",
    "method_version_relations",
    "allowed_evidence_states",
    "lineage_rules",
    "score_policy",
    "phase_policy",
    "chromosome_screen_policy",
    "human_gate",
}
RELATION_KEYS = {
    "receipt_role",
    "receipt_schema",
    "method_id",
    "method_version",
    "allowed_states",
}
LINEAGE_RULE_KEYS = {
    "require_exact_receipt_digest",
    "require_lineage_sha256",
    "require_scientific_evidence_at_or_before_cutoff",
    "reject_duplicate_evidence",
}
SCORE_POLICY_KEYS = {"required_handling", "blending_allowed"}
PHASE_POLICY_KEYS = {
    "required_status",
    "inference_allowed",
    "unsupported_evidence_allowed",
}
CHROMOSOME_POLICY_KEYS = {"negative_state", "maximum_confidence_change"}
HUMAN_GATE_KEYS = {
    "required",
    "decision_receipt_schema",
    "builder_may_author_decision",
    "allowed_decisions",
}
RECEIPT_MANIFEST_KEYS = {
    "schema",
    "scientific_cutoff_at_utc",
    "score_handling",
    "score_blending_requested",
    "phase_status",
    "phase_inference_requested",
    "unsupported_phase_evidence_present",
    "chromosome_screen_state",
    "confidence_change_from_chromosome_screen",
    "human_gate_required",
    "receipts",
}
RECEIPT_ENTRY_KEYS = {"role", "path", "sha256"}
LEDGER_KEYS = {
    "schema",
    "policy_sha256",
    "receipt_manifest_sha256",
    "scientific_cutoff_at_utc",
    "terminal_state",
    "score_handling",
    "phase_status",
    "chromosome_screen_state",
    "confidence_change_from_chromosome_screen",
    "human_decision_receipt_required",
    "receipt_count",
    "receipts",
}
LEDGER_RECEIPT_KEYS = {
    "order",
    "receipt_role",
    "receipt_sha256",
    "lineage_sha256",
    "method_id",
    "method_version",
    "status",
    "scientific_evidence_at_utc",
}
HUMAN_DECISION_KEYS = {
    "schema",
    "status",
    "decision",
    "decided_at_utc",
    "decided_by",
    "decision_reference",
    "policy_sha256",
    "ledger_sha256",
    "scientific_cutoff_at_utc",
}
ALLOWED_RECEIPT_SCHEMAS = {LANE_RECEIPT_SCHEMA, EVIDENCE_RECEIPT_SCHEMA}
SAFE_PRIVATE_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:@/+-]{0,199}$")


def load_and_validate_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    policy, raw = _read_json(path, MAX_POLICY_BYTES)
    validate_policy(policy)
    return policy, raw


def validate_policy(policy: Mapping[str, Any]) -> None:
    if not isinstance(policy, dict):
        raise WorkflowError("policy must be an object")
    _exact_keys(policy, POLICY_KEYS, "policy")
    if policy["schema"] != RECONCILIATION_POLICY_SCHEMA:
        raise WorkflowError("policy schema is invalid")
    _identifier(policy["policy_id"], "policy_id")
    if policy["terminal_state"] != "HUMAN_REVIEW_REQUIRED":
        raise WorkflowError("policy terminal state is invalid")
    required_roles = _identifier_list(
        policy["required_receipt_roles"], "required_receipt_roles"
    )
    allowed_states = _text_list(policy["allowed_evidence_states"], "allowed states")
    if len(allowed_states) != len(set(allowed_states)):
        raise WorkflowError("allowed evidence states are duplicated")

    relations = policy["method_version_relations"]
    if not isinstance(relations, list) or len(relations) != len(required_roles):
        raise WorkflowError("method/version relations do not match required receipts")
    relation_roles: list[str] = []
    for relation in relations:
        if not isinstance(relation, dict):
            raise WorkflowError("method/version relation must be an object")
        _exact_keys(relation, RELATION_KEYS, "method/version relation")
        role = _identifier(relation["receipt_role"], "relation receipt role")
        relation_roles.append(role)
        if relation["receipt_schema"] not in ALLOWED_RECEIPT_SCHEMAS:
            raise WorkflowError("relation receipt schema is invalid")
        _identifier(relation["method_id"], "relation method_id")
        _text(relation["method_version"], "relation method_version", 200)
        states = _text_list(relation["allowed_states"], "relation allowed states")
        if not set(states).issubset(set(allowed_states)) or len(states) != len(set(states)):
            raise WorkflowError("relation evidence states are invalid")
    if relation_roles != required_roles:
        raise WorkflowError("method/version relation order must match required receipts")

    lineage = policy["lineage_rules"]
    if not isinstance(lineage, dict):
        raise WorkflowError("lineage rules must be an object")
    _exact_keys(lineage, LINEAGE_RULE_KEYS, "lineage rules")
    if any(lineage[key] is not True for key in LINEAGE_RULE_KEYS):
        raise WorkflowError("all lineage rules must fail closed")

    score = policy["score_policy"]
    if not isinstance(score, dict):
        raise WorkflowError("score policy must be an object")
    _exact_keys(score, SCORE_POLICY_KEYS, "score policy")
    if score["required_handling"] != "SEPARATE_NON_COMMENSURATE":
        raise WorkflowError("score handling policy is invalid")
    if score["blending_allowed"] is not False:
        raise WorkflowError("score blending must be forbidden")

    phase = policy["phase_policy"]
    if not isinstance(phase, dict):
        raise WorkflowError("phase policy must be an object")
    _exact_keys(phase, PHASE_POLICY_KEYS, "phase policy")
    if phase != {
        "required_status": "UNRESOLVED",
        "inference_allowed": False,
        "unsupported_evidence_allowed": False,
    }:
        raise WorkflowError("phase policy is invalid")

    chromosome = policy["chromosome_screen_policy"]
    if not isinstance(chromosome, dict):
        raise WorkflowError("chromosome screen policy must be an object")
    _exact_keys(chromosome, CHROMOSOME_POLICY_KEYS, "chromosome screen policy")
    if chromosome["negative_state"] != "NO_SIGNAL_RESEARCH_ONLY":
        raise WorkflowError("negative chromosome-screen state is invalid")
    if type(chromosome["maximum_confidence_change"]) not in {int, float}:
        raise WorkflowError("maximum confidence change must be numeric")
    if chromosome["maximum_confidence_change"] != 0:
        raise WorkflowError("negative screen may not increase confidence")

    gate = policy["human_gate"]
    if not isinstance(gate, dict):
        raise WorkflowError("human gate must be an object")
    _exact_keys(gate, HUMAN_GATE_KEYS, "human gate")
    if gate["required"] is not True or gate["builder_may_author_decision"] is not False:
        raise WorkflowError("human decision gate is invalid")
    if gate["decision_receipt_schema"] != HUMAN_DECISION_SCHEMA:
        raise WorkflowError("human decision schema is invalid")
    decisions = _text_list(gate["allowed_decisions"], "allowed decisions")
    if len(decisions) != len(set(decisions)):
        raise WorkflowError("allowed human decisions are duplicated")
    _privacy_check(policy)


def _validate_digest_map(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise WorkflowError(f"{label} must be a nonempty digest map")
    result: dict[str, str] = {}
    for key, digest in value.items():
        role = _identifier(key, f"{label} role")
        if role in result:
            raise WorkflowError(f"{label} role is duplicated")
        result[role] = _sha256_text(digest, f"{label} digest")
    return result


def _validate_receipt(
    receipt: Mapping[str, Any],
    relation: Mapping[str, Any],
    cutoff: datetime,
) -> None:
    if not isinstance(receipt, dict):
        raise WorkflowError("receipt must be an object")
    _exact_keys(receipt, LANE_RECEIPT_KEYS, "receipt")
    if receipt["schema"] != relation["receipt_schema"]:
        raise WorkflowError("receipt schema does not match policy")
    if receipt["receipt_role"] != relation["receipt_role"]:
        raise WorkflowError("receipt role does not match policy")
    if receipt["method_id"] != relation["method_id"]:
        raise WorkflowError("receipt method does not match policy")
    if receipt["method_version"] != relation["method_version"]:
        raise WorkflowError("receipt version does not match policy")
    if receipt["status"] not in relation["allowed_states"]:
        raise WorkflowError("receipt evidence state does not match policy")
    _identifier(receipt["lane_id"], "receipt lane_id")
    started = _parse_utc(receipt["started_at_utc"], "receipt started_at_utc")
    completed = _parse_utc(receipt["completed_at_utc"], "receipt completed_at_utc")
    scientific = _parse_utc(
        receipt["scientific_evidence_at_utc"], "receipt scientific_evidence_at_utc"
    )
    if started > completed or scientific != completed or scientific > cutoff:
        raise WorkflowError("receipt timestamps are malformed or beyond the cutoff")
    _sha256_text(receipt["config_sha256"], "receipt config hash")
    _sha256_text(receipt["input_contract_sha256"], "receipt input contract hash")
    _sha256_text(receipt["asset_contract_sha256"], "receipt asset contract hash")
    _validate_digest_map(receipt["input_digests"], "input digests")
    _validate_digest_map(receipt["asset_digests"], "asset digests")
    _validate_digest_map(receipt["output_digests"], "output digests")
    lineage = _sha256_text(receipt["lineage_sha256"], "receipt lineage hash")
    if lineage != compute_lineage_sha256(receipt):
        raise WorkflowError("receipt lineage hash mismatch")


def _safe_output_path(path: Path) -> Path:
    if not path.is_absolute():
        raise WorkflowError("ledger output path must be absolute")
    resolved = path.resolve(strict=False)
    repo = REPO_ROOT.resolve(strict=True)
    if _is_within(resolved, repo) or resolved == repo:
        raise WorkflowError("ledger output must remain outside the repository")
    if resolved.exists() or resolved.is_symlink():
        raise WorkflowError("ledger output already exists")
    _reject_symlink_chain(resolved.parent)
    if not resolved.parent.resolve(strict=True).is_dir():
        raise WorkflowError("ledger output parent is invalid")
    return resolved


def build_ledger(
    policy: Mapping[str, Any],
    policy_raw: bytes,
    receipt_manifest_path: Path,
    output_path: Path,
) -> tuple[dict[str, Any], bytes]:
    manifest, manifest_raw = _read_json(receipt_manifest_path, MAX_MANIFEST_BYTES)
    _exact_keys(manifest, RECEIPT_MANIFEST_KEYS, "receipt manifest")
    if manifest["schema"] != RECEIPT_MANIFEST_SCHEMA:
        raise WorkflowError("receipt manifest schema is invalid")
    cutoff = _parse_utc(manifest["scientific_cutoff_at_utc"], "scientific cutoff")
    if manifest["score_handling"] != policy["score_policy"]["required_handling"]:
        raise WorkflowError("score handling does not match policy")
    if manifest["score_blending_requested"] is not False:
        raise WorkflowError("score blending is forbidden")
    if manifest["phase_status"] != policy["phase_policy"]["required_status"]:
        raise WorkflowError("phase status does not match policy")
    if manifest["phase_inference_requested"] is not False:
        raise WorkflowError("unsupported phase inference is forbidden")
    if manifest["unsupported_phase_evidence_present"] is not False:
        raise WorkflowError("unsupported phase evidence is forbidden")
    _text(manifest["chromosome_screen_state"], "chromosome screen state", 80)
    confidence_change = manifest["confidence_change_from_chromosome_screen"]
    if type(confidence_change) not in {int, float} or not math.isfinite(
        confidence_change
    ):
        raise WorkflowError("chromosome-screen confidence change must be numeric")
    if (
        manifest["chromosome_screen_state"]
        == policy["chromosome_screen_policy"]["negative_state"]
        and confidence_change
        > policy["chromosome_screen_policy"]["maximum_confidence_change"]
    ):
        raise WorkflowError("negative chromosome screen may not increase confidence")
    if manifest["human_gate_required"] is not True:
        raise WorkflowError("human decision gate is mandatory")

    entries = manifest["receipts"]
    if not isinstance(entries, list):
        raise WorkflowError("receipt entries must be a list")
    required_roles = policy["required_receipt_roles"]
    if len(entries) != len(required_roles):
        raise WorkflowError("required receipt count is incomplete")
    relations = {
        relation["receipt_role"]: relation
        for relation in policy["method_version_relations"]
    }
    seen_paths: set[Path] = set()
    seen_hashes: set[str] = set()
    seen_lineages: set[str] = set()
    ledger_entries: list[dict[str, Any]] = []
    for order, (entry, required_role) in enumerate(
        zip(entries, required_roles, strict=True), start=1
    ):
        if not isinstance(entry, dict):
            raise WorkflowError("receipt entry must be an object")
        _exact_keys(entry, RECEIPT_ENTRY_KEYS, "receipt entry")
        if entry["role"] != required_role:
            raise WorkflowError("receipt manifest order or role is invalid")
        expected_hash = _sha256_text(entry["sha256"], "declared receipt hash")
        path = _safe_existing_file(entry["path"], "receipt path")
        if path in seen_paths or expected_hash in seen_hashes:
            raise WorkflowError("duplicate receipt evidence is forbidden")
        receipt, receipt_raw = _read_json(path, MAX_RECEIPT_BYTES)
        if _hash_bytes(receipt_raw) != expected_hash:
            raise WorkflowError("receipt digest mismatch")
        relation = relations[required_role]
        _validate_receipt(receipt, relation, cutoff)
        if receipt["lineage_sha256"] in seen_lineages:
            raise WorkflowError("duplicate receipt lineage is forbidden")
        seen_paths.add(path)
        seen_hashes.add(expected_hash)
        seen_lineages.add(receipt["lineage_sha256"])
        ledger_entries.append(
            {
                "lineage_sha256": receipt["lineage_sha256"],
                "method_id": receipt["method_id"],
                "method_version": receipt["method_version"],
                "order": order,
                "receipt_role": required_role,
                "receipt_sha256": expected_hash,
                "scientific_evidence_at_utc": receipt["scientific_evidence_at_utc"],
                "status": receipt["status"],
            }
        )

    chromosome_entry = next(
        item for item in ledger_entries if item["receipt_role"] == "chromosome_screen_receipt"
    )
    if chromosome_entry["status"] != manifest["chromosome_screen_state"]:
        raise WorkflowError("chromosome-screen state and receipt disagree")

    ledger = {
        "chromosome_screen_state": manifest["chromosome_screen_state"],
        "confidence_change_from_chromosome_screen": confidence_change,
        "human_decision_receipt_required": True,
        "phase_status": manifest["phase_status"],
        "policy_sha256": _hash_bytes(policy_raw),
        "receipt_count": len(ledger_entries),
        "receipt_manifest_sha256": _hash_bytes(manifest_raw),
        "receipts": ledger_entries,
        "schema": LEDGER_SCHEMA,
        "scientific_cutoff_at_utc": manifest["scientific_cutoff_at_utc"],
        "score_handling": manifest["score_handling"],
        "terminal_state": "HUMAN_REVIEW_REQUIRED",
    }
    _exact_keys(ledger, LEDGER_KEYS, "generated ledger")
    ledger_bytes = _json_bytes(ledger)
    output = _safe_output_path(output_path)
    _atomic_no_overwrite(output, ledger_bytes)
    result = {
        "ledger_sha256": _hash_bytes(ledger_bytes),
        "operation": "build",
        "policy_sha256": _hash_bytes(policy_raw),
        "receipt_count": len(ledger_entries),
        "result_schema": RESULT_SCHEMA,
        "status": "passed",
        "terminal_state": "HUMAN_REVIEW_REQUIRED",
    }
    return result, ledger_bytes


def _validate_ledger(
    ledger: Mapping[str, Any], policy: Mapping[str, Any], policy_hash: str
) -> None:
    if not isinstance(ledger, dict):
        raise WorkflowError("ledger must be an object")
    _exact_keys(ledger, LEDGER_KEYS, "ledger")
    if ledger["schema"] != LEDGER_SCHEMA or ledger["policy_sha256"] != policy_hash:
        raise WorkflowError("ledger schema or policy binding is invalid")
    if ledger["terminal_state"] != "HUMAN_REVIEW_REQUIRED":
        raise WorkflowError("ledger terminal state is invalid")
    if ledger["human_decision_receipt_required"] is not True:
        raise WorkflowError("ledger human gate is missing")
    if ledger["score_handling"] != policy["score_policy"]["required_handling"]:
        raise WorkflowError("ledger score handling is invalid")
    if ledger["phase_status"] != policy["phase_policy"]["required_status"]:
        raise WorkflowError("ledger phase status is invalid")
    _parse_utc(ledger["scientific_cutoff_at_utc"], "ledger scientific cutoff")
    _sha256_text(ledger["receipt_manifest_sha256"], "ledger manifest hash")
    if (
        type(ledger["receipt_count"]) is not int
        or ledger["receipt_count"] != len(policy["required_receipt_roles"])
    ):
        raise WorkflowError("ledger receipt count is invalid")
    entries = ledger["receipts"]
    if not isinstance(entries, list) or len(entries) != ledger["receipt_count"]:
        raise WorkflowError("ledger receipt entries are invalid")
    if [entry.get("receipt_role") for entry in entries] != policy["required_receipt_roles"]:
        raise WorkflowError("ledger receipt order is invalid")
    relations = {
        item["receipt_role"]: item for item in policy["method_version_relations"]
    }
    cutoff = _parse_utc(ledger["scientific_cutoff_at_utc"], "ledger cutoff")
    seen_receipt_hashes: set[str] = set()
    seen_lineages: set[str] = set()
    for expected_order, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise WorkflowError("ledger receipt entry must be an object")
        _exact_keys(entry, LEDGER_RECEIPT_KEYS, "ledger receipt entry")
        if type(entry["order"]) is not int or entry["order"] != expected_order:
            raise WorkflowError("ledger receipt order is invalid")
        relation = relations[entry["receipt_role"]]
        if entry["method_id"] != relation["method_id"]:
            raise WorkflowError("ledger method relation is invalid")
        if entry["method_version"] != relation["method_version"]:
            raise WorkflowError("ledger method version is invalid")
        if entry["status"] not in relation["allowed_states"]:
            raise WorkflowError("ledger evidence state is invalid")
        receipt_hash = _sha256_text(entry["receipt_sha256"], "ledger receipt hash")
        lineage_hash = _sha256_text(entry["lineage_sha256"], "ledger lineage hash")
        if receipt_hash in seen_receipt_hashes or lineage_hash in seen_lineages:
            raise WorkflowError("ledger contains duplicate evidence")
        seen_receipt_hashes.add(receipt_hash)
        seen_lineages.add(lineage_hash)
        evidence_at = _parse_utc(
            entry["scientific_evidence_at_utc"], "ledger evidence timestamp"
        )
        if evidence_at > cutoff:
            raise WorkflowError("ledger evidence is after the scientific cutoff")

    chromosome_state = _text(
        ledger["chromosome_screen_state"], "ledger chromosome-screen state", 80
    )
    chromosome_entry = next(
        entry
        for entry in entries
        if entry["receipt_role"] == "chromosome_screen_receipt"
    )
    if chromosome_state != chromosome_entry["status"]:
        raise WorkflowError("ledger chromosome-screen state and receipt disagree")
    confidence_change = ledger["confidence_change_from_chromosome_screen"]
    if type(confidence_change) not in {int, float} or not math.isfinite(
        confidence_change
    ):
        raise WorkflowError("ledger chromosome-screen confidence change is invalid")
    if (
        chromosome_state == policy["chromosome_screen_policy"]["negative_state"]
        and confidence_change
        > policy["chromosome_screen_policy"]["maximum_confidence_change"]
    ):
        raise WorkflowError("negative chromosome screen may not increase confidence")


def verify_human_decision(
    policy: Mapping[str, Any],
    policy_raw: bytes,
    ledger_path: Path,
    human_path: Path,
) -> dict[str, Any]:
    ledger_resolved = _safe_existing_file(ledger_path, "ledger path")
    ledger, ledger_raw = _read_json(ledger_resolved, MAX_LEDGER_BYTES)
    policy_hash = _hash_bytes(policy_raw)
    _validate_ledger(ledger, policy, policy_hash)
    human_resolved = _safe_existing_file(human_path, "human decision receipt path")
    human, human_raw = _read_json(human_resolved, MAX_HUMAN_RECEIPT_BYTES)
    _exact_keys(human, HUMAN_DECISION_KEYS, "human decision receipt")
    if human["schema"] != policy["human_gate"]["decision_receipt_schema"]:
        raise WorkflowError("human decision receipt schema is invalid")
    if human["status"] != "HUMAN_DECISION_RECORDED":
        raise WorkflowError("human decision receipt status is invalid")
    if human["decision"] not in policy["human_gate"]["allowed_decisions"]:
        raise WorkflowError("human decision is not allowed")
    decided = _parse_utc(human["decided_at_utc"], "human decision timestamp")
    cutoff = _parse_utc(ledger["scientific_cutoff_at_utc"], "ledger cutoff")
    if decided < cutoff or decided > _utc_now():
        raise WorkflowError("human decision timestamp is out of order")
    decided_by = _text(human["decided_by"], "decided_by", 200)
    reference = _text(human["decision_reference"], "decision_reference", 200)
    if not SAFE_PRIVATE_TEXT.fullmatch(decided_by) or not SAFE_PRIVATE_TEXT.fullmatch(reference):
        raise WorkflowError("human decision identity or reference is unsafe")
    if human["policy_sha256"] != policy_hash:
        raise WorkflowError("human decision is bound to the wrong policy")
    ledger_hash = _hash_bytes(ledger_raw)
    if human["ledger_sha256"] != ledger_hash:
        raise WorkflowError("human decision is bound to the wrong ledger")
    if human["scientific_cutoff_at_utc"] != ledger["scientific_cutoff_at_utc"]:
        raise WorkflowError("human decision cutoff binding is invalid")
    return {
        "decision": human["decision"],
        "human_decision_receipt_sha256": _hash_bytes(human_raw),
        "ledger_sha256": ledger_hash,
        "operation": "verify",
        "policy_sha256": policy_hash,
        "result_schema": RESULT_SCHEMA,
        "status": "passed",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify a human-gated reconciliation provenance ledger."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--policy", required=True, type=Path)
    build.add_argument("--receipt-manifest", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--json", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--policy", required=True, type=Path)
    verify.add_argument("--ledger", required=True, type=Path)
    verify.add_argument("--human-decision-receipt", required=True, type=Path)
    verify.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy, policy_raw = load_and_validate_policy(args.policy)
        if args.command == "build":
            result, _ = build_ledger(
                policy, policy_raw, args.receipt_manifest, args.output
            )
        else:
            result = verify_human_decision(
                policy, policy_raw, args.ledger, args.human_decision_receipt
            )
    except (WorkflowError, OSError, ValueError):
        print("secure_wgs_reconciliation_status=failed_closed", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "secure_wgs_reconciliation_status=passed "
            f"operation={result['operation']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
