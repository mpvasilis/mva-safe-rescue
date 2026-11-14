track2_package_versions <- function() {
  package_roles <- c(
    targets = "pipeline orchestration",
    testthat = "focused validation tests",
    readxl = "Excel count-matrix import",
    digest = "SHA-256 checksums",
    jsonlite = "machine-readable result serialization",
    ggplot2 = "figures",
    `data.table` = "declared tabular-data dependency",
    DESeq2 = "count normalization and differential expression",
    apeglm = "log2-fold-change shrinkage",
    roastgsa = "competitive maxmean rotation tests",
    SummarizedExperiment = "VST assay extraction",
    limma = "roastgsa analysis dependency",
    BiocManager = "Bioconductor version management"
  )
  packages <- names(package_roles)
  installed <- vapply(packages, function(package) {
    nzchar(system.file(package = package))
  }, logical(1L))
  track2_assert(all(installed), "Required provenance packages are missing: %s",
                paste(packages[!installed], collapse = ", "))
  bioc_version <- as.character(BiocManager::version())
  track2_assert(identical(bioc_version, "3.23"),
                "Bioconductor provenance mismatch: expected 3.23; observed %s", bioc_version)
  data.frame(
    component_type = c("runtime", "runtime", rep("R_package", length(packages))),
    component = c("R", "Bioconductor", packages),
    version = c(as.character(getRversion()), bioc_version,
                vapply(packages, function(package) {
                  as.character(utils::packageVersion(package))
                }, character(1L))),
    role = c("analysis runtime", "analysis package ecosystem", unname(package_roles)),
    stringsAsFactors = FALSE
  )
}

track2_release_result_paths <- function() {
  c(
    "analysis_summary.json",
    "package_versions.tsv",
    "de/GSE290206_CIN_vs_control_candidates.tsv",
    "manifests/source_checksums.tsv",
    "manifests/source_manifest.tsv",
    "manifests/sample_manifest.tsv",
    "manifests/contrasts.tsv",
    "manifests/primary_modules.tsv",
    "modules/preregistered_include_IEA.tsv",
    "modules/preregistered_exclude_IEA_sensitivity.tsv",
    "modules/annotation_policy_sensitivity_summary.tsv",
    "sensitivity/leave_one_batch_out_summary.tsv",
    "sensitivity/leave_one_batch_out_module_results.tsv",
    "sensitivity/leave_one_batch_out_module_summary.tsv",
    "sensitivity/leave_one_batch_out_module_direction_driver_overlap.tsv",
    "sensitivity/raw_vs_normalized_direction_summary.tsv",
    "sensitivity/stability_verdict.tsv",
    "orthology/policy_sensitivity_summary.tsv",
    "sanity/gene_direction_checks.tsv",
    "sanity/module_direction_checks.tsv",
    "qc/qc_summary.json",
    "qc/primary_library_totals.tsv",
    "qc/primary_vst_pca.tsv",
    "figures/primary_vst_pca.png",
    "figures/primary_volcano.png",
    "figures/primary_modules.png",
    "figures/leave_one_batch_out.png",
    "figures/exploratory_dosage_check.png",
    "sessionInfo.txt"
  )
}

track2_atomic_copy <- function(source, destination) {
  track2_assert(file.exists(source), "Release source is missing: %s", source)
  dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(pattern = "track2-release-", tmpdir = dirname(destination))
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  track2_assert(file.copy(source, tmp, overwrite = TRUE, copy.mode = FALSE,
                          copy.date = FALSE),
                "Could not stage release artifact: %s", source)
  if (file.exists(destination)) unlink(destination, force = TRUE)
  track2_assert(file.rename(tmp, destination),
                "Could not finalize release artifact: %s", destination)
  normalizePath(destination, winslash = "/", mustWork = TRUE)
}

track2_atomic_write_bytes <- function(bytes, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(pattern = "track2-release-", tmpdir = dirname(path))
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  con <- file(tmp, open = "wb")
  tryCatch(writeBin(bytes, con), finally = close(con))
  if (file.exists(path)) unlink(path, force = TRUE)
  track2_assert(file.rename(tmp, path), "Could not finalize release checksum: %s", path)
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_assert_release_has_no_links <- function(release_dir) {
  candidates <- c(
    release_dir,
    list.files(release_dir, recursive = TRUE, full.names = TRUE,
               all.files = TRUE, no.. = TRUE, include.dirs = TRUE)
  )
  if (!length(candidates)) return(invisible(TRUE))
  link_targets <- Sys.readlink(candidates)
  linked <- !is.na(link_targets) & nzchar(link_targets)
  track2_assert(!any(linked), "Release tree contains symbolic links/reparse targets: %s",
                paste(candidates[linked], collapse = ", "))
  invisible(TRUE)
}

track2_verify_release <- function(results_dir, release_dir) {
  results_dir <- normalizePath(results_dir, winslash = "/", mustWork = TRUE)
  release_dir <- normalizePath(release_dir, winslash = "/", mustWork = TRUE)
  track2_assert(basename(release_dir) == "release" &&
                  basename(dirname(release_dir)) == "track2",
                "Release verification is restricted to analysis/track2/release")
  track2_assert_release_has_no_links(release_dir)

  expected_payload <- sort(c("README.md", track2_release_result_paths()))
  expected_files <- sort(c(expected_payload, "release_inventory.tsv",
                           "release_inventory.sha256"))
  entries <- list.files(release_dir, recursive = TRUE, full.names = FALSE,
                        all.files = TRUE, no.. = TRUE, include.dirs = TRUE)
  files <- sort(gsub("\\\\", "/", entries[!dir.exists(file.path(release_dir, entries))]))
  track2_assert(identical(files, expected_files),
                "Release file set differs from the exact whitelist")

  inventory_path <- file.path(release_dir, "release_inventory.tsv")
  inventory <- utils::read.delim(inventory_path, check.names = FALSE,
                                 stringsAsFactors = FALSE)
  track2_assert(identical(names(inventory), c("path", "sha256", "bytes")),
                "Release inventory schema must be path/sha256/bytes")
  track2_assert(identical(inventory$path, expected_payload) &&
                  !anyDuplicated(inventory$path),
                "Release inventory rows differ from the exact payload whitelist")
  unsafe <- grepl("(^[A-Za-z]:|^[/\\\\]|(^|[/\\\\])[.][.]($|[/\\\\]))",
                  inventory$path)
  track2_assert(!any(unsafe), "Release inventory contains unsafe path(s): %s",
                paste(inventory$path[unsafe], collapse = ", "))

  payload_paths <- file.path(release_dir, inventory$path)
  payload_hashes <- unname(vapply(payload_paths, track2_sha256, character(1L)))
  payload_bytes <- unname(vapply(payload_paths, function(path) {
    as.numeric(file.info(path)$size)
  }, numeric(1L)))
  track2_assert(identical(payload_hashes, as.character(inventory$sha256)),
                "Release payload SHA-256 mismatch")
  track2_assert(identical(payload_bytes, as.numeric(inventory$bytes)),
                "Release payload byte-count mismatch")

  hash_record <- readLines(file.path(release_dir, "release_inventory.sha256"),
                           warn = FALSE)
  track2_assert(length(hash_record) == 1L &&
                  grepl("^[0-9a-f]{64}  release_inventory[.]tsv$", hash_record),
                "Release inventory self-hash record has invalid syntax")
  expected_inventory_hash <- substr(hash_record, 1L, 64L)
  track2_assert(identical(track2_sha256(inventory_path), expected_inventory_hash),
                "Release inventory self-hash mismatch")

  result_paths <- file.path(results_dir, track2_release_result_paths())
  released_result_paths <- file.path(release_dir, track2_release_result_paths())
  track2_assert(all(file.exists(result_paths)), "Result source for release verification is missing")
  result_hashes <- unname(vapply(result_paths, track2_sha256, character(1L)))
  released_result_hashes <- unname(vapply(released_result_paths, track2_sha256, character(1L)))
  track2_assert(identical(result_hashes, released_result_hashes),
                "Released payload differs from the authoritative result source")
  invisible(TRUE)
}

track2_refresh_release <- function(results_dir, release_dir, release_readme) {
  release_dir_input <- release_dir
  if (dir.exists(release_dir_input) || file.exists(release_dir_input)) {
    direct_link <- Sys.readlink(release_dir_input)
    track2_assert(is.na(direct_link) || !nzchar(direct_link),
                  "Release directory must not be a symbolic link/reparse target")
  }
  results_dir <- normalizePath(results_dir, winslash = "/", mustWork = TRUE)
  release_dir <- normalizePath(release_dir, winslash = "/", mustWork = FALSE)
  track2_assert(basename(release_dir) == "release" &&
                  basename(dirname(release_dir)) == "track2",
                "Release refresh is restricted to analysis/track2/release")
  track2_assert(file.exists(release_readme), "Release README is missing: %s", release_readme)
  dir.create(release_dir, recursive = TRUE, showWarnings = FALSE)
  track2_assert_release_has_no_links(release_dir)

  relative <- track2_release_result_paths()
  source <- file.path(results_dir, relative)
  track2_assert(all(file.exists(source)), "Release inputs are missing: %s",
                paste(relative[!file.exists(source)], collapse = ", "))
  destination <- file.path(release_dir, relative)
  copied <- vapply(seq_along(source), function(i) {
    track2_atomic_copy(source[[i]], destination[[i]])
  }, character(1L))

  expected_relative <- sort(c("README.md", relative))
  expected_paths <- file.path(release_dir, expected_relative)
  track2_assert(all(file.exists(expected_paths)), "Release snapshot is incomplete after copying")

  inventory <- data.frame(
    path = expected_relative,
    sha256 = vapply(expected_paths, track2_sha256, character(1L)),
    bytes = vapply(expected_paths, function(x) unname(file.info(x)$size), numeric(1L)),
    stringsAsFactors = FALSE
  )
  inventory_path <- track2_atomic_write_tsv(
    inventory, file.path(release_dir, "release_inventory.tsv")
  )
  inventory_hash_path <- track2_atomic_write_bytes(
    charToRaw(paste0(track2_sha256(inventory_path), "  release_inventory.tsv\n")),
    file.path(release_dir, "release_inventory.sha256")
  )

  allowed <- normalizePath(
    c(expected_paths, inventory_path, inventory_hash_path),
    winslash = "/", mustWork = TRUE
  )
  existing <- list.files(release_dir, recursive = TRUE, full.names = TRUE,
                         all.files = TRUE, no.. = TRUE)
  existing <- existing[!dir.exists(existing)]
  stale <- setdiff(normalizePath(existing, winslash = "/", mustWork = TRUE), allowed)
  if (length(stale)) unlink(stale, force = TRUE)

  track2_verify_release(results_dir, release_dir)

  unique(c(copied, inventory_path, inventory_hash_path))
}
