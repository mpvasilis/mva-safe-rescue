track2_read_gene_map <- function(path) {
  track2_assert(file.exists(path), "FlyBase gene map is missing: %s", path)
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  tab <- utils::read.delim(
    con, header = FALSE, sep = "\t", quote = "", comment.char = "#",
    fill = TRUE, stringsAsFactors = FALSE, colClasses = "character"
  )
  track2_assert(ncol(tab) == 6L, "FlyBase gene map schema changed: expected 6 columns; observed %d", ncol(tab))
  names(tab) <- c("organism_abbreviation", "gene_symbol", "flybase_gene_id",
                  "recombination_loc", "cytogenetic_loc", "sequence_loc")
  tab <- tab[tab$organism_abbreviation == "Dmel" &
               grepl("^FBgn[0-9]{7}$", tab$flybase_gene_id), , drop = FALSE]
  track2_assert(!anyDuplicated(tab$flybase_gene_id), "FlyBase gene map has duplicated primary FBgn IDs")
  chromosome_arm <- sub(":.*$", "", tab$sequence_loc)
  chromosome_arm[!grepl(":", tab$sequence_loc, fixed = TRUE)] <- NA_character_
  tab$chromosome_arm <- chromosome_arm
  tab
}

track2_read_orthologs <- function(path) {
  track2_assert(file.exists(path), "FlyBase ortholog table is missing: %s", path)
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  tab <- utils::read.delim(
    con, header = FALSE, sep = "\t", quote = "", comment.char = "#",
    fill = TRUE, stringsAsFactors = FALSE, colClasses = "character"
  )
  track2_assert(ncol(tab) == 8L,
                "FlyBase ortholog schema changed: expected 8 columns; observed %d", ncol(tab))
  names(tab) <- c("flybase_gene_id", "fly_gene_symbol", "human_hgnc_id", "human_omim_id",
                  "human_gene_symbol", "diopt_score", "omim_phenotype_ids",
                  "omim_phenotype_names")
  track2_assert(all(grepl("^FBgn[0-9]{7}$", tab$flybase_gene_id)),
                "Ortholog table contains malformed FBgn IDs")
  track2_assert(all(grepl("^HGNC:[0-9]+$", tab$human_hgnc_id)),
                "Ortholog table contains malformed HGNC IDs")
  tab$diopt_score <- suppressWarnings(as.integer(tab$diopt_score))
  track2_assert(!anyNA(tab$diopt_score) && all(tab$diopt_score >= 0L),
                "Ortholog table contains invalid DIOPT scores")
  unique(tab)
}

track2_orthology_weights <- function(orthologs) {
  split_index <- split(seq_len(nrow(orthologs)), orthologs$flybase_gene_id)
  primary_weight <- sensitivity_weight <- numeric(nrow(orthologs))
  max_score <- co_best_count <- integer(nrow(orthologs))
  for (idx in split_index) {
    scores <- orthologs$diopt_score[idx]
    valid_hgnc <- orthologs$human_hgnc_id[idx] != "HGNC:0"
    maximum <- if (any(valid_hgnc)) max(scores[valid_hgnc]) else NA_integer_
    is_best <- valid_hgnc & scores == maximum & scores >= 5L
    primary_weight[idx[is_best]] <- 1 / sum(is_best)
    eligible_sensitivity <- valid_hgnc & scores >= 3L
    if (any(eligible_sensitivity)) {
      sensitivity_weight[idx[eligible_sensitivity]] <-
        scores[eligible_sensitivity] / sum(scores[eligible_sensitivity])
    }
    max_score[idx] <- if (is.na(maximum)) -1L else maximum
    co_best_count[idx] <- if (is.na(maximum)) 0L else sum(valid_hgnc & scores == maximum)
  }
  out <- orthologs
  out$max_diopt_for_fly_gene <- max_score
  out$co_best_count_at_max <- co_best_count
  out$primary_max_tie_weight <- primary_weight
  out$sensitivity_diopt_weight <- sensitivity_weight
  out$primary_mapping_eligible <- primary_weight > 0
  out$sensitivity_mapping_eligible <- sensitivity_weight > 0
  out$valid_hgnc_identifier <- out$human_hgnc_id != "HGNC:0"
  out$primary_exclusion_reason <- ifelse(
    !out$valid_hgnc_identifier, "HGNC:0_placeholder",
    ifelse(out$diopt_score < 5L, "DIOPT_below_5",
           ifelse(!out$primary_mapping_eligible, "not_maximum_for_fly_gene", "included"))
  )
  out$sensitivity_exclusion_reason <- ifelse(
    !out$valid_hgnc_identifier, "HGNC:0_placeholder",
    ifelse(out$diopt_score < 3L, "DIOPT_below_3", "included")
  )
  out
}

track2_weighted_stouffer <- function(mapping, de, weight_column, policy) {
  stat <- stats::setNames(de$wald_stat, de$flybase_gene_id)
  mapping$fly_wald_stat <- unname(stat[mapping$flybase_gene_id])
  mapping$mapping_weight <- mapping[[weight_column]]
  mapping$used_for_signature <- mapping$mapping_weight > 0 & is.finite(mapping$fly_wald_stat)
  used <- mapping[mapping$used_for_signature, , drop = FALSE]
  track2_assert(nrow(used) > 0L, "No finite primary Wald statistics map under policy: %s", policy)
  groups <- split(seq_len(nrow(used)), used$human_hgnc_id)
  rows <- lapply(groups, function(idx) {
    x <- used[idx, , drop = FALSE]
    denominator <- sqrt(sum(x$mapping_weight^2))
    track2_assert(is.finite(denominator) && denominator > 0,
                  "Invalid Stouffer denominator for %s", x$human_hgnc_id[[1L]])
    symbols <- unique(x$human_gene_symbol)
    track2_assert(length(symbols) == 1L,
                  "HGNC ID %s maps to inconsistent human symbols", x$human_hgnc_id[[1L]])
    data.frame(
      human_hgnc_id = x$human_hgnc_id[[1L]],
      human_gene_symbol = symbols[[1L]],
      weighted_stouffer_stat = sum(x$mapping_weight * x$fly_wald_stat) / denominator,
      stouffer_numerator = sum(x$mapping_weight * x$fly_wald_stat),
      stouffer_denominator = denominator,
      total_mapping_weight = sum(x$mapping_weight),
      n_fly_genes = length(unique(x$flybase_gene_id)),
      flybase_gene_ids = paste(sort(unique(x$flybase_gene_id)), collapse = "|"),
      mapping_policy = policy,
      source_contrast = "GSE290206_CIN_vs_control",
      ranking_eligible = TRUE,
      stringsAsFactors = FALSE
    )
  })
  signature <- do.call(rbind, rows)
  signature <- signature[order(-abs(signature$weighted_stouffer_stat), signature$human_hgnc_id), , drop = FALSE]
  rownames(signature) <- NULL
  mapping$mapping_policy_audited <- policy
  list(signature = signature, mapping = mapping)
}

track2_compare_orthology_policies <- function(primary, sensitivity, top_n = 100L) {
  required <- c("human_hgnc_id", "weighted_stouffer_stat")
  track2_assert(all(required %in% names(primary)) && all(required %in% names(sensitivity)),
                "Orthology policy comparison requires HGNC IDs and weighted Stouffer statistics")
  track2_assert(!anyDuplicated(primary$human_hgnc_id) &&
                  !anyDuplicated(sensitivity$human_hgnc_id),
                "Orthology signatures contain duplicated HGNC IDs")
  track2_assert(length(top_n) == 1L && is.finite(top_n) && top_n >= 1L,
                "top_n must be one positive integer")
  top_n <- as.integer(top_n)
  shared <- merge(
    primary[, required, drop = FALSE], sensitivity[, required, drop = FALSE],
    by = "human_hgnc_id", suffixes = c("_primary", "_sensitivity"), sort = TRUE
  )
  track2_assert(nrow(shared) >= 2L, "Fewer than two human genes are shared across mapping policies")
  primary_top <- head(
    primary$human_hgnc_id[order(-abs(primary$weighted_stouffer_stat), primary$human_hgnc_id)],
    min(top_n, nrow(primary))
  )
  sensitivity_top <- head(
    sensitivity$human_hgnc_id[
      order(-abs(sensitivity$weighted_stouffer_stat), sensitivity$human_hgnc_id)
    ],
    min(top_n, nrow(sensitivity))
  )
  data.frame(
    primary_policy = "DIOPT>=5_max_score_co-best_ties",
    sensitivity_policy = "DIOPT>=3_within-fly_DIOPT_weighted",
    primary_human_genes = nrow(primary),
    sensitivity_human_genes = nrow(sensitivity),
    shared_human_genes = nrow(shared),
    shared_score_spearman = stats::cor(
      shared$weighted_stouffer_stat_primary,
      shared$weighted_stouffer_stat_sensitivity,
      method = "spearman"
    ),
    shared_score_sign_concordance = mean(
      sign(shared$weighted_stouffer_stat_primary) ==
        sign(shared$weighted_stouffer_stat_sensitivity)
    ),
    top_absolute_score_n = top_n,
    top_absolute_score_overlap = length(intersect(primary_top, sensitivity_top)),
    interpretation = paste0(
      "Global signed scores are stable across policies, but top human-gene prioritization is ",
      "mapping-dependent; no top-gene nominee is treated as robust without dual-policy review."
    ),
    stringsAsFactors = FALSE
  )
}

track2_map_human_signatures <- function(primary_de, ortholog_path) {
  orthologs <- track2_read_orthologs(ortholog_path)
  audit <- track2_orthology_weights(orthologs)
  primary <- track2_weighted_stouffer(
    audit, primary_de, "primary_max_tie_weight",
    "DIOPT>=5; per-fly maximum only; co-best ties split equally"
  )
  sensitivity <- track2_weighted_stouffer(
    audit, primary_de, "sensitivity_diopt_weight",
    "DIOPT>=3; all eligible mappings weighted by within-fly DIOPT share"
  )
  audit$fly_wald_stat <- primary$mapping$fly_wald_stat
  audit$has_finite_primary_wald <- is.finite(audit$fly_wald_stat)
  audit$used_primary <- audit$primary_max_tie_weight > 0 & audit$has_finite_primary_wald
  audit$used_sensitivity <- audit$sensitivity_diopt_weight > 0 & audit$has_finite_primary_wald
  list(
    primary = primary$signature,
    sensitivity = sensitivity$signature,
    policy_sensitivity = track2_compare_orthology_policies(
      primary$signature, sensitivity$signature, top_n = 100L
    ),
    audit = audit
  )
}
