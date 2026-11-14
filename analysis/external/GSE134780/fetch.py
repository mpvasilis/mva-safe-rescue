"""Fetch only the pinned public mouse study and its metadata."""
from __future__ import annotations

import concurrent.futures
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "public_data" / "GSE134780"
HERE = Path(__file__).resolve().parent
URL = "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE134nnn/GSE134780/suppl/GSE134780_counts.txt.gz"
COUNT_SHA = "f12a73805eb3aaf95d666e78756def647a11e95e37bd007dda580bc08ec77cba"
PROTOCOL_SHA = "543a454cfa16fb9397c905640ac00e61b20597f6afafadf03e8c5e84d6da2ead"


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read(10_000_001)
    if len(body) > 10_000_000:
        raise ValueError("public input exceeds expected bound")
    return body


def sample(gsm: str) -> tuple[dict[str, str], dict[str, str | int]]:
    url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gsm}&targ=self&form=text&view=brief"
    raw = download(url)
    (CACHE / f"{gsm}.soft").write_bytes(raw)
    title = [line.split(" = ", 1)[1] for line in raw.decode().splitlines()
             if line.startswith("!Sample_title = ")]
    if len(title) != 1:
        raise ValueError("public sample metadata missing title")
    parts = title[0].split("_")
    if len(parts) != 4 or parts[0] != "10mo" or parts[1] not in {"skM", "fat"} or parts[2] not in {"WT", "HL1002P", "HH"}:
        raise ValueError("unexpected public sample design")
    row = {"sample": title[0], "geo_accession": gsm, "tissue": parts[1],
           "genotype": parts[2], "replicate_label": parts[3],
           "age": "8-10 months", "sex": "not_reported", "pairing": "not_assumed"}
    return row, {"source": gsm, "url": url, "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()}


def main() -> None:
    if hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest() != PROTOCOL_SHA:
        raise ValueError("protocol differs from pre-download lock")
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / "counts.txt.gz"
    raw = dest.read_bytes() if dest.exists() else download(URL)
    if hashlib.sha256(raw).hexdigest() != COUNT_SHA:
        raise ValueError("public counts hash mismatch")
    dest.write_bytes(raw)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        gathered = list(pool.map(sample, [f"GSM{i}" for i in range(3968592, 3968615)]))
    with (HERE / "samples.tsv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(gathered[0][0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row, _ in gathered)
    receipts = [{"source": "counts", "url": URL, "bytes": len(raw), "sha256": COUNT_SHA}]
    receipts.extend(receipt for _, receipt in gathered)
    (HERE / "sources.json").write_text(json.dumps({"retrieved_on": datetime.now(timezone.utc).date().isoformat(), "protocol_sha256": PROTOCOL_SHA, "sources": receipts}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "verified", "samples": len(gathered), "count_sha256": COUNT_SHA}))


if __name__ == "__main__":
    main()
