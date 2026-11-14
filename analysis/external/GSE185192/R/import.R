gse_soft_field <- function(lines, key, multiple = FALSE) {
  if (identical(key, "supplementary_file")) {
    hits <- lines[grepl("^!Sample_supplementary_file_[0-9]+ = ", lines)]
    values <- sub("^!Sample_supplementary_file_[0-9]+ = ", "", hits)
  } else {
    prefix <- paste0("!Sample_", key, " = ")
    hits <- lines[startsWith(lines, prefix)]
    values <- sub(prefix, "", hits, fixed = TRUE)
  }
  if (multiple) return(values)
  if (length(values) != 1L) return(NA_character_)
  values[[1L]]
}

gse_parse_soft <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  chars <- gse_soft_field(lines, "characteristics_ch1", multiple = TRUE)
  char_value <- function(name) {
    hit <- chars[startsWith(tolower(chars), paste0(tolower(name), ":"))]
    if (length(hit) != 1L) return(NA_character_)
    trimws(sub("^[^:]+:", "", hit))
  }
  list(
    accession = gse_soft_field(lines, "geo_accession"),
    title = gse_soft_field(lines, "title"),
    organism = gse_soft_field(lines, "organism_ch1"),
    library_strategy = gse_soft_field(lines, "library_strategy"),
    cell_type = char_value("cell type"),
    strain = char_value("strain"),
    treatment = char_value("treatment"),
    cell_line = char_value("cell line"),
    supplementary_files = gse_soft_field(lines, "supplementary_file", multiple = TRUE),
    all_lines = lines
  )
}

gse_validate_sample_eligibility <- function(samples, cache_dir) {
  rows <- lapply(seq_len(nrow(samples)), function(i) {
    s <- samples[i, , drop = FALSE]
    parsed <- gse_parse_soft(file.path(cache_dir, "metadata", s$soft_file))
    checks <- c(
      accession = identical(parsed$accession, s$accession),
      organism = identical(parsed$organism, "Homo sapiens"),
      library_strategy = identical(parsed$library_strategy, "RNA-Seq"),
      treatment = identical(parsed$treatment, s$expected_treatment),
      cell_line = identical(parsed$cell_line, s$expected_cell_line),
      cell_type = identical(parsed$cell_type, s$expected_cell_type),
      strain = identical(parsed$strain, s$expected_strain),
      count_file = any(endsWith(parsed$supplementary_files, s$count_file))
    )
    data.frame(
      accession = s$accession, lineage = s$lineage, condition = s$condition,
      replicate = as.integer(s$replicate), title = parsed$title,
      observed_organism = parsed$organism, observed_library_strategy = parsed$library_strategy,
      observed_treatment = parsed$treatment, observed_cell_line = parsed$cell_line,
      observed_cell_type = parsed$cell_type, observed_strain = parsed$strain,
      accession_ok = checks[["accession"]], organism_ok = checks[["organism"]],
      library_strategy_ok = checks[["library_strategy"]], treatment_ok = checks[["treatment"]],
      cell_line_ok = checks[["cell_line"]], cell_type_ok = checks[["cell_type"]],
      strain_ok = checks[["strain"]], count_file_ok = checks[["count_file"]],
      eligible = all(checks), eligibility_basis = "GEO_SOFT_exact_fields",
      stringsAsFactors = FALSE
    )
  })
  out <- do.call(rbind, rows)
  failed <- out$accession[!out$eligible]
  gse_assert(!length(failed), "SOFT eligibility failed for: %s", paste(failed, collapse = ", "))
  out
}

gse_read_htseq <- function(path, min_rows = 10000L) {
  con <- gzfile(path, open = "rt")
  on.exit(close(con), add = TRUE)
  x <- utils::read.delim(con, header = FALSE, sep = "\t", quote = "",
                         comment.char = "", col.names = c("gene_symbol", "count"),
                         stringsAsFactors = FALSE)
  gse_assert(ncol(x) == 2L && nrow(x) > min_rows, "Unexpected HTSeq table: %s", path)
  gse_assert(!anyDuplicated(x$gene_symbol), "Duplicate gene symbols in %s", path)
  gse_assert(all(is.finite(x$count)) && all(x$count >= 0) && all(x$count == floor(x$count)),
             "Counts must be nonnegative integers in %s", path)
  summary <- x[startsWith(x$gene_symbol, "__"), , drop = FALSE]
  counts <- x[!startsWith(x$gene_symbol, "__"), , drop = FALSE]
  list(counts = counts, summary = summary)
}

gse_import_counts <- function(samples, cache_dir) {
  imported <- lapply(seq_len(nrow(samples)), function(i) {
    gse_read_htseq(file.path(cache_dir, "counts", samples$count_file[[i]]))
  })
  reference_symbols <- imported[[1L]]$counts$gene_symbol
  for (i in seq_along(imported)) {
    gse_assert(identical(imported[[i]]$counts$gene_symbol, reference_symbols),
               "Count gene rows/order differ for %s", samples$accession[[i]])
  }
  matrix_counts <- do.call(cbind, lapply(imported, function(x) x$counts$count))
  storage.mode(matrix_counts) <- "integer"
  rownames(matrix_counts) <- reference_symbols
  colnames(matrix_counts) <- samples$accession
  library_totals <- data.frame(
    accession = samples$accession, lineage = samples$lineage, condition = samples$condition,
    replicate = as.integer(samples$replicate), assigned_gene_counts = colSums(matrix_counts),
    htseq_no_feature = vapply(imported, function(x) {
      value <- x$summary$count[x$summary$gene_symbol == "__no_feature"]
      if (length(value)) value[[1L]] else NA_real_
    }, numeric(1L)), stringsAsFactors = FALSE
  )
  list(counts = matrix_counts, library_totals = library_totals)
}
