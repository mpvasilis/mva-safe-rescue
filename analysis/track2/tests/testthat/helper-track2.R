track2_dir <- normalizePath(file.path(testthat::test_path(), "../.."), winslash = "/", mustWork = TRUE)
repo_root <- normalizePath(file.path(track2_dir, "../.."), winslash = "/", mustWork = TRUE)
r_files <- list.files(file.path(track2_dir, "R"), pattern = "\\.R$", full.names = TRUE)
invisible(lapply(r_files, source, local = globalenv()))

source_manifest <- track2_read_tsv(file.path(track2_dir, "config", "source_manifest.tsv"))
sample_manifest <- track2_read_tsv(file.path(track2_dir, "config", "sample_manifest.tsv"))
contrasts <- track2_read_tsv(file.path(track2_dir, "config", "contrasts.tsv"))
primary_modules <- track2_read_tsv(file.path(track2_dir, "config", "primary_modules.tsv"))
