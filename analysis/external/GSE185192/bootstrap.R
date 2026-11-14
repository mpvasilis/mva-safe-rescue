args <- commandArgs(trailingOnly = TRUE)
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1L]]) else
  "analysis/external/GSE185192/bootstrap.R"
project_dir <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
local_library <- file.path(project_dir, ".Rlib")
dir.create(local_library, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(local_library, .libPaths()))
options(Ncpus = 1L, repos = c(CRAN = "https://cloud.r-project.org"))
if (!(R.version$major == "4" && grepl("^6\\.", R.version$minor))) {
  stop("This pipeline requires R 4.6.x; observed ", R.version.string, call. = FALSE)
}
if (length(setdiff(args, "--check"))) stop("Unknown bootstrap arguments", call. = FALSE)
cran <- c("digest", "fs", "jsonlite", "ggplot2")
bioc <- c("DESeq2", "roastgsa")
in_local <- function(package) nzchar(system.file(package = package, lib.loc = local_library))
if (!"--check" %in% args) {
  if (!in_local("BiocManager")) install.packages("BiocManager", lib = local_library,
                                                  dependencies = c("Depends", "Imports", "LinkingTo"))
  suppressPackageStartupMessages(library("BiocManager", lib.loc = local_library,
                                         character.only = TRUE))
  if (as.character(BiocManager::version()) != "3.23") {
    BiocManager::install(version = "3.23", ask = FALSE, update = FALSE, lib = local_library)
  }
  missing_cran <- cran[!vapply(cran, in_local, logical(1L))]
  if (length(missing_cran)) install.packages(missing_cran, lib = local_library,
                                             dependencies = c("Depends", "Imports", "LinkingTo"))
  missing_bioc <- bioc[!vapply(bioc, in_local, logical(1L))]
  if (length(missing_bioc)) BiocManager::install(missing_bioc, ask = FALSE, update = FALSE,
                                                  lib = local_library,
                                                  dependencies = c("Depends", "Imports", "LinkingTo"))
}
required <- c("BiocManager", cran, bioc)
missing <- required[!vapply(required, in_local, logical(1L))]
if (length(missing)) stop("Local library incomplete: ", paste(missing, collapse = ", "), call. = FALSE)
cat("GSE185192 local R library ready.\n")
for (package in required) cat(package, as.character(utils::packageVersion(package,
                                                                           lib.loc = local_library)), "\n")
