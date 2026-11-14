# Track 1 local runbook

This runbook describes the boundary around the local Track 1 candidate builder.
It is ranking support, not a diagnostic system, clinical report, or substitute
for expert review.

## Public and local zones

The Git checkout is the **public zone**. It may contain source code,
documentation, and small hand-authored fixtures whose labels and values are
obviously synthetic. Never copy gated or patient-derived identifiers, variants,
coordinates, phenotype prose, reads, annotations, candidate JSON, or generated
submissions into this zone. Do not paste them into public logs, issues, or
prompts. Hosted processing, if used at all, belongs to the controlled workflow
and requires documented organizer-compatible processor terms: no provider
rights or training use, purpose- and time-limited retention, exact plan/settings
review, no reusable feedback, and project authorization.

An authorized workflow must use a separately governed **local zone** outside
the checkout. Candidate JSON, reference assets, annotation caches, working
files, and the generated CSV stay there. Apply the applicable access controls,
encryption, retention rules, and audit procedures. The builder enforces only a
filesystem boundary; it does not grant authority to access or process data.

Set `--public-root` to the checkout when the command is launched elsewhere:

```console
python -m rare_mva build-track1 CANDIDATES.json OUTPUT.csv --public-root PATH_TO_PUBLIC_CHECKOUT
python -m rare_mva validate-track1 OUTPUT.csv --expected-proband-id EXPECTED_PROBAND_ID --quiet
```

`EXPECTED_PROBAND_ID` is supplied by the authorized user for the validation
run. Do not hard-code or publish the actual controlled identifier.

The output directory must already exist. Output is rejected if it is equal to
or inside the public root, matches the input JSON, is a symlink or Windows
reparse point, or has a symlink/reparse-point ancestor. A regular existing CSV
may be atomically replaced. Successful `--quiet` commands produce no standard
output; errors contain sanitized rule codes rather than candidate content or
absolute output paths.

The builder captures the output-parent identity, checks that the newly created
temporary file is the same file as its open descriptor, and resolves that file
outside the public root before writing the header or any candidate row. It
checks parent and temporary-file identity again before replacement and validates
the final destination. On Windows it holds handles without delete sharing for
the complete ancestor chain, preventing those directories from being renamed
during the operation. On POSIX it holds a no-follow directory descriptor and
uses descriptor-relative replacement; identity and resolved-location checks
fail closed if a path changes at a checked boundary. An empty temporary file
created during a detected race contains no candidate content and is removed
before error return when the filesystem permits cleanup.

## Candidate contract and provisional confidence

The JSON contract is intentionally exact. It permits 1 to 10 candidates, one or
two strictly validated variants per candidate, explicit finding type, notes,
read-validation status, frequency status, and phase. It rejects extra keys,
duplicate candidate sets, duplicate compound members, compound `cis` phase,
and line breaks in notes. Compound members are ordered genomically; candidates
are stably ordered by final EPCR.

For the current `synthetic_only` calibration milestone, the final EPCR is the
lowest of the raw value and every applicable cap:

| Condition | Cap |
| --- | ---: |
| Synthetic-only calibration | 0.80 |
| Reads not validated | 0.75 |
| Frequency status unknown | 0.50 |
| Compound phase unresolved | 0.55 |

Confirmed or probable trans phase adds no cap. Phase is never inferred. Values
are serialized deterministically with at most six significant decimal digits.
Visible serialized ties preserve input order. Values too small to remain
positive in the existing float-based validator are rejected. Notes are copied;
the builder does not invent phenotype or evidence prose. Every user string must
be strict UTF-8; JSON-escaped unpaired surrogates are rejected.

These caps are conservative workflow controls, not calibrated clinical
probabilities. Review the ranked result under the governing protocol before any
submission or downstream use.

## WSL2 and offline annotation architecture

On Windows, an isolated WSL2 environment can host Linux-only annotation tools
such as VEP. Keep the VEP executable, plugins, reference assembly, and pinned
offline cache versions in the governed local zone. Run VEP in offline/cache
mode with network access disabled, record tool and reference versions locally,
and send only the minimum local intermediate needed to the next local step.

A safe high-level flow is:

```text
authorized local source
  -> offline WSL2 annotation and evidence review
  -> strict candidate JSON in the local zone
  -> build-track1
  -> validated Track 1 CSV in the local zone
```

Do not mount the public checkout as an annotation output location. Do not place
VEP caches, logs, temporary files, candidate JSON, or generated CSVs in the
repository. The public test fixture exercises only invented synthetic values;
it is not a template populated from any real record.

## Preflight and handoff

1. Confirm authorization and that all local paths are outside the public zone.
2. Confirm the assembly, annotation cache, and evidence versions under the
   governing protocol.
3. Review every candidate field; do not infer phase or fill notes automatically.
4. Run `build-track1`, then `validate-track1 --expected-proband-id
   EXPECTED_PROBAND_ID --quiet` on the generated CSV, replacing the placeholder
   with the authorized user-supplied identifier.
5. Inspect the local CSV through an approved local process and hand it off only
   through the authorized channel.
6. Apply the local retention and deletion policy, including genome-scale
   intermediates and stored prompts containing blocks of variant data. Record
   any approved hosted processor, plan/tier, settings, and operational-retention
   terms. Run the repository privacy scan separately to confirm no restricted
   paths were introduced.
