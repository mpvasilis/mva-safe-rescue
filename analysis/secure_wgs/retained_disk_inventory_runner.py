#!/usr/bin/env python3
"""Owner-gated, inventory-only retained-disk runner.

The default ``check`` command validates contracts without opening an authorized
source or creating output.  The explicit ``run`` command inventories only file
identity, size, and SHA-256.  It contains no provider, network, scientific,
heavy-workflow, prioritization, release, or lifecycle implementation.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from analysis.secure_wgs import retained_disk_inventory_preflight as gate


PLAN_SCHEMA = "secure-wgs-retained-disk-inventory-plan/v1"
INPUT_SCOPE_SCHEMA = "secure-wgs-retained-disk-exact-input-scope/v1"
INPUT_SCOPE_APPROVAL_SCHEMA = "secure-wgs-retained-disk-input-scope-approval/v1"
BILLING_RATE_SCHEMA = "secure-wgs-vast-billing-rate-receipt/v1"
SOURCE_IDENTITY_RECEIPT_SCHEMA = (
    "secure-wgs-retained-disk-private-source-identity-receipt/v1"
)
RECORD_EVIDENCE_SCHEMA = "secure-wgs-retained-disk-record-evidence/v1"
RUN_RESULT_SCHEMA = "secure-wgs-retained-disk-inventory-run-result/v1"

PLAN_ID = "vast-retained-disk-inventory-preflight-v1"
EXECUTION_MODE = "OWNER_GATED_EXPLICIT_INVENTORY_ONLY"
IMPLEMENTATION_RELATIVE_PATH = "analysis/secure_wgs/retained_disk_inventory_runner.py"
PLAN_RELATIVE_PATH = "analysis/secure_wgs/retained_disk_inventory_plan.v1.json"
EXPLICIT_RUN_ACKNOWLEDGEMENT = "RUN_SIGNED_READ_ONLY_INVENTORY_PREFLIGHT"
INPUT_ACTIONS = {"INVENTORY", "EXPLICITLY_EXCLUDE"}
MAX_SCOPE_BYTES = 16 * 1024 * 1024
MAX_SCOPE_APPROVAL_BYTES = 256 * 1024
MAX_BILLING_BYTES = 128 * 1024
MAX_SOURCE_BYTES = 16 * 1024**4
MAX_RATE_MICRO_USD_PER_HOUR = 1_000_000_000
READ_CHUNK_BYTES = 1024 * 1024
SOURCE_IDENTITY_POLICY = gate.SOURCE_IDENTITY_POLICY

FORBIDDEN_ACTIONS = [
    "NETWORK_EGRESS",
    "INSTANCE_START",
    "INSTANCE_STOP",
    "INSTANCE_DESTROY",
    "STORAGE_DESTROY",
    "SCIENTIFIC_ANALYSIS",
    "VEP_EXECUTION",
    "XTEA_EXECUTION",
    "BREADTH_EXECUTION",
    "PRIORITIZATION",
    "STRUCTURAL_INTEGRATION",
    "CANDIDATE_CHANGE",
    "PUBLICATION",
    "RELEASE",
    "UPLOAD",
]

PLAN_KEYS = {
    "schema_version",
    "plan_id",
    "execution_mode",
    "implementation",
    "authorization_schema",
    "private_contract_schemas",
    "permitted_lifecycle_action",
    "input_contract",
    "output_contract",
    "runtime_contract",
    "forbidden_actions",
}
IMPLEMENTATION_KEYS = {"relative_path", "sha256"}
PRIVATE_SCHEMA_KEYS = {"input_scope", "input_scope_approval", "billing_rate"}
INPUT_CONTRACT_KEYS = {
    "source_type",
    "path_policy",
    "access_policy",
    "identity_policy",
}
OUTPUT_CONTRACT_KEYS = {
    "namespace_policy",
    "source_manifest_schema",
    "inventory_receipt_schema",
    "generic_record_id_policy",
    "checkpoint_policy",
}
RUNTIME_CONTRACT_KEYS = {
    "read_chunk_bytes",
    "watchdog_source",
    "runtime_limit_source",
    "cost_limit_source",
    "billing_rate_source",
    "production_platform",
}
INPUT_SCOPE_KEYS = {
    "schema_version",
    "scope_id",
    "created_at_utc",
    "root_path",
    "record_count",
    "records",
}
INPUT_RECORD_KEYS = {
    "ordinal",
    "relative_path",
    "expected_type",
    "expected_size_bytes",
    "expected_sha256",
    "requested_action",
}
SCOPE_APPROVAL_KEYS = {
    "schema_version",
    "status",
    "approved_action",
    "input_scope_manifest_sha256",
    "billing_rate_receipt_sha256",
    "record_count",
    "approved_at_utc",
    "approved_by",
}
BILLING_KEYS = {
    "schema_version",
    "status",
    "host_binding_receipt_sha256",
    "rate_usd_per_hour_micros",
    "observed_at_utc",
    "valid_until_utc",
}
SOURCE_IDENTITY_KEYS = {
    "schema_version",
    "record_id",
    "identity_policy",
    "input_scope_manifest_sha256",
    "scope_record_sha256",
    "expected_type",
    "expected_size_bytes",
    "expected_sha256",
    "requested_action",
}
EVIDENCE_KEYS = {
    "schema_version",
    "record_id",
    "source_identity_sha256",
    "disposition",
    "reason_code",
    "observed_size_bytes",
    "observed_sha256",
    "expected_identity_matched",
}

SCOPE_ID_PATTERN = re.compile(r"^scope-[a-z0-9][a-z0-9-]{7,63}$")

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / PLAN_RELATIVE_PATH


class InventoryRunnerError(RuntimeError):
    """Raised when execution must fail closed before or during inventory."""


class WatchdogLimitReached(InventoryRunnerError):
    pass


class SourceUnsupported(InventoryRunnerError):
    pass


class SourceFailed(InventoryRunnerError):
    pass


@dataclass(frozen=True)
class ScopeRecord:
    ordinal: int
    relative_path: str
    expected_size_bytes: int
    expected_sha256: str
    requested_action: str
    raw_contract: Mapping[str, Any]

    @property
    def record_id(self) -> str:
        return f"input-{self.ordinal:06d}"


@dataclass(frozen=True)
class ValidatedContracts:
    authorization: Mapping[str, Any]
    authorization_terms_sha256: str
    signature_receipt: Mapping[str, Any]
    signature_receipt_payload: bytes
    plan: Mapping[str, Any]
    plan_payload: bytes
    scope: Mapping[str, Any]
    scope_payload: bytes
    scope_root: Path
    scope_records: tuple[ScopeRecord, ...]
    scope_approval: Mapping[str, Any]
    billing: Mapping[str, Any]
    billing_payload: bytes
    expected_host_binding_sha256: str
    output_parent: Path


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise InventoryRunnerError(f"{label} fields are invalid")
    return value


def _text(value: Any, label: str, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise InventoryRunnerError(f"{label} must be nonempty trimmed text")
    return value


def _sha256(value: Any, label: str) -> str:
    try:
        return gate._sha256(value, label)
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(str(exc)) from exc


def _strict_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise InventoryRunnerError(f"{label} is outside its integer bounds")
    return value


def _utc(value: Any, label: str) -> datetime:
    try:
        return gate._strict_utc(value, label)
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(str(exc)) from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return gate.canonical_json_bytes(value) + b"\n"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _outside_repo(path: Path, label: str) -> None:
    try:
        path.resolve(strict=True).relative_to(REPO_ROOT)
    except ValueError:
        return
    except OSError as exc:
        raise InventoryRunnerError(f"{label} is unavailable") from exc
    raise InventoryRunnerError(f"{label} must remain outside the public repository")


def _read_private_json(path: Path, maximum: int, label: str) -> tuple[dict[str, Any], bytes]:
    _outside_repo(path, label)
    try:
        return gate.read_regular_json(path, maximum, label)
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(str(exc)) from exc


def validate_plan(plan: Mapping[str, Any], plan_payload: bytes) -> str:
    root = _exact_keys(plan, PLAN_KEYS, "inventory plan")
    if (
        root["schema_version"] != PLAN_SCHEMA
        or root["plan_id"] != PLAN_ID
        or root["execution_mode"] != EXECUTION_MODE
        or root["authorization_schema"] != gate.AUTHORIZATION_SCHEMA
        or root["permitted_lifecycle_action"] != gate.PERMITTED_ACTION
    ):
        raise InventoryRunnerError("inventory plan identity or action is invalid")
    implementation = _exact_keys(root["implementation"], IMPLEMENTATION_KEYS, "implementation")
    if implementation["relative_path"] != IMPLEMENTATION_RELATIVE_PATH:
        raise InventoryRunnerError("inventory plan implementation path is invalid")
    implementation_hash = _sha256(implementation["sha256"], "implementation.sha256")
    if implementation_hash != _hash_file(Path(__file__).resolve(strict=True)):
        raise InventoryRunnerError("inventory runner bytes do not match the plan")
    schemas = _exact_keys(
        root["private_contract_schemas"], PRIVATE_SCHEMA_KEYS, "private_contract_schemas"
    )
    if schemas != {
        "input_scope": INPUT_SCOPE_SCHEMA,
        "input_scope_approval": INPUT_SCOPE_APPROVAL_SCHEMA,
        "billing_rate": BILLING_RATE_SCHEMA,
    }:
        raise InventoryRunnerError("inventory plan private schemas changed")
    input_contract = _exact_keys(root["input_contract"], INPUT_CONTRACT_KEYS, "input_contract")
    if input_contract != {
        "source_type": "REGULAR_FILE_ONLY",
        "path_policy": "ONE_PRIVATE_ABSOLUTE_ROOT_PLUS_STRICT_RELATIVE_PATHS",
        "access_policy": "IDENTITY_SIZE_AND_SHA256_ONLY",
        "identity_policy": SOURCE_IDENTITY_POLICY,
    }:
        raise InventoryRunnerError("inventory plan input contract changed")
    output_contract = _exact_keys(
        root["output_contract"], OUTPUT_CONTRACT_KEYS, "output_contract"
    )
    if output_contract != {
        "namespace_policy": gate.NAMESPACE_MODE,
        "source_manifest_schema": gate.SOURCE_MANIFEST_SCHEMA,
        "inventory_receipt_schema": gate.INVENTORY_RECEIPT_SCHEMA,
        "generic_record_id_policy": gate.RECORD_ID_POLICY,
        "checkpoint_policy": "FULL_EXPLICIT_NO_OVERWRITE_RECEIPT_AFTER_INITIALIZATION_AND_EACH_RECORD",
    }:
        raise InventoryRunnerError("inventory plan output contract changed")
    runtime = _exact_keys(root["runtime_contract"], RUNTIME_CONTRACT_KEYS, "runtime_contract")
    if runtime != {
        "read_chunk_bytes": READ_CHUNK_BYTES,
        "watchdog_source": "SIGNED_OWNER_VALIDITY_RUNTIME_AND_COST_CAPS",
        "runtime_limit_source": "OWNER_AUTHORIZATION_MAX_RUNTIME_SECONDS",
        "cost_limit_source": "OWNER_AUTHORIZATION_MAX_COST_USD_CENTS",
        "billing_rate_source": "OWNER_BOUND_PRIVATE_BILLING_RATE_RECEIPT",
        "production_platform": "LINUX_DESCRIPTOR_NOFOLLOW",
    }:
        raise InventoryRunnerError("inventory plan runtime contract changed")
    if root["forbidden_actions"] != FORBIDDEN_ACTIONS:
        raise InventoryRunnerError("inventory plan forbidden-action list changed")
    return gate.sha256_bytes(plan_payload)


def load_plan(path: Path) -> tuple[dict[str, Any], bytes, str]:
    if path.resolve(strict=True) != PLAN_PATH.resolve(strict=True):
        raise InventoryRunnerError("only the repository-pinned inventory plan is accepted")
    try:
        plan, payload = gate.read_regular_json(path, gate.MAX_AUTHORIZATION_BYTES, "inventory plan")
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(str(exc)) from exc
    return plan, payload, validate_plan(plan, payload)


def _validate_relative_path(value: Any, label: str) -> tuple[str, ...]:
    text = _text(value, label, 1024)
    if "\\" in text or ":" in text or text.startswith("/") or "//" in text:
        raise InventoryRunnerError(f"{label} is not a strict portable relative path")
    pure = PurePosixPath(text)
    parts = pure.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InventoryRunnerError(f"{label} contains path traversal")
    for part in parts:
        if len(part) > 127 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part):
            raise InventoryRunnerError(f"{label} contains a nonportable component")
    return parts


def _is_reparse(metadata: os.stat_result) -> bool:
    reparse_bit = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_bit
    )


def _reject_link_chain(path: Path) -> None:
    current = path.absolute()
    while True:
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise InventoryRunnerError("declared directory ancestry is unavailable") from exc
        if _is_reparse(metadata):
            raise InventoryRunnerError("directory ancestry contains a link or reparse point")
        parent = current.parent
        if parent == current:
            return
        current = parent


def validate_input_scope(value: Mapping[str, Any]) -> tuple[Path, tuple[ScopeRecord, ...]]:
    scope = _exact_keys(value, INPUT_SCOPE_KEYS, "input scope")
    if scope["schema_version"] != INPUT_SCOPE_SCHEMA:
        raise InventoryRunnerError("input scope schema is invalid")
    scope_id = _text(scope["scope_id"], "scope_id", 70)
    if not SCOPE_ID_PATTERN.fullmatch(scope_id):
        raise InventoryRunnerError("input scope_id is not generic")
    _utc(scope["created_at_utc"], "input scope created_at_utc")
    root_text = _text(scope["root_path"], "input scope root_path", 2048)
    root = Path(root_text)
    if not root.is_absolute() or any(part == ".." for part in root.parts):
        raise InventoryRunnerError("input scope root must be an absolute traversal-free path")
    _outside_repo(root, "input scope root")
    _reject_link_chain(root)
    try:
        root_metadata = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise InventoryRunnerError("input scope root is unavailable") from exc
    if not stat.S_ISDIR(root_metadata.st_mode) or _is_reparse(root_metadata):
        raise InventoryRunnerError("input scope root must be a real directory")
    count = _strict_int(scope["record_count"], "input scope record_count", 1, gate.MAX_SOURCE_RECORDS)
    records = scope["records"]
    if not isinstance(records, list) or len(records) != count:
        raise InventoryRunnerError("input scope record cardinality is invalid")
    normalized: list[ScopeRecord] = []
    seen_paths: set[str] = set()
    for expected_ordinal, raw in enumerate(records, start=1):
        record = _exact_keys(raw, INPUT_RECORD_KEYS, f"input scope records[{expected_ordinal - 1}]")
        ordinal = _strict_int(record["ordinal"], "input record ordinal", 1, count)
        if ordinal != expected_ordinal:
            raise InventoryRunnerError("input scope ordinals must be exact and sequential")
        parts = _validate_relative_path(record["relative_path"], "input record relative_path")
        relative_path = "/".join(parts)
        if relative_path in seen_paths:
            raise InventoryRunnerError("input scope contains a duplicate relative path")
        seen_paths.add(relative_path)
        if record["expected_type"] != "REGULAR_FILE":
            raise InventoryRunnerError("input scope expected_type must be REGULAR_FILE")
        expected_size = _strict_int(
            record["expected_size_bytes"], "input record expected_size_bytes", 0, MAX_SOURCE_BYTES
        )
        expected_hash = _sha256(record["expected_sha256"], "input record expected_sha256")
        action = record["requested_action"]
        if action not in INPUT_ACTIONS:
            raise InventoryRunnerError("input record requested_action is invalid")
        normalized.append(
            ScopeRecord(
                ordinal=ordinal,
                relative_path=relative_path,
                expected_size_bytes=expected_size,
                expected_sha256=expected_hash,
                requested_action=action,
                raw_contract=record,
            )
        )
    return root.resolve(strict=True), tuple(normalized)


def validate_billing_receipt(
    value: Mapping[str, Any],
    *,
    expected_host_binding_sha256: str,
    authorization: Mapping[str, Any],
    now: datetime,
) -> int:
    receipt = _exact_keys(value, BILLING_KEYS, "billing rate receipt")
    if receipt["schema_version"] != BILLING_RATE_SCHEMA or receipt["status"] != "OWNER_REVIEWED_CURRENT":
        raise InventoryRunnerError("billing rate receipt status is invalid")
    if receipt["host_binding_receipt_sha256"] != expected_host_binding_sha256:
        raise InventoryRunnerError("billing rate receipt host binding is invalid")
    rate = _strict_int(
        receipt["rate_usd_per_hour_micros"],
        "rate_usd_per_hour_micros",
        1,
        MAX_RATE_MICRO_USD_PER_HOUR,
    )
    observed = _utc(receipt["observed_at_utc"], "billing observed_at_utc")
    valid_until = _utc(receipt["valid_until_utc"], "billing valid_until_utc")
    auth_expires = _utc(authorization["validity"]["expires_at_utc"], "authorization expires_at_utc")
    if not observed <= now < valid_until or valid_until < auth_expires:
        raise InventoryRunnerError("billing rate receipt is stale for the authorization window")
    return rate


def validate_scope_approval(
    value: Mapping[str, Any],
    payload: bytes,
    *,
    authorization: Mapping[str, Any],
    scope_payload: bytes,
    billing_payload: bytes,
    record_count: int,
) -> None:
    approval = _exact_keys(value, SCOPE_APPROVAL_KEYS, "input scope approval")
    if (
        approval["schema_version"] != INPUT_SCOPE_APPROVAL_SCHEMA
        or approval["status"] != "APPROVED"
        or approval["approved_action"] != gate.PERMITTED_ACTION
    ):
        raise InventoryRunnerError("input scope approval status or action is invalid")
    if gate.sha256_bytes(payload) != authorization["protected_data_scope"][
        "approved_input_scope_receipt_sha256"
    ]:
        raise InventoryRunnerError("input scope approval is not owner-authorization-bound")
    if approval["input_scope_manifest_sha256"] != gate.sha256_bytes(scope_payload):
        raise InventoryRunnerError("input scope approval manifest hash mismatch")
    if approval["billing_rate_receipt_sha256"] != gate.sha256_bytes(billing_payload):
        raise InventoryRunnerError("input scope approval billing hash mismatch")
    approved_count = _strict_int(
        approval["record_count"], "input scope approval record_count", 1, gate.MAX_SOURCE_RECORDS
    )
    if approved_count != record_count:
        raise InventoryRunnerError("input scope approval record count mismatch")
    approved_at = _utc(approval["approved_at_utc"], "input scope approved_at_utc")
    signed_at = _utc(authorization["owner_signature"]["signed_at_utc"], "owner signed_at_utc")
    if approved_at > signed_at:
        raise InventoryRunnerError("input scope approval occurred after owner signature")
    _text(approval["approved_by"], "input scope approved_by", 160)


def validate_contracts(
    *,
    plan: Mapping[str, Any],
    plan_payload: bytes,
    authorization: Mapping[str, Any],
    signature_receipt: Mapping[str, Any],
    signature_receipt_payload: bytes,
    input_scope: Mapping[str, Any],
    input_scope_payload: bytes,
    input_scope_approval: Mapping[str, Any],
    input_scope_approval_payload: bytes,
    billing_receipt: Mapping[str, Any],
    billing_receipt_payload: bytes,
    expected_host_binding_sha256: str,
    output_parent: Path,
    now: datetime | None = None,
) -> ValidatedContracts:
    moment = now or _utc_now()
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise InventoryRunnerError("contract validation time must be timezone-aware UTC")
    plan_hash = validate_plan(plan, plan_payload)
    try:
        terms_hash = gate.require_effective_authorization(
            authorization,
            signature_receipt,
            signature_receipt_payload,
            expected_host_binding_sha256=expected_host_binding_sha256,
            expected_output_namespace=authorization["output_policy"]["new_output_namespace"],
            now=moment,
        )
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(str(exc)) from exc
    if authorization["execution_binding"]["preflight_plan_sha256"] != plan_hash:
        raise InventoryRunnerError("owner authorization is bound to a different plan")
    scope_root, scope_records = validate_input_scope(input_scope)
    validate_scope_approval(
        input_scope_approval,
        input_scope_approval_payload,
        authorization=authorization,
        scope_payload=input_scope_payload,
        billing_payload=billing_receipt_payload,
        record_count=len(scope_records),
    )
    validate_billing_receipt(
        billing_receipt,
        expected_host_binding_sha256=expected_host_binding_sha256,
        authorization=authorization,
        now=moment,
    )
    if not output_parent.is_absolute():
        raise InventoryRunnerError("output parent must be absolute")
    _outside_repo(output_parent, "output parent")
    _reject_link_chain(output_parent)
    try:
        output_metadata = os.stat(output_parent, follow_symlinks=False)
    except OSError as exc:
        raise InventoryRunnerError("output parent is unavailable") from exc
    if not stat.S_ISDIR(output_metadata.st_mode) or _is_reparse(output_metadata):
        raise InventoryRunnerError("output parent must be a real directory")
    namespace = authorization["output_policy"]["new_output_namespace"]
    destination = output_parent / namespace
    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise InventoryRunnerError("output namespace cannot be inspected") from exc
    else:
        raise InventoryRunnerError("authorized output namespace already exists")
    return ValidatedContracts(
        authorization=authorization,
        authorization_terms_sha256=terms_hash,
        signature_receipt=signature_receipt,
        signature_receipt_payload=signature_receipt_payload,
        plan=plan,
        plan_payload=plan_payload,
        scope=input_scope,
        scope_payload=input_scope_payload,
        scope_root=scope_root,
        scope_records=scope_records,
        scope_approval=input_scope_approval,
        billing=billing_receipt,
        billing_payload=billing_receipt_payload,
        expected_host_binding_sha256=expected_host_binding_sha256,
        output_parent=output_parent.resolve(strict=True),
    )


class Watchdog:
    def __init__(
        self,
        authorization: Mapping[str, Any],
        rate_usd_per_hour_micros: int,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.authorization = authorization
        self.rate = rate_usd_per_hour_micros
        self.monotonic = monotonic
        self.utc_now = utc_now
        self.started_monotonic = monotonic()
        self.max_runtime = authorization["limits"]["max_runtime_seconds"]
        self.max_cost = authorization["limits"]["max_cost_usd_cents"]
        self.expires = _utc(authorization["validity"]["expires_at_utc"], "expires_at_utc")

    def elapsed_ceiling_seconds(self) -> int:
        return max(0, math.ceil(self.monotonic() - self.started_monotonic))

    def cost_upper_bound_cents(self) -> int:
        seconds = max(1, self.elapsed_ceiling_seconds() + 1)
        return math.ceil(seconds * self.rate / (3600 * 10_000))

    def check(self) -> None:
        if self.utc_now() >= self.expires:
            raise WatchdogLimitReached("authorization expiry reached")
        if self.elapsed_ceiling_seconds() >= self.max_runtime:
            raise WatchdogLimitReached("runtime cap reached")
        if self.cost_upper_bound_cents() > self.max_cost:
            raise WatchdogLimitReached("cost cap reached")


class OutputWriter:
    """Write only new, generic files under one newly created namespace."""

    def __init__(self, parent: Path, namespace: str, *, production: bool) -> None:
        self.parent = parent
        self.namespace = namespace
        self.root = parent / namespace
        self.production = production
        self._known_directories: set[str] = set()
        if production and not (os.name == "posix" and sys.platform.startswith("linux")):
            raise InventoryRunnerError("production inventory requires Linux descriptor semantics")
        try:
            os.mkdir(self.root, 0o700)
        except FileExistsError as exc:
            raise InventoryRunnerError("authorized output namespace already exists") from exc
        except OSError as exc:
            raise InventoryRunnerError("new output namespace cannot be created") from exc
        _reject_link_chain(self.root)
        metadata = os.stat(self.root, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
            raise InventoryRunnerError("new output namespace identity is invalid")
        self._identity = (metadata.st_dev, metadata.st_ino)

    def _revalidate(self) -> None:
        _reject_link_chain(self.root)
        metadata = os.stat(self.root, follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != self._identity or not stat.S_ISDIR(metadata.st_mode):
            raise InventoryRunnerError("output namespace identity changed")

    def ensure_directory(self, relative: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", relative):
            raise InventoryRunnerError("output directory name is invalid")
        self._revalidate()
        path = self.root / relative
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            metadata = os.stat(path, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
                raise InventoryRunnerError("output subdirectory identity is invalid")
        except OSError as exc:
            raise InventoryRunnerError("output subdirectory cannot be created") from exc
        self._known_directories.add(relative)

    def write_new(self, relative: str, payload: bytes) -> None:
        pure = PurePosixPath(relative)
        parts = pure.parts
        if (
            not parts
            or len(parts) > 2
            or any(part in {"", ".", ".."} for part in parts)
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", part) for part in parts)
        ):
            raise InventoryRunnerError("output relative path is invalid")
        if len(parts) == 2 and parts[0] not in self._known_directories:
            raise InventoryRunnerError("output directory was not created by this run")
        self._revalidate()
        path = self.root.joinpath(*parts)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise InventoryRunnerError("refusing to overwrite an output artifact") from exc
        except OSError as exc:
            raise InventoryRunnerError("output artifact cannot be created") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise InventoryRunnerError("output artifact is not a regular file")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise InventoryRunnerError("output artifact write failed")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class SourceReader:
    def __init__(self, root: Path, *, production: bool) -> None:
        self.root = root
        self.production = production
        if production and not (os.name == "posix" and sys.platform.startswith("linux")):
            raise InventoryRunnerError("production inventory requires Linux descriptor semantics")
        self.root_fd = -1
        if production:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            self.root_fd = os.open(root, flags)
            metadata = os.fstat(self.root_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(self.root_fd)
                self.root_fd = -1
                raise InventoryRunnerError("input root descriptor is not a directory")

    def close(self) -> None:
        if self.root_fd >= 0:
            os.close(self.root_fd)
            self.root_fd = -1

    def _open_production(self, parts: tuple[str, ...]) -> int:
        current = os.dup(self.root_fd)
        try:
            for part in parts[:-1]:
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
                next_fd = os.open(part, flags, dir_fd=current)
                os.close(current)
                current = next_fd
                if not stat.S_ISDIR(os.fstat(current).st_mode):
                    raise SourceUnsupported("source ancestry is not a directory")
            flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
            return os.open(parts[-1], flags, dir_fd=current)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise SourceUnsupported("source link or type is unsupported") from exc
            raise SourceFailed("source is unavailable") from exc
        finally:
            os.close(current)

    def _open_test(self, parts: tuple[str, ...]) -> int:
        path = self.root.joinpath(*parts)
        try:
            _reject_link_chain(path)
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            return os.open(resolved, flags)
        except ValueError as exc:
            raise SourceUnsupported("source escaped the approved root") from exc
        except InventoryRunnerError as exc:
            raise SourceUnsupported("source link or reparse point is unsupported") from exc
        except OSError as exc:
            raise SourceFailed("source is unavailable") from exc

    def inspect(self, record: ScopeRecord, watchdog: Watchdog) -> tuple[int, str]:
        parts = _validate_relative_path(record.relative_path, "runtime relative path")
        descriptor = self._open_production(parts) if self.production else self._open_test(parts)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise SourceUnsupported("source is not a regular file")
            if before.st_size > MAX_SOURCE_BYTES:
                raise SourceFailed("source exceeds the inventory size bound")
            digest = hashlib.sha256()
            observed = 0
            while True:
                watchdog.check()
                chunk = os.read(descriptor, READ_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
                observed += len(chunk)
            after = os.fstat(descriptor)
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
            )
            if after_identity != before_identity or observed != before.st_size:
                raise SourceFailed("source changed during inventory")
            return observed, digest.hexdigest()
        finally:
            os.close(descriptor)


def _identity_receipt(record: ScopeRecord, scope_hash: str) -> tuple[dict[str, Any], bytes, str]:
    value = {
        "schema_version": SOURCE_IDENTITY_RECEIPT_SCHEMA,
        "record_id": record.record_id,
        "identity_policy": SOURCE_IDENTITY_POLICY,
        "input_scope_manifest_sha256": scope_hash,
        "scope_record_sha256": gate.sha256_bytes(gate.canonical_json_bytes(record.raw_contract)),
        "expected_type": "REGULAR_FILE",
        "expected_size_bytes": record.expected_size_bytes,
        "expected_sha256": record.expected_sha256,
        "requested_action": record.requested_action,
    }
    _exact_keys(value, SOURCE_IDENTITY_KEYS, "source identity receipt")
    payload = _json_bytes(value)
    return value, payload, gate.sha256_bytes(payload)


def _evidence_receipt(
    *,
    record_id: str,
    source_identity_sha256: str,
    disposition: str,
    reason_code: str,
    observed_size_bytes: int | None,
    observed_sha256: str | None,
    expected_identity_matched: bool,
) -> tuple[dict[str, Any], bytes, str]:
    value = {
        "schema_version": RECORD_EVIDENCE_SCHEMA,
        "record_id": record_id,
        "source_identity_sha256": source_identity_sha256,
        "disposition": disposition,
        "reason_code": reason_code,
        "observed_size_bytes": observed_size_bytes,
        "observed_sha256": observed_sha256,
        "expected_identity_matched": expected_identity_matched,
    }
    _exact_keys(value, EVIDENCE_KEYS, "record evidence")
    payload = _json_bytes(value)
    return value, payload, gate.sha256_bytes(payload)


def _receipt(
    *,
    context: ValidatedContracts,
    source_manifest_payload: bytes,
    records: Sequence[Mapping[str, Any]],
    started_at: datetime,
    completed_at: datetime,
    cost_upper_bound_cents: int,
) -> tuple[dict[str, Any], bytes]:
    counts = {key: 0 for key in gate.DISPOSITION_COUNT_KEYS}
    for record in records:
        counts[gate.DISPOSITION_TO_COUNT_KEY[record["disposition"]]] += 1
    value = {
        "schema_version": gate.INVENTORY_RECEIPT_SCHEMA,
        "status": (
            "ALL_INPUTS_ACCOUNTED_WITH_FAILURES" if counts["failed"] else "ALL_INPUTS_ACCOUNTED"
        ),
        "authorization_terms_sha256": context.authorization_terms_sha256,
        "source_manifest_sha256": gate.sha256_bytes(source_manifest_payload),
        "output_namespace": context.authorization["output_policy"]["new_output_namespace"],
        "started_at_utc": _utc_text(started_at),
        "completed_at_utc": _utc_text(completed_at),
        "elapsed_runtime_seconds": int((completed_at - started_at).total_seconds()),
        "provider_cost_upper_bound_usd_cents": cost_upper_bound_cents,
        "source_count": len(records),
        "disposition_counts": counts,
        "records": list(records),
        "next_step_state": gate.NEXT_STEP_STATE,
        "downstream_authorizations": dict(
            context.authorization["downstream_authorizations"]
        ),
    }
    return value, _json_bytes(value)


def execute_inventory(
    context: ValidatedContracts,
    *,
    production: bool = True,
    utc_now: Callable[[], datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Execute only the signed identity/size/SHA inventory contract."""

    started_at = utc_now()
    rate = validate_billing_receipt(
        context.billing,
        expected_host_binding_sha256=context.expected_host_binding_sha256,
        authorization=context.authorization,
        now=started_at,
    )
    watchdog = Watchdog(
        context.authorization,
        rate,
        monotonic=monotonic,
        utc_now=utc_now,
    )
    watchdog.check()
    namespace = context.authorization["output_policy"]["new_output_namespace"]
    writer = OutputWriter(context.output_parent, namespace, production=production)
    writer.ensure_directory("source-identities")
    writer.ensure_directory("record-evidence")
    scope_hash = gate.sha256_bytes(context.scope_payload)

    source_records: list[dict[str, str]] = []
    identities: dict[str, str] = {}
    for record in context.scope_records:
        _, identity_payload, identity_hash = _identity_receipt(record, scope_hash)
        writer.write_new(f"source-identities/{record.record_id}.json", identity_payload)
        identities[record.record_id] = identity_hash
        source_records.append(
            {"record_id": record.record_id, "source_identity_sha256": identity_hash}
        )
    enumerated_at = utc_now()
    source_manifest = {
        "schema_version": gate.SOURCE_MANIFEST_SCHEMA,
        "authorization_terms_sha256": context.authorization_terms_sha256,
        "approved_input_scope_receipt_sha256": context.authorization[
            "protected_data_scope"
        ]["approved_input_scope_receipt_sha256"],
        "output_namespace": namespace,
        "enumerated_at_utc": _utc_text(enumerated_at),
        "source_count": len(source_records),
        "records": source_records,
    }
    source_manifest_payload = _json_bytes(source_manifest)
    writer.write_new("source_manifest.json", source_manifest_payload)

    result_records: list[dict[str, Any]] = []
    for record in context.scope_records:
        _, evidence_payload, evidence_hash = _evidence_receipt(
            record_id=record.record_id,
            source_identity_sha256=identities[record.record_id],
            disposition="FAILED",
            reason_code="NOT_YET_PROCESSED",
            observed_size_bytes=None,
            observed_sha256=None,
            expected_identity_matched=False,
        )
        writer.write_new(f"record-evidence/{record.record_id}.initial.json", evidence_payload)
        result_records.append(
            {
                "record_id": record.record_id,
                "source_identity_sha256": identities[record.record_id],
                "disposition": "FAILED",
                "output_state": "EXPLICIT_DISPOSITION",
                "reason_code": "NOT_YET_PROCESSED",
                "evidence_sha256": evidence_hash,
            }
        )
    checkpoint, checkpoint_payload = _receipt(
        context=context,
        source_manifest_payload=source_manifest_payload,
        records=result_records,
        started_at=started_at,
        completed_at=utc_now(),
        cost_upper_bound_cents=watchdog.cost_upper_bound_cents(),
    )
    del checkpoint
    writer.write_new("inventory_receipt.checkpoint.000000.json", checkpoint_payload)

    reader = SourceReader(context.scope_root, production=production)
    watchdog_stopped = False
    try:
        for index, record in enumerate(context.scope_records):
            if watchdog_stopped:
                break
            disposition = "FAILED"
            output_state = "EXPLICIT_DISPOSITION"
            reason_code = "SOURCE_UNAVAILABLE_OR_UNREADABLE"
            observed_size: int | None = None
            observed_sha: str | None = None
            matched = False
            try:
                watchdog.check()
                if record.requested_action == "EXPLICITLY_EXCLUDE":
                    disposition = "EXPLICITLY_EXCLUDED"
                    reason_code = "OWNER_SCOPE_EXCLUSION"
                else:
                    observed_size, observed_sha = reader.inspect(record, watchdog)
                    matched = (
                        observed_size == record.expected_size_bytes
                        and observed_sha == record.expected_sha256
                    )
                    if matched:
                        disposition = "INVENTORIED"
                        output_state = "EXPLICIT_OUTPUT"
                        reason_code = "IDENTITY_SIZE_SHA256_MATCH"
                    else:
                        reason_code = "EXPECTED_IDENTITY_MISMATCH"
            except WatchdogLimitReached:
                reason_code = "WATCHDOG_LIMIT_REACHED"
                watchdog_stopped = True
            except SourceUnsupported:
                disposition = "UNSUPPORTED"
                reason_code = "SOURCE_LINK_REPARSE_OR_TYPE_UNSUPPORTED"
            except (SourceFailed, OSError):
                reason_code = "SOURCE_UNAVAILABLE_CHANGED_OR_UNREADABLE"
            _, evidence_payload, evidence_hash = _evidence_receipt(
                record_id=record.record_id,
                source_identity_sha256=identities[record.record_id],
                disposition=disposition,
                reason_code=reason_code,
                observed_size_bytes=observed_size,
                observed_sha256=observed_sha,
                expected_identity_matched=matched,
            )
            writer.write_new(f"record-evidence/{record.record_id}.final.json", evidence_payload)
            result_records[index] = {
                "record_id": record.record_id,
                "source_identity_sha256": identities[record.record_id],
                "disposition": disposition,
                "output_state": output_state,
                "reason_code": reason_code,
                "evidence_sha256": evidence_hash,
            }
            completed = utc_now()
            checkpoint, checkpoint_payload = _receipt(
                context=context,
                source_manifest_payload=source_manifest_payload,
                records=result_records,
                started_at=started_at,
                completed_at=completed,
                cost_upper_bound_cents=watchdog.cost_upper_bound_cents(),
            )
            del checkpoint
            writer.write_new(
                f"inventory_receipt.checkpoint.{index + 1:06d}.json",
                checkpoint_payload,
            )
    finally:
        reader.close()

    completed_at = utc_now()
    final_receipt, final_payload = _receipt(
        context=context,
        source_manifest_payload=source_manifest_payload,
        records=result_records,
        started_at=started_at,
        completed_at=completed_at,
        cost_upper_bound_cents=watchdog.cost_upper_bound_cents(),
    )
    writer.write_new("inventory_receipt.json", final_payload)
    try:
        validation_result = gate.validate_inventory_receipt(
            final_receipt,
            receipt_payload=final_payload,
            source_manifest=source_manifest,
            source_manifest_payload=source_manifest_payload,
            authorization=context.authorization,
            signature_receipt=context.signature_receipt,
            signature_receipt_payload=context.signature_receipt_payload,
            expected_host_binding_sha256=context.expected_host_binding_sha256,
            expected_output_namespace=namespace,
        )
    except gate.PreflightContractError as exc:
        raise InventoryRunnerError(f"self-validation rejected final receipt: {exc}") from exc
    counts = validation_result["disposition_counts"]
    return {
        "schema_version": RUN_RESULT_SCHEMA,
        "status": (
            "INVENTORY_ACCOUNTED"
            if counts["failed"] == 0 and counts["unsupported"] == 0
            else "INVENTORY_ACCOUNTED_FAIL_CLOSED"
        ),
        "source_count": validation_result["source_count"],
        "disposition_counts": counts,
        "all_inputs_accounted": True,
        "followup_authorized": False,
        "lifecycle_action_performed": False,
        "network_egress_performed": False,
        "scientific_analysis_performed": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_check = subparsers.add_parser("plan-check", help="validate only the public plan and runner binding")
    plan_check.add_argument("--plan", type=Path, default=PLAN_PATH)
    plan_check.add_argument("--json", action="store_true")
    for name in ("check", "run"):
        command = subparsers.add_parser(
            name,
            help=(
                "validate all private contracts without opening sources or creating output"
                if name == "check"
                else "run only the explicitly signed identity/size/SHA inventory"
            ),
        )
        command.add_argument("--plan", type=Path, default=PLAN_PATH)
        command.add_argument("--authorization", required=True, type=Path)
        command.add_argument("--signature-verification-receipt", required=True, type=Path)
        command.add_argument("--input-scope", required=True, type=Path)
        command.add_argument("--input-scope-approval", required=True, type=Path)
        command.add_argument("--billing-rate-receipt", required=True, type=Path)
        command.add_argument("--expected-host-binding-sha256", required=True)
        command.add_argument("--output-parent", required=True, type=Path)
        if name == "run":
            command.add_argument("--execute-inventory", required=True)
        command.add_argument("--json", action="store_true")
    return parser


def _load_contract_context(args: argparse.Namespace) -> ValidatedContracts:
    plan, plan_payload, _ = load_plan(args.plan)
    authorization, _ = _read_private_json(
        args.authorization, gate.MAX_AUTHORIZATION_BYTES, "authorization"
    )
    signature, signature_payload = _read_private_json(
        args.signature_verification_receipt,
        gate.MAX_SIGNATURE_RECEIPT_BYTES,
        "signature verification receipt",
    )
    scope, scope_payload = _read_private_json(args.input_scope, MAX_SCOPE_BYTES, "input scope")
    approval, approval_payload = _read_private_json(
        args.input_scope_approval, MAX_SCOPE_APPROVAL_BYTES, "input scope approval"
    )
    billing, billing_payload = _read_private_json(
        args.billing_rate_receipt, MAX_BILLING_BYTES, "billing rate receipt"
    )
    return validate_contracts(
        plan=plan,
        plan_payload=plan_payload,
        authorization=authorization,
        signature_receipt=signature,
        signature_receipt_payload=signature_payload,
        input_scope=scope,
        input_scope_payload=scope_payload,
        input_scope_approval=approval,
        input_scope_approval_payload=approval_payload,
        billing_receipt=billing,
        billing_receipt_payload=billing_payload,
        expected_host_binding_sha256=args.expected_host_binding_sha256,
        output_parent=args.output_parent,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "plan-check":
            _, _, plan_hash = load_plan(args.plan)
            result = {
                "schema_version": RUN_RESULT_SCHEMA,
                "status": "PLAN_VALID",
                "plan_sha256": plan_hash,
                "authorization_effective": False,
                "execution_performed": False,
            }
        else:
            context = _load_contract_context(args)
            if args.command == "check":
                result = {
                    "schema_version": RUN_RESULT_SCHEMA,
                    "status": "CONTRACTS_VALID_NO_EXECUTION",
                    "authorization_effective": True,
                    "source_count": len(context.scope_records),
                    "source_files_opened": False,
                    "output_created": False,
                    "followup_authorized": False,
                }
            else:
                if args.execute_inventory != EXPLICIT_RUN_ACKNOWLEDGEMENT:
                    raise InventoryRunnerError("explicit inventory acknowledgement is invalid")
                result = execute_inventory(context, production=True)
    except (InventoryRunnerError, gate.PreflightContractError) as exc:
        print(f"retained-disk inventory rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")) if args.json else result["status"])
    return 0 if result["status"] not in {"INVENTORY_ACCOUNTED_FAIL_CLOSED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
