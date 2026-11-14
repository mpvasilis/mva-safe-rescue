#!/usr/bin/env bash
# Research-only, fail-closed short-read WGS germline small-variant workflow.
set -Eeuo pipefail
umask 077
export LC_ALL=C
export TZ=UTC
export TCMALLOC_MAX_TOTAL_THREAD_CACHE_BYTES=268435456

EXPECTED_PARABRICKS_VERSION="4.7.1-1"
# This deliberately fails its regex until the reviewed NGC manifest digest is
# patched into the public runner as a second, independent provisioning control.
APPROVED_PARABRICKS_IMAGE_DIGEST="sha256:REPLACE_WITH_VERIFIED_64_HEX"
REFERENCE_ACCESSION="GCA_000001405.15"
REFERENCE_BASENAME="GCA_000001405.15_GRCh38_no_alt_analysis_set.fna"
REFERENCE_URL="https://ftp.ncbi.nlm.nih.gov/genomes/all/GCA/000/001/405/GCA_000001405.15_GRCh38/seqs_for_alignment_pipelines.ucsc_ids/${REFERENCE_BASENAME}.gz"
REFERENCE_ARCHIVE_MD5="a08035b6a6e31780e96a34008ff21bd6"
RUN_ROOT="${RUN_ROOT:-/workspace/mva-secure-wgs-run}"
INPUT_DIR="${RUN_ROOT}/input"
CONTROL_DIR="${RUN_ROOT}/control"
REFERENCE_DIR="${RUN_ROOT}/reference"
OUTPUT_DIR="${RUN_ROOT}/output"
LOG_DIR="${RUN_ROOT}/logs"
TMP_DIR="${RUN_ROOT}/tmp"
SAMPLE_ID="SAMPLE01"

fail() {
  trap - ERR
  if [[ "${RUN_ROOT:-}" =~ ^/workspace/mva-secure-wgs-[A-Za-z0-9._-]+$ ]] &&
     [[ -d "${CONTROL_DIR:-}" && ! -L "${CONTROL_DIR:-}" ]]; then
    printf '%s\n' 'FAILED_CLOSED' >"${CONTROL_DIR}/run_status" 2>/dev/null || true
  fi
  printf '%s\n' 'secure_wgs_run=failed_closed' >&2
  exit 2
}
trap fail ERR

[[ "${RUN_ROOT}" =~ ^/workspace/mva-secure-wgs-[A-Za-z0-9._-]+$ ]] || fail
[[ -d /workspace && ! -L /workspace ]] || fail
[[ ! -e "${RUN_ROOT}" || ! -L "${RUN_ROOT}" ]] || fail
for path in "${INPUT_DIR}" "${CONTROL_DIR}" "${REFERENCE_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}" "${TMP_DIR}"; do
  [[ ! -e "${path}" || ! -L "${path}" ]] || fail
done
[[ "${SECURE_CLOUD_APPROVED:-}" == YES ]] || fail
[[ "${PROCESSOR_TERMS_APPROVED:-}" == YES ]] || fail
[[ "${CONTROLLED_TRANSFER_APPROVED:-}" == YES ]] || fail
[[ "${REFERENCE_BUILD_APPROVED:-}" == YES ]] || fail
[[ "${RUN_MODE_APPROVED:-}" == RESEARCH_ONLY ]] || fail
[[ "${APPROVED_PARABRICKS_IMAGE_DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail
[[ "${PARABRICKS_IMAGE_DIGEST:-}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail
[[ "${PARABRICKS_IMAGE_DIGEST}" == "${APPROVED_PARABRICKS_IMAGE_DIGEST}" ]] || fail

for tool in pbrun nvidia-smi samtools bcftools bwa curl gzip md5sum sha256sum python3; do
  command -v "${tool}" >/dev/null 2>&1 || fail
done

version_text="$(pbrun --version 2>&1 || true)"
[[ "${version_text}" == *"${EXPECTED_PARABRICKS_VERSION}"* ]] || fail

gpu_memory_min="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk 'NR==1{m=$1} $1<m{m=$1} END{print int(m)}')"
[[ "${gpu_memory_min}" -ge 38000 ]] || fail
[[ "$(nproc)" -ge 24 ]] || fail
memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
[[ "${memory_kib}" -ge 96000000 ]] || fail
free_kib="$(df -Pk /workspace | awk 'NR==2 {print $4}')"
[[ "${free_kib}" -ge 536870912 ]] || fail

mkdir -p "${INPUT_DIR}" "${CONTROL_DIR}" "${REFERENCE_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}" "${TMP_DIR}"
[[ -z "$(find "${OUTPUT_DIR}" -mindepth 1 -print -quit)" ]] || fail
[[ -z "$(find "${LOG_DIR}" -mindepth 1 -print -quit)" ]] || fail
[[ -z "$(find "${RUN_ROOT}" -type l -print -quit)" ]] || fail

provider_gate="${CONTROL_DIR}/provider_gate.json"
input_manifest="${CONTROL_DIR}/input_manifest.json"
[[ -s "${provider_gate}" && -s "${input_manifest}" ]] || fail

python3 - "${provider_gate}" "${EXPECTED_PARABRICKS_VERSION}" "${REFERENCE_ACCESSION}" "${REFERENCE_ARCHIVE_MD5}" "${PARABRICKS_IMAGE_DIGEST}" <<'PY' || fail
import datetime
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    gate = json.load(handle)
required_true = (
    "secure_cloud",
    "datacenter_offer",
    "processor_only",
    "no_training_or_own_use",
    "limited_operational_retention",
    "deletion_certification_available",
    "approved_for_genetic_health_data",
)
assert gate.get("schema") == "secure-wgs-provider-gate/v1"
assert all(gate.get(key) is True for key in required_true)
assert gate.get("parabricks_version") == sys.argv[2]
assert gate.get("reference_accession") == sys.argv[3]
assert gate.get("reference_archive_md5") == sys.argv[4]
assert re.fullmatch(r"sha256:[0-9a-f]{64}", gate.get("parabricks_image_digest", ""))
assert gate.get("parabricks_image_digest") == sys.argv[5]
for key in ("reviewer", "vast_plan_tier"):
    value = gate.get(key)
    assert isinstance(value, str) and value.strip()
    assert not re.search(r"REQUIRED|REPLACE|TODO", value, re.IGNORECASE)
for key in ("vast_offer_id", "vast_machine_id"):
    value = str(gate.get(key, ""))
    assert value.isdigit() and int(value) > 0
approval_date = datetime.date.fromisoformat(gate.get("approval_date", ""))
assert approval_date <= datetime.date.today()
PY

python3 - "${input_manifest}" "${INPUT_DIR}" <<'PY' || fail
import gzip
import hashlib
import json
import pathlib
import re
import sys

manifest_path = pathlib.Path(sys.argv[1]).resolve(strict=True)
input_dir = pathlib.Path(sys.argv[2]).resolve(strict=True)
with manifest_path.open(encoding="utf-8") as handle:
    manifest = json.load(handle)
assert manifest.get("schema") == "secure-wgs-input-manifest/v1"
assert manifest.get("sample_id") == "SAMPLE01"
assert manifest.get("ready_for_transfer") is True
expected = []
for pair in manifest.get("pairs", []):
    assert re.fullmatch(r"L[0-9]{3}", pair.get("lane_id", ""))
    entries = sorted(pair.get("files", []), key=lambda item: item.get("read"))
    assert [entry.get("read") for entry in entries] == [1, 2]
    for entry in entries:
        name = entry.get("staged_name", "")
        assert re.fullmatch(r"SAMPLE01_L[0-9]{3}_R[12]\.fastq\.gz", name)
        path = (input_dir / name).resolve(strict=True)
        assert path.parent == input_dir and not path.is_symlink()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
        assert digest.hexdigest() == entry.get("sha256")
        assert path.stat().st_size == entry.get("size_bytes")
        with gzip.open(path, "rb") as stream:
            for _ in range(4):
                assert stream.readline()
        expected.append(name)
observed = sorted(path.name for path in input_dir.glob("*.fastq.gz"))
assert observed == sorted(expected) and observed
PY

reference_archive="${REFERENCE_DIR}/${REFERENCE_BASENAME}.gz"
reference_fasta="${REFERENCE_DIR}/${REFERENCE_BASENAME}"
if [[ ! -s "${reference_archive}" ]]; then
  curl --fail --location --silent --show-error "${REFERENCE_URL}" --output "${reference_archive}.part"
  mv "${reference_archive}.part" "${reference_archive}"
fi
printf '%s  %s\n' "${REFERENCE_ARCHIVE_MD5}" "${reference_archive}" | md5sum --check --status || fail
if [[ ! -s "${reference_fasta}" ]]; then
  gzip -dc "${reference_archive}" >"${reference_fasta}.part"
  mv "${reference_fasta}.part" "${reference_fasta}"
fi
gzip -dc "${reference_archive}" | cmp -s - "${reference_fasta}" || fail

[[ -s "${reference_fasta}.fai" ]] || samtools faidx "${reference_fasta}" >"${LOG_DIR}/00_reference_faidx.log" 2>&1
if [[ ! -s "${reference_fasta}.bwt" ]]; then
  bwa index "${reference_fasta}" >"${LOG_DIR}/00_reference_bwa.log" 2>&1
fi
for suffix in amb ann bwt pac sa; do
  [[ -s "${reference_fasta}.${suffix}" ]] || fail
done

fq_args=()
mapfile -t read1_files < <(find "${INPUT_DIR}" -maxdepth 1 -type f -name 'SAMPLE01_L???_R1.fastq.gz' | LC_ALL=C sort)
[[ "${#read1_files[@]}" -gt 0 ]] || fail
for read1 in "${read1_files[@]}"; do
  lane="$(basename "${read1}" | sed -E 's/^SAMPLE01_(L[0-9]{3})_R1\.fastq\.gz$/\1/')"
  [[ "${lane}" =~ ^L[0-9]{3}$ ]] || fail
  read2="${INPUT_DIR}/${SAMPLE_ID}_${lane}_R2.fastq.gz"
  [[ -s "${read2}" ]] || fail
  read_group="@RG\\tID:${SAMPLE_ID}.${lane}\\tLB:LIB01\\tPL:ILLUMINA\\tSM:${SAMPLE_ID}\\tPU:${SAMPLE_ID}.${lane}"
  fq_args+=(--in-fq "${read1}" "${read2}" "${read_group}")
done

bam="${OUTPUT_DIR}/${SAMPLE_ID}.markdup.bam"
duplicate_metrics="${OUTPUT_DIR}/${SAMPLE_ID}.duplicate_metrics.txt"
qc_dir="${OUTPUT_DIR}/fq2bam_qc"
wgs_metrics="${OUTPUT_DIR}/${SAMPLE_ID}.wgs_metrics.txt"
vcf="${OUTPUT_DIR}/${SAMPLE_ID}.deepvariant.vcf.gz"
gvcf="${OUTPUT_DIR}/${SAMPLE_ID}.deepvariant.g.vcf.gz"

printf '%s\n' 'RUNNING_FQ2BAM' >"${CONTROL_DIR}/run_status"
pbrun fq2bam \
  --ref "${reference_fasta}" \
  "${fq_args[@]}" \
  --out-bam "${bam}" \
  --out-duplicate-metrics "${duplicate_metrics}" \
  --out-qc-metrics-dir "${qc_dir}" \
  --bwa-options='-K 10000000' \
  --monitor-usage \
  --gpusort \
  --gpuwrite \
  >"${LOG_DIR}/01_fq2bam.log" 2>&1

samtools quickcheck "${bam}" >/dev/null 2>&1 || fail
samtools index -f -@ "$(nproc)" "${bam}" >"${LOG_DIR}/02_bam_index.log" 2>&1
samtools flagstat -@ "$(nproc)" "${bam}" >"${OUTPUT_DIR}/${SAMPLE_ID}.flagstat.txt" 2>"${LOG_DIR}/03_flagstat.log"
samtools stats -@ "$(nproc)" "${bam}" >"${OUTPUT_DIR}/${SAMPLE_ID}.samtools_stats.txt" 2>"${LOG_DIR}/04_samtools_stats.log"
pbrun bammetrics \
  --ref "${reference_fasta}" \
  --bam "${bam}" \
  --out-metrics-file "${wgs_metrics}" \
  >"${LOG_DIR}/05_bammetrics.log" 2>&1

printf '%s\n' 'RUNNING_DEEPVARIANT' >"${CONTROL_DIR}/run_status"
pbrun deepvariant \
  --mode shortread \
  --ref "${reference_fasta}" \
  --in-bam "${bam}" \
  --out-variants "${gvcf}" \
  --gvcf \
  >"${LOG_DIR}/06_deepvariant.log" 2>&1

bcftools view --header-only "${vcf}" >/dev/null 2>&1 || fail
bcftools view --header-only "${gvcf}" >/dev/null 2>&1 || fail
bcftools index --force --tbi "${vcf}" >"${LOG_DIR}/07_vcf_index.log" 2>&1
bcftools index --force --tbi "${gvcf}" >"${LOG_DIR}/07_gvcf_index.log" 2>&1
bcftools stats "${vcf}" >"${OUTPUT_DIR}/${SAMPLE_ID}.deepvariant.bcftools_stats.txt" 2>"${LOG_DIR}/08_vcf_stats.log"

find "${OUTPUT_DIR}" -maxdepth 2 -type f -print0 \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum >"${CONTROL_DIR}/output_checksums.sha256"
sha256sum "${reference_archive}" "${reference_fasta}" >"${CONTROL_DIR}/reference_checksums.sha256"
printf '%s\n' 'HUMAN_QC_AND_GENETICS_REVIEW_REQUIRED' >"${CONTROL_DIR}/HUMAN_REVIEW_REQUIRED"
printf '%s\n' 'COMPLETE_RESEARCH_OUTPUTS_NOT_RELEASE_APPROVED' >"${CONTROL_DIR}/run_status"
printf '%s\n' 'secure_wgs_run=complete_human_review_required'
