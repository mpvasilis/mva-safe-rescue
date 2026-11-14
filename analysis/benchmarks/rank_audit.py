"""Show cap-induced rank changes without exporting variants or changing evidence."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rare_mva.track1.builder import _load_document, _prepare_document, _format_epcr
from rare_mva.track1.schema import Variant


def audit(document: dict) -> dict:
    _, prepared = _prepare_document(document)
    rows = document["candidates"]
    signatures = {frozenset(Variant(**v) for v in row["variants"]): i for i, row in enumerate(rows)}
    raw_order = sorted(range(len(rows)), key=lambda i: Decimal(_format_epcr(rows[i]["raw_epcr"])), reverse=True)
    raw_ranks = {i: rank for rank, i in enumerate(raw_order, 1)}
    result = []
    for final_rank, candidate in enumerate(prepared, 1):
        i = signatures[frozenset(candidate.variants)]
        row = rows[i]
        flags = ["synthetic_calibration_cap"]
        if not row["read_validated"]: flags.append("read_review_unvalidated")
        if row["frequency_status"] == "unknown": flags.append("frequency_unknown")
        if row["phase"] == "unresolved": flags.append("phase_unresolved")
        result.append({"input_row": i + 1, "raw_rank": raw_ranks[i], "final_rank": final_rank,
                       "raw_epcr": _format_epcr(row["raw_epcr"]), "final_epcr": candidate.epcr_text,
                       "rank_changed": raw_ranks[i] != final_rank,
                       "score_reduced": Decimal(candidate.epcr_text) < Decimal(_format_epcr(row["raw_epcr"])),
                       "applicable_flags": flags})
    return {"scope": "Private decision-policy audit; not diagnostic accuracy or clinical calibration",
            "candidate_count": len(result), "rank_changed_count": sum(r["rank_changed"] for r in result),
            "review_required": any(r["rank_changed"] or r["score_reduced"] for r in result), "rows": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        destination = args.output.resolve(strict=False)
        if destination.is_relative_to(ROOT):
            raise ValueError("audit output must stay outside the public repository")
        result = audit(_load_document(args.input))
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2); handle.write("\n")
    except (OSError, ValueError, TypeError):
        print("Rank audit failed closed; no evidence or paths printed.", file=sys.stderr)
        return 2
    print("Rank audit saved in the requested external location. Review before release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
