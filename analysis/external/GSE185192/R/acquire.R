gse_source_path <- function(cache_dir, cache_path) {
  normalizePath(file.path(cache_dir, cache_path), winslash = "/", mustWork = FALSE)
}

gse_verify_source <- function(row, cache_dir, candidate_path = NULL) {
  path <- if (is.null(candidate_path)) gse_source_path(cache_dir, row$cache_path) else candidate_path
  gse_assert(file.exists(path), "Missing pinned source %s at %s", row$source_id, row$cache_path)
  observed_bytes <- unname(file.info(path)$size)
  gse_assert(is.finite(observed_bytes) && observed_bytes == as.numeric(row$bytes),
             "Byte-count mismatch for %s: expected %s, observed %s",
             row$source_id, row$bytes, observed_bytes)
  observed_sha <- gse_sha256(path)
  gse_assert(identical(observed_sha, tolower(row$sha256)),
             "SHA-256 mismatch for %s: expected %s, observed %s",
             row$source_id, row$sha256, observed_sha)
  data.frame(source_id = row$source_id, kind = row$kind, cache_path = row$cache_path,
             expected_bytes = as.numeric(row$bytes), observed_bytes = observed_bytes,
             expected_sha256 = tolower(row$sha256), observed_sha256 = observed_sha,
             verified = TRUE, stringsAsFactors = FALSE)
}

gse_verify_sources <- function(sources, cache_dir) {
  do.call(rbind, lapply(seq_len(nrow(sources)), function(i) {
    gse_verify_source(sources[i, , drop = FALSE], cache_dir)
  }))
}

gse_download_sources <- function(sources, cache_dir) {
  dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
  verified <- vector("list", nrow(sources))
  for (i in seq_len(nrow(sources))) {
    row <- sources[i, , drop = FALSE]
    destination <- gse_source_path(cache_dir, row$cache_path)
    if (file.exists(destination)) {
      verified[[i]] <- gse_verify_source(row, cache_dir)
      next
    }
    dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
    partial <- tempfile(pattern = paste0(row$source_id, "_"), tmpdir = dirname(destination),
                        fileext = ".part")
    on.exit(if (file.exists(partial)) unlink(partial), add = TRUE)
    utils::download.file(row$url, partial, mode = "wb", method = "libcurl", quiet = FALSE)
    gse_verify_source(row, cache_dir, candidate_path = partial)
    gse_assert(file.rename(partial, destination), "Could not atomically accept %s", row$source_id)
    verified[[i]] <- gse_verify_source(row, cache_dir)
  }
  do.call(rbind, verified)
}
