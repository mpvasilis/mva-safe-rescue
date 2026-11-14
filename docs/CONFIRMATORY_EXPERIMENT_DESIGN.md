# Confirmatory Safe Rescue experiment design

Design status: **proposed and not yet executable**. The model, assays, doses,
minimum worthwhile effects, safety margins, and biological replicate count must
be calibrated and prospectively frozen before confirmatory treatment outcomes
are available. Nothing here is a clinical threshold or treatment recommendation.

## Qualification before confirmation

Use separate qualification/dose-selection and confirmatory stages. Qualification
must establish reproducible separation between an inducible partial-SAC-
deficient model and its isogenic non-targeting vehicle control on the named
neural endpoint below. Before the confirmatory stage, freeze:

- the day-21 primary neural endpoint, its image-analysis derivation, direction,
  harvest window, and smallest worthwhile rescue effect;
- exactly two orthogonal mitochondrial endpoints;
- the marker panel, model-eligibility rule, assay controls, and plate-quality
  rules;
- two adjacent target-engaging, noncytotoxic concentrations per candidate; and
- calibrated safety margins and the complete statistical analysis plan.

Qualification data may verify the model, assays, doses, and margins, but cannot
support candidate advancement. Failure of the prespecified day-21 markers or
timing requires a documented redesign and a new freeze before any confirmatory
candidate outcomes exist; it does not permit endpoint switching after results.

## Conditional model branch

The proposed model is one karyotypically normal parental human iPSC line with an
AAVS1-integrated, inducible dCas9-KRAB system, differentiated through a
PAX6+SOX2+ neural-progenitor stage. At least two independently designed,
non-overlapping targeting guides must each produce partial, not lethal,
depletion of the **authorized case-selected SAC gene**; matched isogenic
comparators carry non-targeting guides. The exact gene branch may be
chosen only by authorized local case analysis that establishes a defensible
mechanism. It must not be inferred from the public fly or trisomy-21 analyses or
written into public artifacts from patient information. If the authorized
mechanism is not compatible with partial SAC deficiency, this model is
inapplicable and the experiment stops for redesign.

Qualification must verify on-target repression, knockdown titratability,
negligible uninduced leak, karyotype, and maintained CRISPRi activity through
the PAX6+SOX2+ progenitor stage and the day-21 neuronal harvest. AAVS1
performance in undifferentiated iPSCs cannot be assumed to transfer unchanged
through neural differentiation; failure of this expression/knockdown gate
requires redesign rather than interpretation of candidate outcomes.

Both guides must show concordant target repression and the qualified deficient-
state checkpoint/CIN and neural-yield phenotype before a lead guide is frozen
for the vehicle-controlled candidate screen. Lead-guide selection uses only
target engagement and assay-quality information, never candidate outcomes. Any
candidate that passes the primary model must then reproduce with the second
guide or in a prespecified orthogonal complementation/rescue model before
advancement. Discordance blocks a gene-specific rescue interpretation.
A non-targeting guide alone does not exclude guide-specific off-target effects.

Freeze the induction-to-treatment interval during qualification. Confirmatory
candidate exposure begins only after the partial-SAC perturbation has produced
the prespecified checkpoint/CIN state without catastrophic toxicity, verified
by a pretreatment-compatible readout or parallel sacrificed cultures. A
preventive exposure beginning before that state is established answers a
different question and cannot be pooled with or substituted for rescue.

This is a conditional mechanism model, not a patient avatar and not evidence of
MVA by itself. A public `BUB3` CRISPRi construct may be used as an assay-
development control because the fly experiment depleted `bub3`, but it cannot
silently substitute for the authorized gene branch or support a case-specific
claim.

## Primary question and estimand

The single primary neural endpoint is **day-21 live MAP2+TUBB3+ neuron yield per
100 starting viable PAX6+SOX2+ neural progenitors**. The numerator is the blinded
automated count of cells negative for the terminal viability dye and positive
for both MAP2 and TUBB3 in the frozen day-21 imaging window. The denominator is
the viable PAX6+SOX2+ progenitor count plated at differentiation day 0, scaled to
100. Qualification must demonstrate marker kinetics, segmentation accuracy,
dynamic range, and between-run repeatability. NeuN may be recorded as a support
marker only if qualification shows reliable day-21 expression; it is not an
alternative primary definition.

For each candidate and locked dose, the primary estimand is the blocked mean
treatment-minus-vehicle difference in this yield among SAC-deficient cells,
with higher yield favorable. Closure of the deficient-vehicle versus non-
targeting-vehicle gap is descriptive; inference stays on the endpoint's
original scale because gap-normalized ratios become unstable when that control
gap is small.

Neural identity, differentiation fidelity, and general viability remain
required support or veto outcomes, not interchangeable alternatives to the
primary endpoint. The confirmatory advancement family contains exactly two
vehicle-controlled candidate hypotheses: arimoclomol versus vehicle and
elamipretide versus vehicle. Sirolimus, everolimus, and acetylcysteine are
assay/mechanistic/hazard controls and are ineligible for advancement in this
family. A direct arimoclomol-versus-elamipretide ranking is secondary unless
separately powered and prespecified.

Exactly two mitochondrial endpoints are co-required support outcomes at day 21:

1. ATP-linked oxygen-consumption rate after oligomycin response, normalized to
   the prespecified viable-cell denominator; and
2. TMRM membrane-potential signal normalized to mitochondrial mass under a
   frozen acquisition and positive-control protocol.

Both mitochondrial endpoints and the primary neural endpoint must pass at both
locked doses. They cannot compensate for one another.

Only these three endpoints at two doses (the six SRE01/SRE03 comparisons) define
affirmative benefit. Mitophagy flux, proteotoxic stress, and energetic behavior
in a separate high-aneuploid compartment are frozen support/safety diagnostics:
their improvement is not required and cannot create or replace a benefit pass.
A prespecified replicated material worsening or an interval supporting a
calibrated safety harm may veto; lack of improvement alone is neutral, while an
interval crossing a safety margin is indeterminate/no-advance rather than
evidence of harm.

## Experimental units, randomization, and blinding

Each independent culture initiation/differentiation day is a randomized block
and a biological experimental unit. Wells, organoids, fields, images, and cells
within one run are subsamples unless independently randomized for the intended
inference; they never replace replication of the full run. Technical observations
are averaged within run-condition or retained under a hierarchical model.
Confirmation requires a fresh biological run and ultimately an independently
derived neural model. Generalization across genotypes requires independently
derived clone pairs or models.

Every complete block should contain both genotypes, vehicle, both locked doses
of each confirmatory candidate, and assay controls. Use a saved computer-generated
randomization sequence, balance plate edge and acquisition order, and include
vehicle on every plate. If a complete block does not fit, prospectively use a
balanced incomplete-block layout; never confound treatment with plate. Conceal
treatment codes from outcome assessors, image analysts, and the statistician
until quality control, endpoint derivation, exclusions, and analysis code are
frozen; conceal them from culture operators where feasible.

## Analysis and multiplicity

Analyze continuous outcomes with a blocked hierarchical model containing
genotype, guide/model instance, candidate-dose condition, and their relevant
interactions, with run, clone, plate, and treatment-by-run variation represented according to the sampling
design. Treat doses as categorical. Use beta-binomial or binomial mixed models
for chromosome-error and abnormal-karyotype proportions, log-scale mixed models
for positive ratios such as clonogenic AUC, migration, and invasion, joint
concentration-response models for IC50 ratios, and treatment-by-time models for
serial clone trajectories. Cells within a culture are clustered observations,
not independent Bernoulli replicates. Report effects and confidence intervals,
not p-values alone.

"Any two of five" mitochondrial outcomes and "any one" functional outcome are
not confirmatory rules. Candidate success is an intersection-union decision:
both locked doses must exceed the calibrated minimum-benefit criterion on the
named primary endpoint, both named mitochondrial endpoints must pass at both
doses, and every applicable safety gate must pass. Every chromosome-error,
abnormal-clone-persistence, malignant-fitness, invasion, chemotherapy-
resistance, viability, or unresolved-safety gate is a noncompensatory veto;
benefit cannot be averaged against harm. Control the
candidate-level family across arimoclomol and elamipretide, for example using
Holm or a shared-control max-t/Dunnett procedure. Optional endpoints, multiple
time points, dose-pair selection, or candidate selection require additional
multiplicity control. No favorable tumor-panel average may override a harmful
prespecified line.

## Missing data, exclusions, and confirmation

Freeze exclusions before unblinding and limit them to objective pre-treatment
eligibility or technical failure: contamination, authentication failure,
documented instrument failure, failed prespecified plate controls, or protocol
deviation. Post-treatment low viability, clone loss, or assay failure plausibly
caused by treatment is an outcome, not an exclusion. If a block is invalid,
repeat the complete randomized block rather than selected arms. Report every
randomized unit and reason for missingness by group. Do not delete statistical
outliers ad hoc; use a prespecified transformation or robust model and show an
all-observation sensitivity. Treatment-related missingness requires a
conservative sensitivity analysis. Unresolved safety missingness is
indeterminate/no-advance.

## Sample size and margin calibration

No fixed biological-replicate count is defensible from the current public
evidence. Estimate between-run and treatment-by-run variation, guide/clone
heterogeneity, assay intraclass correlation, event rates, endpoint correlations,
and attrition from qualification controls and relevant historical runs. Do not
use technical-well variability or a tiny treatment pilot as the variance basis.
Simulate the full hierarchical, multiplicity-adjusted decision rule and choose
biological `n` for both primary-endpoint power and safety-bound precision. Large
numbers of cells cannot compensate for few independent runs. Record the chosen
familywise false-positive level and power target before confirmation; 0.05 is a
provisional familywise level, not a completed power calculation.

The [public-only deterministic power sensitivity](../analysis/design_power/README.md)
is the first executable planning layer. It uses fixed-seed Monte Carlo run-level
treatment-minus-vehicle differences for the primary endpoint and exactly two
mitochondrial endpoints, each at two doses. It applies a one-sided
candidate-level alpha of 0.025 (`0.05 / 2`) and requires all six comparisons to
pass. The
grid varies true benefit, paired-difference variability, and 6--32 independent
culture initiation/differentiation runs. Its all-benefit probability is
conditional on every safety veto passing: it is not advancement power and does
not size rare-event or confidence-bound safety endpoints. Qualification must
replace its provisional standardized effects, variance, correlation, margin,
and attrition assumptions before a biological run count is frozen.

In the central illustrative variability scenario (paired-difference SD 1.00),
the fixed-seed estimate for all three benefit endpoints at both doses was 0.3741
with 32 runs when the common true effect was 0.70 SD, but 0.8377 with 24 runs
when it was 1.00 SD; both are measured against a provisional 0.20-SD margin.
This sensitivity is why the public calculation does not nominate a sample size.
The qualification stage must supply endpoint-specific effects and covariance,
and the safety precision calculation may require more runs than benefit power.

The current ratios `1.10`, `1.20`, and `1.25`, and the absolute 10-percentage-
point limits, have no public assay-performance or biological calibration. They
are **prospectively specified provisional screening margins**:

- `1.10` means a 10% relative increase; passing requires the appropriate upper
  confidence bound below 1.10.
- `1.20` means a 20% relative increase; migration and invasion rules likewise
  require an upper confidence bound below 1.20.
- 10 percentage points is an absolute risk difference, not 10%; it must be
  analyzed on that scale and is not interchangeable with a risk ratio of 1.10.
- `1.25` means a 25% relative increase in chemotherapy IC50; it requires a joint
  concentration-response model and an interval for the IC50 ratio.

Calibrate all margins from blinded vehicle/positive-control behavior,
between-run repeatability, baseline event rates, and oncology/model-expert
judgment about the smallest unacceptable harm. Version any revision without
access to confirmatory candidate outcomes. A confidence interval crossing a
margin is indeterminate/no-advance, not proof of harm; a hard-stop harm claim
requires a prespecified replicated adverse signal or an interval supporting
material harm.

## Methodological sources

- AAVS1-integrated inducible dCas9-KRAB feasibility in human iPSCs:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4830697/
- CRISPRi through human iPSC-neuronal differentiation, including the need to
  qualify safe-harbor expression in neurons:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC6813890/
- Day-21 MAP2/TUBB3 human iPSC-neural marker feasibility context; timing and
  marker performance remain protocol-specific:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8301075/
- Day-21 high-content human iPSC-neural phenotyping context:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10121225/
- Experimental units and pseudoreplication: https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.2005282
- ARRIVE 2.0 explanation for design, randomization, blinding, exclusions, sample size, and reporting: https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3000411
- NINDS rigorous preclinical design and transparent reporting: https://www.ninds.nih.gov/funding/preparing-your-application/preparing-research-plan/rigorous-study-design-and-transparent-reporting
- Multiplicity principles, used by analogy rather than as a preclinical regulatory requirement: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/multiple-endpoints-clinical-trials
- Confidence-bound and margin-selection principles, likewise used conceptually: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/non-inferiority-clinical-trials
