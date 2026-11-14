track2_validate_sample_manifest <- function(sample_manifest) {
  required <- c("dataset", "sample_id", "gsm", "batch", "condition", "genotype",
                "age_days_ael", "temperature_c", "sex", "tissue",
                "brains_per_library", "paired_group", "contrast_eligible", "scope")
  track2_assert(all(required %in% names(sample_manifest)),
                "sample_manifest.tsv is missing columns: %s",
                paste(setdiff(required, names(sample_manifest)), collapse = ", "))
  track2_assert(!anyDuplicated(paste(sample_manifest$dataset, sample_manifest$sample_id)),
                "sample_manifest has duplicated dataset/sample_id rows")
  track2_assert(!anyDuplicated(sample_manifest$gsm), "sample_manifest GSM accessions are not unique")

  expected_primary <- c("0916_2024", "0917_2024", "0933_2024", "0934_2024",
                        "1224_2024", "1225_2024")
  primary <- sample_manifest[sample_manifest$dataset == "GSE290206", , drop = FALSE]
  track2_assert(identical(primary$sample_id, expected_primary),
                "GSE290206 sample order does not match the analysis-locked workbook columns")
  track2_assert(identical(primary$condition, rep(c("control", "CIN"), 3L)),
                "GSE290206 must contain a control/CIN pair in each batch")
  track2_assert(identical(primary$batch, rep(c("4", "5", "6"), each = 2L)),
                "GSE290206 batches must be paired 4/5/6")
  track2_assert(all(primary$age_days_ael == "4") && all(primary$temperature_c == "29") &&
                  all(primary$sex == "female") && all(primary$brains_per_library == "3"),
                "GSE290206 biological design fields changed unexpectedly")

  expected_secondary <- c("0918_2024", "0919_2024", "0920_2024", "0921_2024", "0922_2024",
                          "0935_2024", "0936_2024", "0937_2024", "0938_2024", "0939_2024",
                          "1209_2024", "1210_2024", "1211_2024", "1212_2024", "1213_2024")
  expected_condition <- c("ORE", "CDXY", "CDXX", "C2L", "T2L",
                          "ORE", "CDXY", "CDXX", "C2L", "T2L",
                          "ORE", "C2L", "T2L", "CDXY", "CDXX")
  secondary <- sample_manifest[sample_manifest$dataset == "GSE301548", , drop = FALSE]
  track2_assert(identical(secondary$sample_id, expected_secondary),
                "GSE301548 sample order does not match the public workbook")
  track2_assert(identical(secondary$condition, expected_condition),
                "GSE301548 genotype/library mapping changed unexpectedly")
  controls <- secondary$condition %in% c("CDXY", "C2L")
  trisomies <- secondary$condition %in% c("CDXX", "T2L")
  track2_assert(all(secondary$age_days_ael[controls] == "5") &&
                  all(secondary$age_days_ael[trisomies] == "8"),
                "GSE301548 must preserve its perfect age/genotype confounding (5d controls, 8d trisomies)")
  invisible(TRUE)
}

track2_validate_contrasts <- function(contrasts, sample_manifest) {
  required <- c("contrast_id", "dataset", "numerator", "denominator", "batches",
                "design", "scope", "estimand", "size_factor_control", "ranking_eligible")
  track2_assert(all(required %in% names(contrasts)),
                "contrasts.tsv is missing columns: %s",
                paste(setdiff(required, names(contrasts)), collapse = ", "))
  track2_assert(identical(contrasts$contrast_id,
                          c("CIN_vs_control", "CDXX_vs_CDXY", "T2L_vs_C2L")),
                "Contrast registry must contain exactly the analysis-locked contrasts in order")
  track2_assert(contrasts$scope[[1L]] == "primary" &&
                  all(contrasts$scope[-1L] == "exploratory_adversarial"),
                "Only CIN_vs_control may be primary")
  track2_assert(contrasts$ranking_eligible[[1L]] == "TRUE" &&
                  all(contrasts$ranking_eligible[-1L] == "FALSE"),
                "GSE301548 contrasts must remain excluded from candidate ranking")

  for (i in seq_len(nrow(contrasts))) {
    row <- contrasts[i, , drop = FALSE]
    samples <- sample_manifest[
      sample_manifest$dataset == row$dataset &
        sample_manifest$condition %in% c(row$denominator, row$numerator), , drop = FALSE]
    track2_assert(nrow(samples) == 6L,
                  "%s must contain exactly three matched batch pairs", row$contrast_id)
    samples$batch <- factor(samples$batch)
    samples$condition <- factor(samples$condition, levels = c(row$denominator, row$numerator))
    design <- stats::model.matrix(~ batch + condition, data = samples)
    track2_assert(qr(design)$rank == ncol(design),
                  "Design matrix is rank deficient for contrast %s", row$contrast_id)
    tab <- table(samples$batch, samples$condition)
    track2_assert(identical(dim(tab), c(3L, 2L)) && all(tab == 1L),
                  "%s is not one denominator/one numerator per batch", row$contrast_id)
  }
  invisible(TRUE)
}

track2_validate_modules <- function(primary_modules) {
  required <- c("module_order", "module_id", "module_label", "go_id",
                "post_primary_fixed_nomination_set")
  track2_assert(all(required %in% names(primary_modules)),
                "primary_modules.tsv is missing columns: %s",
                paste(setdiff(required, names(primary_modules)), collapse = ", "))
  track2_assert(all(grepl("^GO:[0-9]{7}$", primary_modules$go_id)),
                "Every module root must be a seven-digit GO identifier")
  ids <- unique(primary_modules$module_id)
  track2_assert(length(ids) == 13L, "Expected 13 analysis-locked modules; observed %d", length(ids))
  track2_assert(!anyDuplicated(primary_modules[, c("module_id", "go_id")]),
                "Duplicated module/GO root row")
  by_module <- split(primary_modules$post_primary_fixed_nomination_set,
                     primary_modules$module_id)
  track2_assert(all(vapply(by_module, function(x) length(unique(x)) == 1L, logical(1L))),
                "post_primary_fixed_nomination_set must be consistent across GO roots within a module")
  decision_ids <- sort(names(by_module)[vapply(by_module, function(x) x[[1L]] == "TRUE", logical(1L))])
  expected_decision_ids <- sort(c(
    "mitochondrial_energy", "proteostasis_stress", "folding_proteasome",
    "autophagy_mitophagy", "oxidative_stress", "oxidant_detox", "ribosome_RNA"
  ))
  track2_assert(identical(decision_ids, expected_decision_ids),
                paste0("The post-primary implementation-amendment nomination set changed: ",
                       "expected [%s]; observed [%s]"),
                paste(expected_decision_ids, collapse = ", "), paste(decision_ids, collapse = ", "))
  invisible(TRUE)
}

track2_validate_configuration <- function(source_manifest, sample_manifest, contrasts,
                                          primary_modules, repo_root) {
  track2_assert(normalizePath(repo_root, mustWork = TRUE) == normalizePath(file.path(getwd(), "../.."), mustWork = TRUE) ||
                  dir.exists(file.path(repo_root, "analysis", "track2")),
                "repo_root does not contain analysis/track2")
  required_sources <- c("GSE290206_counts", "GSE301548_counts", "FlyBase_orthologs_FB2026_02",
                        "FlyBase_gene_map_FB2026_02", "FlyBase_GAF_FB2026_02",
                        "FlyBase_GO_graph_FB2026_02", "FlyBase_RPKM_FB2026_02")
  track2_assert(identical(source_manifest$source_id, required_sources),
                "source_manifest must contain exactly the pinned public sources in analysis-locked order")
  track2_validate_sample_manifest(sample_manifest)
  track2_validate_contrasts(contrasts, sample_manifest)
  track2_validate_modules(primary_modules)
  invisible(TRUE)
}

track2_import_count_workbook <- function(path, manifest_row, sample_manifest) {
  track2_assert(requireNamespace("readxl", quietly = TRUE),
                "Package 'readxl' is required to import counts. Run bootstrap.R.")
  track2_validate_xlsx(path, manifest_row)
  expected_headers <- track2_expected_headers(manifest_row$expected_headers[[1L]])
  tab <- readxl::read_excel(
    path,
    sheet = manifest_row$expected_sheet[[1L]],
    col_types = c("text", rep("numeric", length(expected_headers) - 1L)),
    .name_repair = "minimal"
  )
  ids <- tab[[1L]]
  track2_assert(!anyNA(ids) && all(nzchar(ids)), "%s contains missing/blank gene identifiers",
                manifest_row$source_id[[1L]])
  track2_assert(all(grepl("^FBgn[0-9]{7}$", ids)),
                "%s contains identifiers that are not canonical FBgn IDs",
                manifest_row$source_id[[1L]])
  track2_assert(!anyDuplicated(ids), "%s contains duplicated FBgn identifiers",
                manifest_row$source_id[[1L]])

  counts <- as.matrix(tab[-1L])
  rownames(counts) <- ids
  colnames(counts) <- expected_headers[-1L]
  track2_assert(is.numeric(counts) && !anyNA(counts) && all(is.finite(counts)),
                "%s contains missing or nonnumeric counts", manifest_row$source_id[[1L]])
  track2_assert(all(counts >= 0), "%s contains negative counts", manifest_row$source_id[[1L]])
  track2_assert(all(counts == floor(counts)), "%s contains non-integer counts",
                manifest_row$source_id[[1L]])
  track2_assert(max(counts) <= .Machine$integer.max,
                "%s contains counts larger than R's integer range", manifest_row$source_id[[1L]])
  storage.mode(counts) <- "integer"

  dataset <- if (manifest_row$source_id[[1L]] == "GSE290206_counts") "GSE290206" else "GSE301548"
  samples <- sample_manifest[sample_manifest$dataset == dataset, , drop = FALSE]
  track2_assert(identical(colnames(counts), samples$sample_id),
                "%s count columns do not exactly match sample_manifest order", dataset)
  rownames(samples) <- samples$sample_id

  list(
    dataset = dataset,
    counts = counts,
    samples = samples,
    source_sha256 = track2_sha256(path),
    source_dimensions = c(genes = nrow(counts), libraries = ncol(counts))
  )
}

track2_filter_counts <- function(counts, min_count = 10L, min_samples = 3L) {
  track2_assert(is.matrix(counts) && storage.mode(counts) == "integer",
                "Count filtering requires an integer matrix")
  keep <- rowSums(counts >= min_count) >= min_samples
  track2_assert(any(keep), "No genes pass the analysis-locked count filter")
  list(
    counts = counts[keep, , drop = FALSE],
    keep = keep,
    threshold = list(min_count = min_count, min_samples = min_samples),
    n_input = nrow(counts),
    n_retained = sum(keep)
  )
}

track2_library_totals <- function(imported, filtered) {
  data.frame(
    dataset = imported$dataset,
    sample_id = colnames(imported$counts),
    raw_library_total = as.numeric(colSums(imported$counts)),
    retained_library_total = as.numeric(colSums(filtered$counts)),
    retained_fraction = as.numeric(colSums(filtered$counts) / colSums(imported$counts)),
    stringsAsFactors = FALSE
  )
}

track2_pca_table <- function(vst_matrix, samples) {
  track2_assert(identical(colnames(vst_matrix), samples$sample_id),
                "VST columns and sample manifest are not aligned")
  pcs <- stats::prcomp(t(vst_matrix), center = TRUE, scale. = FALSE)
  variance <- pcs$sdev^2 / sum(pcs$sdev^2)
  data.frame(
    sample_id = rownames(pcs$x),
    PC1 = pcs$x[, 1L],
    PC2 = pcs$x[, 2L],
    PC1_variance = variance[[1L]],
    PC2_variance = variance[[2L]],
    batch = samples[rownames(pcs$x), "batch"],
    condition = samples[rownames(pcs$x), "condition"],
    stringsAsFactors = FALSE,
    row.names = NULL
  )
}

track2_qc_payload <- function(primary_import, primary_filter, primary_analysis,
                              exploratory_import, exploratory_filter) {
  list(
    schema_version = "1.0",
    seed = 20260826L,
    primary = list(
      dataset = primary_import$dataset,
      source_sha256 = primary_import$source_sha256,
      source_dimensions = as.list(primary_import$source_dimensions),
      filter = primary_filter$threshold,
      retained_genes = primary_filter$n_retained,
      library_totals = track2_library_totals(primary_import, primary_filter),
      pca = track2_pca_table(primary_analysis$vst, primary_import$samples)
    ),
    exploratory_adversarial = list(
      dataset = exploratory_import$dataset,
      warning = paste0("GSE301548 genotype is perfectly confounded with chronological age; ",
                       "outputs estimate combined age+genotype contrasts only."),
      source_sha256 = exploratory_import$source_sha256,
      source_dimensions = as.list(exploratory_import$source_dimensions),
      filter = exploratory_filter$threshold,
      retained_genes = exploratory_filter$n_retained,
      library_totals = track2_library_totals(exploratory_import, exploratory_filter)
    )
  )
}
