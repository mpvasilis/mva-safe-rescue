#!/usr/bin/env python3
"""Privacy-safe, complete OOXML text extraction and DOCX package audit.

The extractor intentionally uses only Python's standard library.  It reads the
WordprocessingML package directly so text in headers, footers, notes, comments,
glossary entries, tables, text boxes, and DrawingML is not lost by a
``python-docx``-style main-document-only traversal.

The complete-text output contains provenance markers and extracted document
text.  The JSON audit never contains extracted document text: it records only
part names, roles, hashes, counts, and package-accounting metadata.  The CLI
likewise emits only a small, content-free JSON summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable, Mapping
from xml.etree import ElementTree as ET


AUDIT_SCHEMA_VERSION = "1.0.0"
TEXT_FORMAT_VERSION = "1.0.0"
DEFAULT_MAX_XML_PART_BYTES = 64 * 1024 * 1024

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
V_NS = "urn:schemas-microsoft-com:vml"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def _qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


TEXT_NODE_LABELS = {
    _qname(W_NS, "t"): "w:t",
    _qname(A_NS, "t"): "a:t",
    _qname(M_NS, "t"): "m:t",
    _qname(W_NS, "delText"): "w:delText",
    _qname(W_NS, "instrText"): "w:instrText",
}

TEXT_BOUNDARY_LABELS = {
    _qname(W_NS, "tab"): "\t",
    _qname(W_NS, "br"): "\n",
    _qname(W_NS, "cr"): "\n",
    _qname(W_NS, "noBreakHyphen"): "\u2011",
    _qname(W_NS, "softHyphen"): "\u00ad",
}

PARAGRAPH_TAGS = {_qname(W_NS, "p"), _qname(A_NS, "p")}
TABLE_TAG = _qname(W_NS, "tbl")
TABLE_CELL_TAG = _qname(W_NS, "tc")
TABLE_ROW_TAG = _qname(W_NS, "tr")
ALTERNATE_CONTENT_TAG = _qname(MC_NS, "AlternateContent")
CHOICE_TAG = _qname(MC_NS, "Choice")
FALLBACK_TAG = _qname(MC_NS, "Fallback")

TEXT_BOX_TAGS = {
    _qname(W_NS, "txbxContent"),
    _qname(V_NS, "textbox"),
    _qname(WPS_NS, "txbx"),
}

DRAWING_OBJECT_TAGS = {
    _qname(W_NS, "drawing"),
    _qname(W_NS, "pict"),
}

REVISION_TAGS = {
    _qname(W_NS, "ins"),
    _qname(W_NS, "del"),
    _qname(W_NS, "moveFrom"),
    _qname(W_NS, "moveTo"),
}

ROLE_ORDER = {
    "main_document": 0,
    "header": 10,
    "footer": 20,
    "footnotes": 30,
    "endnotes": 40,
    "comments": 50,
    "glossary": 60,
    "drawing_content": 70,
    "additional_text_content": 80,
}

STRUCTURAL_EXACT_PARTS = {
    "[Content_Types].xml",
    "word/settings.xml",
    "word/styles.xml",
    "word/stylesWithEffects.xml",
    "word/numbering.xml",
    "word/fontTable.xml",
    "word/webSettings.xml",
    "word/people.xml",
}

STRUCTURAL_PREFIXES = (
    "_rels/",
    "docProps/",
    "word/_rels/",
    "word/theme/",
    "word/glossary/_rels/",
    "word/glossary/styles",
    "word/charts/_rels/",
    "word/diagrams/_rels/",
)

EMBEDDED_PREFIXES = (
    "word/embeddings/",
    "word/activeX/",
)

KNOWN_RELATIONSHIP_KINDS = {
    "aFChunk",
    "chart",
    "comments",
    "diagramData",
    "diagramDrawing",
    "endnotes",
    "footer",
    "footnotes",
    "glossaryDocument",
    "header",
    "hyperlink",
    "image",
    "officeDocument",
    "oleObject",
    "package",
    "settings",
    "styles",
    "theme",
}


class DocxAuditError(RuntimeError):
    """Raised for fail-closed DOCX validation or extraction errors."""


@dataclass(frozen=True)
class AuditResult:
    """Paths and content-free metadata for a completed audit."""

    audit: Mapping[str, Any]
    text_output: Path
    audit_output: Path


@dataclass(frozen=True)
class _ContentTypes:
    defaults: Mapping[str, str]
    overrides: Mapping[str, str]

    def for_part(self, part_name: str) -> str | None:
        override = self.overrides.get(part_name)
        if override is not None:
            return override
        extension = PurePosixPath(part_name).suffix.lstrip(".").lower()
        return self.defaults.get(extension)


@dataclass(frozen=True)
class _ExtractedPart:
    part_name: str
    role: str
    package_index: int
    raw_sha256: str
    raw_bytes: int
    content_type: str | None
    text: str
    statistics: Mapping[str, Any]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/"):
        return False
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts


def _natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(piece) if piece.isdigit() else piece.lower()
        for piece in re.split(r"(\d+)", value)
    )


def _role_for_part(part_name: str) -> str | None:
    if part_name == "word/document.xml":
        return "main_document"
    if re.fullmatch(r"word/header[^/]*\.xml", part_name):
        return "header"
    if re.fullmatch(r"word/footer[^/]*\.xml", part_name):
        return "footer"
    if part_name == "word/footnotes.xml":
        return "footnotes"
    if part_name == "word/endnotes.xml":
        return "endnotes"
    if re.fullmatch(r"word/comments[^/]*\.xml", part_name):
        return "comments"
    if part_name == "word/glossary/document.xml":
        return "glossary"
    if re.fullmatch(
        r"word/(?:charts|diagrams|drawings)/[^/]+\.xml", part_name
    ):
        return "drawing_content"
    return None


def _is_structural_part(part_name: str) -> bool:
    return (
        part_name in STRUCTURAL_EXACT_PARTS
        or part_name.endswith(".rels")
        or part_name.startswith(STRUCTURAL_PREFIXES)
    )


def _is_embedded_part(part_name: str) -> bool:
    return (
        part_name.startswith(EMBEDDED_PREFIXES)
        or part_name == "word/vbaProject.bin"
        or part_name == "word/vbaData.xml"
    )


def _unsupported_reason(part_name: str) -> str:
    lowered = part_name.lower()
    if "afchunk" in lowered or lowered.endswith((".mht", ".mhtml", ".html", ".htm")):
        return "alternative_format_chunk_not_decoded"
    if part_name.startswith("customXml/"):
        return "custom_xml_not_interpreted"
    if "vba" in lowered or part_name.startswith("word/activeX/"):
        return "executable_or_macro_content_not_executed"
    if part_name.startswith(("word/charts/", "word/diagrams/", "word/drawings/")):
        return "drawing_auxiliary_part_has_no_supported_text_nodes"
    return "non_text_package_part_not_interpreted"


def _read_xml_part(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    max_xml_part_bytes: int,
) -> bytes:
    if info.file_size > max_xml_part_bytes:
        raise DocxAuditError("OOXML part exceeds the configured safe size limit")
    return archive.read(info)


def _parse_content_types(
    archive: zipfile.ZipFile,
    info_by_name: Mapping[str, zipfile.ZipInfo],
    *,
    max_xml_part_bytes: int,
) -> _ContentTypes:
    info = info_by_name.get("[Content_Types].xml")
    if info is None:
        raise DocxAuditError("DOCX package has no content-types manifest")
    try:
        root = ET.fromstring(
            _read_xml_part(
                archive, info, max_xml_part_bytes=max_xml_part_bytes
            )
        )
    except ET.ParseError as exc:
        raise DocxAuditError("DOCX content-types manifest is malformed") from exc

    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for child in root:
        if child.tag == _qname(CONTENT_TYPES_NS, "Default"):
            extension = child.attrib.get("Extension", "").lower()
            content_type = child.attrib.get("ContentType", "")
            if extension and content_type:
                defaults[extension] = content_type
        elif child.tag == _qname(CONTENT_TYPES_NS, "Override"):
            part_name = child.attrib.get("PartName", "").lstrip("/")
            content_type = child.attrib.get("ContentType", "")
            if part_name and content_type:
                overrides[part_name] = content_type
    return _ContentTypes(defaults=defaults, overrides=overrides)


def _has_supported_text_nodes(data: bytes) -> bool:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return False
    return any(element.tag in TEXT_NODE_LABELS for element in root.iter())


def _branch_has_supported_text(element: ET.Element) -> bool:
    return any(descendant.tag in TEXT_NODE_LABELS for descendant in element.iter())


def _extract_xml_text(data: bytes) -> tuple[str, Mapping[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise DocxAuditError("A selected OOXML text part is malformed") from exc

    pieces: list[str] = []
    text_node_counts: Counter[str] = Counter()
    structural_counts: Counter[str] = Counter()

    def visit(element: ET.Element) -> None:
        tag = element.tag

        if tag in TEXT_NODE_LABELS:
            label = TEXT_NODE_LABELS[tag]
            text_node_counts[label] += 1
            if element.text:
                pieces.append(element.text)
            return

        if tag in TEXT_BOUNDARY_LABELS:
            structural_counts[tag] += 1
            pieces.append(TEXT_BOUNDARY_LABELS[tag])
            return

        if tag == ALTERNATE_CONTENT_TAG:
            structural_counts["mc:AlternateContent"] += 1
            children = list(element)
            choices = [child for child in children if child.tag == CHOICE_TAG]
            fallback = next(
                (child for child in children if child.tag == FALLBACK_TAG), None
            )
            chosen = next(
                (choice for choice in choices if _branch_has_supported_text(choice)),
                choices[0] if choices else fallback,
            )
            if chosen is not None:
                for child in chosen:
                    visit(child)
            return

        if tag in TEXT_BOX_TAGS:
            structural_counts["text_box"] += 1
        if tag in DRAWING_OBJECT_TAGS:
            structural_counts["drawing_object"] += 1
        if tag in REVISION_TAGS:
            structural_counts["revision_container"] += 1
        if tag == TABLE_TAG:
            structural_counts["table"] += 1
        elif tag == TABLE_ROW_TAG:
            structural_counts["table_row"] += 1
        elif tag == TABLE_CELL_TAG:
            structural_counts["table_cell"] += 1
        elif tag in PARAGRAPH_TAGS:
            structural_counts["paragraph"] += 1

        for child in element:
            visit(child)

        if tag in PARAGRAPH_TAGS:
            pieces.append("\n")
        elif tag == TABLE_CELL_TAG:
            pieces.append("\t")
        elif tag == TABLE_ROW_TAG:
            pieces.append("\n")

    visit(root)
    text = "".join(pieces).replace("\r\n", "\n").replace("\r", "\n")
    encoded = text.encode("utf-8")
    line_count = 0 if not text else text.count("\n") + (0 if text.endswith("\n") else 1)

    statistics: dict[str, Any] = {
        "text_sha256": _sha256_bytes(encoded),
        "characters": len(text),
        "utf8_bytes": len(encoded),
        "words": len(re.findall(r"\S+", text, flags=re.UNICODE)),
        "lines": line_count,
        "text_node_counts": dict(sorted(text_node_counts.items())),
        "paragraph_count": structural_counts["paragraph"],
        "table_count": structural_counts["table"],
        "table_row_count": structural_counts["table_row"],
        "table_cell_count": structural_counts["table_cell"],
        "text_box_count": structural_counts["text_box"],
        "drawing_object_count": structural_counts["drawing_object"],
        "revision_container_count": structural_counts["revision_container"],
        "alternate_content_count": structural_counts["mc:AlternateContent"],
    }
    return text, statistics


def _part_record(
    *,
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    package_index: int,
    content_types: _ContentTypes,
    digest_cache: dict[str, str],
) -> dict[str, Any]:
    digest = digest_cache.get(info.filename)
    if digest is None:
        with archive.open(info, "r") as handle:
            digest = _sha256_stream(handle)
        digest_cache[info.filename] = digest
    return {
        "part_name": info.filename,
        "package_index": package_index,
        "content_type": content_types.for_part(info.filename),
        "bytes": info.file_size,
        "sha256": digest,
    }


def _relationship_kind(raw_type: str) -> str:
    suffix = raw_type.rstrip("/").rsplit("/", 1)[-1]
    return suffix if suffix in KNOWN_RELATIONSHIP_KINDS else "other"


def _relationship_summary(
    archive: zipfile.ZipFile,
    infos: Iterable[zipfile.ZipInfo],
    *,
    max_xml_part_bytes: int,
) -> Mapping[str, Any]:
    kinds: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    malformed_parts = 0
    relationship_part_count = 0
    total = 0

    for info in infos:
        if info.is_dir() or not info.filename.endswith(".rels"):
            continue
        relationship_part_count += 1
        try:
            root = ET.fromstring(
                _read_xml_part(
                    archive, info, max_xml_part_bytes=max_xml_part_bytes
                )
            )
        except (ET.ParseError, DocxAuditError):
            malformed_parts += 1
            continue
        for relationship in root:
            if relationship.tag != _qname(REL_NS, "Relationship"):
                continue
            total += 1
            kinds[_relationship_kind(relationship.attrib.get("Type", ""))] += 1
            mode = relationship.attrib.get("TargetMode", "Internal")
            modes["external" if mode == "External" else "internal"] += 1

    return {
        "relationship_part_count": relationship_part_count,
        "relationship_count": total,
        "target_mode_counts": dict(sorted(modes.items())),
        "kind_counts": dict(sorted(kinds.items())),
        "malformed_relationship_part_count": malformed_parts,
        "targets_included_in_audit": False,
    }


def _render_complete_text(parts: Iterable[_ExtractedPart]) -> str:
    rendered: list[str] = []
    for extraction_order, part in enumerate(parts, start=1):
        rendered.append(
            "[[DOCX_PART_BEGIN "
            f"order={extraction_order:04d} "
            f"role={part.role} "
            f"package_index={part.package_index} "
            f"name={part.part_name}]]\n"
        )
        rendered.append(part.text)
        if part.text and not part.text.endswith("\n"):
            rendered.append("\n")
        rendered.append(f"[[DOCX_PART_END order={extraction_order:04d}]]\n")
    return "".join(rendered)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _resolve_output_paths(
    source: Path,
    *,
    output_dir: Path | None,
    text_output: Path | None,
    audit_output: Path | None,
) -> tuple[Path, Path]:
    default_dir = (
        output_dir
        if output_dir is not None
        else source.parent / f"{source.stem}.docx-audit"
    )
    resolved_text = text_output or default_dir / "complete_text.txt"
    resolved_audit = audit_output or default_dir / "audit.json"

    source_resolved = source.resolve(strict=False)
    text_resolved = resolved_text.resolve(strict=False)
    audit_resolved = resolved_audit.resolve(strict=False)
    if source_resolved in {text_resolved, audit_resolved}:
        raise DocxAuditError("An output path would overwrite the source DOCX")
    if text_resolved == audit_resolved:
        raise DocxAuditError("Text and audit outputs must be different files")
    return resolved_text, resolved_audit


def audit_docx(
    docx_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    text_output: str | Path | None = None,
    audit_output: str | Path | None = None,
    max_xml_part_bytes: int = DEFAULT_MAX_XML_PART_BYTES,
) -> AuditResult:
    """Extract all supported DOCX text and write a content-free JSON audit.

    ``output_dir`` is optional.  When omitted, outputs are written to a sibling
    directory named ``<input-stem>.docx-audit``.  ``text_output`` and
    ``audit_output`` may independently override the two filenames.
    """

    source = Path(docx_path)
    if max_xml_part_bytes <= 0:
        raise DocxAuditError("The XML size limit must be positive")
    if not source.is_file():
        raise DocxAuditError("The DOCX source is not a regular file")
    if not zipfile.is_zipfile(source):
        raise DocxAuditError("The source is not a valid ZIP-based DOCX package")

    resolved_text_output, resolved_audit_output = _resolve_output_paths(
        source,
        output_dir=Path(output_dir) if output_dir is not None else None,
        text_output=Path(text_output) if text_output is not None else None,
        audit_output=Path(audit_output) if audit_output is not None else None,
    )

    source_sha256 = _sha256_file(source)
    source_bytes = source.stat().st_size
    digest_cache: dict[str, str] = {}

    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise DocxAuditError("The DOCX package contains duplicate part names")
        if any(not _safe_archive_name(name) for name in names):
            raise DocxAuditError("The DOCX package contains an unsafe part name")

        info_by_name = {info.filename: info for info in infos}
        if "word/document.xml" not in info_by_name:
            raise DocxAuditError("The DOCX package has no main Word document part")
        content_types = _parse_content_types(
            archive,
            info_by_name,
            max_xml_part_bytes=max_xml_part_bytes,
        )

        package_indices = {info.filename: index for index, info in enumerate(infos)}
        xml_cache: dict[str, bytes] = {}
        role_by_name: dict[str, str] = {}

        for info in infos:
            if info.is_dir():
                continue
            role = _role_for_part(info.filename)
            if role is not None:
                data = _read_xml_part(
                    archive, info, max_xml_part_bytes=max_xml_part_bytes
                )
                xml_cache[info.filename] = data
                role_by_name[info.filename] = role

        # Scan all remaining XML package parts for supported text nodes.  This
        # catches linked DrawingML/chart parts and future OOXML extensions
        # without silently treating them as structural metadata.
        for info in infos:
            name = info.filename
            if (
                info.is_dir()
                or name in role_by_name
                or not name.lower().endswith(".xml")
                or _is_structural_part(name)
                or _is_embedded_part(name)
                or name == "[Content_Types].xml"
            ):
                continue
            data = _read_xml_part(
                archive, info, max_xml_part_bytes=max_xml_part_bytes
            )
            if _has_supported_text_nodes(data):
                xml_cache[name] = data
                role_by_name[name] = _role_for_part(name) or "additional_text_content"

        ordered_names = sorted(
            role_by_name,
            key=lambda name: (
                ROLE_ORDER[role_by_name[name]],
                _natural_key(name),
                package_indices[name],
            ),
        )

        extracted_parts: list[_ExtractedPart] = []
        for name in ordered_names:
            info = info_by_name[name]
            data = xml_cache[name]
            text, statistics = _extract_xml_text(data)
            digest = _sha256_bytes(data)
            digest_cache[name] = digest
            extracted_parts.append(
                _ExtractedPart(
                    part_name=name,
                    role=role_by_name[name],
                    package_index=package_indices[name],
                    raw_sha256=digest,
                    raw_bytes=len(data),
                    content_type=content_types.for_part(name),
                    text=text,
                    statistics=statistics,
                )
            )

        extracted_names = set(role_by_name)
        media: list[dict[str, Any]] = []
        embedded_objects: list[dict[str, Any]] = []
        structural_parts: list[dict[str, Any]] = []
        unsupported_parts: list[dict[str, Any]] = []

        for info in infos:
            if info.is_dir() or info.filename in extracted_names:
                continue
            record = _part_record(
                archive=archive,
                info=info,
                package_index=package_indices[info.filename],
                content_types=content_types,
                digest_cache=digest_cache,
            )
            if info.filename.startswith("word/media/"):
                media.append(record)
            elif _is_embedded_part(info.filename):
                record["execution_policy"] = "never_executed"
                embedded_objects.append(record)
            elif _is_structural_part(info.filename) or info.filename == "[Content_Types].xml":
                structural_parts.append(record)
            else:
                record["reason"] = _unsupported_reason(info.filename)
                unsupported_parts.append(record)

        relationships = _relationship_summary(
            archive,
            infos,
            max_xml_part_bytes=max_xml_part_bytes,
        )

    complete_text = _render_complete_text(extracted_parts)
    complete_text_bytes = complete_text.encode("utf-8")
    body_text = "".join(part.text for part in extracted_parts)
    body_text_bytes = body_text.encode("utf-8")

    parts_audit: list[dict[str, Any]] = []
    for extraction_order, part in enumerate(extracted_parts, start=1):
        parts_audit.append(
            {
                "extraction_order": extraction_order,
                "package_index": part.package_index,
                "part_name": part.part_name,
                "role": part.role,
                "content_type": part.content_type,
                "raw_xml_bytes": part.raw_bytes,
                "raw_xml_sha256": part.raw_sha256,
                **part.statistics,
            }
        )

    accounted_file_count = (
        len(extracted_parts)
        + len(media)
        + len(embedded_objects)
        + len(structural_parts)
        + len(unsupported_parts)
    )
    package_file_count = sum(1 for info in infos if not info.is_dir())
    audit: dict[str, Any] = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "privacy": {
            "audit_contains_extracted_document_text": False,
            "cli_prints_extracted_document_text": False,
            "external_relationship_targets_recorded": False,
        },
        "source": {
            "sha256": source_sha256,
            "bytes": source_bytes,
            "package_file_count": package_file_count,
        },
        "extraction": {
            "text_format_version": TEXT_FORMAT_VERSION,
            "ordering_policy": (
                "logical_role_then_natural_part_name; original package_index retained"
            ),
            "tracked_deleted_text_included": True,
            "field_instruction_text_included": True,
            "alternate_content_policy": "one_text_bearing_choice_then_fallback",
            "part_count": len(extracted_parts),
            "parts": parts_audit,
            "body_text_sha256": _sha256_bytes(body_text_bytes),
            "body_text_characters": len(body_text),
            "body_text_utf8_bytes": len(body_text_bytes),
            "complete_text_sha256": _sha256_bytes(complete_text_bytes),
            "complete_text_characters": len(complete_text),
            "complete_text_utf8_bytes": len(complete_text_bytes),
            "complete_text_lines": complete_text.count("\n")
            + (0 if not complete_text or complete_text.endswith("\n") else 1),
        },
        "package": {
            "media": media,
            "embedded_objects": embedded_objects,
            "unsupported_parts": unsupported_parts,
            "structural_parts": structural_parts,
            "relationships": relationships,
            "accounting": {
                "package_file_count": package_file_count,
                "accounted_file_count": accounted_file_count,
                "unaccounted_file_count": package_file_count - accounted_file_count,
            },
        },
        "completeness": {
            "status": (
                "complete_with_reported_unsupported_parts"
                if unsupported_parts
                else "complete_for_supported_ooxml_text_nodes"
            ),
            "unsupported_part_count": len(unsupported_parts),
            "malformed_relationship_part_count": relationships[
                "malformed_relationship_part_count"
            ],
        },
    }

    audit_bytes = (
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(resolved_text_output, complete_text_bytes)
    _atomic_write_bytes(resolved_audit_output, audit_bytes)

    return AuditResult(
        audit=audit,
        text_output=resolved_text_output,
        audit_output=resolved_audit_output,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract all supported Word OOXML text with provenance and write a "
            "content-free JSON audit. Document text is never printed."
        )
    )
    parser.add_argument("docx", help="input .docx package")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="output directory (default: a sibling <stem>.docx-audit directory)",
    )
    parser.add_argument("--text-output", help="optional complete-text output path")
    parser.add_argument("--audit-output", help="optional JSON-audit output path")
    parser.add_argument(
        "--max-xml-part-mib",
        type=int,
        default=DEFAULT_MAX_XML_PART_BYTES // (1024 * 1024),
        help="fail-closed maximum size of one XML part in MiB (default: 64)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = audit_docx(
            args.docx,
            args.output_dir,
            text_output=args.text_output,
            audit_output=args.audit_output,
            max_xml_part_bytes=args.max_xml_part_mib * 1024 * 1024,
        )
    except Exception:
        # Deliberately do not echo filenames, XML parser snippets, exception
        # messages, or document content on this privacy boundary.
        print("docx_audit_status=failed_closed", file=sys.stderr)
        return 2

    extraction = result.audit["extraction"]
    summary = {
        "status": "ok",
        "part_count": extraction["part_count"],
        "body_text_characters": extraction["body_text_characters"],
        "complete_text_sha256": extraction["complete_text_sha256"],
        "unsupported_part_count": result.audit["completeness"][
            "unsupported_part_count"
        ],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main() tests
    raise SystemExit(main())
