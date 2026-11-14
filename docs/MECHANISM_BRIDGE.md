# Mechanism to experiment: a conditional, falsifiable bridge

Prepared 9 September 2026. Public evidence and experimental design only.
This document does not identify the challenge participant's gene or variants.

## What the argument actually supports

The proposal investigates whether downstream stress modulation can restore
lineage-correct neural output after a compatible spindle-checkpoint defect,
without helping abnormal clones persist. It does not claim that increasing
stress tolerance repairs a causal allele. The model applies only after the
authorized case review selects a compatible mechanism. Partial gene depletion
cannot automatically represent a missense allele or a distinct MVA mechanism.

The public mouse work reinforces this qualification requirement: different
BubR1 alleles and tissues can produce different phenotypes. Our new
[GSE134780 analysis](../analysis/external/GSE134780/README.md) found selected
expression changes, including fat Hsf1 increases, but no coherent HSP70 or
cardiolipin panel support. This is a reason to measure engagement, not evidence
that either probe works. The primary fly analysis remains 0/12 supported modules.

## Same evidence, different decisions

The simple comparison asks whether a mechanism sounds relevant enough to test.
Safe Rescue asks whether functional benefit and every applicable safety gate
are satisfied. These answer different questions; their disagreement is not an
accuracy score. General safety assessment is not claimed as a new invention.

| Test article | Mechanism-match rationale | Evidence or contradiction that matters | Safe Rescue decision today |
|---|---|---|---|
| Arimoclomol | Proteostasis / HSF1-HSP70 experimental probe | Published fly rescue involves Hsp60/Hsp60c; this is not interchangeable with HSP70. Mouse panel does not validate a coherent HSP70 response. No MVA response measurement. | Eligible for qualification; no advancement evidence. Require engagement plus neural and mitochondrial rescue. |
| Elamipretide | Orthogonal mitochondrial benchmark | Mitochondrial function is a relevant testable downstream hypothesis. Neither the fly module nor mouse cardiolipin panel validates response. | Eligible for qualification; no advancement evidence. Require functional benefit at both doses and full safety. |
| Sirolimus / rapamycin | Survival and autophagy relevance could motivate testing | Same-model publication reports more aneuploid neural stem cells without recovery of differentiated progeny or brain size. This is not a clinical harm finding. | Uncoupled-rescue control; cannot advance in the prespecified two-candidate family. |
| Everolimus | Translational mTOR-class comparator | Class relationship is not evidence of identical response in this model. | Comparator only; cannot advance. |
| Acetylcysteine | Redox-direction control | A redox change alone does not establish neural recovery or acceptable clone behavior. | Control only; cannot advance. |

Candidate-specific pharmacology and contradictory studies remain in
[CANDIDATE_RATIONALE.md](CANDIDATE_RATIONALE.md), with claim-level sources in
[CLAIM_LEDGER.tsv](CLAIM_LEDGER.tsv). The same-model premise is the
[SAC/CIN primary study](https://pubmed.ncbi.nlm.nih.gov/41820377/). Mouse context
comes from the [JCI study](https://www.jci.org/articles/view/126863) and
[GEO](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE134780).

## The experiment that could change our conclusion

1. Confirm case-mechanism applicability in the protected review. If incompatible,
   revise the model or stop this branch; do not use the public data to infer it.
2. Qualify the neural model using two independent guides, target engagement,
   abnormal chromosome behavior, and differentiation fidelity. Do not select a
   guide or dose for producing a favorable candidate outcome.
3. Compare the two eligible candidates with vehicle at two locked adjacent
   noncytotoxic exposures. Require day-21 live MAP2+TUBB3+ neuron yield per 100
   starting viable PAX6+SOX2+ NPCs, ATP-linked oxygen consumption per viable cell,
   and TMRM signal per mitochondrial mass to pass at both exposures.
4. Require all chromosome, clone, selectivity, malignant-fitness, invasion and
   chemotherapy-resistance gates. Missing or uncertain safety means no advance;
   it is not automatically proven harm. Confirm using an independent guide or
   orthogonal rescue model. Calibrate margins and sample size before confirmation.

The [executable contract](../src/rare_mva/track2/decision.py) preserves these
qualitative decisions. It consumes reviewed statuses; it does not infer them
from RNA expression or set clinical thresholds. The [synthetic comparison](../analysis/benchmarks/README.md)
demonstrates its behavior, including a passing positive control.

## Review packet and unresolved evidence

The qualified genetics reviewer needs the existing protected case evidence and
the applicability decision; the pharmacology reviewer needs the five-row table,
candidate dossier, null results, and experiment design. Record agree/disagree,
the exact reason, conflicts, reviewer qualifications, date, and source version
in the existing external release record. Keep private variants out of this file.

No laboratory has been engaged or quoted by this work. No measured drug-response
result, binding laboratory budget, account-setting attestation, or human review
has been invented. The immediate computational work is complete; those external
facts remain necessary to support a stronger translational claim.
