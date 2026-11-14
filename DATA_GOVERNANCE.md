# Data governance

This repository is a **public/synthetic zone**. It contains public source code,
documentation, and small, deliberately invented fixtures only.

## Zones

### Public/synthetic zone

Allowed:

- source code and configuration that contain no patient-derived material;
- public specifications with appropriate attribution;
- small fixtures invented from scratch and clearly labeled `SYNTHETIC`;
- documented public assets whose provenance and redistribution terms have been
  reviewed.

A synthetic record is not a redacted, shifted, hashed, summarized, or otherwise
transformed patient record.

### Gated/controlled zone

Gated, clinical, genomic, or patient-derived material belongs only in an
approved access-controlled local environment, separate from this repository.
Examples include variants and coordinates, identifiers or pseudonyms,
phenotypes, pedigrees, sequence/alignment files, organizer ground truth,
clinical documents, derived embeddings, model artifacts trained on controlled
data, and outputs that could reveal those inputs.

## Handling rules

- Do not copy gated material into this checkout, Git, fixtures, public logs,
  reports, issues, pull requests, chat messages, screenshots, or ordinary
  hosted third-party services.
- Do not inspect gated patient data while developing or testing this package.
- Keep authorized processing local, access-controlled, encrypted as required,
  and limited to the minimum necessary people and systems.
- The organizer's 2026-08-27 clarification permits a hosted service to act as a
  processor only when it takes no rights in inputs or outputs, does not train on
  them, and retains logs only for a limited operational purpose and time. Verify
  the exact provider, plan/tier, applicable terms, and account settings; opt out
  of training and do not submit feedback that can be reused. Record those facts
  in the controlled methods log. Until that verification and project approval
  are complete, keep all gated content local.
- Data-access approval does not by itself imply permission to publish,
  redistribute, or use an unverified hosted service.
- Use the local path-only privacy gate before commits and in CI. It is a defense
  in depth control, not proof that content is safe.

Files larger than 5 MiB are rejected by the privacy gate unless they are under
`public_data` or `public-assets` and that directory contains `README.md`,
`PUBLIC_ASSETS.md`, or `public-assets.md`. Documentation must state provenance,
license, purpose, and a reviewer; the scanner checks only that such a marker
exists and never reads file contents.

The gate rejects symbolic links without following them, so an apparently safe
repository path cannot alias data elsewhere. Traversal or metadata errors also
fail closed as stable path-only findings.

## Access, retention, and disposal

Use least privilege and organizer-approved storage. Retain authorized inputs
and outputs only for the approved period. The organizer's deletion boundary
includes VCF/BAM/CRAM files and indexes; copies, subsets, slices, or reformats;
genome-scale per-variant intermediates and notebook/cache state; stored prompts
containing blocks of variant data; and weights, embeddings, or fine-tunes
trained on the raw genome. Findings such as the submitted ranked candidate
variants, HPO terms, gene/pathway rankings, mechanism analyses, and drug
candidates may be retained when otherwise allowed. Record access, service
configuration, and deletion using approved controlled systems without copying
sensitive details into this repository. The deletion attestation covers systems
the team controls; document any permitted provider's time-limited operational
logs that the team cannot directly delete.

Source: [Sage Privacy and Compliance clarification, 2026-08-27](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/2).

If exposure is suspected, stop work, avoid further copying, use a private
incident channel, and follow `DELETION_RUNBOOK.md` immediately.
