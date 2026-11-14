gse_assert <- function(ok, fmt, ...) {
  if (!isTRUE(ok)) stop(sprintf(fmt, ...), call. = FALSE)
}

gse_read_tsv <- function(path) {
  gse_assert(file.exists(path), "Missing TSV: %s", path)
  utils::read.delim(path, sep = "\t", header = TRUE, quote = "", comment.char = "",
                    check.names = FALSE, stringsAsFactors = FALSE)
}

gse_write_tsv <- function(x, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  utils::write.table(x, path, sep = "\t", quote = FALSE, row.names = FALSE,
                     col.names = TRUE, na = "NA", eol = "\n", fileEncoding = "UTF-8")
  invisible(path)
}

gse_write_tsv_gz <- function(x, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  con <- gzfile(path, open = "wt")
  on.exit(close(con), add = TRUE)
  utils::write.table(x, con, sep = "\t", quote = FALSE, row.names = FALSE,
                     col.names = TRUE, na = "NA", eol = "\n")
  invisible(path)
}

gse_assert_rectangular_tsv <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  gse_assert(length(lines) >= 1L, "Empty TSV: %s", path)
  fields <- lengths(strsplit(lines, "\t", fixed = TRUE))
  gse_assert(length(unique(fields)) == 1L, "Non-rectangular TSV: %s", path)
  invisible(TRUE)
}

gse_sha256 <- function(path) {
  gse_assert(requireNamespace("digest", quietly = TRUE),
             "Package 'digest' is required. Run bootstrap.R.")
  tolower(digest::digest(path, algo = "sha256", file = TRUE, serialize = FALSE))
}

gse_direction <- function(x) {
  ifelse(is.na(x), "missing", ifelse(x > 0, "up", ifelse(x < 0, "down", "zero")))
}

gse_validate_configs <- function(samples, modules, sources) {
  gse_assert(nrow(samples) == 12L, "Expected 12 eligible samples; found %d", nrow(samples))
  gse_assert(!anyDuplicated(samples$accession), "Sample accessions must be unique")
  gse_assert(length(unique(samples$lineage)) == 2L &&
               setequal(unique(samples$lineage), c("iPSC", "NPC")),
             "Lineages must be exactly iPSC and NPC")
  for (lineage in c("NPC", "iPSC")) {
    x <- samples[samples$lineage == lineage, , drop = FALSE]
    gse_assert(nrow(x) == 6L, "%s must have six samples", lineage)
    condition_counts <- table(x$condition)
    gse_assert(all(condition_counts[c("Iso-E", "Iso-T")] == 3L),
               "%s must contain three Iso-E and three Iso-T samples", lineage)
  }
  gse_assert(nrow(modules) == 7L && !anyDuplicated(modules$module_id),
             "Exactly seven unique locked modules are required")
  expected <- c("mitochondrial_energy", "proteostasis_stress", "folding_proteasome",
                "autophagy_mitophagy", "oxidative_stress", "oxidant_detox", "ribosome_RNA")
  gse_assert(identical(modules$module_id[order(as.integer(modules$module_order))], expected),
             "Locked module identities/order changed")
  gse_assert("module_status" %in% names(modules) &&
               all(modules$module_status ==
                     "configured_original_analysis_locked_not_external_preregistration"),
             "External module status must remain explicit and non-preregistration")
  gse_assert(nrow(sources) == 27L && !anyDuplicated(sources$source_id),
             "Source manifest must contain 27 unique rows")
  gse_assert(all(grepl("^[0-9a-f]{64}$", sources$sha256)), "Invalid SHA-256 in source manifest")
  gse_assert(all(grepl("^https://", sources$url)), "All source URLs must use HTTPS")
  gse_assert(all(!grepl("(^|[\\\\/])\\.\\.([\\\\/]|$)", sources$cache_path)),
             "Cache paths may not traverse upward")
  invisible(TRUE)
}
