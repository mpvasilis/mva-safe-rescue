# Public-only Safe Rescue power sensitivity

This directory turns the proposed confirmatory design into an auditable,
deterministic sensitivity calculation. It is a planning aid, not a sample-size
justification. It contains no patient, variant, gated, or treatment-outcome
data.

## Conditional model and endpoints

The design uses one inducible isogenic human iPSC neural model. Authorized local
case analysis must first select and justify the affected spindle-assembly-
checkpoint gene branch. The public artifact deliberately records only
`AUTHORIZED_CASE_SELECTED_SAC_GENE`; it must not be replaced with a guess. If
the authorized mechanism is not compatible with inducible partial SAC
deficiency, this design is inapplicable and must not be forced onto the case.
Qualification requires concordant deficient-state phenotypes from at least two
independent non-overlapping guides before one lead guide is frozen using only
target-engagement and assay-quality information. A candidate that passes the
lead-guide comparison still requires second-guide or orthogonal
complementation/rescue confirmation before advancement.

Each independent culture initiation and differentiation run is one randomized
block and one biological unit. Every complete run contains vehicle and both
locked doses. Wells, fields, images, and cells are technical subsamples and are
summarized within run-condition before inference.

The one primary neural endpoint is **day-21 live MAP2+TUBB3+ neuron yield per
100 starting viable PAX6+SOX2+ neural progenitors**. Qualification must first
show that the day-21 marker kinetics, automated segmentation, and run-level
repeatability are adequate, then freeze the acquisition and derivation. NeuN
may be recorded as a qualification/support marker only if its kinetics are
reliable; it is not an alternative primary endpoint and cannot replace TUBB3
after outcomes are examined. Exactly two required
mitochondrial support endpoints are retained:

1. day-21 ATP-linked oxygen-consumption rate per viable cell; and
2. day-21 TMRM membrane-potential signal per mitochondrial mass.

All three endpoints must clear the calibrated benefit margin at both locked
doses. These six comparisons form an intersection-union rule: a strong result
cannot compensate for a failed endpoint or dose. Every applicable Safe Rescue
safety gate is also a noncompensatory veto.

## Simulation model

The simulation directly generates the six treatment-minus-vehicle differences
for each independent run. Their means are the provisional true benefit; their
SD is varied over the grid in `assumptions.tsv`. An equicorrelated run-response
term represents shared treatment-by-run behavior across endpoints and doses.
Technical replication does not increase the biological run count.

For each endpoint-dose comparison, a one-sided paired t lower bound must exceed
the provisional minimum-benefit margin. A conservative candidate-level alpha of
`0.05 / 2 = 0.025` represents Bonferroni control across the two confirmatory
candidates. Because every comparison for a candidate must pass, no additional
alpha division is needed within that intersection-union decision. The output
reports:

- the probability that the primary endpoint passes at both doses;
- the probability that both mitochondrial endpoints pass at both doses; and
- the probability that all three benefit endpoints pass at both doses.

The last probability is **not advancement power**. It is conditional on every
safety veto passing and on complete safety information. Safety-event rates,
confidence-bound precision, attrition, guide/clone heterogeneity, and assay-
specific covariance require separate qualification estimates. The public grid
does not simulate the required second-guide/complementation confirmation. The
final biological run count must be the largest count required by benefit power,
safety-bound precision, quality-control loss, and any prespecified sensitivity
or confirmation analysis.

## Illustrative results

The central variability scenario sets the run-level paired-difference SD to
`1.00` qualification-control SD. Selected fixed-seed results are:

| Common true benefit | Independent runs | Primary, both doses | All 3 endpoints, both doses |
|---:|---:|---:|---:|
| 0.40 SD | 8 | 0.0140 | 0.0000 |
| 0.40 SD | 32 | 0.0655 | 0.0063 |
| 0.70 SD | 8 | 0.0859 | 0.0071 |
| 0.70 SD | 32 | 0.6414 | 0.3741 |
| 1.00 SD | 8 | 0.3000 | 0.0744 |
| 1.00 SD | 24 | 0.9347 | 0.8377 |
| 1.00 SD | 32 | 0.9851 | 0.9570 |

Here every true benefit is measured from the provisional `0.20 SD` margin, so
the actual signals above that margin are 0.20, 0.50, and 0.80 SD. The wide
spread is the result: a run count that appears adequate under a large,
repeatable effect can be badly underpowered under a moderate effect. No row is
a recommended `n`, and the displayed `0.0000` is a finite-simulation estimate
(zero successes in 12,000 iterations), not proof that the probability is zero.
The complete 72-row grid in `power_scenarios.tsv` includes paired SD values
0.80, 1.00, and 1.20 and all run counts.

The fixed seed and common random numbers make comparisons across effect and
variability scenarios reproducible and reduce Monte Carlo noise. The committed
table is regenerated or checked with:

```powershell
.venv\Scripts\python.exe analysis\design_power\simulate_power.py
.venv\Scripts\python.exe analysis\design_power\simulate_power.py --check
```

Before confirmation, replace every provisional numerical assumption with
blinded qualification-control estimates and expert-calibrated margins, increase
the Monte Carlo iterations, simulate the frozen missingness and multiplicity
rules, and version the result without access to candidate outcomes.
