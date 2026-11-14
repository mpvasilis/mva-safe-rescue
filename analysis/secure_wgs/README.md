# Secure WGS execution scaffold

> **Judge quickstart:** start with the privacy-safe
> [Track 1 reproducibility map](../../docs/TRACK1_REPRODUCIBILITY_MAP.md) and its
> [machine-readable workflow contract](public_workflow_contract.json). The
> synthetic smoke validates orchestration and entrypoint boundaries without
> biological data or provider access.

This directory is a **public-safe scaffold**, not authorization to process the
challenge case. No controlled dataset file, original filename, signed URL,
clinical text, token, run log, result, instance address, or completed approval
record belongs in this repository. The scripts deliberately fail closed and
emit only generic status/count messages.

No Vast instance is created, contacted, or destroyed by this scaffold. The
operator must perform the provider and dataset approvals below before any
controlled transfer.

## Non-negotiable provider gate

Use only a Vast **Secure Cloud / datacenter** offer (`datacenter=True`), never a
merely Verified marketplace host. Vast states that hosts can technically access
files on their machines; Secure Cloud is a vetted datacenter category, not by
itself a BAA, HIPAA determination, or guarantee that plaintext genomic data is
inaccessible to the host.

Before transfer, an authorized human reviewer must obtain and privately retain:

1. the applicable Vast plan/tier and executed DPA or equivalent terms;
2. written confirmation that Vast and the selected infrastructure provider act
   only as processors for this project, acquire no rights in the data, do not
   train on or otherwise use it, retain it only for limited operations, and can
   provide deletion confirmation;
3. confirmation that the agreement covers pediatric genetic and health data and
   satisfies the organizer's third-party processor conditions;
4. the selected offer ID, machine ID, datacenter status, retention terms,
   reviewer, and approval date; and
5. the exact Parabricks image digest and reference identity.

Copy `provider_gate.example.json` to a **private directory outside this repo**,
replace every placeholder, and set a Boolean to `true` only after evidence is
reviewed. The remote runner rejects the example as shipped. Vast's DPA is
substantially processor-oriented and lists genetic/health data, but its
"Anonymous Data" own-use language and the absence of an explicit no-training
sentence require written clarification for this challenge. If clarification is
not obtained, do not upload.

The data are necessarily plaintext while the caller runs. Vast recommends
application-level encryption and external key management, but encryption alone
cannot hide actively processed reads from the host. Therefore the DPA/provider
gate (not disk encryption) is the decisive control. Use ephemeral instance disk;
do not attach a persistent volume unless the same approval explicitly covers it.

## Hardware and cost selection (read-only first)

The reproducible baseline requires one GPU with at least 38 GB memory; prefer an
L40S/A6000 48 GB or A100 80 GB, at least 32 effective CPU threads, 128 GB RAM,
and 1.2 TB fast local disk. The extra disk margin supports the 85 GB compressed
input, reference indexes, BAM, gVCF, QC, and export staging. Vast instance disk
cannot be resized after creation.

Search only; this command does not rent anything:

```powershell
vastai search offers 'datacenter=True verified=True rentable=True rented=False num_gpus=1 gpu_ram>=48 cpu_cores_effective>=32 cpu_ram>=128 disk_space>=1200 reliability>=0.99 static_ip=True direct_port_count>=1' --type on-demand --storage 1200 --order dph --raw
```

Privately review the returned `dph`, `storage_cost`, transfer prices, maximum
duration, GPU model, disk bandwidth, location, host/machine IDs, and a fixed
spend ceiling. Re-run the query immediately before rental because offers and
prices change. Use on-demand capacity only.

Rental remains a manual approval boundary. Only after the gate is complete,
substitute the reviewed offer and a verified NGC digest:

```powershell
vastai create instance $REVIEWED_OFFER_ID --image 'nvcr.io/nvidia/clara/clara-parabricks:4.7.1-1@sha256:REPLACE_WITH_VERIFIED_64_HEX' --disk 1200 --ssh --cancel-unavail --label mva-secure-wgs
```

Do not use `--jupyter`, `--direct`, `--env -p`, an on-start command containing a
secret, interruptible bidding, or registry credentials on the command line. Use
a dedicated passphrase-protected SSH key; upload only its public half to Vast,
keep the private half off-instance, and remove the public key after cleanup.
If NGC authentication cannot be arranged without exposing a credential in Vast
configuration/history, stop and resolve that before rental.

Two values intentionally remain blocked:

- `parabricks_image_digest`: obtain from the authenticated NGC manifest and
  independently verify it; a tag or `pbrun --version` is not a digest check.
  Patch that reviewed value into `APPROVED_PARABRICKS_IMAGE_DIGEST` in the
  public runner, use the same digest in the create command/private gate/runtime
  variable, and verify the control-plane image reference before transfer. The
  runner intentionally cannot start while its placeholder remains.
- `PUBLIC_BUNDLE_SHA256`: NVIDIA documents its public sample URL but does not
  publish an archive SHA-256 on the cited page. Record an independently approved
  digest privately before the full public smoke benchmark.

## Exact staged method

### 0. Public-only preflight

Copy only `remote/public_smoke_test.sh` to a clean instance. It first verifies
Parabricks 4.7.1-1, the GPU, and required tools without case data:

```bash
bash public_smoke_test.sh preflight
```

The optional public benchmark runs NVIDIA's documented sample through `fq2bam`
and DeepVariant only when both approval variables are present:

```bash
PUBLIC_SMOKE_APPROVED=YES \
PUBLIC_BUNDLE_SHA256=REPLACE_WITH_APPROVED_64_HEX \
bash public_smoke_test.sh benchmark
```

Do not transfer controlled data unless preflight succeeds and the image digest,
not just its displayed version, matches the private provider gate.

### 1. Metadata-only private manifest (no 85 GB local download)

Run from the repository root on the trusted local machine. `hf auth login` may
already have stored a token; `huggingface_hub` uses that cache. `HF_TOKEN`, if
set in the process environment, takes precedence. The command downloads only
gated repository metadata, requires an LFS SHA-256 and size for every FASTQ,
pairs reads privately, pins the resolved commit, and prints only generic counts:

```powershell
python -m analysis.secure_wgs.orchestrator prepare-hf `
  --manifest 'D:\mva-private\control\input_manifest.json' `
  --sample-id SAMPLE01 `
  --revision main
```

The manifest is controlled metadata because it contains original repository
paths. It must remain outside this repository with restrictive permissions. The
token is used in memory and is never written into the manifest.

For already-local FASTQs, `prepare` is an alternative. It validates a private
absolute input directory, rejects symlinks and repository paths, assigns generic
`SAMPLE01_L###_R[12].fastq.gz` aliases, and calculates SHA-256:

```powershell
python -m analysis.secure_wgs.orchestrator prepare `
  --input-dir 'D:\mva-private\source' `
  --manifest 'D:\mva-private\control\input_manifest.json' `
  --work-dir 'D:\mva-private\work' `
  --materialize hardlink
```

### 2. Short-lived direct transfer plan

Resolve each gated Hub object to an expiring HTTPS URL at the pinned commit:

```powershell
python -m analysis.secure_wgs.orchestrator sign-plan `
  --manifest 'D:\mva-private\control\input_manifest.json' `
  --output 'D:\mva-private\control\signed_transfer_plan.json'
```

The Hub bearer token is sent only to `huggingface.co`; redirects are captured so
the Authorization header is not forwarded to object storage. The output contains
signed bearer URLs and is therefore a short-lived secret even though it contains
no HF token. Transfer it and the private manifest over dedicated-key SSH, never
paste either into a terminal, ticket, chat, or log.

On the approved instance, create the fixed private layout and use the downloader:

```bash
install -d -m 700 /workspace/mva-secure-wgs-run/{input,control,reference,output,logs,tmp}
python3 fetch_signed_plan.py \
  --plan /workspace/mva-secure-wgs-run/control/signed_transfer_plan.json \
  --destination /workspace/mva-secure-wgs-run/input
rm -f /workspace/mva-secure-wgs-run/control/signed_transfer_plan.json
```

`fetch_signed_plan.py` accepts only HTTPS URLs, unexpired plans, an empty target,
generic target names, exact sizes, and SHA-256 matches. It never prints URLs or
filenames. Deleting the plan after verified transfer limits capability lifetime;
revoking/rotating the local HF credential is still required after the run.

### 3. Reproducible germline baseline

Place the privately completed `provider_gate.json` and `input_manifest.json` in
`/workspace/mva-secure-wgs-run/control`, then run:

```bash
SECURE_CLOUD_APPROVED=YES \
PROCESSOR_TERMS_APPROVED=YES \
CONTROLLED_TRANSFER_APPROVED=YES \
REFERENCE_BUILD_APPROVED=YES \
RUN_MODE_APPROVED=RESEARCH_ONLY \
PARABRICKS_IMAGE_DIGEST=sha256:REPLACE_WITH_VERIFIED_64_HEX \
bash run_parabricks_deepvariant.sh
```

The runner performs, in order:

1. approval, image-version, hardware, disk, symlink, empty-output, and manifest
   checksum/size/FASTQ checks;
2. download of NCBI `GCA_000001405.15` GRCh38 no-alt analysis-set FASTA, locked
   to archive MD5 `a08035b6a6e31780e96a34008ff21bd6`, followed by content and
   BWA/samtools index checks;
3. Parabricks `fq2bam` alignment, coordinate sorting and duplicate marking with
   one generic read group per lane and BWA `-K 10000000` compatibility setting;
4. duplicate/QC metrics, `samtools quickcheck`, index, flagstat/stats, and
   Parabricks `bammetrics`;
5. Parabricks 4.7.1-1 DeepVariant `shortread` germline calling with its shipped
   model, producing both VCF and gVCF; and
6. VCF/gVCF parse/index checks, VCF statistics, deterministic stage logs,
   output/reference checksums, and a mandatory human-review marker.

BQSR is intentionally omitted: DeepVariant does not require it, and adding it
without frozen known-sites resources would create an unreviewed reference
dependency. Parabricks 4.7.1-1 documents compatibility with Google DeepVariant
1.9.0; this baseline must not be described as DeepVariant 1.10.0.

### 4. Analysis needed for a competitive submission

This runner covers **germline SNVs and small indels only**. Preserve its gVCF for
future trio calling, compare the fresh VCF with the organizer-supplied VCF after
normalization, and manually review discordant rare variants in the BAM. A strong
submission also needs separately pinned and validated SV/CNV, mitochondrial, and
repeat-expansion lanes; offline annotation; phenotype/inheritance ranking; read
review; and segregation/phasing where possible. Do not silently infer trans
compound heterozygosity from a singleton short-read VCF.

The authorized private workflow uses the following prespecified, complementary
lanes. Completion and case-level findings remain private; listing a tool here is
not a claim that it found or excluded a causal variant.

| Question | Pinned private method | Interpretation boundary |
|---|---|---|
| Germline SNVs and small indels | Parabricks 4.7.1-1 `fq2bam` plus its documented DeepVariant 1.9-compatible short-read model | Fresh calls require BAM review, normalization, inheritance review, and clinical confirmation. |
| Structural and copy-number variation | Manta 1.6, DELLY 2.3, and CNVpytor 1.3.2 with depth plus B-allele-frequency evidence | Caller agreement is technical corroboration from shared reads, not independent biological confirmation. |
| Mobile-element insertions | xTea v0.1.9, immutable commit `20c7e9fbecbe4c0e35eb0766c4c7b4e6125fe71e`; Alu-only complete germline workflow when the authorized mechanism branch warrants it | A targeted clip/discordant-pair signal is triage only. Any candidate requires two-junction review and breakpoint confirmation. |
| Short tandem-repeat expansions | ExpansionHunter 5.0.0 with its pinned GRCh38 variant catalog and male/female sensitivity runs when reported sex is unknown | The catalog is not genome-wide discovery, and negative short-read output does not exclude every repeat disorder. |
| Mitochondrial SNVs/indels and heteroplasmy | GATK 4.7.0.0 mitochondrial Best Practices transcribed with standard and shifted chrM calling, Haplocheck, blacklist filtering, and the separate 4.7 `NuMTFilterTool` | Interpret AF/AD rather than diploid GT; low heteroplasmy, NUMTs, tissue restriction, and large mtDNA rearrangements remain limitations. |
| Coding disease prioritization | Exomiser 15.1.0 with 2602 data; official exome preset plus a human-only, no-blacklist sensitivity lane | Scores prioritize; the ClinVar whitelist and partial automated ACMG fields are exposed, not treated as independent confirmation. |
| Joint sequence/SV/MEI prioritization | Exomiser 15.1.0 official exome preset on two separately audited combined VCFs: DeepVariant+Manta as the supported primary lane and DeepVariant+xTea as an exploratory sensitivity lane | Manta and xTea representations are never scored together; sequence/SV compound hypotheses require read review and phase/segregation confirmation. |
| Noncoding disease prioritization | Genomiser/Exomiser 15.1.0 genome model with ReMM 0.4 and SpliceAI; official preset plus a human-only, no-blacklist sensitivity lane | ReMM/SpliceAI support triage of regulatory or splice hypotheses; they do not establish pathogenicity. |
| Disease-level phenotype/genotype likelihood | LIRICAL 2.4.1: frozen-Phenopacket baseline, default OMIM+DECIPHER genotype run, strict inheritance sensitivity, and Orphanet-augmented sensitivity | LIRICAL probabilities are model outputs, not calibrated clinical probabilities; database-specific probabilities are not averaged. |
| Local phase and read support | WhatsHap 2.8 plus independent-fragment allele metrics | A shared short-read phase set is supportive only; parental segregation or direct long-molecule phasing is stronger evidence. |

Reconciliation is ordered rather than vote-based: analytical validity first,
then inheritance/mechanism and phase, curated gene/variant evidence, phenotype
fit, and finally a **rank envelope** recording the best rank, worst rank, and
prespecified lanes containing each candidate. Exomiser, Genomiser, and LIRICAL
reuse HPO, OMIM, ClinVar, and prediction resources, so apparent concordance is
not independent replication and their scores must not be averaged.

### Track 1 hypothesis construction and scoring boundary

The live organizer form accepts at most ten GRCh38 candidate rows. Each row is
one causal hypothesis: either a single variant or one proposed compound-
heterozygous pair. The final builder must emit the official column order
(`proband_id`, the two variant slots, `epcr`, `finding_type`, and `notes`), keep
`epcr` in `(0, 1]` and monotonically descending, and keep primary and secondary
findings explicitly separated.

Candidate construction is therefore deliberately narrow:

1. fail candidates that do not pass the relevant call/read-quality and
   reference-build checks;
2. represent a two-allele recessive hypothesis as one paired row only when the
   molecular mechanism is coherent, recording unresolved phase rather than
   silently assuming trans configuration;
3. order the surviving hypotheses using the evidence hierarchy above, not by
   averaging dependent prioritizer scores;
4. use `epcr` as an auditable within-submission ranking confidence, not as a
   calibrated probability of diagnosis; and
5. freeze the ranked list before any leaderboard upload. The six permitted
   uploads are not treated as an adaptive search over the hidden answer.

This policy is designed for both organizer metrics: rank points reward putting
the complete causal hypothesis near the top, while F-max penalizes burying it
among weak primary guesses. As inspected on 2026-08-27, the live FAQ says that
secondary findings do not hurt the automated score, but the public evaluator
(last modified at `37e25dceda63ecec7c5b2ebeffd1ea0052ad886e`, observed at
Space head `d27c33953ecb0cfd7fa316c7cd93ff0ffb05cc1d`) treats `finding_type` as
informational and includes every row
in the EPCR sort and F-max threshold sweep. Until those two surfaces agree, the
release policy is stricter than either: keep incidental findings in the report,
not in the scored CSV, and re-audit the evaluator immediately before upload.

Short reads and this baseline do not exclude exon/large CNVs, balanced SVs,
repeat expansions, complex regions, regulatory variants, low-level/tissue-limited
mosaicism, mitochondrial variants, or unresolved phase. Bulk-blood WGS cannot
confirm mosaic variegated aneuploidy; cytogenetic testing remains necessary.

### 5. Export, destroy, and verify

Export only organizer-permitted deliverables over SSH, verify their SHA-256 on a
trusted destination, and retain private QC/provenance separately. Then destroy
the exact instance and any explicitly attached volumes using the IDs recorded in
the private gate. Stopping is not deletion:

```powershell
vastai destroy instance $REVIEWED_INSTANCE_ID
vastai delete volume $REVIEWED_VOLUME_ID
```

Do not run the volume command when no volume was created. After the private local
staging paths are also removed through the project's approved deletion runbook,
verify absence without printing provider responses:

```powershell
python -m analysis.secure_wgs.cleanup_verify `
  --instance-id $REVIEWED_INSTANCE_ID `
  --volume-id $REVIEWED_VOLUME_ID `
  --expected-deleted-path 'D:\mva-private\work' `
  --expected-deleted-path 'D:\mva-private\control' `
  --attestation 'D:\mva-audit\cleanup_attestation.json'
```

The helper is non-destructive. It checks exact local-path absence plus API-visible
instance/volume absence and writes a private attestation. This is not proof that
provider backups are erased; retain the contractual deletion confirmation or DPA
certificate separately. Rotate temporary HF/Vast/NGC credentials and remove the
dedicated SSH public key.

## Research-only boundary

### Aggregate chromosome mosaic screen

`mosaic_aneuploidy_scan.py` is a standard-library-only analyzer for an
authorized secure environment. It accepts aggregate 1-Mb depth, a single-sample
indexed VCF queried in place through bcftools, an FAI, and aggregate 100-kb
GC-corrected/strict-mask CNVpytor ratios. It writes deterministic chromosome and
10-Mb block summaries plus method/runtime metadata. The companion
`remote/run_mosaic_aneuploidy_scan.sh` requires a pinned CNVpytor 1.3.2 Python
path and opens the existing `.pytor` file strictly read-only. It generates
aggregate inputs within its secure output directory, applies the fixed
MAPQ/flag/coverage rules, and hashes declared inputs and outputs without storing
private paths or basenames in either checksum manifest.

After privacy review, the only files that may be copied from the secure output
directory are this explicit allow-list:

- `chromosome_summary.tsv`
- `methods.json`
- `runtime.json`
- `inputs.sha256`
- `CHECKSUMS.sha256`

`block_summary.tsv`, autosomal window files, raw bedcov output, aggregate depth
inputs, and CNVpytor-bin inputs remain inside the secure environment. VCF
records and other per-site material are never exported by this workflow.

The BAF decision statistic is empirical Q90 absolute deviation from 0.5. This is
intentional: selecting sites from heterozygous variant calls conditions the BAF
distribution, so a binomial-noise-corrected variance can be underdispersed and
clip to zero. No balance filter is applied. This screen is non-diagnostic; bulk
blood WGS can miss low-fraction, balanced, or tissue-specific mosaicism and
cannot resolve phase.

Outputs are hypothesis-generation material for this hackathon. They are not a
diagnosis, medical device output, treatment recommendation, or substitute for a
clinical geneticist, laboratory confirmation, segregation testing, cytogenetics,
or genetic counseling. Do not contact the child/family, alter care, or publicly
release individual-level findings. Any potentially explanatory result must be
reported with evidence, uncertainty, assay blind spots, and required clinical
validation.

## Official sources

- [Organizer public processor clarification](https://huggingface.co/spaces/SageBio/rare-disease-real-kid-mva-hackathon-2026/discussions/2)
- [Hugging Face authentication and cached tokens](https://huggingface.co/docs/huggingface_hub/en/package_reference/authentication)
- [Hugging Face repository metadata API](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api)
- [Vast Secure Cloud and offer selection](https://docs.vast.ai/guides/instances/choosing/find-and-rent)
- [Vast security FAQ](https://docs.vast.ai/guides/reference/faq/security)
- [Vast instance-management security/deletion caveats](https://docs.vast.ai/guides/instances/manage-instances)
- [Vast storage types](https://docs.vast.ai/guides/instances/storage/types)
- [Vast CLI offer fields](https://docs.vast.ai/cli/reference/search-instances)
- [Vast CLI instance creation](https://docs.vast.ai/cli/reference/create-instance)
- [Vast CLI volume deletion](https://docs.vast.ai/cli/reference/delete-volume)
- [Vast Data Processing Agreement](https://vast.ai/data-processing-agreement)
- [Vast compliance](https://vast.ai/compliance)
- [NVIDIA Parabricks 4.7.1-1 release notes](https://docs.nvidia.com/clara/parabricks/about-parabricks/release-notes/4-7-1-1-release-notes)
- [NVIDIA Parabricks WGS tutorial](https://docs.nvidia.com/clara/parabricks/tutorials/detailed-tutorials/wgs-variant-calling)
- [NVIDIA `fq2bam` reference](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/fq2bam)
- [NVIDIA DeepVariant reference](https://docs.nvidia.com/clara/parabricks/tool-reference/tools/deepvariant)
- [DeepVariant primary publication](https://www.nature.com/articles/nbt.4235)
- [NVIDIA public sample data](https://docs.nvidia.com/clara/parabricks/tutorials/step-by-step-tutorials/getting-the-sample-data)
- [NCBI GRCh38 alignment resources](https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/)
- [Manta 1.6 release](https://github.com/Illumina/manta/releases/tag/v1.6.0)
- [DELLY 2.3 release](https://github.com/dellytools/delly/releases/tag/v2.3.0)
- [CNVpytor 1.3.2 release](https://github.com/abyzovlab/CNVpytor/releases/tag/1.3.2)
- [CNVpytor primary publication](https://academic.oup.com/gigascience/article/10/11/giab074/6431225)
- [xTea short-read workflow](https://github.com/parklab/xTea)
- [xTea primary publication](https://www.nature.com/articles/s41467-021-24041-8)
- [ExpansionHunter 5.0.0 release](https://github.com/Illumina/ExpansionHunter/releases/tag/v5.0.0)
- [ExpansionHunter primary publication](https://genome.cshlp.org/content/27/11/1895)
- [GATK mitochondrial short-variant Best Practices](https://gatk.broadinstitute.org/hc/en-us/articles/4403870837275-Mitochondrial-short-variant-discovery-SNVs-Indels)
- [Exomiser 15.1 analysis configuration](https://exomiser.readthedocs.io/en/stable/advanced_analysis.html)
- [Exomiser structural-variant prioritization](https://exomiser.readthedocs.io/en/stable/sv_prioritisation.html)
- [ReMM 0.4](https://remm.bihealth.org/)
- [LIRICAL 2.4.1 running guide](https://thejacksonlaboratory.github.io/LIRICAL/stable/running.html)
- [WhatsHap phasing guide](https://whatshap.readthedocs.io/en/latest/guide.html)
- [Official Track 1 instructions and scoring](https://sagebio-rare-disease-real-kid-mva-hackathon-2026.hf.space/)
