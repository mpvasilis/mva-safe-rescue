# Contradiction-first approved-drug candidate panel

Evidence lock: 2026-08-26. This is a preclinical research screen, not treatment advice. FDA approval is indication- and formulation-specific; no approval below establishes efficacy, safety, suitability, or dosing in mosaic variegated aneuploidy (MVA).

## Decision

Use a comparative, vehicle-controlled panel, not a transcriptomically nominated winner.

- **Arimoclomol is the primary proteostasis probe.** It has the strongest combination of pediatric neurological rare-disease experience, documented human CSF exposure, and measurable proximal pharmacology. That priority is experimental only. The published fly rescue used mitochondrial Hsp60/Hsp60c rather than HSP70, the current MIPLYFFA label says the clinical mechanism in Niemann-Pick disease type C (NPC) is unknown, and HSF1-mediated stress tolerance creates a serious CIN/chemoresistance question.
- **Elamipretide is the secondary mitochondrial benchmark.** Its cardiolipin/inner-mitochondrial-membrane pharmacology maps cleanly onto a mitochondrial hypothesis, but the public mitochondrial module is null, the broader primary-mitochondrial-myopathy phase 3 trial missed both primary outcomes, and two cancer-cell studies provide candidate-specific invasion or chemotherapy-protection contradictions.
- **Sirolimus is a mandatory same-model control, not a lead.** Rapamycin/sirolimus was tested in the SAC/CIN fly model: it increased aneuploid neural-stem-cell count without rescuing differentiated progeny or brain size. That uncoupling is exactly what the safety-first design must detect.
- **Everolimus is a translational mTOR-class comparator.** Its pediatric TSC brain-tumor and seizure labels establish substantial CNS experience in another disease, while its anti-proliferative mechanism and the incomplete sirolimus result argue against treating it as a neurodevelopmental rescue nominee.
- **Acetylcysteine (NAC) is a ROS-direction control, not a lead.** It is an approved antidote with human CSF exposure and a plausible glutathione readout, but repeated mouse and cancer-cell results show that redox buffering can promote tumors, metastasis, or chemotherapy survival in some contexts.

The machine-readable scores and row-level falsifiers are in [CANDIDATE_SCORECARD.tsv](CANDIDATE_SCORECARD.tsv).

## Why the public transcriptome cannot nominate a drug

The authoritative analysis configured 13 modules; 12 were evaluable, and **zero of 12 reached BH q<=0.10** in the primary result ([module table](../analysis/track2/release/modules/preregistered_include_IEA.tsv)). Mitochondrial energy had q=0.734; autophagy/mitophagy, ribosome/RNA, and apoptosis each had q=0.198. These are null or hypothesis-generating results, not drug support.

The Hsp70Ba, Hsp70Bb, Hsp70Bc, and Hsp70Bbb calls all come from the same six-library fly experiment ([direction checks](../analysis/track2/release/sanity/gene_direction_checks.tsv)). They are correlated paralogs in one HSP70-family signal, not four replications, not Hsp60/Hsp60c rescue evidence, and not a significant proteostasis module.

The module-level leave-one-batch-out analysis requires a downgrade: folding/proteasome and oxidative-stress directions reverse when blocks 4 or 6 are omitted ([module influence summary](../analysis/track2/release/sensitivity/leave_one_batch_out_module_summary.tsv), [verdict](../analysis/track2/release/sensitivity/stability_verdict.tsv)). This specifically prevents using the HSP-family or GstE8 signals to manufacture arimoclomol or NAC support. No positive public-result score exceeds 1/4.

## Score interpretation

Positive dimensions use 0-4: 0 = no support or contradictory evidence; 1 = remote/uncertain; 2 = adjacent; 3 = strong direct evidence in another relevant context; 4 = the same intervention in the relevant SAC/CIN/MVA context. Regulatory scoring is deliberately indication-specific: 4 would require an MVA indication, so no candidate receives it.

Cancer/CIN hazard also uses 0-4, but higher is worse: 0 = no identified signal; 1 = theoretical; 2 = label/class concern; 3 = direct pathway or same-model concern; 4 = repeated or candidate-specific tumor, invasion, metastasis, or chemotherapy-protection evidence. Scores are **not summed** because a hard-stop hazard cannot be compensated by pediatric experience or regulatory convenience.

Evidence tiers used in the scorecard are:

- **T1:** current official FDA/DailyMed status or label; establishes only the labeled indication.
- **T2:** intervention tested directly in the published SAC/CIN model.
- **T3:** controlled human evidence or human exposure in another disease/context.
- **T4:** adjacent primary preclinical, cell, mechanistic, or cancer-contradiction evidence.
- **T5:** the checksum-locked public transcriptomic analysis and its explicit inference boundary.

## Candidate rationale and contradictions

### Arimoclomol: primary probe, conditional on a safety veto

The current [MIPLYFFA label](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=5feffc0e-453d-47fa-91dd-38d4952309bc&type=display) limits approval to use with miglustat for neurological manifestations of NPC in adults and children aged 2 years and older. It reports dose-dependent CSF concentrations but explicitly says the mechanism of clinical effect in NPC is unknown. The [FDA approval page](https://www.fda.gov/news-events/press-announcements/fda-approves-first-treatment-niemann-pick-disease-type-c) and the [randomized NPC trial](https://pubmed.ncbi.nlm.nih.gov/34418116/) establish pediatric neurological experience in NPC, not MVA.

Primary models describe arimoclomol as an HSP co-inducer, with HSP70 induction and aggregate reduction in a SOD1 mouse model, but later neuronal work found context-dependent or absent HSP70 induction despite other effects ([mouse study](https://pubmed.ncbi.nlm.nih.gov/18673445/), [neuronal study](https://pubmed.ncbi.nlm.nih.gov/38570009/)). That uncertainty matters because the SAC/CIN paper's successful chaperone interventions were Hsp60/Hsp60c, not arimoclomol or HSP70 ([SAC/CIN study](https://pubmed.ncbi.nlm.nih.gov/41820377/)).

A randomized phase 3 ALS trial found no efficacy benefit over placebo, and the authors concluded that available safety data made a higher dose unlikely to be tolerable ([ORARIALS-01](https://pubmed.ncbi.nlm.nih.gov/38782015/)). ALS is not MVA, so this is not a disease-specific falsification; it is strong counterevidence against assuming that HSP co-induction generalizes into neurological benefit.

The contradiction is mechanistically sharp: HSF1 overexpression was an aneuploidy-tolerating change in human cells ([aneuploid-cell study](https://pubmed.ncbi.nlm.nih.gov/25205676/)), and HSF1 activation has supported cancer-cell resistance to etoposide in experimental systems ([chemoresistance study](https://pubmed.ncbi.nlm.nih.gov/38280079/)). Those are not arimoclomol carcinogenicity results. Indeed, the label reports no tumor increase in long-term rat and rasH2-mouse studies. They are, however, enough to require clone-persistence and chemotherapy hard stops before any rescue interpretation.

**Falsifier:** verified HSF1/HSP70 engagement without replicated restoration of neural identity, differentiated output, and tissue-level function; a prespecified replicated increase in aneuploid-clone persistence, tumor-cell fitness/invasion, or chemotherapy survival, or an interval supporting calibrated material harm.

### Elamipretide: secondary benchmark, not the mitochondrial winner

The current [FORZINITY label](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=146bf34c-76f2-48db-ac07-fb29cce2cd75&version=10) describes a mitochondrial cardiolipin binder and an accelerated approval only for improving muscle strength in Barth syndrome in adult and pediatric patients weighing at least 30 kg. Continued approval may depend on a confirmatory trial. The [FDA page](https://www.fda.gov/news-events/press-announcements/fda-grants-accelerated-approval-first-treatment-barth-syndrome) makes the indication-specific basis clear. The label also records that the randomized Barth trial was not superior to placebo on its primary walking and fatigue endpoints; the approval relied on an intermediate endpoint observed in an open-label extension.

Neural plausibility is preclinical: elamipretide improved mitochondrial and behavioral endpoints in an inflammatory mouse-memory model ([mouse study](https://pubmed.ncbi.nlm.nih.gov/31747905/)). Broader efficacy does not generalize automatically: the 218-participant primary mitochondrial myopathy trial missed both primary outcomes ([MMPOWER-3](https://pubmed.ncbi.nlm.nih.gov/37268435/)).

Two direct contradictions dominate the safety rank. Elamipretide reversed the reduced invasion phenotype of ACADM-knockdown breast-cancer cells ([breast-cancer study](https://pubmed.ncbi.nlm.nih.gov/40579130/)); it also protected osteosarcoma cells from ROS/ER-stress-mediated killing in a cytotoxic-drug experiment ([osteosarcoma study](https://pubmed.ncbi.nlm.nih.gov/30704503/)). The label states that carcinogenicity studies were not conducted. These results do not establish clinical cancer harm, but they prohibit a safety assumption in a cancer-predisposed CIN disorder.

**Falsifier:** improved mitochondrial morphology or respiration without neural functional rescue; a prespecified replicated invasion, malignant-fitness, aneuploid-clone-persistence, or chemotherapy-protection increase, or an interval supporting calibrated material harm.

### Sirolimus and everolimus: controls that expose the key failure mode

The SAC/CIN study provides the most relevant pharmacology in the panel: rapamycin feeding increased the count of aneuploid neural stem cells, but neither rapamycin nor the other autophagy-enhancing interventions rescued differentiated Pros-positive cells or brain size ([SAC/CIN study](https://pubmed.ncbi.nlm.nih.gov/41820377/)). That result may reflect survival without restored proliferative output. A candidate that preserves aneuploid cells while failing tissue function has failed, even if a single cell-count endpoint looks better.

The current [sirolimus label](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=a71c205f-7acc-40e5-9eee-69daeb49a352) covers renal-transplant rejection prophylaxis from age 13 and lymphangioleiomyomatosis. It carries prominent infection and lymphoma/other-malignancy warnings related to immunosuppression. Sirolimus is therefore the direct same-compound mechanistic control, not the translational favorite.

The current [AFINITOR/AFINITOR DISPERZ label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=2150f73a-179b-4afc-b8ce-67c85cc72f04) includes TSC-associated SEGA from age 1 and TSC-associated seizures from age 2. The randomized [EXIST-1 study](https://pubmed.ncbi.nlm.nih.gov/27351628/) establishes long pediatric CNS experience in TSC. But everolimus is anti-proliferative, serious infections were more frequent in younger children in the label, and autophagy has mediated resistance to everolimus in a lymphoma model ([resistance study](https://pubmed.ncbi.nlm.nih.gov/22879389/)). Its approved antineoplastic indications and negative rodent oncogenicity studies are important counterevidence; CIN-specific clone behavior still has to be measured directly.

**Falsifier:** more aneuploid neural stem cells without restored differentiated output and tissue function; suppression of euploid neural growth; a prespecified replicated increase in CIN-clone or chemotherapy survival, or an interval supporting calibrated material harm.

### Acetylcysteine: informative ROS control with a non-negotiable cancer gate

The current [ACETADOTE label](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=472f158a-5ab9-4308-8e49-1116e6ea3d39) is for preventing or lessening liver injury after acetaminophen overdose in adults and pediatric patients weighing at least 5 kg. Its labeled mechanism includes maintaining or restoring glutathione. A small human study found dose-dependent CSF NAC after oral administration, supporting CNS exposure but not MVA efficacy ([human CSF study](https://pubmed.ncbi.nlm.nih.gov/25765302/)).

The adjacent mechanism is real but not equivalent: the fly study used genetic overexpression of Sod2 or GTPx-1 and achieved broad rescue; NAC is a systemic thiol/glutathione precursor. The cancer evidence is deliberately reported in both directions. NAC accelerated lung-tumor progression and melanoma metastasis in mouse models and promoted intestinal-tumor progression at human-relevant plasma concentrations ([lung study](https://pubmed.ncbi.nlm.nih.gov/24477002/), [melanoma study](https://pubmed.ncbi.nlm.nih.gov/26446958/), [intestinal study](https://pubmed.ncbi.nlm.nih.gov/33557356/)); it also reduced ROS-dependent osteosarcoma killing in vitro ([osteosarcoma study](https://pubmed.ncbi.nlm.nih.gov/30704503/)). Conversely, older experiments reported anti-invasive and anti-metastatic effects in other models ([counterexample](https://pubmed.ncbi.nlm.nih.gov/7705924/)). Context dependence is the reason to measure malignant fitness rather than label NAC simply safe or dangerous.

**Falsifier:** ROS reduction without restored neural function; a prespecified replicated tumor-growth, metastasis, CIN-clone-persistence, or chemotherapy-protection increase, or an interval supporting calibrated material harm.

## Recommended comparative preclinical experiment

Use the same blinded, randomized run structure for all candidates and keep clinical label doses out of the design. Qualification selects two adjacent target-engaging, noncytotoxic concentrations per candidate without access to confirmatory outcomes.

1. **Conditional primary human-neural model:** use one karyotypically normal human iPSC line with an AAVS1-integrated, inducible dCas9-KRAB system, differentiated through a PAX6+SOX2+ neural-progenitor stage. The targeting guide is the public placeholder `AUTHORIZED_CASE_SELECTED_SAC_GENE`, which authorized local case analysis must select and justify; the matched comparator uses a non-targeting guide. If the authorized mechanism is not compatible with inducible partial SAC deficiency, this model is inapplicable. Public BUB3 perturbation may be an assay-development control only, never a silent case-gene substitute.
2. **Locked benefit rule:** the one primary endpoint is day-21 live MAP2+TUBB3+ neuron yield per 100 starting viable PAX6+SOX2+ progenitors. Exactly two co-required mitochondrial endpoints are day-21 ATP-linked oxygen-consumption rate per viable cell and day-21 TMRM membrane-potential signal per mitochondrial mass. All three endpoints must clear the calibrated margin at both locked doses; a biochemical improvement cannot compensate for failed neuronal yield.
3. **Required genome-safety domain:** use longitudinal single-cell karyotype or equivalent low-pass DNA profiling plus clone tracking. Distinguish true restoration of functional lineage output from survival or expansion of highly aneuploid clones.
4. **Orthogonal confirmation:** qualification requires concordant deficient-state phenotypes from at least two independent non-overlapping guides before one lead guide is frozen without using candidate outcomes. Repeat any vehicle-qualified candidate with the second guide or a prespecified complementation/rescue model, then in the published fly paradigm or a faithful equivalent. Require benefit across independent culture initiation/differentiation runs; wells, fields, images, and cells remain technical subsamples.
5. **Oncology/chemotherapy veto:** run p53-intact and p53-deficient CIN tumor models, invasion assays, and chemotherapy co-exposure in parallel. A prespecified replicated increase in malignant fitness, invasion, aneuploid-clone persistence, or chemotherapy survival (or an interval supporting calibrated material harm) is a hard stop. An interval crossing a safety margin is indeterminate/no-advance, not evidence of harm.

The [deterministic public power sensitivity](../analysis/design_power/README.md) covers the six co-required benefit comparisons for arimoclomol and elamipretide. It is not advancement power and does not recommend a run count: qualification data must replace every standardized effect, covariance, attrition, and margin assumption, while safety-bound precision may determine a larger design.

The confirmatory advancement family contains exactly two primary vehicle-controlled hypotheses: **arimoclomol versus vehicle** and **elamipretide versus vehicle**. Sirolimus, everolimus, and NAC define assay, mechanistic, and hazard boundaries and are ineligible for advancement in this family. A direct arimoclomol-versus-elamipretide ranking is secondary unless separately powered and prespecified. A clean, prospectively locked no-go for both advancement candidates is scientifically preferable to advancing a cytoprotective drug that rescues the wrong cells.

Throughout this dossier, a descriptive adverse trend triggers review or repeat but is not itself called harm. Only a prespecified replicated adverse signal or an interval supporting a calibrated material-harm threshold supports a harm statement. An interval that merely crosses a safety margin is indeterminate/no-advance, not evidence of harm.

## Candidate additions and exclusions

No extra drug was added. The five-compound panel already spans the three interventions supported by the published fly experiment: proteostasis/heat-shock modulation, mTOR/autophagy, and mitochondrial/ROS rescue. Adding supplements, unapproved analogs, or chemically broad chaperones now would increase multiplicity without improving the mechanistic contrast. Any future addition must enter through the same public-evidence scorecard before results are examined and must bring either a distinct falsifiable axis or a safer within-axis control.

## Claim boundary

Nothing here characterizes a gated participant, a private variant, or an individual treatment. No candidate is described as effective or safe for MVA. The only recommendation is a public preclinical comparison, reusable across candidates within this SAC/CIN screening context, with noncompensatory cancer/CIN hard stops.
