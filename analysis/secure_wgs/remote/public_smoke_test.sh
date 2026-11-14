#!/usr/bin/env bash
# Public-data-only Parabricks preflight and optional NVIDIA sample smoke test.
set -Eeuo pipefail
umask 077
export LC_ALL=C
export TZ=UTC

EXPECTED_VERSION="4.7.1-1"
PUBLIC_BUNDLE_URL="https://s3.amazonaws.com/parabricks.sample/parabricks_sample.tar.gz"
SMOKE_ROOT="${SMOKE_ROOT:-/workspace/public-smoke-parabricks-4.7.1-1}"
MODE="${1:-preflight}"

fail() {
  trap - ERR
  printf '%s\n' 'public_smoke_status=failed_closed' >&2
  exit 2
}
trap fail ERR

[[ "${SMOKE_ROOT}" == /workspace/public-smoke-parabricks-4.7.1-1 ]] || fail
[[ "${MODE}" == preflight || "${MODE}" == benchmark ]] || fail
command -v pbrun >/dev/null 2>&1 || fail
command -v nvidia-smi >/dev/null 2>&1 || fail
command -v samtools >/dev/null 2>&1 || fail
command -v bcftools >/dev/null 2>&1 || fail
command -v sha256sum >/dev/null 2>&1 || fail
command -v curl >/dev/null 2>&1 || fail
command -v gzip >/dev/null 2>&1 || fail
command -v tar >/dev/null 2>&1 || fail

version_text="$(pbrun --version 2>&1 || true)"
[[ "${version_text}" == *"${EXPECTED_VERSION}"* ]] || fail
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader >/dev/null 2>&1 || fail
pbrun fq2bam --help >/dev/null 2>&1 || fail
pbrun deepvariant --help >/dev/null 2>&1 || fail

if [[ "${MODE}" == preflight ]]; then
  printf '%s\n' 'public_smoke_status=preflight_ok'
  exit 0
fi

[[ "${PUBLIC_SMOKE_APPROVED:-}" == YES ]] || fail
[[ "${PUBLIC_BUNDLE_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || fail
[[ "${PUBLIC_BUNDLE_SHA256}" != 0000000000000000000000000000000000000000000000000000000000000000 ]] || fail

mkdir -p "${SMOKE_ROOT}/download" "${SMOKE_ROOT}/work" "${SMOKE_ROOT}/output" "${SMOKE_ROOT}/logs"
[[ -z "$(find "${SMOKE_ROOT}/output" -mindepth 1 -print -quit)" ]] || fail

bundle="${SMOKE_ROOT}/download/parabricks_sample.tar.gz"
curl --fail --location --silent --show-error "${PUBLIC_BUNDLE_URL}" --output "${bundle}"
printf '%s  %s\n' "${PUBLIC_BUNDLE_SHA256}" "${bundle}" | sha256sum --check --status || fail
tar -xzf "${bundle}" -C "${SMOKE_ROOT}/work"

reference="${SMOKE_ROOT}/work/parabricks_sample/Ref/Homo_sapiens_assembly38.fasta"
read1="${SMOKE_ROOT}/work/parabricks_sample/Data/sample_1.fq.gz"
read2="${SMOKE_ROOT}/work/parabricks_sample/Data/sample_2.fq.gz"
bam="${SMOKE_ROOT}/output/PUBLIC_SAMPLE.bam"
vcf="${SMOKE_ROOT}/output/PUBLIC_SAMPLE.deepvariant.vcf.gz"

[[ -s "${reference}" && -s "${read1}" && -s "${read2}" ]] || fail
gzip -t "${read1}" "${read2}" >/dev/null 2>&1 || fail

pbrun fq2bam \
  --ref "${reference}" \
  --in-fq "${read1}" "${read2}" '@RG\tID:PUBLIC.L001\tLB:PUBLIC\tPL:ILLUMINA\tSM:PUBLIC_SAMPLE\tPU:PUBLIC.L001' \
  --out-bam "${bam}" \
  --out-duplicate-metrics "${SMOKE_ROOT}/output/PUBLIC_SAMPLE.duplicate_metrics.txt" \
  --bwa-options='-K 10000000' \
  >"${SMOKE_ROOT}/logs/01_fq2bam.log" 2>&1

samtools quickcheck "${bam}" >/dev/null 2>&1 || fail
pbrun deepvariant \
  --mode shortread \
  --ref "${reference}" \
  --in-bam "${bam}" \
  --out-variants "${vcf}" \
  >"${SMOKE_ROOT}/logs/02_deepvariant.log" 2>&1

bcftools view --header-only "${vcf}" >/dev/null 2>&1 || fail
sha256sum "${bam}" "${vcf}" | LC_ALL=C sort >"${SMOKE_ROOT}/output/output_checksums.sha256"
printf '%s\n' 'public_smoke_status=benchmark_ok'
