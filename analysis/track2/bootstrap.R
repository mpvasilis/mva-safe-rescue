args <- commandArgs(trailingOnly = TRUE)
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[[1L]]) else "analysis/track2/bootstrap.R"
track2_dir <- normalizePath(dirname(script_path), winslash = "/", mustWork = TRUE)
local_library <- file.path(track2_dir, ".Rlib")
dir.create(local_library, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(local_library, .libPaths()))
options(Ncpus = 1L, repos = c(CRAN = "https://cloud.r-project.org"))

if (!(R.version$major == "4" && grepl("^6\\.", R.version$minor))) {
  stop("Track 2 requires R 4.6.x; observed ", R.version.string, call. = FALSE)
}
if (length(setdiff(args, "--check"))) {
  stop("Unknown bootstrap arguments: ", paste(setdiff(args, "--check"), collapse = ", "), call. = FALSE)
}

cran_packages <- c("targets", "testthat", "readxl", "digest", "jsonlite", "ggplot2", "data.table")
bioc_packages <- c("DESeq2", "apeglm", "roastgsa")

in_local_library <- function(package) {
  nzchar(system.file(package = package, lib.loc = local_library))
}

if (!"--check" %in% args) {
  if (!in_local_library("BiocManager")) {
    install.packages("BiocManager", lib = local_library,
                     dependencies = c("Depends", "Imports", "LinkingTo"))
  }
  suppressPackageStartupMessages(library("BiocManager", lib.loc = local_library, character.only = TRUE))
  if (as.character(BiocManager::version()) != "3.23") {
    BiocManager::install(version = "3.23", ask = FALSE, update = FALSE, lib = local_library)
  }
  missing_cran <- cran_packages[!vapply(cran_packages, in_local_library, logical(1L))]
  if (length(missing_cran)) {
    install.packages(missing_cran, lib = local_library,
                     dependencies = c("Depends", "Imports", "LinkingTo"))
  }
  missing_bioc <- bioc_packages[!vapply(bioc_packages, in_local_library, logical(1L))]
  if (length(missing_bioc)) {
    BiocManager::install(missing_bioc, ask = FALSE, update = FALSE, lib = local_library,
                         dependencies = c("Depends", "Imports", "LinkingTo"))
  }
}

required <- c("BiocManager", cran_packages, bioc_packages)
missing <- required[!vapply(required, in_local_library, logical(1L))]
if (length(missing)) {
  stop("Local Track 2 library is incomplete: ", paste(missing, collapse = ", "), call. = FALSE)
}
if (as.character(BiocManager::version()) != "3.23") {
  stop("Bioconductor 3.23 is required; BiocManager reports ", BiocManager::version(), call. = FALSE)
}
cat("Track 2 local library is ready at:", normalizePath(local_library, winslash = "/"), "\n")
cat("R:", R.version.string, "\nBioconductor: 3.23\n")
for (package in c(cran_packages, bioc_packages)) {
  cat(sprintf("%-12s %s\n", package, as.character(utils::packageVersion(package, lib.loc = local_library))))
}
