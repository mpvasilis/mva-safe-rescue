testthat::test_that("primary call requires q, shrunken magnitude, and 2-of-3 raw directions", {
  ids <- c("FBgn0000001", "FBgn0000002")
  unshrunk <- data.frame(baseMean = c(100, 100), log2FoldChange = c(1, 1),
                         lfcSE = c(0.2, 0.2), stat = c(5, 5), pvalue = c(1e-5, 1e-5),
                         padj = c(0.05, 0.05), row.names = ids)
  shrunk <- data.frame(baseMean = c(100, 100), log2FoldChange = c(1, 0.1),
                       lfcSE = c(0.2, 0.2), row.names = ids)
  samples <- sample_manifest[sample_manifest$dataset == "GSE290206", , drop = FALSE]
  raw <- matrix(as.integer(c(10, 30, 10, 30, 30, 10,
                             10, 30, 10, 30, 10, 30)), nrow = 2L, byrow = TRUE,
                dimnames = list(ids, samples$sample_id))
  model <- list(unshrunk = unshrunk, shrunk = shrunk, normalized_counts = raw)
  out <- track2_de_table(model, raw, samples, "control", "CIN", primary_thresholds = TRUE)
  testthat::expect_true(out$passes_primary_threshold[[1L]])
  testthat::expect_false(out$passes_primary_threshold[[2L]])
  testthat::expect_identical(out$raw_direction_agreement_n, c(2L, 3L))
})

testthat::test_that("GO descendants traverse only registered is_a/part_of edges", {
  graph <- list(
    terms = data.frame(go_id = c("GO:0000001", "GO:0000002", "GO:0000003")),
    edges = data.frame(child = c("GO:0000002", "GO:0000003"),
                       parent = c("GO:0000001", "GO:0000002"),
                       relation = c("is_a", "part_of"))
  )
  testthat::expect_setequal(track2_go_descendants(graph, "GO:0000001"),
                            c("GO:0000001", "GO:0000002", "GO:0000003"))
})

testthat::test_that("orthology weights split co-best ties and sensitivity uses DIOPT shares", {
  orthologs <- data.frame(
    flybase_gene_id = c("FBgn0000001", "FBgn0000001", "FBgn0000001", "FBgn0000002"),
    fly_gene_symbol = c("a", "a", "a", "b"),
    human_hgnc_id = c("HGNC:1", "HGNC:2", "HGNC:3", "HGNC:1"),
    human_omim_id = "", human_gene_symbol = c("H1", "H2", "H3", "H1"),
    diopt_score = c(7L, 7L, 3L, 5L), omim_phenotype_ids = "", omim_phenotype_names = "",
    stringsAsFactors = FALSE
  )
  weighted <- track2_orthology_weights(orthologs)
  testthat::expect_equal(weighted$primary_max_tie_weight, c(0.5, 0.5, 0, 1))
  testthat::expect_equal(sum(weighted$sensitivity_diopt_weight[1:3]), 1)
})

testthat::test_that("weighted Stouffer denominator is sqrt sum of squared mapping weights", {
  mapping <- data.frame(
    flybase_gene_id = c("FBgn0000001", "FBgn0000002"),
    human_hgnc_id = c("HGNC:1", "HGNC:1"), human_gene_symbol = c("H1", "H1"),
    w = c(0.5, 1), stringsAsFactors = FALSE
  )
  de <- data.frame(flybase_gene_id = mapping$flybase_gene_id, wald_stat = c(2, -1))
  out <- track2_weighted_stouffer(mapping, de, "w", "unit test")$signature
  testthat::expect_equal(out$stouffer_denominator, sqrt(1.25))
  testthat::expect_equal(out$weighted_stouffer_stat, 0)
})

testthat::test_that("orthology policy sensitivity reports global and top-rank robustness", {
  primary <- data.frame(
    human_hgnc_id = paste0("HGNC:", 1:3),
    weighted_stouffer_stat = c(3, 2, 1),
    stringsAsFactors = FALSE
  )
  sensitivity <- data.frame(
    human_hgnc_id = paste0("HGNC:", 1:4),
    weighted_stouffer_stat = c(2.8, -1.5, 1.1, 0.2),
    stringsAsFactors = FALSE
  )
  out <- track2_compare_orthology_policies(primary, sensitivity, top_n = 2L)
  testthat::expect_identical(out$primary_human_genes, 3L)
  testthat::expect_identical(out$sensitivity_human_genes, 4L)
  testthat::expect_identical(out$shared_human_genes, 3L)
  testthat::expect_equal(out$shared_score_sign_concordance, 2 / 3)
  testthat::expect_identical(out$top_absolute_score_overlap, 2L)
  testthat::expect_match(out$interpretation, "mapping-dependent")
})

testthat::test_that("large audit tables use reproducible gzip TSV output", {
  value <- data.frame(id = c("a", "b"), score = c(1.25, -2.5))
  first <- tempfile(fileext = ".tsv.gz")
  second <- tempfile(fileext = ".tsv.gz")
  on.exit(unlink(c(first, second), force = TRUE), add = TRUE)
  track2_atomic_write_tsv_gz(value, first)
  track2_atomic_write_tsv_gz(value, second)
  testthat::expect_identical(track2_sha256(first), track2_sha256(second))
  header <- readBin(first, what = "raw", n = 8L)
  testthat::expect_identical(as.integer(header[5:8]), rep(0L, 4L))
  testthat::expect_equal(utils::read.delim(gzfile(first)), value)
})

testthat::test_that("module direction-driver diagnostic is deterministic and direction-specific", {
  de <- data.frame(
    flybase_gene_id = paste0("g", 1:10),
    wald_stat = c(10, 9, 8, 7, 6, -20, -19, -18, -17, -16),
    stringsAsFactors = FALSE
  )
  testthat::expect_identical(
    track2_direction_driver_set(de, de$flybase_gene_id, direction = 1, fraction = 0.20),
    "g1"
  )
  testthat::expect_identical(
    track2_direction_driver_set(de, de$flybase_gene_id, direction = -1, fraction = 0.40),
    c("g6", "g7")
  )
})

testthat::test_that("module downgrade flags reversal and single-block dependence", {
  reversal <- track2_module_stability_flags(1.2, -0.4, 0.3, 0.5)
  testthat::expect_true(unname(reversal[["direction_reversal"]]))
  testthat::expect_false(unname(reversal[["single_block_dependence"]]))
  dependent <- track2_module_stability_flags(-1.2, -0.2, 0.04, 0.4)
  testthat::expect_false(unname(dependent[["direction_reversal"]]))
  testthat::expect_true(unname(dependent[["single_block_dependence"]]))
})

testthat::test_that("module exports distinguish authoritative and evaluable-only adjustments", {
  module <- data.frame(module_id = "m", adj.pval = 0.02, module_qvalue = 0.05,
                       check.names = FALSE)
  exported <- track2_module_export(module)
  testthat::expect_false("adj.pval" %in% names(exported))
  testthat::expect_true("roastgsa_adj_pvalue_evaluable_only" %in% names(exported))
  testthat::expect_identical(exported$module_qvalue, 0.05)
})

testthat::test_that("annotation-policy direction flips remain descriptive when both null", {
  primary <- data.frame(module_id = "folding_proteasome", nes = -1.2,
                        module_qvalue = 0.70)
  no_iea <- data.frame(module_id = "folding_proteasome", nes = 1.4,
                       module_qvalue = 0.43)
  out <- track2_annotation_policy_summary(primary, no_iea)
  testthat::expect_true(out$direction_flip)
  testthat::expect_false(out$include_IEA_supported_q_le_0_10)
  testthat::expect_false(out$exclude_IEA_supported_q_le_0_10)
  testthat::expect_match(out$interpretation, "both policies are null")
})

testthat::test_that("sanity symbols require exactly one case-insensitive gene-map hit", {
  unique_map <- data.frame(
    gene_symbol = c("Bub3", "other"),
    flybase_gene_id = c("FBgn0000001", "FBgn0000002")
  )
  testthat::expect_identical(track2_unique_symbol_indices("bub3", unique_map), 1L)
  ambiguous <- rbind(unique_map, data.frame(gene_symbol = "bUb3", flybase_gene_id = "FBgn0000003"))
  testthat::expect_error(track2_unique_symbol_indices("bub3", ambiguous), "bub3\\(n=2\\)")
  testthat::expect_error(track2_unique_symbol_indices("missing", unique_map), "missing\\(n=0\\)")
})

testthat::test_that("normalized direction sensitivity does not replace the locked raw gate", {
  de <- data.frame(
    flybase_gene_id = c("g1", "g2"),
    padj = c(0.01, 0.01),
    log2FoldChange_shrunken = c(1, 1),
    raw_direction_agreement_n = c(2L, 2L),
    passes_primary_threshold = c(TRUE, TRUE),
    within_batch_normalized_log2fc_4 = c(1, 1),
    within_batch_normalized_log2fc_5 = c(1, -1),
    within_batch_normalized_log2fc_6 = c(-1, -1)
  )
  out <- track2_direction_gate_sensitivity(de)
  testthat::expect_identical(out$gene_results$normalized_gate_sensitivity_call,
                             c(TRUE, FALSE))
  testthat::expect_identical(out$gene_results$locked_raw_gate_call, c(TRUE, TRUE))
  testthat::expect_identical(out$summary$locked_raw_only_candidates, 1L)
})

testthat::test_that("unshrunk LOO diagnostics must cover finite genes in every omission", {
  valid <- data.frame(
    omitted_batch = c("4", "5", "6"),
    n_genes_compared_unshrunk = c(100L, 100L, 100L),
    spearman_unshrunk_lfc_vs_full = c(0.8, 0.7, 0.9),
    direction_concordance_all_unshrunk = c(0.8, 0.75, 0.9)
  )
  testthat::expect_invisible(track2_validate_unshrunk_loo_summary(valid))
  invalid <- valid
  invalid$n_genes_compared_unshrunk[[3L]] <- 0L
  invalid$spearman_unshrunk_lfc_vs_full[[3L]] <- NA_real_
  testthat::expect_error(track2_validate_unshrunk_loo_summary(invalid),
                         "omitted batch\\(es\\): 6")
})

testthat::test_that("release refresh is deterministic and excludes bulky artifacts", {
  base <- tempfile("track2-release-test-")
  results <- file.path(base, "track2", "results")
  release <- file.path(base, "track2", "release")
  dir.create(results, recursive = TRUE)
  dir.create(release, recursive = TRUE)
  on.exit(unlink(base, recursive = TRUE, force = TRUE), add = TRUE)
  relative <- track2_release_result_paths()
  for (path in relative) {
    destination <- file.path(results, path)
    dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
    writeBin(charToRaw(paste0("fixture:", path, "\n")), destination)
  }
  readme <- file.path(release, "README.md")
  writeBin(charToRaw("release fixture\n"), readme)
  first <- track2_refresh_release(results, release, readme)
  first_hashes <- stats::setNames(vapply(first, track2_sha256, character(1L)), basename(first))
  second <- track2_refresh_release(results, release, readme)
  second_hashes <- stats::setNames(vapply(second, track2_sha256, character(1L)), basename(second))
  testthat::expect_identical(first_hashes, second_hashes)
  inventory <- utils::read.delim(file.path(release, "release_inventory.tsv"))
  testthat::expect_false(any(grepl("human_signature|all_mapping_audit|_full\\.tsv$",
                                  inventory$path)))
  testthat::expect_false(any(grepl("^[A-Za-z]:[/\\\\]", inventory$path)))
  expected_inventory_hash <- strsplit(
    readLines(file.path(release, "release_inventory.sha256"), warn = FALSE), "  ", fixed = TRUE
  )[[1L]][[1L]]
  testthat::expect_identical(track2_sha256(file.path(release, "release_inventory.tsv")),
                             expected_inventory_hash)
  testthat::expect_invisible(track2_verify_release(results, release))

  writeBin(charToRaw("unexpected\n"), file.path(release, "unexpected.txt"))
  testthat::expect_error(track2_verify_release(results, release),
                         "exact whitelist")
  unlink(file.path(release, "unexpected.txt"), force = TRUE)

  tampered <- file.path(release, relative[[1L]])
  writeBin(charToRaw("tampered\n"), tampered)
  testthat::expect_error(track2_verify_release(results, release),
                         "SHA-256 mismatch")
  testthat::expect_true(length(track2_refresh_release(results, release, readme)) > 0L)
  testthat::expect_invisible(track2_verify_release(results, release))
})

testthat::test_that("explicit package provenance covers declared statistical packages", {
  versions <- track2_package_versions()
  testthat::expect_setequal(
    c("R", "Bioconductor", "targets", "testthat", "readxl", "digest",
      "jsonlite", "ggplot2", "data.table", "DESeq2", "apeglm", "roastgsa",
      "SummarizedExperiment", "limma", "BiocManager"),
    versions$component
  )
  testthat::expect_true(all(nzchar(versions$version)))
  testthat::expect_identical(
    versions$version[versions$component == "Bioconductor"], "3.23"
  )
})
