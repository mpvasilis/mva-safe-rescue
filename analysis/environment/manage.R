# Exact package-state capture/check/restore for each public R workflow.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L || !args[1] %in% c("snapshot", "check", "restore") ||
    !args[2] %in% c("track2", "external")) stop("Usage: Rscript manage.R snapshot|check|restore track2|external")
script <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[[1]])
here <- normalizePath(dirname(script), winslash = "/")
root <- normalizePath(file.path(here, "../.."), winslash = "/")
pipeline <- if (args[2] == "track2") file.path(root, "analysis/track2") else file.path(root, "analysis/external/GSE185192")
lib <- file.path(pipeline, ".Rlib")
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
libraries <- unique(c(lib, file.path(root, "analysis/track2/.Rlib"), .Library))
.libPaths(c(libraries, .libPaths()))
if (!requireNamespace("renv", quietly = TRUE)) stop("Install renv from CRAN into the workflow library before using this command")
lockfile <- file.path(here, paste0(args[2], ".renv.lock"))
options(repos = c(CRAN = "https://cloud.r-project.org", BioCsoft = "https://bioconductor.org/packages/3.23/bioc",
                 BioCann = "https://bioconductor.org/packages/3.23/data/annotation",
                 BioCexp = "https://bioconductor.org/packages/3.23/data/experiment"))
if (args[1] == "snapshot") {
  required <- c("DESeq2", "roastgsa", "digest", "fs", "jsonlite", "ggplot2", "renv")
  if (any(!vapply(required, requireNamespace, logical(1), quietly = TRUE))) stop("Cannot freeze an incomplete scientific environment")
  renv::snapshot(project = pipeline, library = libraries, lockfile = lockfile,
                 type = "all", prompt = FALSE, force = FALSE)
  quit(status = 0L)
}
lock <- renv::lockfile_read(lockfile)
if (as.character(getRversion()) != lock$R$Version) stop("R version differs from the frozen environment")
if (args[1] == "restore") renv::restore(project = pipeline, library = lib, lockfile = lockfile, prompt = FALSE)
wrong <- vapply(names(lock$Packages), function(p) {
  installed <- tryCatch(as.character(packageDescription(p, lib.loc = libraries, fields = "Version")), error = function(e) NA_character_)
  is.na(installed) || installed != lock$Packages[[p]]$Version
}, logical(1))
if (any(wrong)) stop("Environment mismatch: ", paste(names(wrong)[wrong], collapse = ", "))
cat("Exact environment verified:", args[2], "R", lock$R$Version, length(wrong), "package versions\n")
