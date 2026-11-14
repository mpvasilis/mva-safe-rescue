# Track 1 WGS reproducibility map

## 60-second public quickstart

From the repository root, run the standard-library contract smoke test:

```text
python analysis/secure_wgs/synthetic_contract_smoke.py --contract analysis/secure_wgs/public_workflow_contract.json --self-test --json
```

A passing result reports `status` as `passed`, nine connected stages, seven
repository entrypoints, two documentation-only stages, and a passing negative
self-test. Then run the focused public regressions:

```text
python -m pytest -q tests/test_secure_wgs.py tests/test_mosaic_aneuploidy_scan.py tests/test_secure_wgs_reproducibility.py
```

The machine-readable source of truth is
[`analysis/secure_wgs/public_workflow_contract.json`](../analysis/secure_wgs/public_workflow_contract.json).
The operational safeguards and scientific lane inventory are in
[`analysis/secure_wgs/README.md`](../analysis/secure_wgs/README.md).

The synthetic smoke validates orchestration/contracts, not biological
equivalence or the 85-GB rerun. It creates temporary role markers containing no
biological data and deletes them when the check completes.

## Scope and claim boundary

This layer maps the accepted Track 1 WGS workflow without changing its frozen
submission, scientific conclusions, candidate evidence, or protected data. It
separates three different reproducibility claims:

1. **Publicly runnable now:** contract validation, input-manifest logic,
   signed-plan validation, aggregate screen logic, submission-format validation,
   and non-destructive cleanup verification have repository entrypoints.
2. **Runnable only inside an approved protected environment:** data transfer,
   accelerated primary calling, and aggregate screening require controlled
   inputs, reviewed credentials or approvals, pinned reference resources, and
   substantial compute. Public source does not make those inputs or approvals
   public.
3. **Executable contracts with human review:** complementary analysis now has
   `analysis/secure_wgs/public/run_complementary_workflow.py`, and reconciliation
   has `analysis/secure_wgs/public/build_reconciliation_ledger.py`. These require
   protected evidence and pinned external tools for a real analysis. The
   synthetic end-to-end smoke exercises all 21 lane contracts and reconciliation
   behavior; it is not a biological rerun or a replacement for scientific review.

The accepted run's controlled evidence package already contains privacy-safe
receipt evidence for heavyweight execution and review. This map publishes each
receipt's role and validation contract, not its protected contents, and does not
regenerate, replace, or reinterpret any existing receipt.

## Stage-by-stage map

| # | Stage | Execution class | Public entrypoint | Evidence-receipt status |
|---:|---|---|---|---|
| 1 | Contract preflight | Public local | `analysis/secure_wgs/synthetic_contract_smoke.py` | Deterministic aggregate receipt can be regenerated now. |
| 2 | Protected input manifest | Public code; protected inputs | `analysis/secure_wgs/orchestrator.py` | Controlled manifest receipt remains private. |
| 3 | Secure transfer | Public code; external credentials | `analysis/secure_wgs/remote/fetch_signed_plan.py` | Integrity receipt remains inside the approved boundary. |
| 4 | Alignment and small variants | Containerized heavyweight protected run | `analysis/secure_wgs/remote/run_parabricks_deepvariant.sh` | Accepted-run quality and integrity receipt already exists in controlled evidence. |
| 5 | Complementary variant and phenotype analysis | Public execution contract; protected external lanes | `analysis/secure_wgs/public/run_complementary_workflow.py` | Existing lane receipts are retained; real execution needs pinned tools and assets. |
| 6 | Chromosome research screen | Public analyzer; heavyweight protected inputs | `analysis/secure_wgs/mosaic_aneuploidy_scan.py` | Aggregate screen receipt exists; per-site evidence stays protected. |
| 7 | Evidence reconciliation | Public ledger builder; human scientific review | `analysis/secure_wgs/public/build_reconciliation_ledger.py` | Ledger automation does not certify scientific correctness or resolve phase. |
| 8 | Submission validation | Public local | `src/rare_mva/cli.py` | Format validation is publicly repeatable; upload is never automatic. |
| 9 | Cleanup verification | Public non-destructive external verifier | `analysis/secure_wgs/cleanup_verify.py` | A private pass/fail attestation is produced only when every declared resource is absent. |

The original nine-stage JSON deliberately retains its historical classification
and smoke counters. The newer complementary contract and this map document the
added execution layer; a historical `documentation-only` counter is not a claim
that the newer code is absent. Run the newer smoke as well:

```console
python analysis/secure_wgs/public/synthetic_end_to_end_smoke.py --json
```

For every stage, the JSON contract records ordered input and output roles, tool
and container version evidence, validation obligations, fail-closed conditions,
scaling notes, and the evidence-receipt role. Those roles are generic by design:
they do not expose protected source names, identifiers, variants, paths, or
service endpoints.

## Exact public commands

These commands inspect or validate public code without contacting a provider or
reading protected inputs:

```text
python analysis/secure_wgs/synthetic_contract_smoke.py --contract analysis/secure_wgs/public_workflow_contract.json --self-test --json
python analysis/secure_wgs/orchestrator.py --help
python analysis/secure_wgs/orchestrator.py prepare --help
python analysis/secure_wgs/remote/fetch_signed_plan.py --help
python analysis/secure_wgs/mosaic_aneuploidy_scan.py --help
python -m analysis.secure_wgs.cleanup_verify --help
bash -n analysis/secure_wgs/remote/run_parabricks_deepvariant.sh
bash -n analysis/secure_wgs/remote/run_mosaic_aneuploidy_scan.sh
```

To run the public Track 1 CSV validator in a clean Python environment:

```text
python -m pip install -e .
python -m rare_mva validate-track1 path/to/submission.csv --quiet
```

The shell syntax checks do not execute a WGS run. The protected commands are
intentionally documented through their `--help` interfaces only; supplying real
inputs is an authorized-operator action outside this public quickstart.

## Heavyweight prerequisites

The primary calling path requires an independently reviewed container digest,
an approved reference identity, complete protected read pairs, provider and
processor approval, a short-lived transfer plan, and an isolated secure runtime.
The accepted baseline is one accelerator with at least 38 GB memory, at least 32
effective CPU threads, 128 GB RAM, and about 1.2 TB of fast ephemeral storage.

Complementary lanes require separately pinned external environments for
structural and copy-number analysis, specialized variant classes, repeat and
mitochondrial analysis, phenotype-aware prioritization, and phasing. Some tools
or resources may be licensed or separately distributed. Their absence is a hard
stop, not permission to substitute an unpinned alternative.

Nothing in this public layer creates, starts, stops, or destroys cloud compute;
downloads protected inputs; or grants authorization to process them.

## Determinism and privacy boundaries

- The contract uses ordered stages and stable generic role identifiers. The
  smoke result is deterministic for the same exact contract bytes and includes
  both contract and graph digests.
- The smoke materializes only synthetic role markers in a temporary directory.
  It neither simulates sequence content nor evaluates biological calls.
- Public entrypoints must resolve to files inside the repository. Duplicate JSON
  keys, unknown fields, absolute paths, service URLs, credential-like values,
  obvious subject identifiers, and variant-like literals are rejected.
- Protected inputs, per-site evidence, clinical source material, runtime logs,
  signed transfer material, private receipts, and external resource identifiers
  stay outside the repository.
- Caller agreement and ranking scores are technical evidence. They are not
  independent biological confirmation or diagnostic conclusions.

## Scaling strategy

The graph isolates orchestration from byte-heavy analysis. Manifest and
integrity work scales linearly with object count. Primary calling uses parallel
host processing with one high-memory accelerator and fast ephemeral storage;
larger cohorts should use one isolated run per sample or an explicitly reviewed
batch scheduler. Complementary lanes can fan out after primary evidence is
ready, then converge on a bounded reconciliation step. Aggregate chromosome
preparation can parallelize by chromosome while retaining only bounded summaries
for public evidence.

This design makes compute and receipt boundaries explicit, but it does not make
the human reconciliation step infinitely scalable. Accountable review remains a
deliberate bottleneck whenever protected evidence or scientific uncertainty is
material.

## Failure policy

Every stage fails closed. Missing approvals, incomplete pairs, expired transfer
plans, unsafe redirects or paths, integrity mismatches, unpinned images or tools,
reference mismatches, malformed aggregate inputs, missing evidence lineage, and
absent human review all stop the workflow. A provider error is never interpreted
as proof of cleanup. The public validator never uploads or submits a file.

No stage may silently downgrade a method, merge incompatible representations,
publish protected evidence, infer missing confirmation, or turn a research
screen into a clinical conclusion.

## Honest limitations

- The repository does not contain the protected 85-GB dataset, private transfer
  material, cloud approvals, licensed resources, or protected evidence receipts.
- The contract smoke checks connectivity, structure, privacy, and entrypoint
  existence; it does not execute the external tools or reproduce scientific
  outputs.
- The primary public runner is intentionally blocked until an operator installs
  an independently reviewed container digest and satisfies every approval gate.
- Complementary analysis has a public orchestration runner, but no single
  container supplies every protected or separately distributed dependency.
- Evidence reconciliation has an automated ledger. Its protected inputs and
  accountable scientific approval remain separate requirements.
- Re-running with future databases, references, callers, or parameters could
  change rankings; it would be a new analysis, not reproduction of the accepted
  scientific cutoff.
