# Contributing

Contributions must preserve the repository's public-only, synthetic-only
boundary.

## Before making a change

1. Read `DATA_GOVERNANCE.md`.
2. Work only with public source code and obviously synthetic examples.
3. Never open, copy, transform, summarize, upload, or paste gated or
   patient-derived data for repository work.
4. Keep local sensitive zones outside this checkout. Do not weaken `.gitignore`
   or the privacy scanner to accommodate local data.
5. When testing `build-track1`, keep generated CSV outputs outside the checkout
   and use only hand-authored, obviously synthetic candidate JSON.

## Tests and fixtures

Fixture IDs must begin with `SYNTHETIC_`, use deliberately invented values, and
contain no patient-derived identifiers, coordinates, variants, phenotype text,
or clinical content. Keep fixtures tiny and human-reviewable. A synthetic
fixture must never be produced by de-identifying, perturbing, or sampling a
patient record.

Run before proposing a change:

```console
python -m pip install -e ".[dev]"
python -m pytest -q
python -m rare_mva privacy-scan .
git diff --check
```

Do not include sensitive values in test output, screenshots, commit messages,
issues, reviews, reports, logs, or hosted third-party services. Report a privacy concern
through the project's approved private channel, not a public issue, and follow
`DELETION_RUNBOOK.md`.

## Code quality

- Support Python 3.11 and 3.12 on Windows and Linux.
- Keep runtime dependencies in the Python standard library.
- Add type hints and concise docstrings to public functions and classes.
- Keep CLI output deterministic and machine-readable.
- Add tests for behavior changes and use only synthetic data.
- Preserve the builder's fail-closed public-root, symlink/reparse-point, atomic
  write, and sanitized-output guarantees.

By contributing, you agree that your contribution is licensed under
`CC-BY-4.0`.
