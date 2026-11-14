track2_stop <- function(...) {
  stop(sprintf(...), call. = FALSE)
}

track2_assert <- function(ok, ...) {
  if (!isTRUE(ok)) track2_stop(...)
  invisible(TRUE)
}

track2_read_tsv <- function(path) {
  track2_assert(file.exists(path), "Required configuration file is missing: %s", path)
  out <- utils::read.delim(
    path,
    header = TRUE,
    sep = "\t",
    quote = "",
    comment.char = "",
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = character()
  )
  track2_assert(nrow(out) > 0L, "Configuration file is empty: %s", path)
  out
}

track2_sha256 <- function(path) {
  track2_assert(file.exists(path), "Cannot hash missing file: %s", path)

  if (requireNamespace("digest", quietly = TRUE)) {
    return(tolower(digest::digest(path, algo = "sha256", file = TRUE, serialize = FALSE)))
  }

  sha256sum <- Sys.which("sha256sum")
  if (nzchar(sha256sum)) {
    ans <- system2(sha256sum, args = shQuote(normalizePath(path)), stdout = TRUE, stderr = TRUE)
    hit <- regmatches(ans, regexpr("[0-9A-Fa-f]{64}", ans))
    hit <- hit[nchar(hit) == 64L]
    if (length(hit)) return(tolower(hit[[1L]]))
  }

  shasum <- Sys.which("shasum")
  if (nzchar(shasum)) {
    ans <- system2(shasum, args = c("-a", "256", shQuote(normalizePath(path))), stdout = TRUE, stderr = TRUE)
    hit <- regmatches(ans, regexpr("[0-9A-Fa-f]{64}", ans))
    hit <- hit[nchar(hit) == 64L]
    if (length(hit)) return(tolower(hit[[1L]]))
  }

  certutil <- Sys.which("certutil")
  if (nzchar(certutil)) {
    ans <- system2(certutil, args = c("-hashfile", shQuote(normalizePath(path)), "SHA256"), stdout = TRUE, stderr = TRUE)
    compact <- gsub("[^0-9A-Fa-f]", "", ans)
    hit <- compact[nchar(compact) == 64L]
    if (length(hit)) return(tolower(hit[[1L]]))
  }

  track2_stop("No SHA-256 implementation is available. Install digest or provide sha256sum/shasum/certutil.")
}

track2_expected_headers <- function(value) {
  if (is.na(value) || !nzchar(value)) return(character())
  strsplit(value, "|", fixed = TRUE)[[1L]]
}

track2_validate_xlsx <- function(path, manifest_row) {
  track2_assert(requireNamespace("readxl", quietly = TRUE),
                "Package 'readxl' is required for workbook structure validation. Run bootstrap.R.")
  expected_sheet <- manifest_row$expected_sheet[[1L]]
  sheets <- readxl::excel_sheets(path)
  track2_assert(identical(sheets, expected_sheet),
                "%s sheet mismatch: expected exactly '%s'; observed %s",
                manifest_row$source_id[[1L]], expected_sheet, paste(sheets, collapse = ", "))

  tab <- readxl::read_excel(path, sheet = expected_sheet, col_types = "text", .name_repair = "minimal")
  expected_rows <- as.integer(manifest_row$expected_rows[[1L]])
  expected_columns <- as.integer(manifest_row$expected_columns[[1L]])
  expected_headers <- track2_expected_headers(manifest_row$expected_headers[[1L]])

  track2_assert(nrow(tab) == expected_rows,
                "%s row mismatch: expected %d data rows; observed %d",
                manifest_row$source_id[[1L]], expected_rows, nrow(tab))
  track2_assert(ncol(tab) == expected_columns,
                "%s column mismatch: expected %d columns; observed %d",
                manifest_row$source_id[[1L]], expected_columns, ncol(tab))
  track2_assert(identical(names(tab), expected_headers),
                "%s header mismatch. Expected [%s]; observed [%s]",
                manifest_row$source_id[[1L]], paste(expected_headers, collapse = ", "),
                paste(names(tab), collapse = ", "))
  invisible(TRUE)
}

track2_verify_source <- function(manifest_row, repo_root, validate_structure = TRUE) {
  path <- file.path(repo_root, manifest_row$destination[[1L]])
  track2_assert(file.exists(path), "Pinned public source is missing: %s", path)
  observed <- track2_sha256(path)
  expected <- tolower(manifest_row$sha256[[1L]])
  track2_assert(identical(observed, expected),
                "Checksum mismatch for %s. Expected %s; observed %s. The source was not modified.",
                manifest_row$source_id[[1L]], expected, observed)
  if (validate_structure && identical(manifest_row$file_format[[1L]], "xlsx")) {
    track2_validate_xlsx(path, manifest_row)
  }
  data.frame(
    source_id = manifest_row$source_id[[1L]],
    path = normalizePath(path, winslash = "/", mustWork = TRUE),
    sha256 = observed,
    bytes = unname(file.info(path)$size),
    stringsAsFactors = FALSE
  )
}

track2_download_source <- function(manifest_row, repo_root, replace_invalid = FALSE,
                                   validate_structure = TRUE) {
  destination <- file.path(repo_root, manifest_row$destination[[1L]])
  dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)

  if (file.exists(destination)) {
    observed <- track2_sha256(destination)
    if (identical(observed, tolower(manifest_row$sha256[[1L]]))) {
      return(track2_verify_source(manifest_row, repo_root, validate_structure))
    }
    track2_assert(replace_invalid,
                  paste0("Existing public source has the wrong checksum and will not be overwritten: %s. ",
                         "Remove it explicitly or rerun with replace_invalid = TRUE."), destination)
  }

  suffix <- paste0(".", basename(destination), ".download")
  tmp <- tempfile(pattern = "track2-", tmpdir = dirname(destination), fileext = suffix)
  on.exit(unlink(tmp, force = TRUE), add = TRUE)
  status <- tryCatch({
    utils::download.file(manifest_row$url[[1L]], tmp, mode = "wb", method = "libcurl", quiet = FALSE)
  }, error = function(e) e)
  if (inherits(status, "error")) {
    track2_stop("Download failed for %s from %s: %s",
                manifest_row$source_id[[1L]], manifest_row$url[[1L]], conditionMessage(status))
  }
  track2_assert(identical(status, 0L), "Download returned status %s for %s", status,
                manifest_row$source_id[[1L]])
  observed <- track2_sha256(tmp)
  expected <- tolower(manifest_row$sha256[[1L]])
  track2_assert(identical(observed, expected),
                "Downloaded checksum mismatch for %s. Expected %s; observed %s.",
                manifest_row$source_id[[1L]], expected, observed)

  if (file.exists(destination)) unlink(destination, force = TRUE)
  moved <- file.rename(tmp, destination)
  track2_assert(moved, "Verified download could not be moved to %s", destination)
  track2_verify_source(manifest_row, repo_root, validate_structure)
}

track2_download_and_verify_sources <- function(source_manifest, repo_root,
                                               replace_invalid = FALSE,
                                               validate_structure = TRUE) {
  required <- c("source_id", "url", "destination", "sha256", "file_format",
                "required_in_analysis")
  track2_assert(all(required %in% names(source_manifest)),
                "source_manifest.tsv is missing columns: %s",
                paste(setdiff(required, names(source_manifest)), collapse = ", "))
  track2_assert(!anyDuplicated(source_manifest$source_id), "source_manifest source_id values are not unique")
  track2_assert(!anyDuplicated(source_manifest$destination), "source_manifest destinations are not unique")
  track2_assert(all(grepl("^https://", source_manifest$url)), "All source URLs must use HTTPS")
  track2_assert(all(grepl("^[0-9a-f]{64}$", source_manifest$sha256)),
                "Every source must have a lowercase 64-character SHA-256")

  rows <- lapply(seq_len(nrow(source_manifest)), function(i) {
    track2_download_source(source_manifest[i, , drop = FALSE], repo_root,
                           replace_invalid = replace_invalid,
                           validate_structure = validate_structure)
  })
  do.call(rbind, rows)
}

track2_verify_existing_sources <- function(source_manifest, repo_root,
                                           analysis_only = FALSE,
                                           validate_structure = TRUE) {
  selected <- source_manifest
  if (analysis_only) {
    selected <- selected[toupper(selected$required_in_analysis) == "TRUE", , drop = FALSE]
  }
  rows <- lapply(seq_len(nrow(selected)), function(i) {
    track2_verify_source(selected[i, , drop = FALSE], repo_root, validate_structure)
  })
  do.call(rbind, rows)
}

track2_source_path <- function(source_manifest, source_id, repo_root) {
  hit <- source_manifest$source_id == source_id
  track2_assert(sum(hit) == 1L, "Expected exactly one source_manifest row for %s", source_id)
  file.path(repo_root, source_manifest$destination[hit])
}
