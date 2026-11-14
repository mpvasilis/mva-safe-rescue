#!/usr/bin/env python3
"""Fail-closed retrieval of a short-lived, private signed-URL plan.

Only generic transfer metadata is emitted.  Signed URLs, target names, response
bodies, filesystem paths, and exception details are never written to stdout or
stderr.  The default command remains compatible with the original
``--plan ... --destination ...`` interface.  Validation and planning are
cross-platform and read-only; real transfer execution requires Linux support
for anonymous ``O_TMPFILE`` staging and descriptor-based ``linkat`` publication.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


SCHEMA = "secure-wgs-signed-transfer-plan/v1"
CLASSIFICATION = "SECRET_CONTROLLED_SIGNED_URLS_DO_NOT_COMMIT"
TARGET = re.compile(r"^SAMPLE[0-9]{2}_L[0-9]{3}_R[12]\.fastq\.gz$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Deliberately finite, explicit limits.  They comfortably cover the challenge
# bundle while preventing a plan from becoming an unbounded parser/download job.
MAX_PLAN_BYTES = 1 * 1024 * 1024
MAX_FILE_COUNT = 64
MAX_FILE_BYTES = 256 * 1024**3
MAX_TOTAL_BYTES = 1 * 1024**4
MAX_URL_CHARS = 32 * 1024
READ_CHUNK_BYTES = 8 * 1024 * 1024
NETWORK_TIMEOUT_SECONDS = 120
COMPLETION_MARKER = "TRANSFER_COMPLETE.json"
COMPLETION_SCHEMA = "secure-wgs-transfer-completion/v1"
AT_EMPTY_PATH = 0x1000
AT_FDCWD = -100
AT_SYMLINK_FOLLOW = 0x400
PROC_SUPER_MAGIC = 0x9FA0

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "classification",
        "created_utc",
        "source",
        "token_persisted",
        "expires_utc",
        "file_count",
        "files",
    }
)
SOURCE_FIELDS = frozenset({"provider", "repo_id", "revision"})
FILE_FIELDS = frozenset(
    {"target_name", "sha256", "size_bytes", "signed_url", "expires_utc"}
)
class TransferError(Exception):
    """Internal validation/transfer failure whose detail must never be emitted."""


class RedactedArgumentParser(argparse.ArgumentParser):
    """Keep malformed command lines from reflecting private path arguments."""

    def error(self, message: str) -> None:  # noqa: ARG002
        print("secure_wgs_transfer=failed_closed", file=sys.stderr)
        raise SystemExit(2)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disable every redirect; a changed authority must always fail closed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        return None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection whose socket can use only pre-vetted public addresses."""

    def __init__(
        self,
        declared_host: str,
        addresses: Sequence[str],
        *,
        port: int = 443,
        timeout: int = NETWORK_TIMEOUT_SECONDS,
    ) -> None:
        if not addresses or any(not _address_is_public(address) for address in addresses):
            raise TransferError("pinned_addresses_must_be_public_ipv4")
        super().__init__(
            declared_host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._approved_addresses = tuple(addresses)

    def connect(self) -> None:
        last_error: OSError | None = None
        for address in self._approved_addresses:
            raw_socket: socket.socket | None = None
            try:
                # address is an already-parsed IP literal, so this cannot send
                # the declared hostname through a second, unvetted DNS lookup.
                raw_socket = socket.create_connection(
                    (address, self.port), self.timeout, self.source_address
                )
                self.sock = self._context.wrap_socket(
                    raw_socket,
                    server_hostname=self.host,
                )
                return
            except OSError as exc:
                last_error = exc
                if raw_socket is not None:
                    try:
                        raw_socket.close()
                    except OSError:
                        pass
        raise TransferError("pinned_connection_failure") from last_error


class PinnedHTTPSResponse:
    """Small context-manager adapter with urllib-compatible response methods."""

    def __init__(
        self,
        response: http.client.HTTPResponse,
        connection: PinnedHTTPSConnection,
        declared_url: str,
    ) -> None:
        self._response = response
        self._connection = connection
        self._declared_url = declared_url
        self.status = response.status
        self.headers = response.headers

    def __enter__(self) -> PinnedHTTPSResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()

    def geturl(self) -> str:
        return self._declared_url

    def read(self, size: int) -> bytes:
        return self._response.read(size)


class PinnedHTTPSOpener:
    """One-request opener that never redirects and never re-resolves its host."""

    def __init__(self, declared_host: str, addresses: Sequence[str]) -> None:
        self._declared_host = declared_host
        self._addresses = tuple(addresses)

    def open(self, request: urllib.request.Request, *, timeout: int) -> PinnedHTTPSResponse:
        parsed = urllib.parse.urlsplit(request.full_url)
        host = _normalize_host(parsed.hostname)
        port = parsed.port or 443
        if (
            parsed.scheme != "https"
            or host != self._declared_host
            or port != 443
            or request.get_method() != "GET"
        ):
            raise TransferError("pinned_request_mismatch")
        connection = PinnedHTTPSConnection(
            self._declared_host,
            self._addresses,
            port=port,
            timeout=timeout,
        )
        selector = parsed.path or "/"
        if parsed.query:
            selector += "?" + parsed.query
        try:
            connection.request(
                "GET",
                selector,
                headers=dict(request.header_items()),
            )
            response = connection.getresponse()
        except Exception:
            connection.close()
            raise
        return PinnedHTTPSResponse(response, connection, request.full_url)


@dataclass(frozen=True)
class TransferFile:
    target_name: str
    sha256: str
    size_bytes: int
    signed_url: str
    expires_utc: datetime
    declared_host: str


@dataclass(frozen=True)
class TransferPlan:
    created_utc: datetime
    expires_utc: datetime
    files: tuple[TransferFile, ...]
    total_size_bytes: int
    declared_host: str


@dataclass(frozen=True)
class DestinationGuard:
    path: Path
    device: int
    inode: int
    repository_root: Path | None

    def revalidate(self) -> None:
        """Recheck destination identity, topology, and containment before publish."""

        _assert_no_reparse_components(self.path)
        current = self.path.resolve(strict=True)
        if current != self.path or not current.is_dir():
            raise TransferError("destination_changed")
        current_stat = os.stat(current, follow_symlinks=False)
        if (current_stat.st_dev, current_stat.st_ino) != (self.device, self.inode):
            raise TransferError("destination_changed")
        if self.repository_root is not None and _is_within(current, self.repository_root):
            raise TransferError("destination_inside_repository")


@dataclass
class StagedFile:
    """A verified anonymous inode retained by an open descriptor."""

    item: TransferFile | None
    size_bytes: int
    descriptor: int
    device: int
    inode: int
    closed: bool = False


def _discover_repository_root(start: Path) -> Path | None:
    """Return the enclosing checkout root, if this copy still lives in a checkout."""

    absolute = start.resolve(strict=False)
    for candidate in (absolute.parent, *absolute.parents):
        if (candidate / ".git").exists():
            return candidate.resolve(strict=True)
    return None


REPOSITORY_ROOT = _discover_repository_root(Path(__file__))


def _fail() -> int:
    print("secure_wgs_transfer=failed_closed", file=sys.stderr)
    return 2


def _reject_constant(value: str) -> None:
    raise TransferError("invalid_json_constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransferError("duplicate_json_key")
        result[key] = value
    return result


def _load_bounded_json(path: Path) -> Mapping[str, Any]:
    _assert_no_reparse_components(path)
    if not path.is_file():
        raise TransferError("plan_not_regular_file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_PLAN_BYTES:
        raise TransferError("plan_size_out_of_bounds")
    with path.open("rb") as handle:
        raw = handle.read(MAX_PLAN_BYTES + 1)
    if len(raw) != size or len(raw) > MAX_PLAN_BYTES:
        raise TransferError("plan_changed_or_too_large")
    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransferError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise TransferError("plan_not_object")
    return payload


def _require_exact_fields(value: Mapping[str, Any], expected: frozenset[str]) -> None:
    if frozenset(value) != expected:
        raise TransferError("missing_or_unknown_fields")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise TransferError("invalid_timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TransferError("invalid_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransferError("naive_timestamp")
    return parsed.astimezone(timezone.utc)


def _require_bounded_text(value: Any, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TransferError("invalid_text_field")
    return value


def _normalize_host(host: str | None) -> str:
    if not host or len(host) > 253:
        raise TransferError("invalid_host")
    try:
        normalized = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise TransferError("invalid_host") from exc
    if not normalized or any(len(label) > 63 or not label for label in normalized.split(".")):
        raise TransferError("invalid_host")
    return normalized


def _address_is_public(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    # IPv6 cannot be made unambiguous in the presence of RFC 6052
    # network-specific translation prefixes.  This fetcher therefore pins and
    # connects only ordinary public IPv4 addresses.
    if not isinstance(parsed, ipaddress.IPv4Address):
        return False
    return bool(
        parsed.is_global
        and not parsed.is_private
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_multicast
        and not parsed.is_reserved
        and not parsed.is_unspecified
    )


def _validate_url(value: Any) -> tuple[str, urllib.parse.SplitResult]:
    if not isinstance(value, str) or not value or len(value) > MAX_URL_CHARS:
        raise TransferError("invalid_url")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise TransferError("invalid_url") from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise TransferError("unsafe_url")
    host = _normalize_host(parsed.hostname)
    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if isinstance(literal, ipaddress.IPv6Address):
        raise TransferError("ipv6_host_forbidden")
    if literal is not None and not _address_is_public(str(literal)):
        raise TransferError("non_public_host")
    return host, parsed


def _machine_url_expiry(parsed: urllib.parse.SplitResult) -> datetime:
    try:
        pairs = urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=256,
        )
    except (ValueError, TypeError) as exc:
        raise TransferError("invalid_url_query") from exc
    query: dict[str, str] = {}
    for raw_key, raw_value in pairs:
        key = raw_key.lower()
        if key in query:
            raise TransferError("duplicate_url_query_key")
        query[key] = raw_value

    if "expires" in query:
        try:
            epoch = int(query["expires"])
            if str(epoch) != query["expires"]:
                raise ValueError
            return datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise TransferError("invalid_url_expiry") from exc

    if "x-amz-date" in query and "x-amz-expires" in query:
        try:
            issued = datetime.strptime(query["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
            lifetime = int(query["x-amz-expires"])
        except ValueError as exc:
            raise TransferError("invalid_url_expiry") from exc
        if lifetime <= 0 or lifetime > 7 * 24 * 60 * 60:
            raise TransferError("invalid_url_expiry")
        return issued + timedelta(seconds=lifetime)

    raise TransferError("missing_url_expiry")


def load_transfer_plan(path: Path, *, now: datetime | None = None) -> TransferPlan:
    """Parse and validate a plan without performing DNS, network, or writes."""

    # Keep the lexical path until after the reparse-component check; resolving
    # first would hide a symlinked plan or parent directory.
    payload = _load_bounded_json(Path(os.path.abspath(os.fspath(path))))
    _require_exact_fields(payload, TOP_LEVEL_FIELDS)
    if payload["schema"] != SCHEMA:
        raise TransferError("wrong_schema")
    if payload["classification"] != CLASSIFICATION:
        raise TransferError("wrong_classification")
    if payload["token_persisted"] is not False:
        raise TransferError("token_persisted")

    source = payload["source"]
    if not isinstance(source, dict):
        raise TransferError("invalid_source")
    _require_exact_fields(source, SOURCE_FIELDS)
    if source["provider"] != "Hugging Face":
        raise TransferError("unexpected_provider")
    _require_bounded_text(source["repo_id"], maximum=512)
    _require_bounded_text(source["revision"], maximum=512)

    created = _parse_timestamp(payload["created_utc"])
    plan_expiry = _parse_timestamp(payload["expires_utc"])
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if created > plan_expiry or plan_expiry <= current:
        raise TransferError("expired_or_incoherent_plan")

    raw_files = payload["files"]
    file_count = payload["file_count"]
    if type(file_count) is not int or not 1 <= file_count <= MAX_FILE_COUNT:
        raise TransferError("invalid_file_count")
    if not isinstance(raw_files, list) or len(raw_files) != file_count:
        raise TransferError("file_count_mismatch")

    files: list[TransferFile] = []
    names: set[str] = set()
    total_size = 0
    declared_host: str | None = None
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise TransferError("invalid_file_entry")
        _require_exact_fields(raw_file, FILE_FIELDS)
        name = raw_file["target_name"]
        checksum = raw_file["sha256"]
        size = raw_file["size_bytes"]
        if not isinstance(name, str) or not TARGET.fullmatch(name) or name in names:
            raise TransferError("invalid_or_duplicate_target")
        if not isinstance(checksum, str) or not SHA256.fullmatch(checksum):
            raise TransferError("invalid_digest")
        if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
            raise TransferError("file_size_out_of_bounds")
        total_size += size
        if total_size > MAX_TOTAL_BYTES:
            raise TransferError("total_size_out_of_bounds")

        host, parsed_url = _validate_url(raw_file["signed_url"])
        file_expiry = _parse_timestamp(raw_file["expires_utc"])
        if file_expiry <= current or _machine_url_expiry(parsed_url) != file_expiry:
            raise TransferError("expired_or_mismatched_url")
        if declared_host is None:
            declared_host = host
        elif declared_host != host:
            raise TransferError("mixed_signed_authorities")

        names.add(name)
        files.append(
            TransferFile(
                target_name=name,
                sha256=checksum,
                size_bytes=size,
                signed_url=raw_file["signed_url"],
                expires_utc=file_expiry,
                declared_host=host,
            )
        )

    if not files or declared_host is None or plan_expiry != min(item.expires_utc for item in files):
        raise TransferError("invalid_plan_expiry")
    return TransferPlan(
        created_utc=created,
        expires_utc=plan_expiry,
        files=tuple(files),
        total_size_bytes=total_size,
        declared_host=declared_host,
    )


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(stat_result.st_mode) or bool(attributes & reparse_flag)


def _assert_no_reparse_components(path: Path) -> None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    chain = list(reversed((absolute, *absolute.parents)))
    for component in chain:
        try:
            component_stat = os.lstat(component)
        except OSError as exc:
            raise TransferError("missing_path_component") from exc
        if _is_reparse(component_stat):
            raise TransferError("symlink_or_reparse_component")


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath(
            [os.path.normcase(str(candidate)), os.path.normcase(str(parent))]
        ) == os.path.normcase(str(parent))
    except ValueError:
        return False


def validate_destination(
    destination: Path, *, repository_root: Path | None = REPOSITORY_ROOT
) -> DestinationGuard:
    """Validate an existing destination without creating or modifying anything."""

    lexical = Path(os.path.abspath(os.fspath(destination)))
    _assert_no_reparse_components(lexical)
    resolved = lexical.resolve(strict=True)
    if not resolved.is_dir():
        raise TransferError("destination_not_directory")
    normalized_repo = repository_root.resolve(strict=True) if repository_root is not None else None
    if normalized_repo is not None and _is_within(resolved, normalized_repo):
        raise TransferError("destination_inside_repository")
    destination_stat = os.stat(resolved, follow_symlinks=False)
    return DestinationGuard(
        path=resolved,
        device=destination_stat.st_dev,
        inode=destination_stat.st_ino,
        repository_root=normalized_repo,
    )


def _resolve_public_addresses(
    host: str,
    resolver: Callable[..., Sequence[tuple[Any, ...]]] = socket.getaddrinfo,
) -> frozenset[str]:
    try:
        records = resolver(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise TransferError("dns_failure") from exc
    addresses: set[str] = set()
    for record in records:
        try:
            family = record[0]
            address = record[4][0]
        except (IndexError, TypeError) as exc:
            raise TransferError("invalid_dns_response") from exc
        if family == socket.AF_INET6:
            # AAAA records are deliberately ignored: no IPv6 address is ever
            # considered for a connection.
            continue
        if family != socket.AF_INET or not isinstance(address, str):
            raise TransferError("invalid_dns_response")
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise TransferError("invalid_dns_response") from exc
        if not isinstance(parsed, ipaddress.IPv4Address) or not _address_is_public(address):
            raise TransferError("non_public_dns_response")
        addresses.add(str(parsed))
    if not addresses:
        raise TransferError("no_public_ipv4_dns_response")
    return frozenset(addresses)


def _same_signed_url(observed: str, declared: str) -> bool:
    try:
        observed_parts = urllib.parse.urlsplit(observed)
        declared_parts = urllib.parse.urlsplit(declared)
        observed_port = observed_parts.port or 443
        declared_port = declared_parts.port or 443
        return (
            observed_parts.scheme == "https"
            and declared_parts.scheme == "https"
            and _normalize_host(observed_parts.hostname) == _normalize_host(declared_parts.hostname)
            and observed_port == declared_port
            and observed_parts.path == declared_parts.path
            and observed_parts.query == declared_parts.query
            and not observed_parts.fragment
        )
    except (TransferError, ValueError):
        return False


def _response_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if headers is not None else None
    if value is None:
        return None
    try:
        length = int(value)
    except (TypeError, ValueError) as exc:
        raise TransferError("invalid_content_length") from exc
    if length < 0:
        raise TransferError("invalid_content_length")
    return length


def _path_exists_without_following(path: Path) -> bool:
    return os.path.lexists(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clock_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TransferError("invalid_execution_clock")
    return value.astimezone(timezone.utc)


def _assert_plan_unexpired(plan: TransferPlan, clock: Callable[[], datetime]) -> None:
    current = _clock_now(clock)
    if plan.expires_utc <= current or any(item.expires_utc <= current for item in plan.files):
        raise TransferError("transfer_plan_expired")


def _require_linux_descriptor_execution() -> None:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise TransferError("execution_requires_linux_descriptor_support")
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_TMPFILE")
    if any(not hasattr(os, name) for name in required_flags):
        raise TransferError("linux_descriptor_primitive_unavailable")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise TransferError("linux_dirfd_primitive_unavailable")
    if os.stat not in os.supports_follow_symlinks:
        raise TransferError("linux_nofollow_stat_unavailable")
    try:
        linkat = getattr(ctypes.CDLL(None, use_errno=True), "linkat")
    except (AttributeError, OSError) as exc:
        raise TransferError("linux_linkat_unavailable") from exc
    if linkat is None:
        raise TransferError("linux_linkat_unavailable")


def _open_guarded_directory(guard: DestinationGuard) -> int:
    guard.revalidate()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(guard.path, flags)
    except OSError as exc:
        raise TransferError("destination_descriptor_open_failed") from exc
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISDIR(identity.st_mode):
            raise TransferError("destination_descriptor_not_directory")
        if (identity.st_dev, identity.st_ino) != (guard.device, guard.inode):
            raise TransferError("destination_descriptor_identity_changed")
        guard.revalidate()
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_anonymous_stage(directory_descriptor: int) -> int:
    flags = os.O_TMPFILE | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(".", flags, stat.S_IRUSR | stat.S_IWUSR, dir_fd=directory_descriptor)
    except OSError as exc:
        raise TransferError("anonymous_staging_unavailable") from exc
    try:
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 0:
            raise TransferError("anonymous_staging_identity_invalid")
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _probe_anonymous_staging(directory_descriptor: int) -> None:
    descriptor = _open_anonymous_stage(directory_descriptor)
    os.close(descriptor)


def _directory_entry_stat(directory_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise TransferError("destination_entry_stat_failed") from exc


def _require_entry_absent(directory_descriptor: int, name: str) -> None:
    if _directory_entry_stat(directory_descriptor, name) is not None:
        raise TransferError("target_collision")


def _linux_linkat() -> Any:
    try:
        linkat = ctypes.CDLL(None, use_errno=True).linkat
    except (AttributeError, OSError) as exc:
        raise TransferError("linux_linkat_unavailable") from exc
    linkat.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    linkat.restype = ctypes.c_int
    return linkat


def _linux_fstatfs_type(descriptor: int) -> int:
    """Return the Linux filesystem magic for an open descriptor."""

    try:
        fstatfs = ctypes.CDLL(None, use_errno=True).fstatfs
    except (AttributeError, OSError) as exc:
        raise TransferError("linux_fstatfs_unavailable") from exc
    fstatfs.argtypes = [ctypes.c_int, ctypes.c_void_p]
    fstatfs.restype = ctypes.c_int
    # The filesystem type is the first native long in every Linux statfs ABI.
    # A deliberately oversized buffer avoids depending on the remaining,
    # architecture-specific fields.
    result_buffer = ctypes.create_string_buffer(256)
    ctypes.set_errno(0)
    if fstatfs(descriptor, ctypes.byref(result_buffer)) != 0:
        error_number = ctypes.get_errno()
        raise TransferError("linux_fstatfs_failed") from OSError(
            error_number, "fstatfs"
        )
    return ctypes.c_long.from_buffer(result_buffer).value


def _verified_procfd_source(staged: StagedFile) -> bytes:
    """Return a procfs descriptor path only after exact inode verification."""

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        proc_descriptor = os.open("/proc", flags)
    except OSError as exc:
        raise TransferError("procfs_unavailable") from exc
    try:
        if _linux_fstatfs_type(proc_descriptor) != PROC_SUPER_MAGIC:
            raise TransferError("procfs_mount_required")
    finally:
        os.close(proc_descriptor)

    proc_path = f"/proc/self/fd/{staged.descriptor}"
    try:
        link_identity = os.lstat(proc_path)
        source_identity = os.stat(proc_path, follow_symlinks=True)
        descriptor_identity = os.fstat(staged.descriptor)
    except OSError as exc:
        raise TransferError("procfd_identity_unavailable") from exc
    if not stat.S_ISLNK(link_identity.st_mode):
        raise TransferError("procfd_source_not_symlink")
    if (
        not stat.S_ISREG(source_identity.st_mode)
        or source_identity.st_nlink != 0
        or (source_identity.st_dev, source_identity.st_ino)
        != (descriptor_identity.st_dev, descriptor_identity.st_ino)
        or (descriptor_identity.st_dev, descriptor_identity.st_ino)
        != (staged.device, staged.inode)
    ):
        raise TransferError("procfd_identity_mismatch")
    return os.fsencode(proc_path)


def _link_anonymous_file(
    staged: StagedFile, directory_descriptor: int, name: str
) -> str:
    """Publish an anonymous inode without ever creating a named staging file."""

    linkat = _linux_linkat()
    ctypes.set_errno(0)
    result = linkat(
        staged.descriptor,
        b"",
        directory_descriptor,
        os.fsencode(name),
        AT_EMPTY_PATH,
    )
    if result == 0:
        return "AT_EMPTY_PATH"
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise TransferError("publish_race")

    # linkat(AT_EMPTY_PATH) requires CAP_DAC_READ_SEARCH on Linux.  The open(2)
    # and linkat(2) interfaces document a capability-free alternative for an
    # O_TMPFILE descriptor: follow its verified /proc/self/fd magic link while
    # keeping the destination relative to the retained guarded directory fd.
    proc_source = _verified_procfd_source(staged)
    ctypes.set_errno(0)
    result = linkat(
        AT_FDCWD,
        proc_source,
        directory_descriptor,
        os.fsencode(name),
        AT_SYMLINK_FOLLOW,
    )
    if result == 0:
        return "PROC_FD"
    proc_error_number = ctypes.get_errno()
    if proc_error_number == errno.EEXIST:
        raise TransferError("publish_race")
    raise TransferError("descriptor_publish_failed") from OSError(
        proc_error_number, "linkat"
    )


def _verify_published_identity(
    staged: StagedFile, directory_descriptor: int, name: str
) -> None:
    identity = _directory_entry_stat(directory_descriptor, name)
    if identity is None or _is_reparse(identity) or not stat.S_ISREG(identity.st_mode):
        raise TransferError("published_identity_invalid")
    if (
        (identity.st_dev, identity.st_ino) != (staged.device, staged.inode)
        or identity.st_nlink != 1
    ):
        raise TransferError("published_identity_changed")


def _close_staged(staged: StagedFile) -> None:
    if staged.closed:
        return
    try:
        os.close(staged.descriptor)
    finally:
        staged.closed = True


def _stage_bytes(data: bytes, directory_descriptor: int) -> StagedFile:
    descriptor = _open_anonymous_stage(directory_descriptor)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise TransferError("anonymous_stage_write_failed")
            view = view[written:]
        os.fsync(descriptor)
        identity = os.fstat(descriptor)
        if identity.st_size != len(data) or identity.st_nlink != 0:
            raise TransferError("anonymous_stage_verification_failed")
        return StagedFile(
            item=None,
            size_bytes=len(data),
            descriptor=descriptor,
            device=identity.st_dev,
            inode=identity.st_ino,
        )
    except Exception:
        os.close(descriptor)
        raise


def _download_to_anonymous(
    plan: TransferPlan,
    item: TransferFile,
    guard: DestinationGuard,
    directory_descriptor: int,
    *,
    opener: Any | None,
    resolver: Callable[..., Sequence[tuple[Any, ...]]],
    clock: Callable[[], datetime],
) -> StagedFile:
    """Download one object into a verified anonymous destination inode."""

    _assert_plan_unexpired(plan, clock)
    guard.revalidate()
    descriptor = _open_anonymous_stage(directory_descriptor)
    digest = hashlib.sha256()
    observed_size = 0
    try:
        approved_addresses = _resolve_public_addresses(item.declared_host, resolver)
        _assert_plan_unexpired(plan, clock)
        request = urllib.request.Request(
            item.signed_url,
            headers={"User-Agent": "secure-wgs/3", "Accept-Encoding": "identity"},
            method="GET",
        )
        active_opener = opener or PinnedHTTPSOpener(
            item.declared_host, sorted(approved_addresses)
        )
        with os.fdopen(os.dup(descriptor), "wb") as output:
            with active_opener.open(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                status_code = getattr(response, "status", 200)
                observed_url = response.geturl()
                if status_code != 200 or not isinstance(observed_url, str):
                    raise TransferError("unexpected_http_response")
                if not _same_signed_url(observed_url, item.signed_url):
                    raise TransferError("redirect_or_authority_change")
                if _normalize_host(urllib.parse.urlsplit(observed_url).hostname) != item.declared_host:
                    raise TransferError("response_host_mismatch")
                declared_length = _response_content_length(response)
                if declared_length is not None and declared_length != item.size_bytes:
                    raise TransferError("content_length_mismatch")
                while True:
                    block = response.read(READ_CHUNK_BYTES)
                    if not block:
                        break
                    if not isinstance(block, (bytes, bytearray)):
                        raise TransferError("invalid_response_body")
                    observed_size += len(block)
                    if observed_size > item.size_bytes:
                        raise TransferError("object_larger_than_declared")
                    output.write(block)
                    digest.update(block)
            output.flush()
            os.fsync(output.fileno())
        _assert_plan_unexpired(plan, clock)
        if observed_size != item.size_bytes:
            raise TransferError("object_size_mismatch")
        if digest.hexdigest() != item.sha256:
            raise TransferError("object_digest_mismatch")
        identity = os.fstat(descriptor)
        if (
            not stat.S_ISREG(identity.st_mode)
            or identity.st_nlink != 0
            or identity.st_size != observed_size
        ):
            raise TransferError("anonymous_stage_verification_failed")
        return StagedFile(
            item=item,
            size_bytes=observed_size,
            descriptor=descriptor,
            device=identity.st_dev,
            inode=identity.st_ino,
        )
    except Exception:
        os.close(descriptor)
        raise


def _completion_marker_bytes(plan: TransferPlan) -> bytes:
    payload = {
        "file_count": len(plan.files),
        "schema": COMPLETION_SCHEMA,
        "status": "COMPLETE",
        "target_sha256": [item.sha256 for item in plan.files],
        "total_size_bytes": plan.total_size_bytes,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def execute_transfer(
    plan: TransferPlan,
    guard: DestinationGuard,
    *,
    opener: Any | None = None,
    resolver: Callable[..., Sequence[tuple[Any, ...]]] = socket.getaddrinfo,
    clock: Callable[[], datetime] = _utc_now,
) -> int:
    """Stage, verify, then descriptor-publish a Linux transfer plan."""

    _assert_plan_unexpired(plan, clock)
    _require_linux_descriptor_execution()
    directory_descriptor = -1
    staged_files: list[StagedFile] = []
    marker: StagedFile | None = None
    try:
        directory_descriptor = _open_guarded_directory(guard)
        _probe_anonymous_staging(directory_descriptor)
        for item in plan.files:
            _require_entry_absent(directory_descriptor, item.target_name)
        _require_entry_absent(directory_descriptor, COMPLETION_MARKER)

        observed_total = 0
        for item in plan.files:
            staged = _download_to_anonymous(
                plan,
                item,
                guard,
                directory_descriptor,
                opener=opener,
                resolver=resolver,
                clock=clock,
            )
            staged_files.append(staged)
            observed_total += staged.size_bytes

        if observed_total != plan.total_size_bytes:
            raise TransferError("total_size_mismatch")
        _assert_plan_unexpired(plan, clock)
        marker = _stage_bytes(_completion_marker_bytes(plan), directory_descriptor)

        for staged in staged_files:
            if staged.item is None:
                raise TransferError("staged_item_binding_missing")
            _assert_plan_unexpired(plan, clock)
            guard.revalidate()
            _require_entry_absent(directory_descriptor, staged.item.target_name)
            _link_anonymous_file(staged, directory_descriptor, staged.item.target_name)
            _verify_published_identity(staged, directory_descriptor, staged.item.target_name)

        _assert_plan_unexpired(plan, clock)
        guard.revalidate()
        for staged in staged_files:
            if staged.item is None:
                raise TransferError("staged_item_binding_missing")
            _verify_published_identity(staged, directory_descriptor, staged.item.target_name)
        _require_entry_absent(directory_descriptor, COMPLETION_MARKER)
        _assert_plan_unexpired(plan, clock)
        _link_anonymous_file(marker, directory_descriptor, COMPLETION_MARKER)
        _verify_published_identity(marker, directory_descriptor, COMPLETION_MARKER)
        return observed_total
    finally:
        if marker is not None:
            _close_staged(marker)
        for staged in staged_files:
            _close_staged(staged)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _build_parser() -> argparse.ArgumentParser:
    parser = RedactedArgumentParser(
        description=(
            "Validate or fetch a private signed transfer plan without disclosing it. "
            "Execution is Linux-only and requires O_TMPFILE plus descriptor-based "
            "linkat publication (AT_EMPTY_PATH or verified procfs descriptor); "
            "validation and planning remain cross-platform and read-only."
        )
    )
    parser.add_argument("--plan", type=Path, required=True, help="private transfer-plan path")
    parser.add_argument(
        "--destination",
        type=Path,
        help=(
            "existing out-of-repository directory; execution requires Linux descriptor "
            "publication support"
        ),
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--validate-only",
        action="store_true",
        help="validate plan syntax and policy without DNS, network, or writes",
    )
    modes.add_argument(
        "--plan-only",
        action="store_true",
        help="also validate destination readiness without DNS, network, or writes",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        plan = load_transfer_plan(args.plan)
        if args.validate_only:
            print(json.dumps({"file_count": len(plan.files), "status": "valid"}, sort_keys=True))
            return 0
        if args.destination is None:
            raise TransferError("destination_required")
        guard = validate_destination(args.destination)
        if args.plan_only:
            for item in plan.files:
                if _path_exists_without_following(guard.path / item.target_name):
                    raise TransferError("target_collision")
            if _path_exists_without_following(guard.path / COMPLETION_MARKER):
                raise TransferError("target_collision")
            print(json.dumps({"file_count": len(plan.files), "status": "ready"}, sort_keys=True))
            return 0
        execute_transfer(plan, guard)
    except Exception:  # Every operational detail is deliberately redacted at the CLI boundary.
        return _fail()

    print(json.dumps({"file_count": len(plan.files), "status": "ok"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
