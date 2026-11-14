"""Verify the three public scientific release inventories without private inputs."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(relative):
    folder = ROOT / relative
    inventory = folder / "release_inventory.tsv"
    digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    if digest != (folder / "release_inventory.sha256").read_text().split()[0]:
        raise ValueError("Inventory digest differs")
    rows = list(csv.DictReader(inventory.open(encoding="utf-8"), delimiter="\t"))
    seen = set()
    for row in rows:
        path = (folder / row["path"]).resolve()
        if not path.is_relative_to(folder.resolve()) or row["path"] in seen:
            raise ValueError("Unsafe or duplicate release entry")
        seen.add(row["path"])
        payload = path.read_bytes()
        if len(payload) != int(row["bytes"]) or hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError("Scientific release bytes differ")
    return {"release": relative, "files": len(rows), "inventory_sha256": digest, "status": "passed"}


if __name__ == "__main__":
    print(json.dumps([verify(p) for p in ("analysis/track2/release", "analysis/external/GSE185192/release",
                                         "analysis/external/GSE134780/release")], indent=2))
