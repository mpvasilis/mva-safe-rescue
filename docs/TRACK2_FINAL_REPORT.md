# MVA Safe Rescue

Track 2 report for Rare Disease, Real Kid: the 2026 MVA Hackathon. 9 September 2026.

## Summary

Cells in mosaic variegated aneuploidy (MVA) mis-segregate chromosomes, so a compound that helps stressed cells survive can also keep abnormal clones alive. We propose a comparative preclinical screen in which a benefit in neurons cannot offset chromosome or oncology harm.

We would investigate arimoclomol as a proteostasis probe and elamipretide as a second, mitochondrial benchmark, on the condition that a qualified review of the case mechanism supports the model. Sirolimus, everolimus and acetylcysteine are controls. No compound showed a benefit for MVA in this work.

| What the evidence supports | What it means for the decision |
|---|---|
| Fly brain analysis: 179 gene calls, 0 of 12 modules supported. | We do not nominate a drug from this transcriptome. |
| Mouse analysis: 23 samples, 17 of 84 predeclared panel tests meet both thresholds. | Target engagement has to be measured in the qualified neural model. RNA changes are not drug-response evidence. |
| Executable Safe Rescue decisions with synthetic comparisons. | Missing safety data, failed function or confirmed harm each block advancement. |

The next experiment qualifies the model with two independent guides, then tests one neural endpoint and two mitochondrial endpoints at both locked exposures. Every applicable safety gate has to pass, and an apparent pass needs independent confirmation. Both candidates may fail, and the design counts that as a valid result.

What we contribute is a decision process that can be inspected step by step and that keeps null results and contradictions in view. Its purpose is to stop abnormal-cell survival from being read as functional rescue. The rules can be reused, but the mechanism, assays and margins have to be qualified again in each new context.

This report is a preclinical proposal backed by reproducible public evidence. It makes no claim about clinical dose, treatment or efficacy in MVA, and the model stays conditional on a compatible case mechanism.

## What the data say

### Fly brain: the null result stands

GSE290206 has six whole-brain libraries in three paired blocks after bub3 depletion. The model is batch plus condition. Fixed gene-level criteria give 179 calls, and none of the 12 evaluable primary modules reaches BH q <= 0.10. Mitochondrial energy has q = 0.734. Some module directions reverse in sensitivity analyses. We do not treat the gene list as a signature for ranking medicines. [1]

### Mouse: genotype and tissue context

GSE134780 has 23 public samples from WT, H/L1002P and H/H mice in skeletal muscle and fat. We wrote and hashed the plan before looking at counts. It fixed 14 genes, three contrasts per tissue, one BH family of 84 tests, q <= 0.10 and an absolute log2 fold change of at least log2(1.25). Seventeen tests meet both criteria. None of them is the direct H/L1002P versus H/H contrast. [2]

| Selected result | Log2 change | Panel q |
|---|---|---|
| Hsf1, fat, H/L1002P versus WT | +0.373 | 0.0423 |
| Hsf1, fat, H/H versus WT | +0.433 | 0.0152 |
| Hspd1, muscle, H/H versus WT | -0.390 | 0.00890 |
| Sod2, fat, H/L1002P versus WT | -0.980 | 0.0210 |
| Gpx1, muscle, H/H versus WT | +0.490 | 0.0234 |

The complete 84-row panel is released, including null and unavailable results. No Hspa1a, Hspa1b, Hspa8, Crls1 or Taz test meets both criteria. Cdkn2a and Cdkn1a were predeclared as contextual controls, and Cdkn1a moves in opposite directions in muscle and fat. Taken together, the panel shows scattered expression changes and no coherent HSP70 or cardiolipin response.

The limits are small groups, mixed genetic background, unreported sex, exact age and litter, bulk-tissue composition, non-neural tissue and the absence of any drug intervention. We do not pool across species or claim replication of human MVA. The source study's corrigendum concerns Figure 2E and the mitotic-index methods and reports no correction to RNA-seq counts. [3]

The human GSE185192 results stay at appendix level. They describe trisomy 21 in one derivative cell-line pair, which is a different condition from MVA, and they do not change the fly null. Full provenance and limitations are in the [detailed report](REPORT_DRAFT.md) and the public analysis releases.

## Why these five compounds

We ask whether modulating downstream stress responses can restore neural output of the correct lineage after a compatible checkpoint defect, without preserving harmful clones. Stress tolerance does not repair a causal allele, and we do not claim that it does. The authorized case review has to select the mechanism, because partial depletion cannot stand in for every missense allele or every MVA subtype.

| Test article | Role and main limitation |
|---|---|
| Arimoclomol | Proteostasis / HSF1-HSP70 probe. The published fly rescue used Hsp60/Hsp60c, and these interventions are not interchangeable. There is no MVA drug-response measurement, so engagement must be demonstrated. |
| Elamipretide | Second, mitochondrial benchmark. Neither the fly mitochondrial module nor the mouse cardiolipin panel supports a response claim. Requires orthogonal functional benefit. |
| Sirolimus / rapamycin | Same-model control for uncoupled rescue. The published fly treatment increased aneuploid neural stem-cell count without restoring differentiated progeny or brain size. This is not a clinical harm finding. |
| Everolimus | Translational mTOR-class comparator. Class similarity does not prove an identical response in the model. Cannot advance in this family. |
| Acetylcysteine | Redox-direction control. A biochemical change alone does not establish neural benefit or acceptable clone behavior. Cannot advance. |

The chain of evidence we require runs from the reviewed case mechanism to a qualified model, then target engagement, neural and mitochondrial benefit, all safety gates and independent confirmation.

Arimoclomol and elamipretide are two eligible experimental hypotheses. We do not rank them as clinical leads. A mechanism match is the reason to test them, and Safe Rescue decides whether the evidence is enough to advance. The two approaches can disagree, and that disagreement is not an accuracy score.

Public pharmacology, label records and the contradictory studies for each candidate are kept in [CANDIDATE_RATIONALE.md](CANDIDATE_RATIONALE.md) and [CLAIM_LEDGER.tsv](CLAIM_LEDGER.tsv). The same-model premise comes from [4] and the mouse context from [2, 3]. Approval in another indication establishes nothing about efficacy, clinical safety, suitability or dose in MVA.

## The proposed experiment

### 1. Qualify the mechanism and the model

Use an isogenic human iPSC neural system only if the authorized case analysis supports inducible partial deficiency of the selected checkpoint gene. Two independent guides have to produce concordant deficient-state phenotypes, with target engagement, differentiation fidelity and assay controls in place. If the mechanism is incompatible, revise the design or stop this branch.

### 2. Freeze the comparison before any outcome is seen

Compare each eligible candidate with vehicle at two adjacent noncytotoxic exposures chosen independently. Doses are selected on engagement and tolerability, never on favorable rescue outcomes. Randomize in blocks by independent culture initiation or differentiation run, and blind the outcome assessment. Ranking the candidates against each other is secondary unless separately powered.

| All three benefits, at both exposures | Fixed endpoint |
|---|---|
| Neural primary | Day-21 live MAP2+TUBB3+ neuron yield per 100 starting viable PAX6+SOX2+ NPCs. |
| Mitochondrial benefit 1 | Day-21 ATP-linked oxygen consumption per viable cell. |
| Mitochondrial benefit 2 | Day-21 TMRM membrane-potential signal per mitochondrial mass. |

### 3. Keep safety as a veto

Assess chromosome errors, abnormal-clone persistence, aneuploid selectivity, malignant fitness, invasion and chemotherapy resistance across the applicable exposures and models. Confirmed material harm is a veto. Missing evidence, or an interval that crosses an uncertainty margin, also means no advancement, although it is not proof of harm.

### 4. Confirm independently

Confirm with a second guide or a prespecified orthogonal rescue system, then in another neural model and in the published fly context or a faithful equivalent. Discordant results block any gene-specific rescue claim. Margins, missingness rules, multiplicity and sample size are calibrated before confirmation. Safety precision may set the sample size even when benefit power looks adequate.

The full specification is in [CONFIRMATORY_EXPERIMENT_DESIGN.md](CONFIRMATORY_EXPERIMENT_DESIGN.md) and the 16-gate [SAFE_RESCUE_ENVELOPE.tsv](SAFE_RESCUE_ENVELOPE.tsv). The power sensitivity is a planning illustration and should not be read as a sample-size recommendation. No laboratory has been engaged or quoted, and we claim no wet-lab outcomes.

## The decision as code

The Safe Rescue contract takes statuses that were reviewed separately: pass, fail, indeterminate or not measured. It does not derive safety from transcriptomics and it does not invent thresholds. Every configured field is required, unknown fields are rejected, and controls that are not eligible cannot advance.

| Invented evidence pattern | Weighted illustration | Safe Rescue |
|---|---|---|
| Eligible all-pass positive control | Advance | Advance |
| Benefit fails at one dose | Advance | Block: benefit |
| Confirmed abnormal-clone harm | Advance | Block: safety |
| Indeterminate invasion safety | Advance | Block: uncertainty |
| Incompatible case mechanism | Advance | Block: qualification |
| No measured support | Block | Block: no evidence |

The full comparison has nine invented archetypes. The weighted comparator gives 80% to benefit and 20% to safety with a threshold of 0.75. It is a deliberately simple illustration and is neither validated nor a conventional clinical method. The tests also cover each safety veto across all 64 pass/fail combinations of the six benefit measurements. That verifies the software does what the specification says. It says nothing about efficacy or about how accurate the decisions would be in a real experiment.

### Reproducibility and measured scope

The public analyses keep pinned input receipts, fixed designs, all panel outcomes, package versions and hashed releases. The mouse run took 78.13 seconds locally with R 4.6.1 and DESeq2 1.52.0 and produced no fit warnings. The Python comparison took 17.06 seconds on its first run. Both are timings for single local tasks.

The R environment locks record 121 package versions with provenance. The public source excludes controlled inputs, so the synthetic workflow tests exercise the contracts and do not rerun a protected whole genome.

Run the Python comparison with `analysis/benchmarks/run.py`. The mouse analysis uses `analysis/external/GSE134780/fetch.py` followed by `run.R`. Restore and check instructions are in [analysis/environment/README.md](../analysis/environment/README.md).

Track 1 has its own synthetic policy comparison of 2,400 cases. It keeps favorable and adverse regimes, simple score surrogates and cap ablations. It measures neither clinical accuracy nor an official challenge score. The confidence policy is unchanged, and a new audit makes rank changes caused by caps reviewable.

## What a reviewer can inspect

The repository contains the complete public analysis releases, executable Safe Rescue examples, the 2,400-case synthetic policy comparison and exact R environment locks. The primary and external releases keep their original inventory hashes. The Python suite passes 346 tests in a fresh installation on Windows, where 17 platform-specific tests are skipped.

The fly null and the tissue-dependent mouse results stay visible. We claim no drug-response experiment, no prospective treatment benefit, no replication of human MVA and no cross-platform scientific reproduction. Every proposed model, dose and safety criterion needs qualification before use. We have no laboratory commitment and give no full-project cost estimate.

Under Safe Rescue every requirement for advancement can be inspected. Benefit at one exposure cannot make up for failure at another, and a favorable aggregate score cannot erase confirmed harm. Missing safety data stays an open uncertainty and blocks advancement.

## Sources

1. [Primary public fly data: GSE290206](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE290206)
2. [Independent public mouse data: GSE134780](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE134780)
3. [Sieben et al., BubR1 allelic effects, JCI](https://www.jci.org/articles/view/126863) and the [related corrigendum](https://www.jci.org/articles/view/144781)
4. [SAC/CIN primary study, PMID 41820377](https://pubmed.ncbi.nlm.nih.gov/41820377/)
5. [Official Track 2 instructions](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/blob/main/tabs/submit_track2.py)

The repository includes the full candidate rationale, a source-by-source claim ledger, the proposed experiment, the safety envelope, the complete public analysis tables and machine-readable provenance. The report and the pitch share the same claim boundaries.

## Acknowledgement

> This work was made possible through the Hackathon, organized by Sage Bionetworks in partnership with the MVA Society, Hugging Face, and BEACON (The Benchmarking, Evaluation, and Assessment Consortium for Science), with prize sponsorship from AWS and Anthropic. We are deeply grateful to the child and their family who generously contributed their data and their story to advance research into this rare disease. We acknowledge their trust in making this Hackathon possible.

Challenge citation: Sage Bionetworks, Rare Disease, Real Kid. The 2026 MVA Hackathon, Synapse syn76251147, accessed 27 August 2026.

Team: MVA Safe Rescue.
