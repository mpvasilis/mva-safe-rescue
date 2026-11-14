gse_read_fly_reference <- function(repo_root, module_ids) {
  relative <- "analysis/track2/release/modules/preregistered_include_IEA.tsv"
  path <- file.path(repo_root, relative)
  expected_sha <- "34632d7e5d3a021b9e7064727b499be9a824350ad3dbb28cfaeb66d5da3a4283"
  gse_assert(file.exists(path), "Tracked fly module reference is missing: %s", relative)
  observed_sha <- gse_sha256(path)
  gse_assert(identical(observed_sha, expected_sha),
             "Tracked fly module reference checksum changed: %s", observed_sha)
  fly <- gse_read_tsv(path)
  fly <- fly[fly$module_id %in% module_ids, , drop = FALSE]
  fly <- fly[match(module_ids, fly$module_id), , drop = FALSE]
  gse_assert(nrow(fly) == 7L && !anyNA(fly$module_id), "Fly reference lacks a locked module")
  list(
    data = data.frame(module_id = fly$module_id, fly_nes = fly$nes,
                      fly_direction = gse_direction(fly$nes),
                      fly_module_qvalue = fly$module_qvalue, stringsAsFactors = FALSE),
    provenance = data.frame(
      source = relative, expected_sha256 = expected_sha, observed_sha256 = observed_sha,
      primary_evaluable_modules = 12L, primary_modules_q_le_0_10 = 0L,
      leave_one_block_out_direction_reversals = "folding_proteasome|oxidative_stress",
      usage = "descriptive_direction_comparison_only_no_pooling_no_rescue_claim",
      stringsAsFactors = FALSE
    )
  )
}

gse_compare_to_fly <- function(human_modules, fly) {
  out <- merge(human_modules[, c("lineage", "sensitivity", "module_id", "nes", "direction",
                                  "pvalue", "module_qvalue_BH_n7_authoritative")],
               fly, by = "module_id", all.x = TRUE, sort = FALSE)
  names(out)[names(out) == "nes"] <- "human_nes"
  names(out)[names(out) == "direction"] <- "human_direction"
  names(out)[names(out) == "pvalue"] <- "human_pvalue"
  names(out)[names(out) == "module_qvalue_BH_n7_authoritative"] <-
    "human_module_qvalue_BH_n7_authoritative"
  out$direction_concordant <- with(out, ifelse(
    human_direction %in% c("up", "down") & fly_direction %in% c("up", "down"),
    human_direction == fly_direction, NA
  ))
  out$comparison_scope <- "descriptive_only_no_pooled_statistic"
  out$primary_fly_null_preserved <- TRUE
  out <- out[order(match(out$lineage, c("NPC", "iPSC")),
                   match(out$sensitivity, c("full", "chr21_excluded")),
                   match(out$module_id, unique(human_modules$module_id))), ]
  rownames(out) <- NULL
  out
}

gse_make_figures <- function(pca, modules, figure_dir) {
  gse_assert(requireNamespace("ggplot2", quietly = TRUE), "Package 'ggplot2' is required")
  dir.create(figure_dir, recursive = TRUE, showWarnings = FALSE)
  pca_full <- pca[pca$sensitivity == "full", , drop = FALSE]
  p1 <- ggplot2::ggplot(pca_full, ggplot2::aes(x = PC1, y = PC2, color = condition)) +
    ggplot2::geom_hline(yintercept = 0, color = "grey88", linewidth = 0.3) +
    ggplot2::geom_vline(xintercept = 0, color = "grey88", linewidth = 0.3) +
    ggplot2::geom_point(size = 3) +
    ggplot2::geom_text(ggplot2::aes(label = replicate), vjust = -1.1, size = 3.2,
                       show.legend = FALSE) +
    ggplot2::facet_wrap(~ lineage, scales = "free") +
    ggplot2::scale_color_manual(values = c("Iso-E" = "#2878B5", "Iso-T" = "#D1495B")) +
    ggplot2::scale_y_continuous(expand = ggplot2::expansion(mult = c(0.08, 0.15))) +
    ggplot2::labs(title = "GSE185192 untreated isogenic RNA-seq PCA",
                  subtitle = "VST within lineage; labels are culture replicate numbers",
                  x = "PC1", y = "PC2", color = "Derivative") +
    ggplot2::theme_bw(base_size = 11) +
    ggplot2::theme(legend.position = "bottom", panel.grid.minor = ggplot2::element_blank())
  ggplot2::ggsave(file.path(figure_dir, "pca_by_lineage.png"), p1,
                  width = 8, height = 4.7, dpi = 160, bg = "white")

  modules$module_label <- factor(modules$module_id, levels = rev(unique(modules$module_id)))
  modules$lineage <- factor(modules$lineage, levels = c("NPC", "iPSC"))
  modules$sensitivity <- factor(modules$sensitivity,
                                levels = c("full", "chr21_excluded"))
  modules$plot_q <- ifelse(is.finite(modules$module_qvalue_BH_n7_authoritative),
                           pmin(-log10(pmax(
                             modules$module_qvalue_BH_n7_authoritative, 1e-4)), 4), 0)
  p2 <- ggplot2::ggplot(modules, ggplot2::aes(x = nes, y = module_label,
                                              color = direction, size = plot_q)) +
    ggplot2::geom_vline(xintercept = 0, color = "grey50", linewidth = 0.4) +
    ggplot2::geom_point(na.rm = TRUE) +
    ggplot2::facet_grid(lineage ~ sensitivity, scales = "free_x") +
    ggplot2::scale_color_manual(values = c("down" = "#2878B5", "up" = "#D1495B",
                                           "zero" = "grey50", "missing" = "grey75")) +
    ggplot2::scale_size_continuous(range = c(2, 6), name = expression(-log[10]("BH q"))) +
    ggplot2::labs(title = "Configured, original analysis-locked human module effects",
                  subtitle = "Competitive maxmean rotation; authoritative BH family n=7",
                  x = "Normalized enrichment score", y = NULL, color = "Direction") +
    ggplot2::theme_bw(base_size = 10) +
    ggplot2::theme(legend.position = "bottom", panel.grid.minor = ggplot2::element_blank())
  ggplot2::ggsave(file.path(figure_dir, "locked_module_effects.png"), p2,
                  width = 10, height = 7.2, dpi = 160, bg = "white")
  invisible(c("pca_by_lineage.png", "locked_module_effects.png"))
}

gse_release_readme <- function(summaries) {
  lookup <- function(lineage, sensitivity, column) {
    x <- summaries[summaries$lineage == lineage & summaries$sensitivity == sensitivity, column]
    if (length(x) != 1L) NA else x[[1L]]
  }
  c(
    "# GSE185192 external public challenge — release snapshot",
    "",
    "This small snapshot reports a fixed-seed, one-CPU reanalysis with deterministic settings and recorded software versions of public untreated HTSeq counts from [GEO GSE185192](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192). The priority contrast is NPC Iso-T versus Iso-E; untreated iPSC Iso-T versus Iso-E is a separate lineage control. The contrasts are never pooled. No lockfile or byte-identical cross-machine reproduction claim is made.",
    "",
    "The seven modules were configured and locked for this original external analysis before its authoritative run. They have no external preregistration timestamp and are not presented as externally preregistered. `locked_module_results.tsv` retains every configured row; `module_qvalue_BH_n7_authoritative` is the only decision q-value. The package-supplied evaluable-only adjustment is labeled nondecision and is not used in summaries or figures.",
    "",
    sprintf("NPC full analysis: %d retained genes, %d/7 locked modules at BH q <= 0.10. NPC chromosome-21-excluded sensitivity: %d retained genes, %d/7 modules at q <= 0.10.",
            lookup("NPC", "full", "retained_gene_rows"), lookup("NPC", "full", "modules_q_le_0_10"),
            lookup("NPC", "chr21_excluded", "retained_gene_rows"),
            lookup("NPC", "chr21_excluded", "modules_q_le_0_10")),
    sprintf("iPSC full analysis: %d retained genes, %d/7 locked modules at BH q <= 0.10. iPSC chromosome-21-excluded sensitivity: %d retained genes, %d/7 modules at q <= 0.10.",
            lookup("iPSC", "full", "retained_gene_rows"), lookup("iPSC", "full", "modules_q_le_0_10"),
            lookup("iPSC", "chr21_excluded", "retained_gene_rows"),
            lookup("iPSC", "chr21_excluded", "modules_q_le_0_10")),
    "",
    "## Non-negotiable inference boundary",
    "",
    "Iso-E and Iso-T are one isogenic derivative pair from AG05397. The three deposited count files per state are repeated cultures/libraries, not three independent donors. Genotype is perfectly confounded with derivative line, so DESeq2 p-values and rotation p-values are descriptive within this pair and cannot establish population-level replication.",
    "",
    "GSE185192 is a constitutive trisomy-21/Down-syndrome isogenic context. It is not MVA, not SAC depletion, and not evidence of ongoing chromosome mis-segregation or chromosomal instability. It is used only as an aneuploid neural-context stress test.",
    "",
    "This external analysis cannot rescue or override the primary fly null: zero of 12 evaluable primary modules reached BH q <= 0.10, and leave-one-block-out direction reversals occurred for folding/proteasome and oxidative-stress modules. Human-versus-fly comparison is sign/effect description only—there is no pooled statistic, meta-analysis, candidate nomination, clinical claim, or dosing guidance.",
    "",
    "## Reproduce and inspect",
    "",
    "Run `Rscript analysis/external/GSE185192/bootstrap.R`, then `Rscript analysis/external/GSE185192/run.R`. Use `--download-only`, `--test`, or `--verify-release` for the corresponding bounded operation. `GSE185192_CACHE_DIR` may override the default relative public cache. The run fixes seed 20260826, 9,999 rotations, and one CPU. DESeq2 uses `~ condition` with Iso-E as reference, Cook's-distance censoring disabled, automatic count replacement disabled, and independent filtering enabled.",
    "",
    paste0(
      "Inputs were retrieved on 2026-08-26–27 (exact per-source UTC timestamps are in the manifest) and are not redistributed in this snapshot. `manifests/sources.tsv` pins exact HTTPS URLs, byte counts, and SHA-256 values; `sample_eligibility.tsv` exposes every eligibility check. `gencode_mapping_audit.tsv` reports mapped, unmapped, ambiguous, and chromosome-21-excluded symbol counts. `package_versions.tsv` records the direct and key statistical packages used. `manifests/full_result_hashes.tsv` ties this compact release to the four exact ignored full-DE tables by relative path, byte count, and SHA-256. Review [NCBI policies](https://www.ncbi.nlm.nih.gov/",
      "home/about/policies/) and source-specific terms before reuse."
    ),
    "",
    "Primary sources and annotation references: [Meharena et al., Cell Stem Cell (PMC8805993)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8805993/), [versioned GO 2026-08-05 basic ontology](https://release.geneontology.org/2026-08-05/ontology/go-basic.obo), matching dated [GO 2026-08-05 HUMAN-UniProt GAF](https://release.geneontology.org/2026-08-05/annotations/gaf/HUMAN-uniprot.gaf.gz), and [GENCODE v19](https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_19/gencode.v19.annotation.gtf.gz).",
    "",
    "`release_inventory.tsv` hashes every snapshot artifact except itself; `release_inventory.sha256` hashes that inventory."
  )
}

gse_release_payload_paths <- function() {
  sort(c(
    "README.md", "analysis_summary.json", "sessionInfo.txt", "package_versions.tsv",
    "sample_eligibility.tsv", "library_totals.tsv", "module_construction.tsv",
    "annotation_summary.tsv", "gencode_mapping_audit.tsv", "size_factors.tsv",
    "pca_coordinates.tsv",
    "de_summary.tsv", "top_de_excerpt.tsv", "locked_module_results.tsv",
    "fly_direction_comparison.tsv", "figures/pca_by_lineage.png",
    "figures/locked_module_effects.png", "manifests/sources.tsv",
    "manifests/samples.tsv", "manifests/locked_modules.tsv",
    "manifests/source_verification.tsv", "manifests/fly_reference.tsv",
    "manifests/full_result_hashes.tsv"
  ))
}

gse_full_result_ids <- function() {
  c("NPC_full", "NPC_chr21_excluded", "iPSC_full", "iPSC_chr21_excluded")
}

gse_full_result_relative_paths <- function() {
  paste0("results/de/", gse_full_result_ids(), ".tsv.gz")
}

gse_validate_full_result_hashes <- function(manifest) {
  expected_names <- c("analysis_id", "result_path", "bytes", "sha256", "release_policy")
  gse_assert(identical(names(manifest), expected_names),
             "Full-result hash manifest schema is invalid")
  gse_assert(identical(manifest$analysis_id, gse_full_result_ids()),
             "Full-result analysis IDs/order are invalid")
  gse_assert(identical(manifest$result_path, gse_full_result_relative_paths()),
             "Full-result relative paths are invalid")
  bytes <- suppressWarnings(as.numeric(manifest$bytes))
  gse_assert(all(is.finite(bytes) & bytes > 0 & bytes == floor(bytes)),
             "Full-result byte counts must be positive integers")
  gse_assert(all(grepl("^[0-9a-f]{64}$", manifest$sha256)),
             "Full-result SHA-256 values are invalid")
  gse_assert(all(manifest$release_policy == "ignored_full_table_hash_only_not_redistributed"),
             "Full-result release policy changed")
  invisible(TRUE)
}

gse_full_result_hashes <- function(results_dir) {
  result_paths <- file.path(results_dir, "de", paste0(gse_full_result_ids(), ".tsv.gz"))
  gse_assert(all(file.exists(result_paths)), "An authoritative full-DE table is missing")
  gse_assert(!any(nzchar(Sys.readlink(result_paths))),
             "Symlinked full-DE tables are forbidden")
  manifest <- data.frame(
    analysis_id = gse_full_result_ids(),
    result_path = gse_full_result_relative_paths(),
    bytes = unname(file.info(result_paths)$size),
    sha256 = vapply(result_paths, gse_sha256, character(1L)),
    release_policy = "ignored_full_table_hash_only_not_redistributed",
    stringsAsFactors = FALSE
  )
  gse_validate_full_result_hashes(manifest)
  manifest
}

gse_verify_local_full_results_if_present <- function(release_dir, manifest) {
  gse_validate_full_result_hashes(manifest)
  project_dir <- dirname(release_dir)
  result_paths <- file.path(project_dir, manifest$result_path)
  present <- file.exists(result_paths)
  gse_assert(!any(present) || all(present),
             "Only part of the four local full-DE tables is present")
  if (!all(present)) return(invisible(TRUE))
  gse_assert(!any(nzchar(Sys.readlink(result_paths))),
             "Symlinked local full-DE tables are forbidden")
  gse_assert(all(unname(file.info(result_paths)$size) == as.numeric(manifest$bytes)),
             "Local full-DE byte count differs from release manifest")
  observed <- vapply(result_paths, gse_sha256, character(1L))
  gse_assert(identical(unname(observed), unname(manifest$sha256)),
             "Local full-DE checksum differs from release manifest")
  invisible(TRUE)
}

gse_package_versions <- function() {
  packages <- c("BiocManager", "digest", "fs", "jsonlite", "ggplot2", "DESeq2", "roastgsa",
                "SummarizedExperiment", "BiocParallel", "limma")
  roles <- c(
    "Bioconductor release resolver", "SHA-256 implementation",
    "release symlink and Windows reparse-point detection", "JSON serialization",
    "figure generation", "gene-level negative-binomial modeling",
    "competitive rotation gene-set testing", "VST assay extraction",
    "explicit serial execution registration", "key roastgsa statistical dependency"
  )
  gse_assert(all(vapply(packages, requireNamespace, logical(1L), quietly = TRUE)),
             "A package required for provenance is unavailable")
  data.frame(
    component = c("R", "Bioconductor", packages),
    role = c("runtime", "biostatistics release", roles),
    version = c(R.version.string, as.character(BiocManager::version()),
                vapply(packages, function(package) {
                  as.character(utils::packageVersion(package))
                }, character(1L))),
    stringsAsFactors = FALSE
  )
}

gse_release_all_paths <- function() {
  sort(c(gse_release_payload_paths(), "release_inventory.tsv", "release_inventory.sha256"))
}

gse_release_existing_paths <- function(release_dir) {
  if (!dir.exists(release_dir)) return(character())
  files <- list.files(release_dir, recursive = TRUE, full.names = TRUE, all.files = TRUE,
                      no.. = TRUE)
  files <- files[file.info(files)$isdir %in% FALSE]
  if (!length(files)) return(character())
  prefix <- normalizePath(release_dir, winslash = "/", mustWork = TRUE)
  sort(substring(normalizePath(files, winslash = "/", mustWork = TRUE), nchar(prefix) + 2L))
}

gse_assert_no_release_symlinks <- function(release_dir) {
  if (!dir.exists(release_dir)) return(invisible(TRUE))
  gse_assert(requireNamespace("fs", quietly = TRUE),
             "Package 'fs' is required for reparse-point-safe release verification")
  entries <- list.files(release_dir, recursive = TRUE, full.names = TRUE, all.files = TRUE,
                        no.. = TRUE, include.dirs = TRUE)
  entries <- unique(c(release_dir, entries))
  links <- entries[nzchar(Sys.readlink(entries)) | fs::is_link(entries)]
  gse_assert(!length(links), "Symlinked or reparse-point release entry is forbidden: %s",
             paste(basename(links), collapse = ", "))
  invisible(TRUE)
}

gse_assert_no_stale_release_files <- function(release_dir) {
  gse_assert_no_release_symlinks(release_dir)
  stale <- setdiff(gse_release_existing_paths(release_dir), gse_release_all_paths())
  gse_assert(!length(stale),
             "Unexpected stale release file(s); remove after review before refresh: %s",
             paste(stale, collapse = ", "))
  invisible(TRUE)
}

gse_validate_inventory_table <- function(inventory) {
  gse_assert(identical(names(inventory), c("path", "bytes", "sha256")),
             "Release inventory schema is invalid")
  gse_assert(nrow(inventory) > 0L && !anyDuplicated(inventory$path),
             "Release inventory paths must be nonempty and unique")
  bytes <- suppressWarnings(as.numeric(inventory$bytes))
  gse_assert(all(is.finite(bytes) & bytes >= 0 & bytes == floor(bytes)),
             "Release inventory byte counts must be nonnegative integers")
  gse_assert(all(grepl("^[0-9a-f]{64}$", inventory$sha256)),
             "Release inventory SHA-256 values are invalid")
  unsafe <- !nzchar(inventory$path) | grepl("^[A-Za-z]:|^/|^\\\\", inventory$path) |
    grepl("(^|/)\\.\\.(/|$)", inventory$path) | grepl("\\\\", inventory$path) |
    basename(inventory$path) %in% c("release_inventory.tsv", "release_inventory.sha256")
  gse_assert(!any(unsafe), "Unsafe release inventory path(s): %s",
             paste(inventory$path[unsafe], collapse = ", "))
  gse_assert(identical(sort(inventory$path), gse_release_payload_paths()),
             "Inventory rows differ from explicit release whitelist")
  invisible(TRUE)
}

gse_write_inventory <- function(release_dir) {
  gse_assert_no_stale_release_files(release_dir)
  existing_payload <- setdiff(gse_release_existing_paths(release_dir),
                              c("release_inventory.tsv", "release_inventory.sha256"))
  expected_payload <- gse_release_payload_paths()
  gse_assert(identical(existing_payload, expected_payload),
             "Release payload differs from explicit whitelist; missing=%s extras=%s",
             paste(setdiff(expected_payload, existing_payload), collapse = "|"),
             paste(setdiff(existing_payload, expected_payload), collapse = "|"))
  files <- file.path(release_dir, expected_payload)
  inventory <- data.frame(path = expected_payload, bytes = unname(file.info(files)$size),
                          sha256 = vapply(files, gse_sha256, character(1L)), stringsAsFactors = FALSE)
  inventory_path <- file.path(release_dir, "release_inventory.tsv")
  gse_write_tsv(inventory, inventory_path)
  writeLines(paste(gse_sha256(inventory_path), "release_inventory.tsv"),
             file.path(release_dir, "release_inventory.sha256"), useBytes = TRUE)
  invisible(inventory)
}

gse_verify_release <- function(release_dir) {
  inventory_path <- file.path(release_dir, "release_inventory.tsv")
  sha_path <- file.path(release_dir, "release_inventory.sha256")
  gse_assert(file.exists(inventory_path) && file.exists(sha_path), "Release inventory is incomplete")
  inventory <- gse_read_tsv(inventory_path)
  gse_validate_inventory_table(inventory)
  gse_assert_no_release_symlinks(release_dir)
  actual_files <- list.files(release_dir, recursive = TRUE, full.names = TRUE,
                             all.files = TRUE, no.. = TRUE)
  actual_files <- actual_files[file.info(actual_files)$isdir %in% FALSE]
  release_prefix <- normalizePath(release_dir, winslash = "/", mustWork = TRUE)
  actual_relative <- substring(normalizePath(actual_files, winslash = "/", mustWork = TRUE),
                               nchar(release_prefix) + 2L)
  expected_relative <- gse_release_all_paths()
  extras <- setdiff(actual_relative, expected_relative)
  missing_listed <- setdiff(expected_relative, actual_relative)
  gse_assert(!length(extras) && !length(missing_listed),
             "Release file set differs from inventory; extras=%s missing=%s",
             paste(extras, collapse = "|"), paste(missing_listed, collapse = "|"))
  for (i in seq_len(nrow(inventory))) {
    path <- file.path(release_dir, inventory$path[[i]])
    gse_assert(!nzchar(Sys.readlink(path)), "Symlink is forbidden in release: %s",
               inventory$path[[i]])
    gse_assert(file.exists(path), "Release artifact missing: %s", inventory$path[[i]])
    gse_assert(unname(file.info(path)$size) == as.numeric(inventory$bytes[[i]]),
               "Release byte mismatch: %s", inventory$path[[i]])
    gse_assert(identical(gse_sha256(path), inventory$sha256[[i]]),
               "Release checksum mismatch: %s", inventory$path[[i]])
  }
  sha_lines <- readLines(sha_path, warn = FALSE, encoding = "UTF-8")
  gse_assert(length(sha_lines) == 1L &&
               grepl("^[0-9a-f]{64} release_inventory\\.tsv$", sha_lines[[1L]]),
             "Inventory checksum sidecar schema is invalid")
  recorded <- strsplit(sha_lines[[1L]], " ", fixed = TRUE)[[1L]][[1L]]
  gse_assert(identical(gse_sha256(inventory_path), recorded), "Inventory checksum mismatch")
  tsvs <- list.files(release_dir, pattern = "\\.tsv$", recursive = TRUE, full.names = TRUE)
  invisible(lapply(tsvs, gse_assert_rectangular_tsv))
  full_result_manifest <- gse_read_tsv(
    file.path(release_dir, "manifests", "full_result_hashes.tsv")
  )
  gse_verify_local_full_results_if_present(release_dir, full_result_manifest)
  text_files <- list.files(release_dir, pattern = "\\.(tsv|json|txt|md|sha256)$",
                           recursive = TRUE, full.names = TRUE)
  absolute_roots <- paste0("/", c("home", "Users", "mnt", "tmp"), "/")
  absolute_path_pattern <- sprintf(
    "(^|[^A-Za-z0-9])([A-Za-z]:[/\\\\]|%s)",
    paste(absolute_roots, collapse = "|")
  )
  absolute_path_hits <- vapply(text_files, function(path) {
    text <- paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
    grepl(absolute_path_pattern, text, perl = TRUE)
  }, logical(1L))
  gse_assert(!any(absolute_path_hits), "Absolute local path found in release text: %s",
             paste(basename(text_files[absolute_path_hits]), collapse = ", "))
  TRUE
}

gse_json_records <- function(x) {
  gse_assert(is.data.frame(x), "JSON record input must be a data frame")
  rownames(x) <- NULL
  unname(lapply(seq_len(nrow(x)), function(i) {
    stats::setNames(lapply(x, function(column) column[[i]]), names(x))
  }))
}

gse_analysis_summary <- function(summaries, mapping_audit) {
  list(
    schema_version = "1.0", dataset = "GSE185192", seed = 20260826L,
    one_cpu = TRUE, priority_contrast = "NPC_Iso-T_vs_Iso-E",
    lineage_control = "iPSC_Iso-T_vs_Iso-E", pooled_analysis = FALSE,
    isogenic_derivative_pairs = 1L, independent_donor_replication = FALSE,
    lockfile_present = FALSE, byte_identical_cross_machine_reproduction_claim = FALSE,
    genotype_derivative_line_confound = TRUE,
    external_analysis_scope = "descriptive_within_one_isogenic_derivative_pair",
    disease_context_boundary = paste(
      "Constitutive trisomy-21/Down-syndrome isogenic context only; not MVA, not SAC",
      "depletion, and not evidence of ongoing chromosome mis-segregation or CIN."
    ),
    configured_original_analysis_locked_modules = 7L,
    externally_preregistered = FALSE,
    external_preregistration_timestamp = NA_character_,
    module_lock_provenance = paste(
      "Configured and locked for this original external analysis before the authoritative run;",
      "not presented as externally preregistered."
    ),
    authoritative_module_qvalue = "module_qvalue_BH_n7_authoritative",
    nondecision_adjustment = "roastgsa_adj_pvalue_evaluable_only_nondecision",
    gene_filter = "count_at_least_10_in_at_least_3_samples_within_each_analysis",
    deseq2_options = list(design = "~ condition", reference = "Iso-E",
                          cooks_cutoff = FALSE, independent_filtering = TRUE,
                          min_replicates_for_replace = "Inf"),
    module_testing = list(method = "roastgsa_competitive_maxmean_on_VST",
                          rotations = 9999L, authoritative_BH_family_size = 7L),
    full_de_result_hash_manifest = "manifests/full_result_hashes.tsv",
    gencode_mapping_audit = gse_json_records(mapping_audit),
    external_results = gse_json_records(summaries),
    primary_fly_context = list(evaluable_modules = 12L, modules_q_le_0_10 = 0L,
                               leave_one_block_out_downgrade_required = TRUE,
                               direction_reversals = c("folding_proteasome",
                                                       "oxidative_stress")),
    claim_boundary = paste(
      "External GSE185192 results do not rescue the primary 0/12 module null, establish",
      "population replication, validate a drug/candidate, or support any clinical or dosing claim."
    )
  )
}

gse_write_outputs <- function(project_dir, repo_root, sources, samples, modules_config,
                              source_verification, eligibility, imported, annotations, analyses) {
  results_dir <- file.path(project_dir, "results")
  release_dir <- file.path(project_dir, "release")
  dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
  dir.create(release_dir, recursive = TRUE, showWarnings = FALSE)
  gse_assert_no_stale_release_files(release_dir)
  names(analyses) <- c("NPC_full", "NPC_chr21_excluded", "iPSC_full", "iPSC_chr21_excluded")
  for (name in names(analyses)) {
    gse_write_tsv_gz(analyses[[name]]$de, file.path(results_dir, "de", paste0(name, ".tsv.gz")))
  }
  full_result_hashes <- gse_full_result_hashes(results_dir)
  human_modules <- do.call(rbind, lapply(analyses, `[[`, "modules"))
  summaries <- do.call(rbind, lapply(analyses, `[[`, "summary"))
  pca <- do.call(rbind, lapply(analyses, `[[`, "pca"))
  top <- do.call(rbind, lapply(analyses, `[[`, "top"))
  size_factors <- do.call(rbind, lapply(analyses, `[[`, "size_factors"))
  fly <- gse_read_fly_reference(repo_root, modules_config$module_id)
  comparison <- gse_compare_to_fly(human_modules, fly$data)
  mapping_audit <- gse_gencode_mapping_audit(rownames(imported$counts),
                                             annotations$chromosomes)
  package_versions <- gse_package_versions()

  manifest_dir <- file.path(release_dir, "manifests")
  gse_write_tsv(sources, file.path(manifest_dir, "sources.tsv"))
  gse_write_tsv(samples, file.path(manifest_dir, "samples.tsv"))
  gse_write_tsv(modules_config, file.path(manifest_dir, "locked_modules.tsv"))
  gse_write_tsv(source_verification, file.path(manifest_dir, "source_verification.tsv"))
  gse_write_tsv(fly$provenance, file.path(manifest_dir, "fly_reference.tsv"))
  gse_write_tsv(full_result_hashes, file.path(manifest_dir, "full_result_hashes.tsv"))
  gse_write_tsv(eligibility, file.path(release_dir, "sample_eligibility.tsv"))
  gse_write_tsv(imported$library_totals, file.path(release_dir, "library_totals.tsv"))
  gse_write_tsv(annotations$modules$audit, file.path(release_dir, "module_construction.tsv"))
  gse_write_tsv(annotations$ontology_summary, file.path(release_dir, "annotation_summary.tsv"))
  gse_write_tsv(mapping_audit, file.path(release_dir, "gencode_mapping_audit.tsv"))
  gse_write_tsv(package_versions, file.path(release_dir, "package_versions.tsv"))
  gse_write_tsv(size_factors, file.path(release_dir, "size_factors.tsv"))
  gse_write_tsv(pca, file.path(release_dir, "pca_coordinates.tsv"))
  gse_write_tsv(summaries, file.path(release_dir, "de_summary.tsv"))
  gse_write_tsv(top, file.path(release_dir, "top_de_excerpt.tsv"))
  gse_write_tsv(human_modules, file.path(release_dir, "locked_module_results.tsv"))
  gse_write_tsv(comparison, file.path(release_dir, "fly_direction_comparison.tsv"))
  gse_make_figures(pca, human_modules, file.path(release_dir, "figures"))

  summary_json <- gse_analysis_summary(summaries, mapping_audit)
  jsonlite::write_json(summary_json, file.path(release_dir, "analysis_summary.json"),
                       pretty = TRUE, auto_unbox = TRUE, na = "null", digits = 15)
  capture.output(utils::sessionInfo(), file = file.path(release_dir, "sessionInfo.txt"))
  writeLines(gse_release_readme(summaries), file.path(release_dir, "README.md"), useBytes = TRUE)
  gse_write_inventory(release_dir)
  gse_assert(gse_verify_release(release_dir), "Release verification failed")
  list(summaries = summaries, modules = human_modules, comparison = comparison,
       release_dir = release_dir)
}
