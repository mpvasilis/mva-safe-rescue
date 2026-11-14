# GSE185192 local public-data cache

This ignored directory contains only public inputs retrieved for the fixed-settings analysis in `analysis/external/GSE185192`. It is not a redistribution bundle and must never contain challenge-gated, clinical, patient-level, credential-bearing, or private material.

Recorded retrieval: counts, SOFT records, GO basic OBO, and GENCODE v19 on 2026-08-26; matching dated HUMAN-UniProt GAF on 2026-08-27. The authoritative pinned registry is `analysis/external/GSE185192/config/sources.tsv`. It selects 12 untreated GEO HTSeq count files, 12 matching per-sample GEO SOFT records, GO basic OBO, HUMAN-UniProt GAF, and GENCODE v19 GTF. The pipeline validates byte counts and SHA-256 before use.

Provenance and purpose:

- NCBI GEO GSE185192 counts/metadata: public external neural-lineage challenge; https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE185192
- Versioned GO 2026-08-05 basic ontology and matching dated HUMAN-UniProt GAF: analysis-locked seven-module construction; https://release.geneontology.org/2026-08-05/ontology/go-basic.obo and https://release.geneontology.org/2026-08-05/annotations/gaf/HUMAN-uniprot.gaf.gz. Both are pinned by byte count and SHA-256.
- GENCODE v19: gene-symbol chromosome mapping and chromosome-21 sensitivity; https://ftp.ebi.ac.uk/pub/databases/gencode/Gencode_human/release_19/

Cached bytes are ignored by Git. Do not commit, mirror, attach, or repackage them. Cite GSE185192 and the primary publication, retain GO/GENCODE attribution, review [NCBI policies](https://www.ncbi.nlm.nih.gov/home/about/policies/) and source-specific terms, and record any unresolved redistribution question before a public release. Public provenance does not by itself establish a blanket license for every submitter-provided file.

Provenance preflight, 2026-08-27, working-tree manifest updated through 2026-08-27. The 27 exact URLs, byte counts, SHA-256 values, sample purposes, matching dated GO ontology and HUMAN-UniProt GAF URLs, non-redistribution boundary, and cited policy/attribution pages were reviewed. Disposition: local analysis and aggregate release may proceed only while all checks fail closed; this is not legal advice.

Final human sign-off is pending. Before public freeze, a named team provenance reviewer must confirm the committed manifest revision, source-specific attribution/terms, unresolved questions, and release disposition.
