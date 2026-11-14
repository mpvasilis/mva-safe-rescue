# MVA Safe Rescue: a contradiction-first comparative screen after SAC depletion/CIN

**Track 2 detailed report, public-data section**  
Public evidence reviewed through: 2026-09-09 (mouse extension and decision comparison)
Primary module/data lock: 2026-08-26  
Submission deadline: 2026-10-24 23:59 UTC

> **Release boundary:** This public report leaves the controlled case-to-mechanism bridge empty until an authorized segregated analysis confirms the applicable disease-gene branch. No FASTQ, VCF, BAM, CRAM, source clinical document, genome-scale intermediate, credential, or cloud access detail is part of this repository. Nothing in this report is treatment advice.

## Executive decision

The principal Track 2 innovation is the **Safe Rescue Envelope**. A compound must restore neural output and orthogonal mitochondrial function at the same two adjacent noncytotoxic exposures while chromosome-error, abnormal-clone persistence, malignant-fitness, invasion, and chemotherapy-resistance gates can veto apparent benefit. Benefit and harm are not averaged into one score: any hard stop, failed control, conflicting confirmation, or indeterminate safety result is no-go.

Sirolimus is the worked example. In the published SAC/CIN fly context, rapamycin increased aneuploid neural-stem-cell count without restoring differentiated progeny or brain size. A survival-only score could call that favorable; Safe Rescue classifies it as an uncoupled-rescue control and no-go pattern.

We therefore recommend a **comparative preclinical investigation**, not a treatment nomination. Arimoclomol is the first experimental proteostasis probe; elamipretide is the orthogonal mitochondrial benchmark. Sirolimus is the same-model uncoupled-rescue control, everolimus is the translational mTOR-class comparator, and acetylcysteine is the redox-direction control. This ordering is designed to discriminate mechanisms. It is not a clinical lead hierarchy, and every compound may correctly receive a no-go result.

The public transcriptomic analysis is a stress test of that decision discipline, not a drug-nomination engine. In six fly whole-brain libraries forming three matched pairs, 179 genes passed the fixed gene-level criteria, including `bub3` down and a correlated Hsp70-family signal plus `GstE8` up. However, zero of 12 evaluable modules passed BH `q <= 0.10`. Mitochondrial energy had `q=.734`; nominal ribosome/RNA, autophagy/mitophagy, and apoptosis results at `q=.198` are hypothesis-generating only. Leave-one-block-out module analysis requires a downgrade because folding/proteasome and oxidative-stress directions reverse. The honest inference is therefore a **null-module branch**: published SAC/CIN phenotypes justify a falsifiable experiment, but this transcriptome does not validate the pathway or prefer a medication.

The new [conditional mechanism bridge](MECHANISM_BRIDGE.md) makes the five-compound
comparison and decisive falsifiers explicit. The [mouse extension](../analysis/external/GSE134780/README.md)
adds independently analyzed public genotype/tissue context: 17/84 predeclared
panel tests pass the fixed effect and BH thresholds, without a coherent HSP70
or cardiolipin-panel result and without any candidate-response measurement.
It does not change the primary fly null or the candidate roles.

## 1. Claim boundary and local-only case bridge

The public challenge material does not identify BUB1B (or any other gene) as this case's causal gene. Public sources establish that BUB1B/BUBR1 can participate in an MVA mechanism, while the primary public experiment directly depletes fly `bub3`. These are related SAC/CIN contexts, not interchangeable genes or variant models.

> **LOCAL-ONLY GATED VARIANT CHARACTERIZATION. DO NOT COMMIT OR COPY INTO A PUBLIC ARTIFACT.** In the authorized segregated workflow, record the actual gene, variant(s), phase/zygosity, molecular consequence, evidence strength, phenotype fit, and the reason a public mechanism branch applies. If the local result does not support the SAC/CIN branch used here, revise or stop the submission. Do not infer or fill this section from the public fly result.

The public evidence chain is deliberately conditional:

1. authorized local analysis confirms the actual case mechanism;
2. only the matching public mechanism branch is selected;
3. public SAC-depletion/CIN evidence defines downstream stress phenotypes;
4. the locked transcriptomic test reports a null module result rather than manufacturing support;
5. approved medications enter a comparative falsification screen; and
6. noncompensatory genome and oncology safety gates decide advancement.

## 2. Safe Rescue architecture and public evidence hierarchy

Conventional mechanism-match ranking can reward any biochemical improvement. Safe Rescue requires benefit and safety to answer different questions, and a safety failure cannot be averaged away. Sirolimus demonstrates the distinction in the same public model context: an increased aneuploid neural-stem-cell count without restored differentiated progeny or brain size is uncoupled rescue, not functional recovery. The same logic makes context-specific tumor invasion or chemotherapy protection decisive falsifiers for otherwise plausible mitochondrial or stress-response probes.

| Evidence layer | Role | What it cannot establish |
|---|---|---|
| GSE290206, six fly whole-brain libraries | Primary paired transcriptomic test after `bub3` depletion | BUB1B-specific effects, a gated variant mechanism, a human neural effect, or drug efficacy |
| Associated SAC/CIN fly study | Published downstream proteostasis, mitochondrial, ROS, neural-output, and rescue premise | Transcriptomic replication, human translation, or safety of the five compounds |
| GSE185192 untreated isogenic trisomy-21 NPC and iPSC contrasts | Appendix-level human-neural dosage context | MVA or SAC-depletion modeling, evidence of ongoing chromosome mis-segregation/CIN, independent-donor replication, or rescue of the primary null |
| GSE301548 | Exploratory age-plus-genotype dosage check | An identifiable genotype effect or candidate ranking |
| Current labels, regulatory pages, trials, and primary studies | Exact indication, exposure, mechanistic, efficacy, and contradiction facts | MVA efficacy, dose, suitability, or safety |
| Safe Rescue Envelope | Proposed noncompensatory research-screening rules, to be calibrated and frozen before confirmation | Clinical thresholds, validated margins, or treatment recommendations |

No counts, transformed matrices, effects, p-values, or samples are pooled across datasets, tissues, platforms, or species. No proprietary source was used.

## 3. Public computational stress-test methods

### 3.1 Dataset and estimand

GSE290206 contains six female Drosophila whole-brain RNA-seq libraries collected at 96 hours AEL and 29 °C. Each library pools three brains. Batches 4, 5, and 6 each contain one `bub3-RNAi` and one `GFP-RNAi` control library. The primary estimand is `bub3-RNAi - GFP-RNAi` under the paired design `~ batch + condition`. Whole-brain cell-composition changes remain unresolved.

Inputs are downloaded from pinned public URLs into a local ignored cache. The workflow records byte counts, verifies SHA-256 and schema, and checks samples against the locked manifest. Counts must be nonnegative integers with unique, aligned gene identifiers. Genes with count `>=10` in at least three libraries are retained; 10,132 genes passed.

### 3.2 Gene-level analysis

DESeq2 estimates size factors and fits the negative-binomial Wald model. Cook's outlier replacement and Cook's p-value censoring are disabled; independent filtering remains enabled. `apeglm` supplies shrunken log2 fold changes. Raw-count and DESeq2-normalized within-pair log ratios use a fixed `+0.5` pseudocount. A fixed gene-level call requires:

- gene-level BH `q <= 0.10`;
- absolute shrunken fold change `>=1.25`; and
- agreement with the shrunken direction in at least two of the three within-block raw-count log ratios.

DESeq2-normalized within-block directions are a result-neutral sensitivity, not a replacement gate. VST values are not used for gene-level differential-expression testing.

### 3.3 Module analysis

Thirteen GO modules were prespecified in the original analysis lock. There is no immutable external preregistration timestamp; historical filenames containing `preregistered` are compatibility identifiers, not evidence of external timestamping. GO descendants use only `is_a` and `part_of`; annotations with `NOT` or `ND` are excluded. The primary policy includes IEA, and a separate sensitivity excludes IEA. Sets require at least 10 measured genes.

The authoritative module analysis supplies sample-level VST expression to `roastgsa` under the paired design and CIN contrast. It uses competitive normalized maxmean testing, residual shrinkage, one CPU, seed `20260826`, and 9,999 rotations. BH correction uses `n=13` configured modules even when a module is unevaluable. Continuous Wald mean/maxmean summaries are auxiliary.

The executable roastgsa method replaces early protocol text that described a one-column rank analysis. The exact seven-module influence-verdict subset is a dated **post-primary implementation amendment**, fixed before module leave-one-block-out analysis. It cannot alter the full-analysis p-values, q-values, module membership, eligibility, or null branch.

### 3.4 Robustness and annotation checks

Each leave-one-block-out analysis refits DESeq2, VST, and the 13 module tests. Gene-level Spearman correlation, direction concordance, and q-and-shrunken-effect retention are descriptive influence diagnostics. The block-6 `apeglm` fit emitted eight line-search warnings; therefore unshrunk DESeq2 effect diagnostics are reported separately. Module reversals are instability evidence, not new significant enrichment.

The orthology audit compares two explicit fly-to-human mapping policies. It is used to expose mapping dependence, not to manufacture a human signature or candidate score.

## 4. Public computational stress-test results

### 4.1 Gene-level result

The locked analysis retained 10,132 genes and called 179. The normalized-direction sensitivity called the identical 179 genes even though the raw and normalized agreement counts differed for 1,859 genes.

| Sanity gene | Shrunken log2 FC | BH q | Raw direction blocks | Interpretation |
|---|---:|---:|---:|---|
| `bub3` | -0.521 | .0267 | 3/3 | Confirms target depletion direction in this fly experiment |
| `Hsp70Ba` | 2.495 | <.001 | 3/3 | One member of a correlated Hsp70-family signal |
| `Hsp70Bb` | 2.872 | <.001 | 3/3 | Same family signal; not independent replication |
| `Hsp70Bc` | 2.429 | <.001 | 3/3 | Same family signal; not Hsp60/Hsp60c rescue evidence |
| `Hsp70Bbb` | 2.353 | <.001 | 3/3 | Same family signal; not a significant proteostasis module |
| `GstE8` | 2.154 | .00787 | 3/3 | Single detoxification gene, not pathway replication |

All 179 calls retained shrunken and unshrunk effect direction in every omission. Only 58, 72, and 39 retained the q-and-shrunken-effect criteria after omitting blocks 4, 5, and 6. Shrunken-effect Spearman correlations with the full fit were .835, .734, and .936; the separate unshrunk correlations were .807, .746, and .893. These are influence diagnostics with four libraries per refit, not independent validation.

### 4.2 Complete module decision

Thirteen modules were configured; 12 were evaluable under the primary include-IEA policy and 11 under the no-IEA sensitivity. Zero primary modules reached BH `q <= 0.10`.

| Module | NES | Rotation p | BH q | Decision |
|---|---:|---:|---:|---|
| mitochondrial energy | -1.021 | .3965 | .734 | Null |
| proteostasis stress | 1.497 | .1685 | .548 | Null |
| folding/proteasome | -1.178 | .2691 | .700 | Null |
| autophagy/mitophagy | 1.790 | .0457 | .198 | Hypothesis-generating only |
| oxidative stress | .423 | .7123 | .772 | Null |
| ribosome/RNA | -1.790 | .0341 | .198 | Hypothesis-generating only |
| apoptosis | 1.573 | .0351 | .198 | Hypothesis-generating only |

The influence verdict is **DOWNGRADE**:

- folding/proteasome reverses direction after omitting blocks 4 or 6;
- oxidative stress reverses direction after omitting blocks 4 or 6;
- proteostasis stress reaches `q=.0013` only after omitting block 5, versus `q=.548` in the full analysis; and
- excluding IEA flips the null folding/proteasome NES from -1.178 to +1.425; both annotation policies remain null.

The isolated omission result and null-policy sign flip are fragility evidence. Neither may replace the locked full-analysis null.

## 5. Candidate decision dossier

The selection process is contradiction-first. Positive dimensions and cancer/CIN hazard are scored separately from 0 to 4; no arithmetic total is used because a hard-stop hazard cannot be compensated by regulatory convenience or CNS exposure.

| Compound | Experimental role | Why it is informative | Decisive limitation or contradiction |
|---|---|---|---|
| arimoclomol | First proteostasis probe | Approved with miglustat for neurological NPC from age 2; dose-dependent human CSF exposure; measurable HSF1/HSP70 axis | NPC clinical mechanism is unknown; fly rescue used Hsp60/Hsp60c; full proteostasis module is null; ALS phase 3 was negative; HSF1 stress tolerance demands clone/chemotherapy gates |
| elamipretide | Orthogonal mitochondrial benchmark | Cardiolipin/inner-membrane mechanism and current Barth-syndrome label make mitochondrial pharmacology testable | Mitochondrial module is null; broader mitochondrial-myopathy phase 3 missed both primary outcomes; candidate-specific cancer-cell invasion and cytotoxic-protection reports |
| sirolimus | Same-model assay control | Rapamycin was directly tested in the SAC/CIN fly model | Increased aneuploid neural-stem-cell count without restoring differentiated progeny or brain size |
| everolimus | Translational mTOR-class comparator | Pediatric TSC CNS experience in another disease | Anti-proliferative and immunosuppressive context; cannot override the same-model sirolimus result or null autophagy module |
| acetylcysteine | Redox-direction control | Glutathione target engagement and human CSF exposure are measurable | Repeated context-specific tumor, metastasis, and chemotherapy-protection contradictions; oxidative-stress module is null and unstable |

Full row-level sources, scores, counterevidence, falsifiers, and advance rules are in [CANDIDATE_SCORECARD.tsv](CANDIDATE_SCORECARD.tsv) and [CANDIDATE_RATIONALE.md](CANDIDATE_RATIONALE.md). A bounded post-panel refresh on 2026-08-27 is documented in the [candidate-search protocol](CANDIDATE_SEARCH_PROTOCOL.md) and its [machine-readable log](CANDIDATE_SEARCH_LOG.tsv). Three broad PubMed queries returned 564, 79, and 301 records; deterministic subsets contained 227 unique PMIDs. Twelve candidate-specific bridge searches, 12 current DailyMed checks, and two ClinicalTrials.gov queries found no direct public MVA medicine trial and no evidence sufficient to change the five experimental roles. This was a non-systematic refresh after the panel and primary result were known (not independent validation) and named human curation sign-off remains required before submission.

## 6. Decisive next experiment

Conditional on authorized local case analysis selecting and justifying a compatible SAC-gene branch, use one karyotypically normal parental human iPSC line with an AAVS1-integrated, inducible dCas9-KRAB system targeting `AUTHORIZED_CASE_SELECTED_SAC_GENE`; matched isogenic comparators carry non-targeting guides. Qualification requires concordant deficient-state phenotypes from at least two independent non-overlapping targeting guides before a lead guide is frozen using only target-engagement and assay-quality information. The placeholder must be selected only by authorized local analysis, never inferred from the public fly or trisomy-21 results. If the authorized mechanism is incompatible with inducible partial SAC deficiency, this design is inapplicable and must not be forced onto the case. Use blinded assessment, blocked randomization by independent culture initiation/differentiation run, and treatment only after CIN is established. Compare vehicle, arimoclomol, elamipretide, sirolimus, everolimus, and acetylcysteine over a noncytotoxic concentration series selected from target engagement and tolerability, not clinical doses.

After qualification, the primary advancement family contains exactly two vehicle-controlled hypotheses: whether arimoclomol versus vehicle and whether elamipretide versus vehicle improve the one prespecified neural endpoint (**day-21 live MAP2+TUBB3+ neuron yield per 100 starting viable PAX6+SOX2+ NPCs**) at both independently selected adjacent exposures. Exactly two co-required mitochondrial benefit endpoints must also pass at both exposures: **day-21 ATP-linked oxygen-consumption rate per viable cell** and **day-21 TMRM membrane-potential signal per mitochondrial mass**. Sirolimus, everolimus, and acetylcysteine are controls and cannot advance in this family; a direct arimoclomol-versus-elamipretide ranking is secondary unless separately powered and prespecified. Neural identity, differentiation fidelity, viability, and tissue-level function remain required support or veto outcomes; they are not interchangeable alternatives to the primary endpoint. Other mechanistic and safety measurements include HSF1/HSP70/HSP60 engagement, aggregate and proteasome burden, mitochondrial ROS, true mitophagy flux, mitotic timing, lagging chromosomes, bridges, micronuclei, and longitudinal single-cell karyotype/clone tracking; none becomes a third mitochondrial benefit endpoint after outcomes are seen.

Confirm any vehicle-qualified candidate with the second independent guide or a prespecified orthogonal complementation/rescue model, then in another neural model and the published fly paradigm or a faithful equivalent. Discordance blocks a gene-specific rescue claim and advancement. In parallel, test p53-intact and p53-deficient CIN tumor models, invasion, and representative chemotherapy co-exposure. A prespecified replicated increase in abnormal-clone persistence, malignant fitness, invasion, or chemotherapy survival (or an interval supporting material harm) is a hard stop. A confidence interval crossing a calibrated margin is indeterminate/no-advance, not by itself proof of harm.

The current 16-gate contract is [SAFE_RESCUE_ENVELOPE.tsv](SAFE_RESCUE_ENVELOPE.tsv). Its numerical margins are provisional screening values, not validated or clinical thresholds. Qualification and confirmatory stages are separated: one neural primary endpoint, exactly two mitochondrial endpoints, two independently selected adjacent doses, biological-run replication, blocked randomization, blinded assessment, hierarchical models, multiplicity control, objective missingness/exclusion rules, and simulation-based sample-size and margin calibration must be frozen before confirmatory outcomes. The full design specification is [CONFIRMATORY_EXPERIMENT_DESIGN.md](CONFIRMATORY_EXPERIMENT_DESIGN.md).

The [public power-sensitivity analysis](../analysis/design_power/README.md) is an auditable planning aid, not a sample-size justification. In its central illustrative variability scenario, the probability that all three benefit endpoints pass at both doses is `.3741` for a common true benefit of `0.70 SD` with `n=32`, versus `.8377` for `1.00 SD` with `n=24`, each tested against a provisional `0.20-SD` margin. These benefit-only probabilities are conditional on every safety veto passing; they are not advancement power and no row is a sample-size recommendation. Safety-bound precision, quality-control loss, or a prespecified sensitivity analysis may require more biological runs than benefit power and determine the final run count.

## 7. Potential impact and scalability

### Potential impact

If (and only if) the authorized case analysis supports this SAC/CIN branch, the immediate decision changes from “which approved drug sounds mechanistically plausible?” to “which, if any, produces lineage-correct neural benefit without preserving harmful aneuploid or malignant cells?” Qualification can stop an unsuitable model or unmeasurable assay before an expensive candidate comparison. Confirmation can stop a compound for lack of functional benefit, chromosome-error worsening, abnormal-clone persistence, malignant fitness, invasion, or chemotherapy protection. A clean no-go is useful: it prevents a weak or cytoprotective signal from being mistaken for patient benefit.

For MVA research, the contribution is a transparent way to connect a case mechanism to falsifiable preclinical choices while retaining negative results and safety contradictions. For other rare-disease programs, the transferable idea is not these five compounds or uncalibrated margins; it is the staged separation of model qualification, benefit, mechanism, and noncompensatory harm. The work does not diagnose the child, recommend treatment, or claim clinical impact before independent validation.

### Scalability

The public computational layer already runs on one CPU and uses explicit dataset adapters, pinned sources, fixed seeds, machine-readable manifests, claim-level provenance, and closed release inventories. It has been exercised on a paired fly SAC-depletion dataset; a separate appendix-level human trisomy-21 neural context uses different identifiers, organisms, designs, and sensitivity rules. That demonstrates portability of the evidence discipline, not general biological validity. Transfer beyond SAC/CIN requires a new case-mechanism bridge, assay and margin calibration, and an independent benchmark. Final clean-clone wall time, peak memory, storage, and cost remain to be recorded before any quantitative scalability claim.

## 8. Strengths and limitations

Strengths are the exact paired estimand, checksum-verified public inputs, complete module reporting, conservative BH denominator, explicit method amendment, two annotation policies, gene- and module-level influence diagnostics, contradiction-seeking drug review, machine-readable claim ledger, and safety vetoes that cannot be averaged away.

Limitations are decisive. The primary dataset has three pairs, profiles pooled whole brain, and directly perturbs `bub3`, not BUB1B or a gated variant. Cell composition is unresolved. No configured module met the predefined support threshold; with this small design, that is non-support rather than evidence that the biology is absent. Selected null-module directions are also fragile under block omission and annotation policy. The gene-level candidate set is not a medication-ranking signature. The external human dataset is one derivative pair. No proposed compound was tested in the primary transcriptomic experiment, and there is no MVA efficacy, dose, clinical-safety, or patient-suitability evidence. The release now includes exact package locks; clean restoration and reproduction on another operating system remain distinct verification steps.

## 9. Reproducibility and governance

The public workflow is CPU-only, uses fixed seed `20260826` and one-core settings, and is reproducible when rerun in the recorded package environment. It separates ignored upstream/results stores from a small tracked aggregate release. Exact dependency locks and version checks are now supplied in analysis/environment; a version match alone does not prove a clean restore or cross-platform scientific reproduction. The release inventory and SHA-256 checksum must verify before submission. A fresh anonymous clone must reproduce every public link and output before the final upload.

Automated steps include download verification, metadata/count validation, filtering, DESeq2, roastgsa, influence refits, orthology-policy comparison, figure/export generation, release hashing, schema tests, and privacy scanning. Public-source discovery, eligibility assessment, contradiction seeking, code review, visual QA, claim-boundary review, and drafting sit outside the automated pipeline. Human review remains responsible for every scientific and regulatory claim. No FASTQ, VCF, BAM, CRAM, source clinical document, genome-scale intermediate, credential, or cloud access detail entered this repository.

The organizer's 2026-08-27 clarification permits a hosted service only when it takes no rights in inputs or outputs, performs no training on them, and limits retention by purpose and time; teams must record the provider, plan/tier, and settings. Controlled challenge files and genome-scale derivatives remained in an authorized segregated workflow. Raw genomic files, copies/reformats, genome-scale variant intermediates, stored variant-data prompts, and models trained on the genome fall inside the organizer's deletion boundary; approved findings such as the ranked candidate list, HPO terms, gene/pathway analyses, and drug candidates may survive.

Run from the repository root:

```console
Rscript analysis/track2/run.R --dry-run
Rscript analysis/track2/bootstrap.R
Rscript analysis/track2/run.R --validate-only --download
Rscript analysis/track2/tests/testthat.R
Rscript analysis/track2/run.R
python -m pytest -q
python -m rare_mva privacy-scan .
```

Review [the aggregate Track 2 release](../analysis/track2/release/README.md), [the computational protocol](TRACK2_PROTOCOL.md), [the claim ledger](CLAIM_LEDGER.tsv), and [the data-governance policy](../DATA_GOVERNANCE.md).

## 10. Claims and nonclaims

**Supported public claims:** the exact public model and estimand; the 179 fixed-criteria fly gene calls; the complete null module result; the influence and annotation fragility; exact current label facts; published context-specific efficacy and oncology contradictions; and the proposed preclinical decision rules.

**Unsupported or prohibited claims:** that a public dataset identifies the gated causal gene or variant; that `bub3-RNAi` reproduces a BUB1B allele; that the transcriptome validates mitochondrial or proteostasis rescue; that any compound treats MVA; any clinical dose, individual suitability, or safety conclusion; and any promotion of an external, nominal, orthology, or leave-one-out result over the primary null.

## 11. Acknowledgement and dataset citation

> *This work was made possible through the Hackathon, organized by Sage Bionetworks in partnership with the MVA Society, Hugging Face, and BEACON (The Benchmarking, Evaluation, and Assessment Consortium for Science), with prize sponsorship from AWS and Anthropic. We are deeply grateful to the child and their family who generously contributed their data and their story to advance research into this rare disease. We acknowledge their trust in making this Hackathon possible.*

Challenge citation: Sage Bionetworks. *Rare Disease, Real Kid. The 2026 MVA Hackathon*. Synapse project `syn76251147`, accessed 2026-08-27, https://www.synapse.org/Synapse:syn76251147/wiki/642892.

## Appendix A. Context-only human-neural analysis

GSE185192 is retained as appendix-level contextual evidence, not a headline result. It was analyzed as two separate untreated contrasts: `Iso-T - Iso-E` in NPCs is the priority, and the analogous iPSC contrast is a lineage control. This is a constitutive trisomy-21/Down-syndrome isogenic context, not MVA, SAC depletion, or evidence of ongoing chromosome mis-segregation/CIN. Each comparison contains three deposited cultures/libraries per state but represents one AG05397 derivative pair. Genotype and derivative line are therefore perfectly confounded, and there is no independent-donor replication. The p-values, q-values, and differential-expression counts below describe separation within that pair; they do not support population inference.

| Lineage | Sensitivity | Retained genes | Genes q<=.10; also \|LFC\|>=.5 | Locked modules q<=.10 | Exact module result |
|---|---|---:|---:|---:|---|
| NPC | Full | 20,711 | 11,633; 7,068 | 1/7 | ribosome/RNA down, NES -2.446, q=.0189 |
| NPC | Chr21 excluded | 20,530 | 11,490; 6,962 | 1/7 | ribosome/RNA down, NES -2.430, q=.0231 |
| iPSC | Full | 18,046 | 4,281; 1,084 | 2/7 | oxidative stress down, NES -2.066, q=.0133; folding/proteasome down, NES -2.069, q=.0963 |
| iPSC | Chr21 excluded | 17,895 | 4,089; 1,010 | 1/7 | oxidative stress down, NES -2.023, q=.0147; folding/proteasome q=.1068 |

The full analyses show the expected chromosome-21 dosage context: median chromosome-21 log2 fold change is +0.557 in NPCs and +0.534 in iPSCs, versus approximately zero off chromosome 21. Excluding all 517 GENCODE-v19 symbols mapped to chromosome 21 leaves the NPC ribosome/RNA result and iPSC oxidative-stress result below the locked BH threshold. The iPSC folding/proteasome result crosses from q=.0963 to q=.1068, so it is explicitly threshold-sensitive.

The NPC ribosome/RNA direction agrees with the fly direction, but the fly full-analysis module is null at q=.198. The iPSC oxidative-stress direction is opposite the fly direction. These are descriptive cross-context comparisons only: there is no pooled statistic, no replication claim, and no promotion of a candidate. The external result cannot rescue the primary fly 0/12 module result or its leave-one-block-out downgrade. Exact outputs and limitations are in the [checksum-verified GSE185192 release](../analysis/external/GSE185192/release/README.md).

## Key public sources

- Challenge overview and rubric: https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/blob/main/tabs/about.py
- Track 2 submission instructions: https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/blob/main/tabs/submit_track2.py
- Challenge rules: https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/blob/main/tabs/rules.py
- Organizer privacy and compliance clarification: https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/2
- Synapse challenge project: https://www.synapse.org/Synapse:syn76251147/wiki/642892
- GSE290206: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE290206
- SAC/CIN study: https://pubmed.ncbi.nlm.nih.gov/41820377/
- GSE185192: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192
- Candidate source dossier: [CANDIDATE_RATIONALE.md](CANDIDATE_RATIONALE.md)
