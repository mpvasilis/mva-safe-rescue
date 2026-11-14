# GSE185192 untreated isogenic neural challenge

This directory implements the first external public challenge for Track 2. It reanalyzes only the untreated HTSeq count files from [GEO GSE185192](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192): NPC Iso-T versus Iso-E is the priority contrast, and iPSC Iso-T versus Iso-E is a separately fitted lineage control. The two lineages are never pooled. The workflow fixes seed/CPU/method settings and records package versions; without a tested lockfile it does not claim byte-identical cross-machine output.

## Design and claim boundary

The selected samples are GSM5617616 to GSM5617627: three deposited RNA-seq counts for each lineage/state combination. Every sample must pass exact checks against its downloaded GEO SOFT record for accession, Homo sapiens, RNA-Seq, untreated status, AG05397, expected cell type, expected Control/Down syndrome strain label, and expected HTSeq filename.

Iso-E and Iso-T are one isogenic derivative pair. The three files per state are repeated cultures/libraries from that pair, not independent donors. Genotype is therefore perfectly confounded with derivative line. DESeq2 and rotation p-values are descriptive within this pair and do not establish population replication. This external analysis cannot rescue the primary fly result (0/12 evaluable modules at BH q <= 0.10) or erase its leave-one-block-out direction reversals for folding/proteasome and oxidative stress. It cannot validate a rescue candidate, therapeutic efficacy, clinical use, or dosing.

GSE185192 models a constitutive trisomy-21/Down-syndrome isogenic context. It is not mosaic variegated aneuploidy (MVA), not spindle-assembly-checkpoint depletion, and not evidence of ongoing chromosome mis-segregation or chromosomal instability. Its role here is limited to an aneuploid neural-context stress test.

## Locked analysis

The seven modules were configured and locked for this original external analysis before its authoritative run. There is no external preregistration timestamp, and they are not described as externally preregistered.

- One CPU, fixed seed 20260826, and 9,999 rotations.
- Separate DESeq2 `~ condition` models for NPC and iPSC, with Iso-E as reference; no cross-lineage coefficient or pooling. Cook's-distance p-value censoring and automatic count replacement are disabled; DESeq2 independent filtering remains enabled.
- Genes retained at count >= 10 in at least three samples within a lineage/analysis.
- A full fit and a chromosome-21-excluded sensitivity for each lineage. The sensitivity removes any count symbol mapped to chromosome 21 in GENCODE v19, then refits filtering, size factors, dispersion, Wald model, VST, and module test.
- Seven configured, original analysis-locked modules: mitochondrial energy, proteostasis stress, folding/proteasome, autophagy/mitophagy, oxidative stress, oxidant detoxification, and ribosome/RNA. The dated GO HUMAN-UniProt GAF's DB Object Symbol annotations include IEA and exclude `NOT` and `ND`; descendants traverse only `is_a` and `part_of` in the pinned GO graph.
- Competitive `roastgsa` maxmean testing uses the sample-level VST matrix. The authoritative BH q-value is computed with `n=7` over all seven configured modules in each of the four analyses. All nulls and unevaluable rows remain visible. The package-supplied evaluable-only adjusted p-value is explicitly labeled nondecision and is never used in summaries or plots.
- The checksum-pinned fly module table is compared by NES/sign/q only. There is no pooled test, meta-analysis, or cross-species significance claim.

## Reproduce

From the repository root:

```text
Rscript analysis/external/GSE185192/bootstrap.R
Rscript analysis/external/GSE185192/run.R --download-only
Rscript analysis/external/GSE185192/run.R --test
Rscript analysis/external/GSE185192/run.R
Rscript analysis/external/GSE185192/run.R --verify-release
```

The default public cache is `public_data/GSE185192/`. Set `GSE185192_CACHE_DIR` to another repository-relative or absolute local directory if required; paths written to public outputs remain relative. `bootstrap.R` creates a local ignored `.Rlib`. The pipeline is portable `Rscript` code and never invokes a GPU.

`config/sources.tsv` pins the 12 count files, 12 sample-level SOFT records, and three required annotation references by HTTPS URL, byte count, SHA-256, and exact per-source UTC retrieval time (2026-08-26 to 27). Missing files are downloaded to a temporary part file and accepted only after checksum/size validation. An invalid existing file is never silently overwritten. Upstream counts and annotations are ignored and are not included in `release/`.

Complete DE tables are written only to ignored `results/`. The tracked `release/` snapshot contains eligibility checks, source verification, library/QC summaries, GENCODE mapped/unmapped/ambiguous/chromosome-21-exclusion audit counts, exact package versions, PCA coordinates, compact top-DE excerpts, all 28 module rows, all 28 descriptive fly comparisons, two figures, machine-readable limitations, session information, and a SHA-256 inventory.

## Sources and use notes

- Dataset and deposited metadata/counts: [NCBI GEO GSE185192](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192).
- Primary study: [Meharena et al., *Cell Stem Cell*, PMC8805993](https://pmc.ncbi.nlm.nih.gov/articles/PMC8805993/).
- Ontology: [versioned GO 2026-08-05 basic OBO](https://release.geneontology.org/2026-08-05/ontology/go-basic.obo) (the file declares `data-version: releases/2026-07-26`).
- Human GO annotations: [GO 2026-08-05 HUMAN-UniProt GAF](https://release.geneontology.org/2026-08-05/annotations/gaf/HUMAN-uniprot.gaf.gz), aligned to the same dated GO release as the ontology and pinned by byte count and SHA-256.
- Genome annotation aligned to the authors' GRCh37/GENCODE19 workflow: [GENCODE v19 GTF](https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_19/gencode.v19.annotation.gtf.gz).
- Usage policy: [NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/).

These are publicly retrievable research files, but this repository does not assert a blanket file-level license transfer or redistribute the source bytes. Reusers must cite the accession/publication, preserve GO/GENCODE attribution, and review source-specific terms. The tracked manifests provide provenance, not legal advice or a new license grant.
