# Suspected sensitive-data exposure runbook

Use this runbook if gated, clinical, genomic, patient-derived, or secret material
may have entered this checkout, Git history, an issue, a log, a hosted tool, or a
shared artifact. Do not quote the exposed content while reporting the incident.

## 1. Contain

1. Stop commits, pushes, CI jobs, sharing, and hosted-tool use for the affected
   material.
2. Restrict access to the repository or artifact using the hosting provider's
   controls. Do not make additional copies for investigation.
3. Notify the project privacy/security owner and organizer through the approved
   private channel. Record only the minimum path, time window, and systems
   affected, not patient content.
4. Preserve authorized audit metadata. Do not preserve exposed data merely for
   convenience; follow incident-response and legal instructions.

## 2. Remove local working copies

Identify exact affected paths without printing their contents. Remove them from
the working tree and staging area, then place any required incident copy only in
an approved controlled location. Verify with the path-only privacy scan and
`git status`. Also check build outputs, caches, notebooks, reports, archives,
virtual environments, temporary directories, and local backups.

## 3. Revoke and rotate credentials

If a token, password, key, connection string, or signed URL may have been
exposed, revoke it first, rotate it at its issuer, update authorized systems, and
review access logs. Treat deletion from Git as insufficient credential
remediation.

## 4. Rewrite Git history when directed

Coordinate before rewriting shared history. Make a protected backup only if the
incident lead authorizes it. Using an approved `git-filter-repo` installation,
replace `<EXACT-AFFECTED-PATH>` with a verified repository-relative path:

```console
git filter-repo --path <EXACT-AFFECTED-PATH> --invert-paths
```

For several exact paths, provide a separate `--path` for each. Inspect rewritten
refs, run the privacy scan and tests, then force-push only the specifically
approved branches and tags. Ask collaborators to discard old clones and create
fresh ones; expire local reflogs and garbage-collect only under the incident
lead's instructions.

**History rewriting does not erase remote copies.** Existing clones, forks,
caches, CI artifacts, package indexes, search indexes, logs, backups, hosted
services, and other recipients may retain the material. Contact every relevant
provider or owner for deletion under their process and obtain confirmation where
possible. For an organizer-compatible processor, record any purpose- and
time-limited operational logs that the team cannot directly delete; the
organizer's 2026-08-27 clarification limits the team's deletion attestation to
systems it controls, without excusing an unauthorized disclosure or unsuitable
provider terms.

## 5. Verify and document privately

- Confirm the exact files are absent from the working tree, all reachable Git
  refs, CI artifacts, releases, packages, issues, reports, and hosted tools.
- Confirm revoked credentials no longer work and review for unauthorized use.
- Re-run tests and `python -m rare_mva privacy-scan .`.
- Record scope, notifications, deletion confirmations, residual risks, and
  follow-up controls in the approved private incident system.
- Do not place incident evidence or patient details in this public repository.
