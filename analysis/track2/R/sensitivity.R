track2_validate_unshrunk_loo_summary <- function(summary) {
  required <- c("omitted_batch", "n_genes_compared_unshrunk",
                "spearman_unshrunk_lfc_vs_full",
                "direction_concordance_all_unshrunk")
  track2_assert(all(required %in% names(summary)),
                "LOO summary lacks unshrunk diagnostic columns: %s",
                paste(setdiff(required, names(summary)), collapse = ", "))
  invalid <- summary$n_genes_compared_unshrunk <= 0L |
    !is.finite(summary$spearman_unshrunk_lfc_vs_full) |
    !is.finite(summary$direction_concordance_all_unshrunk)
  track2_assert(!any(invalid),
                "Unshrunk LOO diagnostics are missing/non-finite for omitted batch(es): %s",
                paste(summary$omitted_batch[invalid], collapse = ", "))
  invisible(TRUE)
}

track2_leave_one_batch_out <- function(primary_import, primary_filter, primary_analysis) {
  full <- primary_analysis$de
  batches <- sort(unique(primary_import$samples$batch))
  gene_results <- vector("list", length(batches))
  summaries <- vector("list", length(batches))
  vst_matrices <- vector("list", length(batches))
  names(vst_matrices) <- batches

  for (i in seq_along(batches)) {
    omitted <- batches[[i]]
    samples <- primary_import$samples[primary_import$samples$batch != omitted, , drop = FALSE]
    counts <- primary_filter$counts[, samples$sample_id, drop = FALSE]
    fit_warnings <- character()
    model <- withCallingHandlers(
      track2_deseq_model(
        counts, samples, denominator = "control", numerator = "CIN", make_vst = TRUE
      ),
      warning = function(w) {
        fit_warnings <<- c(fit_warnings, conditionMessage(w))
      }
    )
    de <- track2_de_table(model, counts, samples, "control", "CIN", primary_thresholds = FALSE)
    de$omitted_batch <- omitted
    gene_results[[i]] <- de
    vst_matrices[[omitted]] <- model$vst

    idx <- match(full$flybase_gene_id, de$flybase_gene_id)
    full_lfc <- full$log2FoldChange_shrunken
    loo_lfc <- de$log2FoldChange_shrunken[idx]
    usable <- is.finite(full_lfc) & is.finite(loo_lfc)
    correlation <- if (sum(usable) >= 3L) {
      stats::cor(full_lfc[usable], loo_lfc[usable], method = "spearman")
    } else {
      NA_real_
    }
    sign_concordance_all <- if (any(usable)) {
      mean(sign(full_lfc[usable]) == sign(loo_lfc[usable]))
    } else {
      NA_real_
    }
    full_unshrunk_lfc <- full$log2FoldChange_unshrunk
    loo_unshrunk_lfc <- de$log2FoldChange_unshrunk[idx]
    usable_unshrunk <- is.finite(full_unshrunk_lfc) & is.finite(loo_unshrunk_lfc)
    unshrunk_correlation <- if (sum(usable_unshrunk) >= 3L) {
      stats::cor(full_unshrunk_lfc[usable_unshrunk], loo_unshrunk_lfc[usable_unshrunk],
                 method = "spearman")
    } else {
      NA_real_
    }
    unshrunk_sign_concordance_all <- if (any(usable_unshrunk)) {
      mean(sign(full_unshrunk_lfc[usable_unshrunk]) ==
             sign(loo_unshrunk_lfc[usable_unshrunk]))
    } else {
      NA_real_
    }
    candidate <- full$passes_primary_threshold & usable
    sign_concordance_candidates <- if (any(candidate)) {
      mean(sign(full_lfc[candidate]) == sign(loo_lfc[candidate]))
    } else {
      NA_real_
    }
    candidate_direction_retained <- candidate & sign(full_lfc) == sign(loo_lfc)
    candidate_unshrunk <- full$passes_primary_threshold & usable_unshrunk
    candidate_direction_retained_unshrunk <- candidate_unshrunk &
      sign(full_unshrunk_lfc) == sign(loo_unshrunk_lfc)
    candidate_q_and_shrunken_effect_retained <- candidate & !is.na(de$padj[idx]) &
      de$padj[idx] <= 0.10 & abs(loo_lfc) >= log2(1.25)
    n_full_candidates <- sum(full$passes_primary_threshold)
    summaries[[i]] <- data.frame(
      omitted_batch = omitted,
      retained_batches = paste(setdiff(batches, omitted), collapse = "|"),
      n_libraries = nrow(samples),
      n_genes_compared = sum(usable),
      spearman_shrunken_lfc_vs_full = correlation,
      direction_concordance_all = sign_concordance_all,
      n_genes_compared_unshrunk = sum(usable_unshrunk),
      spearman_unshrunk_lfc_vs_full = unshrunk_correlation,
      direction_concordance_all_unshrunk = unshrunk_sign_concordance_all,
      n_full_primary_candidates = n_full_candidates,
      direction_concordance_full_candidates = sign_concordance_candidates,
      n_full_candidates_retaining_direction = sum(candidate_direction_retained),
      fraction_full_candidates_retaining_direction = if (n_full_candidates) {
        sum(candidate_direction_retained) / n_full_candidates
      } else NA_real_,
      n_full_candidates_retaining_direction_unshrunk =
        sum(candidate_direction_retained_unshrunk),
      fraction_full_candidates_retaining_direction_unshrunk = if (n_full_candidates) {
        sum(candidate_direction_retained_unshrunk) / n_full_candidates
      } else NA_real_,
      n_full_candidates_retaining_q_and_shrunken_effect =
        sum(candidate_q_and_shrunken_effect_retained),
      fraction_full_candidates_retaining_q_and_shrunken_effect = if (n_full_candidates) {
        sum(candidate_q_and_shrunken_effect_retained) / n_full_candidates
      } else NA_real_,
      q_and_shrunken_effect_retention_interpretation = paste0(
        paste0("Descriptive only: n=4 after omission reduces power; loss of ",
               "q-and-shrunken-effect criteria is not a contradiction.")
      ),
      fit_warning_count = length(fit_warnings),
      fit_warnings = paste(unique(fit_warnings), collapse = " | "),
      warning_scope = if (length(fit_warnings)) {
        paste0("apeglm shrinkage warning: shrunken-LFC Spearman and ",
               "q-and-shrunken-effect retention require ",
               "caution; unshrunk DESeq2 LFC diagnostics are reported separately. Module fits ",
               "and the full primary fit are unaffected by this omission-specific warning.")
      } else {
        "No omission-specific fit warning recorded."
      },
      diagnostic_only = TRUE,
      stringsAsFactors = FALSE
    )
  }

  summary <- do.call(rbind, summaries)
  track2_validate_unshrunk_loo_summary(summary)
  list(
    gene_results = do.call(rbind, gene_results),
    summary = summary,
    vst = vst_matrices,
    note = paste0("Gene-level correlations and direction concordance are diagnostic only and do not ",
                  "set the downgrade branch. With only three pairs, no exact permutation p<0.05 is claimed.")
  )
}

track2_direction_gate_sensitivity <- function(primary_de) {
  normalized_columns <- paste0("within_batch_normalized_log2fc_", c("4", "5", "6"))
  required <- c("flybase_gene_id", "padj", "log2FoldChange_shrunken",
                "raw_direction_agreement_n", "passes_primary_threshold",
                normalized_columns)
  track2_assert(all(required %in% names(primary_de)),
                "Primary DE table lacks direction-gate sensitivity columns: %s",
                paste(setdiff(required, names(primary_de)), collapse = ", "))
  normalized_effects <- as.matrix(primary_de[, normalized_columns, drop = FALSE])
  direction <- sign(primary_de$log2FoldChange_shrunken)
  normalized_agreement <- as.integer(rowSums(
    sign(normalized_effects) == direction & sign(normalized_effects) != 0L,
    na.rm = TRUE
  ))
  normalized_call <- !is.na(primary_de$padj) & primary_de$padj <= 0.10 &
    abs(primary_de$log2FoldChange_shrunken) >= log2(1.25) & normalized_agreement >= 2L
  raw_call <- primary_de$passes_primary_threshold
  gene_results <- data.frame(
    flybase_gene_id = primary_de$flybase_gene_id,
    raw_direction_agreement_n = primary_de$raw_direction_agreement_n,
    normalized_direction_agreement_n = normalized_agreement,
    agreement_count_differs = primary_de$raw_direction_agreement_n != normalized_agreement,
    locked_raw_gate_call = raw_call,
    normalized_gate_sensitivity_call = normalized_call,
    stringsAsFactors = FALSE
  )
  summary <- data.frame(
    genes_evaluated = nrow(primary_de),
    genes_with_different_agreement_count = sum(gene_results$agreement_count_differs),
    locked_raw_gate_candidates = sum(raw_call),
    normalized_gate_candidates = sum(normalized_call),
    overlap_candidates = sum(raw_call & normalized_call),
    locked_raw_only_candidates = sum(raw_call & !normalized_call),
    normalized_only_candidates = sum(!raw_call & normalized_call),
    primary_gate = "raw_count_log2_ratios_2_of_3_locked",
    sensitivity_gate = "DESeq2_normalized_count_log2_ratios_2_of_3_result_neutral",
    interpretation = if (identical(raw_call, normalized_call)) {
      "Normalized-direction sensitivity does not change any primary candidate call."
    } else {
      "Normalized-direction sensitivity changes candidate calls; inspect the gene-level audit."
    },
    stringsAsFactors = FALSE
  )
  list(gene_results = gene_results, summary = summary)
}

track2_direction_driver_set <- function(de, module_genes, direction, fraction = 0.20) {
  track2_assert(fraction > 0 && fraction <= 1, "Direction-driver fraction must be in (0, 1]")
  if (!is.finite(direction) || direction == 0) return(character())
  stat <- stats::setNames(de$wald_stat, de$flybase_gene_id)
  measured <- intersect(module_genes, names(stat))
  eligible <- measured[is.finite(stat[measured]) & sign(stat[measured]) == sign(direction)]
  if (!length(eligible)) return(character())
  ordered <- eligible[order(-abs(stat[eligible]), eligible)]
  ordered[seq_len(max(1L, ceiling(length(ordered) * fraction)))]
}

track2_module_stability_flags <- function(full_nes, loo_nes, full_qvalue, loo_qvalue) {
  reversal <- is.finite(full_nes) && is.finite(loo_nes) && full_nes != 0 && loo_nes != 0 &&
    sign(full_nes) != sign(loo_nes)
  full_supported <- is.finite(full_qvalue) && full_qvalue <= 0.10
  loo_supported <- is.finite(loo_qvalue) && loo_qvalue <= 0.10
  c(
    direction_reversal = reversal,
    full_supported_q_le_0_10 = full_supported,
    loo_supported_q_le_0_10 = loo_supported,
    single_block_dependence = full_supported && !loo_supported
  )
}

track2_leave_one_batch_modules <- function(primary_import, primary_analysis,
                                           module_collection, module_primary,
                                           leave_one_out, decision_module_ids,
                                           seed = 20260826L,
                                           nrot = 9999L) {
  track2_assert(length(decision_module_ids) > 0L &&
                  all(decision_module_ids %in% module_primary$module_id),
                "Nomination decision modules must be a nonempty subset of configured modules")
  batches <- sort(unique(primary_import$samples$batch))
  rows <- vector("list", length(batches))
  driver_overlap_rows <- vector("list", length(batches))

  for (i in seq_along(batches)) {
    omitted <- batches[[i]]
    samples <- primary_import$samples[primary_import$samples$batch != omitted, , drop = FALSE]
    de <- leave_one_out$gene_results[
      leave_one_out$gene_results$omitted_batch == omitted, , drop = FALSE
    ]
    scores <- track2_run_roast_modules(
      leave_one_out$vst[[omitted]],
      samples,
      module_collection,
      de,
      paste0("include_IEA_exclude_NOT_ND_leave_out_batch_", omitted),
      seed,
      nrot
    )
    full_idx <- match(scores$module_id, module_primary$module_id)
    scores$omitted_batch <- omitted
    scores$retained_batches <- paste(setdiff(batches, omitted), collapse = "|")
    scores$full_nes <- module_primary$nes[full_idx]
    scores$full_module_qvalue <- module_primary$module_qvalue[full_idx]
    flags <- t(vapply(seq_len(nrow(scores)), function(j) {
      track2_module_stability_flags(
        scores$full_nes[[j]], scores$nes[[j]],
        scores$full_module_qvalue[[j]], scores$module_qvalue[[j]]
      )
    }, logical(4L)))
    scores$direction_reversal <- flags[, "direction_reversal"]
    scores$full_supported_q_le_0_10 <- flags[, "full_supported_q_le_0_10"]
    scores$loo_supported_q_le_0_10 <- flags[, "loo_supported_q_le_0_10"]
    scores$single_block_dependence <- flags[, "single_block_dependence"]
    scores$in_post_primary_fixed_nomination_set <- scores$module_id %in% decision_module_ids
    scores$triggers_downgrade <- scores$in_post_primary_fixed_nomination_set &
      (scores$direction_reversal | scores$single_block_dependence)
    rows[[i]] <- scores

    edge_rows <- lapply(seq_len(nrow(scores)), function(j) {
      module_id <- scores$module_id[[j]]
      genes <- module_collection$sets[[module_id]]
      full_drivers <- track2_direction_driver_set(primary_analysis$de, genes, scores$full_nes[[j]])
      loo_drivers <- track2_direction_driver_set(de, genes, scores$nes[[j]])
      overlap <- intersect(full_drivers, loo_drivers)
      driver_union <- union(full_drivers, loo_drivers)
      data.frame(
        module_id = module_id,
        omitted_batch = omitted,
        diagnostic_name = "direction_driver_overlap_not_formal_leading_edge",
        direction_driver_rule = "top_20_percent_absolute_Wald_with_roastgsa_NES_direction",
        affects_rotation_p_or_q = FALSE,
        affects_downgrade_verdict = FALSE,
        full_direction_driver_n = length(full_drivers),
        loo_direction_driver_n = length(loo_drivers),
        overlap_n = length(overlap),
        jaccard_overlap = if (length(driver_union)) length(overlap) / length(driver_union) else NA_real_,
        full_driver_recovered_fraction = if (length(full_drivers)) {
          length(overlap) / length(full_drivers)
        } else NA_real_,
        full_direction_driver_genes = paste(full_drivers, collapse = "|"),
        loo_direction_driver_genes = paste(loo_drivers, collapse = "|"),
        overlap_genes = paste(overlap, collapse = "|"),
        stringsAsFactors = FALSE
      )
    })
    driver_overlap_rows[[i]] <- do.call(rbind, edge_rows)
  }

  results <- do.call(rbind, rows)
  direction_driver_overlaps <- do.call(rbind, driver_overlap_rows)
  module_ids <- unique(module_primary$module_id)
  module_summary <- do.call(rbind, lapply(module_ids, function(module_id) {
    x <- results[results$module_id == module_id, , drop = FALSE]
    e <- direction_driver_overlaps[direction_driver_overlaps$module_id == module_id, , drop = FALSE]
    data.frame(
      module_id = module_id,
      full_nes = x$full_nes[[1L]],
      full_module_qvalue = x$full_module_qvalue[[1L]],
      in_post_primary_fixed_nomination_set = module_id %in% decision_module_ids,
      direction_reversal_any = any(x$direction_reversal),
      reversed_when_omitting = paste(x$omitted_batch[x$direction_reversal], collapse = "|"),
      single_block_dependence_any = any(x$single_block_dependence),
      dependent_on_batches = paste(x$omitted_batch[x$single_block_dependence], collapse = "|"),
      triggers_downgrade = any(x$triggers_downgrade),
      min_direction_driver_jaccard = suppressWarnings(min(e$jaccard_overlap, na.rm = TRUE)),
      min_full_driver_recovered_fraction = suppressWarnings(min(e$full_driver_recovered_fraction, na.rm = TRUE)),
      stringsAsFactors = FALSE
    )
  }))
  module_summary$min_direction_driver_jaccard[
    !is.finite(module_summary$min_direction_driver_jaccard)
  ] <- NA_real_
  module_summary$min_full_driver_recovered_fraction[
    !is.finite(module_summary$min_full_driver_recovered_fraction)
  ] <- NA_real_
  downgrade <- any(module_summary$triggers_downgrade)
  verdict <- data.frame(
    downgrade_required = downgrade,
    nomination_decision_modules = paste(decision_module_ids, collapse = "|"),
    decision_set_provenance = paste0(
      "Post-primary implementation amendment dated 2026-08-26; fixed before module-level ",
      "leave-one-batch sensitivity. The original analysis lock covers all 13 modules, not this subset; ",
      "no immutable external preregistration timestamp exists."
    ),
    rule = paste0("Downgrade if a module in the post-primary fixed nomination set reverses direction ",
                  "in a leave-one-batch-out rotation fit, or if a full-analysis decision-set module ",
                  "with BH q<=0.10 loses BH q<=0.10 when one batch is omitted ",
                  "(single-block dependence). Reversals in other configured modules are diagnostic only."),
    note = paste0("Module-level maxmean fits use 9,999 rotations and BH across the same 13 modules. ",
                  "Direction-driver overlap is a descriptive diagnostic, not a formal leading edge. ",
                  "A direction reversal of a module without full-analysis BH support is descriptive ",
                  "instability, not statistically meaningful enrichment evidence. With only three pairs, no exact ",
                  "permutation p<0.05 is claimed. Gene-level Spearman does not set this verdict."),
    stringsAsFactors = FALSE
  )
  list(results = results, direction_driver_overlaps = direction_driver_overlaps,
       module_summary = module_summary, verdict = verdict)
}
