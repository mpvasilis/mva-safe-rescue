args <- commandArgs(trailingOnly = TRUE)
file_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)[[1]]
here <- normalizePath(dirname(sub("^--file=", "", file_arg)), winslash = "/")
root <- normalizePath(file.path(here, "../../.."), winslash = "/")
.libPaths(c(file.path(root, "analysis/track2/.Rlib"), .libPaths()))
options(mc.cores = 1L)
set.seed(20260909L)
suppressPackageStartupMessages(library(DESeq2))
suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(digest))

panel_symbols <- c("Bub1b", "Hsf1", "Hspa1a", "Hspa1b", "Hspa8", "Hspd1", "Hspe1",
                   "Crls1", "Taz", "Ppargc1a", "Sod2", "Gpx1", "Cdkn2a", "Cdkn1a")
validate_input <- function(x, samples) {
  if (anyDuplicated(rownames(x)) || anyDuplicated(colnames(x))) stop("duplicate gene or sample")
  if (!identical(colnames(x), samples$sample)) stop("sample identity/order mismatch")
  if (any(!is.finite(x)) || any(x < 0) || any(x != floor(x))) stop("counts must be nonnegative integers")
  expected <- c("skM.WT" = 4L, "skM.HL1002P" = 4L, "skM.HH" = 3L,
                "fat.WT" = 4L, "fat.HL1002P" = 4L, "fat.HH" = 4L)
  actual <- table(paste(samples$tissue, samples$genotype, sep = "."))
  if (!setequal(names(actual), names(expected)) || any(actual[names(expected)] != expected)) stop("unexpected group sizes")
  invisible(TRUE)
}
if ("--self-test" %in% args) {
  samples <- read.delim(file.path(here, "samples.tsv"), check.names = FALSE)
  x <- matrix(12L, nrow = 20, ncol = 23, dimnames = list(paste0("SYNTHETIC_G", 1:20), samples$sample))
  stopifnot(validate_input(x, samples))
  broken <- x; broken[1, 1] <- -1
  stopifnot(inherits(try(validate_input(broken, samples), silent = TRUE), "try-error"))
  broken <- x; colnames(broken)[1] <- "SYNTHETIC_UNKNOWN"
  stopifnot(inherits(try(validate_input(broken, samples), silent = TRUE), "try-error"))
  stopifnot(length(panel_symbols) == 14L, length(unique(panel_symbols)) == 14L)
  stopifnot(p.adjust(0.001, method = "BH", n = 84L) == 0.084)
  cat("GSE134780 public input and multiplicity self-tests passed\n")
  quit(status = 0)
}
if (length(args)) stop("Only --self-test is supported")
expected_sha <- "f12a73805eb3aaf95d666e78756def647a11e95e37bd007dda580bc08ec77cba"
input <- file.path(root, "public_data/GSE134780/counts.txt.gz")
if (!identical(digest(input, algo = "sha256", file = TRUE), expected_sha)) stop("count input hash mismatch")
source_record <- fromJSON(file.path(here, "sources.json"))
if (digest(file.path(here, "PROTOCOL.md"), algo = "sha256", file = TRUE) != source_record$protocol_sha256) stop("protocol lock mismatch")
x <- read.delim(gzfile(input), check.names = FALSE, stringsAsFactors = FALSE)
if (names(x)[1] != "gene_symbol" || anyDuplicated(x[[1]])) stop("gene-symbol input contract failed")
counts <- as.matrix(x[, -1, drop = FALSE]); rownames(counts) <- x[[1]]
samples <- read.delim(file.path(here, "samples.tsv"), check.names = FALSE)
validate_input(counts, samples)
out <- file.path(here, "release"); dir.create(out, recursive = TRUE, showWarnings = FALSE)
cache_out <- file.path(root, "public_data/GSE134780/full_results"); dir.create(cache_out, recursive = TRUE, showWarnings = FALSE)
write_tsv <- function(x, name) write.table(x, file.path(out, name), sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
warning_log <- character(); panel_rows <- list(); summaries <- list(); expression_rows <- list(); size_rows <- list()
contrasts <- list(c("HL1002P", "WT"), c("HH", "WT"), c("HL1002P", "HH"))
start <- proc.time()[["elapsed"]]
for (tissue in c("skM", "fat")) {
  sub <- samples[samples$tissue == tissue, , drop = FALSE]
  sub$genotype <- factor(sub$genotype, levels = c("WT", "HL1002P", "HH")); rownames(sub) <- sub$sample
  mat <- counts[, sub$sample, drop = FALSE]; keep <- rowSums(mat >= 10) >= 3
  dds <- DESeqDataSetFromMatrix(mat[keep, , drop = FALSE], sub, ~ genotype)
  dds <- withCallingHandlers(DESeq(dds, minReplicatesForReplace = Inf, quiet = TRUE), warning = function(w) {
    warning_log <<- c(warning_log, paste(tissue, conditionMessage(w))); invokeRestart("muffleWarning")
  })
  norm <- counts(dds, normalized = TRUE)
  size_rows[[tissue]] <- data.frame(sample = colnames(dds), tissue = tissue, size_factor = sizeFactors(dds))
  for (symbol in intersect(panel_symbols, rownames(norm))) {
    expression_rows[[length(expression_rows) + 1L]] <- data.frame(gene = symbol, sample = colnames(norm), tissue = tissue, normalized_count = as.numeric(norm[symbol, ]))
  }
  for (contrast in contrasts) {
    cname <- paste(contrast, collapse = "_minus_")
    result <- as.data.frame(results(dds, contrast = c("genotype", contrast), cooksCutoff = FALSE, independentFiltering = FALSE, alpha = 0.1))
    result$gene <- rownames(result)
    write.table(result, file.path(cache_out, paste0(tissue, "_", cname, ".tsv")), sep = "\t", row.names = FALSE, quote = FALSE)
    summaries[[length(summaries) + 1L]] <- data.frame(tissue = tissue, contrast = cname,
      n_numerator = sum(sub$genotype == contrast[1]), n_denominator = sum(sub$genotype == contrast[2]),
      genes_tested = sum(!is.na(result$pvalue)), converged_genes = sum(mcols(dds)$betaConv, na.rm = TRUE),
      supported_genes = sum(result$padj <= 0.1 & abs(result$log2FoldChange) >= log2(1.25), na.rm = TRUE))
    for (symbol in panel_symbols) {
      row <- result[match(symbol, result$gene), , drop = FALSE]
      panel_rows[[length(panel_rows) + 1L]] <- data.frame(tissue = tissue, contrast = cname, gene = symbol,
        status = ifelse(symbol %in% result$gene, "evaluated", "absent_or_filtered"),
        log2_fold_change = row$log2FoldChange, standard_error = row$lfcSE, pvalue = row$pvalue,
        transcriptome_qvalue = row$padj)
    }
  }
}
panel <- do.call(rbind, panel_rows)
stopifnot(nrow(panel) == 84L)
panel$panel_qvalue <- p.adjust(panel$pvalue, method = "BH", n = 84L)
panel$decision <- ifelse(is.na(panel$panel_qvalue), "UNEVALUABLE", ifelse(panel$panel_qvalue <= 0.10 & abs(panel$log2_fold_change) >= log2(1.25), "EXPRESSION_CONTEXT_ONLY", "NO_PANEL_SUPPORT"))
write_tsv(panel, "target_context_panel.tsv")
write_tsv(do.call(rbind, summaries), "contrast_summary.tsv")
write_tsv(do.call(rbind, expression_rows), "normalized_panel_expression.tsv")
write_tsv(do.call(rbind, size_rows), "size_factors.tsv")
write_tsv(samples, "samples.tsv")
writeLines(if (length(warning_log)) warning_log else "No fit warnings captured.", file.path(out, "fit_warnings.txt"))
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
metadata <- list(dataset = "GSE134780", analysis_date = as.character(Sys.Date()), samples = 23,
  panel_genes = panel_symbols, configured_panel_tests = 84, supported_panel_tests = sum(panel$decision == "EXPRESSION_CONTEXT_ONLY"),
  input_sha256 = expected_sha, protocol_sha256 = source_record$protocol_sha256,
  r_version = as.character(getRversion()), DESeq2_version = as.character(packageVersion("DESeq2")),
  warning_count = length(warning_log), wall_seconds = proc.time()[["elapsed"]] - start,
  claims = "Independent mouse allele/tissue expression context; no drug response, human replication, clinical inference, or rescue of fly null.")
write_json(metadata, file.path(out, "analysis_summary.json"), pretty = TRUE, auto_unbox = TRUE)
paths <- sort(setdiff(list.files(out), c("release_inventory.tsv", "release_inventory.sha256")))
inventory <- data.frame(path = paths, bytes = file.info(file.path(out, paths))$size,
  sha256 = vapply(file.path(out, paths), digest, character(1), algo = "sha256", file = TRUE))
write_tsv(inventory, "release_inventory.tsv")
writeLines(digest(file.path(out, "release_inventory.tsv"), algo = "sha256", file = TRUE), file.path(out, "release_inventory.sha256"))
cat(toJSON(metadata, auto_unbox = TRUE, pretty = TRUE), "\n")
