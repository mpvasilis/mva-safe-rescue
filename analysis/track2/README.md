# SAC/CIN Safe Rescue: Track 2 public-data pipeline

This is a CPU-only R 4.6 / Bioconductor 3.23 analysis of public Drosophila whole-brain RNA-seq counts with fixed analysis settings and checksum-pinned inputs. No package lockfile is present, so the reproducibility claim covers those fixed settings and pinned inputs, not byte-identical cross-machine output. The analysis is designed to support a bounded thesis about pathways downstream of SAC depletion/chromosomal instability (CIN). It does **not** make a BUB1B-specific, clinical, or treatment claim.

## Scientific scope and claim boundary

GSE290206 is primary. It contains six female whole-brain libraries collected at 96 hours AEL and 29 °C, with three brains per library and a control/CIN pair in each of batches 4, 5, and 6. The experimental construct depletes `bub3`; therefore the study provides SAC-depletion/CIN pathway evidence, not evidence specific to BUB1B.

GSE301548 is adversarial/exploratory only. Its controls were dissected at 5 days AEL and trisomies at 8 days AEL, so genotype is perfectly confounded with chronological age. `CDXX_vs_CDXY` and `T2L_vs_C2L` estimate combined age+genotype contrasts. They are never described as matched, replication, a negative control, or identifiable genotype effects, and are excluded from primary inference and candidate ranking.

Both studies profile whole brain, so changes in tissue or cell composition can contribute to apparent expression effects. Named candidates are prospective preclinical benchmarks only; none is transcriptomically validated or preferred, and none is used to select genes, define modules, alter thresholds, or manufacture transcriptomic support.

## Reproduce

Run commands from the repository root. The first command is intentionally lightweight and works before package installation:

```text
Rscript analysis/track2/run.R --dry-run
Rscript analysis/track2/bootstrap.R
Rscript analysis/track2/run.R --validate-only --download
Rscript analysis/track2/tests/testthat.R
Rscript analysis/track2/run.R
```

`bootstrap.R` installs the declared packages into `analysis/track2/.Rlib` without administrator access or changes to the global R library. It requires R 4.6.x and checks that Bioconductor reports version 3.23. If `Rscript` is not on `PATH`, invoke the R 4.6.x executable installed on that machine.

No lockfile is hand-authored or present. `results/package_versions.tsv` explicitly records R, Bioconductor, and every declared or directly used analysis package, including packages that may not remain loaded when the final reporting target runs. `results/sessionInfo.txt` supplements this with the namespaces loaded by that reporting process. A future bootstrap can still resolve newer packages within R 4.6/Bioconductor 3.23, so the workflow claims deterministic settings and checksum-pinned inputs, not byte-identical cross-machine outputs. A lockfile should be added only if genuinely generated and tested in a compatible clean environment.

The downloader retrieves all sources from official public HTTPS endpoints into `public_data/`, verifies exact SHA-256 values before accepting them, and refuses to silently overwrite an invalid existing file. Workbooks additionally require their exact sheet, dimensions, and ordered headers. Downloaded binaries are ignored by Git.

## Prespecified methods

- Seed `20260826`, one CPU, and 9,999 rotations are fixed.
- Count matrices must have exact public dimensions and headers, unique canonical FBgn IDs, and finite nonnegative integer counts. The source objects are never mutated. Genes are retained at at least 10 counts in at least three libraries, and raw/retained library totals are reported.
- Primary DE uses DESeq2 design `~ batch + condition`, a Wald CIN-versus-control coefficient, and apeglm shrinkage. Cook outliers are neither automatically replaced nor censored from results. VST values are used only for QC and `roastgsa`, never for gene-level DE.
- A primary gene-level call requires BH q ≤ 0.10, absolute shrunken fold change ≥ 1.25, and agreement with the shrunken direction in at least two of three within-batch raw-count log ratios. The full continuous Wald statistic is retained for every tested gene; no significance cutoff is used to manufacture enrichment or human signatures.
- Leave-one-batch-out gene-level analyses refit DESeq2 and VST after each omission, then report shrunken and unshrunk effect-direction concordance and Spearman correlation with the full fit as diagnostics only. Omission-specific apeglm warnings are retained verbatim; unshrunk DESeq2 metrics are reported separately so shrinkage warnings are not hidden. Separate module-level fits use the corresponding omission-specific VST and rerun competitive maxmean testing with 9,999 rotations and BH correction over the same 13 configured modules. For every evaluable module/omission they report direction and adjusted significance. A separate direction-driver overlap diagnostic compares the top 20% by absolute continuous Wald statistic among genes agreeing with the roastgsa NES direction; this is **not** a formal roastgsa or GSEA leading edge and does not alter rotation p-values, q-values, or the downgrade verdict. The amended diagnostic result is marked for downgrade if a module in the post-primary fixed nomination set reverses direction, or if a full-analysis set module at BH q ≤ 0.10 loses that support when a batch is omitted (single-block dependence). With only three pairs, this workflow does not claim an exact permutation p-value below 0.05.
- The seven-module nomination decision subset is a dated post-primary implementation amendment, not part of the original 13-module analysis lock. It was fixed on 2026-08-26 before the module-level leave-one-batch sensitivity rerun and is encoded in `primary_modules.tsv`: `mitochondrial_energy`, `proteostasis_stress`, `folding_proteasome`, `autophagy_mitophagy`, `oxidative_stress`, `oxidant_detox`, and `ribosome_RNA`. It operationalizes the mitochondrial/proteostasis hypothesis as mitochondrial energy, direct stress/folding/proteasome machinery, downstream autophagy/mitophagy quality control, oxidative stress/detoxification, and ribosome/RNA burden. Direction reversals or single-block dependence in that set determine the amended diagnostic downgrade flag. Results for all 13 modules in the original analysis lock are exported, but SAC, chromosome-segregation, neural-stemness, cell-cycle, DNA-damage/repair, and apoptosis reversals cannot change that amended sensitivity verdict. If the full module result is null, a reversal is descriptive instability evidence, not statistically meaningful enrichment or a second inferential rejection.
- The raw-count 2-of-3 direction rule remains the locked primary gene gate. A result-neutral sensitivity recomputes direction agreement with DESeq2-normalized counts and exports gene-level and summary comparisons; it never replaces the raw gate.
- Thirteen modules were prespecified and analysis-locked in `config/primary_modules.tsv` before the authoritative run. There is no immutable external preregistration timestamp; historical output filenames and JSON keys containing `preregistered` are retained only for compatibility and do not assert external preregistration. GO descendants are traversed only through `is_a` and `part_of`. GAF annotations with `NOT` or `ND` are excluded. The primary module analysis includes IEA; a separate sensitivity excludes IEA. `roastgsa` uses competitive maxmean testing over every retained, measured gene with 9,999 rotations. The authoritative `module_qvalue` applies BH with `n=13` configured modules and is the only adjusted value used for decisions. The exported `roastgsa_adj_pvalue_evaluable_only` is retained transparently but adjusts over evaluable sets only and is not a decision column. Continuous Wald mean/maxmean summaries are also exported; genome-wide investigations beyond these modules are exploratory.
- Directional sanity checks expect `bub3` down; `Hsp70Ba`, `Hsp70Bb`, `Hsp70Bc`, `Hsp70Bbb`, and `GstE8` up; and mitochondrial-energy and ribosome/RNA modules down. Failures remain visible and never change the data or thresholds.
- GSE301548 uses `~ batch + condition` only within each combined contrast. X-contrast size factors use mapped non-X genes; 2L-contrast size factors use mapped genes outside 2L. A duplicated-region dosage summary is descriptive and does not repair the age confounding.
- Primary orthology retains mappings with DIOPT ≥ 5, selects the maximum score per fly gene, splits that fly gene's weight over co-best human ties, and combines fly Wald statistics per human gene as `sum(w*z) / sqrt(sum(w^2))`. The sensitivity uses every DIOPT ≥ 3 mapping weighted by its within-fly DIOPT share. Every mapping and decision is audited.

## Outputs

Generated artifacts are written only under `analysis/track2/results/` and are ignored by Git. They include:

- copied registries and observed source checksums;
- QC JSON, library totals, and VST PCA coordinates;
- the complete primary DE table and the thresholded subset;
- primary and no-IEA module scores plus module-construction audits;
- gzip-compressed gene-level results, module direction/q-value and direction-driver overlap tables, summaries, and a module-based leave-one-batch-out stability verdict;
- both exploratory combined age+genotype contrasts, chromosome-aware size factors, duplicated-region dosage checks, and a prominent interpretation warning;
- primary and sensitivity human signatures, a compact cross-policy robustness summary, and the full gzip-compressed TSV orthology mapping audit;
- sanity-check tables, plots, `package_versions.tsv`, `sessionInfo.txt`, a result inventory, and its checksums.

A compact, tracked `release/` snapshot is refreshed from an explicit whitelist after every successful results target. It contains only public aggregate and small review artifacts, plus a SHA-256 inventory; bulky full DE, exploratory gene tables, human signatures, and orthology audits remain excluded.

The FlyBase RPKM matrix is checksum-pinned and downloaded for provenance, but it is deliberately not used to alter RNA-seq evidence, module definitions, or ranking.

## Protocol implementation amendment

The executable enrichment implementation is sample-level `roastgsa`, not a one-column rank test. It supplies the retained-gene VST matrix, the full-rank `~ batch + condition` design, and the CIN coefficient to competitive maxmean rotation testing. This matches the declared `roastgsa` method and preserves exchangeability at the sample/design level. The complete DESeq2 Wald statistic remains continuous and unthresholded in gene-level exports, descriptive module Wald summaries, orthology, and the explicitly non-inferential direction-driver overlap diagnostic.

The registry always contains 13 modules, but `roastgsa` requires at least 10 measured genes. The primary include-IEA analysis currently has 12 evaluable modules; `neural_stemness` has eight measured genes and is reported as NA. The no-IEA sensitivity currently has 11 evaluable modules; `neural_stemness` and `oxidant_detox` (six genes) are reported as NA. BH adjustment remains conservative with `n=13` configured modules. These counts are computed into the result summary rather than assumed.

Two descriptive instabilities remain prominent without changing the null primary branch. `proteostasis_stress` changes from full-analysis module q=0.547625 to q=0.0013 only after batch 5 is omitted; this fragile n=4 sensitivity cannot override the full null. Excluding IEA flips `folding_proteasome` from NES=-1.178407, q=0.69966 to NES=1.425172, q=0.43238; both annotation policies remain null. Exact values and interpretation are exported in the leave-one-batch and annotation-policy tables and in `analysis_summary.json`.

## Prespecified null-module branch

If zero evaluable primary modules reach BH q ≤ 0.10, the result is the null-module branch: the transcriptomics does not validate a specific rescue candidate. Nominal module p-values, stable gene directions, leave-one-batch diagnostics, exploratory GSE301548 contrasts, or orthology cannot promote that branch into pathway or treatment support. The machine-readable summary states this independently of the module-level downgrade flag.
