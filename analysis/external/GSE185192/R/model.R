gse_filter_counts <- function(counts, min_count = 10L, min_samples = 3L) {
  keep <- rowSums(counts >= min_count) >= min_samples
  gse_assert(sum(keep) >= 1000L, "Too few genes remain after count filtering: %d", sum(keep))
  counts[keep, , drop = FALSE]
}

gse_fit_deseq <- function(counts, samples) {
  gse_assert(requireNamespace("DESeq2", quietly = TRUE), "Package 'DESeq2' is required")
  if (requireNamespace("BiocParallel", quietly = TRUE)) {
    BiocParallel::register(BiocParallel::SerialParam())
  }
  gse_assert(identical(colnames(counts), samples$accession), "Counts and samples are misaligned")
  safe_condition <- ifelse(samples$condition == "Iso-E", "IsoE", "IsoT")
  col_data <- data.frame(
    condition = factor(safe_condition, levels = c("IsoE", "IsoT")),
    row.names = samples$accession, check.names = FALSE
  )
  design_matrix <- stats::model.matrix(~ condition, data = col_data)
  gse_assert(qr(design_matrix)$rank == ncol(design_matrix), "DESeq2 design is rank deficient")
  dds <- DESeq2::DESeqDataSetFromMatrix(countData = counts, colData = col_data,
                                        design = ~ condition)
  dds <- DESeq2::DESeq(dds, test = "Wald", minReplicatesForReplace = Inf,
                       parallel = FALSE, quiet = TRUE)
  result <- DESeq2::results(dds, contrast = c("condition", "IsoT", "IsoE"),
                            alpha = 0.10, cooksCutoff = FALSE, independentFiltering = TRUE)
  vst <- SummarizedExperiment::assay(DESeq2::varianceStabilizingTransformation(dds, blind = FALSE))
  list(dds = dds, result = result, vst = vst, size_factors = DESeq2::sizeFactors(dds))
}

gse_pca_coordinates <- function(vst, samples, lineage, sensitivity) {
  pca <- stats::prcomp(t(vst), center = TRUE, scale. = FALSE)
  percent <- 100 * (pca$sdev^2 / sum(pca$sdev^2))
  data.frame(
    lineage = lineage, sensitivity = sensitivity, accession = rownames(pca$x),
    condition = samples$condition[match(rownames(pca$x), samples$accession)],
    replicate = as.integer(samples$replicate[match(rownames(pca$x), samples$accession)]),
    PC1 = pca$x[, 1L], PC2 = pca$x[, 2L],
    PC1_percent_variance = percent[[1L]], PC2_percent_variance = percent[[2L]],
    stringsAsFactors = FALSE, row.names = NULL
  )
}

gse_continuous_module_summary <- function(wald, genes) {
  values <- wald[match(genes, names(wald))]
  values <- values[is.finite(values)]
  if (!length(values)) return(c(n = 0, mean = NA_real_, maxmean = NA_real_))
  pos <- mean(pmax(values, 0))
  neg <- mean(pmax(-values, 0))
  c(n = length(values), mean = mean(values), maxmean = if (pos >= neg) pos else -neg)
}

gse_test_modules <- function(vst, samples, module_sets, de_table, lineage, sensitivity,
                             seed = 20260826L, nrot = 9999L) {
  gse_assert(requireNamespace("roastgsa", quietly = TRUE), "Package 'roastgsa' is required")
  original_ids <- rownames(vst)
  measured_sets <- lapply(module_sets, function(symbols) {
    original_ids[toupper(original_ids) %in% symbols]
  })
  eligible <- lengths(measured_sets) >= 10L
  gse_assert(any(eligible), "No locked module has at least ten measured genes")
  covar <- data.frame(
    condition = factor(ifelse(samples$condition == "Iso-E", "IsoE", "IsoT"),
                       levels = c("IsoE", "IsoT")),
    row.names = samples$accession
  )
  form <- ~ condition
  design <- stats::model.matrix(form, data = covar)
  contrast <- rep(0, ncol(design))
  contrast[[ncol(design)]] <- 1
  set.seed(seed)
  fit <- roastgsa::roastgsa(
    y = vst, covar = covar, form = form, contrast = contrast,
    index = measured_sets[eligible], self.contained = FALSE,
    set.statistic = "maxmean", nrot = nrot, minsize = 10L,
    maxsize = nrow(vst), mccores = 1L, executation.info = FALSE,
    shrink.resid = TRUE, normalizeScores = TRUE
  )
  observed <- as.data.frame(fit$res)
  observed$module_id <- rownames(observed)
  rownames(observed) <- NULL
  out <- data.frame(module_id = names(measured_sets),
                    configured_gene_symbols = lengths(module_sets),
                    measured_genes_declared = lengths(measured_sets),
                    evaluable_min_10_measured = eligible, stringsAsFactors = FALSE)
  out <- merge(out, observed, by = "module_id", all.x = TRUE, sort = FALSE)
  out <- out[match(names(measured_sets), out$module_id), , drop = FALSE]
  pcol <- intersect(c("pval", "p.value", "P.Value"), names(out))
  gse_assert(length(pcol) == 1L, "Could not identify roastgsa p-value column")
  out$pvalue <- out[[pcol]]
  out[[pcol]] <- NULL
  adj_col <- intersect(c("adj.pval", "adj.p.value", "adj.P.Val"), names(out))
  gse_assert(length(adj_col) == 1L, "Could not identify roastgsa evaluable-only adjusted p-value")
  names(out)[names(out) == adj_col] <- "roastgsa_adj_pvalue_evaluable_only_nondecision"
  out$module_qvalue_BH_n7_authoritative <- NA_real_
  finite <- is.finite(out$pvalue)
  out$module_qvalue_BH_n7_authoritative[finite] <-
    stats::p.adjust(out$pvalue[finite], method = "BH", n = 7L)
  wald <- stats::setNames(de_table$wald_stat, de_table$gene_symbol)
  continuous <- t(vapply(measured_sets, gse_continuous_module_summary, numeric(3L), wald = wald))
  out$n_finite_continuous_wald <- continuous[out$module_id, "n"]
  out$mean_continuous_wald <- continuous[out$module_id, "mean"]
  out$maxmean_continuous_wald <- continuous[out$module_id, "maxmean"]
  out$lineage <- lineage
  out$sensitivity <- sensitivity
  out$contrast <- "Iso-T_vs_Iso-E"
  out$direction <- gse_direction(out$nes)
  out$seed <- seed
  out$nrot <- nrot
  out$multiple_testing_family <- "authoritative_BH_n7_across_all_configured_modules"
  out$roastgsa_adjustment_use <- "evaluable_only_transparency_column_not_used_for_decisions"
  out$test_type <- "competitive_rotation_maxmean"
  lead <- c("lineage", "sensitivity", "contrast", "module_id", "configured_gene_symbols",
            "measured_genes_declared", "evaluable_min_10_measured", "est", "nes",
            "direction", "pvalue",
            "module_qvalue_BH_n7_authoritative",
            "roastgsa_adj_pvalue_evaluable_only_nondecision")
  out[, c(lead[lead %in% names(out)], setdiff(names(out), lead)), drop = FALSE]
}

gse_run_analysis <- function(all_counts, all_samples, chromosome_map, module_sets,
                             lineage, sensitivity) {
  samples <- all_samples[all_samples$lineage == lineage, , drop = FALSE]
  samples <- samples[order(match(samples$condition, c("Iso-E", "Iso-T")),
                           as.integer(samples$replicate)), , drop = FALSE]
  counts <- all_counts[, samples$accession, drop = FALSE]
  chromosome_idx <- match(toupper(rownames(counts)), chromosome_map$gene_symbol_upper)
  is_chr21 <- chromosome_map$is_chr21[chromosome_idx]
  is_chr21[is.na(is_chr21)] <- FALSE
  chromosome_ambiguous <- chromosome_map$chromosome_mapping_ambiguous[chromosome_idx]
  chromosome_ambiguous[is.na(chromosome_ambiguous)] <- FALSE
  unmapped_before_filter <- is.na(chromosome_idx)
  chr21_excluded_before_filter <- if (sensitivity == "chr21_excluded") sum(is_chr21) else 0L
  if (sensitivity == "chr21_excluded") counts <- counts[!is_chr21, , drop = FALSE]
  filtered <- gse_filter_counts(counts)
  fit <- gse_fit_deseq(filtered, samples)
  de <- as.data.frame(fit$result)
  de$gene_symbol <- rownames(de)
  rownames(de) <- NULL
  names(de)[names(de) == "stat"] <- "wald_stat"
  idx <- match(toupper(de$gene_symbol), chromosome_map$gene_symbol_upper)
  de$chromosome_labels <- chromosome_map$chromosome_labels[idx]
  de$is_chr21 <- chromosome_map$is_chr21[idx]
  de$is_chr21[is.na(de$is_chr21)] <- FALSE
  de$chromosome_mapping_ambiguous <- chromosome_map$chromosome_mapping_ambiguous[idx]
  de$lineage <- lineage
  de$sensitivity <- sensitivity
  de$contrast <- "Iso-T_vs_Iso-E"
  de <- de[, c("lineage", "sensitivity", "contrast", "gene_symbol", "chromosome_labels",
               "is_chr21", "chromosome_mapping_ambiguous", "baseMean", "log2FoldChange",
               "lfcSE", "wald_stat", "pvalue", "padj")]
  modules <- gse_test_modules(fit$vst, samples, module_sets, de, lineage, sensitivity)
  pca <- gse_pca_coordinates(fit$vst, samples, lineage, sensitivity)
  full_chr21 <- de$is_chr21 & is.finite(de$log2FoldChange)
  off_chr21 <- !de$is_chr21 & is.finite(de$log2FoldChange)
  summary <- data.frame(
    lineage = lineage, sensitivity = sensitivity, contrast = "Iso-T_vs_Iso-E",
    input_gene_rows = nrow(all_counts), analyzed_gene_rows_before_filter = nrow(counts),
    input_gencode_unmapped_gene_rows = sum(unmapped_before_filter),
    input_gencode_ambiguous_multichromosome_rows = sum(chromosome_ambiguous),
    chr21_gene_rows_excluded_before_filter = chr21_excluded_before_filter,
    retained_gene_rows = nrow(filtered), padj_nonmissing = sum(is.finite(de$padj)),
    gene_level_q_le_0_10 = sum(is.finite(de$padj) & de$padj <= 0.10),
    gene_level_q_le_0_10_abs_lfc_ge_0_5 = sum(is.finite(de$padj) & de$padj <= 0.10 &
                                               abs(de$log2FoldChange) >= 0.5),
    mapped_chr21_genes_tested = sum(full_chr21),
    median_chr21_log2fc = if (any(full_chr21)) stats::median(de$log2FoldChange[full_chr21]) else NA_real_,
    median_nonchr21_log2fc = if (any(off_chr21)) stats::median(de$log2FoldChange[off_chr21]) else NA_real_,
    chr21_minus_nonchr21_median_log2fc = if (any(full_chr21) && any(off_chr21))
      stats::median(de$log2FoldChange[full_chr21]) - stats::median(de$log2FoldChange[off_chr21]) else NA_real_,
    evaluable_modules = sum(is.finite(modules$pvalue)),
    modules_q_le_0_10 = sum(is.finite(modules$module_qvalue_BH_n7_authoritative) &
                              modules$module_qvalue_BH_n7_authoritative <= 0.10),
    design = "~ condition", independent_donor_count = 1L,
    confound = "genotype_perfectly_confounded_with_derivative_line",
    stringsAsFactors = FALSE
  )
  top_order <- order(ifelse(is.finite(de$padj), de$padj, Inf), -abs(de$wald_stat), de$gene_symbol)
  top <- de[head(top_order, 25L), , drop = FALSE]
  size_factors <- data.frame(lineage = lineage, sensitivity = sensitivity,
                             accession = names(fit$size_factors),
                             size_factor = as.numeric(fit$size_factors), stringsAsFactors = FALSE)
  list(de = de, modules = modules, pca = pca, summary = summary, top = top,
       size_factors = size_factors)
}
