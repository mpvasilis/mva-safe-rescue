from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from analysis.clinical_document import full_docx_audit


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

DOCUMENT_TEXT = (
    "SYNTHETIC_MAIN_4102",
    "SYNTHETIC_TABLE_4103",
    "SYNTHETIC_TEXTBOX_4104",
    "SYNTHETIC_DRAWING_4105",
    "SYNTHETIC_DELETED_4106",
    "SYNTHETIC_FIELD_4107",
    "SYNTHETIC_HEADER_4108",
    "SYNTHETIC_FOOTER_4109",
    "SYNTHETIC_FOOTNOTE_4110",
    "SYNTHETIC_ENDNOTE_4111",
    "SYNTHETIC_COMMENT_4112",
    "SYNTHETIC_GLOSSARY_4113",
    "SYNTHETIC_CHART_4114",
    "SYNTHETIC_ALTERNATE_4115",
)


def _content_types() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CT_NS}">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Default Extension="bin" ContentType="application/vnd.openxmlformats-officedocument.oleObject"/>
  <Default Extension="html" ContentType="text/html"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
  <Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>
  <Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""


def _single_text_part(root_name: str, text: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:{root_name} xmlns:w="{W_NS}"><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:{root_name}>"""


def _main_document() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="{W_NS}" xmlns:a="{A_NS}" xmlns:mc="{MC_NS}">
  <w:body>
    <w:p><w:r><w:t>{DOCUMENT_TEXT[0]}</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>{DOCUMENT_TEXT[1]}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    <w:p><w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>{DOCUMENT_TEXT[2]}</w:t></w:r></w:p></w:txbxContent><a:p><a:r><a:t>{DOCUMENT_TEXT[3]}</a:t></a:r></a:p></w:drawing></w:r></w:p>
    <w:p><w:del><w:r><w:delText>{DOCUMENT_TEXT[4]}</w:delText></w:r></w:del><w:r><w:instrText>{DOCUMENT_TEXT[5]}</w:instrText></w:r></w:p>
    <mc:AlternateContent>
      <mc:Choice Requires="w"><w:p><w:r><w:t>{DOCUMENT_TEXT[13]}</w:t></w:r></w:p></mc:Choice>
      <mc:Fallback><w:p><w:r><w:t>{DOCUMENT_TEXT[13]}</w:t></w:r></w:p></mc:Fallback>
    </mc:AlternateContent>
  </w:body>
</w:document>"""


def _relationships() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/oleObject1.bin"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/aFChunk" Target="afchunk1.html"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid/sensitive-target-is-not-audited" TargetMode="External"/>
</Relationships>"""


def _write_synthetic_docx(path: Path) -> None:
    entries: list[tuple[str, str | bytes]] = [
        ("[Content_Types].xml", _content_types()),
        ("word/footer2.xml", _single_text_part("ftr", DOCUMENT_TEXT[7])),
        ("word/document.xml", _main_document()),
        ("word/header1.xml", _single_text_part("hdr", DOCUMENT_TEXT[6])),
        ("word/footnotes.xml", _single_text_part("footnotes", DOCUMENT_TEXT[8])),
        ("word/endnotes.xml", _single_text_part("endnotes", DOCUMENT_TEXT[9])),
        ("word/comments.xml", _single_text_part("comments", DOCUMENT_TEXT[10])),
        (
            "word/glossary/document.xml",
            _single_text_part("document", DOCUMENT_TEXT[11]),
        ),
        (
            "word/charts/chart1.xml",
            f'<c:chart xmlns:c="urn:chart" xmlns:a="{A_NS}"><a:p><a:r><a:t>{DOCUMENT_TEXT[12]}</a:t></a:r></a:p></c:chart>',
        ),
        ("word/styles.xml", f'<w:styles xmlns:w="{W_NS}"/>'),
        ("word/_rels/document.xml.rels", _relationships()),
        ("word/media/image1.png", b"\x89PNG\r\n\x1a\nsynthetic-image"),
        ("word/embeddings/oleObject1.bin", b"synthetic-ole-object"),
        ("word/afchunk1.html", b"<p>UNSUPPORTED_HTML_BODY_5110</p>"),
        ("customXml/item1.xml", b"<record>UNSUPPORTED_CUSTOM_XML_5111</record>"),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)


def test_extracts_every_relevant_part_with_provenance_and_order(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.docx"
    _write_synthetic_docx(source)

    result = full_docx_audit.audit_docx(source, tmp_path / "results")
    complete_text = result.text_output.read_text(encoding="utf-8")
    audit = json.loads(result.audit_output.read_text(encoding="utf-8"))

    assert all(text in complete_text for text in DOCUMENT_TEXT)
    assert complete_text.count(DOCUMENT_TEXT[13]) == 1
    assert complete_text.index(DOCUMENT_TEXT[0]) < complete_text.index(DOCUMENT_TEXT[1])
    assert complete_text.index(DOCUMENT_TEXT[1]) < complete_text.index(DOCUMENT_TEXT[2])
    assert complete_text.index(DOCUMENT_TEXT[2]) < complete_text.index(DOCUMENT_TEXT[3])

    parts = audit["extraction"]["parts"]
    assert [part["role"] for part in parts] == [
        "main_document",
        "header",
        "footer",
        "footnotes",
        "endnotes",
        "comments",
        "glossary",
        "drawing_content",
    ]
    assert [part["extraction_order"] for part in parts] == list(range(1, 9))
    assert parts[0]["package_index"] == 2
    assert "[[DOCX_PART_BEGIN order=0001 role=main_document" in complete_text
    assert "name=word/glossary/document.xml]]" in complete_text

    main = parts[0]
    assert main["text_node_counts"] == {
        "a:t": 1,
        "w:delText": 1,
        "w:instrText": 1,
        "w:t": 4,
    }
    assert main["table_count"] == 1
    assert main["table_cell_count"] == 1
    assert main["text_box_count"] == 1
    assert main["drawing_object_count"] == 1
    assert main["revision_container_count"] == 1
    assert main["alternate_content_count"] == 1

    complete_bytes = result.text_output.read_bytes()
    assert hashlib.sha256(complete_bytes).hexdigest() == audit["extraction"][
        "complete_text_sha256"
    ]
    assert audit["extraction"]["complete_text_utf8_bytes"] == len(complete_bytes)


def test_audit_reports_all_non_text_parts_without_document_text(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.docx"
    _write_synthetic_docx(source)

    result = full_docx_audit.audit_docx(source, tmp_path / "results")
    audit_text = result.audit_output.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert all(text not in audit_text for text in DOCUMENT_TEXT)
    assert "UNSUPPORTED_HTML_BODY_5110" not in audit_text
    assert "UNSUPPORTED_CUSTOM_XML_5111" not in audit_text
    assert audit["privacy"] == {
        "audit_contains_extracted_document_text": False,
        "cli_prints_extracted_document_text": False,
        "external_relationship_targets_recorded": False,
    }

    media = audit["package"]["media"]
    embedded = audit["package"]["embedded_objects"]
    unsupported = audit["package"]["unsupported_parts"]
    assert [part["part_name"] for part in media] == ["word/media/image1.png"]
    assert [part["part_name"] for part in embedded] == [
        "word/embeddings/oleObject1.bin"
    ]
    assert embedded[0]["execution_policy"] == "never_executed"
    assert {part["part_name"] for part in unsupported} == {
        "customXml/item1.xml",
        "word/afchunk1.html",
    }
    assert all(len(part["sha256"]) == 64 for part in media + embedded + unsupported)

    relationships = audit["package"]["relationships"]
    assert relationships["relationship_count"] == 4
    assert relationships["target_mode_counts"] == {"external": 1, "internal": 3}
    assert relationships["targets_included_in_audit"] is False
    assert "sensitive-target-is-not-audited" not in audit_text
    assert audit["package"]["accounting"]["unaccounted_file_count"] == 0
    assert audit["completeness"]["status"] == "complete_with_reported_unsupported_parts"


def test_cli_uses_custom_output_paths_and_never_prints_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "synthetic.docx"
    _write_synthetic_docx(source)
    text_output = tmp_path / "private-output" / "all.txt"
    audit_output = tmp_path / "private-output" / "audit.json"

    exit_code = full_docx_audit.main(
        [
            str(source),
            "--text-output",
            str(text_output),
            "--audit-output",
            str(audit_output),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["status"] == "ok"
    assert summary["part_count"] == 8
    assert text_output.is_file()
    assert audit_output.is_file()
    assert all(text not in captured.out for text in DOCUMENT_TEXT)
    assert "synthetic.docx" not in captured.out


def test_cli_failure_is_generic_and_does_not_echo_sensitive_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sensitive_name = "private-patient-name-never-echo.docx"
    exit_code = full_docx_audit.main([str(tmp_path / sensitive_name)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "docx_audit_status=failed_closed"
    assert sensitive_name not in captured.err
