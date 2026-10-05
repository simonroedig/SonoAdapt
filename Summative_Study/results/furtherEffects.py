"""
furtherEffects.py – Exploratory pairwise comparisons within cells of the 3×2×2 design.
======================================================================================

This script performs targeted Wilcoxon signed-rank comparisons to explore
specific questions within the System × Urgency/Importance × Scenario design:

GROUP 1 — Urgency/Importance Effect (LOW vs HIGH):
  Within each System × Scenario cell, compare LOW vs HIGH.
  → Shows how urgency/importance changes ratings for each system in each scenario.

GROUP 2 — Sanity Checks (SonoAdapt ≈ Baseline for HIGH):
  SonoAdapt resolves to Earcon in Interview and Speech in Math for HIGH.
  → Ratings should be similar (no significant difference expected).

GROUP 3 — System Choice for HIGH:
  Compare Earcon vs Speech for HIGH in each scenario.
  → Was SonoAdapt's adaptive choice the better option?

GROUP 4 — Scenario Effect (Interview vs Math):
  Within each System × Urgency cell, compare Interview vs Math.
  → Do the scenarios influence ratings?

All tests: Wilcoxon signed-rank (2-condition paired, single trial per cell per participant).
These are exploratory analyses — p-values are uncorrected within each comparison.

Data source: raw.xlsx (with outlier removal via potential_outliers.json)
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ── 0. Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
RAW_PATH = SCRIPT_DIR / "raw.xlsx"
OUTLIERS_PATH = SCRIPT_DIR / "potential_outliers.json"
OUTPUT_DIR = SCRIPT_DIR / "furtherEffectsPlotsAndData"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_TXT = OUTPUT_DIR / "furtherEffectsResults.txt"

# ── Tee ───────────────────────────────────────────────────────────────────────
class _Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()

_output_file = open(OUTPUT_TXT, "w", encoding="utf-8")
sys.stdout = _Tee(sys.__stdout__, _output_file)


# ── 1. Configuration ─────────────────────────────────────────────────────────
REMOVE_OUTLIERS = True
ALPHA = 0.05

SYSTEM_LABELS = {"E": "Earcon", "S": "Speech", "X": "SonoAdapt"}
URGENCY_LABELS = {"L": "Low", "H": "High"}
SCENARIO_LABELS = {"I": "Interview", "M": "Math"}
SYSTEM_ORDER = ["Earcon", "Speech", "SonoAdapt"]

APPROPRIATENESS_MAP = {
    "Completely inappropriate": 1, "Inappropriate": 2,
    "Somewhat inappropriate": 3, "Neither appropriate nor inappropriate": 4,
    "Somewhat appropriate": 5, "Appropriate": 6, "Completely appropriate": 7,
}
DETECTABILITY_MAP = {
    "Very difficult to detect": 1, "Difficult to detect": 2,
    "Somewhat difficult to detect": 3, "Neither easy nor difficult to detect": 4,
    "Somewhat easy to detect": 5, "Easy to detect": 6, "Very easy to detect": 7,
}
DISRUPTIVENESS_MAP = {
    "Not disruptive at all": 1, "Slightly disruptive": 2,
    "Somewhat disruptive": 3, "Moderately disruptive": 4,
    "Disruptive": 5, "Very disruptive": 6, "Extremely disruptive": 7,
}
SOCIAL_MAP = {
    "Completely unacceptable": 1, "Unacceptable": 2,
    "Somewhat unacceptable": 3, "Neither acceptable nor unacceptable": 4,
    "Somewhat acceptable": 5, "Acceptable": 6,
    "Completely acceptable": 7, "Completely Acceptable": 7,
}

DV_MAPS = {
    "Appropriateness": APPROPRIATENESS_MAP,
    "Detectability": DETECTABILITY_MAP,
    "Disruptiveness": DISRUPTIVENESS_MAP,
    "SocialAcceptability": SOCIAL_MAP,
}

DV_COLUMNS = {
    "Appropriateness": "Appropriate_1",
    "Detectability": "Detect_1",
    "Disruptiveness": "Disruptive_1",
    "SocialAcceptability": "Social_1",
}

DV_ORDER = ["Appropriateness", "SocialAcceptability", "Detectability", "Disruptiveness"]

DV_PLOT_TITLES = {
    "Appropriateness": "Appropriateness",
    "SocialAcceptability": "Social\nAcceptability",
    "Detectability": "Detectability",
    "Disruptiveness": "Disruptiveness\n(lower = better)",
}

DV_SHORT = {
    "Appropriateness": "Appr.",
    "SocialAcceptability": "Social",
    "Detectability": "Detect.",
    "Disruptiveness": "Disrupt.",
}


# ── Color blending utility and base colors ────────────────────────────────────
def _blend(hex_color, alpha):
    """Blend hex_color toward white by (1-alpha)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return "#{:02X}{:02X}{:02X}".format(
        int(r * alpha + 255 * (1 - alpha)),
        int(g * alpha + 255 * (1 - alpha)),
        int(b * alpha + 255 * (1 - alpha)),
    )

_BASE_EARCON = "#FFC300"
_BASE_SPEECH = "#694487"
_BASE_MUTE   = "#56C959"

# ── 2. Data Loading ───────────────────────────────────────────────────────────
def hr(title="", char="=", width=88):
    if title:
        print(f"\n{char * width}")
        print(title)
        print(char * width)
    else:
        print(char * width)


hr("SonoAdapt Summative Study — Further Exploratory Analyses")
print(f"Data source: {RAW_PATH}")
print(f"Output dir:  {OUTPUT_DIR}\n")

df_raw = pd.read_excel(RAW_PATH, header=0, skiprows=[1])
df_raw = df_raw.iloc[1:].reset_index(drop=True)

records = []
for _, row in df_raw.iterrows():
    pid = str(row["Participant ID"]).strip()
    pname = str(row["Participant Name"]).strip()
    for trial_num in range(1, 13):
        prefix = f"{trial_num}_"
        code = row.get(f"{prefix}ID")
        if pd.isna(code) or str(code).strip() == "":
            continue
        code = str(code).strip().upper()
        rec = {
            "pid": pid, "participant": pname, "trial": trial_num, "code": code,
            "scenario": SCENARIO_LABELS.get(code[0], code[0]),
            "system": SYSTEM_LABELS.get(code[1], code[1]),
            "urgency": URGENCY_LABELS.get(code[2], code[2]),
        }
        for dv, col_suffix in DV_COLUMNS.items():
            label = str(row.get(f"{prefix}{col_suffix}", "")).strip()
            rec[dv] = DV_MAPS[dv].get(label, np.nan)
        records.append(rec)

df = pd.DataFrame(records)
df["system"] = pd.Categorical(df["system"], SYSTEM_ORDER, ordered=True)
df["urgency"] = pd.Categorical(df["urgency"], ["Low", "High"], ordered=True)
df["scenario"] = pd.Categorical(df["scenario"], ["Interview", "Math"], ordered=True)

# Outlier removal
if REMOVE_OUTLIERS and OUTLIERS_PATH.exists():
    with open(OUTLIERS_PATH, "r", encoding="utf-8") as fh:
        outlier_data = json.load(fh)
    outlier_names = [o["name"] for o in outlier_data.get("outliers", [])
                     if o.get("status") == "is_outlier"]
    df = df[~df["participant"].isin(outlier_names)].reset_index(drop=True)

# SonoAdapt+LOW Detectability → NaN
silent_mask = (df["system"] == "SonoAdapt") & (df["urgency"] == "Low")
df.loc[silent_mask, "Detectability"] = np.nan

N = df["pid"].nunique()
print(f"N = {N} participants (after outlier removal)")
print(f"Total trials: {len(df)}")
print()


# ── 3. Statistical Helpers ────────────────────────────────────────────────────

def wilcoxon_pair(a, b):
    """Wilcoxon signed-rank test with effect sizes."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    nz = d[d != 0]
    n_nz = len(nz)
    if n_nz == 0:
        return dict(W=np.nan, p=1.0, z=0.0, r=0.0, rb=0.0, n_nonzero=0)
    try:
        res = stats.wilcoxon(a, b, zero_method="wilcox", method="auto")
    except TypeError:
        res = stats.wilcoxon(a, b, zero_method="wilcox")
    W, p = float(res.statistic), float(res.pvalue)
    ranks = stats.rankdata(np.abs(nz))
    t_pos = ranks[nz > 0].sum()
    t_neg = ranks[nz < 0].sum()
    rb = (t_pos - t_neg) / (t_pos + t_neg) if (t_pos + t_neg) > 0 else 0.0
    mu = n_nz * (n_nz + 1) / 4.0
    sd = np.sqrt(n_nz * (n_nz + 1) * (2 * n_nz + 1) / 24.0)
    z = (min(t_pos, t_neg) - mu) / sd if sd > 0 else 0.0
    r = abs(z) / np.sqrt(len(a))
    return dict(W=W, p=p, z=z, r=r, rb=rb, n_nonzero=n_nz)


def cohen_dz(a, b):
    d = np.asarray(a, float) - np.asarray(b, float)
    sd = d.std(ddof=1)
    return d.mean() / sd if sd > 0 else np.nan


def sig_stars(p):
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    if p < 0.10:  return "."
    return "n.s."


def get_cell(system=None, urgency=None, scenario=None):
    """Filter the main dataframe to a specific cell."""
    mask = pd.Series(True, index=df.index)
    if system:   mask &= df["system"] == system
    if urgency:  mask &= df["urgency"] == urgency
    if scenario: mask &= df["scenario"] == scenario
    return df[mask].copy()


def participant_values(cell_data, dvs=None):
    """Get participant-level values (mean if multiple trials in cell)."""
    if dvs is None:
        dvs = DV_ORDER
    return cell_data.groupby("pid")[dvs].mean()


def run_comparison(label, cell_a, cell_b, name_a, name_b, dvs=None, expect_ns=False):
    """Run Wilcoxon on each DV for a 2-condition paired comparison."""
    if dvs is None:
        dvs = DV_ORDER

    print(f"\n{'-' * 88}")
    tag = "  [SANITY CHECK — expect n.s.]" if expect_ns else ""
    print(f"{label}{tag}")
    print(f"{'-' * 88}")

    pa = participant_values(cell_a, dvs)
    pb = participant_values(cell_b, dvs)
    common = pa.index.intersection(pb.index)
    pa, pb = pa.loc[common], pb.loc[common]

    print(f"\n  {'DV':<18} {'N':>4}  {name_a + ' M(SD)':>15}  {name_b + ' M(SD)':>15}"
          f"  {'ΔM':>7}  {'W':>7}  {'p':>9}  {'r_rb':>6}  {'d_z':>6}   sig")
    print(f"  {'-' * 86}")

    results = {}
    for dv in dvs:
        a = pa[dv].dropna()
        b = pb[dv].dropna()
        common_dv = a.index.intersection(b.index)
        a, b = a.loc[common_dv], b.loc[common_dv]

        if len(a) < 3:
            print(f"  {DV_SHORT[dv]:<18} {len(a):>4}  {'insufficient data':>33}")
            results[dv] = None
            continue

        res = wilcoxon_pair(a.values, b.values)
        dz = cohen_dz(a.values, b.values)
        diff = a.mean() - b.mean()
        ma_str = f"{a.mean():.2f} ({a.std(ddof=1):.2f})"
        mb_str = f"{b.mean():.2f} ({b.std(ddof=1):.2f})"

        print(f"  {DV_SHORT[dv]:<18} {len(a):>4}  {ma_str:>15}  {mb_str:>15}"
              f"  {diff:>7.2f}  {res['W']:>7.1f}  {res['p']:>9.5f}"
              f"  {res['rb']:>6.2f}  {dz:>6.2f}   {sig_stars(res['p'])}")

        results[dv] = {
            "n": len(a), "M_a": a.mean(), "SD_a": a.std(ddof=1),
            "M_b": b.mean(), "SD_b": b.std(ddof=1),
            "diff": diff, "W": res["W"], "p": res["p"],
            "rb": res["rb"], "r": res["r"], "dz": dz,
        }

    return results, pa, pb


# ── 4. Plotting Helpers ───────────────────────────────────────────────────────

def plot_panel(ax, pa, pb, name_a, name_b, color_a, color_b, dvs, title,
               results=None):
    """Plot a single subplot: 2-condition boxplots across DVs."""
    rows = []
    common = pa.index.intersection(pb.index)
    for dv in dvs:
        for pid in common:
            va, vb = pa.loc[pid, dv], pb.loc[pid, dv]
            if pd.notna(va):
                rows.append({"DV": DV_PLOT_TITLES[dv], "cond": name_a, "rating": va})
            if pd.notna(vb):
                rows.append({"DV": DV_PLOT_TITLES[dv], "cond": name_b, "rating": vb})

    pdf = pd.DataFrame(rows)
    if pdf.empty:
        ax.set_visible(False)
        return
    pdf["DV"] = pd.Categorical(pdf["DV"], [DV_PLOT_TITLES[d] for d in dvs], True)
    pdf["cond"] = pd.Categorical(pdf["cond"], [name_a, name_b], True)

    sns.boxplot(data=pdf, x="DV", y="rating", hue="cond",
                palette={name_a: color_a, name_b: color_b},
                width=0.6, whis=(0, 100), ax=ax, saturation=1.0)

    # Add M(SD) annotations above each box
    hue_off = [-0.15, 0.15]
    common = pa.index.intersection(pb.index)
    for gi, dv in enumerate(dvs):
        for ci, (pcond, name) in enumerate([(pa, name_a), (pb, name_b)]):
            vals = pcond.loc[common, dv].dropna()
            if len(vals) > 0:
                m = vals.mean()
                sd = vals.std(ddof=1)
                ax.text(gi + hue_off[ci], 7.2, f"M={m:.2f}\nSD={sd:.2f}",
                        ha="center", fontsize=7,
                        color="black", fontweight="bold",
                        fontfamily="Arial")

    # Add significance brackets + stars (matching main/simple effects style)
    if results:
        hue_positions = [-0.15, 0.15]
        y_start = 8.1
        for gi, dv in enumerate(dvs):
            r = results.get(dv)
            if r and r["p"] < 0.05:
                stars = sig_stars(r["p"])
                x1, x2 = gi + hue_positions[0], gi + hue_positions[1]
                bar_height = y_start
                bar_tips = bar_height - 0.06
                ax.plot([x1, x1, x2, x2], [bar_tips, bar_height, bar_height, bar_tips],
                        lw=1.5, c="black")
                ax.text((x1 + x2) / 2, bar_height, stars, ha="center", va="bottom",
                        color="black", fontsize=10)

    ax.set_title(title, fontsize=10, fontweight="bold", pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("Rating (1–7)", fontsize=9)
    ax.set_ylim(0.5, 9.5)
    ax.set_yticks(range(1, 8))
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(fontsize=8, loc="upper left", framealpha=0.9)
    ax.grid(True, alpha=0.3, axis="y")


# ══════════════════════════════════════════════════════════════════════════════
# ── 5. GROUP 1: URGENCY/IMPORTANCE EFFECT ─────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GROUP 1 — URGENCY/IMPORTANCE EFFECT (LOW vs HIGH)")
print("Within each System × Scenario cell, compare Low vs High urgency/importance.")
print("Each participant has exactly 1 trial per condition.\n")

COLOR_LOW = "#7BB3C7"
COLOR_HIGH = "#E84855"

urgency_comparisons = [
    ("Interview", "Earcon"), ("Interview", "Speech"),
    ("Math", "Earcon"), ("Math", "Speech"),
]

urg_results = {}
urg_data = {}
for scenario, system in urgency_comparisons:
    key = f"{scenario}_{system}"
    cell_low = get_cell(system=system, urgency="Low", scenario=scenario)
    cell_high = get_cell(system=system, urgency="High", scenario=scenario)
    res, pa, pb = run_comparison(
        f"{scenario} × {system}: Low vs High Urgency/Importance",
        cell_low, cell_high, "Low", "High"
    )
    urg_results[key] = res
    urg_data[key] = (pa, pb)

# Plot: 2×2 grid
matplotlib.rcdefaults()
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})

fig, axes = plt.subplots(2, 2, figsize=(14, 11))
fig.suptitle("Urgency/Importance Effect: Low vs High\n(within each System × Scenario)",
             fontsize=14, fontweight="bold", y=0.98)

for idx, (scenario, system) in enumerate(urgency_comparisons):
    key = f"{scenario}_{system}"
    r, c = divmod(idx, 2)
    pa, pb = urg_data[key]
    plot_panel(axes[r, c], pa, pb, "Low", "High", COLOR_LOW, COLOR_HIGH,
               DV_ORDER, f"{scenario} × {system}", urg_results[key])

plt.subplots_adjust(hspace=0.35)
plt.tight_layout(rect=[0, 0, 1, 0.94])
for ext in ("png", "pdf"):
    fig.savefig(OUTPUT_DIR / f"fig_urgencyEffect.{ext}", dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\nSaved: fig_urgencyEffect.png / .pdf")


# ══════════════════════════════════════════════════════════════════════════════
# ── 6. GROUP 2: SANITY CHECKS ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GROUP 2 — SANITY CHECKS (SonoAdapt ≈ Baseline for HIGH)")
print("SonoAdapt plays Earcon in Interview (HIGH) and Speech in Math (HIGH).")
print("If the system works correctly, ratings should be nearly identical.\n")

sanity_checks = [
    ("Interview", "Earcon", "SonoAdapt", "SonoAdapt plays Earcon in Interview-HIGH"),
    ("Math", "Speech", "SonoAdapt", "SonoAdapt plays Speech in Math-HIGH"),
]

san_results = {}
san_data = {}
for scenario, sys_a, sys_b, note in sanity_checks:
    key = f"sanity_{scenario}"
    cell_a = get_cell(system=sys_a, urgency="High", scenario=scenario)
    cell_b = get_cell(system=sys_b, urgency="High", scenario=scenario)
    res, pa, pb = run_comparison(
        f"Sanity: {scenario} HIGH — {sys_a} vs {sys_b}  ({note})",
        cell_a, cell_b, sys_a, sys_b, expect_ns=True
    )
    san_results[key] = res
    san_data[key] = (pa, pb, sys_a, sys_b)


# ══════════════════════════════════════════════════════════════════════════════
# ── 7. GROUP 3: SYSTEM CHOICE FOR HIGH ────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GROUP 3 — SYSTEM CHOICE FOR HIGH (Earcon vs Speech)")
print("For HIGH urgency/importance, compare Earcon vs Speech in each scenario.")
print("This reveals whether SonoAdapt's adaptive choice was the better option.\n")

choice_comparisons = [
    ("Interview", "SonoAdapt chose Earcon here — was it better than Speech?"),
    ("Math", "SonoAdapt chose Speech here — was it better than Earcon?"),
]

choice_results = {}
choice_data = {}
for scenario, note in choice_comparisons:
    key = f"choice_{scenario}"
    cell_a = get_cell(system="Earcon", urgency="High", scenario=scenario)
    cell_b = get_cell(system="Speech", urgency="High", scenario=scenario)
    res, pa, pb = run_comparison(
        f"{scenario} HIGH: Earcon vs Speech  ({note})",
        cell_a, cell_b, "Earcon", "Speech"
    )
    choice_results[key] = res
    choice_data[key] = (pa, pb)

# Separate plots: Sanity checks and System choice
COLORS_SYS = {"Earcon": "#FFC300", "Speech": "#694487", "SonoAdapt": "#56C959"}

# What SonoAdapt resolves to in each scenario (for labelling)
SANITY_RESOLVES = {"Interview": "Earcon", "Math": "Speech"}

def make_sanity_figure(adapt_name):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.suptitle(f"Sanity Check: {adapt_name} \u2248 Baseline for High Urgency/Importance",
                 fontsize=14, fontweight="bold", y=1.02)

    # Use 70% opacity colors (matching combined overview HIGH)
    sanity_color_a = {
        "Interview": _blend(_BASE_EARCON, 0.70),  # Earcon at 70%
        "Math": _blend(_BASE_SPEECH, 0.70),        # Speech at 70%
    }
    sanity_color_b = _blend(_BASE_MUTE, 0.70)  # SonoAdapt at 70% (green)

    from matplotlib.patches import Rectangle

    for idx, (scenario, sys_a, sys_b, note) in enumerate(sanity_checks):
        key = f"sanity_{scenario}"
        pa, pb, sa, sb = san_data[key]
        display_b = adapt_name
        resolves_to = SANITY_RESOLVES[scenario]
        subplot_title = (f"Sanity: {scenario} High \u2014 "
                         f"{sa} vs {display_b} (= {resolves_to})")

        col_a = sanity_color_a[scenario]
        col_b = sanity_color_b

        plot_panel(axes[idx], pa, pb, sa, display_b,
                   col_a, col_b,
                   DV_ORDER, subplot_title,
                   san_results[key])

        # Fix zero-height boxes: draw a colored rectangle for thin IQR
        ax = axes[idx]
        MIN_BOX_HEIGHT = 0.18
        BOX_WIDTH = 0.6
        common = pa.index.intersection(pb.index)
        hue_off = [-0.15, 0.15]
        for gi, dv in enumerate(DV_ORDER):
            for ci, (pcond, col) in enumerate([(pa, col_a), (pb, col_b)]):
                vals = pcond.loc[common, dv].dropna()
                if len(vals) == 0:
                    continue
                q1 = vals.quantile(0.25)
                q3 = vals.quantile(0.75)
                iqr = q3 - q1
                if iqr < MIN_BOX_HEIGHT:
                    center = (q1 + q3) / 2
                    box_w = BOX_WIDTH / 2 * 0.9
                    x_center = gi + hue_off[ci]
                    rect = Rectangle(
                        (x_center - box_w / 2, center - MIN_BOX_HEIGHT / 2),
                        box_w, MIN_BOX_HEIGHT,
                        facecolor=col, edgecolor="black",
                        linewidth=1.0, zorder=2
                    )
                    ax.add_patch(rect)

    plt.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT_DIR / f"fig_sanityChecks_{adapt_name}.{ext}",
                    dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: fig_sanityChecks_{adapt_name}.png / .pdf")

def make_system_choice_figure(adapt_name):
    # SonoAdapt chose Earcon in Interview, Speech in Math
    CHOSEN_IN = {"Interview": "Earcon", "Math": "Speech"}

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.suptitle(f"System Choice for HIGH Urgency/Importance: Earcon vs Speech\n"
                 f"(Was {adapt_name}'s adaptive choice the better option?)",
                 fontsize=14, fontweight="bold", y=1.02)

    for idx, (scenario, note) in enumerate(choice_comparisons):
        key = f"choice_{scenario}"
        pa, pb = choice_data[key]
        chosen = CHOSEN_IN[scenario]
        if chosen == "Earcon":
            title = f"{scenario} HIGH: Earcon (chosen by {adapt_name}) vs Speech"
        else:
            title = f"{scenario} HIGH: Earcon vs Speech (chosen by {adapt_name})"
        plot_panel(axes[idx], pa, pb, "Earcon", "Speech",
                   COLORS_SYS["Earcon"], COLORS_SYS["Speech"],
                   DV_ORDER, title,
                   choice_results[key])

    plt.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT_DIR / f"fig_systemChoice_{adapt_name}.{ext}",
                    dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: fig_systemChoice_{adapt_name}.png / .pdf")

make_sanity_figure("SonoAdapt")
make_sanity_figure("AudioAdapt")
make_system_choice_figure("SonoAdapt")
make_system_choice_figure("AudioAdapt")


# ══════════════════════════════════════════════════════════════════════════════
# ── 8. GROUP 4: SCENARIO EFFECT ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GROUP 4 — SCENARIO EFFECT (Interview vs Math)")
print("Within each System × Urgency cell, compare Interview vs Math.")
print("Also 'combined' (averaging across urgency levels).\n")

COLOR_INT = "#2196F3"
COLOR_MATH = "#FF9800"

scenario_comparisons = [
    ("Speech", "High",  "Speech × High: Interview vs Math"),
    ("Speech", "Low",   "Speech × Low: Interview vs Math"),
    ("Speech", None,    "Speech × Combined: Interview vs Math"),
    ("Earcon", "High",  "Earcon × High: Interview vs Math"),
    ("Earcon", "Low",   "Earcon × Low: Interview vs Math"),
    ("Earcon", None,    "Earcon × Combined: Interview vs Math"),
]

scen_results = {}
scen_data = {}
for system, urgency, label in scenario_comparisons:
    key = f"scen_{system}_{urgency or 'all'}"
    cell_int = get_cell(system=system, urgency=urgency, scenario="Interview")
    cell_math = get_cell(system=system, urgency=urgency, scenario="Math")
    res, pa, pb = run_comparison(label, cell_int, cell_math, "Interview", "Math")
    scen_results[key] = res
    scen_data[key] = (pa, pb)

# Plot: 2×3 grid (rows: Speech/Earcon, cols: High/Low/Combined)
fig, axes = plt.subplots(2, 3, figsize=(18, 11))
fig.suptitle("Scenario Effect: Interview vs Math\n"
             "(within each System × Urgency/Importance)",
             fontsize=14, fontweight="bold", y=0.98)

plot_order = [
    ("Speech", "High"), ("Speech", "Low"), ("Speech", None),
    ("Earcon", "High"), ("Earcon", "Low"), ("Earcon", None),
]

for idx, (system, urgency) in enumerate(plot_order):
    r, c = divmod(idx, 3)
    key = f"scen_{system}_{urgency or 'all'}"
    pa, pb = scen_data[key]
    urg_str = urgency if urgency else "Combined"
    plot_panel(axes[r, c], pa, pb, "Interview", "Math",
               COLOR_INT, COLOR_MATH, DV_ORDER,
               f"{system} × {urg_str}", scen_results[key])

plt.subplots_adjust(hspace=0.35)
plt.tight_layout(rect=[0, 0, 1, 0.94])
for ext in ("png", "pdf"):
    fig.savefig(OUTPUT_DIR / f"fig_scenarioEffect.{ext}", dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\nSaved: fig_scenarioEffect.png / .pdf")


# ══════════════════════════════════════════════════════════════════════════════
# ── 9. GRAND SUMMARY TABLE ───────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GRAND SUMMARY — All Pairwise Comparisons")

def print_summary_group(title, comparisons_info):
    """Print a summary table for a group of comparisons."""
    print(f"\n  {title}")
    print(f"  {'Comparison':<48} {'DV':<10} {'N':>3} {'M_A':>6} {'M_B':>6}"
          f" {'ΔM':>6} {'p':>9} {'r_rb':>6} {'d_z':>6} sig")
    print(f"  {'─' * 115}")
    for label, results_dict in comparisons_info:
        for dv in DV_ORDER:
            r = results_dict.get(dv)
            if r is None:
                continue
            first_col = label if dv == DV_ORDER[0] else ""
            print(f"  {first_col:<48} {DV_SHORT[dv]:<10} {r['n']:>3}"
                  f" {r['M_a']:>6.2f} {r['M_b']:>6.2f}"
                  f" {r['diff']:>6.2f} {r['p']:>9.5f}"
                  f" {r['rb']:>6.2f} {r['dz']:>6.2f} {sig_stars(r['p'])}")
        print()

# Group 1
g1 = [(f"{sc} × {sy}: Low vs High", urg_results[f"{sc}_{sy}"])
      for sc, sy in urgency_comparisons]
print_summary_group("GROUP 1 — URGENCY/IMPORTANCE EFFECT (Low vs High)", g1)

# Group 2
g2 = []
for scenario, sys_a, sys_b, note in sanity_checks:
    key = f"sanity_{scenario}"
    g2.append((f"Sanity: {scenario} HIGH — {sys_a} vs {sys_b}", san_results[key]))
print_summary_group("GROUP 2 — SANITY CHECKS [expect n.s.]", g2)

# Group 3
g3 = [(f"{sc} HIGH: Earcon vs Speech", choice_results[f"choice_{sc}"])
      for sc, _ in choice_comparisons]
print_summary_group("GROUP 3 — SYSTEM CHOICE FOR HIGH", g3)

# Group 4
g4 = [(label, scen_results[f"scen_{sy}_{urg or 'all'}"])
      for sy, urg, label in scenario_comparisons]
print_summary_group("GROUP 4 — SCENARIO EFFECT (Interview vs Math)", g4)

print()
print("All p-values are uncorrected (exploratory analyses).")
print("Significance codes: *** p<.001, ** p<.01, * p<.05, . p<.10, n.s. p≥.10")
print()

# ── Generate dataForWriting.txt ───────────────────────────────────────────────
ref_path = OUTPUT_DIR / "dataForWriting.txt"
with open(ref_path, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("FURTHER EFFECTS — Data Reference for Writing\n")
    f.write("=" * 80 + "\n")
    f.write(f"N = 23 participants (after removing 4 outliers)\n")
    f.write(f"All values are participant-level (1 trial per cell).\n")
    f.write(f"All p-values are UNCORRECTED (exploratory analyses).\n\n")

    def write_comparison_block(f, title, pa, pb, name_a, name_b, results, dvs):
        """Write one comparison block to the reference file."""
        f.write("-" * 80 + "\n")
        f.write(f"COMPARISON: {title}\n")
        f.write(f"  Conditions: {name_a} vs {name_b}\n\n")

        common = pa.index.intersection(pb.index)
        for dv in dvs:
            dv_label = DV_PLOT_TITLES.get(dv, dv).replace("\n", " ")
            vals_a = pa.loc[common, dv].dropna()
            vals_b = pb.loc[common, dv].dropna()
            if len(vals_a) == 0 and len(vals_b) == 0:
                continue

            ma = vals_a.mean() if len(vals_a) > 0 else float("nan")
            sda = vals_a.std(ddof=1) if len(vals_a) > 0 else float("nan")
            mb = vals_b.mean() if len(vals_b) > 0 else float("nan")
            sdb = vals_b.std(ddof=1) if len(vals_b) > 0 else float("nan")

            r = results.get(dv, {}) if results else {}
            p_val = r.get("p", float("nan"))
            rb = r.get("rb", float("nan"))

            f.write(f"  {dv_label}:\n")
            f.write(f"    {name_a:12s}  M = {ma:.2f},  SD = {sda:.2f}\n")
            f.write(f"    {name_b:12s}  M = {mb:.2f},  SD = {sdb:.2f}\n")
            if not pd.isna(p_val):
                f.write(f"    ΔM = {ma - mb:.2f},  p = {p_val:.5f},  r_rb = {rb:.2f}  {sig_stars(p_val)}\n")
            f.write(f"    Snippet: {name_a} (M = {ma:.2f}, SD = {sda:.2f}) vs "
                    f"{name_b} (M = {mb:.2f}, SD = {sdb:.2f}), ΔM = {ma - mb:.2f}, p = {p_val:.5f}\n\n")

    # GROUP 1: Urgency Effect
    f.write("=" * 80 + "\n")
    f.write("GROUP 1 — URGENCY/IMPORTANCE EFFECT (Low vs High)\n")
    f.write("Plot: fig_urgencyEffect.png/.pdf\n")
    f.write("=" * 80 + "\n\n")
    for scenario, system in urgency_comparisons:
        key = f"{scenario}_{system}"
        pa, pb = urg_data[key]
        write_comparison_block(f, f"{scenario} × {system}: Low vs High",
                               pa, pb, "Low", "High", urg_results[key], DV_ORDER)

    # GROUP 2: Sanity Checks
    f.write("=" * 80 + "\n")
    f.write("GROUP 2 — SANITY CHECKS (SonoAdapt ≈ Baseline for HIGH)\n")
    f.write("Plot: fig_sanityChecks_SonoAdapt/AudioAdapt.png/.pdf\n")
    f.write("=" * 80 + "\n\n")
    for scenario, sys_a, sys_b, note in sanity_checks:
        key = f"sanity_{scenario}"
        pa, pb, sa, sb = san_data[key]
        write_comparison_block(f, f"Sanity: {scenario} HIGH — {sa} vs {sb}",
                               pa, pb, sa, sb, san_results[key], DV_ORDER)

    # GROUP 3: System Choice
    f.write("=" * 80 + "\n")
    f.write("GROUP 3 — SYSTEM CHOICE FOR HIGH (Earcon vs Speech)\n")
    f.write("Plot: fig_systemChoice_SonoAdapt/AudioAdapt.png/.pdf\n")
    f.write("Note: Uses BASELINE data (justified by sanity checks above)\n")
    f.write("=" * 80 + "\n\n")
    for scenario, note in choice_comparisons:
        key = f"choice_{scenario}"
        pa, pb = choice_data[key]
        chosen = {"Interview": "Earcon", "Math": "Speech"}[scenario]
        write_comparison_block(f, f"{scenario} HIGH: Earcon vs Speech (SonoAdapt chose {chosen})",
                               pa, pb, "Earcon", "Speech", choice_results[key], DV_ORDER)

    # GROUP 4: Scenario Effect
    f.write("=" * 80 + "\n")
    f.write("GROUP 4 — SCENARIO EFFECT (Interview vs Math)\n")
    f.write("Plot: fig_scenarioEffect.png/.pdf\n")
    f.write("=" * 80 + "\n\n")
    for system, urgency, label in scenario_comparisons:
        key = f"scen_{system}_{urgency or 'all'}"
        pa, pb = scen_data[key]
        write_comparison_block(f, label,
                               pa, pb, "Interview", "Math", scen_results[key], DV_ORDER)

    f.write("=" * 80 + "\n")
    f.write("END\n")

sys.__stdout__.write(f"  Saved: {ref_path}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ── GROUP 5: COMBINED OVERVIEW FIGURE ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("GROUP 5 — COMBINED OVERVIEW FIGURE")
print("Combined figure showing Mute (SonoAdapt Low), Earcon Low/High, Speech Low/High")
print("for each scenario across 3 DVs.")
print("The HIGH condition that SonoAdapt chose is marked with ≈ SonoAdapt.\n")

# DVs to include (Detectability included — Mute/SonoAdapt-Low will simply be absent)
combined_dvs = ["Appropriateness", "SocialAcceptability", "Detectability", "Disruptiveness"]

COLOR_EARCON_LOW  = _blend(_BASE_EARCON, 0.40)
COLOR_EARCON_HIGH = _blend(_BASE_EARCON, 0.70)
COLOR_SPEECH_LOW  = _blend(_BASE_SPEECH, 0.40)
COLOR_SPEECH_HIGH = _blend(_BASE_SPEECH, 0.70)
COLOR_MUTE        = _blend(_BASE_MUTE,   0.40)

# Internal keys for data lookup (scenario-independent)
_data_keys = [
    ("SonoAdapt", "Low",  "mute"),
    ("Earcon",    "Low",  "earcon_low"),
    ("Speech",    "Low",  "speech_low"),
    ("Earcon",    "High", "earcon_high"),
    ("Speech",    "High", "speech_high"),
]

scenarios = ["Interview", "Math"]

# Scenario-specific display labels: mark the chosen HIGH system with ≈ SonoAdapt
def get_cond_labels(scenario):
    """Return ordered condition labels for a given scenario."""
    labels = [
        "Mute\nLow (= SonoAdapt)",
        "Earcon\nLow",
        "Speech\nLow",
    ]
    if scenario == "Interview":
        labels.append("Earcon\nHigh (≈ SonoAdapt)")
        labels.append("Speech\nHigh")
    else:  # Math
        labels.append("Earcon\nHigh")
        labels.append("Speech\nHigh (≈ SonoAdapt)")
    return labels

def get_cond_colors(scenario):
    """Return color dict matching the scenario-specific labels."""
    labels = get_cond_labels(scenario)
    return {
        labels[0]: COLOR_MUTE,
        labels[1]: COLOR_EARCON_LOW,
        labels[2]: COLOR_SPEECH_LOW,
        labels[3]: COLOR_EARCON_HIGH,
        labels[4]: COLOR_SPEECH_HIGH,
    }

# Gather data (use internal keys)
combined_cell_data = {}
for scenario in scenarios:
    for system, urgency, ikey in _data_keys:
        cell = get_cell(system=system, urgency=urgency, scenario=scenario)
        pv = participant_values(cell, combined_dvs)
        combined_cell_data[(scenario, ikey)] = pv

# Internal key order (matches label order)
_ikey_order = ["mute", "earcon_low", "speech_low", "earcon_high", "speech_high"]

# Run Wilcoxon tests for key comparisons within each scenario
combined_stats = {}
for scenario in scenarios:
    earcon_h = combined_cell_data[(scenario, "earcon_high")]
    speech_h = combined_cell_data[(scenario, "speech_high")]
    earcon_l = combined_cell_data[(scenario, "earcon_low")]
    speech_l = combined_cell_data[(scenario, "speech_low")]
    mute     = combined_cell_data[(scenario, "mute")]

    def _test(a_df, b_df, tag):
        common = a_df.index.intersection(b_df.index)
        for dv in combined_dvs:
            a = a_df.loc[common, dv].dropna()
            b = b_df.loc[common, dv].dropna()
            ci = a.index.intersection(b.index)
            if len(ci) >= 3:
                res = wilcoxon_pair(a.loc[ci].values, b.loc[ci].values)
                combined_stats[(scenario, dv, tag)] = res

    _test(earcon_h, speech_h, "EH_SH")
    _test(mute, earcon_l, "Mute_EL")
    _test(mute, speech_l, "Mute_SL")
    _test(speech_l, speech_h, "SL_SH")

# Print combined stats
for key, res in sorted(combined_stats.items()):
    scenario, dv, comp = key
    print(f"  {scenario} | {dv:20s} | {comp:8s} | p = {res['p']:.5f} {sig_stars(res['p']):>4s} | r_rb = {res['rb']:.2f}")

# ── Plot ──────────────────────────────────────────────────────────────────────
matplotlib.rcdefaults()
plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42,
                      "font.family": "sans-serif", "font.sans-serif": ["Arial"]})

fig, axes = plt.subplots(2, 4, figsize=(20, 10))

# Color list in condition order (same for both scenarios)
_color_order = [COLOR_MUTE, COLOR_EARCON_LOW, COLOR_SPEECH_LOW, COLOR_EARCON_HIGH, COLOR_SPEECH_HIGH]

for row_idx, scenario in enumerate(scenarios):
    cond_labels = get_cond_labels(scenario)
    cond_colors = get_cond_colors(scenario)

    for col_idx, dv in enumerate(combined_dvs):
        ax = axes[row_idx, col_idx]

        # Build data for this subplot
        plot_rows = []
        for idx, ikey in enumerate(_ikey_order):
            label = cond_labels[idx]
            pv = combined_cell_data[(scenario, ikey)]
            # Skip Mute for Detectability (undefined when muted)
            if dv == "Detectability" and ikey == "mute":
                continue
            for pid in pv.index:
                val = pv.loc[pid, dv]
                if pd.notna(val):
                    plot_rows.append({"Condition": label, "rating": val})

        pdf = pd.DataFrame(plot_rows)
        if pdf.empty:
            ax.set_visible(False)
            continue

        # For Detectability, only show the 4 non-mute conditions
        if dv == "Detectability":
            valid_labels = cond_labels[1:]  # skip Mute
            valid_colors = {k: v for k, v in cond_colors.items() if k != cond_labels[0]}
        else:
            valid_labels = cond_labels
            valid_colors = cond_colors

        pdf["Condition"] = pd.Categorical(pdf["Condition"], valid_labels, ordered=True)

        bp = sns.boxplot(data=pdf, x="Condition", y="rating",
                    hue="Condition", palette=valid_colors, order=valid_labels,
                    hue_order=valid_labels, legend=False,
                    width=0.65, whis=(0, 100), ax=ax, saturation=1.0)

        # Fix zero-height boxes: draw a colored rectangle behind thin boxes
        # Seaborn boxplot patches may have zero height when IQR=0.
        # We overlay a visible colored bar so they aren't just a black line.
        from matplotlib.patches import FancyBboxPatch, Rectangle
        MIN_BOX_HEIGHT = 0.18  # data units
        BOX_WIDTH = 0.65
        n_conds = len(valid_labels)
        for ci in range(n_conds):
            subset = pdf[pdf["Condition"] == valid_labels[ci]]["rating"]
            if len(subset) == 0:
                continue
            q1 = subset.quantile(0.25)
            q3 = subset.quantile(0.75)
            iqr = q3 - q1
            if iqr < MIN_BOX_HEIGHT:
                center = (q1 + q3) / 2
                color_for_ci = valid_colors[valid_labels[ci]]
                rect = Rectangle(
                    (ci - BOX_WIDTH / 2, center - MIN_BOX_HEIGHT / 2),
                    BOX_WIDTH, MIN_BOX_HEIGHT,
                    facecolor=color_for_ci, edgecolor="black",
                    linewidth=1.0, zorder=2
                )
                ax.add_patch(rect)

        # Add M/SD annotations
        for ci, ikey in enumerate(_ikey_order):
            # Skip Mute for Detectability
            if dv == "Detectability" and ikey == "mute":
                continue
            # Map ikey to x-position: for Detectability, shift by -1 (no Mute)
            if dv == "Detectability":
                x_pos = _ikey_order.index(ikey) - 1  # mute=0 skipped, so earcon_low=0, etc.
            else:
                x_pos = ci
            pv = combined_cell_data[(scenario, ikey)]
            vals = pv[dv].dropna()
            if len(vals) > 0:
                m = vals.mean()
                sd = vals.std(ddof=1)
                ax.text(x_pos, 7.2, f"M={m:.2f}\nSD={sd:.2f}",
                        ha="center", fontsize=6, color="black",
                        fontweight="bold", fontfamily="Arial")

        # Title and labels
        dv_label = DV_PLOT_TITLES.get(dv, dv).replace("\n", " ")
        ax.set_title(f"{scenario}: {dv_label}", fontsize=10, fontweight="bold", pad=12)
        ax.set_xlabel("")
        ax.set_ylabel("Rating (1–7)" if col_idx == 0 else "", fontsize=9)
        ax.set_ylim(0.5, 9.8)
        ax.set_yticks(range(1, 8))
        ax.tick_params(axis="x", labelsize=7)
        ax.grid(True, alpha=0.3, axis="y")

        # Bold x-tick labels that contain "SonoAdapt"
        for tick_label in ax.get_xticklabels():
            if "SonoAdapt" in tick_label.get_text():
                tick_label.set_fontweight("bold")

        # Add significance brackets for key comparisons
        # New order indices: 0=Mute, 1=EarconLow, 2=SpeechLow, 3=EarconHigh, 4=SpeechHigh
        # For Detectability, indices shift: 0=EarconLow, 1=SpeechLow, 2=EarconHigh, 3=SpeechHigh
        brackets = []

        if dv == "Detectability":
            # Only Earcon-High vs Speech-High (indices 2 and 3 in the 4-box layout)
            r = combined_stats.get((scenario, dv, "EH_SH"))
            if r and r["p"] < 0.05:
                brackets.append((2, 3, sig_stars(r["p"])))
        else:
            # Earcon-High vs Speech-High (system choice — indices 3 and 4)
            r = combined_stats.get((scenario, dv, "EH_SH"))
            if r and r["p"] < 0.05:
                brackets.append((3, 4, sig_stars(r["p"])))

            # Mute vs Earcon-Low (indices 0 and 1)
            r = combined_stats.get((scenario, dv, "Mute_EL"))
            if r and r["p"] < 0.05:
                brackets.append((0, 1, sig_stars(r["p"])))

            # Mute vs Speech-Low (indices 0 and 2)
            r = combined_stats.get((scenario, dv, "Mute_SL"))
            if r and r["p"] < 0.05:
                brackets.append((0, 2, sig_stars(r["p"])))

        # Draw brackets at staggered heights
        y_base = 8.2
        for bi, (x1, x2, stars) in enumerate(brackets):
            y = y_base + bi * 0.45
            left, right = min(x1, x2), max(x1, x2)
            tip = y - 0.06
            ax.plot([left, left, right, right], [tip, y, y, tip],
                    lw=1.2, c="black")
            ax.text((left + right) / 2, y, stars, ha="center", va="bottom",
                    color="black", fontsize=8)

fig.suptitle("Combined Overview: System Ratings by Scenario, Urgency/Importance, and Modality",
             fontsize=13, fontweight="bold", y=1.0)
plt.tight_layout(rect=[0, 0, 1, 0.96])

for suffix in ("SonoAdapt", "AudioAdapt"):
    for ext in ("png", "pdf"):
        fig.savefig(OUTPUT_DIR / f"fig_combinedOverview_{suffix}.{ext}",
                    dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\nSaved: fig_combinedOverview_SonoAdapt.png / .pdf")
print(f"Saved: fig_combinedOverview_AudioAdapt.png / .pdf")



# ── Close output ──────────────────────────────────────────────────────────────
hr("DONE", "=")
print(f"All results saved to: {OUTPUT_DIR}")

_output_file.close()
sys.stdout = sys.__stdout__
print(f"\n✅ Further effects analysis complete. Results saved to: {OUTPUT_DIR}")
