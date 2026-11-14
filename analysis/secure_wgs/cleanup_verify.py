#!/usr/bin/env python3
"""Verify that controlled paths and Vast resources are absent.

This helper is intentionally non-destructive.  It captures Vast CLI output in
memory, writes a private attestation outside the repository, and emits only a
generic pass/fail status.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from analysis.secure_wgs.orchestrator import (
    REPO_ROOT,
    SecureWgsError,
    _atomic_json_write,
    _is_within,
    _resolved,
)


ATTESTATION_SCHEMA = "secure-wgs-cleanup-attestation/v1"


def _resource_ids(payload: object, collection_keys: tuple[str, ...]) -> set[int]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = None
        for key in collection_keys:
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
        if records is None:
            raise SecureWgsError("Vast cleanup state has an unknown structure")
    else:
        raise SecureWgsError("Vast cleanup state has an unknown structure")
    found: set[int] = set()
    for record in records:
        if not isinstance(record, dict):
            raise SecureWgsError("Vast cleanup state has an invalid record")
        value = record.get("id", record.get("instance_id", record.get("volume_id")))
        try:
            resource_id = int(value)
        except (TypeError, ValueError) as exc:
            raise SecureWgsError("Vast cleanup state has an invalid resource ID") from exc
        if resource_id <= 0:
            raise SecureWgsError("Vast cleanup state has an invalid resource ID")
        found.add(resource_id)
    return found


def _vast_json(arguments: list[str]) -> object:
    try:
        result = subprocess.run(
            ["vastai", *arguments, "--raw"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SecureWgsError("Vast cleanup state could not be queried") from exc
    if result.returncode != 0:
        raise SecureWgsError("Vast cleanup state could not be queried")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SecureWgsError("Vast cleanup state was not machine-readable") from exc


def verify_cleanup(
    *,
    expected_deleted_paths: list[Path],
    instance_id: int,
    volume_ids: list[int],
    attestation_path: Path,
    instances_payload: object | None = None,
    volumes_payload: object | None = None,
) -> dict:
    """Fail unless all exact local paths and remote resource IDs are absent."""

    local_absent = True
    for path in expected_deleted_paths:
        resolved = _resolved(path, must_exist=False)
        if _is_within(path.absolute(), REPO_ROOT) or _is_within(resolved, REPO_ROOT):
            raise SecureWgsError("cleanup targets must not be repository paths")
        if path.exists() or path.is_symlink() or resolved.exists():
            local_absent = False

    if instance_id <= 0 or any(volume_id <= 0 for volume_id in volume_ids):
        raise SecureWgsError("cleanup resource IDs must be positive")

    if instances_payload is None:
        instances_payload = _vast_json(["show", "instances"])
    active_instances = _resource_ids(instances_payload, ("instances", "results"))
    instance_absent = instance_id not in active_instances

    if volumes_payload is None:
        volumes_payload = _vast_json(["show", "volumes"])
    active_volumes = _resource_ids(volumes_payload, ("volumes", "results"))
    volumes_absent = all(volume_id not in active_volumes for volume_id in volume_ids)

    passed = local_absent and instance_absent and volumes_absent
    payload = {
        "schema": ATTESTATION_SCHEMA,
        "classification": "PRIVATE_AUDIT_METADATA_DO_NOT_COMMIT",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "instance_id": instance_id,
        "volume_ids": sorted(volume_ids),
        "expected_deleted_path_count": len(expected_deleted_paths),
        "local_paths_absent": local_absent,
        "instance_absent": instance_absent,
        "volumes_absent": volumes_absent,
        "passed": passed,
        "limits": (
            "This verifies API-visible resource absence and exact local-path absence only; "
            "retain the provider deletion confirmation or DPA certificate separately."
        ),
    }
    _atomic_json_write(attestation_path, payload)
    if not passed:
        raise SecureWgsError("cleanup verification failed")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify controlled WGS cleanup without deletion.")
    parser.add_argument("--instance-id", required=True, type=int)
    parser.add_argument("--volume-id", action="append", type=int, default=[])
    parser.add_argument("--expected-deleted-path", action="append", type=Path, default=[])
    parser.add_argument("--attestation", required=True, type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        verify_cleanup(
            expected_deleted_paths=args.expected_deleted_path,
            instance_id=args.instance_id,
            volume_ids=args.volume_id,
            attestation_path=args.attestation,
        )
    except SecureWgsError:
        print("secure_wgs_cleanup=failed_closed", file=sys.stderr)
        return 2
    print("secure_wgs_cleanup=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
