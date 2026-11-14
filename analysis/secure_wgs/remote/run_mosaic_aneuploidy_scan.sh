#!/usr/bin/env bash
# Research-only aggregate mosaic-aneuploidy screen. Raw and per-site data stay
# inside the operator-declared secure output directory.
set -Eeuo pipefail
umask 077
export LC_ALL=C
export TZ=UTC
run_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() {
  trap - ERR
  printf '%s\n' 'mosaic_aneuploidy_runner=failed_closed' >&2
  exit 2
}
trap fail ERR

usage() {
  printf '%s\n' 'usage: run_mosaic_aneuploidy_scan.sh --bam BAM --bai BAI --vcf VCF.GZ --tbi VCF.GZ.TBI --reference FASTA --fai FASTA.FAI --cnvpytor-pyt FILE.PYTOR --cnvpytor-pythonpath DIR --output-dir DIR [--sample-label LABEL] [--analyzer FILE]' >&2
  exit 2
}

bam=''
bai=''
vcf=''
tbi=''
reference=''
fai=''
cnvpytor_pyt=''
cnvpytor_pythonpath=''
output_dir=''
sample_label='case'
analyzer=''
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --bam) bam="${2:-}"; shift 2 ;;
    --bai) bai="${2:-}"; shift 2 ;;
    --vcf) vcf="${2:-}"; shift 2 ;;
    --tbi) tbi="${2:-}"; shift 2 ;;
    --reference) reference="${2:-}"; shift 2 ;;
    --fai) fai="${2:-}"; shift 2 ;;
    --cnvpytor-pyt) cnvpytor_pyt="${2:-}"; shift 2 ;;
    --cnvpytor-pythonpath) cnvpytor_pythonpath="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --sample-label) sample_label="${2:-}"; shift 2 ;;
    --analyzer) analyzer="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "${bam}" && -n "${bai}" && -n "${vcf}" && -n "${tbi}" ]] || usage
[[ -n "${reference}" && -n "${fai}" && -n "${cnvpytor_pyt}" && -n "${cnvpytor_pythonpath}" && -n "${output_dir}" ]] || usage
[[ "${sample_label}" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || fail
for tool in samtools bcftools python3 sha256sum awk sort date; do
  command -v "${tool}" >/dev/null 2>&1 || fail
done

if [[ -z "${analyzer}" ]]; then
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  analyzer="${script_dir}/../mosaic_aneuploidy_scan.py"
fi
runner_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"

[[ -d "${cnvpytor_pythonpath}" && ! -L "${cnvpytor_pythonpath}" ]] || fail
cnvpytor_pythonpath="$(cd -- "${cnvpytor_pythonpath}" && pwd -P)"
python3 - "${cnvpytor_pythonpath}" <<'PY' || fail
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
mode = path.stat().st_mode
assert path.is_absolute() and path.is_dir() and not path.is_symlink()
assert not mode & (stat.S_IWGRP | stat.S_IWOTH)
assert path.stat().st_uid in {0, os.geteuid()}
PY

samtools_version="$(samtools --version | awk 'NR==1{print;exit}')"
bcftools_version="$(bcftools --version | awk 'NR==1{print;exit}')"
python_version="$(python3 --version 2>&1)"
[[ "${samtools_version}" == 'samtools 1.13' ]] || fail
[[ "${bcftools_version}" == 'bcftools 1.13' ]] || fail
cnvpytor_version="$(PYTHONPATH="${cnvpytor_pythonpath}" python3 - "${cnvpytor_pythonpath}" <<'PY'
import importlib.metadata
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
import cnvpytor
origin = pathlib.Path(cnvpytor.__file__).resolve()
assert os.path.commonpath([str(root), str(origin)]) == str(root)
version = importlib.metadata.version("CNVpytor")
assert version == "1.3.2"
print(version)
PY
)"
[[ "${cnvpytor_version}" == '1.3.2' ]] || fail

for path in "${bam}" "${bai}" "${vcf}" "${tbi}" "${reference}" "${fai}" "${cnvpytor_pyt}" "${analyzer}"; do
  [[ -f "${path}" && -s "${path}" && ! -L "${path}" ]] || fail
done
[[ "${bai}" == "${bam}.bai" || "${bai}" == "${bam%.bam}.bai" ]] || fail
[[ "${tbi}" == "${vcf}.tbi" ]] || fail
[[ "${fai}" == "${reference}.fai" ]] || fail
samtools quickcheck "${bam}" >/dev/null 2>&1 || fail
samtools idxstats "${bam}" >/dev/null 2>&1 || fail
bcftools view --header-only "${vcf}" >/dev/null 2>&1 || fail
bcftools index --stats "${vcf}" >/dev/null 2>&1 || fail
samtools faidx "${reference}" chr1:1-1 >/dev/null 2>&1 || samtools faidx "${reference}" 1:1-1 >/dev/null 2>&1 || fail

[[ ! -e "${output_dir}" || ( -d "${output_dir}" && ! -L "${output_dir}" ) ]] || fail
mkdir -p "${output_dir}"
output_dir="$(cd -- "${output_dir}" && pwd -P)"
[[ -z "$(find "${output_dir}" -mindepth 1 -print -quit)" ]] || fail

# Record digests with logical roles only. No input basename or path is copied
# into the manifest.
sha256_of() { sha256sum "$1" | awk '{print $1}'; }
analyzer_sha256="$(sha256_of "${analyzer}")"
runner_sha256="$(sha256_of "${runner_path}")"
cnvpytor_before_sha256="$(sha256_of "${cnvpytor_pyt}")"
{
  printf '%s  %s\n' "$(sha256_of "${bam}")" bam
  printf '%s  %s\n' "$(sha256_of "${bai}")" bam_index
  printf '%s  %s\n' "$(sha256_of "${vcf}")" baf_vcf
  printf '%s  %s\n' "$(sha256_of "${tbi}")" baf_vcf_index
  printf '%s  %s\n' "$(sha256_of "${reference}")" reference_fasta
  printf '%s  %s\n' "$(sha256_of "${fai}")" reference_fai
  printf '%s  %s\n' "${cnvpytor_before_sha256}" cnvpytor_pyt
  printf '%s  %s\n' "${analyzer_sha256}" analyzer
  printf '%s  %s\n' "${runner_sha256}" runner
} >"${output_dir}/inputs.sha256"

windows_bed="${output_dir}/autosomal_1mb_windows.bed"
depth_raw="${output_dir}/depth_bedcov.private.tsv"
depth_tsv="${output_dir}/depth_1mb.private.tsv"
cnvpytor_tsv="${output_dir}/cnvpytor_rd_100kb.private.tsv"
cnvpytor_normalization_json="${output_dir}/cnvpytor_normalization.private.json"

# Only canonical autosomes are generated. A terminal bin shorter than 500 kb is
# deliberately omitted; full and >=half-size terminal bins are retained.
awk -F '\t' 'BEGIN{OFS="\t"}
  $1 ~ /^(chr)?([1-9]|1[0-9]|2[0-2])$/ {
    for (s=0; s<$2; s+=1000000) {
      e=s+1000000; if (e>$2) e=$2;
      if (e-s>=500000) print $1,s,e
    }
  }' "${fai}" >"${windows_bed}"
[[ "$(wc -l <"${windows_bed}")" -gt 0 ]] || fail

# -d 10 emits the number of bases at >=10x. -Q 20 and -G 3844 exclude
# unmapped, secondary, QC-fail, duplicate, and supplementary alignments.
samtools bedcov -Q 20 -G 3844 -d 10 "${windows_bed}" "${bam}" >"${depth_raw}"
printf '%s\n' $'chrom\tstart\tend\tdepth_sum\tcallable_bases_ge10' >"${depth_tsv}"
awk -F '\t' 'BEGIN{OFS="\t"} NF==5 {print $1,$2,$3,$4,$5} NF!=5 {exit 2}' "${depth_raw}" >>"${depth_tsv}"

# Read only pre-existing 100-kb GC-corrected, strict-mask signals. IO(ro=True)
# is the only CNVpytor file handle; no Root object or signal creation is allowed.
PYTHONPATH="${cnvpytor_pythonpath}" python3 - "${cnvpytor_pyt}" "${cnvpytor_tsv}" "${fai}" "${cnvpytor_normalization_json}" <<'PY'
import json
import math
import sys

from cnvpytor.io import FLAG_GC_CORR, FLAG_USEMASK, IO

pytor_path, output_path, fai_path, normalization_path = sys.argv[1:]
lengths = {}
with open(fai_path, encoding="utf-8") as handle:
    for line in handle:
        name, length, *_ = line.rstrip("\n").split("\t")
        text = name[3:] if name.lower().startswith("chr") else name
        if text.isdigit() and 1 <= int(text) <= 22 and str(int(text)) == text:
            assert int(text) not in lengths
            lengths[int(text)] = int(length)
assert set(lengths) == set(range(1, 23))

io = IO(pytor_path, ro=True)
chroms = []
for name in io.rd_chromosomes():
    text = name[3:] if name.lower().startswith("chr") else name
    if text.isdigit() and 1 <= int(text) <= 22 and str(int(text)) == text:
        chroms.append((int(text), name))
assert len(chroms) == 22 and len({number for number, _ in chroms}) == 22
signal_flags = FLAG_GC_CORR | FLAG_USEMASK
normal_gc_raw = io.rd_normal_level(100000, FLAG_GC_CORR)
assert normal_gc_raw is not None and len(normal_gc_raw) >= 2
normal_gc = float(normal_gc_raw[0])
spread_gc = float(normal_gc_raw[1])
assert math.isfinite(normal_gc) and normal_gc > 0
assert math.isfinite(spread_gc) and spread_gc >= 0
normal_combined_raw = io.rd_normal_level(100000, signal_flags)
normal_combined = None
spread_combined = None
combined_match_status = "zero_or_missing_allowed"
if normal_combined_raw is not None and len(normal_combined_raw) > 0:
    normal_combined = float(normal_combined_raw[0])
    assert math.isfinite(normal_combined) and normal_combined >= 0
    if len(normal_combined_raw) > 1:
        spread_combined = float(normal_combined_raw[1])
        assert math.isfinite(spread_combined) and spread_combined >= 0
    if normal_combined > 0:
        assert spread_combined is not None
        assert math.isclose(normal_combined, normal_gc, rel_tol=1e-9, abs_tol=1e-6)
        assert math.isclose(spread_combined, spread_gc, rel_tol=1e-9, abs_tol=1e-6)
        combined_match_status = "matched"
with open(normalization_path, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(
        {
            "combined_match_status": combined_match_status,
            "combined_normal_level": normal_combined,
            "combined_normal_spread": spread_combined,
            "gc_normal_level": normal_gc,
            "gc_normal_spread": spread_gc,
            "normalization_flag": "FLAG_GC_CORR",
            "signal_flags": "FLAG_GC_CORR|FLAG_USEMASK",
        },
        handle,
        indent=2,
        sort_keys=True,
    )
    handle.write("\n")
signals = {}
for number, name in chroms:
    signal = io.get_signal(name, 100000, "RD", signal_flags)
    values = [float(value) for value in signal]
    assert values
    signals[number] = values
with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
    handle.write("chrom\tstart\tend\tratio\n")
    for number in sorted(signals):
        for index, value in enumerate(signals[number]):
            start = index * 100000
            if start >= lengths[number]:
                continue
            if math.isfinite(value) and value > 0:
                end = min(start + 100000, lengths[number])
                handle.write(f"chr{number}\t{start}\t{end}\t{value/normal_gc:.10f}\n")
PY
[[ -s "${cnvpytor_tsv}" && -s "${cnvpytor_normalization_json}" ]] || fail
[[ "$(sha256_of "${cnvpytor_pyt}")" == "${cnvpytor_before_sha256}" ]] || fail

python3 "${analyzer}" \
  --depth-tsv "${depth_tsv}" \
  --baf-vcf "${vcf}" \
  --fai "${fai}" \
  --cnvpytor-rd-tsv "${cnvpytor_tsv}" \
  --output-dir "${output_dir}" \
  --sample-label "${sample_label}" \
  --bcftools bcftools \
  --seed 20260829

run_ended_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 - "${output_dir}/runtime.json" "${run_started_utc}" "${run_ended_utc}" \
  "${samtools_version}" "${bcftools_version}" "${python_version}" "${cnvpytor_version}" \
  "${analyzer_sha256}" "${runner_sha256}" "${cnvpytor_normalization_json}" <<'PY'
import json
import os
import sys

(
    runtime_path,
    started,
    ended,
    samtools_version,
    bcftools_version,
    python_version,
    cnvpytor_version,
    analyzer_sha256,
    runner_sha256,
    normalization_path,
) = sys.argv[1:]
with open(runtime_path, encoding="utf-8") as handle:
    payload = json.load(handle)
with open(normalization_path, encoding="utf-8") as handle:
    cnvpytor_normalization = json.load(handle)
cnvpytor_normalization["post_read_sha256_matched"] = True
payload["timestamps_omitted_for_determinism"] = False
payload["runner"] = {
    "analyzer_core_deterministic": True,
    "analyzer_sha256": analyzer_sha256,
    "command_profile": {
        "analyzer": "two-pass single-sample VCF stream; chromosome and 10-Mb aggregates",
        "cnvpytor": "IO(ro=True); existing 100-kb FLAG_GC_CORR|FLAG_USEMASK RD normalized by FLAG_GC_CORR rd_normal_level",
        "depth": "canonical-autosome 1-Mb windows; bedcov MAPQ>=20 flags=3844 callable-depth>=10",
    },
    "ended_utc": ended,
    "cnvpytor_normalization": cnvpytor_normalization,
    "runner_sha256": runner_sha256,
    "started_utc": started,
    "threshold_profile": "prespecified-mosaic-aneuploidy-q90-v2",
    "versions": {
        "bcftools": bcftools_version,
        "cnvpytor": cnvpytor_version,
        "python": python_version,
        "samtools": samtools_version,
    },
}
temporary = runtime_path + ".tmp"
with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
    handle.write("\n")
os.replace(temporary, runtime_path)
PY

for expected in chromosome_summary.tsv block_summary.tsv methods.json runtime.json inputs.sha256; do
  [[ -s "${output_dir}/${expected}" && ! -L "${output_dir}/${expected}" ]] || fail
done
(cd -- "${output_dir}" && sha256sum chromosome_summary.tsv methods.json runtime.json inputs.sha256 >CHECKSUMS.sha256)
[[ -s "${output_dir}/CHECKSUMS.sha256" ]] || fail
printf '%s\n' 'mosaic_aneuploidy_runner=complete_research_only'
