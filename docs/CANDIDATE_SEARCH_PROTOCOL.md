# Dated candidate-search refresh: conditional SAC/CIN branch

Search date: **2026-08-27**  
API retrieval window: **2026-08-27T10:42:12Z to 2026-08-27T10:43:25Z**  
Scope: public information only; preclinical research prioritization, not diagnosis or treatment advice.

## Status and inference boundary

This is a bounded, reproducible **post-panel refresh**, not a preregistered systematic review. It is explicitly non-systematic and not independent validation. The original five-compound panel was assembled by targeted, hypothesis-driven curation and evidence-locked on 2026-08-26. The present search was run after that panel and after the public transcriptomic results were known. It must not be described as a blinded review or a retrospective record of searches that were not logged at the time.

The protocol and log create a prospective rule only for future refreshes: rerun the frozen URLs, append a new dated snapshot, and apply the same rules before changing a disposition. The search is intentionally non-exhaustive. It covers PubMed title/abstract metadata, current DailyMed label records, and two ClinicalTrials.gov queries; it does not cover every bibliographic database, patent, preprint, conference abstract, non-indexed full text, medicine ontology, country, or spelling variant. A zero count means “no record matched this exact query at this snapshot,” not “no evidence exists.”

The branch itself remains conditional. Public data cannot establish the gated child's causal variant or that the relevant mechanism is SAC deficiency/CIN. No compound below has demonstrated MVA efficacy, dosing, individual suitability, or clinical safety.

## Question

Among named medicines with an official US prescription label, does a dated public search identify a direct MVA/SAC/CIN neural-rescue candidate, or change the experimental role of the existing five-compound panel?

## Sources and frozen search layers

The machine-readable audit trail is [CANDIDATE_SEARCH_LOG.tsv](CANDIDATE_SEARCH_LOG.tsv). It records exact query strings, URLs, snapshot counts, deterministic screened subsets, returned identifiers, selected label set IDs, dispositions, and row-level rationale.

### Layer 1: broad PubMed discovery

PubMed was queried through the official NCBI E-utilities `esearch` endpoint. Every query used `db=pubmed`, `retmode=json`, `sort=relevance`, and an Entry Date ceiling of `2026/08/27`. The exact encoded URLs and returned PMIDs are in rows `Q01`-`Q03` of the log.

- `Q01` targets MVA/BUB1B/BUBR1/BUB3 plus drug, pharmacology, therapy, treatment, or rescue terms: 564 records; the first 50 relevance-ranked records were title-screened.
- `Q02` targets neural or neurodevelopmental SAC/CIN intervention literature: 79 records; all 79 were title-screened.
- `Q03` targets aneuploidy/CIN plus the four pre-existing mechanism axes (proteostasis/heat shock, mitochondria/mitophagy, autophagy, and oxidative stress) plus intervention terms: 301 records; the first 100 relevance-ranked records were title-screened.

The three broad subsets contained 227 unique PMIDs because two records overlapped. Relevance ordering is a PubMed service behavior and may change; the frozen PMID lists, not a later rerun's order, define this snapshot.

### Layer 2: named-candidate bridge searches

Each of the five existing candidates and seven close, labeled alternatives was searched by generic name against the same MVA/BUB1B/BUBR1/BUB3/SAC/aneuploidy/CIN bridge. All returned records were title-screened because every candidate query returned 50 or fewer records. Across the nonzero searches, 62 hits (60 unique PMIDs) were screened. Exact searches and hits are in rows `P_C01`-`P_A07`.

The known fly SAC/CIN anchor, PMID `41820377`, was hand-seeded from the prior targeted curation. It did not appear in the exact candidate title/abstract queries and is not falsely counted as a new discovery. That miss is itself a reason not to interpret a zero API count as an exhaustive absence claim.

### Layer 3: official label check

The DailyMed v2 SPL endpoint was queried by each generic name. The API's `total_elements` value is a count of label records matching the name, not a count of approvals, unique products, active products, or relevant indications. A specific label set was then inspected for indication, mechanism, and pediatric-use boundaries. Rows `D_C01`-`D_A07` preserve the API count and selected set ID.

Presence in DailyMed was required for this bounded “approved-medicine” comparison, but it does not imply approval for MVA or for the proposed route, dose, age, duration, or use. Approval is indication- and formulation-specific.

### Layer 4: ClinicalTrials.gov check

The official v2 API returned zero studies for the exact condition `Mosaic Variegated Aneuploidy` (`CT01`). A broader free-text query for `"mosaic variegated aneuploidy" OR BUB1B OR BUBR1` returned two records (`CT02`): `NCT00539422` and `NCT07713797`. Both were screened and excluded because they are observational studies in breast disease and endometriosis, respectively, not MVA intervention studies. This supports only the narrow statement that these two exact registry queries found no MVA interventional trial on the search date.

## Prespecified screening rules used for this refresh

### Include for full candidate disposition

A named medicine entered the disposition table if all of the following held:

1. A US human prescription label could be inspected in DailyMed.
2. The medicine either mapped to one of the four axes fixed before this refresh or was a close pharmacologic/class alternative to an existing panel member.
3. It could add a distinct, falsifiable probe, benchmark, or control to the proposed neural SAC/CIN experiment.
4. Its direct and contradiction evidence could be checked in public primary literature or an official label.

Direct MVA/SAC/CIN rescue was preferred but not required for a **control** role. Absence of direct evidence prohibits efficacy language; it does not prevent use of a compound as an assay control or mechanistic comparator.

### Exclude from the first-round panel

A medicine was not advanced when any of the following applied:

- it was investigational-only, a supplement/nutrient rather than a labeled prescription medicine, a genetic intervention, or not a named agent;
- the retrieved use was primarily to induce, exploit, or kill CIN cells, rather than to test restoration of viable neural output;
- it did not map to the conditional mechanism or could not discriminate among the four axes;
- it duplicated an existing control/class role without adding a materially different readout, neural-use boundary, or safety test;
- its official indication and mechanism were too remote to justify first-round use in the fixed six-arm design; or
- the record was descriptive, review-only, non-neural, non-MVA, or an unrelated acronym/name match.

Safety contradictions were not automatically discarded. Under the contradiction-first design they can convert a plausible medicine into a control and trigger a noncompensatory hard stop. Conversely, pediatric or rare-disease label experience cannot compensate for a lack of MVA efficacy evidence.

### Screened-subset rule

For broad queries with more than 100 results, only the first 100 relevance-ranked titles were eligible for this refresh; `Q01` was capped at 50 because its early results were dominated by BUB-family oncology records. A query with 100 or fewer results was screened in full. No snowball expansion was counted as part of the prospective subset. Previously known anchor papers and candidate-specific contradiction papers were retained as **prior targeted curation** and labeled as such.

Title-screen exclusions were not promoted to evidence claims. If a title could plausibly name an eligible medicine or direct neural rescue, its PubMed record/primary article was checked before disposition. Full-text availability was not a requirement for counting a search hit, but a candidate could not be advanced on a title alone.

## Reconciliation result

The refresh found no direct public MVA medicine trial and no new candidate that met the first-round inclusion rules. It therefore leaves the existing panel unchanged while sharpening its nonclaims:

| Medicine | Refresh disposition | What the disposition means |
|---|---|---|
| arimoclomol | Retain as first proteostasis probe | No direct bridge hit; adjacent HSP pharmacology, human CSF exposure, and pediatric neurological NPC experience justify a falsifiable probe only. It is not an MVA treatment nominee. |
| elamipretide | Retain as secondary mitochondrial benchmark | No direct bridge hit; current cardiolipin/mitochondrial pharmacology makes a distinct benchmark, while candidate-specific oncology contradictions require hard-stop testing. |
| sirolimus (rapamycin) | Retain as same-model control | The prior anchor study directly tested rapamycin in the fly SAC/CIN model and showed an uncoupled partial result; the 45 bridge-query records do not establish MVA neural rescue. |
| everolimus | Retain as mTOR-class comparator | Two bridge hits were oncology/CIN contexts, not MVA neural rescue. Pediatric TSC CNS labeling makes it a translation comparator, subordinate to the direct sirolimus control. |
| acetylcysteine (NAC) | Retain as redox-direction control; ineligible for lead status | Four bridge hits concern oxidative/genotoxic/ploidy contexts rather than MVA rescue. The genetic ROS-rescue anchor and candidate-specific tumor/chemotherapy contradictions make it useful only as a direction and safety control. |

The `prior_panel_status` tokens in the dated machine-readable log preserve the
labels that existed when the refresh ran. The final scorecard subsequently
clarified, without changing panel composition or evidence, that arimoclomol and
elamipretide are two separately vehicle-controlled advancement candidates, that
their direct ranking is secondary unless separately powered, and that the three
controls are ineligible for advancement in the current family.

The following close alternatives were explicitly considered and rejected from the first round; “reject” here is an experimental panel decision, not clinical advice:

| Medicine | Why it was close | Why it was not added |
|---|---|---|
| omaveloxolone | Labeled Friedreich-ataxia medicine; activates the Nrf2 oxidative-stress response | Zero direct bridge hits; labeled use begins at age 16; it duplicates the redox axis without a direct SAC/CIN or assay-validity advantage. |
| edaravone | Labeled neurological medicine and plausible redox probe | Zero direct bridge hits; pediatric use is not established and the label says its ALS therapeutic mechanism is unknown; NAC already supplies the more directly measurable glutathione control. |
| dimethyl fumarate | Labeled neurological medicine with Nrf2-pathway activation | Zero direct bridge hits; adult-only relapsing-MS indication and no direct SAC/CIN evidence; it duplicates the redox/Nrf2 axis without first-round incremental value. |
| metformin | Labeled from age 10 and often used as an indirect metabolic/AMPK-mTOR modifier | Nine bridge hits, but none demonstrated MVA neural rescue; the hits include high-dose genotoxic stress and a high-glucose neuronal MAD2B context. Its systemic metabolic effects make it less discriminating than the direct mTOR controls. |
| temsirolimus | Direct mTOR inhibitor and sirolimus-class neighbor | Two bridge hits; one reports increased chromosomal instability in a glioblastoma context. Its label is for advanced renal-cell carcinoma, pediatric effectiveness is not established, and it adds no needed role beyond sirolimus plus everolimus. |
| sodium phenylbutyrate | Labeled pediatric rare-disease medicine sometimes discussed as a chemical chaperone | Zero direct bridge hits; the inspected label's mechanism is nitrogen disposal in urea-cycle disorders, not a validated SAC/CIN proteostasis rescue. It is less specific than the selected HSP probe. |
| miglustat | Rare-disease medicine paired with arimoclomol in the MIPLYFFA regimen | Zero direct bridge hits; its own inspected US label is adult type-1 Gaucher substrate-reduction therapy. Proximity to NPC care does not provide an SAC/CIN mechanism or MVA evidence. |

Approved or investigational agents that appeared only in excluded cancer/CIN-exploitation or exposure-toxicity records (such as hydroxyurea, olaparib, temozolomide, gefitinib, canagliflozin, propofol, MPS1 inhibitors, and BAL101553) were not treated as neural-rescue candidates. Genetic fly interventions such as `Hsp60`, `Hsp60c`, `Sod2`, and `GTPx-1` are mechanistic anchors, not medicines.

## Decision rule for future updates

A new medicine may enter the first-round panel only if a dated appended search identifies evidence that changes a distinct experimental role. Replacement (not panel expansion) is preferred when the six-arm assay is fixed. The candidate must beat the incumbent on directness or discriminating value and inherit the same neural-function, CIN-clone, malignant-fitness, invasion, and chemotherapy-survival gates. A registry entry, label, pathway match, or nominal transcriptomic direction alone is insufficient.

## Reproduction and audit notes

- No named human curation sign-off is recorded yet. Before submission, a named reviewer must verify the frozen links and dispositions, date the review, and record any disagreement and resolution; absence of that sign-off is a release blocker, not an implied approval.
- Reopen each `source_url` in the log and preserve the returned count and identifiers with a new UTC timestamp. Do not overwrite this snapshot if counts change.
- For PubMed, compare the rerun against the frozen PMID list. Later indexing and relevance reordering are expected.
- For DailyMed, inspect the selected set ID and note if a newer label supersedes it. Do not interpret `total_elements` as approval count.
- For ClinicalTrials.gov, inspect every returned study and record why it is or is not an MVA intervention.
- Keep candidate dispositions separate from evidence facts. A retained probe is not an efficacy claim; a rejected first-round alternative is not a statement that the medicine is unsafe or ineffective in its labeled indication.

Official API documentation: [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/), [DailyMed web services](https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm), and [ClinicalTrials.gov API](https://clinicaltrials.gov/data-api/api).
