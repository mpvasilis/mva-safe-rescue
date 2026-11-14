track2_read_obo <- function(path) {
  track2_assert(file.exists(path), "GO graph is missing: %s", path)
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  lines <- readLines(con, warn = FALSE, encoding = "UTF-8")
  starts <- which(lines == "[Term]")
  track2_assert(length(starts) > 0L, "No [Term] blocks found in GO OBO file")
  all_blocks <- which(grepl("^\\[.+\\]$", lines))
  block_positions <- match(starts, all_blocks)
  block_ends <- ifelse(block_positions < length(all_blocks),
                       all_blocks[pmin(block_positions + 1L, length(all_blocks))] - 1L,
                       length(lines))
  terms <- vector("list", length(starts))
  edges <- vector("list", length(starts))
  alternatives <- vector("list", length(starts))

  value_after <- function(block, prefix) {
    hit <- block[startsWith(block, prefix)]
    if (!length(hit)) character() else sub(prefix, "", hit, fixed = TRUE)
  }
  for (i in seq_along(starts)) {
    start <- starts[[i]]
    end <- block_ends[[i]]
    block <- lines[seq.int(start + 1L, end)]
    id <- value_after(block, "id: ")
    if (length(id) != 1L || !grepl("^GO:[0-9]{7}$", id)) next
    obsolete <- any(block == "is_obsolete: true")
    name <- value_after(block, "name: ")
    terms[[i]] <- data.frame(
      go_id = id,
      go_name = if (length(name)) name[[1L]] else NA_character_,
      is_obsolete = obsolete,
      stringsAsFactors = FALSE
    )
    alt <- value_after(block, "alt_id: ")
    if (length(alt)) {
      alternatives[[i]] <- data.frame(alt_id = alt, go_id = id, stringsAsFactors = FALSE)
    }
    isa <- sub("^is_a: (GO:[0-9]{7}).*$", "\\1", block[grepl("^is_a: GO:[0-9]{7}", block)])
    partof <- sub("^relationship: part_of (GO:[0-9]{7}).*$", "\\1",
                  block[grepl("^relationship: part_of GO:[0-9]{7}", block)])
    parents <- unique(c(isa, partof))
    if (length(parents)) {
      edges[[i]] <- data.frame(child = id, parent = parents,
                               relation = c(rep("is_a", length(isa)), rep("part_of", length(partof)))[
                                 match(parents, c(isa, partof))],
                               stringsAsFactors = FALSE)
    }
  }
  terms <- do.call(rbind, Filter(Negate(is.null), terms))
  edges <- do.call(rbind, Filter(Negate(is.null), edges))
  alternatives <- do.call(rbind, Filter(Negate(is.null), alternatives))
  if (is.null(alternatives)) alternatives <- data.frame(alt_id = character(), go_id = character())
  valid <- !terms$is_obsolete
  valid_ids <- terms$go_id[valid]
  edges <- edges[edges$child %in% valid_ids & edges$parent %in% valid_ids, , drop = FALSE]
  list(terms = terms[valid, , drop = FALSE], edges = unique(edges), alternatives = alternatives)
}

track2_go_descendants <- function(go_graph, root) {
  track2_assert(root %in% go_graph$terms$go_id, "Analysis-locked GO root is absent from pinned graph: %s", root)
  seen <- root
  frontier <- root
  while (length(frontier)) {
    children <- unique(go_graph$edges$child[go_graph$edges$parent %in% frontier])
    children <- setdiff(children, seen)
    if (!length(children)) break
    seen <- c(seen, children)
    frontier <- children
  }
  unique(seen)
}

track2_read_gaf <- function(path, include_iea = TRUE) {
  track2_assert(file.exists(path), "FlyBase GAF is missing: %s", path)
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  gaf <- utils::read.delim(
    con, header = FALSE, sep = "\t", quote = "", comment.char = "!",
    fill = TRUE, stringsAsFactors = FALSE, colClasses = "character"
  )
  track2_assert(ncol(gaf) >= 15L, "GAF has fewer than 15 columns")
  names(gaf)[seq_len(15L)] <- c(
    "db", "flybase_gene_id", "gene_symbol", "qualifier", "go_id", "reference",
    "evidence_code", "with_from", "aspect", "gene_name", "synonym",
    "object_type", "taxon", "date", "assigned_by"
  )
  not_qualified <- grepl("(^|\\|)NOT(\\||$)", gaf$qualifier)
  keep <- !not_qualified & gaf$evidence_code != "ND"
  if (!include_iea) keep <- keep & gaf$evidence_code != "IEA"
  out <- gaf[keep, c("flybase_gene_id", "gene_symbol", "go_id", "evidence_code"), drop = FALSE]
  out <- out[grepl("^FBgn[0-9]{7}$", out$flybase_gene_id) &
               grepl("^GO:[0-9]{7}$", out$go_id), , drop = FALSE]
  unique(out)
}

track2_build_module_sets <- function(primary_modules, go_graph, gaf, annotation_policy) {
  alt_map <- stats::setNames(go_graph$alternatives$go_id, go_graph$alternatives$alt_id)
  alt_hit <- gaf$go_id %in% names(alt_map)
  gaf$go_id[alt_hit] <- unname(alt_map[gaf$go_id[alt_hit]])
  module_ids <- unique(primary_modules$module_id[order(as.integer(primary_modules$module_order))])
  sets <- stats::setNames(vector("list", length(module_ids)), module_ids)
  audit <- vector("list", length(module_ids))
  for (i in seq_along(module_ids)) {
    module_id <- module_ids[[i]]
    roots <- primary_modules$go_id[primary_modules$module_id == module_id]
    terms <- unique(unlist(lapply(roots, function(root) {
      track2_go_descendants(go_graph, root)
    }), use.names = FALSE))
    ann <- gaf[gaf$go_id %in% terms, , drop = FALSE]
    sets[[module_id]] <- sort(unique(ann$flybase_gene_id))
    audit[[i]] <- data.frame(
      module_id = module_id,
      annotation_policy = annotation_policy,
      root_go_ids = paste(roots, collapse = "|"),
      descendant_term_count_including_roots = length(terms),
      annotated_gene_count = length(sets[[module_id]]),
      stringsAsFactors = FALSE
    )
  }
  list(sets = sets, audit = do.call(rbind, audit))
}

track2_module_collections <- function(primary_modules, go_graph_path, gaf_path) {
  graph <- track2_read_obo(go_graph_path)
  gaf_iea <- track2_read_gaf(gaf_path, include_iea = TRUE)
  gaf_no_iea <- track2_read_gaf(gaf_path, include_iea = FALSE)
  list(
    include_iea = track2_build_module_sets(primary_modules, graph, gaf_iea, "include_IEA_exclude_NOT_ND"),
    exclude_iea = track2_build_module_sets(primary_modules, graph, gaf_no_iea, "exclude_IEA_NOT_ND"),
    graph_summary = data.frame(
      active_terms = nrow(graph$terms),
      is_a_or_part_of_edges = nrow(graph$edges),
      stringsAsFactors = FALSE
    )
  )
}

track2_continuous_wald_summary <- function(stats, gene_ids) {
  values <- stats[match(gene_ids, names(stats))]
  values <- values[is.finite(values)]
  if (!length(values)) {
    return(c(n_finite_wald = 0, mean_wald = NA_real_, maxmean_wald = NA_real_))
  }
  positive <- mean(pmax(values, 0))
  negative <- mean(pmax(-values, 0))
  maxmean <- if (positive >= negative) positive else -negative
  c(n_finite_wald = length(values), mean_wald = mean(values), maxmean_wald = maxmean)
}

track2_run_roast_modules <- function(vst_matrix, samples, module_collection,
                                     primary_de, annotation_policy,
                                     seed = 20260826L, nrot = 9999L) {
  track2_assert(requireNamespace("roastgsa", quietly = TRUE),
                "Package 'roastgsa' is required. Run bootstrap.R.")
  track2_assert(identical(colnames(vst_matrix), samples$sample_id),
                "VST matrix is not aligned to samples for module testing")
  sets <- lapply(module_collection$sets, intersect, y = rownames(vst_matrix))
  eligible <- lengths(sets) >= 10L
  track2_assert(any(eligible), "No analysis-locked module has at least 10 measured genes")
  covar <- data.frame(
    batch = factor(samples$batch),
    condition = factor(samples$condition, levels = c("control", "CIN")),
    row.names = samples$sample_id
  )
  form <- ~ batch + condition
  design <- stats::model.matrix(form, data = covar)
  track2_assert(qr(design)$rank == ncol(design), "Module-test design is rank deficient")
  contrast <- rep(0, ncol(design))
  contrast[match("conditionCIN", colnames(design))] <- 1
  track2_assert(sum(abs(contrast)) == 1, "Could not construct CIN-vs-control roastgsa contrast")
  set.seed(seed)
  fit <- roastgsa::roastgsa(
    y = vst_matrix,
    covar = covar,
    form = form,
    contrast = contrast,
    index = sets[eligible],
    self.contained = FALSE,
    set.statistic = "maxmean",
    nrot = nrot,
    minsize = 10L,
    maxsize = nrow(vst_matrix),
    mccores = 1L,
    executation.info = FALSE,
    shrink.resid = TRUE,
    normalizeScores = TRUE
  )
  observed <- as.data.frame(fit$res)
  observed$module_id <- rownames(observed)
  rownames(observed) <- NULL
  all_modules <- data.frame(module_id = names(sets), measured_genes_declared = lengths(sets),
                            stringsAsFactors = FALSE)
  out <- merge(all_modules, observed, by = "module_id", all.x = TRUE, sort = FALSE)
  out <- out[match(names(sets), out$module_id), , drop = FALSE]
  p_column <- intersect(c("pval", "p.value", "P.Value"), names(out))
  track2_assert(length(p_column) == 1L, "Could not identify roastgsa p-value column")
  out$pval <- out[[p_column]]
  finite <- is.finite(out$pval)
  out$module_qvalue <- NA_real_
  out$module_qvalue[finite] <- stats::p.adjust(out$pval[finite], method = "BH", n = nrow(out))
  out$annotation_policy <- annotation_policy
  out$seed <- seed
  out$nrot <- nrot
  out$set_statistic <- "maxmean"
  out$test_type <- "competitive_rotation"

  wald <- stats::setNames(primary_de$wald_stat, primary_de$flybase_gene_id)
  continuous <- t(vapply(sets, track2_continuous_wald_summary, numeric(3L), stats = wald))
  out$n_finite_continuous_wald <- continuous[out$module_id, "n_finite_wald"]
  out$mean_continuous_wald <- continuous[out$module_id, "mean_wald"]
  out$maxmean_continuous_wald <- continuous[out$module_id, "maxmean_wald"]
  out
}
