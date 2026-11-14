# GSE185192 external public challenge — release snapshot

This small snapshot reports a fixed-seed, one-CPU reanalysis with deterministic settings and recorded software versions of public untreated HTSeq counts from [GEO GSE185192](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192). The priority contrast is NPC Iso-T versus Iso-E; untreated iPSC Iso-T versus Iso-E is a separate lineage control. The contrasts are never pooled. No lockfile or byte-identical cross-machine reproduction claim is made.

The seven modules were configured and locked for this original external analysis before its authoritative run. They have no external preregistration timestamp and are not presented as externally preregistered. `locked_module_results.tsv` retains every configured row; `module_qvalue_BH_n7_authoritative` is the only decision q-value. The package-supplied evaluable-only adjustment is labeled nondecision and is not used in summaries or figures.

NPC full analysis: 20711 retained genes, 1/7 locked modules at BH q <= 0.10. NPC chromosome-21-excluded sensitivity: 20530 retained genes, 1/7 modules at q <= 0.10.
iPSC full analysis: 18046 retained genes, 2/7 locked modules at BH q <= 0.10. iPSC chromosome-21-excluded sensitivity: 17895 retained genes, 1/7 modules at q <= 0.10.

## Non-negotiable inference boundary

Iso-E and Iso-T are one isogenic derivative pair from AG05397. The three deposited count files per state are repeated cultures/libraries, not three independent donors. Genotype is perfectly confounded with derivative line, so DESeq2 p-values and rotation p-values are descriptive within this pair and cannot establish population-level replication.

GSE185192 is a constitutive trisomy-21/Down-syndrome isogenic context. It is not MVA, not SAC depletion, and not evidence of ongoing chromosome mis-segregation or chromosomal instability. It is used only as an aneuploid neural-context stress test.

This external analysis cannot rescue or override the primary fly null: zero of 12 evaluable primary modules reached BH q <= 0.10, and leave-one-block-out direction reversals occurred for folding/proteasome and oxidative-stress modules. Human-versus-fly comparison is sign/effect description only—there is no pooled statistic, meta-analysis, candidate nomination, clinical claim, or dosing guidance.

## Reproduce and inspect

Run `Rscript analysis/external/GSE185192/bootstrap.R`, then `Rscript analysis/external/GSE185192/run.R`. Use `--download-only`, `--test`, or `--verify-release` for the corresponding bounded operation. `GSE185192_CACHE_DIR` may override the default relative public cache. The run fixes seed 20260826, 9,999 rotations, and one CPU. DESeq2 uses `~ condition` with Iso-E as reference, Cook's-distance censoring disabled, automatic count replacement disabled, and independent filtering enabled.

Inputs were retrieved on 2026-08-26–27 (exact per-source UTC timestamps are in the manifest) and are not redistributed in this snapshot. `manifests/sources.tsv` pins exact HTTPS URLs, byte counts, and SHA-256 values; `sample_eligibility.tsv` exposes every eligibility check. `gencode_mapping_audit.tsv` reports mapped, unmapped, ambiguous, and chromosome-21-excluded symbol counts. `package_versions.tsv` records the direct and key statistical packages used. `manifests/full_result_hashes.tsv` ties this compact release to the four exact ignored full-DE tables by relative path, byte count, and SHA-256. Review [NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/) and source-specific terms before reuse.

Primary sources and annotation references: [Meharena et al., Cell Stem Cell (PMC8805993)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8805993/), [versioned GO 2026-08-05 basic ontology](https://release.geneontology.org/2026-08-05/ontology/go-basic.obo), matching dated [GO 2026-08-05 HUMAN-UniProt GAF](https://release.geneontology.org/2026-08-05/annotations/gaf/HUMAN-uniprot.gaf.gz), and [GENCODE v19](https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_19/gencode.v19.annotation.gtf.gz).

`release_inventory.tsv` hashes every snapshot artifact except itself; `release_inventory.sha256` hashes that inventory.
