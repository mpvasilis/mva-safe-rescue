# MVA Safe Rescue: a contradiction-first, phenotype-first framework for SAC-deficiency/CIN

**Computational protocol and dated implementation amendment, explicitly not a clinical protocol**

Version 1.2, original computational lock dated 2026-08-26; Safe Rescue design amendment dated 2026-08-27

This protocol governs a public-data research submission. It does **not** propose treatment, establish a drug mechanism in MVA, or contain patient-level facts. The Safe Rescue framework begins with phenotypes and safety vetoes; compounds enter only as falsifiable test articles.

## Settled public result and decision boundary

**Defensible headline.** Public paired fly-brain transcriptomics identifies 179 directionally stable gene-level calls/influence-analysis directions (`bub3`/Bub3 down; `Hsp70Ba`, `Hsp70Bb`, `Hsp70Bc`, `Hsp70Bbb`, and `GstE8` up), but zero of 12 evaluable primary modules reach BH `q <= 0.10`. Thirteen modules were configured, 12 were evaluable in the primary include-IEA analysis, and 11 were evaluable in the no-IEA sensitivity. The mitochondrial-energy module has `q=.734`. The nominal `q=.198` signals for ribosome/RNA, autophagy/mitophagy, and apoptosis are hypothesis-generating only.

“Directionally stable” is deliberately limited to influence-analysis direction. All 179 full-analysis calls retain direction in each leave-one-batch-out refit, but only 58, 72, and 39 retain the `q`-and-shrunken-effect thresholds when batches 4, 5, and 6 are omitted, respectively. The leave-one-out Spearman correlations are 0.835, 0.734, and 0.936. A result-neutral sensitivity that uses DESeq2-normalized-count directions produces the identical set of 179 calls; it does not replace the locked raw-count direction gate. The report must not call the 179 genes unqualified “batch-stable.”

The primary result therefore takes the **null-module branch**: transcriptomics does not validate a mitochondrial/proteostasis program, a specific rescue mechanism, or a rescue candidate. External challenges, nominal module results, orthology, exploratory contrasts, or direction stability cannot rescue that null primary conclusion.

The module influence verdict is **DOWNGRADE**. Folding/proteasome and oxidative-stress reverse direction when blocks 4 or 6 are omitted. Proteostasis/stress reaches `q=.0013` only after omitting block 5, despite the full-analysis `q=.548`; that isolated sensitivity is fragility evidence and cannot replace the locked full result. Excluding IEA also flips folding/proteasome from NES `-1.178` to `+1.425`, while both annotation policies remain null. The batch-6 gene-level shrunken-effect fit emitted eight retained apeglm line-search warnings, so the shrunken diagnostics are reported with an unshrunk-effect sensitivity and never called fully verified.

## Question and estimand

**Question.** Can public evidence define a falsifiable, safety-gated phenotype-first screen for downstream consequences of spindle-assembly-checkpoint (SAC) deficiency and chromosomal instability (CIN), while allowing null transcriptomic evidence to stop candidate-specific claims?

**Primary estimand.** In GSE290206 whole fly brain, estimate `bub3-RNAi - GFP-RNAi` across three paired experimental blocks, using `~ batch + condition` at gene level and the paired design at module level. This is SAC-depletion/CIN pathway evidence; it is not a BUB1B-specific experimental result. Whole-brain composition remains unresolved, so expression changes cannot be assigned to a cell type or assumed cell-autonomous.

**Candidate interpretation.** Use a comparative experiment, not a transcriptomically nominated winner. Arimoclomol is the first experimental proteostasis probe because its pediatric neurological rare-disease experience, human CSF exposure, and proximal HSF1/HSP70 readouts make it testable. This priority is not efficacy evidence: the four Hsp70 calls are one correlated family signal, the full proteostasis module is null, the published fly rescue used Hsp60/Hsp60c rather than HSP70, the current NPC label says the clinical mechanism is unknown, and a phase 3 ALS trial was negative. Elamipretide is the orthogonal mitochondrial benchmark, not a second treatment lead. Its cardiolipin mechanism is testable, but mitochondrial energy is null and candidate-specific cancer-cell studies create invasion and chemotherapy-protection vetoes. The advancement family contains exactly two vehicle-controlled hypotheses, arimoclomol versus vehicle and elamipretide versus vehicle; their direct ranking is secondary unless separately powered. Sirolimus, everolimus, and acetylcysteine serve as same-model, mTOR-class, and redox controls and cannot advance in this family. No panel member is established as effective, safe, suitable, or dosable for MVA.

## Public SAC/CIN model and gated boundary

Public sources describe BUB1B/BUBR1 as one established spindle-checkpoint component whose loss of function can cause an MVA mechanism. However, the public challenge material does not identify BUB1B as this case's causal gene. The public report may explain the SAC-depletion, chromosome-segregation-error, and CIN biology tested in public models; it may use a BUB1B branch only after the authorized local workflow confirms that the branch applies.

The report must not infer that the fly `bub3-RNAi` contrast reproduces a particular human BUB1B allele or establish the consequence of any gated variant.

> **LOCAL-ONLY GATED VARIANT CHARACTERIZATION PLACEHOLDER. DO NOT COMMIT OR COPY INTO PUBLIC ARTIFACTS.** Insert actual variant, zygosity/phase, evidence, phenotype, and case-specific interpretation only inside the authorized segregated workflow and only if the challenge rules permit that use. The public repository leaves this placeholder unfilled and invents no patient fact.

## Evidence hierarchy and datasets

1. **Primary dataset: GSE290206.** Six public whole-brain libraries form three `bub3-RNAi`/`GFP-RNAi` pairs. This dataset supports the bounded result above.
2. **Mechanistic anchor.** The associated fly study reports proteostasis failure, mitochondrial dysfunction, and genetic rescue experiments downstream of complex aneuploidy. Those published experiments are separate evidence from this null-module transcriptomic reanalysis.
3. **Human neural dosage context: GSE185192.** The priority untreated comparison is the isogenic `Iso-T` versus `Iso-E` NPC RNA-seq contrast. The untreated iPSC `Iso-T` versus `Iso-E` contrast is a lineage control. This is one constitutive trisomy-21/Down-syndrome derivative pair (not MVA, SAC depletion, or evidence of ongoing chromosome mis-segregation/CIN) and not independent biological replication across donors.
4. **Deferred optional cancer/CIN context: GSE47830.** This dataset is not analyzed in the current release and must not be presented as completed evidence. If added before the submission freeze, analyze `HPT1` and `HPT2` separately, each only against the diploid comparator measured on the same microarray platform. These HCT116-derived complex-aneuploid contexts would be safety/contradiction evidence, not neural or disease replication.
5. **Exploratory only: GSE301548.** Genotype is perfectly confounded with chronological age: controls are 5 days AEL and trisomy samples are 8 days AEL. Its contrasts estimate combined age plus genotype and cannot support primary inference, candidate ranking, or trisomy-specific claims.
6. **Pharmacology and safety context.** Label and regulatory sources establish only their exact product facts. Published cancer studies are contradiction-seeking context, not proof of safety or harm in MVA.

No counts, effects, p-values, samples, or transformed matrices are pooled across datasets, platforms, tissues, or species. External analyses test generalizability and contradiction; they cannot promote or rescue the null primary module result.

## Locked gene-level analysis

- Use deposited GSE290206 gene-level raw counts and public sample metadata; verify identities, paired blocks, count integrality, library sizes, and design rank.
- Retain genes with counts `>=10` in `>=3` libraries. Use seed `20260826` and one CPU, and record package, annotation, and reference versions.
- Fit DESeq2 with design `~ batch + condition`, reference `GFP-RNAi`, and report the Wald effect `bub3-RNAi - GFP-RNAi`. Apply BH at gene level and shrink log2 fold changes with `apeglm`.
- A primary gene-level call requires `q <= 0.10`, absolute shrunken fold change `>=1.25`, and agreement with the shrunken direction in at least two of three within-batch raw-count log ratios. Zero differences do not support a direction.
- VST is never used for gene-level differential-expression testing. It is used for QC/display and, under the amendment below, sample-level module testing.

## Configured GO modules

The 13 modules and GO roots remain fixed in `analysis/track2/config/primary_modules.tsv`:

| Order | Module ID | Module label | GO ID(s) |
|---:|---|---|---|
| 1 | SAC | Spindle assembly checkpoint | GO:0031577 |
| 2 | chromosome_segregation | Chromosome segregation | GO:0007059 |
| 3 | mitochondrial_energy | Mitochondrial energy | GO:0006119; GO:0022904; GO:0032543; GO:0005761 |
| 4 | proteostasis_stress | Proteostasis stress | GO:0006986; GO:0030968 |
| 5 | folding_proteasome | Folding and proteasome | GO:0006457; GO:0010498; GO:0000502 |
| 6 | autophagy_mitophagy | Autophagy and mitophagy | GO:0006914; GO:0000422 |
| 7 | oxidative_stress | Oxidative stress | GO:0006979 |
| 8 | oxidant_detox | Oxidant detoxification | GO:0098869 |
| 9 | ribosome_RNA | Ribosome and RNA | GO:0042254; GO:0006396 |
| 10 | neural_stemness | Neural stemness | GO:0097150 |
| 11 | cell_cycle_proliferation | Cell cycle and proliferation | GO:0000278; GO:0008283 |
| 12 | DNA_damage_repair | DNA damage and repair | GO:0006974; GO:0006281 |
| 13 | apoptosis | Apoptosis | GO:0006915 |

All 13 configured modules above belong to the original analysis lock. The exact seven-module nomination-verdict subset (`mitochondrial_energy`, `proteostasis_stress`, `folding_proteasome`, `autophagy_mitophagy`, `oxidative_stress`, `oxidant_detox`, and `ribosome_RNA`) is a dated **post-primary operational amendment** fixed before the module-level leave-one-batch-out runs. It delimits which biologically relevant reversals can trigger the amended diagnostic downgrade; it cannot alter any full-analysis module p-value, q-value, eligibility decision, or the null branch. The other six original modules remain visible diagnostics. No result-dependent GO term or threshold may be added.

## Dated implementation amendment, 2026-08-26

The original pathway text described a one-column continuous Wald-ranking analysis. The implemented and authoritative primary module test is instead sample-level VST expression supplied to `roastgsa` with the paired `~ batch + condition` design and the CIN coefficient, using competitive (`self.contained=FALSE`) normalized maxmean testing, residual shrinkage, one CPU, and 9,999 rotations. This amendment records the executable method; it does not relax a threshold, add any of the 13 original modules, or reinterpret a favorable result. It also records the seven-module post-primary verdict subset above, fixed before the module influence runs and unable to change the locked full-analysis null.

- Modules require at least 10 measured genes. All 13 remain in outputs, with unevaluable modules shown as `NA`.
- Primary annotations include IEA while excluding `NOT` and `ND`; the sensitivity excludes IEA. GO descendants use only `is_a` and `part_of`.
- BH adjustment uses `n=13` configured modules even when 12 primary or 11 no-IEA modules are evaluable.
- Complete continuous DESeq2 Wald mean/maxmean summaries remain auxiliary and descriptive. They are not the module p-value calculation.
- The direction-driver diagnostic takes the top 20% by absolute Wald statistic among module genes agreeing with the roastgsa NES direction. Its overlap across omissions is **not** a formal GSEA or roastgsa leading edge, does not affect rotation p/q values, and does not set the verdict.

## Influence analyses and decision rules

Each leave-one-batch-out analysis refits DESeq2, VST, and the module test. Gene-level Spearman and direction concordance are influence diagnostics only. For the post-primary seven-module verdict subset, a downgrade is triggered by a direction reversal or by loss of `q <= 0.10` after an omission when the full module met that threshold. For a null full module, a reversal is descriptive instability, not a second inferential rejection.

Result branches are:

- **Null primary modules:** state that transcriptomics did not validate a pathway or candidate; retain only the phenotype-first framework and published mechanistic premise.
- **Supported primary module plus concordant external context:** describe broader consistency with model and tissue caveats; never claim universality.
- **Supported primary module but absent or discordant externally:** narrow to the fly context and report the contradiction.
- **Influence downgrade:** report dependence/reversal and do not replace the threshold.

The current analysis is the null-primary-module branch.

## Orthology

- Primary fly-to-human mapping admits DIOPT scores `>=5`, retains maximum-score/co-best human orthologs, and splits a fly gene's weight across co-best ties.
- Multiple fly contributors are combined by weighted signed Stouffer aggregation: `Z_h = sum_i(w_ih * Z_i) / sqrt(sum_i(w_ih^2))`.
- Sensitivity retains DIOPT pairs `>=3` with score weighting. The complete identifier-level audit remains public; symbols alone are never used for mapping.
- Orthology supports comparison, not equivalence of genes, tissues, organisms, diseases, or treatment response, and cannot rescue the null primary module result.

## Safe Rescue and nonclaims

The Safe Rescue Envelope is reusable across candidates within the proposed SAC/CIN screening context, but its present numerical margins are provisional. A qualification stage must verify and calibrate the conditional AAVS1-integrated, inducible dCas9-KRAB human iPSC neural model, whose public targeting placeholder is `AUTHORIZED_CASE_SELECTED_SAC_GENE` and whose isogenic comparators use non-targeting guides. Authorized local case analysis must select and justify the gene branch; if it does not support inducible partial SAC deficiency, this model is inapplicable. At least two independent non-overlapping guides must show concordant deficient-state phenotypes before one lead guide is frozen without candidate outcomes; any apparent pass requires second-guide or orthogonal complementation/rescue confirmation. Qualification must also verify the named primary endpoint (day-21 live MAP2+TUBB3+ neuron yield per 100 starting viable PAX6+SOX2+ progenitors) plus exactly two mitochondrial endpoints: day-21 ATP-linked oxygen-consumption rate per viable cell and day-21 TMRM membrane-potential signal per mitochondrial mass. Those six endpoint-dose comparisons are the complete affirmative benefit family; mitophagy, high-aneuploid fitness, and proteotoxic-stress diagnostics may explain or veto but cannot add benefit passes. The assays, two adjacent target-engaging noncytotoxic doses per candidate, margins, and analysis plan must be frozen without access to confirmatory treatment outcomes. A candidate advances only if all three endpoints pass at both doses while every applicable chromosome-error, clone-persistence, malignant-fitness, invasion, and chemotherapy-resistance gate passes. A prespecified replicated adverse signal or an interval supporting material harm is a hard stop. A confidence interval that merely crosses a margin is indeterminate/no-advance, not proof of harm. Failed controls, conflicting confirmation, or unresolved safety are also no-advance. The [confirmatory design](CONFIRMATORY_EXPERIMENT_DESIGN.md) and [public deterministic power sensitivity](../analysis/design_power/README.md) make the benefit rule executable, but the sensitivity is not advancement power or a sample-size recommendation; qualification, confirmation, and safety-bound precision must determine the final run count. Transfer to another mechanism or disease requires separate calibration and validation.

Permitted claims are limited to public mechanism, model-specific association, the exact null result, and a falsifiable preclinical screening proposal. Prohibited claims include clinical efficacy, dose, suitability for an individual, MVA treatment status, causal patient mechanism, variant-specific interpretation in public artifacts, BUB1B-specific transcriptional effects from `bub3-RNAi`, or safety in a cancer-predisposed population.

## Public sources

- GSE290206: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE290206
- GSE301548: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE301548
- GSE185192: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192
- GSE47830: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE47830
- NCBI BUB1B Gene record: https://www.ncbi.nlm.nih.gov/gene/701
- Public BUB1B/MVA genetic association: https://pubmed.ncbi.nlm.nih.gov/15475955/
- Public mechanistic fly paper: https://pubmed.ncbi.nlm.nih.gov/41820377/
- DIOPT/FlyBase: https://www.flyrnai.org/diopt
