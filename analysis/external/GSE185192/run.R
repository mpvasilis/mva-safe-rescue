args <- commandArgs(trailingOnly = TRUE)
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1L]]) else
  "analysis/external/GSE185192/run.R"
project_dir <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
repo_root <- normalizePath(file.path(project_dir, "../../.."), winslash = "/", mustWork = TRUE)
local_library <- file.path(project_dir, ".Rlib")
if (dir.exists(local_library)) .libPaths(c(local_library, file.path(repo_root, "analysis/track2/.Rlib"), .libPaths()))
options(mc.cores = 1L, Ncpus = 1L)
Sys.setenv(OMP_NUM_THREADS = "1", OPENBLAS_NUM_THREADS = "1", MKL_NUM_THREADS = "1")
set.seed(20260826L)

usage <- function() {
  cat(paste0(
    "Usage: Rscript analysis/external/GSE185192/run.R [mode]\n",
    "  no mode          Verify inputs, run four separate DE/module analyses, refresh release\n",
    "  --download-only  Selectively download/verify 27 pinned public inputs and sample eligibility\n",
    "  --test           Run offline unit/configuration tests\n",
    "  --verify-release Verify every tracked release byte and rectangular TSV\n"
  ))
}
if (any(args %in% c("--help", "-h"))) { usage(); quit(status = 0L) }
known <- c("--download-only", "--test", "--verify-release")
unknown <- setdiff(args, known)
if (length(unknown)) stop("Unknown arguments: ", paste(unknown, collapse = ", "), call. = FALSE)
if (length(args) > 1L) stop("Choose exactly one mode", call. = FALSE)

r_files <- list.files(file.path(project_dir, "R"), pattern = "\\.R$", full.names = TRUE)
invisible(lapply(r_files, source, local = globalenv()))
required_base <- c("digest", "fs", "jsonlite")
missing_base <- required_base[!vapply(required_base, requireNamespace, logical(1L), quietly = TRUE)]
if (length(missing_base)) stop("Missing packages: ", paste(missing_base, collapse = ", "),
                               ". Run bootstrap.R.", call. = FALSE)

cache_setting <- Sys.getenv("GSE185192_CACHE_DIR", unset = "")
cache_dir <- if (nzchar(cache_setting)) {
  if (grepl("^([A-Za-z]:|/|\\\\)", cache_setting)) cache_setting else file.path(repo_root, cache_setting)
} else file.path(repo_root, "public_data", "GSE185192")
cache_dir <- normalizePath(cache_dir, winslash = "/", mustWork = FALSE)

sources <- gse_read_tsv(file.path(project_dir, "config", "sources.tsv"))
samples <- gse_read_tsv(file.path(project_dir, "config", "samples.tsv"))
modules <- gse_read_tsv(file.path(project_dir, "config", "modules.tsv"))
source_usage <- gse_read_tsv(file.path(project_dir, "config", "source_usage_notes.tsv"))
sources$usage_note <- source_usage$usage_note[match(sources$kind, source_usage$kind)]
gse_validate_configs(samples, modules, sources)

if (identical(args, "--test")) {
  source(file.path(project_dir, "tests", "run_tests.R"), local = globalenv())
  gse_run_tests(project_dir)
  quit(status = 0L)
}
if (identical(args, "--verify-release")) {
  gse_assert(gse_verify_release(file.path(project_dir, "release")), "Release verification failed")
  cat("Release verification passed.\n")
  quit(status = 0L)
}
if (identical(args, "--download-only")) {
  verification <- gse_download_sources(sources, cache_dir)
  eligibility <- gse_validate_sample_eligibility(samples, cache_dir)
  cat(sprintf("Verified %d pinned public inputs and %d eligible untreated samples.\n",
              nrow(verification), sum(eligibility$eligible)))
  quit(status = 0L)
}

required_analysis <- c("jsonlite", "ggplot2", "DESeq2", "roastgsa")
missing_analysis <- required_analysis[!vapply(required_analysis, requireNamespace,
                                               logical(1L), quietly = TRUE)]
if (length(missing_analysis)) stop("Missing analysis packages: ",
                                   paste(missing_analysis, collapse = ", "),
                                   ". Run bootstrap.R.", call. = FALSE)
source_verification <- gse_verify_sources(sources, cache_dir)
eligibility <- gse_validate_sample_eligibility(samples, cache_dir)
imported <- gse_import_counts(samples, cache_dir)
annotations <- gse_prepare_annotations(cache_dir, modules)

# Priority NPC analyses run first. Each sensitivity rebuilds filtering and the full model.
analyses <- list(
  gse_run_analysis(imported$counts, samples, annotations$chromosomes,
                   annotations$modules$sets, "NPC", "full"),
  gse_run_analysis(imported$counts, samples, annotations$chromosomes,
                   annotations$modules$sets, "NPC", "chr21_excluded"),
  gse_run_analysis(imported$counts, samples, annotations$chromosomes,
                   annotations$modules$sets, "iPSC", "full"),
  gse_run_analysis(imported$counts, samples, annotations$chromosomes,
                   annotations$modules$sets, "iPSC", "chr21_excluded")
)
output <- gse_write_outputs(project_dir, repo_root, sources, samples, modules,
                            source_verification, eligibility, imported, annotations, analyses)
print(output$summaries, row.names = FALSE)
cat("External challenge complete. Results are descriptive within one isogenic derivative pair.\n")
cat("The primary fly 0/12 module null remains unchanged.\n")
