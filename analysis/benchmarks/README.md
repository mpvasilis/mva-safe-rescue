# Reproducible decision-policy comparison

Run `python analysis/benchmarks/run.py` from the repository root. No private
input, credentials, network call, or nonstandard Python dependency is needed.
The [protocol](PROTOCOL.md) was written before execution on 9 September 2026;
it is a local dated plan, not independent preregistration. Results and hashes
are in [release/summary.json](release/summary.json).

## Track 1: flags are useful only when their provenance is reliable

The test generates 2,400 wholly invented cases, ten candidates per case, with
four evidence-quality regimes and six methods. It calls the real submission
builder and scorer for production caps. Variant and phenotype baselines are
explicit score surrogates, not executions of VEP or Exomiser. Half the cases in
each regime have two-variant truth. A threshold of 0.60 is a benchmark setting,
not a clinical cutoff. No challenge score or diagnostic accuracy is estimated.

| Evidence regime; 600 cases each | Phenotype surrogate top-1 | Production caps top-1 | Improved / regressed cases |
|---|---:|---:|---:|
| Informative review flags | 77.0% | 80.2% | 31 / 12 |
| Uninformative review flags | 78.8% | 65.7% | 11 / 90 |
| Adverse review flags | 77.5% | 41.3% | 4 / 221 |
| True pairs often lack phase | 76.3% | 64.8% | 9 / 78 |

Under informative flags, micro precision at 0.60 rises from 71.9% to 89.0%,
while recall falls from 69.1% to 62.8%. The adverse regime exposes the opposite
behavior. The full table retains false positives, abstention, top-3 recovery,
F-max, and frequency/phase/read-review ablations for every regime.

These results justify a review of evidence-flag provenance and rank changes;
they do not justify weakening the frozen caps to increase a synthetic score.
Unresolved phase stays unresolved. Before final submission, inspect candidates
whose rank changes after caps and reconcile the underlying evidence. Run the
public `analysis/benchmarks/rank_audit.py` on an authorized builder document
inside its existing protected environment; its output is private by default.

The benchmark took 17.06 seconds in the first local run. This is benchmark wall
time only; it excludes full WGS analysis, human review, and scientific work.
Biological variant-class coverage and clinical recovery were not tested.

## Track 2: executable vetoes, with an explicit positive control

Nine invented evidence patterns compare any biochemical pass, an illustrative
weighted score (80% benefit, 20% safety; threshold 0.75), and the production
Safe Rescue decision function. These are deliberately simple comparators, not
validated clinical decision tools or a measured literature baseline.

Safe Rescue admits the eligible all-pass positive control. It blocks each
incomplete, harmful, unqualified, conflicting, or ineligible example. The
weighted score admits examples with confirmed clone harm, indeterminate safety,
or benefit at only one dose; no positive endpoint can compensate for those
failures in Safe Rescue. Tests additionally exercise every safety veto over all
64 combinations of the six benefit statuses. This proves specified software
behavior, not the predictive validity of thresholds or drugs.

For an evidence-grounded five-compound comparison, see
[the public mechanism bridge](../../docs/MECHANISM_BRIDGE.md). No actual candidate
currently satisfies all advancement requirements. Missing evidence is a reason
to investigate or stop, not a measured harm finding.
