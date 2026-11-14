#!/usr/bin/env python3
"""Validate, plan, or execute the public complementary-WGS role contract.

The executor is deliberately ignorant of biological meaning.  It validates
generic role manifests, expands separately approved argv arrays, verifies exact
tool versions and digests, and writes private provenance receipts.  It performs
no downloads, interpretation, scoring, or release action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from analysis.secure_wgs.public import COMPLEMENTARY_WORKFLOW_SCHEMA


INPUT_MANIFEST_SCHEMA = "secure-wgs-role-manifest/v1"
ASSET_MANIFEST_SCHEMA = "secure-wgs-asset-manifest/v1"
PARAMETER_SCHEMA = "secure-wgs-approved-parameters/v1"
APPROVAL_SCHEMA = "secure-wgs-execution-approval/v1"
LANE_RECEIPT_SCHEMA = "secure-wgs-lane-receipt/v1"
WORKFLOW_RECEIPT_SCHEMA = "secure-wgs-complementary-workflow-receipt/v1"
OPERATION_RESULT_SCHEMA = "secure-wgs-complementary-operation-result/v1"

REPO_ROOT = _BOOTSTRAP_ROOT
MAX_CONFIG_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PARAMETER_BYTES = 256 * 1024
MAX_APPROVAL_BYTES = 128 * 1024
MAX_TOOL_SECONDS = 7 * 24 * 60 * 60

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
PLACEHOLDER = re.compile(
    r"^\{(asset|input|output|runtime|approved_probe|approved_run):([a-z][a-z0-9_]{2,95})\}$"
)
FORBIDDEN_SHELL_CHARS = re.compile(r"[&|;<>`$]")
UNSAFE_PUBLIC_TEXT = (
    re.compile(r"(?i)\b(?:https?|s3|gs|ssh)://"),
    re.compile(r"(?i)(?:^|\s)[a-z]:[\\/]"),
    re.compile(r"(?:^|\s)\\\\[^\s]+"),
    re.compile(r"(?:^|\s)/(?!/)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._${}-]+)+"),
    re.compile(r"(?i)\b(?:hf_[a-z0-9]{12,}|akia[0-9a-z]{12,}|bearer\s+[a-z0-9._~-]{8,})\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|password)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(
        r"\b(?:chr)?(?:[0-9]{1,2}|X|Y|M|MT):[0-9][0-9,]*(?:[-:][0-9][0-9,]*)?\b"
    ),
    re.compile(r"\b[ACGTN]+>[ACGTN]+\b", re.IGNORECASE),
    re.compile(r"\b(?:NM|NR|ENST)_?[0-9]+(?:\.[0-9]+)?\b", re.IGNORECASE),
    re.compile(r"(?i)\b(?:sample|proband|patient)[_-]?[0-9]+\b"),
)

CONFIG_KEYS = {
    "schema",
    "workflow_id",
    "source_roles",
    "terminal_roles",
    "tool_contracts",
    "asset_contracts",
    "lanes",
}
TOOL_KEYS = {
    "tool_id",
    "display_name",
    "version",
    "executable_asset_role",
    "probe_parameter_role",
    "version_probe",
    "version_match",
}
ASSET_CONTRACT_KEYS = {"role", "kind", "version", "licence_required"}
LANE_KEYS = {
    "order",
    "lane_id",
    "purpose",
    "depends_on",
    "tool_id",
    "method_version",
    "evidence_state",
    "input_roles",
    "output_roles",
    "asset_roles",
    "parameter_role",
    "argv_template",
    "receipt_role",
    "resource_class",
    "parallelization_class",
    "limitations",
    "fail_closed_conditions",
}
INPUT_MANIFEST_KEYS = {"schema", "roles"}
INPUT_ROLE_KEYS = {"role", "path", "sha256"}
ASSET_MANIFEST_KEYS = {"schema", "assets"}
ASSET_ENTRY_KEYS = {"role", "path", "sha256", "version", "licence_acknowledged"}
PARAMETER_KEYS = {
    "schema",
    "lane_id",
    "tool_id",
    "version_probe_arguments",
    "run_arguments",
}
APPROVAL_KEYS = {
    "schema",
    "status",
    "purpose",
    "approved_at_utc",
    "expires_at_utc",
    "approved_by",
    "config_sha256",
    "input_manifest_sha256",
    "asset_manifest_sha256",
}
LANE_RECEIPT_KEYS = {
    "schema",
    "status",
    "receipt_role",
    "lane_id",
    "method_id",
    "method_version",
    "scientific_evidence_at_utc",
    "started_at_utc",
    "completed_at_utc",
    "config_sha256",
    "input_contract_sha256",
    "asset_contract_sha256",
    "input_digests",
    "asset_digests",
    "output_digests",
    "lineage_sha256",
}
EVIDENCE_STATES = {
    "COMPLETE_RESEARCH_ONLY",
    "SENSITIVITY_ONLY",
    "REVIEW_ARTIFACT_ONLY",
}
ASSET_KINDS = {"executable", "file"}


class WorkflowError(RuntimeError):
    """Raised when the public workflow must fail closed."""


def _duplicate_guard(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise WorkflowError(f"non-standard JSON constant is forbidden: {value}")


def _read_json(path: Path, maximum: int) -> tuple[dict[str, Any], bytes]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise WorkflowError("JSON input is unavailable") from exc
    if size <= 0 or size > maximum:
        raise WorkflowError("JSON input size is invalid")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkflowError("JSON input cannot be read as UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_json_constant,
        )
    except WorkflowError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise WorkflowError("JSON input is invalid") from exc
    if not isinstance(value, dict):
        raise WorkflowError("JSON root must be an object")
    return value, raw


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise WorkflowError(f"{label} fields are invalid")


def _text(value: Any, label: str, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise WorkflowError(f"{label} must be trimmed nonempty text")
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise WorkflowError(f"{label} text is invalid")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _text(value, label, 96)
    if not IDENTIFIER.fullmatch(text):
        raise WorkflowError(f"{label} is invalid")
    return text


def _sha256_text(value: Any, label: str) -> str:
    text = _text(value, label, 64)
    if not SHA256_PATTERN.fullmatch(text):
        raise WorkflowError(f"{label} must be a lowercase SHA-256")
    return text


def _text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WorkflowError(f"{label} must be a nonempty list")
    return [_text(item, f"{label} item") for item in value]


def _identifier_list(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise WorkflowError(f"{label} must be a list")
    items = [_identifier(item, f"{label} item") for item in value]
    if len(items) != len(set(items)):
        raise WorkflowError(f"{label} contains duplicates")
    return items


def _walk_text(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk_text(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_text(item)


def _privacy_check(value: Mapping[str, Any]) -> None:
    for text in _walk_text(value):
        if any(pattern.search(text) for pattern in UNSAFE_PUBLIC_TEXT):
            raise WorkflowError("configuration contains privacy-unsafe text")


def _parse_utc(value: Any, label: str) -> datetime:
    text = _text(value, label, 20)
    if not UTC_PATTERN.fullmatch(text):
        raise WorkflowError(f"{label} must be strict UTC ending Z")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise WorkflowError(f"{label} is malformed") from exc
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _hash_bytes(raw)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_reparse(file_status: Any) -> bool:
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(getattr(file_status, "st_mode", 0)) or bool(
        getattr(file_status, "st_file_attributes", 0) & reparse_attribute
    )


def _reject_symlink_chain(path: Path) -> None:
    current = path
    while True:
        try:
            file_status = os.lstat(current)
        except OSError as exc:
            raise WorkflowError("declared path is unavailable") from exc
        if _is_reparse(file_status):
            raise WorkflowError("symlinks and reparse points are forbidden")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _safe_existing_file(value: Any, label: str, *, outside_repo: bool = True) -> Path:
    text = _text(str(value) if isinstance(value, Path) else value, label, 1024)
    if FORBIDDEN_SHELL_CHARS.search(text):
        raise WorkflowError("declared path contains an unsafe character")
    path = Path(text)
    if not path.is_absolute():
        raise WorkflowError("declared runtime path must be absolute")
    _reject_symlink_chain(path)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise WorkflowError("declared file does not resolve") from exc
    if not resolved.is_file():
        raise WorkflowError("declared path must be a regular file")
    if outside_repo and _is_within(resolved, REPO_ROOT.resolve(strict=True)):
        raise WorkflowError("runtime material must remain outside the repository")
    return resolved


def _safe_new_private_root(value: Path) -> Path:
    if not value.is_absolute():
        raise WorkflowError("receipt root must be absolute")
    text = str(value)
    if FORBIDDEN_SHELL_CHARS.search(text):
        raise WorkflowError("receipt root contains an unsafe character")
    root = value.resolve(strict=False)
    repo = REPO_ROOT.resolve(strict=True)
    if _is_within(root, repo) or root == repo:
        raise WorkflowError("receipt root must remain outside the repository")
    if root.exists() or root.is_symlink():
        raise WorkflowError("receipt root must not already exist")
    parent = root.parent
    _reject_symlink_chain(parent)
    if not parent.resolve(strict=True).is_dir():
        raise WorkflowError("receipt root parent is invalid")
    return root


def _atomic_no_overwrite(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise WorkflowError("refusing to overwrite an existing artifact")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".staged-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise WorkflowError("refusing to overwrite an existing artifact") from exc
        except OSError as exc:
            raise WorkflowError("atomic no-overwrite write failed") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _argument_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WorkflowError(f"{label} must be a nonempty argv array")
    result: list[str] = []
    for item in value:
        text = _text(item, f"{label} item", 1000)
        if FORBIDDEN_SHELL_CHARS.search(text):
            raise WorkflowError("argv contains a shell metacharacter")
        result.append(text)
    return result


def load_and_validate_config(path: Path) -> tuple[dict[str, Any], bytes]:
    config, raw = _read_json(path, MAX_CONFIG_BYTES)
    validate_config(config)
    return config, raw


def validate_config(config: Mapping[str, Any]) -> None:
    if not isinstance(config, dict):
        raise WorkflowError("configuration must be an object")
    _exact_keys(config, CONFIG_KEYS, "configuration")
    if config["schema"] != COMPLEMENTARY_WORKFLOW_SCHEMA:
        raise WorkflowError("configuration schema is invalid")
    _identifier(config["workflow_id"], "workflow_id")
    source_roles = _identifier_list(config["source_roles"], "source_roles")
    terminal_roles = _identifier_list(config["terminal_roles"], "terminal_roles")
    if set(source_roles) & set(terminal_roles):
        raise WorkflowError("source and terminal roles overlap")

    tool_contracts = config["tool_contracts"]
    if not isinstance(tool_contracts, list) or not tool_contracts:
        raise WorkflowError("tool_contracts must be a nonempty list")
    tools: dict[str, Mapping[str, Any]] = {}
    for tool in tool_contracts:
        if not isinstance(tool, dict):
            raise WorkflowError("tool contract must be an object")
        _exact_keys(tool, TOOL_KEYS, "tool contract")
        tool_id = _identifier(tool["tool_id"], "tool_id")
        if tool_id in tools:
            raise WorkflowError("tool_id is duplicated")
        _text(tool["display_name"], "display_name", 120)
        _text(tool["version"], "tool version", 120)
        executable_role = _identifier(
            tool["executable_asset_role"], "executable_asset_role"
        )
        parameter_role = _identifier(
            tool["probe_parameter_role"], "probe_parameter_role"
        )
        probe = _argument_list(tool["version_probe"], "version_probe")
        if probe != [
            f"{{asset:{executable_role}}}",
            f"{{approved_probe:{parameter_role}}}",
        ]:
            raise WorkflowError("version probe must use the executable and approved probe roles")
        _text(tool["version_match"], "version_match", 160)
        tools[tool_id] = tool

    asset_contracts = config["asset_contracts"]
    if not isinstance(asset_contracts, list) or not asset_contracts:
        raise WorkflowError("asset_contracts must be a nonempty list")
    assets: dict[str, Mapping[str, Any]] = {}
    for asset in asset_contracts:
        if not isinstance(asset, dict):
            raise WorkflowError("asset contract must be an object")
        _exact_keys(asset, ASSET_CONTRACT_KEYS, "asset contract")
        role = _identifier(asset["role"], "asset role")
        if role in assets:
            raise WorkflowError("asset role is duplicated")
        if asset["kind"] not in ASSET_KINDS:
            raise WorkflowError("asset kind is invalid")
        _text(asset["version"], "asset version", 160)
        if asset["licence_required"] is not True:
            raise WorkflowError("every external asset requires licence acknowledgement")
        assets[role] = asset

    for tool in tools.values():
        executable = tool["executable_asset_role"]
        parameter = tool["probe_parameter_role"]
        if executable not in assets or assets[executable]["kind"] != "executable":
            raise WorkflowError("tool executable asset contract is missing")
        if assets[executable]["version"] != tool["version"]:
            raise WorkflowError("tool and executable asset versions disagree")
        if parameter not in assets or assets[parameter]["kind"] != "file":
            raise WorkflowError("tool probe parameter asset contract is missing")

    lanes = config["lanes"]
    if not isinstance(lanes, list) or not lanes:
        raise WorkflowError("lanes must be a nonempty ordered list")
    lane_ids: set[str] = set()
    receipt_roles: set[str] = set()
    produced_by: dict[str, str] = {}
    available = set(source_roles)
    used_tools: set[str] = set()
    used_assets: set[str] = set()
    for expected_order, lane in enumerate(lanes, start=1):
        if not isinstance(lane, dict):
            raise WorkflowError("lane must be an object")
        _exact_keys(lane, LANE_KEYS, "lane")
        if type(lane["order"]) is not int or lane["order"] != expected_order:
            raise WorkflowError("lane order must be consecutive")
        lane_id = _identifier(lane["lane_id"], "lane_id")
        if lane_id in lane_ids:
            raise WorkflowError("lane_id is duplicated")
        _text(lane["purpose"], "lane purpose")
        dependencies = _identifier_list(
            lane["depends_on"], "depends_on", allow_empty=True
        )
        if any(dependency not in lane_ids for dependency in dependencies):
            raise WorkflowError("lane dependency is unavailable or out of order")
        tool_id = _identifier(lane["tool_id"], "lane tool_id")
        if tool_id not in tools:
            raise WorkflowError("lane tool is not declared")
        used_tools.add(tool_id)
        _text(lane["method_version"], "method_version", 200)
        if lane["evidence_state"] not in EVIDENCE_STATES:
            raise WorkflowError("lane evidence_state is invalid")
        input_roles = _identifier_list(lane["input_roles"], "input_roles")
        output_roles = _identifier_list(lane["output_roles"], "output_roles")
        missing = set(input_roles) - available
        if missing:
            raise WorkflowError("lane consumes an unavailable role")
        if set(output_roles) & available:
            raise WorkflowError("lane output role is duplicated")
        required_dependencies = {
            produced_by[role] for role in input_roles if role in produced_by
        }
        if not required_dependencies.issubset(set(dependencies)):
            raise WorkflowError("lane dependency does not cover produced inputs")
        asset_roles = _identifier_list(lane["asset_roles"], "asset_roles")
        if any(role not in assets for role in asset_roles):
            raise WorkflowError("lane asset role is undeclared")
        used_assets.update(asset_roles)
        tool = tools[tool_id]
        if tool["executable_asset_role"] not in asset_roles:
            raise WorkflowError("lane omits its tool executable asset")
        parameter_role = _identifier(lane["parameter_role"], "parameter_role")
        if parameter_role not in asset_roles or assets[parameter_role]["kind"] != "file":
            raise WorkflowError("lane parameter role is invalid")
        template = _argument_list(lane["argv_template"], "argv_template")
        expected_template = [
            f"{{asset:{tool['executable_asset_role']}}}",
            f"{{approved_run:{parameter_role}}}",
        ]
        if template != expected_template:
            raise WorkflowError("lane argv template must use tool and approved parameter roles")
        receipt = _identifier(lane["receipt_role"], "receipt_role")
        if receipt in receipt_roles or receipt in available or receipt in output_roles:
            raise WorkflowError("receipt role is duplicated")
        _identifier(lane["resource_class"], "resource_class")
        _identifier(lane["parallelization_class"], "parallelization_class")
        _text_list(lane["limitations"], "limitations")
        _text_list(lane["fail_closed_conditions"], "fail_closed_conditions")

        lane_ids.add(lane_id)
        receipt_roles.add(receipt)
        for role in output_roles:
            produced_by[role] = lane_id
        available.update(output_roles)

    if not set(terminal_roles).issubset(set(produced_by)):
        raise WorkflowError("every terminal role must be produced")
    if used_tools != set(tools):
        raise WorkflowError("every declared tool must be used")
    if used_assets != set(assets):
        raise WorkflowError("every declared asset must be used")
    _privacy_check(config)


def _load_parameter(path: Path, lane: Mapping[str, Any]) -> dict[str, Any]:
    value, _ = _read_json(path, MAX_PARAMETER_BYTES)
    _exact_keys(value, PARAMETER_KEYS, "approved parameter record")
    if value["schema"] != PARAMETER_SCHEMA:
        raise WorkflowError("approved parameter schema is invalid")
    if value["lane_id"] != lane["lane_id"] or value["tool_id"] != lane["tool_id"]:
        raise WorkflowError("approved parameters are bound to the wrong lane or tool")
    probe = _argument_list(value["version_probe_arguments"], "version_probe_arguments")
    run = _argument_list(value["run_arguments"], "run_arguments")
    for argument in probe + run:
        if any(pattern.search(argument) for pattern in UNSAFE_PUBLIC_TEXT):
            raise WorkflowError("approved argv contains privacy-unsafe text")
    allowed_input = set(lane["input_roles"])
    allowed_output = set(lane["output_roles"])
    allowed_asset = set(lane["asset_roles"])
    has_lane_contract = False
    for argument in probe + run:
        if "{" not in argument and "}" not in argument:
            continue
        match = PLACEHOLDER.fullmatch(argument)
        if not match:
            raise WorkflowError("approved argv contains an invalid placeholder")
        kind, role = match.groups()
        if kind == "input" and role not in allowed_input:
            raise WorkflowError("approved argv references an undeclared input")
        if kind == "output" and role not in allowed_output:
            raise WorkflowError("approved argv references an undeclared output")
        if kind == "asset" and role not in allowed_asset:
            raise WorkflowError("approved argv references an undeclared asset")
        if kind == "runtime":
            if role != "lane_contract":
                raise WorkflowError("approved argv references an invalid runtime role")
            has_lane_contract = True
        if kind in {"approved_probe", "approved_run"}:
            raise WorkflowError("approved argv cannot recursively expand parameters")
    if not has_lane_contract:
        referenced_inputs = {
            PLACEHOLDER.fullmatch(item).group(2)
            for item in run
            if PLACEHOLDER.fullmatch(item)
            and PLACEHOLDER.fullmatch(item).group(1) == "input"
        }
        referenced_outputs = {
            PLACEHOLDER.fullmatch(item).group(2)
            for item in run
            if PLACEHOLDER.fullmatch(item)
            and PLACEHOLDER.fullmatch(item).group(1) == "output"
        }
        if referenced_inputs != allowed_input or referenced_outputs != allowed_output:
            raise WorkflowError("approved argv must reference every input/output or lane contract")
    return value


def _semantic_input_hash(entries: Mapping[str, Mapping[str, Any]]) -> str:
    return _canonical_hash(
        [{"role": role, "sha256": entries[role]["sha256"]} for role in sorted(entries)]
    )


def _semantic_asset_hash(entries: Mapping[str, Mapping[str, Any]]) -> str:
    return _canonical_hash(
        [
            {
                "role": role,
                "sha256": entries[role]["sha256"],
                "version": entries[role]["version"],
                "licence_acknowledged": entries[role]["licence_acknowledged"],
            }
            for role in sorted(entries)
        ]
    )


def load_role_manifests(
    config: Mapping[str, Any], input_path: Path, asset_path: Path
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    bytes,
    bytes,
]:
    input_manifest, input_raw = _read_json(input_path, MAX_MANIFEST_BYTES)
    _exact_keys(input_manifest, INPUT_MANIFEST_KEYS, "input manifest")
    if input_manifest["schema"] != INPUT_MANIFEST_SCHEMA:
        raise WorkflowError("input manifest schema is invalid")
    if not isinstance(input_manifest["roles"], list):
        raise WorkflowError("input roles must be a list")
    inputs: dict[str, dict[str, Any]] = {}
    for entry in input_manifest["roles"]:
        if not isinstance(entry, dict):
            raise WorkflowError("input role entry must be an object")
        _exact_keys(entry, INPUT_ROLE_KEYS, "input role entry")
        role = _identifier(entry["role"], "input role")
        if role in inputs:
            raise WorkflowError("input role is duplicated")
        expected = _sha256_text(entry["sha256"], "input digest")
        resolved = _safe_existing_file(entry["path"], "input path")
        if _hash_file(resolved) != expected:
            raise WorkflowError("input digest mismatch")
        inputs[role] = {**entry, "resolved_path": resolved}
    if set(inputs) != set(config["source_roles"]):
        raise WorkflowError("input manifest roles do not match the workflow contract")

    asset_manifest, asset_raw = _read_json(asset_path, MAX_MANIFEST_BYTES)
    _exact_keys(asset_manifest, ASSET_MANIFEST_KEYS, "asset manifest")
    if asset_manifest["schema"] != ASSET_MANIFEST_SCHEMA:
        raise WorkflowError("asset manifest schema is invalid")
    if not isinstance(asset_manifest["assets"], list):
        raise WorkflowError("assets must be a list")
    contracts = {entry["role"]: entry for entry in config["asset_contracts"]}
    assets: dict[str, dict[str, Any]] = {}
    for entry in asset_manifest["assets"]:
        if not isinstance(entry, dict):
            raise WorkflowError("asset entry must be an object")
        _exact_keys(entry, ASSET_ENTRY_KEYS, "asset entry")
        role = _identifier(entry["role"], "asset role")
        if role in assets or role not in contracts:
            raise WorkflowError("asset role is duplicate or unexpected")
        expected = _sha256_text(entry["sha256"], "asset digest")
        resolved = _safe_existing_file(entry["path"], "asset path")
        if _hash_file(resolved) != expected:
            raise WorkflowError("asset digest mismatch")
        contract = contracts[role]
        if entry["version"] != contract["version"]:
            raise WorkflowError("asset version mismatch")
        if entry["licence_acknowledged"] is not True:
            raise WorkflowError("asset licence has not been acknowledged")
        if contract["kind"] == "executable" and os.name != "nt":
            if not os.access(resolved, os.X_OK):
                raise WorkflowError("tool asset is not executable")
        assets[role] = {**entry, "resolved_path": resolved}
    if set(assets) != set(contracts):
        raise WorkflowError("asset manifest roles do not match the workflow contract")

    parameters: dict[str, dict[str, Any]] = {}
    for lane in config["lanes"]:
        role = lane["parameter_role"]
        parameters[role] = _load_parameter(assets[role]["resolved_path"], lane)
    return inputs, assets, parameters, input_raw, asset_raw


def build_plan(
    config: Mapping[str, Any],
    config_raw: bytes,
    inputs: Mapping[str, Mapping[str, Any]],
    assets: Mapping[str, Mapping[str, Any]],
    *,
    operation: str,
) -> dict[str, Any]:
    return {
        "asset_contract_sha256": _semantic_asset_hash(assets),
        "asset_role_count": len(assets),
        "config_sha256": _hash_bytes(config_raw),
        "input_contract_sha256": _semantic_input_hash(inputs),
        "input_role_count": len(inputs),
        "lane_count": len(config["lanes"]),
        "operation": operation,
        "ordered_plan": [
            {
                "depends_on": lane["depends_on"],
                "evidence_state": lane["evidence_state"],
                "lane_id": lane["lane_id"],
                "method_version": lane["method_version"],
                "order": lane["order"],
                "parallelization_class": lane["parallelization_class"],
                "receipt_role": lane["receipt_role"],
                "resource_class": lane["resource_class"],
                "tool_id": lane["tool_id"],
            }
            for lane in config["lanes"]
        ],
        "result_schema": OPERATION_RESULT_SCHEMA,
        "status": "passed",
        "terminal_role_count": len(config["terminal_roles"]),
        "tool_count": len(config["tool_contracts"]),
    }


def _expand_parameter_arguments(
    arguments: Sequence[str],
    *,
    input_paths: Mapping[str, Path],
    asset_paths: Mapping[str, Path],
    output_paths: Mapping[str, Path],
    lane_contract: Path | None,
) -> list[str]:
    expanded: list[str] = []
    for argument in arguments:
        match = PLACEHOLDER.fullmatch(argument)
        if not match:
            if "{" in argument or "}" in argument:
                raise WorkflowError("argv contains an unresolved placeholder")
            expanded.append(argument)
            continue
        kind, role = match.groups()
        if kind == "input" and role in input_paths:
            expanded.append(str(input_paths[role]))
        elif kind == "asset" and role in asset_paths:
            expanded.append(str(asset_paths[role]))
        elif kind == "output" and role in output_paths:
            expanded.append(str(output_paths[role]))
        elif kind == "runtime" and role == "lane_contract" and lane_contract is not None:
            expanded.append(str(lane_contract))
        else:
            raise WorkflowError("argv placeholder cannot be resolved")
    return expanded


def _expand_template(
    template: Sequence[str],
    *,
    mode: str,
    parameter: Mapping[str, Any],
    input_paths: Mapping[str, Path],
    asset_paths: Mapping[str, Path],
    output_paths: Mapping[str, Path],
    lane_contract: Path | None,
) -> list[str]:
    result: list[str] = []
    for item in template:
        match = PLACEHOLDER.fullmatch(item)
        if not match:
            result.append(item)
            continue
        kind, role = match.groups()
        if kind == "asset":
            result.append(str(asset_paths[role]))
        elif kind == "approved_probe" and mode == "probe":
            result.extend(
                _expand_parameter_arguments(
                    parameter["version_probe_arguments"],
                    input_paths=input_paths,
                    asset_paths=asset_paths,
                    output_paths=output_paths,
                    lane_contract=lane_contract,
                )
            )
        elif kind == "approved_run" and mode == "run":
            result.extend(
                _expand_parameter_arguments(
                    parameter["run_arguments"],
                    input_paths=input_paths,
                    asset_paths=asset_paths,
                    output_paths=output_paths,
                    lane_contract=lane_contract,
                )
            )
        else:
            raise WorkflowError("argv template placeholder cannot be resolved")
    if not result or any(FORBIDDEN_SHELL_CHARS.search(item) for item in result):
        raise WorkflowError("expanded argv is invalid")
    return result


def _safe_environment() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH", "LANG", "LC_ALL")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def _verify_tool_versions(
    config: Mapping[str, Any],
    assets: Mapping[str, Mapping[str, Any]],
    parameters: Mapping[str, Mapping[str, Any]],
) -> None:
    asset_paths = {role: entry["resolved_path"] for role, entry in assets.items()}
    lanes_by_parameter = {lane["parameter_role"]: lane for lane in config["lanes"]}
    for tool in config["tool_contracts"]:
        parameter_role = tool["probe_parameter_role"]
        lane = lanes_by_parameter[parameter_role]
        argv = _expand_template(
            tool["version_probe"],
            mode="probe",
            parameter=parameters[parameter_role],
            input_paths={},
            asset_paths=asset_paths,
            output_paths={},
            lane_contract=None,
        )
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                cwd=assets[tool["executable_asset_role"]]["resolved_path"].parent,
                env=_safe_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkflowError("tool version probe failed") from exc
        combined = completed.stdout + b"\n" + completed.stderr
        try:
            version_text = combined.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise WorkflowError("tool version output is not UTF-8") from exc
        if completed.returncode != 0 or tool["version_match"] not in version_text:
            raise WorkflowError("tool version mismatch")


def _load_approval(
    path: Path,
    *,
    config_hash: str,
    input_hash: str,
    asset_hash: str,
) -> dict[str, Any]:
    resolved = _safe_existing_file(path, "approval record")
    approval, _ = _read_json(resolved, MAX_APPROVAL_BYTES)
    _exact_keys(approval, APPROVAL_KEYS, "approval record")
    if approval["schema"] != APPROVAL_SCHEMA:
        raise WorkflowError("approval schema is invalid")
    if approval["status"] != "APPROVED" or approval["purpose"] != "RESEARCH_ONLY":
        raise WorkflowError("approval status or purpose is invalid")
    approved = _parse_utc(approval["approved_at_utc"], "approved_at_utc")
    expires = _parse_utc(approval["expires_at_utc"], "expires_at_utc")
    now = _utc_now()
    if approved > now or expires <= now or approved >= expires:
        raise WorkflowError("approval is missing, expired, or out of order")
    _text(approval["approved_by"], "approved_by", 160)
    if approval["config_sha256"] != config_hash:
        raise WorkflowError("approval is bound to the wrong configuration")
    if approval["input_manifest_sha256"] != input_hash:
        raise WorkflowError("approval is bound to the wrong input manifest")
    if approval["asset_manifest_sha256"] != asset_hash:
        raise WorkflowError("approval is bound to the wrong asset manifest")
    return approval


def compute_lineage_sha256(receipt: Mapping[str, Any]) -> str:
    payload = {
        "asset_contract_sha256": receipt["asset_contract_sha256"],
        "asset_digests": receipt["asset_digests"],
        "config_sha256": receipt["config_sha256"],
        "input_contract_sha256": receipt["input_contract_sha256"],
        "input_digests": receipt["input_digests"],
        "lane_id": receipt["lane_id"],
        "method_id": receipt["method_id"],
        "method_version": receipt["method_version"],
        "output_digests": receipt["output_digests"],
        "receipt_role": receipt["receipt_role"],
        "scientific_evidence_at_utc": receipt["scientific_evidence_at_utc"],
        "status": receipt["status"],
    }
    return _canonical_hash(payload)


def _ensure_exact_generated_files(root: Path, allowed: set[Path]) -> None:
    _reject_symlink_chain(root)
    actual: set[Path] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        _reject_symlink_chain(directory)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    file_status = entry.stat(follow_symlinks=False)
                    if _is_reparse(file_status):
                        raise WorkflowError(
                            "tool created a symlink or reparse point"
                        )
                    _reject_symlink_chain(path)
                    if stat.S_ISDIR(file_status.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(file_status.st_mode):
                        actual.add(path.resolve(strict=True))
                    else:
                        raise WorkflowError("tool created an unsupported output type")
        except WorkflowError:
            raise
        except OSError as exc:
            raise WorkflowError("generated output tree cannot be inspected") from exc
    expected: set[Path] = set()
    for path in allowed:
        _reject_symlink_chain(path)
        expected.add(path.resolve(strict=True))
    if actual != expected:
        raise WorkflowError("tool created an unexpected output or receipt")


def run_workflow(
    config: Mapping[str, Any],
    config_raw: bytes,
    inputs: Mapping[str, Mapping[str, Any]],
    assets: Mapping[str, Mapping[str, Any]],
    parameters: Mapping[str, Mapping[str, Any]],
    approval_path: Path,
    receipt_root_arg: Path,
    input_raw: bytes,
    asset_raw: bytes,
) -> dict[str, Any]:
    config_hash = _hash_bytes(config_raw)
    input_raw_hash = _hash_bytes(input_raw)
    asset_raw_hash = _hash_bytes(asset_raw)
    _load_approval(
        approval_path,
        config_hash=config_hash,
        input_hash=input_raw_hash,
        asset_hash=asset_raw_hash,
    )
    root = _safe_new_private_root(receipt_root_arg)
    _verify_tool_versions(config, assets, parameters)
    root.mkdir(mode=0o700)
    receipts_root = root / "receipts"
    work_root = root / "work"
    receipts_root.mkdir(mode=0o700)
    work_root.mkdir(mode=0o700)

    input_contract_hash = _semantic_input_hash(inputs)
    asset_contract_hash = _semantic_asset_hash(assets)
    source_paths = {role: entry["resolved_path"] for role, entry in inputs.items()}
    source_digests = {role: entry["sha256"] for role, entry in inputs.items()}
    asset_paths = {role: entry["resolved_path"] for role, entry in assets.items()}
    asset_digests = {role: entry["sha256"] for role, entry in assets.items()}
    produced_paths: dict[str, Path] = {}
    produced_digests: dict[str, str] = {}
    receipt_index: list[dict[str, str]] = []

    for lane in config["lanes"]:
        lane_root = work_root / lane["lane_id"]
        outputs_root = lane_root / "outputs"
        lane_root.mkdir(mode=0o700)
        outputs_root.mkdir(mode=0o700)
        output_paths = {role: outputs_root / role for role in lane["output_roles"]}
        input_paths = {
            role: source_paths.get(role, produced_paths.get(role))
            for role in lane["input_roles"]
        }
        if any(path is None for path in input_paths.values()):
            raise WorkflowError("lane input path is unavailable")
        input_digest_map = {
            role: source_digests.get(role, produced_digests.get(role))
            for role in lane["input_roles"]
        }
        if any(value is None for value in input_digest_map.values()):
            raise WorkflowError("lane input digest is unavailable")

        lane_contract_path = lane_root / "lane_contract.json"
        lane_contract = {
            "asset_paths": {role: str(asset_paths[role]) for role in lane["asset_roles"]},
            "input_paths": {role: str(input_paths[role]) for role in lane["input_roles"]},
            "lane_id": lane["lane_id"],
            "output_paths": {role: str(output_paths[role]) for role in lane["output_roles"]},
            "schema": "secure-wgs-private-lane-runtime/v1",
        }
        _atomic_no_overwrite(lane_contract_path, _json_bytes(lane_contract))
        argv = _expand_template(
            lane["argv_template"],
            mode="run",
            parameter=parameters[lane["parameter_role"]],
            input_paths=input_paths,
            asset_paths=asset_paths,
            output_paths=output_paths,
            lane_contract=lane_contract_path,
        )
        stdout_path = lane_root / "tool.stdout.private"
        stderr_path = lane_root / "tool.stderr.private"
        started = _utc_now()
        try:
            with stdout_path.open("xb") as stdout_handle, stderr_path.open("xb") as stderr_handle:
                completed = subprocess.run(
                    argv,
                    shell=False,
                    cwd=lane_root,
                    env=_safe_environment(),
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    timeout=MAX_TOOL_SECONDS,
                    check=False,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkflowError("tool execution failed") from exc
        if completed.returncode != 0:
            raise WorkflowError("tool execution returned nonzero")
        completed_at = _utc_now()

        allowed_files = {lane_contract_path, stdout_path, stderr_path, *output_paths.values()}
        _ensure_exact_generated_files(lane_root, allowed_files)
        output_digest_map: dict[str, str] = {}
        for role, path in output_paths.items():
            _reject_symlink_chain(path)
            if not path.is_file() or path.stat().st_size <= 0:
                raise WorkflowError("required lane output is missing or empty")
            output_digest_map[role] = _hash_file(path)

        receipt = {
            "asset_contract_sha256": asset_contract_hash,
            "asset_digests": {role: asset_digests[role] for role in sorted(lane["asset_roles"])},
            "completed_at_utc": _utc_text(completed_at),
            "config_sha256": config_hash,
            "input_contract_sha256": input_contract_hash,
            "input_digests": {role: input_digest_map[role] for role in sorted(input_digest_map)},
            "lane_id": lane["lane_id"],
            "lineage_sha256": "0" * 64,
            "method_id": lane["tool_id"],
            "method_version": lane["method_version"],
            "output_digests": {role: output_digest_map[role] for role in sorted(output_digest_map)},
            "receipt_role": lane["receipt_role"],
            "schema": LANE_RECEIPT_SCHEMA,
            "scientific_evidence_at_utc": _utc_text(completed_at),
            "started_at_utc": _utc_text(started),
            "status": lane["evidence_state"],
        }
        _exact_keys(receipt, LANE_RECEIPT_KEYS, "generated lane receipt")
        receipt["lineage_sha256"] = compute_lineage_sha256(receipt)
        receipt_path = receipts_root / f"{lane['receipt_role']}.json"
        receipt_bytes = _json_bytes(receipt)
        _atomic_no_overwrite(receipt_path, receipt_bytes)
        receipt_index.append(
            {
                "receipt_role": lane["receipt_role"],
                "sha256": _hash_bytes(receipt_bytes),
            }
        )
        produced_paths.update(output_paths)
        produced_digests.update(output_digest_map)

    workflow_receipt = {
        "asset_contract_sha256": asset_contract_hash,
        "config_sha256": config_hash,
        "input_contract_sha256": input_contract_hash,
        "lane_count": len(config["lanes"]),
        "receipts": receipt_index,
        "schema": WORKFLOW_RECEIPT_SCHEMA,
        "status": "COMPLETE_RESEARCH_ONLY",
        "terminal_state": "HUMAN_REVIEW_REQUIRED",
    }
    workflow_receipt_path = receipts_root / "workflow_receipt.json"
    workflow_receipt_bytes = _json_bytes(workflow_receipt)
    _atomic_no_overwrite(workflow_receipt_path, workflow_receipt_bytes)
    return {
        "config_sha256": config_hash,
        "lane_count": len(config["lanes"]),
        "operation": "run",
        "receipt_count": len(receipt_index),
        "result_schema": OPERATION_RESULT_SCHEMA,
        "status": "passed",
        "terminal_state": "HUMAN_REVIEW_REQUIRED",
        "workflow_receipt_sha256": _hash_bytes(workflow_receipt_bytes),
    }


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--asset-manifest", required=True, type=Path)
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, plan, or execute the public complementary-WGS role contract."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    _add_common_arguments(validate)
    plan = subparsers.add_parser("plan")
    _add_common_arguments(plan)
    run = subparsers.add_parser("run")
    _add_common_arguments(run)
    run.add_argument("--approval-record", required=True, type=Path)
    run.add_argument("--receipt-root", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config, config_raw = load_and_validate_config(args.config)
        inputs, assets, parameters, input_raw, asset_raw = load_role_manifests(
            config, args.input_manifest, args.asset_manifest
        )
        if args.command in {"validate", "plan"}:
            result = build_plan(
                config,
                config_raw,
                inputs,
                assets,
                operation=args.command,
            )
        else:
            result = run_workflow(
                config,
                config_raw,
                inputs,
                assets,
                parameters,
                args.approval_record,
                args.receipt_root,
                input_raw,
                asset_raw,
            )
    except (WorkflowError, OSError, ValueError):
        print("secure_wgs_complementary_status=failed_closed", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "secure_wgs_complementary_status=passed "
            f"operation={result['operation']} lanes={result['lane_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
