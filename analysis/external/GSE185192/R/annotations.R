gse_read_obo <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  starts <- which(lines == "[Term]")
  gse_assert(length(starts) > 0L, "No GO [Term] blocks in %s", path)
  block_headers <- which(grepl("^\\[.+\\]$", lines))
  positions <- match(starts, block_headers)
  ends <- ifelse(positions < length(block_headers), block_headers[positions + 1L] - 1L,
                 length(lines))
  terms <- vector("list", length(starts))
  edges <- vector("list", length(starts))
  alternatives <- vector("list", length(starts))
  value_after <- function(block, prefix) {
    hit <- block[startsWith(block, prefix)]
    if (!length(hit)) character() else sub(prefix, "", hit, fixed = TRUE)
  }
  for (i in seq_along(starts)) {
    block <- lines[seq.int(starts[[i]] + 1L, ends[[i]])]
    id <- value_after(block, "id: ")
    if (length(id) != 1L || !grepl("^GO:[0-9]{7}$", id)) next
    terms[[i]] <- data.frame(go_id = id, is_obsolete = any(block == "is_obsolete: true"),
                             stringsAsFactors = FALSE)
    alt <- value_after(block, "alt_id: ")
    if (length(alt)) alternatives[[i]] <- data.frame(alt_id = alt, go_id = id)
    isa <- sub("^is_a: (GO:[0-9]{7}).*$", "\\1", block[grepl("^is_a: GO:[0-9]{7}", block)])
    partof <- sub("^relationship: part_of (GO:[0-9]{7}).*$", "\\1",
                  block[grepl("^relationship: part_of GO:[0-9]{7}", block)])
    parents <- unique(c(isa, partof))
    if (length(parents)) edges[[i]] <- data.frame(child = id, parent = parents,
                                                   stringsAsFactors = FALSE)
  }
  terms <- do.call(rbind, Filter(Negate(is.null), terms))
  terms <- terms[!terms$is_obsolete, , drop = FALSE]
  edges <- do.call(rbind, Filter(Negate(is.null), edges))
  if (is.null(edges)) edges <- data.frame(child = character(), parent = character())
  edges <- unique(edges[edges$child %in% terms$go_id & edges$parent %in% terms$go_id, , drop = FALSE])
  alternatives <- do.call(rbind, Filter(Negate(is.null), alternatives))
  if (is.null(alternatives)) alternatives <- data.frame(alt_id = character(), go_id = character())
  list(terms = terms, edges = edges, alternatives = alternatives)
}

gse_go_descendants <- function(graph, root) {
  gse_assert(root %in% graph$terms$go_id, "Locked GO root absent from pinned ontology: %s", root)
  seen <- root
  frontier <- root
  while (length(frontier)) {
    children <- setdiff(unique(graph$edges$child[graph$edges$parent %in% frontier]), seen)
    if (!length(children)) break
    seen <- c(seen, children)
    frontier <- children
  }
  unique(seen)
}

gse_read_human_gaf <- function(path) {
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  gaf <- utils::read.delim(con, header = FALSE, sep = "\t", quote = "",
                           comment.char = "!", fill = TRUE, colClasses = "character",
                           stringsAsFactors = FALSE)
  gse_assert(ncol(gaf) >= 15L, "Human GOA GAF has fewer than 15 columns")
  qualifier <- gaf[[4L]]
  evidence <- gaf[[7L]]
  taxon <- gaf[[13L]]
  keep <- !grepl("(^|\\|)NOT(\\||$)", qualifier) & evidence != "ND" &
    grepl("(^|\\|)taxon:9606(\\||$)", taxon)
  out <- data.frame(gene_symbol = toupper(gaf[[3L]][keep]), go_id = gaf[[5L]][keep],
                    evidence_code = evidence[keep], stringsAsFactors = FALSE)
  out <- out[nzchar(out$gene_symbol) & grepl("^GO:[0-9]{7}$", out$go_id), , drop = FALSE]
  unique(out)
}

gse_build_modules <- function(modules, graph, gaf) {
  alt_map <- stats::setNames(graph$alternatives$go_id, graph$alternatives$alt_id)
  alt_hit <- gaf$go_id %in% names(alt_map)
  gaf$go_id[alt_hit] <- unname(alt_map[gaf$go_id[alt_hit]])
  sets <- stats::setNames(vector("list", nrow(modules)), modules$module_id)
  audit <- vector("list", nrow(modules))
  for (i in seq_len(nrow(modules))) {
    roots <- strsplit(modules$root_go_ids[[i]], "|", fixed = TRUE)[[1L]]
    terms <- unique(unlist(lapply(roots, function(root) gse_go_descendants(graph, root)),
                           use.names = FALSE))
    sets[[modules$module_id[[i]]]] <- sort(unique(gaf$gene_symbol[gaf$go_id %in% terms]))
    audit[[i]] <- data.frame(
      module_order = as.integer(modules$module_order[[i]]),
      module_id = modules$module_id[[i]], root_go_ids = modules$root_go_ids[[i]],
      descendant_term_count_including_roots = length(terms),
      annotated_human_gene_symbols = length(sets[[modules$module_id[[i]]]]),
      annotation_policy = paste0(
        "GO_2026-08-05_HUMAN-uniprot_include_IEA_exclude_NOT_ND_",
        "DB_Object_Symbol"
      ),
      module_status = modules$module_status[[i]],
      stringsAsFactors = FALSE
    )
  }
  list(sets = sets, audit = do.call(rbind, audit))
}

gse_read_gencode_chromosomes <- function(path) {
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  collected <- list()
  block <- 0L
  repeat {
    lines <- readLines(con, n = 100000L, warn = FALSE, encoding = "UTF-8")
    if (!length(lines)) break
    hit <- !startsWith(lines, "#") & grepl("\tgene\t", lines, fixed = TRUE)
    if (!any(hit)) next
    fields <- strsplit(lines[hit], "\t", fixed = TRUE)
    fields <- fields[lengths(fields) >= 9L]
    attrs <- vapply(fields, `[[`, character(1L), 9L)
    symbols <- sub('.*gene_name "([^"]+)";.*', "\\1", attrs)
    valid <- symbols != attrs & nzchar(symbols)
    block <- block + 1L
    collected[[block]] <- data.frame(
      gene_symbol_upper = toupper(symbols[valid]),
      chromosome = sub("^chr", "", vapply(fields[valid], `[[`, character(1L), 1L),
                       ignore.case = TRUE), stringsAsFactors = FALSE
    )
  }
  map <- unique(do.call(rbind, collected))
  gse_assert(nrow(map) > 20000L, "Too few gene records parsed from GENCODE v19")
  chromosome_groups <- split(map$chromosome, map$gene_symbol_upper)
  chromosome_groups <- lapply(chromosome_groups, function(x) sort(unique(x)))
  data.frame(
    gene_symbol_upper = names(chromosome_groups),
    chromosome_labels = vapply(chromosome_groups, paste, character(1L), collapse = "|"),
    is_chr21 = vapply(chromosome_groups, function(x) "21" %in% x, logical(1L)),
    chromosome_mapping_ambiguous = lengths(chromosome_groups) > 1L,
    stringsAsFactors = FALSE, row.names = NULL
  )
}

gse_gencode_mapping_audit <- function(gene_symbols, chromosome_map) {
  symbols_upper <- toupper(gene_symbols)
  idx <- match(symbols_upper, chromosome_map$gene_symbol_upper)
  mapped <- !is.na(idx)
  ambiguous <- mapped & chromosome_map$chromosome_mapping_ambiguous[idx]
  chr21 <- mapped & chromosome_map$is_chr21[idx]
  gse_assert(sum(mapped) + sum(!mapped) == length(gene_symbols),
             "GENCODE mapping audit does not reconcile")
  data.frame(
    audit_scope = "all_input_HTSeq_gene_symbols_before_lineage_filtering",
    input_gene_symbols = length(gene_symbols),
    gencode_v19_mapped_symbols = sum(mapped),
    gencode_v19_unmapped_symbols = sum(!mapped),
    ambiguous_multichromosome_symbols = sum(ambiguous),
    chromosome_21_mapped_symbols = sum(chr21),
    chromosome_21_symbols_excluded_in_sensitivity = sum(chr21),
    matching_policy = "case_insensitive_primary_gene_symbol;any_chr21_mapping_is_excluded",
    stringsAsFactors = FALSE
  )
}

gse_prepare_annotations <- function(cache_dir, modules) {
  graph <- gse_read_obo(file.path(cache_dir, "references", "go-basic.obo"))
  gaf <- gse_read_human_gaf(file.path(cache_dir, "references", "HUMAN-uniprot.gaf.gz"))
  module_collection <- gse_build_modules(modules, graph, gaf)
  chromosomes <- gse_read_gencode_chromosomes(
    file.path(cache_dir, "references", "gencode.v19.annotation.gtf.gz")
  )
  list(modules = module_collection, chromosomes = chromosomes,
       ontology_summary = data.frame(active_terms = nrow(graph$terms),
                                     is_a_or_part_of_edges = nrow(graph$edges),
                                     retained_human_gaf_rows = nrow(gaf),
                                     stringsAsFactors = FALSE))
}
