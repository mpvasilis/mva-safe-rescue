# Frozen public R environments

`track2.renv.lock` and `external.renv.lock` capture the full installed package
state with renv. They include dependencies, source provenance and the exact R
version rather than only listing directly imported libraries. The mouse
GSE134780 extension uses the Track 2 environment.

Run from the repository root with R 4.6.1:

```console
Rscript analysis/environment/manage.R check track2
Rscript analysis/environment/manage.R check external
Rscript analysis/environment/manage.R restore track2
Rscript analysis/environment/manage.R restore external
```

Restore requires renv, an available compiler/toolchain for source-only packages,
and access to the upstream repositories. Install renv from CRAN into the
relevant `.Rlib` first if it is absent. Each restore targets that pipeline's
isolated library. The external runner can also use the frozen Track 2 library
as an explicit local fallback; version checks inspect that same search order.
It does not update the frozen scientific outputs.

For a Windows installation not on PATH, find `InstallPath` in
`HKCU/Software/R-core/R` or `HKLM/Software/R-core/R`, then use its `bin/Rscript.exe`.
Use `LANG=C` and `LC_ALL=C` when the Windows runtime does not accept `C.UTF-8`.

`snapshot` is a deliberate maintainer operation. Do not call it to hide a failed
check or silently replace a dependency. A lockfile and successful version check
do not prove that a clean restore, a different operating system, or a scientific
rerun produces identical results. The improvement status records which checks
actually ran.

Source: [renv snapshot and restore documentation](https://rstudio.github.io/renv/reference/snapshot.html).
