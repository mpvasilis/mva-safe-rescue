from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).absolute().parent.parent

CANDIDATE_COLUMNS = [
    "candidate_id",
    "generic_name",
    "screen_role",
    "mechanistic_axis",
    "mechanism_match_0_4",
    "public_result_match_0_4",
    "cns_neural_plausibility_0_4",
    "pediatric_rare_experience_0_4",
    "regulatory_status_0_4",
    "testability_0_4",
    "cancer_cin_hazard_0_4",
    "mechanism_basis",
    "public_result_boundary",
    "cns_pediatric_regulatory_basis",
    "hazard_contradiction",
    "counterevidence",
    "evidence_tiers",
    "falsifier",
    "advance_rule",
    "official_sources",
    "primary_sources",
]

CLAIM_COLUMNS = [
    "claim_id",
    "proposed_wording",
    "evidence_type",
    "source_or_result",
    "status",
    "confidence",
    "falsifier",
    "public_safety",
]

SAFE_RESCUE_COLUMNS = [
    "gate_id",
    "compartment",
    "endpoint",
    "advance_rule",
    "hard_stop",
    "rationale",
    "status",
]

CANDIDATE_SEARCH_COLUMNS = [
    "record_type",
    "record_id",
    "retrieval_window_utc",
    "source",
    "query_or_entity",
    "result_count",
    "screened_count",
    "screen_rule",
    "snapshot_ids_or_label_setid",
    "prior_panel_status",
    "refresh_disposition",
    "rationale",
    "source_url",
    "supporting_sources",
]

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def read_tsv(relative_path: str) -> tuple[list[str], list[dict[str, str]]]:
    with (REPO_ROOT / relative_path).open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        rows = list(reader)
    assert reader.fieldnames is not None
    assert all(None not in row for row in rows), f"ragged TSV: {relative_path}"
    assert all(
        value is not None for row in rows for value in row.values()
    ), f"missing TSV field: {relative_path}"
    return reader.fieldnames, rows


def test_candidate_scorecard_contract() -> None:
    columns, rows = read_tsv("docs/CANDIDATE_SCORECARD.tsv")
    assert columns == CANDIDATE_COLUMNS
    assert len(rows) == 5
    assert len({row["candidate_id"] for row in rows}) == 5
    assert len({row["generic_name"] for row in rows}) == 5

    expected_roles = {
        "arimoclomol": "confirmatory_vehicle_controlled_proteostasis_probe",
        "elamipretide": "confirmatory_vehicle_controlled_mitochondrial_benchmark",
        "sirolimus": "mandatory_same_model_mechanistic_control_ineligible_to_advance",
        "everolimus": "translational_mTOR_class_control_ineligible_to_advance",
        "acetylcysteine (N-acetylcysteine; NAC)": (
            "mandatory_ROS_direction_control_ineligible_to_advance"
        ),
    }
    assert {row["generic_name"]: row["screen_role"] for row in rows} == expected_roles

    score_columns = [column for column in columns if column.endswith("_0_4")]
    assert score_columns
    for row in rows:
        for column in score_columns:
            assert re.fullmatch(r"[0-4]", row[column]), (
                row["candidate_id"],
                column,
                row[column],
            )

    prohibited_aggregate_columns = {
        "total",
        "total_score",
        "score_total",
        "rank",
        "ranking",
        "weighted_score",
    }
    assert prohibited_aggregate_columns.isdisjoint(
        {column.lower() for column in columns}
    )
    for row in rows:
        assert "indeterminate/no-advance, not evidence of harm" in row[
            "falsifier"
        ].lower()
    for generic_name in (
        "sirolimus",
        "everolimus",
        "acetylcysteine (N-acetylcysteine; NAC)",
    ):
        row = next(item for item in rows if item["generic_name"] == generic_name)
        assert "ineligible for advancement" in row["advance_rule"].lower()


def test_candidate_search_refresh_contract() -> None:
    columns, rows = read_tsv("docs/CANDIDATE_SEARCH_LOG.tsv")
    assert columns == CANDIDATE_SEARCH_COLUMNS
    assert len(rows) == 41
    assert len({row["record_id"] for row in rows}) == len(rows)
    assert all(row["source_url"].startswith("https://") for row in rows)

    by_type: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_type.setdefault(row["record_type"], []).append(row)
        for field in ("result_count", "screened_count"):
            if row[field]:
                assert row[field].isdigit(), (row["record_id"], field, row[field])

    assert {kind: len(items) for kind, items in by_type.items()} == {
        "QUERY": 3,
        "PUBMED_BRIDGE": 12,
        "DAILYMED_LABEL": 12,
        "TRIAL_QUERY": 2,
        "CANDIDATE": 12,
    }
    by_id = {row["record_id"]: row for row in rows}
    assert [by_id[f"Q0{i}"]["result_count"] for i in range(1, 4)] == [
        "564",
        "79",
        "301",
    ]
    assert by_id["CT01"]["result_count"] == "0"
    assert by_id["CT02"]["result_count"] == "2"

    candidate_rows = by_type["CANDIDATE"]
    assert sum(row["record_id"].startswith("C") for row in candidate_rows) == 5
    assert sum(row["record_id"].startswith("A") for row in candidate_rows) == 7
    assert all(
        row["refresh_disposition"].startswith("retain_")
        for row in candidate_rows
        if row["record_id"].startswith("C")
    )
    assert all(
        row["refresh_disposition"].startswith("reject_first_round_")
        for row in candidate_rows
        if row["record_id"].startswith("A")
    )

    protocol = (REPO_ROOT / "docs" / "CANDIDATE_SEARCH_PROTOCOL.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "non-systematic" in protocol
    assert "not independent validation" in protocol
    assert "no named human curation sign-off is recorded yet" in protocol
    assert "release blocker" in protocol
    assert "prior_panel_status" in protocol
    assert "separately vehicle-controlled advancement candidates" in protocol


def test_claim_ledger_contract() -> None:
    columns, rows = read_tsv("docs/CLAIM_LEDGER.tsv")
    assert columns == CLAIM_COLUMNS
    assert rows
    identifiers = [row["claim_id"] for row in rows]
    assert len(identifiers) == len(set(identifiers))
    assert all(re.fullmatch(r"CL\d{3}", identifier) for identifier in identifiers)
    allowed_statuses = {"supported", "unsupported", "conditional", "prohibited"}
    assert all(row["status"] in allowed_statuses for row in rows)
    assert all(value.strip() for row in rows for value in row.values())
    by_id = {row["claim_id"]: row for row in rows}
    assert "not advancement power" in by_id["CL048"]["public_safety"].lower()
    assert "sample-size recommendation" in by_id["CL048"]["public_safety"].lower()


def test_safe_rescue_contract() -> None:
    columns, rows = read_tsv("docs/SAFE_RESCUE_ENVELOPE.tsv")
    assert columns == SAFE_RESCUE_COLUMNS
    assert [row["gate_id"] for row in rows] == [
        f"SRE{number:02d}" for number in range(1, 17)
    ]
    for row in rows:
        assert row["advance_rule"].strip()
        assert row["hard_stop"].strip()
        status = row["status"].lower()
        assert "provisional" in status
        assert "calibrate" in status
        assert "before confirmatory dosing" in status

    by_id = {row["gate_id"]: row for row in rows}
    assert all(
        "nonmalignant mva model" not in row["compartment"].lower()
        for row in rows
    )
    assert "atp-linked oxygen-consumption rate per viable cell" in by_id["SRE01"][
        "endpoint"
    ].lower()
    assert "tmrm membrane-potential signal per mitochondrial mass" in by_id[
        "SRE01"
    ]["endpoint"].lower()
    assert "day-21 live map2+tubb3+ neuron yield" in by_id["SRE03"][
        "endpoint"
    ].lower()
    for gate_id in ("SRE02", "SRE06", "SRE07"):
        assert "not required" in by_id[gate_id]["advance_rule"].lower()
        assert "affirmative benefit" in by_id[gate_id]["advance_rule"].lower()
    for gate_id in ("SRE10", "SRE14"):
        assert "indeterminate/no-advance, not evidence of harm" in by_id[gate_id][
            "hard_stop"
        ].lower()
    assert "every safety veto" in by_id["SRE16"]["endpoint"].lower()
    assert "only sre01 and sre03 define the six affirmative benefit comparisons" in (
        by_id["SRE16"]["rationale"].lower()
    )

    design = " ".join(
        (REPO_ROOT / "docs" / "CONFIRMATORY_EXPERIMENT_DESIGN.md")
        .read_text(encoding="utf-8")
        .lower()
        .split()
    )
    assert "day-21 live map2+tubb3+ neuron yield" in design
    assert "per 100 starting viable pax6+sox2+ neural progenitors" in design
    assert "exactly two orthogonal mitochondrial endpoints" in design
    assert "independent culture initiation/differentiation day" in design
    assert "indeterminate/no-advance" in design


def test_hosted_processor_governance_matches_organizer_clarification() -> None:
    governance = (REPO_ROOT / "DATA_GOVERNANCE.md").read_text(encoding="utf-8")
    normalized = governance.lower()
    assert "2026-08-27" in governance
    assert "no rights" in normalized
    assert "does not train" in normalized
    assert "plan/tier" in normalized
    assert "limited operational purpose and time" in normalized
    assert "discussions/2" in governance

    public_documents = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "DATA_GOVERNANCE.md",
        REPO_ROOT / "docs" / "REPORT_DRAFT.md",
    ]
    stale_phrases = (
        "pending written organizer guidance",
        "until the organizers clarify",
    )
    for document in public_documents:
        text = document.read_text(encoding="utf-8").lower()
        for phrase in stale_phrases:
            assert phrase not in text, f"stale governance wording in {document.name}"


def test_relative_markdown_links_resolve_without_symlinks() -> None:
    analysis_root = REPO_ROOT / "analysis"
    public_data_root = REPO_ROOT / "public_data"
    documents = sorted(
        {
            *REPO_ROOT.glob("*.md"),
            *(REPO_ROOT / "docs").rglob("*.md"),
            *(analysis_root / "track2").glob("README.md"),
            *(analysis_root / "track2" / "release").glob("*.md"),
            *(analysis_root / "external").glob("*/README.md"),
            *(analysis_root / "external").glob("*/release/*.md"),
            *public_data_root.glob("*.md"),
            *public_data_root.glob("*/README.md"),
        }
    )
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            assert target, f"empty relative link in {document.relative_to(REPO_ROOT)}"

            # abspath normalizes '..' lexically and does not resolve filesystem links.
            candidate = Path(os.path.abspath(document.parent / target))
            try:
                relative = candidate.relative_to(REPO_ROOT)
            except ValueError as exc:
                raise AssertionError(
                    f"relative link escapes repository: {document.name} -> {target}"
                ) from exc

            cursor = REPO_ROOT
            for component in relative.parts:
                cursor = cursor / component
                assert not cursor.is_symlink(), (
                    f"relative link traverses a symlink: {document.name} -> {target}"
                )
            assert candidate.exists(), (
                f"broken relative link: {document.relative_to(REPO_ROOT)} -> {target}"
            )
