script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1L]]) else "analysis/track2/tests/testthat.R"
tests_dir <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
track2_dir <- normalizePath(file.path(tests_dir, ".."), winslash = "/", mustWork = TRUE)
local_library <- file.path(track2_dir, ".Rlib")
if (dir.exists(local_library)) .libPaths(c(local_library, .libPaths()))
if (!requireNamespace("testthat", quietly = TRUE)) {
  stop("Package 'testthat' is missing. Run analysis/track2/bootstrap.R first.", call. = FALSE)
}
testthat::test_dir(file.path(tests_dir, "testthat"), reporter = "summary", stop_on_failure = TRUE)
