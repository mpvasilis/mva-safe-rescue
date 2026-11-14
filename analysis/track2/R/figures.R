track2_save_plot <- function(plot, path, width = 8, height = 5) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  ggplot2::ggsave(path, plot = plot, width = width, height = height,
                  units = "in", dpi = 160, bg = "white")
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_make_figures <- function(results_dir, qc_payload, primary_de, module_primary,
                                leave_one_out, module_leave_one_out, exploratory) {
  track2_assert(requireNamespace("ggplot2", quietly = TRUE),
                "Package 'ggplot2' is required. Run bootstrap.R.")
  fig_dir <- file.path(results_dir, "figures")
  dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)
  paths <- character()

  pca <- qc_payload$primary$pca
  pc1_pct <- round(100 * pca$PC1_variance[[1L]], 1)
  pc2_pct <- round(100 * pca$PC2_variance[[1L]], 1)
  pca$label_x <- pca$PC1 + ifelse(pca$PC1 < -15, 2.2,
                                  ifelse(pca$PC1 > 15, -2.2, 1.3))
  pca$label_y <- pca$PC2 + ifelse(pca$sample_id == "1224_2024", 2.4,
                                  ifelse(pca$sample_id == "1225_2024", -2.4, 1.6))
  pca$label_hjust <- ifelse(pca$PC1 > 15, 1, 0)
  p <- ggplot2::ggplot(pca, ggplot2::aes(PC1, PC2, color = condition, shape = batch, label = sample_id)) +
    ggplot2::geom_point(size = 3) +
    ggplot2::geom_text(ggplot2::aes(x = label_x, y = label_y, hjust = label_hjust),
                       show.legend = FALSE, size = 3) +
    ggplot2::scale_x_continuous(expand = ggplot2::expansion(mult = c(0.15, 0.15))) +
    ggplot2::scale_y_continuous(expand = ggplot2::expansion(mult = c(0.12, 0.12))) +
    ggplot2::coord_cartesian(clip = "off") +
    ggplot2::labs(title = "GSE290206 VST quality-control PCA",
                  subtitle = "VST is used only for QC and rotation-based module testing",
                  x = sprintf("PC1 (%.1f%%)", pc1_pct), y = sprintf("PC2 (%.1f%%)", pc2_pct)) +
    ggplot2::theme_bw() +
    ggplot2::theme(plot.margin = ggplot2::margin(8, 18, 8, 18))
  paths <- c(paths, track2_save_plot(p, file.path(fig_dir, "primary_vst_pca.png")))

  volcano <- primary_de
  volcano$minus_log10_padj <- -log10(pmax(volcano$padj, .Machine$double.xmin))
  volcano$primary_call <- ifelse(volcano$passes_primary_threshold, "passes all criteria", "other")
  p <- ggplot2::ggplot(volcano, ggplot2::aes(log2FoldChange_shrunken, minus_log10_padj,
                                             color = primary_call)) +
    ggplot2::geom_point(alpha = 0.55, size = 1.2, na.rm = TRUE) +
    ggplot2::geom_vline(xintercept = c(-log2(1.25), log2(1.25)), linetype = 2) +
    ggplot2::scale_color_manual(values = c("other" = "grey65", "passes all criteria" = "#A33A2B")) +
    ggplot2::labs(title = "Primary CIN-versus-control transcriptome",
                  subtitle = "BH q<=0.10, shrunken fold-change magnitude >=1.25x, raw direction agreement in >=2/3 batches",
                  x = "apeglm shrunken log2 fold change", y = "-log10(BH q)", color = NULL) +
    ggplot2::theme_bw()
  paths <- c(paths, track2_save_plot(p, file.path(fig_dir, "primary_volcano.png")))

  modules <- module_primary
  modules$module_id <- factor(modules$module_id, levels = rev(modules$module_id))
  p <- ggplot2::ggplot(modules, ggplot2::aes(nes, module_id, color = module_qvalue <= 0.10)) +
    ggplot2::geom_vline(xintercept = 0, color = "grey70") +
    ggplot2::geom_point(size = 2.7, na.rm = TRUE) +
    ggplot2::scale_color_manual(values = c(`TRUE` = "#A33A2B", `FALSE` = "#365F91"), na.value = "grey70") +
    ggplot2::labs(title = "Original analysis-locked GO modules",
                  subtitle = "roastgsa maxmean, 9,999 rotations; IEA included; BH across 13 modules",
                  x = "Normalized enrichment score", y = NULL, color = "q<=0.10") +
    ggplot2::theme_bw()
  paths <- c(paths, track2_save_plot(p, file.path(fig_dir, "primary_modules.png"), height = 6.5))

  loo <- leave_one_out$summary
  reversal_rows <- module_leave_one_out$module_summary[
    module_leave_one_out$module_summary$in_post_primary_fixed_nomination_set &
      module_leave_one_out$module_summary$direction_reversal_any, , drop = FALSE
  ]
  reversal_text <- if (nrow(reversal_rows)) {
    paste0(
      "Post-primary fixed-set reversals:\n",
      paste(reversal_rows$module_id, collapse = " and "),
      " (omit 4 or 6); all full-analysis modules have q>0.10."
    )
  } else {
    "No fixed decision-set module direction reversal."
  }
  p <- ggplot2::ggplot(loo, ggplot2::aes(omitted_batch, spearman_shrunken_lfc_vs_full)) +
    ggplot2::geom_col(fill = "#365F91") +
    ggplot2::coord_cartesian(ylim = c(0, 1)) +
    ggplot2::labs(title = "Leave-one-batch-out stability", x = "Omitted batch",
                  subtitle = "Bars are gene-level shrunken-effect diagnostics; module verdict is annotated below",
                  caption = reversal_text,
                  y = "Spearman correlation with full shrunken effects") +
    ggplot2::theme_bw() +
    ggplot2::theme(
      plot.caption = ggplot2::element_text(
        hjust = 0, face = "bold", size = 9, lineheight = 1.1,
        margin = ggplot2::margin(t = 6)
      ),
      plot.margin = ggplot2::margin(8, 10, 12, 10)
    )
  paths <- c(paths, track2_save_plot(p, file.path(fig_dir, "leave_one_batch_out.png")))

  dosage <- do.call(rbind, lapply(exploratory, `[[`, "dosage"))
  p <- ggplot2::ggplot(dosage, ggplot2::aes(contrast_id, median_shift, fill = duplicated_region)) +
    ggplot2::geom_col(width = 0.65) +
    ggplot2::geom_hline(yintercept = 0, color = "grey50") +
    ggplot2::labs(title = "Exploratory duplicated-region dosage check",
                  subtitle = "Descriptive combined age+genotype contrasts; not identifiable genotype effects",
                  x = NULL, y = "Median unshrunk log2FC: duplicated region minus elsewhere", fill = "region") +
    ggplot2::theme_bw()
  paths <- c(paths, track2_save_plot(p, file.path(fig_dir, "exploratory_dosage_check.png")))
  paths
}

track2_atomic_write_tsv <- function(x, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(pattern = "track2-write-", tmpdir = dirname(path), fileext = ".tsv")
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  utils::write.table(x, tmp, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  if (file.exists(path)) unlink(path, force = TRUE)
  track2_assert(file.rename(tmp, path), "Could not finalize output: %s", path)
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_atomic_write_tsv_gz <- function(x, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(pattern = "track2-write-", tmpdir = dirname(path), fileext = ".tsv.gz")
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  con <- gzfile(tmp, open = "wt", compression = 9L)
  tryCatch(
    utils::write.table(x, con, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA"),
    finally = close(con)
  )
  if (file.exists(path)) unlink(path, force = TRUE)
  track2_assert(file.rename(tmp, path), "Could not finalize compressed output: %s", path)
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_atomic_write_json <- function(x, path, pretty = TRUE) {
  track2_assert(requireNamespace("jsonlite", quietly = TRUE),
                "Package 'jsonlite' is required. Run bootstrap.R.")
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- tempfile(pattern = "track2-write-", tmpdir = dirname(path), fileext = ".json")
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  jsonlite::write_json(x, tmp, pretty = pretty, auto_unbox = TRUE, na = "null", digits = 16)
  if (file.exists(path)) unlink(path, force = TRUE)
  track2_assert(file.rename(tmp, path), "Could not finalize output: %s", path)
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_annotate_de <- function(de, gene_map) {
  idx <- match(de$flybase_gene_id, gene_map$flybase_gene_id)
  out <- de
  out$gene_symbol <- gene_map$gene_symbol[idx]
  out$chromosome_arm <- gene_map$chromosome_arm[idx]
  out[, c("flybase_gene_id", "gene_symbol", "chromosome_arm",
          setdiff(names(out), c("flybase_gene_id", "gene_symbol", "chromosome_arm"))), drop = FALSE]
}

track2_module_export <- function(x) {
  if ("adj.pval" %in% names(x)) {
    names(x)[names(x) == "adj.pval"] <- "roastgsa_adj_pvalue_evaluable_only"
  }
  x
}

track2_annotation_policy_summary <- function(module_primary, module_no_iea) {
  keep <- c("module_id", "nes", "module_qvalue")
  track2_assert(all(keep %in% names(module_primary)) && all(keep %in% names(module_no_iea)),
                "Module tables lack fields required for annotation-policy sensitivity")
  out <- merge(
    module_primary[, keep, drop = FALSE], module_no_iea[, keep, drop = FALSE],
    by = "module_id", suffixes = c("_include_IEA", "_exclude_IEA"), sort = FALSE
  )
  out$direction_flip <- is.finite(out$nes_include_IEA) & is.finite(out$nes_exclude_IEA) &
    sign(out$nes_include_IEA) != sign(out$nes_exclude_IEA)
  out$include_IEA_supported_q_le_0_10 <- is.finite(out$module_qvalue_include_IEA) &
    out$module_qvalue_include_IEA <= 0.10
  out$exclude_IEA_supported_q_le_0_10 <- is.finite(out$module_qvalue_exclude_IEA) &
    out$module_qvalue_exclude_IEA <= 0.10
  out$interpretation <- ifelse(
    out$direction_flip & !out$include_IEA_supported_q_le_0_10 &
      !out$exclude_IEA_supported_q_le_0_10,
    "Descriptive annotation-policy direction instability; both policies are null at BH q<=0.10.",
    "No direction reversal across evaluable annotation policies."
  )
  order_index <- match(module_primary$module_id, out$module_id)
  out[order_index, , drop = FALSE]
}

track2_write_session_info <- function(path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  capture.output(utils::sessionInfo(), file = path)
  normalizePath(path, winslash = "/", mustWork = TRUE)
}

track2_write_results <- function(results_dir, source_checksums, source_manifest,
                                 sample_manifest, contrasts, primary_modules,
                                 qc_payload, primary_analysis, gene_map,
                                 module_collections, module_primary, module_no_iea,
                                 leave_one_out, module_leave_one_out,
                                 direction_gate_sensitivity,
                                 exploratory, human_signatures,
                                 sanity_checks) {
  dir.create(results_dir, recursive = TRUE, showWarnings = FALSE)
  paths <- character()
  write_tsv <- function(x, relative) {
    path <- track2_atomic_write_tsv(x, file.path(results_dir, relative))
    paths <<- c(paths, path)
    path
  }

  source_checksums_export <- source_checksums
  source_index <- match(source_checksums_export$source_id, source_manifest$source_id)
  track2_assert(!anyNA(source_index), "Source checksum rows do not match source_manifest IDs")
  source_checksums_export$path <- source_manifest$destination[source_index]
  write_tsv(source_checksums_export, "manifests/source_checksums.tsv")
  write_tsv(source_manifest, "manifests/source_manifest.tsv")
  write_tsv(sample_manifest, "manifests/sample_manifest.tsv")
  write_tsv(contrasts, "manifests/contrasts.tsv")
  write_tsv(primary_modules, "manifests/primary_modules.tsv")
  write_tsv(track2_package_versions(), "package_versions.tsv")
  paths <- c(paths, track2_atomic_write_json(qc_payload, file.path(results_dir, "qc/qc_summary.json")))
  write_tsv(qc_payload$primary$library_totals, "qc/primary_library_totals.tsv")
  write_tsv(qc_payload$exploratory_adversarial$library_totals,
            "qc/exploratory_library_totals.tsv")
  write_tsv(qc_payload$primary$pca, "qc/primary_vst_pca.tsv")

  annotated_de <- track2_annotate_de(primary_analysis$de, gene_map)
  write_tsv(annotated_de, "de/GSE290206_CIN_vs_control_full.tsv")
  write_tsv(annotated_de[annotated_de$passes_primary_threshold, , drop = FALSE],
            "de/GSE290206_CIN_vs_control_candidates.tsv")
  module_primary_export <- track2_module_export(module_primary)
  module_no_iea_export <- track2_module_export(module_no_iea)
  annotation_policy_summary <- track2_annotation_policy_summary(module_primary, module_no_iea)
  write_tsv(module_primary_export, "modules/preregistered_include_IEA.tsv")
  write_tsv(module_no_iea_export, "modules/preregistered_exclude_IEA_sensitivity.tsv")
  write_tsv(annotation_policy_summary, "modules/annotation_policy_sensitivity_summary.tsv")
  write_tsv(module_collections$include_iea$audit, "modules/module_construction_include_IEA.tsv")
  write_tsv(module_collections$exclude_iea$audit, "modules/module_construction_exclude_IEA.tsv")
  loo_path <- track2_atomic_write_tsv_gz(
    leave_one_out$gene_results,
    file.path(results_dir, "sensitivity/leave_one_batch_out_gene_results.tsv.gz")
  )
  paths <- c(paths, loo_path)
  write_tsv(leave_one_out$summary, "sensitivity/leave_one_batch_out_summary.tsv")
  write_tsv(track2_module_export(module_leave_one_out$results),
            "sensitivity/leave_one_batch_out_module_results.tsv")
  write_tsv(module_leave_one_out$direction_driver_overlaps,
            "sensitivity/leave_one_batch_out_module_direction_driver_overlap.tsv")
  write_tsv(module_leave_one_out$module_summary,
            "sensitivity/leave_one_batch_out_module_summary.tsv")
  write_tsv(direction_gate_sensitivity$gene_results,
            "sensitivity/raw_vs_normalized_direction_gene_audit.tsv")
  write_tsv(direction_gate_sensitivity$summary,
            "sensitivity/raw_vs_normalized_direction_summary.tsv")
  verdict_export <- module_leave_one_out$verdict
  significant_modules <- module_primary$module_id[
    !is.na(module_primary$module_qvalue) & module_primary$module_qvalue <= 0.10
  ]
  configured_modules <- nrow(module_primary)
  evaluable_primary_modules <- sum(is.finite(module_primary$pval))
  evaluable_no_iea_modules <- sum(is.finite(module_no_iea$pval))
  loo_supported_from_full_null <- module_leave_one_out$results[
    !module_leave_one_out$results$full_supported_q_le_0_10 &
      module_leave_one_out$results$loo_supported_q_le_0_10, , drop = FALSE
  ]
  annotation_direction_flips <- annotation_policy_summary[
    annotation_policy_summary$direction_flip, , drop = FALSE
  ]
  verdict_export$module_inference_boundary <- if (length(significant_modules)) {
    paste0("Leave-one-batch stability is an influence check only; module evidence is separately ",
           "supported at BH q<=0.10 for: ", paste(significant_modules, collapse = "|"), ".")
  } else {
    paste0("Leave-one-batch stability is an influence check only. Zero of ",
           evaluable_primary_modules, " evaluable primary modules (", configured_modules,
           " configured) reach BH q<=0.10; stability must not be interpreted as mitochondrial, ",
           "proteostasis, or other module enrichment evidence.")
  }
  write_tsv(verdict_export, "sensitivity/stability_verdict.tsv")
  write_tsv(sanity_checks$genes, "sanity/gene_direction_checks.tsv")
  write_tsv(sanity_checks$modules, "sanity/module_direction_checks.tsv")

  exploratory_warning <- data.frame(
    dataset = "GSE301548",
    scope = "exploratory_adversarial_only",
    warning = paste0("Genotype is perfectly confounded with chronological age (5d controls, 8d trisomies). ",
                     "Neither contrast identifies a genotype effect; neither is used for primary inference or ranking."),
    stringsAsFactors = FALSE
  )
  write_tsv(exploratory_warning, "exploratory/GSE301548_INTERPRETATION_WARNING.tsv")
  for (id in names(exploratory)) {
    write_tsv(exploratory[[id]]$de, file.path("exploratory", paste0(id, "_combined_age_genotype.tsv")))
    write_tsv(exploratory[[id]]$dosage, file.path("exploratory", paste0(id, "_dosage_check.tsv")))
    write_tsv(exploratory[[id]]$size_factors,
              file.path("exploratory", paste0(id, "_size_factors.tsv")))
  }

  write_tsv(human_signatures$primary, "orthology/human_signature_DIOPT5_max_ties.tsv")
  write_tsv(human_signatures$sensitivity, "orthology/human_signature_DIOPT3_weighted.tsv")
  write_tsv(human_signatures$policy_sensitivity,
            "orthology/policy_sensitivity_summary.tsv")
  audit_path <- track2_atomic_write_tsv_gz(
    human_signatures$audit,
    file.path(results_dir, "orthology/all_mapping_audit.tsv.gz")
  )
  paths <- c(paths, audit_path)
  legacy_large_outputs <- file.path(
    results_dir,
    c("sensitivity/leave_one_batch_out_gene_results.tsv",
      "orthology/all_mapping_audit.tsv")
  )
  unlink(legacy_large_outputs[file.exists(legacy_large_outputs)], force = TRUE)
  legacy_module_output <- file.path(
    results_dir, "sensitivity/leave_one_batch_out_module_leading_edges.tsv"
  )
  unlink(legacy_module_output[file.exists(legacy_module_output)], force = TRUE)

  summary <- list(
    schema_version = "1.0",
    seed = 20260826L,
    primary_dataset = "GSE290206",
    primary_interpretation = primary_analysis$interpretation,
    primary_candidate_count = primary_analysis$candidate_count,
    module_lock_provenance = paste0(
      "The 13-module registry was prespecified and analysis-locked before the authoritative run. ",
      "No immutable external preregistration timestamp exists."
    ),
    immutable_external_preregistration_timestamp = NA_character_,
    preregistered_key_compatibility_note = paste0(
      "Historical filenames and JSON keys containing 'preregistered' are retained only for ",
      "compatibility and do not assert external preregistration."
    ),
    preregistered_modules_configured = configured_modules,
    preregistered_modules_evaluable_primary_include_IEA = evaluable_primary_modules,
    preregistered_modules_evaluable_sensitivity_exclude_IEA = evaluable_no_iea_modules,
    module_multiple_testing = paste0("BH is conservatively computed with n=", configured_modules,
                                     " configured modules, ",
                                     "including modules unevaluable at minsize=10."),
    preregistered_modules_q_le_0_10 = length(significant_modules),
    module_nomination_supported = length(significant_modules) > 0L,
    primary_module_result_branch = if (length(significant_modules)) {
      "module_support_present"
    } else {
      "null_module_support"
    },
    preregistered_module_result = if (length(significant_modules)) {
      paste0("Modules reaching BH q<=0.10: ", paste(significant_modules, collapse = ", "), ".")
    } else {
      paste0("No evaluable primary module reaches BH q<=0.10 (", evaluable_primary_modules,
             " evaluable; ", configured_modules, " configured). Nominal rotation p-values are not ",
             "treated as statistically supported module enrichment.")
    },
    transcriptomic_nomination_conclusion = if (length(significant_modules)) {
      "Evaluate supported modules within the prespecified claim boundary and stability branch."
    } else {
      paste0("Transcriptomics does not validate a specific rescue candidate. Nominal module p-values, ",
             "gene-direction stability, exploratory contrasts, and orthology cannot override this branch.")
    },
    leave_one_batch_out_downgrade_required = module_leave_one_out$verdict$downgrade_required,
    leave_one_batch_out_nomination_decision_modules =
      module_leave_one_out$verdict$nomination_decision_modules,
    leave_one_batch_out_decision_set_provenance =
      module_leave_one_out$verdict$decision_set_provenance,
    leave_one_batch_out_full_null_to_supported_sensitivities = lapply(
      seq_len(nrow(loo_supported_from_full_null)), function(i) {
        list(
          module_id = loo_supported_from_full_null$module_id[[i]],
          omitted_batch = loo_supported_from_full_null$omitted_batch[[i]],
          full_module_qvalue = loo_supported_from_full_null$full_module_qvalue[[i]],
          leave_one_out_module_qvalue = loo_supported_from_full_null$module_qvalue[[i]],
          interpretation = paste0(
            "Fragile leave-one-batch sensitivity only; it cannot override the full-analysis null."
          )
        )
      }
    ),
    leave_one_batch_out_fit_warning_count = sum(leave_one_out$summary$fit_warning_count),
    leave_one_batch_out_fit_warning_note = if (sum(leave_one_out$summary$fit_warning_count) > 0L) {
      paste0("Numerical fit warnings occurred and are retained verbatim by omitted batch in ",
             "sensitivity/leave_one_batch_out_summary.tsv; no values were forced.")
    } else {
      "No numerical fit warnings were recorded."
    },
    leave_one_batch_out_interpretation = paste0(
      "The diagnostic downgrade branch uses a post-primary implementation-amendment subset fixed ",
      "before module leave-one-batch analysis; it is not part of the original 13-module ",
      "analysis lock. Gene-level Spearman is diagnostic only. Stability does not supply statistical ",
      "support for mitochondrial, proteostasis, or any other module enrichment. When the full ",
      "module result is null, a reversal is descriptive instability evidence, not a second ",
      "inferential rejection or statistically meaningful module evidence."
    ),
    normalized_direction_gate_sensitivity = as.list(direction_gate_sensitivity$summary),
    orthology_policy_sensitivity = as.list(human_signatures$policy_sensitivity),
    annotation_policy_direction_flips = lapply(
      seq_len(nrow(annotation_direction_flips)), function(i) {
        list(
          module_id = annotation_direction_flips$module_id[[i]],
          include_IEA_nes = annotation_direction_flips$nes_include_IEA[[i]],
          include_IEA_module_qvalue =
            annotation_direction_flips$module_qvalue_include_IEA[[i]],
          exclude_IEA_nes = annotation_direction_flips$nes_exclude_IEA[[i]],
          exclude_IEA_module_qvalue =
            annotation_direction_flips$module_qvalue_exclude_IEA[[i]],
          interpretation = annotation_direction_flips$interpretation[[i]]
        )
      }
    ),
    authoritative_module_multiplicity_column = paste0(
      "module_qvalue (BH with n=13 configured modules). ",
      "roastgsa_adj_pvalue_evaluable_only is retained for transparency and is not used for decisions."
    ),
    limitations = c(
      "Six whole-brain libraries from three batch pairs; tissue composition can contribute to observed effects.",
      "SAC-depletion/CIN pathway evidence is not BUB1B-specific.",
      "GSE301548 is perfectly confounded by chronological age and genotype and is exploratory only."
    ),
    claim_boundary = paste0(
      "No clinical or treatment claim is made. Named candidates are prospective preclinical ",
      "benchmarks only; none is transcriptomically validated or preferred, and none is used to ",
      "manufacture transcriptomic evidence."
    )
  )
  paths <- c(paths, track2_atomic_write_json(summary, file.path(results_dir, "analysis_summary.json")))
  paths <- c(paths, track2_write_session_info(file.path(results_dir, "sessionInfo.txt")))
  paths <- c(paths, track2_make_figures(results_dir, qc_payload, annotated_de, module_primary,
                                       leave_one_out, module_leave_one_out, exploratory))

  inventory <- data.frame(
    path = vapply(paths, function(x) {
      sub(paste0("^", gsub("([.|()\\^{}+$*?]|\\[|\\])", "\\\\\\1",
                            normalizePath(results_dir, winslash = "/")), "/?"), "", x)
    }, character(1L)),
    sha256 = vapply(paths, track2_sha256, character(1L)),
    bytes = vapply(paths, function(x) unname(file.info(x)$size), numeric(1L)),
    stringsAsFactors = FALSE
  )
  paths <- c(paths, track2_atomic_write_tsv(inventory, file.path(results_dir, "generated_files.tsv")))
  unique(paths)
}
