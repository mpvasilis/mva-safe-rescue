track2_deseq_model <- function(counts, samples, denominator, numerator,
                               control_genes = NULL, make_vst = FALSE) {
  track2_assert(requireNamespace("DESeq2", quietly = TRUE),
                "Package 'DESeq2' is required. Run bootstrap.R.")
  track2_assert(requireNamespace("apeglm", quietly = TRUE),
                "Package 'apeglm' is required. Run bootstrap.R.")
  track2_assert(identical(colnames(counts), samples$sample_id),
                "Counts and sample metadata are not in identical order")

  col_data <- data.frame(
    batch = factor(samples$batch),
    condition = factor(samples$condition, levels = c(denominator, numerator)),
    row.names = samples$sample_id,
    check.names = FALSE
  )
  design_matrix <- stats::model.matrix(~ batch + condition, data = col_data)
  track2_assert(qr(design_matrix)$rank == ncol(design_matrix),
                "DESeq2 design ~ batch + condition is rank deficient for %s vs %s",
                numerator, denominator)
  dds <- DESeq2::DESeqDataSetFromMatrix(
    countData = counts,
    colData = col_data,
    design = ~ batch + condition
  )
  if (is.null(control_genes)) {
    dds <- DESeq2::estimateSizeFactors(dds)
  } else {
    track2_assert(is.logical(control_genes) && length(control_genes) == nrow(dds),
                  "control_genes must be a logical vector aligned to count rows")
    track2_assert(sum(control_genes) >= 100L,
                  "Fewer than 100 genes remain for chromosome-aware size-factor estimation")
    dds <- DESeq2::estimateSizeFactors(dds, controlGenes = which(control_genes))
  }
  track2_assert(all(is.finite(DESeq2::sizeFactors(dds))) && all(DESeq2::sizeFactors(dds) > 0),
                "DESeq2 size-factor estimation failed")

  # Infinite replacement threshold is an explicit guarantee that Cook outliers are not replaced.
  dds <- DESeq2::DESeq(
    dds,
    test = "Wald",
    minReplicatesForReplace = Inf,
    parallel = FALSE,
    quiet = TRUE
  )
  coefficient <- paste0("condition_", numerator, "_vs_", denominator)
  track2_assert(coefficient %in% DESeq2::resultsNames(dds),
                "Expected coefficient '%s' is absent. Available: %s", coefficient,
                paste(DESeq2::resultsNames(dds), collapse = ", "))
  unshrunk <- DESeq2::results(
    dds,
    name = coefficient,
    alpha = 0.10,
    cooksCutoff = FALSE,
    independentFiltering = TRUE
  )
  shrunk <- DESeq2::lfcShrink(dds, coef = coefficient, type = "apeglm")
  vst_matrix <- NULL
  if (make_vst) {
    vst_matrix <- SummarizedExperiment::assay(DESeq2::vst(dds, blind = FALSE))
  }
  list(
    dds = dds,
    unshrunk = unshrunk,
    shrunk = shrunk,
    coefficient = coefficient,
    vst = vst_matrix,
    normalized_counts = DESeq2::counts(dds, normalized = TRUE),
    size_factors = DESeq2::sizeFactors(dds),
    design_matrix = design_matrix
  )
}

track2_within_batch_effects <- function(raw_counts, normalized_counts, samples,
                                        denominator, numerator) {
  batches <- sort(unique(samples$batch))
  raw <- normalized <- matrix(
    NA_real_, nrow = nrow(raw_counts), ncol = length(batches),
    dimnames = list(rownames(raw_counts), paste0("batch", batches))
  )
  for (j in seq_along(batches)) {
    b <- batches[[j]]
    den <- samples$sample_id[samples$batch == b & samples$condition == denominator]
    num <- samples$sample_id[samples$batch == b & samples$condition == numerator]
    track2_assert(length(den) == 1L && length(num) == 1L,
                  "Batch %s is not an exact %s/%s pair", b, denominator, numerator)
    raw[, j] <- log2((raw_counts[, num] + 0.5) / (raw_counts[, den] + 0.5))
    normalized[, j] <- log2((normalized_counts[, num] + 0.5) /
                              (normalized_counts[, den] + 0.5))
  }
  list(raw = raw, normalized = normalized)
}

track2_de_table <- function(model, raw_counts, samples, denominator, numerator,
                            primary_thresholds = FALSE) {
  unshrunk <- as.data.frame(model$unshrunk)
  shrunk <- as.data.frame(model$shrunk)
  track2_assert(identical(rownames(unshrunk), rownames(shrunk)),
                "Unshrunk and shrunken DESeq2 results are not aligned")
  effects <- track2_within_batch_effects(
    raw_counts, model$normalized_counts, samples, denominator, numerator
  )
  effect_column <- function(x, name) {
    if (name %in% colnames(x)) x[, name] else rep(NA_real_, nrow(x))
  }
  direction <- sign(shrunk$log2FoldChange)
  agreement <- as.integer(rowSums(sign(effects$raw) == direction & sign(effects$raw) != 0L,
                                  na.rm = TRUE))
  out <- data.frame(
    flybase_gene_id = rownames(unshrunk),
    baseMean = unshrunk$baseMean,
    log2FoldChange_unshrunk = unshrunk$log2FoldChange,
    lfcSE_unshrunk = unshrunk$lfcSE,
    wald_stat = unshrunk$stat,
    pvalue = unshrunk$pvalue,
    padj = unshrunk$padj,
    log2FoldChange_shrunken = shrunk$log2FoldChange,
    lfcSE_shrunken = shrunk$lfcSE,
    shrunken_fold_change = 2^shrunk$log2FoldChange,
    within_batch_raw_log2fc_4 = effect_column(effects$raw, "batch4"),
    within_batch_raw_log2fc_5 = effect_column(effects$raw, "batch5"),
    within_batch_raw_log2fc_6 = effect_column(effects$raw, "batch6"),
    within_batch_normalized_log2fc_4 = effect_column(effects$normalized, "batch4"),
    within_batch_normalized_log2fc_5 = effect_column(effects$normalized, "batch5"),
    within_batch_normalized_log2fc_6 = effect_column(effects$normalized, "batch6"),
    raw_direction_agreement_n = agreement,
    stringsAsFactors = FALSE,
    row.names = NULL
  )
  if (primary_thresholds) {
    out$passes_primary_threshold <- !is.na(out$padj) & out$padj <= 0.10 &
      abs(out$log2FoldChange_shrunken) >= log2(1.25) &
      out$raw_direction_agreement_n >= 2L
  }
  out
}

track2_run_primary <- function(primary_import, primary_filter) {
  samples <- primary_import$samples
  counts <- primary_filter$counts
  model <- track2_deseq_model(
    counts, samples, denominator = "control", numerator = "CIN", make_vst = TRUE
  )
  de <- track2_de_table(model, counts, samples, "control", "CIN", primary_thresholds = TRUE)
  list(
    model = model,
    de = de,
    vst = model$vst,
    candidate_count = sum(de$passes_primary_threshold),
    interpretation = "SAC-depletion/CIN pathway evidence; not BUB1B-specific",
    source_scope = "female 96h AEL whole brain; 29C; three brains per library"
  )
}

track2_chromosome_control <- function(gene_ids, gene_map, excluded_arm) {
  idx <- match(gene_ids, gene_map$flybase_gene_id)
  arms <- gene_map$chromosome_arm[idx]
  keep <- !is.na(arms) & nzchar(arms) & arms != excluded_arm
  names(keep) <- gene_ids
  keep
}

track2_run_exploratory_contrast <- function(exploratory_import, contrast_row, gene_map) {
  samples <- exploratory_import$samples
  samples <- samples[samples$condition %in% c(contrast_row$denominator, contrast_row$numerator), , drop = FALSE]
  samples <- samples[order(as.integer(samples$batch),
                           match(samples$condition, c(contrast_row$denominator, contrast_row$numerator))), , drop = FALSE]
  counts <- exploratory_import$counts[, samples$sample_id, drop = FALSE]
  filtered <- track2_filter_counts(counts, min_count = 10L, min_samples = 3L)
  excluded_arm <- if (contrast_row$contrast_id == "CDXX_vs_CDXY") "X" else "2L"
  controls <- track2_chromosome_control(rownames(filtered$counts), gene_map, excluded_arm)
  model <- track2_deseq_model(
    filtered$counts, samples,
    denominator = contrast_row$denominator,
    numerator = contrast_row$numerator,
    control_genes = controls,
    make_vst = FALSE
  )
  de <- track2_de_table(
    model, filtered$counts, samples,
    denominator = contrast_row$denominator,
    numerator = contrast_row$numerator,
    primary_thresholds = FALSE
  )
  arm <- gene_map$chromosome_arm[match(de$flybase_gene_id, gene_map$flybase_gene_id)]
  on_arm <- arm == excluded_arm & !is.na(arm)
  dosage <- data.frame(
    contrast_id = contrast_row$contrast_id,
    estimand = contrast_row$estimand,
    duplicated_region = excluded_arm,
    n_genes_on_region = sum(on_arm & is.finite(de$log2FoldChange_unshrunk)),
    median_unshrunk_log2fc_on_region = stats::median(de$log2FoldChange_unshrunk[on_arm], na.rm = TRUE),
    median_unshrunk_log2fc_outside_region = stats::median(de$log2FoldChange_unshrunk[!on_arm], na.rm = TRUE),
    median_shift = stats::median(de$log2FoldChange_unshrunk[on_arm], na.rm = TRUE) -
      stats::median(de$log2FoldChange_unshrunk[!on_arm], na.rm = TRUE),
    stringsAsFactors = FALSE
  )
  de$contrast_id <- contrast_row$contrast_id
  de$estimand <- contrast_row$estimand
  de$scope <- "exploratory_adversarial"
  de$ranking_eligible <- FALSE
  de$chromosome_arm <- arm
  list(
    de = de,
    dosage = dosage,
    size_factors = data.frame(
      contrast_id = contrast_row$contrast_id,
      sample_id = names(model$size_factors),
      size_factor = as.numeric(model$size_factors),
      control_gene_rule = contrast_row$size_factor_control,
      stringsAsFactors = FALSE
    ),
    warning = paste0("Not an identifiable genotype effect: ", contrast_row$estimand,
                     ". Genotype is perfectly confounded with chronological age."),
    filtered_genes = filtered$n_retained
  )
}

track2_run_exploratory <- function(exploratory_import, contrasts, gene_map) {
  registry <- contrasts[contrasts$dataset == "GSE301548", , drop = FALSE]
  analyses <- lapply(seq_len(nrow(registry)), function(i) {
    track2_run_exploratory_contrast(exploratory_import, registry[i, , drop = FALSE], gene_map)
  })
  names(analyses) <- registry$contrast_id
  analyses
}

track2_unique_symbol_indices <- function(requested_symbols, gene_map) {
  hits <- lapply(requested_symbols, function(symbol) {
    which(tolower(gene_map$gene_symbol) == tolower(symbol))
  })
  counts <- lengths(hits)
  track2_assert(all(counts == 1L),
                "Sanity symbols must map uniquely in the pinned gene map; failures: %s",
                paste(sprintf("%s(n=%d)", requested_symbols[counts != 1L], counts[counts != 1L]),
                      collapse = ", "))
  as.integer(vapply(hits, `[[`, integer(1L), 1L))
}

track2_sanity_checks <- function(primary_de, gene_map, module_results) {
  targets <- data.frame(
    gene_symbol = c("bub3", "Hsp70Ba", "Hsp70Bb", "Hsp70Bc", "Hsp70Bbb", "GstE8"),
    expected_direction = c("down", rep("up", 5L)),
    stringsAsFactors = FALSE
  )
  map_index <- track2_unique_symbol_indices(targets$gene_symbol, gene_map)
  mapped <- data.frame(
    flybase_gene_id = gene_map$flybase_gene_id[map_index],
    gene_symbol = targets$gene_symbol,
    canonical_gene_symbol = gene_map$gene_symbol[map_index],
    expected_direction = targets$expected_direction,
    stringsAsFactors = FALSE
  )
  mapped <- merge(mapped, primary_de, by = "flybase_gene_id", all.x = TRUE, sort = FALSE)
  mapped$observed_direction <- ifelse(
    is.na(mapped$log2FoldChange_shrunken), "missing",
    ifelse(mapped$log2FoldChange_shrunken > 0, "up",
           ifelse(mapped$log2FoldChange_shrunken < 0, "down", "zero"))
  )
  mapped$passes_direction_check <- mapped$observed_direction == mapped$expected_direction

  module_expectations <- data.frame(
    module_id = c("mitochondrial_energy", "ribosome_RNA"),
    expected_direction = "down",
    stringsAsFactors = FALSE
  )
  observed <- module_results[, c("module_id", "est", "nes", "pval", "module_qvalue"), drop = FALSE]
  module_checks <- merge(module_expectations, observed, by = "module_id", all.x = TRUE, sort = FALSE)
  module_checks$observed_direction <- ifelse(
    is.na(module_checks$nes), "missing", ifelse(module_checks$nes < 0, "down", "up")
  )
  module_checks$passes_direction_check <- module_checks$observed_direction == module_checks$expected_direction
  list(genes = mapped, modules = module_checks)
}
