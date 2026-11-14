gse_run_tests <- function(project_dir) {
  passed <- 0L
  test <- function(name, expr) {
    force(expr)
    passed <<- passed + 1L
    cat("PASS", name, "\n")
  }
  samples <- gse_read_tsv(file.path(project_dir, "config", "samples.tsv"))
  modules <- gse_read_tsv(file.path(project_dir, "config", "modules.tsv"))
  sources <- gse_read_tsv(file.path(project_dir, "config", "sources.tsv"))
  test("locked configuration", gse_validate_configs(samples, modules, sources))
  test("sample balance", {
    stopifnot(nrow(samples[samples$lineage == "NPC" & samples$condition == "Iso-T", ]) == 3L)
    stopifnot(nrow(samples[samples$lineage == "iPSC" & samples$condition == "Iso-E", ]) == 3L)
  })
  test("SOFT parser", {
    path <- tempfile(fileext = ".soft.txt")
    writeLines(c("^SAMPLE = GSMTEST", "!Sample_geo_accession = GSMTEST",
                 "!Sample_title = synthetic eligibility test", "!Sample_organism_ch1 = Homo sapiens",
                 "!Sample_library_strategy = RNA-Seq",
                 "!Sample_characteristics_ch1 = cell type: Neural Progenitor Cells",
                 "!Sample_characteristics_ch1 = strain: Control",
                 "!Sample_characteristics_ch1 = treatment: untreated",
                 "!Sample_characteristics_ch1 = cell line: AG05397",
                 "!Sample_supplementary_file_1 = ftp://example.test/counts.txt.gz"), path)
    parsed <- gse_parse_soft(path)
    stopifnot(parsed$accession == "GSMTEST", parsed$treatment == "untreated",
              endsWith(parsed$supplementary_files, "counts.txt.gz"))
  })
  test("HTSeq parser", {
    path <- tempfile(fileext = ".txt.gz")
    con <- gzfile(path, open = "wt")
    writeLines(c("GENE1\t4", "GENE2\t11", "__no_feature\t2"), con)
    close(con)
    parsed <- gse_read_htseq(path, min_rows = 1L)
    stopifnot(identical(parsed$counts$gene_symbol, c("GENE1", "GENE2")),
              parsed$summary$count[[1L]] == 2)
  })
  test("SHA-256 verification", {
    cache <- tempfile(pattern = "cache_")
    dir.create(cache)
    path <- file.path(cache, "fixture.bin")
    writeBin(charToRaw("public synthetic checksum fixture"), path)
    row <- data.frame(source_id = "fixture", kind = "test", url = "https://example.test",
                      cache_path = "fixture.bin", bytes = unname(file.info(path)$size),
                      sha256 = gse_sha256(path), retrieved_utc = "2026-08-26T00:00:00Z")
    verified <- gse_verify_source(row, cache)
    stopifnot(verified$verified)
  })
  test("rectangular TSV", {
    path <- tempfile(fileext = ".tsv")
    gse_write_tsv(data.frame(a = 1:2, b = c("x", "y")), path)
    gse_assert_rectangular_tsv(path)
  })
  test("release whitelist rejects unsafe and duplicate paths", {
    stopifnot(length(gse_release_payload_paths()) == 23L,
              all(c("pca_coordinates.tsv", "package_versions.tsv",
                    "gencode_mapping_audit.tsv", "manifests/full_result_hashes.tsv") %in%
                    gse_release_payload_paths()))
    valid <- data.frame(path = gse_release_payload_paths(), bytes = 1,
                        sha256 = strrep("0", 64), stringsAsFactors = FALSE)
    gse_validate_inventory_table(valid)
    unsafe <- valid
    unsafe$path[[1L]] <- "../escape.tsv"
    stopifnot(inherits(try(gse_validate_inventory_table(unsafe), silent = TRUE), "try-error"))
    duplicate <- valid
    duplicate$path[[2L]] <- duplicate$path[[1L]]
    stopifnot(inherits(try(gse_validate_inventory_table(duplicate), silent = TRUE), "try-error"))
    invalid_hash <- valid
    invalid_hash$sha256[[1L]] <- "not-a-sha"
    stopifnot(inherits(try(gse_validate_inventory_table(invalid_hash), silent = TRUE),
                         "try-error"))
    for (bad_path in c("C:/escape.tsv", "/escape.tsv", "nested\\escape.tsv")) {
      unsafe_variant <- valid
      unsafe_variant$path[[1L]] <- bad_path
      stopifnot(inherits(try(gse_validate_inventory_table(unsafe_variant), silent = TRUE),
                         "try-error"))
    }
  })
  test("release whitelist rejects unexpected files", {
    release_dir <- tempfile(pattern = "release_")
    dir.create(release_dir, recursive = TRUE)
    writeLines("unexpected", file.path(release_dir, "unexpected.txt"))
    stopifnot(inherits(try(gse_assert_no_stale_release_files(release_dir), silent = TRUE),
                         "try-error"))
    unlink(file.path(release_dir, "unexpected.txt"))
    writeLines("hidden unexpected", file.path(release_dir, ".unexpected"))
    stopifnot(inherits(try(gse_assert_no_stale_release_files(release_dir), silent = TRUE),
                         "try-error"))
  })
  test("authoritative module q-value is the only decision field", {
    release_source <- paste(readLines(file.path(project_dir, "R", "release.R"), warn = FALSE),
                            collapse = "\n")
    stopifnot(grepl("module_qvalue_BH_n7_authoritative", release_source, fixed = TRUE))
    stopifnot(!grepl("modules$module_qvalue)", release_source, fixed = TRUE))
    stopifnot(!grepl('"module_qvalue")', release_source, fixed = TRUE))
    model_source <- paste(readLines(file.path(project_dir, "R", "model.R"), warn = FALSE),
                          collapse = "\n")
    stopifnot(grepl("p.adjust(out$pvalue[finite], method = \"BH\", n = 7L)",
                   model_source, fixed = TRUE))
    stopifnot(grepl("evaluable_only_transparency_column_not_used_for_decisions",
                   model_source, fixed = TRUE))
  })
  test("GENCODE mapping audit reconciles", {
    map <- data.frame(gene_symbol_upper = c("A", "B", "C"),
                      chromosome_labels = c("1", "21", "2|21"),
                      is_chr21 = c(FALSE, TRUE, TRUE),
                      chromosome_mapping_ambiguous = c(FALSE, FALSE, TRUE))
    audit <- gse_gencode_mapping_audit(c("A", "b", "C", "UNMAPPED"), map)
    stopifnot(audit$input_gene_symbols == 4L,
              audit$gencode_v19_mapped_symbols == 3L,
              audit$gencode_v19_unmapped_symbols == 1L,
              audit$ambiguous_multichromosome_symbols == 1L,
              audit$chromosome_21_symbols_excluded_in_sensitivity == 2L)
  })
  test("inventory writer and verifier share one canonical sidecar", {
    project_fixture <- tempfile(pattern = "project_contract_")
    release_dir <- file.path(project_fixture, "release")
    dir.create(release_dir, recursive = TRUE)
    results_dir <- file.path(project_fixture, "results")
    result_paths <- file.path(results_dir, "de", paste0(gse_full_result_ids(), ".tsv.gz"))
    dir.create(dirname(result_paths[[1L]]), recursive = TRUE)
    for (i in seq_along(result_paths)) {
      writeBin(charToRaw(paste0("authoritative-full-result-fixture-", i)), result_paths[[i]])
    }
    full_result_fixture <- gse_full_result_hashes(results_dir)
    for (relative in gse_release_payload_paths()) {
      path <- file.path(release_dir, relative)
      dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
      if (relative == "manifests/full_result_hashes.tsv") {
        gse_write_tsv(full_result_fixture, path)
      } else if (endsWith(relative, ".tsv")) {
        gse_write_tsv(data.frame(fixture = "ok"), path)
      } else {
        writeLines("fixture", path, useBytes = TRUE)
      }
    }
    gse_write_inventory(release_dir)
    sidecar <- readLines(file.path(release_dir, "release_inventory.sha256"), warn = FALSE)
    stopifnot(length(sidecar) == 1L,
              grepl("^[0-9a-f]{64} release_inventory\\.tsv$", sidecar))
    stopifnot(gse_verify_release(release_dir))
  })
  test("JSON records omit row names and serialize missing numerics as null", {
    fixture <- data.frame(id = c("full", "excluded"), value = c(1, NA_real_))
    rownames(fixture) <- c("named_full", "named_excluded")
    path <- tempfile(fileext = ".json")
    jsonlite::write_json(list(rows = gse_json_records(fixture)), path,
                         pretty = TRUE, auto_unbox = TRUE, na = "null")
    text <- paste(readLines(path, warn = FALSE), collapse = "\n")
    stopifnot(!grepl('"_row"', text, fixed = TRUE),
              !grepl('"value": {}', text, fixed = TRUE),
              grepl('"value": null', text, fixed = TRUE))
  })
  test("R files parse", {
    files <- c(list.files(file.path(project_dir, "R"), pattern = "\\.R$", full.names = TRUE),
               file.path(project_dir, "run.R"), file.path(project_dir, "bootstrap.R"))
    invisible(lapply(files, parse))
  })
  cat(sprintf("All %d offline tests passed.\n", passed))
  invisible(TRUE)
}
