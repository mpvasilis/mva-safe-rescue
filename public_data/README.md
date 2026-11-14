# Public data cache and provenance boundary

This directory is a local, reproducible cache for checksum-pinned public inputs used by the Track 2 analysis. Its purpose is source retrieval and verification, not source redistribution. Downloaded workbooks and archives are ignored by Git; the public repository carries URLs, accessions, release identifiers, structural expectations, checksums, methods, and derived aggregate results instead.

**Recorded retrieval dates:** 2026-08-26 to 27; exact per-source UTC timestamps are in the manifests.

No private, controlled, patient-level, challenge-gated, proprietary-database, or credential-bearing material belongs here. Actual challenge-variant characterization remains in an authorized segregated workflow and must not be copied into this cache, Git history, or public reports. Any hosted processor used in that controlled workflow requires documented organizer-compatible terms, settings, and approval; none was used for gated data in this public work.

## Retrieve and validate

Run from the repository root:

```console
Rscript analysis/track2/run.R --dry-run
Rscript analysis/track2/run.R --validate-only --download
Rscript analysis/external/GSE185192/run.R --download-only
```

The primary fly registry is [`analysis/track2/config/source_manifest.tsv`](../analysis/track2/config/source_manifest.tsv); the separate human-neural challenge registry is [`analysis/external/GSE185192/config/sources.tsv`](../analysis/external/GSE185192/config/sources.tsv). They record official HTTPS endpoints, local relative destinations, exact SHA-256 values, expected structures, analysis roles, retrieval dates, and cautious usage notes. Both downloaders reject a checksum mismatch and do not silently overwrite an invalid existing file.

## Registered sources

### NCBI GEO

- **GSE290206**: primary whole-fly-brain raw-count workbook: 14,150 unique FBgn rows by six libraries, sheet `rawcounts(2)`, range `A1:G14151`, SHA-256 `8ca3791e8a69284403f41698ef9af3fa9efbe47b3978c6bcacd906f282a747e9`.
- **GSE301548**: exploratory age-plus-genotype-confounded whole-brain raw-count workbook: 8,990 unique FBgn rows by 15 libraries, sheet `rawcounts_lbarrio_brain`, range `A1:P8991`, SHA-256 `d35eb3c42787a2137bfe453a32b2fc9772e602eeee69a2ca46e154be92993b18`.
- **GSE185192**: implemented as a separate public human-neural contextual challenge. Its registry pins 12 untreated per-sample HTSeq files, 12 exact sample SOFT records, GO/GOA references, and GENCODE v19. NPC and iPSC contrasts are fitted separately; this is one isogenic derivative pair, not independent-donor replication, and cannot rescue the primary fly null.
- **GSE47830**: planned cancer/CIN contextual challenge. Before use, each exact input, checksum, platform/contrast decision, and retrieval date must be registered. No unregistered download may enter an authoritative result.

Accession and usage-status references:

- GSE290206: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE290206
- GSE301548: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE301548
- GSE185192: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192
- GSE47830: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE47830
- NCBI website and molecular-data usage policies: https://www.ncbi.nlm.nih.gov/home/about/policies/
- GEO documentation and citation guidance: https://www.ncbi.nlm.nih.gov/geo/info/

**Usage-status boundary:** These files are publicly retrievable from GEO. This repository does not assert that NCBI transferred a file-level license or every underlying submitter right. Source attribution, accession citations, and any applicable submitter or publication terms must be reviewed before release. Cached source files are not redistributed here.

### FlyBase FB2026_02

The registry pins the following public FB2026_02 files from official FlyBase HTTPS endpoints:

- Drosophila-to-human DIOPT ortholog table;
- gene symbol and chromosome-arm map;
- Gene Ontology annotation file;
- FlyBase-hosted GO basic ontology snapshot; and
- an RPKM matrix retained for provenance only and not used to alter evidence or ranking.

Usage-status and attribution references:

- FlyBase release/download origin: https://flybase.org/ and https://s3ftp.flybase.org/
- FlyBase about/licensing statement: https://wiki.flybase.org/wiki/FlyBase%3AAbout
- FlyBase citation guidance: https://wiki.flybase.org/wiki/FlyBase%3ACiting_FlyBase
- Required attribution: “We used FlyBase (release FB2026_02) to obtain data.” Cite Öztürk-Çolak et al. (2024), *FlyBase: updates to the Drosophila genes and genomes database*, *Genetics* 227(1):iyad211, https://doi.org/10.1093/genetics/iyad211.

**Usage-status boundary:** FlyBase describes FlyBase-produced annotations and data as CC BY 4.0, while also warning that incorporated third-party resources can carry different terms. The manifest records provenance rather than making a blanket license claim for every downloaded byte. The GO snapshot and any upstream content require their own release review.

## Redistribution and reviewer responsibilities

- Do not commit, mirror, attach, or repackage downloaded source binaries in this repository or release bundle.
- Publish the registry, source URLs, retrieval dates, expected structures, checksums, code, and aggregate derived outputs so reviewers can retrieve the same public sources directly.
- A provenance reviewer verifies that each URL resolves to the stated accession/release, the downloaded file matches its checksum and declared structure, attribution is present, and the analysis purpose matches the registry.
- The reviewer records unresolved usage questions in the release checklist and can block redistribution. Review is not legal advice, does not transfer rights, and must not be described as a license grant.
- **Provenance preflight:** 2026-08-27, working-tree source manifests retrieved 2026-08-26 to 27 with exact per-source UTC timestamps. Official FlyBase licensing/citation wording, public GEO/NCBI policy links, checksums, non-redistribution boundary, and analysis purposes reviewed; no source binaries are released. Disposition: computational use and aggregate release may proceed subject to exact checksum verification. This is not legal advice.
- **Final human sign-off:** pending. Before public freeze, a named team provenance reviewer must confirm the exact committed manifest revision, attribution, any unresolved upstream GO/submitter terms, and release disposition.

The final release review must reconcile this page, the source manifest, generated checksums, citations, acknowledgements, and the public report without introducing machine-specific paths.
