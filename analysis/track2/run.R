args <- commandArgs(trailingOnly = TRUE)
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1L]]) else "analysis/track2/run.R"
track2_dir <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
repo_root <- normalizePath(file.path(track2_dir, "../.."), winslash = "/", mustWork = TRUE)
setwd(track2_dir)

local_library <- file.path(track2_dir, ".Rlib")
if (dir.exists(local_library)) .libPaths(c(local_library, .libPaths()))
options(mc.cores = 1L)
set.seed(20260826L)

usage <- function() {
  cat(paste0(
    "Usage: Rscript run.R [--dry-run | --validate-only] [--download]\n",
    "  --dry-run       Parse all R files, validate registries, and hash any present GEO workbooks.\n",
    "                  This mode does not install packages or download files.\n",
    "  --validate-only Validate all pinned public sources; use --download to fetch missing sources.\n",
    "  --download      Download/verify all public inputs before validation.\n",
    "  no mode         Run the one-CPU targets pipeline (which downloads missing public inputs).\n"
  ))
}

if ("--help" %in% args || "-h" %in% args) {
  usage()
  quit(status = 0L)
}
known <- c("--dry-run", "--validate-only", "--download")
unknown <- setdiff(args, known)
if (length(unknown)) stop("Unknown arguments: ", paste(unknown, collapse = ", "), call. = FALSE)
if (all(c("--dry-run", "--validate-only") %in% args)) {
  stop("Choose only one of --dry-run and --validate-only", call. = FALSE)
}
if (all(c("--dry-run", "--download") %in% args)) {
  stop("--dry-run never downloads; remove --download", call. = FALSE)
}

r_files <- list.files(file.path(track2_dir, "R"), pattern = "\\.R$", full.names = TRUE)
parse_files <- c(r_files, file.path(track2_dir, "_targets.R"),
                 file.path(track2_dir, "bootstrap.R"), file.path(track2_dir, "run.R"))
invisible(lapply(parse_files, function(path) parse(file = path, keep.source = FALSE)))
invisible(lapply(r_files, source, local = globalenv()))

source_manifest <- track2_read_tsv(file.path(track2_dir, "config", "source_manifest.tsv"))
sample_manifest <- track2_read_tsv(file.path(track2_dir, "config", "sample_manifest.tsv"))
contrasts <- track2_read_tsv(file.path(track2_dir, "config", "contrasts.tsv"))
primary_modules <- track2_read_tsv(file.path(track2_dir, "config", "primary_modules.tsv"))
track2_validate_configuration(source_manifest, sample_manifest, contrasts, primary_modules, repo_root)

required_packages <- c("targets", "testthat", "readxl", "digest", "jsonlite", "DESeq2",
                       "apeglm", "roastgsa", "ggplot2", "data.table")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace,
                                               logical(1L), quietly = TRUE)]

if ("--dry-run" %in% args) {
  geo <- source_manifest[source_manifest$source_id %in% c("GSE290206_counts", "GSE301548_counts"), , drop = FALSE]
  present <- file.exists(file.path(repo_root, geo$destination))
  if (any(present)) {
    checked <- lapply(which(present), function(i) {
      track2_verify_source(geo[i, , drop = FALSE], repo_root,
                           validate_structure = requireNamespace("readxl", quietly = TRUE))
    })
    cat(sprintf("Verified SHA-256 for %d present GEO workbook(s).\n", length(checked)))
  }
  absent <- source_manifest$source_id[!file.exists(file.path(repo_root, source_manifest$destination))]
  cat("Dry-run validation passed: R files parse, registries are consistent, designs are full rank.\n")
  if (length(missing_packages)) cat("Packages still needed for analysis:", paste(missing_packages, collapse = ", "), "\n")
  if (length(absent)) cat("Public sources still to download:", paste(absent, collapse = ", "), "\n")
  quit(status = 0L)
}

if ("--download" %in% args) {
  track2_download_and_verify_sources(source_manifest, repo_root,
                                     replace_invalid = FALSE, validate_structure = TRUE)
}

if ("--validate-only" %in% args) {
  track2_verify_existing_sources(source_manifest, repo_root,
                                 analysis_only = FALSE, validate_structure = TRUE)
  cat("Validation passed: every pinned public source has the expected checksum and structure.\n")
  quit(status = 0L)
}

if (length(missing_packages)) {
  stop("Missing packages: ", paste(missing_packages, collapse = ", "),
       ". Run Rscript bootstrap.R first.", call. = FALSE)
}
rm(source_manifest, sample_manifest, contrasts, primary_modules)
targets::tar_make(reporter = "balanced")
