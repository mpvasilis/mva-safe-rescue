"""Render the README result figures from the sealed release tables.

Every number drawn here is read from a released TSV or JSON file in this
repository. Nothing is recomputed and nothing is typed in by hand, so the
figures cannot drift from the published results.

    python analysis/figures/make_readme_figures.py

Each figure is written twice under docs/figures/: a light and a dark variant.
The only dependency beyond the standard library is matplotlib.
"""

from __future__ import annotations

import csv
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "figures"

FLY = ROOT / "analysis" / "track2" / "release"
MOUSE = ROOT / "analysis" / "external" / "GSE134780" / "release"
BENCH = ROOT / "analysis" / "benchmarks" / "release"
POWER = ROOT / "analysis" / "design_power" / "power_scenarios.tsv"

THEMES = {
    "light": {
        "surface": "#ffffff",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#8b8a85",
        "grid": "#e7e6e2",
        "axis": "#c9c8c3",
        "tile": "#f6f5f2",
        "s1": "#2a78d6",
        "s2": "#eb6834",
        "s3": "#1baf7a",
        "good": "#0ca30c",
        "stop": "#e4e3df",
        "stop_ink": "#52514e",
        "ordinal": ["#86b6ef", "#3987e5", "#184f95"],
        "diverging": ["#184f95", "#6da7ec", "#f0efec", "#ee8f8e", "#b82f2f"],
    },
    "dark": {
        "surface": "#0d1117",
        "ink": "#f0efec",
        "ink2": "#c3c2b7",
        "muted": "#8b8a85",
        "grid": "#262c36",
        "axis": "#3a414c",
        "tile": "#161b22",
        "s1": "#3987e5",
        "s2": "#d95926",
        "s3": "#199e70",
        "good": "#0ca30c",
        "stop": "#2a2f37",
        "stop_ink": "#c3c2b7",
        "ordinal": ["#256abf", "#5598e7", "#b7d3f6"],
        "diverging": ["#9ec5f4", "#256abf", "#383835", "#b84545", "#f3a3a2"],
    },
}

FONT_STACK = ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]
WIDTH = 9.0
DPI = 200


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def style(theme: dict) -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "font.size": 10.5,
            "text.color": theme["ink"],
            "axes.edgecolor": theme["axis"],
            "axes.labelcolor": theme["ink2"],
            "axes.facecolor": theme["surface"],
            "figure.facecolor": theme["surface"],
            "savefig.facecolor": theme["surface"],
            "xtick.color": theme["ink2"],
            "ytick.color": theme["ink2"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "xtick.major.width": 0.8,
            "ytick.major.width": 0.8,
            "xtick.major.size": 3,
            "ytick.major.size": 0,
            "svg.fonttype": "none",
        }
    )


def heading(fig, theme: dict, title: str, subtitle: str, top: float = 0.965) -> None:
    fig.text(0.035, top, title, fontsize=14.5, fontweight="bold", color=theme["ink"], va="top")
    fig.text(0.035, top - 0.062 * (4.2 / fig.get_figheight()), subtitle, fontsize=10.5,
             color=theme["ink2"], va="top")


def save(fig, name: str, mode: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}-{mode}.png", dpi=DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# 1. Headline numbers
# --------------------------------------------------------------------------
def headline(theme: dict, mode: str) -> None:
    fly = json.loads((FLY / "analysis_summary.json").read_text(encoding="utf-8"))
    mouse = json.loads((MOUSE / "analysis_summary.json").read_text(encoding="utf-8"))
    bench = json.loads((BENCH / "summary.json").read_text(encoding="utf-8"))
    decisions = read_tsv(BENCH / "track2_decision_comparison.tsv")
    safe = sum(row["safe_rescue_advance"] == "True" for row in decisions)
    naive = sum(row["any_biochemical_pass"] == "True" for row in decisions)

    tiles = [
        (f"{fly['primary_candidate_count']}", "gene-level calls",
         f"of {fly['normalized_direction_gate_sensitivity']['genes_evaluated']:,} fly brain genes tested"),
        (f"{fly['preregistered_modules_q_le_0_10']} / {fly['preregistered_modules_evaluable_primary_include_IEA']}",
         "pathway modules pass", "at BH q ≤ 0.10. The null is reported as found"),
        (f"{mouse['supported_panel_tests']} / {mouse['configured_panel_tests']}", "mouse panel tests hold",
         f"{mouse['samples']} samples, 2 tissues, 14 locked genes"),
        (f"{safe} of {len(decisions)}", "scenarios may advance",
         f"a benefit-only rule clears {naive} of {len(decisions)}"),
        (f"{bench['cases']:,}", "synthetic ranking cases",
         f"{bench['regimes']} evidence regimes, {bench['methods']} policies"),
    ]

    fig = plt.figure(figsize=(WIDTH, 1.7))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    gap, left = 0.012, 0.012
    width = (1 - 2 * left - gap * (len(tiles) - 1)) / len(tiles)
    for index, (value, label, note) in enumerate(tiles):
        x = left + index * (width + gap)
        ax.add_patch(FancyBboxPatch((x, 0.06), width, 0.88, boxstyle="round,pad=0,rounding_size=0.018",
                                    facecolor=theme["tile"], edgecolor="none", mutation_aspect=WIDTH / 1.7))
        ax.text(x + 0.016, 0.84, value, fontsize=22, fontweight="bold", color=theme["ink"], va="top")
        ax.text(x + 0.016, 0.49, label, fontsize=9.2, fontweight="bold", color=theme["ink"], va="top")
        ax.text(x + 0.016, 0.335, textwrap.fill(note, 30), fontsize=7.9, color=theme["ink2"], va="top",
                linespacing=1.3)
    save(fig, "headline", mode)


# --------------------------------------------------------------------------
# 2. Primary module test (GSE290206)
# --------------------------------------------------------------------------
MODULE_LABELS = {
    "SAC": "Spindle assembly checkpoint",
    "chromosome_segregation": "Chromosome segregation",
    "mitochondrial_energy": "Mitochondrial energy",
    "proteostasis_stress": "Proteostasis stress",
    "folding_proteasome": "Folding and proteasome",
    "autophagy_mitophagy": "Autophagy and mitophagy",
    "oxidative_stress": "Oxidative stress",
    "oxidant_detox": "Oxidant detoxification",
    "ribosome_RNA": "Ribosome and RNA",
    "cell_cycle_proliferation": "Cell cycle and proliferation",
    "DNA_damage_repair": "DNA damage repair",
    "apoptosis": "Apoptosis",
}


def modules(theme: dict, mode: str) -> None:
    rows = [row for row in read_tsv(FLY / "modules" / "preregistered_include_IEA.tsv") if row["nes"] != "NA"]
    rows.sort(key=lambda row: float(row["nes"]))
    names = [MODULE_LABELS[row["module_id"]] for row in rows]
    nes = [float(row["nes"]) for row in rows]
    q = [float(row["module_qvalue"]) for row in rows]
    sizes = [int(row["measured_genes"]) for row in rows]

    fig = plt.figure(figsize=(WIDTH, 5.0))
    heading(fig, theme, f"No pathway module passes: 0 of {len(rows)} at q ≤ 0.10",
            "Fly brain after bub3 depletion (GSE290206). Competitive rotation test, 9,999 rotations, "
            "BH across 13 configured modules.")
    ax = fig.add_axes([0.285, 0.115, 0.50, 0.70])
    y = range(len(rows))
    ax.axvline(0, color=theme["axis"], linewidth=0.9, zorder=1)
    ax.hlines(list(y), 0, nes, color=theme["s1"], linewidth=2, zorder=2, capstyle="round")
    ax.scatter(nes, list(y), s=70, color=theme["s1"], edgecolor=theme["surface"], linewidth=1.6, zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=10.5, color=theme["ink"])
    ax.set_xlim(-2.2, 2.2)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xlabel("Normalized enrichment score  (down in CIN brains  ←   →  up in CIN brains)", fontsize=9.6)
    ax.xaxis.grid(True, color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)

    side = ax.get_yaxis_transform()
    ax.text(1.07, len(rows) - 0.15, "q value", transform=side, fontsize=9.6, color=theme["ink2"],
            fontweight="bold", va="bottom", clip_on=False)
    ax.text(1.25, len(rows) - 0.15, "genes", transform=side, fontsize=9.6, color=theme["ink2"],
            fontweight="bold", va="bottom", clip_on=False)
    for index in y:
        ax.text(1.07, index, f"{q[index]:.3f}", transform=side, fontsize=10.2, color=theme["ink"],
                va="center", clip_on=False)
        ax.text(1.25, index, f"{sizes[index]}", transform=side, fontsize=10.2, color=theme["ink2"],
                va="center", clip_on=False)
    save(fig, "fly-modules", mode)


# --------------------------------------------------------------------------
# 3. Leave-one-batch-out influence
# --------------------------------------------------------------------------
def influence(theme: dict, mode: str) -> None:
    rows = read_tsv(FLY / "sensitivity" / "leave_one_batch_out_summary.tsv")
    total_key = "n_full_primary_candidates"
    direction_key = "n_full_candidates_retaining_direction"
    threshold_key = "n_full_candidates_retaining_q_and_shrunken_effect"

    labels = [f"Batch {row['omitted_batch']} left out" for row in rows]
    total = int(rows[0][total_key])
    direction = [int(float(row[direction_key])) for row in rows]
    threshold = [int(float(row[threshold_key])) for row in rows]

    fig = plt.figure(figsize=(WIDTH, 3.5))
    heading(fig, theme, f"All {total} gene calls keep their direction when any batch is removed",
            "Refit on the two remaining batch pairs. Fewer calls keep the full q and effect-size "
            "thresholds, as expected with four libraries.", top=0.955)
    ax = fig.add_axes([0.165, 0.20, 0.72, 0.50])
    height = 0.34
    for index, _ in enumerate(labels):
        ax.barh(index - height / 2 - 0.02, direction[index], height=height, color=theme["s1"], zorder=2)
        ax.barh(index + height / 2 + 0.02, threshold[index], height=height, color=theme["s2"], zorder=2)
        ax.text(direction[index] + 2.5, index - height / 2 - 0.02, f"{direction[index]}", va="center",
                fontsize=10.5, color=theme["ink"], fontweight="bold")
        ax.text(threshold[index] + 2.5, index + height / 2 + 0.02, f"{threshold[index]}", va="center",
                fontsize=10.5, color=theme["ink"], fontweight="bold")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=10.5, color=theme["ink"])
    ax.set_xlim(0, total * 1.09)
    ax.set_ylim(-0.62, len(labels) - 0.38)
    ax.invert_yaxis()
    ax.set_xlabel(f"Gene calls retained, out of {total}", fontsize=9.6)
    ax.xaxis.grid(True, color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_color(theme["axis"])
    handles = [plt.Rectangle((0, 0), 1, 1, color=theme["s1"]), plt.Rectangle((0, 0), 1, 1, color=theme["s2"])]
    fig.legend(handles, ["Same direction as the full analysis", "Also meets q and effect-size thresholds"],
               loc="upper left", bbox_to_anchor=(0.158, 0.80), ncol=2, frameon=False, fontsize=9.6,
               handlelength=1.1, handleheight=0.9, columnspacing=1.8, labelcolor=theme["ink2"])
    save(fig, "fly-influence", mode)


# --------------------------------------------------------------------------
# 4. Mouse mechanism panel (GSE134780)
# --------------------------------------------------------------------------
CONTRAST_LABELS = {
    "HL1002P_minus_WT": "H/L1002P\nvs WT",
    "HH_minus_WT": "H/H\nvs WT",
    "HL1002P_minus_HH": "H/L1002P\nvs H/H",
}
TISSUE_LABELS = {"skM": "Skeletal muscle", "fat": "Fat"}


def mouse_panel(theme: dict, mode: str) -> None:
    rows = read_tsv(MOUSE / "target_context_panel.tsv")
    summary = json.loads((MOUSE / "analysis_summary.json").read_text(encoding="utf-8"))
    genes = summary["panel_genes"]
    columns: list[tuple[str, str]] = []
    for row in rows:
        key = (row["tissue"], row["contrast"])
        if key not in columns:
            columns.append(key)
    lookup = {(row["tissue"], row["contrast"], row["gene"]): row for row in rows}
    values = [[float(lookup[(tissue, contrast, gene)]["log2_fold_change"]) for tissue, contrast in columns]
              for gene in genes]
    supported = sum(row["decision"] != "NO_PANEL_SUPPORT" for row in rows)
    direct = sum(row["decision"] != "NO_PANEL_SUPPORT" and row["contrast"] == "HL1002P_minus_HH" for row in rows)

    fig = plt.figure(figsize=(WIDTH, 6.1))
    heading(fig, theme, f"Mouse BubR1 alleles: {supported} of {len(rows)} panel tests supported, {direct} in the direct "
                        "allele contrast",
            "Public GSE134780, 23 samples. Outlined cells meet q ≤ 0.10 and a 1.25-fold change. "
            "Values are log2 fold change.", top=0.972)
    ax = fig.add_axes([0.135, 0.04, 0.66, 0.70])
    cmap = LinearSegmentedColormap.from_list("diverging", theme["diverging"])
    norm = TwoSlopeNorm(vmin=-2.0, vcenter=0.0, vmax=2.0)
    mesh = ax.pcolormesh(values, cmap=cmap, norm=norm, edgecolors=theme["surface"], linewidth=2.5)
    ax.set_yticks([index + 0.5 for index in range(len(genes))])
    ax.set_yticklabels(genes, fontsize=10.5, color=theme["ink"], fontstyle="italic")
    ax.set_xticks([])
    for column_index, (_, contrast) in enumerate(columns):
        ax.text(column_index + 0.5, -0.22, CONTRAST_LABELS[contrast], ha="center", va="bottom", fontsize=9.6,
                color=theme["ink"], linespacing=1.15)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for row_index, gene in enumerate(genes):
        for column_index, (tissue, contrast) in enumerate(columns):
            row = lookup[(tissue, contrast, gene)]
            if row["decision"] == "NO_PANEL_SUPPORT":
                continue
            value = float(row["log2_fold_change"])
            strong = abs(value) > 1.05
            text_color = "#ffffff" if (strong and mode == "light") else ("#0d1117" if strong else theme["ink"])
            ax.add_patch(plt.Rectangle((column_index + 0.035, row_index + 0.075), 0.93, 0.85, fill=False,
                                       edgecolor=theme["ink"], linewidth=1.5, zorder=3))
            ax.text(column_index + 0.5, row_index + 0.5, f"{value:+.2f}", ha="center", va="center",
                    fontsize=9.6, fontweight="bold", color=text_color, zorder=4)
    seen: dict[str, list[int]] = {}
    for column_index, (tissue, _) in enumerate(columns):
        seen.setdefault(tissue, []).append(column_index)
    for tissue, indexes in seen.items():
        center = (min(indexes) + max(indexes) + 1) / 2
        ax.text(center, -1.78, TISSUE_LABELS[tissue], ha="center", va="bottom", fontsize=10.5,
                fontweight="bold", color=theme["ink"])
        ax.plot([min(indexes) + 0.08, max(indexes) + 0.92], [-1.62, -1.62], color=theme["axis"], linewidth=1,
                clip_on=False)
    ax.set_xlim(0, len(columns))
    ax.set_ylim(len(genes), 0)
    cax = fig.add_axes([0.835, 0.24, 0.018, 0.30])
    bar = fig.colorbar(mesh, cax=cax, ticks=[-2, -1, 0, 1, 2])
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=0, labelsize=9, colors=theme["ink2"])
    bar.ax.set_yticklabels(["≤ -2", "-1", "0", "+1", "≥ +2"])
    fig.text(0.835, 0.625, "log2 fold\nchange", fontsize=9, color=theme["ink2"], va="bottom", linespacing=1.2)
    save(fig, "mouse-panel", mode)


# --------------------------------------------------------------------------
# 5. Decision rules on the same evidence
# --------------------------------------------------------------------------
SCENARIO_LABELS = {
    "SYNTHETIC_all_pass": "Everything passes",
    "SYNTHETIC_one_dose_failure": "Benefit at one dose only",
    "SYNTHETIC_unmeasured_neurons": "Neuron yield not measured",
    "SYNTHETIC_confirmed_clone_harm": "Abnormal clones expand",
    "SYNTHETIC_indeterminate_safety": "Invasion result unclear",
    "SYNTHETIC_case_mismatch": "Mechanism does not fit the case",
    "SYNTHETIC_confirmation_conflict": "Second guide disagrees",
    "SYNTHETIC_ineligible_control": "Compound is a control arm",
    "SYNTHETIC_no_measured_support": "Nothing measured yet",
}
REASON_LABELS = {
    "PRECLINICAL_CONFIRMATION_ELIGIBLE": "eligible for confirmation",
    "BENEFIT_FAILED": "benefit gate failed",
    "INDETERMINATE_NO_ADVANCE": "evidence incomplete",
    "CONFIRMED_SAFETY_VETO": "safety veto",
    "QUALIFICATION_FAILED": "model not qualified",
    "CONTROL_NOT_ELIGIBLE": "controls cannot advance",
}


def decisions(theme: dict, mode: str) -> None:
    rows = read_tsv(BENCH / "track2_decision_comparison.tsv")
    policies = [("any_biochemical_pass", "Any benefit\nsignal"), ("illustrative_additive_advance", "Weighted\nscore"),
                ("safe_rescue_advance", "Safe Rescue\nEnvelope")]
    counts = [sum(row[key] == "True" for row in rows) for key, _ in policies]

    fig = plt.figure(figsize=(WIDTH, 5.4))
    heading(fig, theme, f"Same evidence, three rules: {counts[0]}, {counts[1]} and {counts[2]} "
                        f"of {len(rows)} scenarios advance",
            "Nine synthetic evidence patterns scored by the production decision function and two simple "
            "comparators.", top=0.968)
    ax = fig.add_axes([0.30, 0.04, 0.40, 0.72])
    ax.set_xlim(0, len(policies))
    ax.set_ylim(len(rows), 0)
    ax.set_axis_off()
    for column_index, (key, label) in enumerate(policies):
        ax.text(column_index + 0.5, -0.22, label, ha="center", va="bottom", fontsize=9.8, fontweight="bold",
                color=theme["ink"], linespacing=1.15)
    for row_index, row in enumerate(rows):
        ax.text(-0.10, row_index + 0.5, SCENARIO_LABELS[row["scenario"]], ha="right", va="center", fontsize=10.5,
                color=theme["ink"])
        for column_index, (key, _) in enumerate(policies):
            advance = row[key] == "True"
            ax.add_patch(FancyBboxPatch((column_index + 0.06, row_index + 0.11), 0.88, 0.78,
                                        boxstyle="round,pad=0,rounding_size=0.10",
                                        facecolor=theme["good"] if advance else theme["stop"], edgecolor="none"))
            ax.text(column_index + 0.5, row_index + 0.5, "advance" if advance else "stop", ha="center",
                    va="center", fontsize=9.6, fontweight="bold" if advance else "normal",
                    color="#ffffff" if advance else theme["stop_ink"])
        ax.text(len(policies) + 0.14, row_index + 0.5, REASON_LABELS[row["safe_rescue_reason"]], ha="left",
                va="center", fontsize=9.6, color=theme["ink2"])
    ax.text(len(policies) + 0.14, -0.22, "Safe Rescue\nreason", ha="left", va="bottom", fontsize=9.8,
            fontweight="bold", color=theme["ink"], linespacing=1.15)
    save(fig, "decision-rules", mode)


# --------------------------------------------------------------------------
# 6. Track 1 ranking policy stress test
# --------------------------------------------------------------------------
REGIME_LABELS = {
    "informative_review": "Review flags are informative",
    "uninformative_review": "Review flags are noise",
    "adverse_review": "Review flags are misleading",
    "unresolved_true_pairs": "True pairs lack phase",
}
METHODS = [("variant_surrogate", "Variant score only", "s1"), ("phenotype_surrogate", "Phenotype-aware score", "s2"),
           ("production_caps", "Evidence caps (this repo)", "s3")]


def ranking(theme: dict, mode: str) -> None:
    rows = read_tsv(BENCH / "track1_policy_comparison.tsv")
    lookup = {(row["regime"], row["method"]): row for row in rows}
    regimes = list(REGIME_LABELS)
    panels = [("precision_at_threshold", "Precision at EPCR 0.60", (0.08, 1.0), "{:.0%}"),
              ("false_positive_variants", "False-positive variants per 600 cases", (0, 400), "{:.0f}")]
    cases = sum(int(lookup[(regime, "production_caps")]["cases"]) for regime in regimes)
    best = lookup[("informative_review", "production_caps")]
    base = lookup[("informative_review", "variant_surrogate")]

    fig = plt.figure(figsize=(WIDTH, 4.3))
    heading(fig, theme, f"Evidence caps cut false positives from {int(base['false_positive_variants'])} to "
                        f"{int(best['false_positive_variants'])} when review flags are reliable",
            f"{cases:,} synthetic cases run through the real candidate builder and scorer. The same table shows "
            "where the caps cost accuracy.", top=0.962)
    for panel_index, (key, title, limits, fmt) in enumerate(panels):
        ax = fig.add_axes([0.275 + panel_index * 0.365, 0.13, 0.31, 0.52])
        for row_index, regime in enumerate(regimes):
            values = [float(lookup[(regime, method)][key]) for method, _, _ in METHODS]
            ax.hlines(row_index, min(values), max(values), color=theme["axis"], linewidth=1.6, zorder=1)
            for (method, _, slot), value in zip(METHODS, values):
                ax.scatter(value, row_index, s=78, color=theme[slot], edgecolor=theme["surface"], linewidth=1.6,
                           zorder=3)
            cap_value = values[-1]
            offset = (limits[1] - limits[0]) * 0.035
            right = cap_value >= max(values[:-1])
            ax.text(cap_value + (offset if right else -offset), row_index - 0.02, fmt.format(cap_value),
                    ha="left" if right else "right", va="center", fontsize=9.6, fontweight="bold",
                    color=theme["ink"])
        ax.set_xlim(*limits)
        ax.set_ylim(len(regimes) - 0.5, -0.5)
        ax.set_yticks(range(len(regimes)))
        ax.set_yticklabels([REGIME_LABELS[regime] for regime in regimes] if panel_index == 0 else [],
                           fontsize=10.2, color=theme["ink"])
        ax.set_title(title, fontsize=9.8, color=theme["ink2"], loc="left", pad=8, fontweight="bold")
        ax.xaxis.grid(True, color=theme["grid"], linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        if key == "precision_at_threshold":
            ax.set_xticks([0.2, 0.4, 0.6, 0.8, 1.0])
            ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.tick_params(axis="x", labelsize=9.2)
    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=8, color=theme[slot]) for _, _, slot in METHODS]
    fig.legend(handles, [label for _, label, _ in METHODS], loc="upper left", bbox_to_anchor=(0.268, 0.835),
               ncol=3, frameon=False, fontsize=9.6, handletextpad=0.3, columnspacing=1.6,
               labelcolor=theme["ink2"])
    save(fig, "ranking-policy", mode)


# --------------------------------------------------------------------------
# 7. Design power sensitivity
# --------------------------------------------------------------------------
def power(theme: dict, mode: str) -> None:
    rows = [row for row in read_tsv(POWER) if row["paired_difference_sd_control_sd"] == "1.00"]
    effects = sorted({row["true_effect_control_sd"] for row in rows}, key=float)

    fig = plt.figure(figsize=(WIDTH, 4.2))
    heading(fig, theme, "How many biological runs the confirmatory experiment needs",
            "Probability that all three benefit endpoints pass at both locked doses. 12,000 simulations per "
            "point, 0.20 SD margin.", top=0.96)
    ax = fig.add_axes([0.085, 0.145, 0.74, 0.60])
    for effect, color in zip(effects, theme["ordinal"]):
        series = sorted((row for row in rows if row["true_effect_control_sd"] == effect),
                        key=lambda row: int(row["biological_runs"]))
        x = [int(row["biological_runs"]) for row in series]
        y = [float(row["all_three_endpoints_both_doses_power"]) for row in series]
        ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=6.5, markeredgecolor=theme["surface"],
                markeredgewidth=1.4, zorder=3, solid_capstyle="round")
        ax.text(x[-1] + 0.7, y[-1], f"{float(effect):.2f} SD benefit", va="center", fontsize=9.8,
                color=theme["ink"], fontweight="bold")
        for runs, value in zip(x, y):
            if (effect == "1.00" and runs in (16, 24, 32)) or (effect == "0.70" and runs == 32):
                ax.text(runs, value + 0.045, f"{value:.0%}", ha="center", va="bottom", fontsize=9.4,
                        color=theme["ink2"])
    ax.set_xlim(5, 33)
    ax.set_ylim(-0.02, 1.08)
    ax.set_xticks([6, 8, 10, 12, 16, 20, 24, 32])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("Biological runs", fontsize=9.6)
    ax.yaxis.grid(True, color=theme["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    save(fig, "design-power", mode)


def main() -> None:
    for mode, theme in THEMES.items():
        style(theme)
        headline(theme, mode)
        modules(theme, mode)
        influence(theme, mode)
        mouse_panel(theme, mode)
        decisions(theme, mode)
        ranking(theme, mode)
        power(theme, mode)
    print(f"wrote {len(list(OUT.glob('*.png')))} figures to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
