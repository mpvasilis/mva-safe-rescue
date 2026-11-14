# GSE134780: independent BubR1 allele-context challenge

Analysis plan recorded on 2026-09-09 before downloading or inspecting the count
matrix. The study article and GEO sample metadata were already inspected. This
is a dated local analysis lock, not external preregistration or blinded discovery.

Question: does an independent, gene-specific mouse MVA model support treating
different BubR1 alleles and tissues as biologically interchangeable when choosing
a downstream-support experiment? This evaluates model applicability and the
candidate-target expression context. It does not measure response to any drug.

## Inputs and eligibility

- Public GEO GSE134780, deposited by the authors of Sieben et al., JCI 2020,
  DOI 10.1172/JCI126863. Read the linked corrigendum, DOI 10.1172/JCI144781.
- Raw gene counts from the declared GEO supplementary file, fetched over HTTPS.
- Twenty-three samples: gastrocnemius muscle, WT n=4, H/L1002P n=4, H/H n=3;
  inguinal adipose tissue, WT n=4, H/L1002P n=4, H/H n=4.
- The declared age window is 8-10 months and genetic background is mixed
  129Sve/C57BL/6. Sex, exact age, litter and cross-tissue pairing are not exposed
  by the inspected metadata. Do not invent covariates or pair tissues by suffix.
- Analyze tissues separately. Do not combine them with fly, trisomy-21, or
  three-month monoallelic carrier samples. No sample exclusion based on outcome.
- Stop on duplicate genes, missing samples, negative/noninteger counts, or
  mismatch between the matrix and expected tissue/genotype sample groups.

## Locked methods

For each tissue, retain genes with count >=10 in at least three samples. Fit
DESeq2 with design `~ genotype`, WT reference, median-ratio size factors, default
dispersion estimation and Wald testing. Disable automatic count replacement
(`minReplicatesForReplace=Inf`) and set `cooksCutoff=FALSE` and
`independentFiltering=FALSE` for results. Report unshrunken log2 fold change,
standard error, p value, adjusted p value, and sample counts. No gene ranking is
used to choose a drug. Record model convergence and any warnings.

The three contrasts in each tissue are H/L1002P minus WT, H/H minus WT, and
H/L1002P minus H/H. Six contrasts are kept separate. Report BH adjustment within
each full transcriptome as descriptive context; no pathway enrichment analysis
or overlap-based drug ranking is added after inspecting results.

The preselected target-context panel contains exactly 14 mouse symbols:
`Bub1b`, `Hsf1`, `Hspa1a`, `Hspa1b`, `Hspa8`, `Hspd1`, `Hspe1`, `Crls1`,
`Taz`, `Ppargc1a`, `Sod2`, `Gpx1`, `Cdkn2a`, `Cdkn1a`.

These symbols reflect the existing HSF1/HSP70 probe, HSP60 mismatch, mitochondrial
benchmark and redox controls. Bub1b is a model-context check; Cdkn2a/Cdkn1a are
literature-informed senescence controls, not independent discovery endpoints.
No direction is required, and both positive and negative findings are retained.
Panel decisions use BH over **84 configured tests** (14 genes times six
contrasts), with absent or unevaluable tests retained in the denominator.
Expression support requires q <=0.10 and |log2FC| >=log2(1.25). It supports an
expression-context statement only. Missing symbols are explicit and are not
replaced by favorable genes. RNA expression cannot establish protein activity,
drug target engagement, rescue, cancer safety, or the challenge case mechanism.

For interpretation, report whether each target-axis result agrees between the
two mutant-versus-WT contrasts, and show the direct allele contrast. A sign
difference alone is descriptive, not a statistically supported interaction.

## Release and falsifiers

Release only the panel table, all-contrast aggregate counts, normalized panel
expression, sample manifest, warnings, versions and input/output hashes. Keep
downloaded inputs and complete genome-wide tables in ignored public caches.
Do not overwrite earlier primary or external releases.

The result may strengthen, weaken, or leave unchanged the model-applicability
argument. It cannot rescue the primary fly 0/12 module null, identify the child's
allele, or promote either medication to a validated lead. Model age, non-neural
tissue, genetic background, survivor selection and missing covariates limit
translation. Both cohorts came from the same study and are not independent
human replication. The paper reports that experiments were not randomized or
blinded; this limits causal interpretation.

Sources: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE134780;
https://jci.org/articles/view/126863;
https://jci.org/articles/view/144781.
