#!/usr/bin/env python3
"""Fail-closed contracts for a retained-disk inventory preflight.

This module is deliberately non-executing.  It does not contact Vast, start or
stop an instance, inspect a protected filesystem, or authorize a downstream
analysis.  It validates (1) a narrowly scoped owner authorization and (2) the
generic, privacy-safe accounting surface of a later inventory receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


AUTHORIZATION_SCHEMA = (
    "secure-wgs-vast-retained-disk-inventory-preflight-owner-authorization/v1"
)
SIGNATURE_RECEIPT_SCHEMA = (
    "secure-wgs-owner-signature-independent-verification-receipt/v1"
)
SOURCE_MANIFEST_SCHEMA = (
    "secure-wgs-retained-disk-inventory-source-manifest/v1"
)
INVENTORY_RECEIPT_SCHEMA = "secure-wgs-retained-disk-inventory-receipt/v1"
VALIDATION_RESULT_SCHEMA = (
    "secure-wgs-retained-disk-inventory-preflight-validation-result/v1"
)

OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"
OWNER_SIGNED = "OWNER_SIGNED"
NOT_SIGNED = "NOT_SIGNED"
OWNER_SIGNED_AND_INDEPENDENTLY_VERIFIED = (
    "OWNER_SIGNED_AND_INDEPENDENTLY_VERIFIED"
)

PERMITTED_ACTION = (
    "START_DESIGNATED_STOPPED_INSTANCE_RUN_READ_ONLY_RETAINED_DISK_"
    "INVENTORY_THEN_APPLY_SIGNED_DISPOSITION"
)
PURPOSE = "RETAINED_DISK_RECOVERY_INVENTORY_PREFLIGHT_ONLY"
OWNER_ATTESTATION = (
    "I authorize exactly this retained-disk inventory preflight and its signed "
    "post-preflight disposition; I authorize no downstream analysis or release."
)

SIGNATURE_METHOD = "OUT_OF_BAND_OWNER_SIGNATURE_INDEPENDENTLY_VERIFIED"
NAMESPACE_MODE = "NEW_ABSENT_NAMESPACE_ONLY"
OUTPUT_CONTENT_POLICY = "GENERIC_METADATA_DIGESTS_AND_DISPOSITIONS_ONLY"
SOURCE_DOMAIN = "EVERY_RECORD_IN_THE_PINNED_PRIVATE_INPUT_SCOPE"
RECORD_ID_POLICY = "SEQUENTIAL_GENERIC_IDS_WITH_NO_SOURCE_IDENTIFIERS"
SOURCE_IDENTITY_POLICY = "NONZERO_SHA256_OF_PINNED_PRIVATE_SOURCE_IDENTITY_RECEIPT"
ACCOUNTING_EQUATION = (
    "source_count = inventoried + explicitly_excluded + unsupported + failed"
)
NEXT_STEP_STATE = "SEPARATE_OWNER_AUTHORIZATION_REQUIRED"

POST_PREFLIGHT_DISPOSITIONS = {
    "STOP_COMPUTE_RETAIN_DISK",
    "DESTROY_INSTANCE_AND_RETAINED_DISK",
}
DISPOSITIONS = (
    "INVENTORIED",
    "EXPLICITLY_EXCLUDED",
    "UNSUPPORTED",
    "FAILED",
)
DISPOSITION_COUNT_KEYS = (
    "inventoried",
    "explicitly_excluded",
    "unsupported",
    "failed",
)
DISPOSITION_TO_COUNT_KEY = dict(zip(DISPOSITIONS, DISPOSITION_COUNT_KEYS))

MAX_AUTHORIZATION_BYTES = 256 * 1024
MAX_SIGNATURE_RECEIPT_BYTES = 128 * 1024
MAX_SOURCE_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_INVENTORY_RECEIPT_BYTES = 64 * 1024 * 1024
MAX_AUTHORIZATION_LIFETIME = timedelta(hours=24)
MAX_RUNTIME_SECONDS = 24 * 60 * 60
MAX_COST_USD_CENTS = 1_000_000
MAX_SOURCE_RECORDS = 1_000_000

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UTC_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
NAMESPACE_PATTERN = re.compile(r"^preflight-[a-z0-9][a-z0-9-]{7,63}$")
RECORD_ID_PATTERN = re.compile(r"^input-[0-9]{6}$")
REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")

AUTHORIZATION_KEYS = {
    "schema_version",
    "authorization_state",
    "purpose",
    "execution_binding",
    "host_binding",
    "protected_data_scope",
    "limits",
    "validity",
    "output_policy",
    "failure_policy",
    "post_preflight_disposition",
    "inventory_obligation",
    "downstream_authorizations",
    "owner_signature",
}
EXECUTION_BINDING_KEYS = {"permitted_lifecycle_action", "preflight_plan_sha256"}
HOST_BINDING_KEYS = {"provider", "binding_type", "binding_receipt_sha256"}
PROTECTED_SCOPE_KEYS = {
    "approved_input_scope_receipt_sha256",
    "existing_file_access",
    "write_existing_paths_authorized",
    "network_egress_authorized",
    "export_protected_content_authorized",
    "scientific_analysis_authorized",
}
LIMIT_KEYS = {"max_runtime_seconds", "max_cost_usd_cents", "one_lifecycle_attempt_only"}
VALIDITY_KEYS = {"issued_at_utc", "not_before_utc", "expires_at_utc"}
OUTPUT_POLICY_KEYS = {
    "namespace_mode",
    "new_output_namespace",
    "overwrite_authorized",
    "content_policy",
}
FAILURE_POLICY_KEYS = {
    "stop_on_any_error",
    "stop_on_unaccounted_input",
    "continue_to_heavy_workflow",
    "partial_output_disposition",
}
POST_PREFLIGHT_KEYS = {"on_success", "on_failure"}
INVENTORY_OBLIGATION_KEYS = {
    "source_domain",
    "record_id_policy",
    "source_identity_policy",
    "allowed_dispositions",
    "explicit_disposition_required",
    "unique_record_id_required",
    "no_silent_drop",
    "accounting_equation",
}
DOWNSTREAM_KEYS = {
    "vep_heavy_execution_authorized",
    "xtea_heavy_execution_authorized",
    "breadth_heavy_execution_authorized",
    "prioritization_authorized",
    "structural_integration_authorized",
    "candidate_change_authorized",
    "publication_authorized",
    "release_authorized",
    "upload_authorized",
    "diagnostic_claim_authorized",
}
OWNER_SIGNATURE_KEYS = {
    "state",
    "signed_by",
    "signed_at_utc",
    "attestation",
    "signature_verification_receipt_sha256",
}
SIGNATURE_RECEIPT_KEYS = {
    "schema_version",
    "status",
    "authorization_terms_sha256",
    "signed_by",
    "signed_at_utc",
    "signature_method",
    "signature_evidence_sha256",
    "verifier_independent",
    "verified_by",
    "verified_at_utc",
}
SOURCE_MANIFEST_KEYS = {
    "schema_version",
    "authorization_terms_sha256",
    "approved_input_scope_receipt_sha256",
    "output_namespace",
    "enumerated_at_utc",
    "source_count",
    "records",
}
SOURCE_RECORD_KEYS = {"record_id", "source_identity_sha256"}
INVENTORY_RECEIPT_KEYS = {
    "schema_version",
    "status",
    "authorization_terms_sha256",
    "source_manifest_sha256",
    "output_namespace",
    "started_at_utc",
    "completed_at_utc",
    "elapsed_runtime_seconds",
    "provider_cost_upper_bound_usd_cents",
    "source_count",
    "disposition_counts",
    "records",
    "next_step_state",
    "downstream_authorizations",
}
INVENTORY_RECORD_KEYS = {
    "record_id",
    "source_identity_sha256",
    "disposition",
    "output_state",
    "reason_code",
    "evidence_sha256",
}

REPO_ROOT = Path(__file__).resolve().parents[2]


class PreflightContractError(ValueError):
    """Raised whenever a preflight contract must fail closed."""


def _duplicate_guard(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreflightContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PreflightContractError(f"non-standard JSON constant is forbidden: {value}")


def parse_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightContractError(f"{label} is not UTF-8") from exc
    if text.startswith("\ufeff") or "\x00" in text:
        raise PreflightContractError(f"{label} contains forbidden framing")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=_reject_constant,
        )
    except PreflightContractError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise PreflightContractError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise PreflightContractError(f"{label} root must be an object")
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def authorization_terms_sha256(value: Mapping[str, Any]) -> str:
    """Hash every authorization term, excluding only the signature envelope."""

    terms = {key: item for key, item in value.items() if key != "owner_signature"}
    return sha256_bytes(canonical_json_bytes(terms))


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
            raise PreflightContractError("declared contract path is unavailable") from exc
        if _is_reparse(metadata):
            raise PreflightContractError("contract paths must not use links or reparse points")
        parent = current.parent
        if parent == current:
            return
        current = parent


def read_regular_json(path: Path, maximum: int, label: str) -> tuple[dict[str, Any], bytes]:
    _reject_link_chain(path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    binary = getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | binary)
    except OSError as exc:
        raise PreflightContractError(f"{label} cannot be opened") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0 or metadata.st_size > maximum:
            raise PreflightContractError(f"{label} size or type is invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise PreflightContractError(f"{label} ended before its declared size")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        if after_identity != before_identity:
            raise PreflightContractError(f"{label} identity changed while reading")
    finally:
        os.close(descriptor)
    payload = b"".join(chunks)
    return parse_json_bytes(payload, label), payload


def _require_external_private_path(path: Path, label: str) -> None:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        return
    except OSError as exc:
        raise PreflightContractError(f"{label} is unavailable") from exc
    raise PreflightContractError(f"{label} must remain outside the public repository")


def _exact_keys(value: Any, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise PreflightContractError(f"{label} fields are invalid")
    return value


def _trimmed_text(value: Any, label: str, maximum: int = 240) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise PreflightContractError(f"{label} must be nonempty trimmed text")
    return value


def _sha256(value: Any, label: str) -> str:
    text = _trimmed_text(value, label, 64)
    if not SHA256_PATTERN.fullmatch(text) or text == "0" * 64:
        raise PreflightContractError(f"{label} must be a nonzero lowercase SHA-256")
    return text


def _strict_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise PreflightContractError(f"{label} is outside its integer bounds")
    return value


def _strict_utc(value: Any, label: str) -> datetime:
    text = _trimmed_text(value, label, 20)
    if not UTC_PATTERN.fullmatch(text):
        raise PreflightContractError(f"{label} must be second-resolution UTC ending in Z")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise PreflightContractError(f"{label} is not a valid UTC instant") from exc


def _require_bool(value: Any, expected: bool, label: str) -> None:
    if value is not expected:
        raise PreflightContractError(f"{label} must be {str(expected).lower()}")


def _validate_downstream_authorizations(value: Any, label: str) -> None:
    fields = _exact_keys(value, DOWNSTREAM_KEYS, label)
    for key in sorted(DOWNSTREAM_KEYS):
        _require_bool(fields[key], False, f"{label}.{key}")


def _validate_static_terms(value: Mapping[str, Any]) -> None:
    if value["schema_version"] != AUTHORIZATION_SCHEMA:
        raise PreflightContractError("authorization schema_version is unsupported")
    if value["purpose"] != PURPOSE:
        raise PreflightContractError("authorization purpose is not preflight-only")

    execution = _exact_keys(value["execution_binding"], EXECUTION_BINDING_KEYS, "execution_binding")
    if execution["permitted_lifecycle_action"] != PERMITTED_ACTION:
        raise PreflightContractError("permitted lifecycle action is invalid")

    host = _exact_keys(value["host_binding"], HOST_BINDING_KEYS, "host_binding")
    if host["provider"] != "VAST_AI" or host["binding_type"] != "PRIVATE_HOST_BINDING_RECEIPT_SHA256":
        raise PreflightContractError("host binding is not the required abstract Vast binding")

    protected = _exact_keys(
        value["protected_data_scope"], PROTECTED_SCOPE_KEYS, "protected_data_scope"
    )
    if protected["existing_file_access"] != "READ_EXISTING_FILES_FOR_IDENTITY_SIZE_AND_SHA256_ONLY":
        raise PreflightContractError("protected-data access is not read-only inventory scope")
    for field in (
        "write_existing_paths_authorized",
        "network_egress_authorized",
        "export_protected_content_authorized",
        "scientific_analysis_authorized",
    ):
        _require_bool(protected[field], False, f"protected_data_scope.{field}")

    limits = _exact_keys(value["limits"], LIMIT_KEYS, "limits")
    _require_bool(limits["one_lifecycle_attempt_only"], True, "limits.one_lifecycle_attempt_only")

    _exact_keys(value["validity"], VALIDITY_KEYS, "validity")
    output = _exact_keys(value["output_policy"], OUTPUT_POLICY_KEYS, "output_policy")
    if output["namespace_mode"] != NAMESPACE_MODE or output["content_policy"] != OUTPUT_CONTENT_POLICY:
        raise PreflightContractError("output policy is not the fixed private inventory policy")
    _require_bool(output["overwrite_authorized"], False, "output_policy.overwrite_authorized")

    failure = _exact_keys(value["failure_policy"], FAILURE_POLICY_KEYS, "failure_policy")
    _require_bool(failure["stop_on_any_error"], True, "failure_policy.stop_on_any_error")
    _require_bool(
        failure["stop_on_unaccounted_input"],
        True,
        "failure_policy.stop_on_unaccounted_input",
    )
    _require_bool(
        failure["continue_to_heavy_workflow"],
        False,
        "failure_policy.continue_to_heavy_workflow",
    )
    if failure["partial_output_disposition"] != "SEAL_FAILED_RECEIPT_AND_STOP":
        raise PreflightContractError("partial output policy is invalid")

    _exact_keys(
        value["post_preflight_disposition"],
        POST_PREFLIGHT_KEYS,
        "post_preflight_disposition",
    )
    obligation = _exact_keys(
        value["inventory_obligation"],
        INVENTORY_OBLIGATION_KEYS,
        "inventory_obligation",
    )
    if (
        obligation["source_domain"] != SOURCE_DOMAIN
        or obligation["record_id_policy"] != RECORD_ID_POLICY
        or obligation["source_identity_policy"] != SOURCE_IDENTITY_POLICY
        or obligation["allowed_dispositions"] != list(DISPOSITIONS)
        or obligation["accounting_equation"] != ACCOUNTING_EQUATION
    ):
        raise PreflightContractError("inventory no-silent-drop terms changed")
    for field in (
        "explicit_disposition_required",
        "unique_record_id_required",
        "no_silent_drop",
    ):
        _require_bool(obligation[field], True, f"inventory_obligation.{field}")

    _validate_downstream_authorizations(
        value["downstream_authorizations"], "downstream_authorizations"
    )
    _exact_keys(value["owner_signature"], OWNER_SIGNATURE_KEYS, "owner_signature")


def validate_authorization_schema(value: Mapping[str, Any]) -> str:
    """Validate structure and fixed safety terms, but never grant authorization."""

    root = _exact_keys(value, AUTHORIZATION_KEYS, "authorization")
    _validate_static_terms(root)
    state = root["authorization_state"]
    if state not in {OWNER_INPUT_REQUIRED, OWNER_SIGNED}:
        raise PreflightContractError("authorization_state is invalid")

    execution = root["execution_binding"]
    host = root["host_binding"]
    protected = root["protected_data_scope"]
    limits = root["limits"]
    validity = root["validity"]
    output = root["output_policy"]
    post = root["post_preflight_disposition"]
    signature = root["owner_signature"]

    if state == OWNER_INPUT_REQUIRED:
        if (
            execution["preflight_plan_sha256"] is not None
            or host["binding_receipt_sha256"] is not None
            or protected["approved_input_scope_receipt_sha256"] is not None
            or limits["max_runtime_seconds"] is not None
            or limits["max_cost_usd_cents"] is not None
            or any(validity[field] != "" for field in VALIDITY_KEYS)
            or output["new_output_namespace"] != ""
            or any(post[field] != "" for field in POST_PREFLIGHT_KEYS)
            or signature
            != {
                "state": NOT_SIGNED,
                "signed_by": "",
                "signed_at_utc": "",
                "attestation": "",
                "signature_verification_receipt_sha256": None,
            }
        ):
            raise PreflightContractError(
                "OWNER_INPUT_REQUIRED must retain blank owner fields and NOT_SIGNED state"
            )
        return state

    _sha256(execution["preflight_plan_sha256"], "execution_binding.preflight_plan_sha256")
    _sha256(host["binding_receipt_sha256"], "host_binding.binding_receipt_sha256")
    _sha256(
        protected["approved_input_scope_receipt_sha256"],
        "protected_data_scope.approved_input_scope_receipt_sha256",
    )
    _strict_int(limits["max_runtime_seconds"], "limits.max_runtime_seconds", 1, MAX_RUNTIME_SECONDS)
    _strict_int(limits["max_cost_usd_cents"], "limits.max_cost_usd_cents", 1, MAX_COST_USD_CENTS)

    issued = _strict_utc(validity["issued_at_utc"], "validity.issued_at_utc")
    not_before = _strict_utc(validity["not_before_utc"], "validity.not_before_utc")
    expires = _strict_utc(validity["expires_at_utc"], "validity.expires_at_utc")
    if not (issued <= not_before < expires) or expires - issued > MAX_AUTHORIZATION_LIFETIME:
        raise PreflightContractError("authorization validity order or lifetime is invalid")

    namespace = _trimmed_text(output["new_output_namespace"], "output_policy.new_output_namespace", 74)
    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise PreflightContractError("new output namespace is not a safe abstract namespace")
    for field in POST_PREFLIGHT_KEYS:
        if post[field] not in POST_PREFLIGHT_DISPOSITIONS:
            raise PreflightContractError(f"post_preflight_disposition.{field} is invalid")

    if signature["state"] != OWNER_SIGNED_AND_INDEPENDENTLY_VERIFIED:
        raise PreflightContractError("owner signature state is not independently verified")
    _trimmed_text(signature["signed_by"], "owner_signature.signed_by", 160)
    signed_at = _strict_utc(signature["signed_at_utc"], "owner_signature.signed_at_utc")
    if issued > signed_at or signed_at >= expires:
        raise PreflightContractError("owner signature is outside the authorization window")
    if signature["attestation"] != OWNER_ATTESTATION:
        raise PreflightContractError("owner attestation text is not exact")
    _sha256(
        signature["signature_verification_receipt_sha256"],
        "owner_signature.signature_verification_receipt_sha256",
    )
    return state


def _validate_signature_receipt(
    value: Mapping[str, Any],
    payload: bytes,
    authorization: Mapping[str, Any],
) -> None:
    receipt = _exact_keys(value, SIGNATURE_RECEIPT_KEYS, "signature verification receipt")
    if receipt["schema_version"] != SIGNATURE_RECEIPT_SCHEMA or receipt["status"] != "VERIFIED":
        raise PreflightContractError("signature verification receipt status is invalid")
    signature = authorization["owner_signature"]
    if sha256_bytes(payload) != signature["signature_verification_receipt_sha256"]:
        raise PreflightContractError("signature verification receipt hash mismatch")
    if receipt["authorization_terms_sha256"] != authorization_terms_sha256(authorization):
        raise PreflightContractError("signature receipt is bound to different authorization terms")
    if (
        receipt["signed_by"] != signature["signed_by"]
        or receipt["signed_at_utc"] != signature["signed_at_utc"]
        or receipt["signature_method"] != SIGNATURE_METHOD
    ):
        raise PreflightContractError("signature receipt owner binding is invalid")
    _sha256(receipt["signature_evidence_sha256"], "signature_evidence_sha256")
    _require_bool(receipt["verifier_independent"], True, "verifier_independent")
    verified_by = _trimmed_text(receipt["verified_by"], "verified_by", 160)
    if verified_by.casefold() == signature["signed_by"].casefold():
        raise PreflightContractError("signature verifier must be independent of the signer")
    signed_at = _strict_utc(receipt["signed_at_utc"], "signed_at_utc")
    verified_at = _strict_utc(receipt["verified_at_utc"], "verified_at_utc")
    expires = _strict_utc(authorization["validity"]["expires_at_utc"], "expires_at_utc")
    if not signed_at <= verified_at < expires:
        raise PreflightContractError("signature verification time is outside the signed window")


def validate_signed_authorization_binding(
    authorization: Mapping[str, Any],
    signature_receipt: Mapping[str, Any],
    signature_receipt_payload: bytes,
    *,
    expected_host_binding_sha256: str,
    expected_output_namespace: str,
) -> str:
    """Validate a signed document and external signature-verification binding.

    This proves contract binding, not signer identity.  The independent receipt
    is the accountable evidence that identity/signature verification happened.
    """

    if validate_authorization_schema(authorization) != OWNER_SIGNED:
        raise PreflightContractError("owner authorization is not signed")
    expected_host = _sha256(expected_host_binding_sha256, "expected host binding")
    if authorization["host_binding"]["binding_receipt_sha256"] != expected_host:
        raise PreflightContractError("authorization is bound to a different host")
    namespace = _trimmed_text(expected_output_namespace, "expected output namespace", 74)
    if authorization["output_policy"]["new_output_namespace"] != namespace:
        raise PreflightContractError("authorization is bound to a different output namespace")
    _validate_signature_receipt(signature_receipt, signature_receipt_payload, authorization)
    return authorization_terms_sha256(authorization)


def require_effective_authorization(
    authorization: Mapping[str, Any],
    signature_receipt: Mapping[str, Any],
    signature_receipt_payload: bytes,
    *,
    expected_host_binding_sha256: str,
    expected_output_namespace: str,
    now: datetime | None = None,
) -> str:
    """Return the terms digest only while a signed authorization is effective."""

    terms_digest = validate_signed_authorization_binding(
        authorization,
        signature_receipt,
        signature_receipt_payload,
        expected_host_binding_sha256=expected_host_binding_sha256,
        expected_output_namespace=expected_output_namespace,
    )
    moment = now or datetime.now(timezone.utc).replace(microsecond=0)
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        raise PreflightContractError("authorization check time must be timezone-aware UTC")
    not_before = _strict_utc(authorization["validity"]["not_before_utc"], "not_before_utc")
    expires = _strict_utc(authorization["validity"]["expires_at_utc"], "expires_at_utc")
    verified_at = _strict_utc(signature_receipt["verified_at_utc"], "verified_at_utc")
    if not (not_before <= moment < expires) or verified_at > moment:
        raise PreflightContractError("authorization is not currently effective")
    return terms_digest


def validate_source_manifest(
    value: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> list[tuple[str, str]]:
    manifest = _exact_keys(value, SOURCE_MANIFEST_KEYS, "source manifest")
    if manifest["schema_version"] != SOURCE_MANIFEST_SCHEMA:
        raise PreflightContractError("source manifest schema is invalid")
    if manifest["authorization_terms_sha256"] != authorization_terms_sha256(authorization):
        raise PreflightContractError("source manifest authorization binding is invalid")
    if (
        manifest["approved_input_scope_receipt_sha256"]
        != authorization["protected_data_scope"]["approved_input_scope_receipt_sha256"]
    ):
        raise PreflightContractError("source manifest input-scope binding is invalid")
    if manifest["output_namespace"] != authorization["output_policy"]["new_output_namespace"]:
        raise PreflightContractError("source manifest output namespace is invalid")
    enumerated = _strict_utc(manifest["enumerated_at_utc"], "enumerated_at_utc")
    not_before = _strict_utc(authorization["validity"]["not_before_utc"], "not_before_utc")
    expires = _strict_utc(authorization["validity"]["expires_at_utc"], "expires_at_utc")
    if not not_before <= enumerated < expires:
        raise PreflightContractError("source enumeration is outside the authorization window")
    source_count = _strict_int(manifest["source_count"], "source_count", 1, MAX_SOURCE_RECORDS)
    records = manifest["records"]
    if not isinstance(records, list) or len(records) != source_count:
        raise PreflightContractError("source record cardinality is invalid")
    normalized: list[tuple[str, str]] = []
    for index, raw_record in enumerate(records, start=1):
        record = _exact_keys(raw_record, SOURCE_RECORD_KEYS, f"source records[{index - 1}]")
        record_id = record["record_id"]
        if record_id != f"input-{index:06d}" or not RECORD_ID_PATTERN.fullmatch(record_id):
            raise PreflightContractError("source records must use exact sequential generic IDs")
        identity = _sha256(
            record["source_identity_sha256"],
            f"source records[{index - 1}].source_identity_sha256",
        )
        normalized.append((record_id, identity))
    if len({identity for _, identity in normalized}) != source_count:
        raise PreflightContractError("source identity digests must be unique")
    return normalized


def validate_inventory_receipt(
    receipt: Mapping[str, Any],
    *,
    receipt_payload: bytes,
    source_manifest: Mapping[str, Any],
    source_manifest_payload: bytes,
    authorization: Mapping[str, Any],
    signature_receipt: Mapping[str, Any],
    signature_receipt_payload: bytes,
    expected_host_binding_sha256: str,
    expected_output_namespace: str,
) -> dict[str, Any]:
    """Validate explicit one-record/one-disposition accounting.

    Validation is retrospective: the signed authorization must have covered the
    recorded enumeration and completion instants, but it need not still be live.
    It never authorizes a next step.
    """

    del receipt_payload  # The caller retains it for its own immutable sidecar.
    terms_digest = validate_signed_authorization_binding(
        authorization,
        signature_receipt,
        signature_receipt_payload,
        expected_host_binding_sha256=expected_host_binding_sha256,
        expected_output_namespace=expected_output_namespace,
    )
    source_records = validate_source_manifest(source_manifest, authorization)
    value = _exact_keys(receipt, INVENTORY_RECEIPT_KEYS, "inventory receipt")
    if value["schema_version"] != INVENTORY_RECEIPT_SCHEMA:
        raise PreflightContractError("inventory receipt schema is invalid")
    if value["authorization_terms_sha256"] != terms_digest:
        raise PreflightContractError("inventory receipt authorization binding is invalid")
    if value["source_manifest_sha256"] != sha256_bytes(source_manifest_payload):
        raise PreflightContractError("inventory receipt source manifest hash mismatch")
    if value["output_namespace"] != expected_output_namespace:
        raise PreflightContractError("inventory receipt output namespace is invalid")
    if value["next_step_state"] != NEXT_STEP_STATE:
        raise PreflightContractError("inventory receipt improperly authorizes a next step")
    _validate_downstream_authorizations(
        value["downstream_authorizations"], "inventory receipt downstream_authorizations"
    )

    started = _strict_utc(value["started_at_utc"], "started_at_utc")
    completed = _strict_utc(value["completed_at_utc"], "completed_at_utc")
    enumerated = _strict_utc(source_manifest["enumerated_at_utc"], "enumerated_at_utc")
    not_before = _strict_utc(authorization["validity"]["not_before_utc"], "not_before_utc")
    expires = _strict_utc(authorization["validity"]["expires_at_utc"], "expires_at_utc")
    max_runtime = authorization["limits"]["max_runtime_seconds"]
    verified_at = _strict_utc(signature_receipt["verified_at_utc"], "verified_at_utc")
    if not (not_before <= started <= enumerated <= completed < expires):
        raise PreflightContractError("inventory timestamps are outside the signed window")
    if verified_at > started:
        raise PreflightContractError("inventory began before independent signature verification")
    elapsed = _strict_int(
        value["elapsed_runtime_seconds"],
        "elapsed_runtime_seconds",
        0,
        MAX_RUNTIME_SECONDS,
    )
    if elapsed != int((completed - started).total_seconds()) or elapsed > max_runtime:
        raise PreflightContractError("inventory receipt exceeds signed runtime cap")
    observed_cost = _strict_int(
        value["provider_cost_upper_bound_usd_cents"],
        "provider_cost_upper_bound_usd_cents",
        0,
        MAX_COST_USD_CENTS,
    )
    if observed_cost > authorization["limits"]["max_cost_usd_cents"]:
        raise PreflightContractError("inventory receipt exceeds signed cost cap")

    source_count = len(source_records)
    receipt_source_count = _strict_int(
        value["source_count"], "inventory source_count", 1, MAX_SOURCE_RECORDS
    )
    if receipt_source_count != source_count:
        raise PreflightContractError("inventory source_count differs from enumeration")
    counts = _exact_keys(value["disposition_counts"], set(DISPOSITION_COUNT_KEYS), "disposition_counts")
    normalized_counts = {
        key: _strict_int(counts[key], f"disposition_counts.{key}", 0, source_count)
        for key in DISPOSITION_COUNT_KEYS
    }
    if sum(normalized_counts.values()) != source_count:
        raise PreflightContractError("inventory accounting equation is false")

    records = value["records"]
    if not isinstance(records, list) or len(records) != source_count:
        raise PreflightContractError("inventory record cardinality is invalid")
    actual_records: list[tuple[str, str]] = []
    observed_counts = {key: 0 for key in DISPOSITION_COUNT_KEYS}
    for index, raw_record in enumerate(records):
        record = _exact_keys(raw_record, INVENTORY_RECORD_KEYS, f"records[{index}]")
        record_id = record["record_id"]
        if not isinstance(record_id, str) or not RECORD_ID_PATTERN.fullmatch(record_id):
            raise PreflightContractError("inventory record_id is invalid")
        source_identity = _sha256(
            record["source_identity_sha256"], "inventory source_identity_sha256"
        )
        actual_records.append((record_id, source_identity))
        disposition = record["disposition"]
        if disposition not in DISPOSITION_TO_COUNT_KEY:
            raise PreflightContractError("inventory disposition is invalid")
        expected_output_state = (
            "EXPLICIT_OUTPUT" if disposition == "INVENTORIED" else "EXPLICIT_DISPOSITION"
        )
        if record["output_state"] != expected_output_state:
            raise PreflightContractError("inventory output/disposition state is inconsistent")
        reason = record["reason_code"]
        if not isinstance(reason, str) or not REASON_CODE_PATTERN.fullmatch(reason):
            raise PreflightContractError("inventory reason_code is invalid")
        _sha256(record["evidence_sha256"], "inventory evidence_sha256")
        observed_counts[DISPOSITION_TO_COUNT_KEY[disposition]] += 1
    if actual_records != source_records or len(set(actual_records)) != source_count:
        raise PreflightContractError(
            "inventory contains a silent drop, duplicate, substitution, swap, or extra record"
        )
    if observed_counts != normalized_counts:
        raise PreflightContractError("inventory disposition counts do not match records")
    expected_status = (
        "ALL_INPUTS_ACCOUNTED_WITH_FAILURES"
        if normalized_counts["failed"]
        else "ALL_INPUTS_ACCOUNTED"
    )
    if value["status"] != expected_status:
        raise PreflightContractError("inventory status does not match explicit dispositions")
    return {
        "schema_version": VALIDATION_RESULT_SCHEMA,
        "accounting_valid": True,
        "all_inputs_accounted": True,
        "source_count": source_count,
        "disposition_counts": normalized_counts,
        "followup_authorized": False,
        "next_step_state": NEXT_STEP_STATE,
    }


def _json_result(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_external(path: Path, maximum: int, label: str) -> tuple[dict[str, Any], bytes]:
    _require_external_private_path(path, label)
    return read_regular_json(path, maximum, label)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    schema = subparsers.add_parser(
        "schema-check",
        help="validate structure and safety terms; this never authorizes execution",
    )
    schema.add_argument("--authorization", required=True, type=Path)
    schema.add_argument("--json", action="store_true")

    effective = subparsers.add_parser(
        "authorization-check",
        help="require a currently effective owner-signed preflight authorization",
    )
    effective.add_argument("--authorization", required=True, type=Path)
    effective.add_argument("--signature-verification-receipt", required=True, type=Path)
    effective.add_argument("--expected-host-binding-sha256", required=True)
    effective.add_argument("--expected-output-namespace", required=True)
    effective.add_argument("--json", action="store_true")

    inventory = subparsers.add_parser(
        "inventory-check",
        help="audit one explicit output or disposition for every enumerated input",
    )
    inventory.add_argument("--authorization", required=True, type=Path)
    inventory.add_argument("--signature-verification-receipt", required=True, type=Path)
    inventory.add_argument("--source-manifest", required=True, type=Path)
    inventory.add_argument("--inventory-receipt", required=True, type=Path)
    inventory.add_argument("--expected-host-binding-sha256", required=True)
    inventory.add_argument("--expected-output-namespace", required=True)
    inventory.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "schema-check":
            authorization, _ = read_regular_json(
                args.authorization, MAX_AUTHORIZATION_BYTES, "authorization"
            )
            state = validate_authorization_schema(authorization)
            result = {
                "schema_version": VALIDATION_RESULT_SCHEMA,
                "schema_valid": True,
                "authorization_state": state,
                "authorization_effective": False,
                "reason": "SCHEMA_VALIDATION_DOES_NOT_AUTHORIZE_ACTION",
            }
        else:
            authorization, _ = _load_external(
                args.authorization, MAX_AUTHORIZATION_BYTES, "authorization"
            )
            signature, signature_payload = _load_external(
                args.signature_verification_receipt,
                MAX_SIGNATURE_RECEIPT_BYTES,
                "signature verification receipt",
            )
            if args.command == "authorization-check":
                terms_digest = require_effective_authorization(
                    authorization,
                    signature,
                    signature_payload,
                    expected_host_binding_sha256=args.expected_host_binding_sha256,
                    expected_output_namespace=args.expected_output_namespace,
                )
                result = {
                    "schema_version": VALIDATION_RESULT_SCHEMA,
                    "schema_valid": True,
                    "authorization_effective": True,
                    "authorization_terms_sha256": terms_digest,
                    "permitted_lifecycle_action": PERMITTED_ACTION,
                    "max_runtime_seconds": authorization["limits"]["max_runtime_seconds"],
                    "max_cost_usd_cents": authorization["limits"]["max_cost_usd_cents"],
                    "heavy_execution_authorized": False,
                    "publication_authorized": False,
                    "release_authorized": False,
                    "upload_authorized": False,
                }
            else:
                source, source_payload = _load_external(
                    args.source_manifest, MAX_SOURCE_MANIFEST_BYTES, "source manifest"
                )
                receipt, receipt_payload = _load_external(
                    args.inventory_receipt,
                    MAX_INVENTORY_RECEIPT_BYTES,
                    "inventory receipt",
                )
                result = validate_inventory_receipt(
                    receipt,
                    receipt_payload=receipt_payload,
                    source_manifest=source,
                    source_manifest_payload=source_payload,
                    authorization=authorization,
                    signature_receipt=signature,
                    signature_receipt_payload=signature_payload,
                    expected_host_binding_sha256=args.expected_host_binding_sha256,
                    expected_output_namespace=args.expected_output_namespace,
                )
    except PreflightContractError as exc:
        print(f"preflight contract rejected: {exc}", file=sys.stderr)
        return 1
    print(_json_result(result) if args.json else "preflight contract accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
