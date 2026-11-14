# Public decision-policy comparison

Locked before execution on 2026-09-09. This is a locally dated engineering
experiment, not external preregistration, clinical validation, or an official
hackathon score. It uses invented data only and does not change the frozen case.

## Track 1

Generate 2,400 independent synthetic cases with seed 20260909, ten distinct
candidate sets each, and one known causal set. Alternate single and paired
causal sets. Use four equally weighted regimes (600 each): informative review
flags, uninformative flags, adverse flags affecting true candidates more often,
and unresolved phase among true pairs. Publish each regime separately.

Generate the true index before scores and flags. True-versus-decoy variant
scores follow Beta(5,2) versus Beta(2,5). Phenotype scores follow Beta(3,2)
versus Beta(2,3). The illustrative phenotype-priority baseline averages those
two scores. These surrogate scores do not implement Exomiser, LIRICAL or the
protected WGS ensemble, and are not calibrated clinical probabilities.

The production-policy arm calls the existing builder's `_prepare_document`
function on that same phenotype-priority input, exercising the real public
confidence caps and serialization. Compare the variant-only surrogate, the
phenotype-priority surrogate, the production confidence policy, and production
ablations that remove frequency, phase or read-review uncertainty one at a time.
No parameter is fitted or selected using the benchmark results.

Flag-error probabilities (true/decoy) are 0.05/0.55 for informative review,
0.30/0.30 for uninformative review, 0.70/0.10 for adverse review, and 0.10/0.25
for unresolved-phase review. Independent draws determine read and frequency
uncertainty. Compound phase is unresolved with those same probabilities except
in the fourth regime, where it is 0.90/0.20. No cis pair is generated: this is
a ranking/capping study, not a test of the builder's separately tested rejection.

Measure top-1 and top-3 recovery, mean rank points, mean variant-level F-max,
and precision/recall at a fixed priority threshold of 0.60, including abstention.
Use the repository's real scorer for rank points and F-max. Report paired top-1
improvements AND regressions versus the phenotype surrogate. Report elapsed
policy/scoring time separately from WGS runtime and use no cloud-cost estimate.
Do not interpret synthetic mixture averages as an estimate of clinical accuracy.

## Track 2

Exercise three explicit, illustrative advancement policies on the same invented
statuses: any biochemical benefit, an 80%-benefit/20%-safety additive rule with
threshold 0.75, and the production Safe Rescue contract. These are deliberately
simple comparators, not claims about the performance of an established clinical
or drug-discovery method. No numeric clinical safety thresholds are invented.

The named-paper illustration is separate. The published rapamycin result has
increased aneuploid stem-cell count without restored differentiated output or
brain size. A survival-only rule would treat the count direction as favorable;
the reported functional failure blocks Safe Rescue. Other unmeasured drug gates
remain unmeasured. Adjacent cancer evidence does not become a measured MVA harm.

Tests cover missing data, one-dose failure, confirmed harm, failed qualification,
controls, conflicting confirmation and a wholly synthetic all-pass positive
control. Logical veto preservation is not evidence of sensitivity, specificity,
clinical benefit or clinical safety. No candidate in the actual proposal has
completed the advancement experiment.
