#!/usr/bin/env python3
"""Prepare private WGS inputs without disclosing case filenames or tokens.

The CLI deliberately emits only generic status/count messages.  Its manifests
and signed URL plans are controlled artifacts and are required to live outside
the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA = "secure-wgs-input-manifest/v1"
TRANSFER_SCHEMA = "secure-wgs-signed-transfer-plan/v1"
HF_REPO_ID = "SageBio/mva-hackathon-2026-data"
HF_HOST = "huggingface.co"
SAMPLE_ID_PATTERN = re.compile(r"^SAMPLE[0-9]{2}$")
GENERIC_FASTQ_NAME = re.compile(r"^SAMPLE[0-9]{2}_L[0-9]{3}_R[12]\.fastq\.gz$")
FASTQ_SUFFIX = re.compile(r"(?i)(?:\.fastq|\.fq)\.gz$")
READ_MARKERS = (
    re.compile(r"(?i)^(?P<key>.+?)[._-]R(?P<read>[12])(?:[._-]00[0-9])?$"),
    re.compile(r"(?i)^(?P<key>.+?)[._-](?P<read>[12])$"),
)


class SecureWgsError(RuntimeError):
    """An intentionally non-sensitive validation failure."""


@dataclass(frozen=True)
class FastqPair:
    """A paired FASTQ set; source paths are private runtime values."""

    key: str
    read1: Path
    read2: Path


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Capture signed redirects so bearer credentials are never forwarded."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolved(path: Path, *, must_exist: bool) -> Path:
    if not path.is_absolute():
        raise SecureWgsError("an absolute private path is required")
    try:
        return path.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise SecureWgsError("a private path could not be resolved") from exc


def validate_private_directory(path: Path, *, must_exist: bool = True) -> Path:
    """Resolve a private directory and reject repository/symlink locations."""

    resolved = _resolved(path, must_exist=must_exist)
    if must_exist and not resolved.is_dir():
        raise SecureWgsError("the private input location is not a directory")
    if _is_within(resolved, REPO_ROOT):
        raise SecureWgsError("controlled work must remain outside the repository")

    cursor = path
    while True:
        try:
            if cursor.exists() and cursor.is_symlink():
                raise SecureWgsError("symlinked private paths are not accepted")
        except OSError as exc:
            raise SecureWgsError("private path metadata could not be validated") from exc
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return resolved


def validate_private_output(path: Path) -> Path:
    """Validate an output file path whose parent is outside the repository."""

    if not path.is_absolute():
        raise SecureWgsError("an absolute private output path is required")
    parent = validate_private_directory(path.parent, must_exist=False)
    if not parent.exists():
        try:
            parent.mkdir(parents=True, mode=0o700)
        except OSError as exc:
            raise SecureWgsError("the private output directory could not be created") from exc
    parent = validate_private_directory(parent)
    return parent / path.name


def parse_fastq_name(name: str) -> tuple[str, int]:
    """Return a pairing key and read number without retaining it publicly."""

    if not FASTQ_SUFFIX.search(name):
        raise SecureWgsError("all sequence inputs must be gzip-compressed FASTQ files")
    stem = FASTQ_SUFFIX.sub("", name)
    for pattern in READ_MARKERS:
        match = pattern.match(stem)
        if match:
            key = match.group("key")
            if not key:
                break
            return key, int(match.group("read"))
    raise SecureWgsError("a FASTQ read marker could not be classified")


def discover_fastq_pairs(input_dir: Path) -> list[FastqPair]:
    """Pair every top-level FASTQ while failing on ambiguity or incompleteness."""

    private_dir = validate_private_directory(input_dir)
    try:
        candidates = sorted(
            (item for item in private_dir.iterdir() if item.is_file()),
            key=lambda item: item.name.casefold(),
        )
    except OSError as exc:
        raise SecureWgsError("the private input directory could not be enumerated") from exc

    fastqs = [item for item in candidates if FASTQ_SUFFIX.search(item.name)]
    if not fastqs:
        raise SecureWgsError("no gzip-compressed FASTQ inputs were found")

    grouped: dict[str, dict[int, Path | str]] = {}
    for fastq in fastqs:
        key, read = parse_fastq_name(fastq.name)
        normalized = key.casefold()
        bucket = grouped.setdefault(normalized, {0: key})
        if read in bucket:
            raise SecureWgsError("duplicate FASTQ mates were detected")
        bucket[read] = fastq

    pairs: list[FastqPair] = []
    for normalized in sorted(grouped):
        bucket = grouped[normalized]
        if 1 not in bucket or 2 not in bucket:
            raise SecureWgsError("an incomplete FASTQ pair was detected")
        pairs.append(
            FastqPair(
                key=str(bucket[0]),
                read1=Path(bucket[1]),
                read2=Path(bucket[2]),
            )
        )
    return pairs


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise SecureWgsError("a private input could not be checksummed") from exc
    return digest.hexdigest()


def _atomic_json_write(path: Path, payload: dict) -> None:
    destination = validate_private_output(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=".secure-wgs-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, destination)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise SecureWgsError("a private metadata artifact could not be written") from exc


def _materialize(source: Path, destination: Path, mode: str) -> None:
    if destination.exists():
        raise SecureWgsError("the generic staging location is not empty")
    try:
        if mode == "hardlink":
            os.link(source, destination)
        elif mode == "copy":
            shutil.copyfile(source, destination)
        else:
            raise SecureWgsError("unsupported materialization mode")
        os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
    except SecureWgsError:
        raise
    except OSError as exc:
        raise SecureWgsError("a generic FASTQ alias could not be materialized") from exc


def prepare_manifest(
    *,
    input_dir: Path,
    manifest_path: Path,
    sample_id: str = "SAMPLE01",
    work_dir: Path | None = None,
    materialize: str = "none",
    calculate_hashes: bool = True,
) -> dict:
    """Build a private manifest and optional generic FASTQ aliases."""

    if not SAMPLE_ID_PATTERN.fullmatch(sample_id):
        raise SecureWgsError("sample identifiers must use the generic SAMPLE## form")
    if materialize not in {"none", "hardlink", "copy"}:
        raise SecureWgsError("materialization must be none, hardlink, or copy")
    if materialize != "none" and work_dir is None:
        raise SecureWgsError("a private work directory is required for materialization")

    pairs = discover_fastq_pairs(input_dir)
    staged_dir: Path | None = None
    if work_dir is not None:
        private_work = validate_private_directory(work_dir, must_exist=False)
        try:
            private_work.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError as exc:
            raise SecureWgsError("the private work directory could not be created") from exc
        private_work = validate_private_directory(private_work)
        staged_dir = private_work / "staged-fastq"
        if materialize != "none":
            try:
                staged_dir.mkdir(mode=0o700, exist_ok=True)
            except OSError as exc:
                raise SecureWgsError("the generic staging directory could not be created") from exc
            if any(staged_dir.iterdir()):
                raise SecureWgsError("the generic staging location is not empty")

    records: list[dict] = []
    for lane_number, pair in enumerate(pairs, start=1):
        lane = f"L{lane_number:03d}"
        files: list[dict] = []
        for read, source in ((1, pair.read1), (2, pair.read2)):
            generic_name = f"{sample_id}_{lane}_R{read}.fastq.gz"
            checksum = sha256_file(source) if calculate_hashes else None
            if materialize != "none":
                assert staged_dir is not None
                destination = staged_dir / generic_name
                _materialize(source, destination, materialize)
                if destination.stat().st_size != source.stat().st_size:
                    raise SecureWgsError("a staged FASTQ size check failed")
                if calculate_hashes and sha256_file(destination) != checksum:
                    raise SecureWgsError("a staged FASTQ checksum check failed")
            files.append(
                {
                    "read": read,
                    "source_relative": source.name,
                    "staged_name": generic_name,
                    "size_bytes": source.stat().st_size,
                    "sha256": checksum,
                }
            )
        records.append(
            {
                "lane_id": lane,
                "read_group_id": f"{sample_id}.{lane}",
                "files": files,
            }
        )

    payload = {
        "schema": MANIFEST_SCHEMA,
        "classification": "CONTROLLED_PRIVATE_DO_NOT_COMMIT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": sample_id,
        "pair_count": len(records),
        "hash_algorithm": "sha256" if calculate_hashes else None,
        "ready_for_transfer": calculate_hashes,
        "materialization": materialize,
        "pairs": records,
    }
    _atomic_json_write(manifest_path, payload)
    return payload


def _get_hf_token(explicit: str | None = None) -> str:
    """Return an in-memory Hub token, preferring explicit/env over HF's cache."""

    token = explicit or os.environ.get("HF_TOKEN")
    if not token:
        try:
            from huggingface_hub import get_token

            token = get_token()
        except (ImportError, OSError, RuntimeError):
            token = None
    if not token:
        raise SecureWgsError("Hugging Face authentication is not available")
    return token


def _hf_file_metadata(revision: str, token: str) -> tuple[list[dict], str]:
    """Read dataset metadata only; no repository content is downloaded."""

    try:
        from huggingface_hub import HfApi

        info = HfApi().dataset_info(
            HF_REPO_ID,
            revision=revision,
            files_metadata=True,
            token=token,
        )
    except ImportError as exc:
        raise SecureWgsError("huggingface_hub is required for metadata-only preparation") from exc
    except Exception as exc:  # Hub exceptions vary between client releases.
        raise SecureWgsError("Hugging Face metadata could not be retrieved") from exc

    resolved_revision = getattr(info, "sha", None)
    if not isinstance(resolved_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", resolved_revision
    ):
        raise SecureWgsError("Hugging Face did not return a pinned commit revision")

    records: list[dict] = []
    for sibling in getattr(info, "siblings", ()):
        path = getattr(sibling, "rfilename", None)
        if not isinstance(path, str) or not FASTQ_SUFFIX.search(Path(path).name):
            continue
        lfs = getattr(sibling, "lfs", None)
        if isinstance(lfs, dict):
            sha256 = lfs.get("sha256") or lfs.get("oid")
            lfs_size = lfs.get("size")
        else:
            sha256 = getattr(lfs, "sha256", None)
            lfs_size = getattr(lfs, "size", None)
        if isinstance(sha256, str) and sha256.startswith("sha256:"):
            sha256 = sha256.removeprefix("sha256:")
        size = getattr(sibling, "size", None)
        if size is None:
            size = lfs_size
        if (
            not re.fullmatch(r"[0-9a-f]{64}", sha256 or "")
            or not isinstance(lfs_size, int)
            or lfs_size <= 0
            or not isinstance(size, int)
            or size <= 0
            or lfs_size != size
        ):
            raise SecureWgsError("a FASTQ lacks authoritative LFS SHA-256 or size metadata")
        records.append({"path": path, "size_bytes": size, "sha256": sha256})
    if not records:
        raise SecureWgsError("no gzip-compressed FASTQ metadata was found")
    return records, resolved_revision


def prepare_hf_manifest(
    *,
    manifest_path: Path,
    sample_id: str = "SAMPLE01",
    revision: str = "main",
    token: str | None = None,
    metadata_fetcher: Callable[[str, str], tuple[list[dict], str]] | None = None,
) -> dict:
    """Build a transfer-ready manifest from Hub metadata without downloading FASTQs."""

    if not SAMPLE_ID_PATTERN.fullmatch(sample_id):
        raise SecureWgsError("sample identifiers must use the generic SAMPLE## form")
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", revision) or ".." in revision:
        raise SecureWgsError("the Hugging Face revision is invalid")
    bearer = _get_hf_token(token)
    fetcher = metadata_fetcher or _hf_file_metadata
    records, resolved_revision = fetcher(revision, bearer)
    if not re.fullmatch(r"[0-9a-f]{40}", resolved_revision):
        raise SecureWgsError("Hugging Face metadata is not pinned to a commit")

    grouped: dict[str, dict[int, dict | str]] = {}
    for record in records:
        path_value = record.get("path")
        checksum = record.get("sha256")
        size = record.get("size_bytes")
        if (
            not isinstance(path_value, str)
            or path_value.startswith(("/", "\\"))
            or ".." in Path(path_value).parts
            or not re.fullmatch(r"[0-9a-f]{64}", checksum or "")
            or not isinstance(size, int)
            or size <= 0
        ):
            raise SecureWgsError("Hugging Face FASTQ metadata is invalid")
        path = Path(path_value)
        key, read = parse_fastq_name(path.name)
        grouping_key = f"{path.parent.as_posix()}/{key}".casefold()
        bucket = grouped.setdefault(grouping_key, {0: key})
        if read in bucket:
            raise SecureWgsError("duplicate FASTQ mates were detected")
        bucket[read] = record

    pairs: list[dict] = []
    for lane_number, grouping_key in enumerate(sorted(grouped), start=1):
        bucket = grouped[grouping_key]
        if 1 not in bucket or 2 not in bucket:
            raise SecureWgsError("an incomplete FASTQ pair was detected")
        lane = f"L{lane_number:03d}"
        files: list[dict] = []
        for read in (1, 2):
            item = bucket[read]
            assert isinstance(item, dict)
            files.append(
                {
                    "read": read,
                    "source_relative": item["path"],
                    "staged_name": f"{sample_id}_{lane}_R{read}.fastq.gz",
                    "size_bytes": item["size_bytes"],
                    "sha256": item["sha256"],
                }
            )
        pairs.append(
            {
                "lane_id": lane,
                "read_group_id": f"{sample_id}.{lane}",
                "files": files,
            }
        )

    payload = {
        "schema": MANIFEST_SCHEMA,
        "classification": "CONTROLLED_PRIVATE_DO_NOT_COMMIT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": sample_id,
        "pair_count": len(pairs),
        "hash_algorithm": "sha256",
        "ready_for_transfer": True,
        "materialization": "hugging-face-metadata-only",
        "source_revision": resolved_revision,
        "token_persisted": False,
        "pairs": pairs,
    }
    _atomic_json_write(manifest_path, payload)
    return payload


def _load_private_json(path: Path) -> dict:
    if path.is_symlink():
        raise SecureWgsError("private metadata must not be a symbolic link")
    private_path = _resolved(path, must_exist=True)
    if _is_within(private_path, REPO_ROOT):
        raise SecureWgsError("controlled metadata must remain outside the repository")
    try:
        with private_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SecureWgsError("private metadata could not be read") from exc
    if not isinstance(payload, dict):
        raise SecureWgsError("private metadata has an invalid structure")
    return payload


def _redirect_location(resolve_url: str, token: str) -> str:
    request = urllib.request.Request(
        resolve_url,
        method="HEAD",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "secure-wgs/1"},
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        opener.open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise SecureWgsError("Hugging Face did not authorize a transfer artifact") from exc
        location = exc.headers.get("Location")
        if not location:
            raise SecureWgsError("Hugging Face returned no signed transfer location") from exc
        signed_url = urllib.parse.urljoin(resolve_url, location)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SecureWgsError("the signed transfer request failed") from exc
    else:
        raise SecureWgsError("the artifact did not produce an expiring signed URL")

    parsed = urllib.parse.urlparse(signed_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SecureWgsError("the signed transfer location is not HTTPS")
    return signed_url


def _signed_url_expiry(url: str) -> datetime | None:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "Expires" in query:
        try:
            return datetime.fromtimestamp(int(query["Expires"][0]), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if "X-Amz-Date" in query and "X-Amz-Expires" in query:
        try:
            issued = datetime.strptime(query["X-Amz-Date"][0], "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
            return issued + timedelta(seconds=int(query["X-Amz-Expires"][0]))
        except (ValueError, IndexError):
            return None
    return None


def create_signed_transfer_plan(
    *,
    manifest_path: Path,
    output_path: Path,
    revision: str | None = None,
    token: str | None = None,
    resolver: Callable[[str, str], str] = _redirect_location,
) -> dict:
    """Resolve expiring URLs without storing or printing the HF bearer token."""

    manifest = _load_private_json(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("ready_for_transfer") is not True:
        raise SecureWgsError("the private input manifest is not transfer-ready")
    manifest_revision = manifest.get("source_revision")
    selected_revision = revision or manifest_revision or "main"
    if (
        not isinstance(selected_revision, str)
        or not re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", selected_revision)
        or ".." in selected_revision
    ):
        raise SecureWgsError("the Hugging Face revision is invalid")
    if manifest_revision is not None and selected_revision != manifest_revision:
        raise SecureWgsError("the transfer revision does not match the private manifest")
    bearer = _get_hf_token(token)

    files: list[dict] = []
    expiries: list[datetime] = []
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise SecureWgsError("the private input manifest has no FASTQ pairs")
    seen_sources: set[str] = set()
    seen_targets: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, dict) or not isinstance(pair.get("files"), list):
            raise SecureWgsError("the private input manifest is incomplete")
        for item in pair["files"]:
            if not isinstance(item, dict):
                raise SecureWgsError("the private input manifest is incomplete")
            source = item.get("source_relative")
            target = item.get("staged_name")
            checksum = item.get("sha256")
            size = item.get("size_bytes")
            if (
                not isinstance(source, str)
                or not source
                or source.startswith(("/", "\\"))
                or "\\" in source
                or ".." in Path(source).parts
                or not isinstance(target, str)
                or not GENERIC_FASTQ_NAME.fullmatch(target)
                or not isinstance(checksum, str)
                or not re.fullmatch(r"[0-9a-f]{64}", checksum)
                or not isinstance(size, int)
                or size <= 0
            ):
                raise SecureWgsError("the private input manifest is incomplete")
            if source in seen_sources or target in seen_targets:
                raise SecureWgsError("the private input manifest contains duplicate files")
            seen_sources.add(source)
            seen_targets.add(target)
            encoded_source = urllib.parse.quote(source, safe="/")
            resolve_url = (
                f"https://{HF_HOST}/datasets/{HF_REPO_ID}/resolve/"
                f"{urllib.parse.quote(selected_revision, safe='/')}/{encoded_source}"
            )
            signed_url = resolver(resolve_url, bearer)
            expiry = _signed_url_expiry(signed_url)
            if expiry is None:
                raise SecureWgsError("a signed URL has no machine-verifiable expiration")
            if expiry <= datetime.now(timezone.utc):
                raise SecureWgsError("a signed URL is already expired")
            expiries.append(expiry)
            files.append(
                {
                    "target_name": target,
                    "sha256": checksum,
                    "size_bytes": size,
                    "signed_url": signed_url,
                    "expires_utc": expiry.isoformat(),
                }
            )

    if not files:
        raise SecureWgsError("the transfer plan contains no files")
    payload = {
        "schema": TRANSFER_SCHEMA,
        "classification": "SECRET_CONTROLLED_SIGNED_URLS_DO_NOT_COMMIT",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "provider": "Hugging Face",
            "repo_id": HF_REPO_ID,
            "revision": selected_revision,
        },
        "token_persisted": False,
        "expires_utc": min(expiries).isoformat(),
        "file_count": len(files),
        "files": files,
    }
    _atomic_json_write(output_path, payload)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare private WGS transfer metadata without public disclosure."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="pair FASTQs and write a private manifest")
    prepare.add_argument("--input-dir", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--work-dir", type=Path)
    prepare.add_argument("--sample-id", default="SAMPLE01")
    prepare.add_argument("--materialize", choices=("none", "hardlink", "copy"), default="none")
    prepare.add_argument(
        "--no-hash",
        action="store_true",
        help="smoke planning only; resulting manifest is not transfer-ready",
    )

    prepare_hf = subparsers.add_parser(
        "prepare-hf", help="write a private manifest from gated Hub metadata only"
    )
    prepare_hf.add_argument("--manifest", type=Path, required=True)
    prepare_hf.add_argument("--sample-id", default="SAMPLE01")
    prepare_hf.add_argument("--revision", default="main")

    sign = subparsers.add_parser(
        "sign-plan", help="write expiring signed URLs to a private transfer plan"
    )
    sign.add_argument("--manifest", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    sign.add_argument("--revision")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "prepare":
            payload = prepare_manifest(
                input_dir=args.input_dir,
                manifest_path=args.manifest,
                sample_id=args.sample_id,
                work_dir=args.work_dir,
                materialize=args.materialize,
                calculate_hashes=not args.no_hash,
            )
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "pair_count": payload["pair_count"],
                        "ready_for_transfer": payload["ready_for_transfer"],
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "prepare-hf":
            payload = prepare_hf_manifest(
                manifest_path=args.manifest,
                sample_id=args.sample_id,
                revision=args.revision,
            )
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "pair_count": payload["pair_count"],
                        "ready_for_transfer": True,
                    },
                    sort_keys=True,
                )
            )
        else:
            payload = create_signed_transfer_plan(
                manifest_path=args.manifest,
                output_path=args.output,
                revision=args.revision,
            )
            print(json.dumps({"status": "ok", "file_count": payload["file_count"]}))
    except SecureWgsError:
        print("secure_wgs_status=failed_closed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
