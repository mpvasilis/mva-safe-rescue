# GSE134780: independent public mouse mechanism context

This is a new analysis of public BubR1 mouse expression data, performed on
9 September 2026 under the [locked protocol](PROTOCOL.md). It adds allele and
tissue context; it is not human MVA replication or a candidate-response test.

```console
python analysis/external/GSE134780/fetch.py
Rscript analysis/environment/manage.R check track2
Rscript analysis/external/GSE134780/run.R --self-test
Rscript analysis/external/GSE134780/run.R
```

Twenty-three deposited samples form six separate contrasts: H/L1002P versus
WT, H/H versus WT, and H/L1002P versus H/H within skeletal muscle and fat. A
predeclared 14-gene panel produces 84 tests with one panel-wide BH adjustment.
Support requires q <= 0.10 and absolute log2 fold change >= log2(1.25).
The run used R 4.6.1 / DESeq2 1.52.0, took 78.13 seconds, and emitted no fit
warnings. The complete [panel](release/target_context_panel.tsv), including
null and unavailable results, is released with hashes and normalized expression.

## Result and decision

Seventeen of 84 panel tests meet both criteria. None is the direct H/L1002P
versus H/H contrast. Hsf1 increases in fat for both genotypes (log2 changes
0.373 and 0.433; q 0.0423 and 0.0152). No Hspa1a, Hspa1b, or Hspa8 test supports
a coherent HSP70 expression claim. Hspd1 decreases in H/H muscle only (-0.390;
q 0.00890). Sod2 decreases in fat for both genotypes; Gpx1 increases in muscle.
No Crls1 or Taz test meets both panel criteria.

Cdkn2a and Cdkn1a are predeclared contextual controls, not novel discoveries.
Cdkn1a increases in muscle and decreases in fat in both genotype-versus-WT
comparisons. This illustrates why tissue-specific results cannot be pooled or
described as one universal stress-response signature.

**Consequence:** measure target engagement and functional rescue in the
qualified neural model. Neither drug moves up a ranking on these results.
RNA expression does not establish HSF1 activation, protein folding, cardiolipin
function, or response to arimoclomol or elamipretide. The fly primary result
remains 0/12 supported modules. Small groups, mixed genetic background,
unreported sex/exact age/litter, and bulk-tissue composition limit inference.

## Provenance and corrections

[GEO GSE134780](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE134780)
provides the public count file and sample records; `sources.json` records all
24 downloaded inputs. The protocol hash was checked before download and before
analysis. Upstream files stay in the ignored cache and are not redistributed.

The related [JCI study](https://www.jci.org/articles/view/126863) motivates
allele- and tissue-aware interpretation. Its [corrigendum](https://www.jci.org/articles/view/144781)
corrects a duplicated representative image in Figure 2E and adds mitotic-index
methods. It does not report a correction to this RNA-seq count file. This note
does not independently audit the original study.
