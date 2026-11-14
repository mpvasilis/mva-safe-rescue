testthat::test_that("analysis-locked registries validate and designs are full rank", {
  testthat::expect_invisible(
    track2_validate_configuration(source_manifest, sample_manifest, contrasts,
                                  primary_modules, repo_root)
  )
  testthat::expect_identical(contrasts$ranking_eligible, c("TRUE", "FALSE", "FALSE"))
  testthat::expect_match(contrasts$estimand[contrasts$contrast_id == "CDXX_vs_CDXY"],
                        "chronological-age")
})

testthat::test_that("GSE301548 preserves the public batch-six column order", {
  batch6 <- sample_manifest[sample_manifest$dataset == "GSE301548" &
                              sample_manifest$batch == "6", , drop = FALSE]
  testthat::expect_identical(batch6$sample_id,
                            c("1209_2024", "1210_2024", "1211_2024", "1212_2024", "1213_2024"))
  testthat::expect_identical(batch6$condition, c("ORE", "C2L", "T2L", "CDXY", "CDXX"))
})

testthat::test_that("all inputs are public HTTPS sources with pinned SHA-256", {
  testthat::expect_true(all(grepl("^https://", source_manifest$url)))
  testthat::expect_true(all(grepl("^[0-9a-f]{64}$", source_manifest$sha256)))
  testthat::expect_false(any(grepl("(private|controlled|gated|secret)", source_manifest$destination,
                                  ignore.case = TRUE)))
  testthat::expect_true(all(grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                                  source_manifest$retrieval_date)))
  testthat::expect_true(all(nzchar(source_manifest$license_or_usage_status)))
})

testthat::test_that("module registry is fixed to 13 families", {
  testthat::expect_length(unique(primary_modules$module_id), 13L)
  testthat::expect_setequal(primary_modules$go_id,
    c("GO:0031577", "GO:0007059", "GO:0006119", "GO:0022904", "GO:0032543",
      "GO:0005761", "GO:0006986", "GO:0030968", "GO:0006457", "GO:0010498",
      "GO:0000502", "GO:0006914", "GO:0000422", "GO:0006979", "GO:0098869",
      "GO:0042254", "GO:0006396", "GO:0097150", "GO:0000278", "GO:0008283",
      "GO:0006974", "GO:0006281", "GO:0006915"))
  decision <- unique(primary_modules$module_id[
    primary_modules$post_primary_fixed_nomination_set == "TRUE"
  ])
  testthat::expect_setequal(decision,
    c("mitochondrial_energy", "proteostasis_stress", "folding_proteasome",
      "autophagy_mitophagy", "oxidative_stress", "oxidant_detox", "ribosome_RNA"))
})
