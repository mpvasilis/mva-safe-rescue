testthat::test_that("present GEO workbooks match exact public checksums", {
  geo <- source_manifest[source_manifest$source_id %in% c("GSE290206_counts", "GSE301548_counts"), , drop = FALSE]
  for (i in seq_len(nrow(geo))) {
    path <- file.path(repo_root, geo$destination[[i]])
    testthat::expect_true(file.exists(path), info = path)
    testthat::expect_identical(track2_sha256(path), geo$sha256[[i]])
  }
})

testthat::test_that("count import enforces dimensions, headers, identifiers, and integers", {
  testthat::skip_if_not_installed("readxl")
  row <- source_manifest[source_manifest$source_id == "GSE290206_counts", , drop = FALSE]
  imported <- track2_import_count_workbook(file.path(repo_root, row$destination), row, sample_manifest)
  testthat::expect_identical(dim(imported$counts), c(14150L, 6L))
  testthat::expect_identical(storage.mode(imported$counts), "integer")
  testthat::expect_false(anyDuplicated(rownames(imported$counts)) > 0L)
  testthat::expect_true(all(imported$counts >= 0L))
  filtered <- track2_filter_counts(imported$counts)
  testthat::expect_true(filtered$n_retained > 0L)
  testthat::expect_true(all(rowSums(filtered$counts >= 10L) >= 3L))
})

testthat::test_that("filter is exactly >=10 counts in >=3 samples", {
  counts <- matrix(as.integer(c(10, 10, 10, 0, 0, 0,
                                9, 9, 100, 100, 100, 0,
                                10, 10, 0, 0, 0, 0)), nrow = 3L, byrow = TRUE)
  rownames(counts) <- c("keep", "keep_two_high", "drop_two")
  colnames(counts) <- paste0("s", 1:6)
  out <- track2_filter_counts(counts)
  testthat::expect_identical(rownames(out$counts), c("keep", "keep_two_high"))
})
