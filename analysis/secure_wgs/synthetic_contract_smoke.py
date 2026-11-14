#!/usr/bin/env python3
"""Validate the public secure-WGS workflow contract with synthetic role markers.

This module is intentionally standard-library only.  It validates orchestration
and repository entrypoints; it never reads biological or case-specific data.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_SCHEMA = "secure-wgs-public-workflow-contract/v1"
RESULT_SCHEMA = "secure-wgs-synthetic-smoke-result/v1"
MAX_CONTRACT_BYTES = 512 * 1024
REPO_ROOT = Path(__file__).resolve().parents[2]

TOP_LEVEL_KEYS = {
    "schema",
    "contract_id",
    "source_roles",
    "terminal_roles",
    "stages",
}
STAGE_KEYS = {
    "order",
    "stage_id",
    "purpose",
    "input_roles",
    "output_roles",
    "execution_class",
    "tool_container_version_evidence",
    "public_entrypoint",
    "public_entrypoint_reason",
    "validation_contract",
    "fail_closed_conditions",
    "scalability_notes",
    "evidence_receipt_role",
}
TOOL_EVIDENCE_KEYS = {"tool", "version", "container", "evidence"}
EXECUTION_CLASSES = {
    "public-local",
    "public-entrypoint-protected-inputs",
    "public-entrypoint-external-credentials",
    "containerized-heavyweight-protected",
    "documentation-only-external",
    "public-analyzer-heavyweight-inputs",
    "human-gated-protected",
    "public-external-verifier",
}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# These patterns reject values, not harmless schema field names.  They are
# deliberately conservative because the contract is a public artifact.
UNSAFE_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(?:https?|s3|gs|ssh)://"),
    re.compile(r"(?i)(?:^|\s)[a-z]:[\\/]"),
    re.compile(r"(?:^|\s)\\\\[^\s]+"),
    re.compile(r"(?:^|\s)/(?!/)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._${}-]+)+"),
    re.compile(r"(?i)\b(?:hf_[a-z0-9]{12,}|akia[0-9a-z]{12,}|bearer\s+[a-z0-9._~-]{8,})\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b(?:chr)?(?:[0-9]{1,2}|X|Y|M|MT):[0-9][0-9,]*(?:[-:][0-9][0-9,]*)?\b"),
    re.compile(r"\b[ACGTN]+>[ACGTN]+\b", re.IGNORECASE),
    re.compile(r"\b(?:NM|NR|ENST)_?[0-9]+(?:\.[0-9]+)?\b", re.IGNORECASE),
    re.compile(r"(?i)\b(?:sample|proband|patient)[_-]?[0-9]+\b"),
    re.compile(
        r"(?i)\b(?:host|address|endpoint|instance)\s*[:=]?\s*(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    ),
)


class ContractError(ValueError):
    """Raised when the public workflow contract must fail closed."""


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def load_contract(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load a bounded JSON object and reject duplicate keys."""

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ContractError("contract is unavailable") from exc
    if size <= 0 or size > MAX_CONTRACT_BYTES:
        raise ContractError("contract size is invalid")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError("contract cannot be read") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("contract must be UTF-8") from exc
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except ContractError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ContractError("contract JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ContractError("contract root must be an object")
    return value, raw


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ContractError(f"{label} fields are invalid")


def _require_text(value: Any, label: str, *, max_length: int = 1000) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ContractError(f"{label} must be nonempty trimmed text")
    if len(value) > max_length or any(ord(char) < 32 for char in value):
        raise ContractError(f"{label} text is invalid")
    return value


def _require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, max_length=64)
    if not IDENTIFIER.fullmatch(text):
        raise ContractError(f"{label} identifier is invalid")
    return text


def _require_unique_identifiers(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{label} must be a nonempty list")
    result = [_require_identifier(item, f"{label} item") for item in value]
    if len(set(result)) != len(result):
        raise ContractError(f"{label} contains duplicates")
    return result


def _require_text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{label} must be a nonempty list")
    return [_require_text(item, f"{label} item") for item in value]


def _walk_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_text(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_text(item)


def _validate_public_text(contract: Mapping[str, Any]) -> None:
    for text in _walk_text(contract):
        if any(pattern.search(text) for pattern in UNSAFE_TEXT_PATTERNS):
            raise ContractError("contract contains privacy-unsafe text")


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_public_entrypoint(entrypoint: str, repo_root: Path = REPO_ROOT) -> Path:
    """Resolve a POSIX repository-relative entrypoint without following escape paths."""

    text = _require_text(entrypoint, "public_entrypoint", max_length=240)
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ContractError("public entrypoint path is unsafe")
    if "\\" in text or not pure.parts:
        raise ContractError("public entrypoint must use a repository-relative POSIX path")
    root = repo_root.resolve(strict=True)
    candidate = root.joinpath(*pure.parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ContractError("public entrypoint does not resolve") from exc
    if not _is_within(resolved, root) or not resolved.is_file():
        raise ContractError("public entrypoint is outside the repository or is not a file")
    return resolved


def validate_contract(contract: Mapping[str, Any], repo_root: Path = REPO_ROOT) -> None:
    """Validate structure, ordering, graph connectivity, privacy, and entrypoints."""

    if not isinstance(contract, dict):
        raise ContractError("contract must be an object")
    _require_exact_keys(contract, TOP_LEVEL_KEYS, "contract")
    if contract["schema"] != CONTRACT_SCHEMA:
        raise ContractError("contract schema is invalid")
    _require_identifier(contract["contract_id"], "contract_id")
    sources = _require_unique_identifiers(contract["source_roles"], "source_roles")
    terminals = _require_unique_identifiers(contract["terminal_roles"], "terminal_roles")
    if set(sources) & set(terminals):
        raise ContractError("source and terminal roles must be distinct")

    stages = contract["stages"]
    if not isinstance(stages, list) or not stages:
        raise ContractError("stages must be a nonempty list")

    available = set(sources)
    produced: set[str] = set()
    stage_ids: set[str] = set()
    public_count = 0
    documentation_only_count = 0
    for expected_order, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            raise ContractError("stage must be an object")
        _require_exact_keys(stage, STAGE_KEYS, "stage")
        if type(stage["order"]) is not int or stage["order"] != expected_order:
            raise ContractError("stage order must be consecutive and stable")
        stage_id = _require_identifier(stage["stage_id"], "stage_id")
        if stage_id in stage_ids:
            raise ContractError("stage_id must be unique")
        stage_ids.add(stage_id)
        _require_text(stage["purpose"], "purpose")
        input_roles = _require_unique_identifiers(stage["input_roles"], "input_roles")
        output_roles = _require_unique_identifiers(stage["output_roles"], "output_roles")
        if set(input_roles) - available:
            raise ContractError("stage consumes an unavailable role")
        if set(output_roles) & (available | produced):
            raise ContractError("stage output role is not unique")
        execution_class = _require_text(
            stage["execution_class"], "execution_class", max_length=64
        )
        if execution_class not in EXECUTION_CLASSES:
            raise ContractError("execution_class is invalid")

        tool_evidence = stage["tool_container_version_evidence"]
        if not isinstance(tool_evidence, list) or not tool_evidence:
            raise ContractError("tool evidence must be a nonempty list")
        for record in tool_evidence:
            if not isinstance(record, dict):
                raise ContractError("tool evidence record must be an object")
            _require_exact_keys(record, TOOL_EVIDENCE_KEYS, "tool evidence")
            for key in sorted(TOOL_EVIDENCE_KEYS):
                _require_text(record[key], f"tool evidence {key}")

        entrypoint = stage["public_entrypoint"]
        reason = stage["public_entrypoint_reason"]
        if entrypoint is None:
            _require_text(reason, "public_entrypoint_reason")
            documentation_only_count += 1
        else:
            if reason is not None:
                raise ContractError("public entrypoint reason must be null when runnable")
            resolve_public_entrypoint(entrypoint, repo_root)
            public_count += 1

        _require_text_list(stage["validation_contract"], "validation_contract")
        _require_text_list(stage["fail_closed_conditions"], "fail_closed_conditions")
        _require_text(stage["scalability_notes"], "scalability_notes")
        receipt = _require_identifier(
            stage["evidence_receipt_role"], "evidence_receipt_role"
        )
        if receipt not in output_roles or not receipt.endswith("_receipt"):
            raise ContractError("evidence receipt role must be a receipt output")

        produced.update(output_roles)
        available.update(output_roles)

    if not set(terminals).issubset(produced):
        raise ContractError("terminal roles must be produced by the workflow")
    if public_count == 0 or documentation_only_count == 0:
        raise ContractError("contract must distinguish runnable and documentation-only stages")
    _validate_public_text(contract)


def _graph_payload(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_roles": contract["source_roles"],
        "terminal_roles": contract["terminal_roles"],
        "stages": [
            {
                "order": stage["order"],
                "stage_id": stage["stage_id"],
                "input_roles": stage["input_roles"],
                "output_roles": stage["output_roles"],
                "execution_class": stage["execution_class"],
                "public_entrypoint": stage["public_entrypoint"],
            }
            for stage in contract["stages"]
        ],
    }


def build_synthetic_role_graph(contract: Mapping[str, Any]) -> dict[str, int | str]:
    """Materialize deterministic, non-biological role markers in a temporary directory."""

    with tempfile.TemporaryDirectory(prefix="secure-wgs-contract-") as temp_name:
        temp_root = Path(temp_name)
        roles_root = temp_root / "roles"
        roles_root.mkdir(mode=0o700)
        materialized: set[str] = set()

        for role in contract["source_roles"]:
            marker = roles_root / f"{role}.json"
            marker.write_text(
                json.dumps(
                    {"kind": "synthetic_source_role", "role": role},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            materialized.add(role)

        for stage in contract["stages"]:
            if any(role not in materialized for role in stage["input_roles"]):
                raise ContractError("synthetic graph is disconnected")
            for role in stage["output_roles"]:
                marker = roles_root / f"{role}.json"
                if marker.exists():
                    raise ContractError("synthetic role collision")
                marker.write_text(
                    json.dumps(
                        {
                            "kind": "synthetic_output_role",
                            "role": role,
                            "stage_id": stage["stage_id"],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n",
                    encoding="utf-8",
                )
                materialized.add(role)

        if any(role not in materialized for role in contract["terminal_roles"]):
            raise ContractError("synthetic terminal role is unavailable")

        marker_count = len(list(roles_root.glob("*.json")))

    canonical_graph = json.dumps(
        _graph_payload(contract), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "graph_sha256": hashlib.sha256(canonical_graph).hexdigest(),
        "materialized_role_count": marker_count,
    }


def run_negative_self_test(contract: Mapping[str, Any], repo_root: Path = REPO_ROOT) -> None:
    """Prove that an unavailable role mutation is rejected."""

    mutated = copy.deepcopy(contract)
    mutated["stages"][1]["input_roles"].append("unavailable_synthetic_role")
    try:
        validate_contract(mutated, repo_root)
    except ContractError:
        return
    raise ContractError("negative self-test did not fail closed")


def build_result(
    contract: Mapping[str, Any],
    raw_contract: bytes,
    *,
    self_test: bool,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    validate_contract(contract, repo_root)
    graph_result = build_synthetic_role_graph(contract)
    if self_test:
        run_negative_self_test(contract, repo_root)
    stages = contract["stages"]
    return {
        "contract_sha256": hashlib.sha256(raw_contract).hexdigest(),
        "contract_schema": contract["schema"],
        "documentation_only_stage_count": sum(
            stage["public_entrypoint"] is None for stage in stages
        ),
        "graph_sha256": graph_result["graph_sha256"],
        "materialized_role_count": graph_result["materialized_role_count"],
        "negative_self_test": "passed" if self_test else "not_requested",
        "public_entrypoint_count": sum(
            stage["public_entrypoint"] is not None for stage in stages
        ),
        "result_schema": RESULT_SCHEMA,
        "source_role_count": len(contract["source_roles"]),
        "stage_count": len(stages),
        "status": "passed",
        "terminal_role_count": len(contract["terminal_roles"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the public secure-WGS contract using synthetic roles only."
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="emit deterministic aggregate JSON")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also prove that a disconnected-role mutation fails closed",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract, raw = load_contract(args.contract)
        result = build_result(contract, raw, self_test=args.self_test)
    except (ContractError, OSError, ValueError):
        print("secure_wgs_contract_status=failed_closed", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "secure_wgs_contract_status=passed "
            f"stages={result['stage_count']} "
            f"public_entrypoints={result['public_entrypoint_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
