from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from analysis.secure_wgs.remote import fetch_signed_plan as fetcher


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "analysis" / "secure_wgs" / "remote" / "fetch_signed_plan.py"
TEST_NOW = datetime.now(timezone.utc).replace(microsecond=0)
TEST_EXPIRY = TEST_NOW + timedelta(hours=2)
PUBLIC_TEST_ADDRESS = "8.8.8.8"
LINUX_EXECUTION = os.name == "posix" and sys.platform.startswith("linux")
linux_execution = pytest.mark.skipif(
    not LINUX_EXECUTION,
    reason="real transfer execution requires Linux descriptor primitives",
)


def _target_name(index: int) -> str:
    lane = index // 2 + 1
    read = index % 2 + 1
    return f"SAMPLE01_L{lane:03d}_R{read}.fastq.gz"


def _signed_url(host: str = "objects.invalid", expiry: datetime = TEST_EXPIRY) -> str:
    return (
        f"https://{host}/synthetic-object"
        f"?Expires={int(expiry.timestamp())}&Signature=synthetic-only"
    )


def _payload(
    blobs: list[bytes],
    *,
    host: str = "objects.invalid",
    expiry: datetime = TEST_EXPIRY,
) -> dict[str, Any]:
    files = [
        {
            "target_name": _target_name(index),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size_bytes": len(blob),
            "signed_url": _signed_url(host, expiry),
            "expires_utc": expiry.isoformat(),
        }
        for index, blob in enumerate(blobs)
    ]
    return {
        "schema": fetcher.SCHEMA,
        "classification": fetcher.CLASSIFICATION,
        "created_utc": (TEST_NOW - timedelta(minutes=1)).isoformat(),
        "source": {
            "provider": "Hugging Face",
            "repo_id": "synthetic-owner/synthetic-private-data",
            "revision": "synthetic-revision",
        },
        "token_persisted": False,
        "expires_utc": expiry.isoformat(),
        "file_count": len(files),
        "files": files,
    }


def _write_payload(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _load(path: Path, *, now: datetime = TEST_NOW) -> fetcher.TransferPlan:
    return fetcher.load_transfer_plan(path, now=now)


def _public_resolver(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
    assert host
    assert port == 443
    assert kwargs["type"] == socket.SOCK_STREAM
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (PUBLIC_TEST_ADDRESS, 443),
        )
    ]


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        url: str,
        *,
        status: int = 200,
        content_length: int | None = None,
    ) -> None:
        self._body = body
        self._offset = 0
        self._url = url
        self.status = status
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int) -> bytes:
        result = self._body[self._offset : self._offset + size]
        self._offset += len(result)
        return result


class FakeOpener:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, *, timeout: int) -> Any:
        assert timeout == fetcher.NETWORK_TIMEOUT_SECONDS
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if callable(outcome):
            outcome = outcome(request)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _guard(destination: Path) -> fetcher.DestinationGuard:
    return fetcher.validate_destination(destination, repository_root=None)


def _assert_no_transfer_artifacts(destination: Path) -> None:
    assert not list(destination.glob("SAMPLE*.fastq.gz"))
    assert not list(destination.glob(".secure-wgs-*.part"))
    assert not (destination / fetcher.COMPLETION_MARKER).exists()


@linux_execution
def test_success_uses_exact_digest_sizes_and_exclusive_publish(tmp_path: Path) -> None:
    blobs = [b"synthetic-read-one", b"synthetic-read-two"]
    plan_path = _write_payload(tmp_path / "plan.json", _payload(blobs))
    destination = tmp_path / "destination"
    destination.mkdir()
    plan = _load(plan_path)
    opener = FakeOpener(
        [FakeResponse(blob, plan.files[index].signed_url) for index, blob in enumerate(blobs)]
    )

    observed = fetcher.execute_transfer(
        plan,
        _guard(destination),
        opener=opener,
        resolver=_public_resolver,
    )

    assert observed == sum(map(len, blobs)) == plan.total_size_bytes
    assert [
        (destination / item.target_name).read_bytes() for item in plan.files
    ] == blobs
    assert not list(destination.glob(".secure-wgs-*.part"))
    marker = json.loads(
        (destination / fetcher.COMPLETION_MARKER).read_text(encoding="utf-8")
    )
    assert marker == {
        "file_count": len(plan.files),
        "schema": fetcher.COMPLETION_SCHEMA,
        "status": "COMPLETE",
        "target_sha256": [item.sha256 for item in plan.files],
        "total_size_bytes": plan.total_size_bytes,
    }
    assert all(request.get_header("Authorization") is None for request in opener.requests)


def test_duplicate_keys_and_nonfinite_json_are_rejected(tmp_path: Path) -> None:
    valid = json.dumps(_payload([b"x"]))
    duplicate = valid[:-1] + f',"schema":"{fetcher.SCHEMA}"' + "}"
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(fetcher.TransferError, match="duplicate_json_key"):
        _load(duplicate_path)

    nonfinite = valid[:-1] + ',"unknown":NaN}'
    nonfinite_path = tmp_path / "nonfinite.json"
    nonfinite_path.write_text(nonfinite, encoding="utf-8")
    with pytest.raises(fetcher.TransferError, match="invalid_json_constant"):
        _load(nonfinite_path)


@pytest.mark.parametrize("location", ["top", "source", "file"])
def test_unknown_fields_are_rejected(tmp_path: Path, location: str) -> None:
    payload = _payload([b"x"])
    if location == "top":
        payload["unknown"] = True
    elif location == "source":
        payload["source"]["unknown"] = True
    else:
        payload["files"][0]["unknown"] = True
    path = _write_payload(tmp_path / f"{location}.json", payload)
    with pytest.raises(fetcher.TransferError, match="missing_or_unknown_fields"):
        _load(path)


def test_plan_size_file_count_and_manifest_size_bounds(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * fetcher.MAX_PLAN_BYTES + b"}")
    with pytest.raises(fetcher.TransferError, match="plan_size_out_of_bounds"):
        _load(oversized)

    empty = _payload([])
    with pytest.raises(fetcher.TransferError, match="invalid_file_count"):
        _load(_write_payload(tmp_path / "empty.json", empty))

    too_many = _payload([b"x"] * (fetcher.MAX_FILE_COUNT + 1))
    with pytest.raises(fetcher.TransferError, match="invalid_file_count"):
        _load(_write_payload(tmp_path / "too-many.json", too_many))

    total = _payload([b"x"] * 5)
    for item in total["files"]:
        item["size_bytes"] = fetcher.MAX_FILE_BYTES
    with pytest.raises(fetcher.TransferError, match="total_size_out_of_bounds"):
        _load(_write_payload(tmp_path / "too-large.json", total))


@pytest.mark.parametrize("bad_size", [True, 0, -1, fetcher.MAX_FILE_BYTES + 1])
def test_file_sizes_must_be_finite_positive_integers(tmp_path: Path, bad_size: Any) -> None:
    payload = _payload([b"x"])
    payload["files"][0]["size_bytes"] = bad_size
    path = _write_payload(tmp_path / "bad-size.json", payload)
    with pytest.raises(fetcher.TransferError, match="file_size_out_of_bounds"):
        _load(path)


def test_plan_and_url_expiry_are_enforced_and_bound(tmp_path: Path) -> None:
    expired_at = TEST_NOW - timedelta(seconds=1)
    expired = _payload([b"x"], expiry=expired_at)
    with pytest.raises(fetcher.TransferError, match="expired_or_incoherent_plan"):
        _load(_write_payload(tmp_path / "expired.json", expired))

    mismatched = _payload([b"x"])
    mismatched["files"][0]["expires_utc"] = (
        TEST_EXPIRY - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(fetcher.TransferError, match="expired_or_mismatched_url"):
        _load(_write_payload(tmp_path / "mismatch.json", mismatched))


@pytest.mark.parametrize(
    "url",
    [
        f"http://objects.invalid/object?Expires={int(TEST_EXPIRY.timestamp())}",
        f"https://user@objects.invalid/object?Expires={int(TEST_EXPIRY.timestamp())}",
        f"https://objects.invalid:444/object?Expires={int(TEST_EXPIRY.timestamp())}",
        f"https://objects.invalid/object?Expires={int(TEST_EXPIRY.timestamp())}#fragment",
    ],
)
def test_only_credential_free_https_on_standard_port_is_accepted(
    tmp_path: Path, url: str
) -> None:
    payload = _payload([b"x"])
    payload["files"][0]["signed_url"] = url
    with pytest.raises(fetcher.TransferError, match="unsafe_url"):
        _load(_write_payload(tmp_path / "unsafe-url.json", payload))


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "0.0.0.0",
        "224.0.0.1",
        "240.0.0.1",
        "192.0.2.1",
        "[::1]",
        "[fc00::1]",
        "[fe80::1]",
        "[ff02::1]",
        "[::]",
        "[::127.0.0.1]",
        "[::ffff:127.0.0.1]",
        "[::ffff:8.8.8.8]",
        "[64:ff9b::127.0.0.1]",
        "[64:ff9b::10.0.0.1]",
        "[64:ff9b:1::7f00:1]",
        "[2002:7f00:1::]",
        "[2001:0:4136:e378:8000:63bf:3fff:fdd2]",
        "[2001:4860:1:2:0:5efe:7f00:1]",
        "[2001:4860:1:2:200:5efe:800:808]",
    ],
)
def test_forbidden_ip_literals_are_rejected(tmp_path: Path, host: str) -> None:
    path = _write_payload(tmp_path / "literal.json", _payload([b"x"], host=host))
    with pytest.raises(fetcher.TransferError, match="non_public_host|ipv6_host_forbidden"):
        _load(path)


def test_ordinary_global_ipv6_is_rejected_without_translation_ambiguity(
    tmp_path: Path,
) -> None:
    host = "[2606:4700:4700::1111]"
    with pytest.raises(fetcher.TransferError, match="ipv6_host_forbidden"):
        _load(_write_payload(tmp_path / "global-v6.json", _payload([b"x"], host=host)))
    assert not fetcher._address_is_public(host[1:-1])


def test_all_urls_are_bound_to_one_declared_authority(tmp_path: Path) -> None:
    payload = _payload([b"one", b"two"])
    payload["files"][1]["signed_url"] = _signed_url("other.invalid")
    with pytest.raises(fetcher.TransferError, match="mixed_signed_authorities"):
        _load(_write_payload(tmp_path / "mixed-hosts.json", payload))


@pytest.mark.parametrize("addresses", [["127.0.0.1"], [PUBLIC_TEST_ADDRESS, "10.0.0.1"]])
def test_any_nonpublic_a_record_fails_closed(addresses: list[str]) -> None:
    def resolver(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
            for address in addresses
        ]

    with pytest.raises(fetcher.TransferError, match="non_public_dns_response"):
        fetcher._resolve_public_addresses("objects.invalid", resolver)


def test_aaaa_records_are_ignored_and_public_a_records_are_pinned() -> None:
    def mixed_resolver(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("::1", port, 0, 0),
            ),
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC_TEST_ADDRESS, port),
            ),
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:4700:4700::1111", port, 0, 0),
            ),
        ]

    assert fetcher._resolve_public_addresses("objects.invalid", mixed_resolver) == {
        PUBLIC_TEST_ADDRESS
    }

    def aaaa_only(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [
            (
                socket.AF_INET6,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("2606:4700:4700::1111", port, 0, 0),
            )
        ]

    with pytest.raises(fetcher.TransferError, match="no_public_ipv4_dns_response"):
        fetcher._resolve_public_addresses("objects.invalid", aaaa_only)


@linux_execution
def test_redirects_and_response_url_changes_fail_closed(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    redirect = urllib.error.HTTPError(
        plan.files[0].signed_url,
        302,
        "synthetic redirect",
        {},
        None,
    )
    with pytest.raises(urllib.error.HTTPError):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([redirect]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)

    redirect_response = FakeResponse(b"", plan.files[0].signed_url, status=302)
    with pytest.raises(fetcher.TransferError, match="unexpected_http_response"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([redirect_response]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)

    changed = FakeResponse(b"x", _signed_url("other.invalid"))
    with pytest.raises(fetcher.TransferError, match="redirect_or_authority_change"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([changed]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)
    assert fetcher.NoRedirectHandler().redirect_request(None, None, 302, "", {}, "https://x") is None


def test_default_tls_connection_uses_vetted_ip_but_declared_host_for_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    class RawSocket:
        def close(self) -> None:
            calls["raw_closed"] = True

    class Context:
        def wrap_socket(self, raw: Any, *, server_hostname: str) -> object:
            calls["wrapped"] = raw
            calls["sni"] = server_hostname
            return object()

    def create_connection(address: tuple[str, int], timeout: int, source: Any) -> RawSocket:
        calls["address"] = address
        calls["timeout"] = timeout
        calls["source"] = source
        return RawSocket()

    monkeypatch.setattr(fetcher.socket, "create_connection", create_connection)
    connection = object.__new__(fetcher.PinnedHTTPSConnection)
    connection._approved_addresses = (PUBLIC_TEST_ADDRESS,)
    connection.port = 443
    connection.timeout = fetcher.NETWORK_TIMEOUT_SECONDS
    connection.source_address = None
    connection._context = Context()
    connection.host = "objects.invalid"
    connection.sock = None

    connection.connect()

    assert calls["address"] == (PUBLIC_TEST_ADDRESS, 443)
    assert calls["sni"] == "objects.invalid"
    assert calls["wrapped"].__class__ is RawSocket


@linux_execution
def test_default_transfer_path_constructs_pinned_opener_from_checked_dns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    captured: dict[str, Any] = {}

    class InjectedPinnedOpener:
        def __init__(self, host: str, addresses: list[str]) -> None:
            captured["host"] = host
            captured["addresses"] = addresses

        def open(self, request: urllib.request.Request, *, timeout: int) -> FakeResponse:
            captured["timeout"] = timeout
            return FakeResponse(b"x", request.full_url)

    monkeypatch.setattr(fetcher, "PinnedHTTPSOpener", InjectedPinnedOpener)
    fetcher.execute_transfer(
        plan,
        _guard(destination),
        opener=None,
        resolver=_public_resolver,
    )

    assert captured == {
        "host": "objects.invalid",
        "addresses": [PUBLIC_TEST_ADDRESS],
        "timeout": fetcher.NETWORK_TIMEOUT_SECONDS,
    }


def test_destination_must_be_outside_repo_and_non_reparse(tmp_path: Path) -> None:
    with pytest.raises(fetcher.TransferError, match="destination_inside_repository"):
        fetcher.validate_destination(ROOT / "tests", repository_root=ROOT)

    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this Windows host")
    with pytest.raises(fetcher.TransferError, match="symlink_or_reparse_component"):
        fetcher.validate_destination(linked, repository_root=None)


def test_reparse_attribute_is_recognized_independently_of_symlink_mode() -> None:
    reparse = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
    ordinary = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0)
    assert fetcher._is_reparse(reparse)
    assert not fetcher._is_reparse(ordinary)


def test_descriptor_publish_falls_back_only_to_verified_procfd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = fetcher.StagedFile(
        item=None,
        size_bytes=1,
        descriptor=37,
        device=11,
        inode=22,
    )
    calls: list[tuple[int, bytes, int, bytes, int]] = []

    def fake_linkat(
        old_directory: int,
        old_name: bytes,
        new_directory: int,
        new_name: bytes,
        flags: int,
    ) -> int:
        calls.append((old_directory, old_name, new_directory, new_name, flags))
        if flags == fetcher.AT_EMPTY_PATH:
            ctypes.set_errno(errno.ENOENT)
            return -1
        return 0

    monkeypatch.setattr(fetcher, "_linux_linkat", lambda: fake_linkat)
    monkeypatch.setattr(
        fetcher,
        "_verified_procfd_source",
        lambda candidate: b"/proc/self/fd/37" if candidate is staged else b"unexpected",
    )

    assert fetcher._link_anonymous_file(staged, 41, "target.bin") == "PROC_FD"
    assert calls == [
        (37, b"", 41, b"target.bin", fetcher.AT_EMPTY_PATH),
        (
            fetcher.AT_FDCWD,
            b"/proc/self/fd/37",
            41,
            b"target.bin",
            fetcher.AT_SYMLINK_FOLLOW,
        ),
    ]


def test_descriptor_publish_fails_closed_when_both_methods_are_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged = fetcher.StagedFile(
        item=None,
        size_bytes=1,
        descriptor=37,
        device=11,
        inode=22,
    )

    def failing_linkat(*args: Any) -> int:
        ctypes.set_errno(errno.ENOENT)
        return -1

    monkeypatch.setattr(fetcher, "_linux_linkat", lambda: failing_linkat)
    monkeypatch.setattr(
        fetcher, "_verified_procfd_source", lambda candidate: b"/proc/self/fd/37"
    )
    with pytest.raises(fetcher.TransferError, match="descriptor_publish_failed"):
        fetcher._link_anonymous_file(staged, 41, "target.bin")


def test_symlinked_plan_is_rejected(tmp_path: Path) -> None:
    real = _write_payload(tmp_path / "real.json", _payload([b"x"]))
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(real)
    except OSError:
        pytest.skip("file symlinks are unavailable on this Windows host")
    with pytest.raises(fetcher.TransferError, match="symlink_or_reparse_component"):
        _load(linked)


@linux_execution
@pytest.mark.parametrize(
    ("body", "expected_error"),
    [
        (b"y", "object_digest_mismatch"),
        (b"", "object_size_mismatch"),
        (b"too-large", "object_larger_than_declared"),
    ],
)
def test_digest_and_both_size_directions_fail_and_clean(
    tmp_path: Path, body: bytes, expected_error: str
) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    response = FakeResponse(body, plan.files[0].signed_url)
    with pytest.raises(fetcher.TransferError, match=expected_error):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([response]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_declared_content_length_mismatch_fails_before_body_publish(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    response = FakeResponse(b"x", plan.files[0].signed_url, content_length=2)
    with pytest.raises(fetcher.TransferError, match="content_length_mismatch"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([response]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_total_size_is_independently_verified_before_publish(tmp_path: Path) -> None:
    blob = b"x"
    parsed = _load(_write_payload(tmp_path / "plan.json", _payload([blob])))
    plan = replace(parsed, total_size_bytes=parsed.total_size_bytes + 1)
    destination = tmp_path / "destination"
    destination.mkdir()
    with pytest.raises(fetcher.TransferError, match="total_size_mismatch"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([FakeResponse(blob, plan.files[0].signed_url)]),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_partial_download_failure_publishes_nothing_and_preserves_existing_files(
    tmp_path: Path,
) -> None:
    blobs = [b"first", b"second"]
    plan = _load(_write_payload(tmp_path / "plan.json", _payload(blobs)))
    destination = tmp_path / "destination"
    destination.mkdir()
    sentinel = destination / "pre-existing.txt"
    sentinel.write_bytes(b"preserve-me")
    responses = [
        FakeResponse(blobs[0], plan.files[0].signed_url),
        FakeResponse(b"broken", plan.files[1].signed_url),
    ]

    with pytest.raises(fetcher.TransferError, match="object_digest_mismatch"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener(responses),
            resolver=_public_resolver,
        )

    assert sentinel.read_bytes() == b"preserve-me"
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_api_failure_closes_anonymous_stages_without_publishing(tmp_path: Path) -> None:
    blobs = [b"first", b"second"]
    plan = _load(_write_payload(tmp_path / "plan.json", _payload(blobs)))
    destination = tmp_path / "destination"
    destination.mkdir()
    api_failure = urllib.error.URLError("synthetic service failure")

    with pytest.raises(urllib.error.URLError):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener(
                [FakeResponse(blobs[0], plan.files[0].signed_url), api_failure]
            ),
            resolver=_public_resolver,
        )
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_preexisting_target_is_never_opened_or_overwritten(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"new"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    target = destination / plan.files[0].target_name
    target.write_bytes(b"old")
    opener = FakeOpener([FakeResponse(b"new", plan.files[0].signed_url)])

    with pytest.raises(fetcher.TransferError, match="target_collision"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=opener,
            resolver=_public_resolver,
        )
    assert target.read_bytes() == b"old"
    assert opener.requests == []
    assert not list(destination.glob(".secure-wgs-*.part"))


@linux_execution
def test_publish_race_never_overwrites_or_deletes_and_leaves_no_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blobs = [b"verified-first", b"verified-second"]
    plan = _load(_write_payload(tmp_path / "plan.json", _payload(blobs)))
    destination = tmp_path / "destination"
    destination.mkdir()
    original_link = fetcher._link_anonymous_file

    def racing_link(
        staged: fetcher.StagedFile, directory_descriptor: int, name: str
    ) -> None:
        if name == plan.files[1].target_name:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_descriptor,
            )
            try:
                os.write(descriptor, b"race-winner")
            finally:
                os.close(descriptor)
        original_link(staged, directory_descriptor, name)

    monkeypatch.setattr(fetcher, "_link_anonymous_file", racing_link)
    with pytest.raises(fetcher.TransferError, match="publish_race"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener(
                [
                    FakeResponse(blob, plan.files[index].signed_url)
                    for index, blob in enumerate(blobs)
                ]
            ),
            resolver=_public_resolver,
        )
    assert (destination / plan.files[0].target_name).read_bytes() == blobs[0]
    assert (destination / plan.files[1].target_name).read_bytes() == b"race-winner"
    assert not (destination / fetcher.COMPLETION_MARKER).exists()
    assert not list(destination.glob(".secure-wgs-*.part"))


@linux_execution
def test_destination_identity_is_rechecked_immediately_before_publish(
    tmp_path: Path
) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    guard = _guard(destination)

    destination.rename(tmp_path / "moved-original")
    destination.mkdir()
    with pytest.raises(fetcher.TransferError, match="destination_changed"):
        guard.revalidate()

    # Use a fresh guarded directory and fail the check intentionally adjacent
    # to descriptor-relative publication, after descriptor open and staging.
    destination.rmdir()
    destination.mkdir()
    fresh = _guard(destination)

    class GuardProbe:
        def __init__(self) -> None:
            self.path = fresh.path
            self.device = fresh.device
            self.inode = fresh.inode
            self.repository_root = fresh.repository_root
            self.calls = 0

        def revalidate(self) -> None:
            self.calls += 1
            if self.calls == 4:
                raise fetcher.TransferError("destination_changed")
            fresh.revalidate()

    probe = GuardProbe()
    with pytest.raises(fetcher.TransferError, match="destination_changed"):
        fetcher.execute_transfer(
            plan,
            probe,  # type: ignore[arg-type]
            opener=FakeOpener([FakeResponse(b"x", plan.files[0].signed_url)]),
            resolver=_public_resolver,
        )
    assert probe.calls == 4
    _assert_no_transfer_artifacts(destination)


def test_expired_in_memory_plan_fails_before_platform_dns_or_writes(
    tmp_path: Path,
) -> None:
    parsed = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    expired_at = TEST_NOW - timedelta(seconds=1)
    expired_file = replace(parsed.files[0], expires_utc=expired_at)
    plan = replace(parsed, expires_utc=expired_at, files=(expired_file,))
    destination = tmp_path / "destination"
    destination.mkdir()
    resolver_called = False

    def forbidden_resolver(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        nonlocal resolver_called
        resolver_called = True
        raise AssertionError("expired plans must not perform DNS")

    with pytest.raises(fetcher.TransferError, match="transfer_plan_expired"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([]),
            resolver=forbidden_resolver,
            clock=lambda: TEST_NOW,
        )
    assert not resolver_called
    _assert_no_transfer_artifacts(destination)


@pytest.mark.skipif(LINUX_EXECUTION, reason="non-Linux fail-closed policy test")
def test_non_linux_execution_fails_before_dns_network_or_writes(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    resolver_called = False

    def forbidden_resolver(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        nonlocal resolver_called
        resolver_called = True
        raise AssertionError("non-Linux execution must not perform DNS")

    with pytest.raises(
        fetcher.TransferError, match="execution_requires_linux_descriptor_support"
    ):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([]),
            resolver=forbidden_resolver,
            clock=lambda: TEST_NOW,
        )
    assert not resolver_called
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_expiry_after_download_prevents_any_publication(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    calls = 0

    def advancing_clock() -> datetime:
        nonlocal calls
        calls += 1
        return plan.expires_utc if calls >= 4 else TEST_NOW

    with pytest.raises(fetcher.TransferError, match="transfer_plan_expired"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([FakeResponse(b"x", plan.files[0].signed_url)]),
            resolver=_public_resolver,
            clock=advancing_clock,
        )
    assert calls == 4
    _assert_no_transfer_artifacts(destination)


@linux_execution
def test_expiry_immediately_before_completion_leaves_no_marker(tmp_path: Path) -> None:
    blob = b"x"
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([blob])))
    destination = tmp_path / "destination"
    destination.mkdir()
    calls = 0

    def advancing_clock() -> datetime:
        nonlocal calls
        calls += 1
        return plan.expires_utc if calls >= 8 else TEST_NOW

    with pytest.raises(fetcher.TransferError, match="transfer_plan_expired"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([FakeResponse(blob, plan.files[0].signed_url)]),
            resolver=_public_resolver,
            clock=advancing_clock,
        )
    assert calls == 8
    assert (destination / plan.files[0].target_name).read_bytes() == blob
    assert not (destination / fetcher.COMPLETION_MARKER).exists()


@linux_execution
def test_marker_collision_fails_before_dns_and_is_preserved(tmp_path: Path) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / fetcher.COMPLETION_MARKER
    marker.write_bytes(b"operator-owned-marker")
    opener = FakeOpener([FakeResponse(b"x", plan.files[0].signed_url)])

    with pytest.raises(fetcher.TransferError, match="target_collision"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=opener,
            resolver=_public_resolver,
            clock=lambda: TEST_NOW,
        )
    assert opener.requests == []
    assert marker.read_bytes() == b"operator-owned-marker"
    assert not list(destination.glob("SAMPLE*.fastq.gz"))


@linux_execution
def test_failure_cleanup_never_calls_path_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _load(_write_payload(tmp_path / "plan.json", _payload([b"x"])))
    destination = tmp_path / "destination"
    destination.mkdir()
    deletion_calls: list[str] = []

    def forbidden_delete(*args: Any, **kwargs: Any) -> None:
        deletion_calls.append("called")
        raise AssertionError("transfer cleanup must never delete a pathname")

    monkeypatch.setattr(fetcher.os, "unlink", forbidden_delete)
    monkeypatch.setattr(fetcher.os, "remove", forbidden_delete)
    with pytest.raises(fetcher.TransferError, match="object_digest_mismatch"):
        fetcher.execute_transfer(
            plan,
            _guard(destination),
            opener=FakeOpener([FakeResponse(b"y", plan.files[0].signed_url)]),
            resolver=_public_resolver,
            clock=lambda: TEST_NOW,
        )
    assert deletion_calls == []
    _assert_no_transfer_artifacts(destination)
    source = SCRIPT.read_text(encoding="utf-8")
    assert ".unlink(" not in source
    assert "os.remove(" not in source


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_help_and_read_only_cli_modes_are_truthful_and_nonmutating(tmp_path: Path) -> None:
    help_result = _run_cli("--help")
    assert help_result.returncode == 0
    assert "--validate-only" in help_result.stdout
    assert "--plan-only" in help_result.stdout
    assert "Linux-only" in help_result.stdout
    assert "O_TMPFILE" in help_result.stdout
    assert "descriptor-based linkat" in help_result.stdout
    assert help_result.stderr == ""

    plan_path = _write_payload(tmp_path / "plan.json", _payload([b"x"]))
    destination = tmp_path / "destination"
    destination.mkdir()
    sentinel = destination / "existing.txt"
    sentinel.write_bytes(b"unchanged")
    before = {path.name: path.read_bytes() for path in destination.iterdir()}

    validate = _run_cli("--plan", str(plan_path), "--validate-only")
    assert validate.returncode == 0
    assert json.loads(validate.stdout) == {"file_count": 1, "status": "valid"}
    assert validate.stderr == ""

    planned = _run_cli(
        "--plan",
        str(plan_path),
        "--destination",
        str(destination),
        "--plan-only",
    )
    assert planned.returncode == 0
    assert json.loads(planned.stdout) == {"file_count": 1, "status": "ready"}
    assert planned.stderr == ""
    after = {path.name: path.read_bytes() for path in destination.iterdir()}
    assert after == before


def test_plan_only_rejects_completion_marker_collision_without_writes(
    tmp_path: Path,
) -> None:
    plan_path = _write_payload(tmp_path / "plan.json", _payload([b"x"]))
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / fetcher.COMPLETION_MARKER
    marker.write_bytes(b"operator-owned-marker")

    result = _run_cli(
        "--plan",
        str(plan_path),
        "--destination",
        str(destination),
        "--plan-only",
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "secure_wgs_transfer=failed_closed"
    assert marker.read_bytes() == b"operator-owned-marker"


def test_cli_failures_are_redacted_and_default_mode_requires_destination(tmp_path: Path) -> None:
    secret_marker = "SYNTHETIC_SECRET_MUST_NOT_LEAK"
    invalid = tmp_path / "private-plan.json"
    invalid.write_text(json.dumps({"secret": secret_marker}), encoding="utf-8")
    result = _run_cli("--plan", str(invalid), "--validate-only")
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "secure_wgs_transfer=failed_closed"
    assert secret_marker not in result.stderr
    assert str(invalid) not in result.stderr

    valid = _write_payload(tmp_path / "valid.json", _payload([b"x"]))
    no_destination = _run_cli("--plan", str(valid))
    assert no_destination.returncode == 2
    assert no_destination.stdout == ""
    assert no_destination.stderr.strip() == "secure_wgs_transfer=failed_closed"
