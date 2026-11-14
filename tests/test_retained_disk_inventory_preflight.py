from __future__ import annotations

import contextlib
import copy
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from analysis.secure_wgs import retained_disk_inventory_preflight as gate


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT
    / "analysis"
    / "secure_wgs"
    / "retained_disk_inventory_preflight_authorization.template.v1.json"
)
HOST_BINDING = "2" * 64
OUTPUT_NAMESPACE = "preflight-synthetic-0001"
NOW = datetime(2030, 1, 1, 0, 5, tzinfo=timezone.utc)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return gate.canonical_json_bytes(value) + b"\n"


def _template() -> dict[str, Any]:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def _signed_authorization() -> tuple[dict[str, Any], dict[str, Any], bytes]:
    value = _template()
    value["authorization_state"] = gate.OWNER_SIGNED
    value["execution_binding"]["preflight_plan_sha256"] = "1" * 64
    value["host_binding"]["binding_receipt_sha256"] = HOST_BINDING
    value["protected_data_scope"]["approved_input_scope_receipt_sha256"] = "3" * 64
    value["limits"]["max_runtime_seconds"] = 600
    value["limits"]["max_cost_usd_cents"] = 500
    value["validity"] = {
        "issued_at_utc": "2030-01-01T00:00:00Z",
        "not_before_utc": "2030-01-01T00:01:00Z",
        "expires_at_utc": "2030-01-01T01:00:00Z",
    }
    value["output_policy"]["new_output_namespace"] = OUTPUT_NAMESPACE
    value["post_preflight_disposition"] = {
        "on_success": "STOP_COMPUTE_RETAIN_DISK",
        "on_failure": "STOP_COMPUTE_RETAIN_DISK",
    }
    value["owner_signature"] = {
        "state": gate.OWNER_SIGNED_AND_INDEPENDENTLY_VERIFIED,
        "signed_by": "synthetic-owner",
        "signed_at_utc": "2030-01-01T00:02:00Z",
        "attestation": gate.OWNER_ATTESTATION,
        "signature_verification_receipt_sha256": None,
    }
    verification = {
        "schema_version": gate.SIGNATURE_RECEIPT_SCHEMA,
        "status": "VERIFIED",
        "authorization_terms_sha256": gate.authorization_terms_sha256(value),
        "signed_by": "synthetic-owner",
        "signed_at_utc": "2030-01-01T00:02:00Z",
        "signature_method": gate.SIGNATURE_METHOD,
        "signature_evidence_sha256": "4" * 64,
        "verifier_independent": True,
        "verified_by": "synthetic-independent-verifier",
        "verified_at_utc": "2030-01-01T00:03:00Z",
    }
    verification_raw = _json_bytes(verification)
    value["owner_signature"]["signature_verification_receipt_sha256"] = gate.sha256_bytes(
        verification_raw
    )
    return value, verification, verification_raw


def _source_manifest(
    authorization: dict[str, Any], count: int = 4
) -> tuple[dict[str, Any], bytes]:
    value = {
        "schema_version": gate.SOURCE_MANIFEST_SCHEMA,
        "authorization_terms_sha256": gate.authorization_terms_sha256(authorization),
        "approved_input_scope_receipt_sha256": authorization["protected_data_scope"][
            "approved_input_scope_receipt_sha256"
        ],
        "output_namespace": OUTPUT_NAMESPACE,
        "enumerated_at_utc": "2030-01-01T00:04:00Z",
        "source_count": count,
        "records": [
            {
                "record_id": f"input-{index:06d}",
                "source_identity_sha256": f"{10 + index:x}" * 64,
            }
            for index in range(1, count + 1)
        ],
    }
    return value, _json_bytes(value)


def _inventory_receipt(
    authorization: dict[str, Any],
    source: dict[str, Any],
    source_raw: bytes,
) -> tuple[dict[str, Any], bytes]:
    dispositions = ["INVENTORIED", "EXPLICITLY_EXCLUDED", "UNSUPPORTED", "FAILED"]
    records: list[dict[str, Any]] = []
    counts = {key: 0 for key in gate.DISPOSITION_COUNT_KEYS}
    for index, source_record in enumerate(source["records"]):
        disposition = dispositions[index % len(dispositions)]
        counts[gate.DISPOSITION_TO_COUNT_KEY[disposition]] += 1
        records.append(
            {
                "record_id": source_record["record_id"],
                "source_identity_sha256": source_record["source_identity_sha256"],
                "disposition": disposition,
                "output_state": (
                    "EXPLICIT_OUTPUT"
                    if disposition == "INVENTORIED"
                    else "EXPLICIT_DISPOSITION"
                ),
                "reason_code": f"SYNTHETIC_{disposition}",
                "evidence_sha256": f"{5 + index:x}" * 64,
            }
        )
    value = {
        "schema_version": gate.INVENTORY_RECEIPT_SCHEMA,
        "status": (
            "ALL_INPUTS_ACCOUNTED_WITH_FAILURES"
            if counts["failed"]
            else "ALL_INPUTS_ACCOUNTED"
        ),
        "authorization_terms_sha256": gate.authorization_terms_sha256(authorization),
        "source_manifest_sha256": gate.sha256_bytes(source_raw),
        "output_namespace": OUTPUT_NAMESPACE,
        "started_at_utc": "2030-01-01T00:03:00Z",
        "completed_at_utc": "2030-01-01T00:06:00Z",
        "elapsed_runtime_seconds": 180,
        "provider_cost_upper_bound_usd_cents": 20,
        "source_count": source["source_count"],
        "disposition_counts": counts,
        "records": records,
        "next_step_state": gate.NEXT_STEP_STATE,
        "downstream_authorizations": copy.deepcopy(
            authorization["downstream_authorizations"]
        ),
    }
    return value, _json_bytes(value)


def _validate_inventory(
    authorization: dict[str, Any],
    signature: dict[str, Any],
    signature_raw: bytes,
    source: dict[str, Any],
    source_raw: bytes,
    receipt: dict[str, Any],
    receipt_raw: bytes,
) -> dict[str, Any]:
    return gate.validate_inventory_receipt(
        receipt,
        receipt_payload=receipt_raw,
        source_manifest=source,
        source_manifest_payload=source_raw,
        authorization=authorization,
        signature_receipt=signature,
        signature_receipt_payload=signature_raw,
        expected_host_binding_sha256=HOST_BINDING,
        expected_output_namespace=OUTPUT_NAMESPACE,
    )


def _invoke(function: Callable[[list[str]], int], argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = function(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def test_blank_template_is_schema_valid_but_not_authorized() -> None:
    value = _template()
    assert gate.validate_authorization_schema(value) == gate.OWNER_INPUT_REQUIRED
    with pytest.raises(gate.PreflightContractError, match="not signed"):
        gate.require_effective_authorization(
            value,
            {},
            b"{}",
            expected_host_binding_sha256=HOST_BINDING,
            expected_output_namespace=OUTPUT_NAMESPACE,
            now=NOW,
        )


def test_schema_cli_never_reports_effective_authorization() -> None:
    code, stdout, stderr = _invoke(
        gate.main,
        ["schema-check", "--authorization", str(TEMPLATE), "--json"],
    )
    assert code == 0
    assert stderr == ""
    result = json.loads(stdout)
    assert result["schema_valid"] is True
    assert result["authorization_effective"] is False
    assert result["reason"] == "SCHEMA_VALIDATION_DOES_NOT_AUTHORIZE_ACTION"


def test_signed_authorization_requires_matching_independent_receipt() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    assert gate.validate_authorization_schema(authorization) == gate.OWNER_SIGNED
    terms = gate.require_effective_authorization(
        authorization,
        signature,
        signature_raw,
        expected_host_binding_sha256=HOST_BINDING,
        expected_output_namespace=OUTPUT_NAMESPACE,
        now=NOW,
    )
    assert terms == gate.authorization_terms_sha256(authorization)


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(gate.PreflightContractError, match="duplicate JSON key"):
        gate.parse_json_bytes(b'{"schema":1,"schema":2}', "synthetic")


def test_unknown_authorization_field_is_rejected() -> None:
    value = _template()
    value["unexpected"] = False
    with pytest.raises(gate.PreflightContractError, match="fields are invalid"):
        gate.validate_authorization_schema(value)


@pytest.mark.parametrize(
    "field",
    [
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
    ],
)
def test_every_downstream_permission_is_fixed_false(field: str) -> None:
    value = _template()
    value["downstream_authorizations"][field] = True
    with pytest.raises(gate.PreflightContractError, match="must be false"):
        gate.validate_authorization_schema(value)


def test_pending_template_cannot_smuggle_an_owner_value() -> None:
    value = _template()
    value["limits"]["max_runtime_seconds"] = 600
    with pytest.raises(gate.PreflightContractError, match="blank owner fields"):
        gate.validate_authorization_schema(value)


def test_signed_authorization_requires_positive_budget() -> None:
    value, _, _ = _signed_authorization()
    value["limits"]["max_cost_usd_cents"] = 0
    with pytest.raises(gate.PreflightContractError, match="integer bounds"):
        gate.validate_authorization_schema(value)


def test_signed_authorization_has_bounded_lifetime() -> None:
    value, _, _ = _signed_authorization()
    value["validity"]["expires_at_utc"] = "2030-01-02T00:00:01Z"
    with pytest.raises(gate.PreflightContractError, match="lifetime"):
        gate.validate_authorization_schema(value)


def test_output_namespace_must_be_abstract_and_new() -> None:
    value, _, _ = _signed_authorization()
    value["output_policy"]["new_output_namespace"] = "/workspace/existing"
    with pytest.raises(gate.PreflightContractError, match="safe abstract namespace"):
        gate.validate_authorization_schema(value)


def test_signature_receipt_hash_mismatch_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    signature["verified_by"] = "different-verifier"
    changed_raw = _json_bytes(signature)
    assert changed_raw != signature_raw
    with pytest.raises(gate.PreflightContractError, match="hash mismatch"):
        gate.require_effective_authorization(
            authorization,
            signature,
            changed_raw,
            expected_host_binding_sha256=HOST_BINDING,
            expected_output_namespace=OUTPUT_NAMESPACE,
            now=NOW,
        )


def test_signature_verifier_must_be_independent() -> None:
    authorization, signature, _ = _signed_authorization()
    signature["verified_by"] = authorization["owner_signature"]["signed_by"]
    signature_raw = _json_bytes(signature)
    authorization["owner_signature"]["signature_verification_receipt_sha256"] = (
        gate.sha256_bytes(signature_raw)
    )
    with pytest.raises(gate.PreflightContractError, match="independent"):
        gate.require_effective_authorization(
            authorization,
            signature,
            signature_raw,
            expected_host_binding_sha256=HOST_BINDING,
            expected_output_namespace=OUTPUT_NAMESPACE,
            now=NOW,
        )


def test_expired_authorization_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    with pytest.raises(gate.PreflightContractError, match="not currently effective"):
        gate.require_effective_authorization(
            authorization,
            signature,
            signature_raw,
            expected_host_binding_sha256=HOST_BINDING,
            expected_output_namespace=OUTPUT_NAMESPACE,
            now=datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    ("host", "namespace", "message"),
    [
        ("9" * 64, OUTPUT_NAMESPACE, "different host"),
        (HOST_BINDING, "preflight-different-0001", "different output namespace"),
    ],
)
def test_effective_authorization_is_bound_to_host_and_namespace(
    host: str, namespace: str, message: str
) -> None:
    authorization, signature, signature_raw = _signed_authorization()
    with pytest.raises(gate.PreflightContractError, match=message):
        gate.require_effective_authorization(
            authorization,
            signature,
            signature_raw,
            expected_host_binding_sha256=host,
            expected_output_namespace=namespace,
            now=NOW,
        )


def test_complete_inventory_has_one_explicit_state_per_input() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    result = _validate_inventory(
        authorization,
        signature,
        signature_raw,
        source,
        source_raw,
        receipt,
        receipt_raw,
    )
    assert result["all_inputs_accounted"] is True
    assert result["source_count"] == 4
    assert result["followup_authorized"] is False
    assert result["disposition_counts"] == {
        "inventoried": 1,
        "explicitly_excluded": 1,
        "unsupported": 1,
        "failed": 1,
    }


def test_silent_drop_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["records"].pop()
    with pytest.raises(gate.PreflightContractError, match="cardinality"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_duplicate_or_reordered_record_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["records"][1]["record_id"] = receipt["records"][0]["record_id"]
    with pytest.raises(gate.PreflightContractError, match="silent drop, duplicate, substitution"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_disposition_count_drift_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["disposition_counts"]["inventoried"] = 2
    with pytest.raises(gate.PreflightContractError, match="accounting equation"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_noninventoried_record_requires_explicit_disposition() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["records"][1]["output_state"] = "EXPLICIT_OUTPUT"
    with pytest.raises(gate.PreflightContractError, match="inconsistent"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_source_manifest_requires_exact_sequential_generic_ids() -> None:
    authorization, _, _ = _signed_authorization()
    source, _ = _source_manifest(authorization)
    source["records"][2]["record_id"] = "input-000004"
    with pytest.raises(gate.PreflightContractError, match="sequential generic IDs"):
        gate.validate_source_manifest(source, authorization)


def test_changed_source_identity_digest_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["records"][1]["source_identity_sha256"] = "e" * 64
    with pytest.raises(gate.PreflightContractError, match="substitution, swap"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_swapped_source_identity_digests_are_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    first = receipt["records"][0]["source_identity_sha256"]
    receipt["records"][0]["source_identity_sha256"] = receipt["records"][1][
        "source_identity_sha256"
    ]
    receipt["records"][1]["source_identity_sha256"] = first
    with pytest.raises(gate.PreflightContractError, match="substitution, swap"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_boolean_inventory_source_count_is_rejected() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization, count=1)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["source_count"] = True
    with pytest.raises(gate.PreflightContractError, match="integer bounds"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_source_manifest_is_bound_to_private_input_scope() -> None:
    authorization, _, _ = _signed_authorization()
    source, _ = _source_manifest(authorization)
    source["approved_input_scope_receipt_sha256"] = "9" * 64
    with pytest.raises(gate.PreflightContractError, match="input-scope binding"):
        gate.validate_source_manifest(source, authorization)


def test_inventory_runtime_cannot_exceed_signed_cap() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    authorization["limits"]["max_runtime_seconds"] = 60
    signature["authorization_terms_sha256"] = gate.authorization_terms_sha256(authorization)
    signature_raw = _json_bytes(signature)
    authorization["owner_signature"]["signature_verification_receipt_sha256"] = gate.sha256_bytes(
        signature_raw
    )
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    with pytest.raises(gate.PreflightContractError, match="runtime cap"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_inventory_cost_cannot_exceed_signed_cap() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    authorization["limits"]["max_cost_usd_cents"] = 10
    signature["authorization_terms_sha256"] = gate.authorization_terms_sha256(authorization)
    signature_raw = _json_bytes(signature)
    authorization["owner_signature"]["signature_verification_receipt_sha256"] = gate.sha256_bytes(
        signature_raw
    )
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    with pytest.raises(gate.PreflightContractError, match="cost cap"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_inventory_receipt_cannot_elevate_downstream_permissions() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    receipt["downstream_authorizations"]["xtea_heavy_execution_authorized"] = True
    with pytest.raises(gate.PreflightContractError, match="must be false"):
        _validate_inventory(
            authorization,
            signature,
            signature_raw,
            source,
            source_raw,
            receipt,
            receipt_raw,
        )


def test_all_inventoried_receipt_uses_nonfailure_status() -> None:
    authorization, signature, signature_raw = _signed_authorization()
    source, source_raw = _source_manifest(authorization, count=1)
    receipt, receipt_raw = _inventory_receipt(authorization, source, source_raw)
    assert receipt["status"] == "ALL_INPUTS_ACCOUNTED"
    result = _validate_inventory(
        authorization,
        signature,
        signature_raw,
        source,
        source_raw,
        receipt,
        receipt_raw,
    )
    assert result["disposition_counts"]["failed"] == 0
