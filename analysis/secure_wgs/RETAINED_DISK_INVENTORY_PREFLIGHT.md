# Retained-disk inventory preflight gate

This gate is for one narrow recovery action: start the designated stopped Vast
instance, inspect the retained disk only for file identity, size, and SHA-256,
write generic inventory evidence into one new absent namespace, and then apply
the owner's signed stop/retain or destroy disposition.

It does not run VEP, xTea, breadth analysis, prioritization, structural
integration, scientific interpretation, candidate changes, publication,
release, or upload. All those permissions are fixed to `false` in the contract.
The validator never contacts Vast and never performs a lifecycle action.

## Two deliberately separate gates

`schema-check` accepts the repository template only as a structurally valid
draft. Its output always says `authorization_effective:false`, even if the
document contains owner-completed fields. A schema acceptance must never be
used as an execution gate.

`authorization-check` is the only current-time gate. It requires all of the
following in private files outside the public repository:

1. a completed `OWNER_SIGNED` authorization;
2. a matching independent signature-verification receipt;
3. the expected abstract private-host binding SHA-256; and
4. the exact new output namespace.

The code validates byte hashes, terms binding, signer/verifier separation, the
time window, runtime/cost caps, and fixed deny flags. The independent receipt is
the accountable evidence that the human signature and signer identity were
actually verified; this standard-library validator does not manufacture or
cryptographically establish that human identity.

Start from
`retained_disk_inventory_preflight_authorization.template.v1.json`, but keep the
completed copy and every referenced receipt outside this repository. Do not
replace blanks with guesses.

## Owner-entered and independently verified values

The owner must supply:

- SHA-256 of the exact preflight plan;
- SHA-256 of the private Vast host-binding receipt (never the instance ID in
  this public contract);
- SHA-256 of the approved private input-scope receipt;
- maximum runtime in seconds and maximum provider cost in integer US cents;
- issue, not-before, and expiry instants in second-resolution UTC (`Z`), with a
  maximum 24-hour authorization lifetime;
- a new generic namespace matching `preflight-...` that is confirmed absent;
- explicit success and failure dispositions, each either
  `STOP_COMPUTE_RETAIN_DISK` or `DESTROY_INSTANCE_AND_RETAINED_DISK`;
- signer name, signing time, and the exact attestation text from the validator;
  and
- SHA-256 of a separate independent signature-verification receipt.

The independent verifier supplies the matching terms SHA-256, signer and
signature time, signature method
`OUT_OF_BAND_OWNER_SIGNATURE_INDEPENDENTLY_VERIFIED`, signature-evidence
SHA-256, verifier name, independence flag, and verification time. The verifier
must not be the signer.

## No-silent-drop receipt

The preflight implementation must first seal a source manifest with ordered
per-record objects. Each object contains a sequential generic ID
(`input-000001`, ...) and a nonzero lowercase SHA-256 of its pinned private
source-identity receipt. Source names and paths are forbidden from this generic
surface. The manifest also binds the signed input scope and enumeration time.
The inventory receipt must repeat each `(record_id, source_identity_sha256)`
pair exactly once and in the same order. Every row must have exactly one of:

- `INVENTORIED` with `EXPLICIT_OUTPUT`;
- `EXPLICITLY_EXCLUDED` with `EXPLICIT_DISPOSITION`;
- `UNSUPPORTED` with `EXPLICIT_DISPOSITION`; or
- `FAILED` with `EXPLICIT_DISPOSITION`.

Every row also needs a reason code and evidence SHA-256. The validator checks
the exact equation

`source_count = inventoried + explicitly_excluded + unsupported + failed`.

It rejects missing, duplicate, reordered, substituted, swapped, or extra
identity pairs and inconsistent counts. Counts are exact integers; JSON
Booleans are rejected even though Python otherwise compares `true` equal to
integer `1`.
It also requires exact elapsed seconds derived from the signed-window
timestamps and a conservative provider-cost upper bound in integer US cents;
both must remain within the owner's caps. Inventory cannot begin before the
independent signature verification time.
This proves reconciliation against the sealed source manifest; completeness of
the original disk enumeration still depends on the separately pinned input
scope and preflight implementation.

Example schema-only check (safe; does not authorize anything):

```text
python -m analysis.secure_wgs.retained_disk_inventory_preflight schema-check \
  --authorization analysis/secure_wgs/retained_disk_inventory_preflight_authorization.template.v1.json \
  --json
```

The effective and inventory commands intentionally require private paths and
host-binding values and are documented by `--help`. Never paste credentials,
instance identifiers, protected filenames, or protected paths into these JSON
documents or terminal arguments.
