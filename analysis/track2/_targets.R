library(targets)

track2_dir <- normalizePath(getwd(), winslash = "/", mustWork = TRUE)
repo_root <- normalizePath(file.path(track2_dir, "../.."), winslash = "/", mustWork = TRUE)
local_library <- file.path(track2_dir, ".Rlib")
if (dir.exists(local_library)) .libPaths(c(local_library, .libPaths()))

r_files <- list.files(file.path(track2_dir, "R"), pattern = "\\.R$", full.names = TRUE)
invisible(lapply(r_files, source, local = globalenv()))

options(mc.cores = 1L)
set.seed(20260826L)
tar_option_set(
  seed = 20260826L,
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient",
  retrieval = "main",
  deployment = "main"
)

config_paths <- file.path(track2_dir, "config",
                          c("source_manifest.tsv", "sample_manifest.tsv", "contrasts.tsv",
                            "primary_modules.tsv"))

list(
  tar_target(config_files, config_paths, format = "file"),
  tar_target(source_manifest, track2_read_tsv(config_files[[1L]])),
  tar_target(sample_manifest, track2_read_tsv(config_files[[2L]])),
  tar_target(contrasts, track2_read_tsv(config_files[[3L]])),
  tar_target(primary_modules, track2_read_tsv(config_files[[4L]])),
  tar_target(
    configuration_valid,
    track2_validate_configuration(source_manifest, sample_manifest, contrasts,
                                  primary_modules, repo_root)
  ),
  tar_target(
    public_source_files,
    {
      configuration_valid
      track2_download_and_verify_sources(source_manifest, repo_root,
                                         replace_invalid = FALSE,
                                         validate_structure = TRUE)$path
    },
    format = "file"
  ),
  tar_target(
    source_checksums,
    {
      public_source_files
      track2_verify_existing_sources(source_manifest, repo_root,
                                     analysis_only = FALSE, validate_structure = TRUE)
    }
  ),
  tar_target(
    primary_import,
    {
      public_source_files
      row <- source_manifest[source_manifest$source_id == "GSE290206_counts", , drop = FALSE]
      track2_import_count_workbook(track2_source_path(source_manifest, "GSE290206_counts", repo_root),
                                   row, sample_manifest)
    }
  ),
  tar_target(
    exploratory_import,
    {
      public_source_files
      row <- source_manifest[source_manifest$source_id == "GSE301548_counts", , drop = FALSE]
      track2_import_count_workbook(track2_source_path(source_manifest, "GSE301548_counts", repo_root),
                                   row, sample_manifest)
    }
  ),
  tar_target(primary_filter, track2_filter_counts(primary_import$counts, 10L, 3L)),
  tar_target(exploratory_filter, track2_filter_counts(exploratory_import$counts, 10L, 3L)),
  tar_target(
    gene_map,
    {
      public_source_files
      track2_read_gene_map(track2_source_path(source_manifest, "FlyBase_gene_map_FB2026_02", repo_root))
    }
  ),
  tar_target(primary_analysis, track2_run_primary(primary_import, primary_filter)),
  tar_target(direction_gate_sensitivity,
             track2_direction_gate_sensitivity(primary_analysis$de)),
  tar_target(
    module_collections,
    {
      public_source_files
      track2_module_collections(
        primary_modules,
        track2_source_path(source_manifest, "FlyBase_GO_graph_FB2026_02", repo_root),
        track2_source_path(source_manifest, "FlyBase_GAF_FB2026_02", repo_root)
      )
    }
  ),
  tar_target(
    module_primary,
    track2_run_roast_modules(primary_analysis$vst, primary_import$samples,
                             module_collections$include_iea, primary_analysis$de,
                             "include_IEA_exclude_NOT_ND", 20260826L, 9999L)
  ),
  tar_target(
    module_no_iea,
    track2_run_roast_modules(primary_analysis$vst, primary_import$samples,
                             module_collections$exclude_iea, primary_analysis$de,
                             "exclude_IEA_NOT_ND", 20260826L, 9999L)
  ),
  tar_target(
    leave_one_out,
    track2_leave_one_batch_out(primary_import, primary_filter, primary_analysis)
  ),
  tar_target(
    module_leave_one_out,
    track2_leave_one_batch_modules(
      primary_import, primary_analysis, module_collections$include_iea,
      module_primary, leave_one_out,
      unique(primary_modules$module_id[
        primary_modules$post_primary_fixed_nomination_set == "TRUE"
      ]),
      20260826L, 9999L
    )
  ),
  tar_target(exploratory, track2_run_exploratory(exploratory_import, contrasts, gene_map)),
  tar_target(
    human_signatures,
    {
      public_source_files
      track2_map_human_signatures(
        primary_analysis$de,
        track2_source_path(source_manifest, "FlyBase_orthologs_FB2026_02", repo_root)
      )
    }
  ),
  tar_target(
    qc_payload,
    track2_qc_payload(primary_import, primary_filter, primary_analysis,
                      exploratory_import, exploratory_filter)
  ),
  tar_target(sanity_checks, track2_sanity_checks(primary_analysis$de, gene_map, module_primary)),
  tar_target(
    result_files,
    track2_write_results(
      file.path(track2_dir, "results"), source_checksums, source_manifest,
      sample_manifest, contrasts, primary_modules, qc_payload, primary_analysis,
      gene_map, module_collections, module_primary, module_no_iea, leave_one_out,
      module_leave_one_out, direction_gate_sensitivity, exploratory,
      human_signatures, sanity_checks
    ),
    format = "file"
  ),
  tar_target(
    release_readme,
    file.path(track2_dir, "release", "README.md"),
    format = "file"
  ),
  tar_target(
    release_files,
    {
      result_files
      track2_refresh_release(
        file.path(track2_dir, "results"),
        file.path(track2_dir, "release"),
        release_readme
      )
    },
    format = "file"
  )
)
