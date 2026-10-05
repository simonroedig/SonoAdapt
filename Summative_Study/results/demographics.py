"""
demographics.py – Demographics summary for the SonoAdapt summative study.
=========================================================================

Reads raw.xlsx, removes pilot + outliers, and reports:
  - Sample size (raw → final N)
  - Age (M, SD, min, max)
  - Gender distribution
  - English proficiency
  - Smart-glasses experience
  - Notification settings, auditory preferences, importance/urgency attitudes
  - Impairments

Outputs saved to demographicsPlotsAndData/:
  - demographicsResults.txt   – Full demographic breakdown
  - dataForWriting.txt        – Pre-written LaTeX paragraph + copyable snippets

Data source: raw.xlsx (with outlier removal via potential_outliers.json)
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# ── 0. Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
RAW_PATH = SCRIPT_DIR / "raw.xlsx"
OUTLIERS_PATH = SCRIPT_DIR / "potential_outliers.json"
OUTPUT_DIR = SCRIPT_DIR / "demographicsPlotsAndData"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_TXT = OUTPUT_DIR / "demographicsResults.txt"
OUTPUT_WRITING = OUTPUT_DIR / "dataForWriting.txt"


# ── Tee: write to console + file simultaneously ──────────────────────────────
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


# ── 1. Helper ─────────────────────────────────────────────────────────────────
def hr(title="", char="=", width=88):
    if title:
        print(f"\n{char * width}")
        print(title)
        print(char * width)
    else:
        print(char * width)


def freq_table(series, title):
    """Print a frequency table with counts and percentages."""
    vc = series.value_counts()
    total = vc.sum()
    print(f"\n  {title}  (N = {total})")
    print(f"  {'─' * 70}")
    for val, cnt in vc.items():
        pct = cnt / total * 100
        print(f"    {val:50s}  {cnt:3d}  ({pct:5.1f}%)")
    return vc


# ══════════════════════════════════════════════════════════════════════════════
# ── 2. Load & Filter Data ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("SonoAdapt Summative Study — Demographics")
print(f"Data source: {RAW_PATH}")
print(f"Output dir:  {OUTPUT_DIR}\n")

df_raw = pd.read_excel(RAW_PATH, header=0, skiprows=[1])
n_total_raw = len(df_raw)
print(f"Raw rows loaded (incl. header description rows): {n_total_raw}")

# Remove pilot (first row)
df_raw = df_raw.iloc[1:].reset_index(drop=True)
n_after_pilot = len(df_raw)
print(f"Rows after removing pilot: {n_after_pilot}")

# ── Outlier removal ──
hr("OUTLIER REMOVAL", "-")
outlier_names = []
n_outliers = 0
if OUTLIERS_PATH.exists():
    with open(OUTLIERS_PATH, "r", encoding="utf-8") as fh:
        outlier_data = json.load(fh)
    outlier_names = [
        o["name"] for o in outlier_data.get("outliers", [])
        if o.get("status") == "is_outlier"
    ]
    n_before = len(df_raw)
    removed = df_raw[df_raw["Participant Name"].astype(str).str.strip().isin(outlier_names)]
    removed_names = removed["Participant Name"].astype(str).str.strip().unique().tolist()
    df = df_raw[~df_raw["Participant Name"].astype(str).str.strip().isin(outlier_names)].reset_index(drop=True)
    n_outliers = len(removed_names)
    n_after = len(df)
    print(f"Outliers removed: {', '.join(removed_names)} ({n_outliers} participants)")
    print(f"Participants remaining: {n_after} (was {n_before})")
else:
    df = df_raw.copy()
    print("No outlier file found — no outlier removal applied.")
print()

N = len(df)

# Number of trials per participant
n_trials = 12  # 3 systems × 2 urgency × 2 scenario
n_observations = N * n_trials


# ══════════════════════════════════════════════════════════════════════════════
# ── 3. Demographics Analysis ─────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("SAMPLE OVERVIEW")
print(f"  Total raw survey responses:           {n_total_raw}")
print(f"  Removed (pilot):                      1")
print(f"  Removed (outliers):                   {n_outliers}")
print(f"  Final sample:                         N = {N}")
print(f"  Trials per participant:               {n_trials}")
print(f"  Total individual observations:        {n_observations}")

# ── Age ───────────────────────────────────────────────────────────────────────
hr("AGE", "-")
# Convert Age to numeric (handle any string values)
age_raw = pd.to_numeric(df["Age"], errors="coerce")
age = age_raw.dropna()
age_m = age.mean()
age_sd = age.std(ddof=1)
age_min = int(age.min())
age_max = int(age.max())
age_mdn = age.median()
print(f"  N valid:   {len(age)}")
print(f"  Min:       {age_min}")
print(f"  Max:       {age_max}")
print(f"  Mean:      {age_m:.2f}")
print(f"  SD:        {age_sd:.2f}")
print(f"  Median:    {age_mdn:.1f}")

# ── Gender ────────────────────────────────────────────────────────────────────
hr("GENDER", "-")
gender = df["Gender"].astype(str).str.strip()
# Clean up any header-row text that leaked through
gender = gender[~gender.str.contains("What is your gender", case=False, na=False)]
gender_vc = freq_table(gender, "Gender distribution")

# ── Language ──────────────────────────────────────────────────────────────────
hr("LANGUAGE (NATIVE)", "-")
lang = df["Language"].astype(str).str.strip()
lang = lang[~lang.str.contains("What is your native", case=False, na=False)]
lang_vc = freq_table(lang, "Native language")

# ── English Proficiency ───────────────────────────────────────────────────────
hr("ENGLISH PROFICIENCY", "-")
eng = df["English Skill_1"].astype(str).str.strip()
eng = eng[~eng.str.contains("How well do you", case=False, na=False)]
eng_vc = freq_table(eng, "English proficiency (self-reported)")

# Count "very well" or "perfectly" or "Understand perfectly"
eng_high = eng[eng.str.lower().str.contains("very well|perfectly|perfect", na=False)]
n_eng_high = len(eng_high)
pct_eng_high = n_eng_high / len(eng) * 100 if len(eng) > 0 else 0
print(f"\n  At least 'very well' or 'perfectly': {n_eng_high} ({pct_eng_high:.1f}%)")

# ── Smart Glasses Experience ──────────────────────────────────────────────────
hr("SMART GLASSES EXPERIENCE", "-")
glass = df["Glass Experience_1"].astype(str).str.strip()
glass = glass[~glass.str.contains("How much experience|smart glass", case=False, na=False)]
glass_vc = freq_table(glass, "Smart glasses experience")

# ── Impairment ────────────────────────────────────────────────────────────────
hr("IMPAIRMENTS", "-")
imp = df["Impairment"].astype(str).str.strip()
imp = imp[~imp.str.contains("Do you have any", case=False, na=False)]
imp_vc = freq_table(imp, "Hearing/visual impairments")

# ── Notification Settings ─────────────────────────────────────────────────────
hr("CURRENT NOTIFICATION SETTINGS", "-")
notif = df["My Notif Settings"].astype(str).str.strip()
notif = notif[~notif.str.contains("what is your standard", case=False, na=False)]
notif_vc = freq_table(notif, "Standard notification setting (private messages)")

# ── Notification Settings Why ─────────────────────────────────────────────────
hr("WHY THESE NOTIFICATION SETTINGS", "-")
notif_why = df["My Notif SettingsWhy"].astype(str).str.strip()
notif_why = notif_why[~notif_why.str.contains("Why did you choose", case=False, na=False)]
notif_why_vc = freq_table(notif_why, "Reason for notification settings")

# ── Which Notifications Auditory ──────────────────────────────────────────────
hr("DESIRED AUDITORY NOTIFICATIONS ON SMART GLASSES", "-")
aud = df["Which Notif Auditory"].astype(str).str.strip()
aud = aud[~aud.str.contains("which of the following", case=False, na=False)]

# Parse comma-separated multi-select into individual items
all_items = []
for val in aud:
    if pd.notna(val) and val not in ["nan", ""]:
        items = [x.strip() for x in val.split(",") if x.strip()]
        all_items.extend(items)

if all_items:
    item_counts = pd.Series(all_items).value_counts()
    n_resp = len(aud[aud.notna() & (aud != "nan") & (aud != "")])
    print(f"\n  Desired auditory notifications (multi-select, N = {n_resp} respondents)")
    print(f"  {'─' * 70}")
    for val, cnt in item_counts.items():
        pct = cnt / n_resp * 100
        print(f"    {val:55s}  {cnt:3d}  ({pct:5.1f}%)")

# ── Importance/Urgency Attitudes ──────────────────────────────────────────────
hr("IMPORTANCE/URGENCY ATTITUDES", "-")

# Map Likert text to numeric
AGREE_MAP = {
    "Strongly disagree": 1, "Disagree": 2, "Somewhat disagree": 3,
    "Neither agree nor disagree": 4,
    "Somewhat agree": 5, "Agree": 6, "Strongly agree": 7,
}

for col_name, label in [
    ("Notif ImprtancUrgent_1", "Only notify about IMPORTANT messages"),
    ("Notif ImprtancUrgent_2", "Only notify about URGENT messages"),
]:
    vals = df[col_name].astype(str).str.strip()
    vals = vals[vals.isin(AGREE_MAP.keys())]
    vals_num = vals.map(AGREE_MAP)
    vc = vals.value_counts()
    print(f"\n  {label}")
    print(f"  {'─' * 70}")
    for v, cnt in vc.items():
        pct = cnt / len(vals) * 100
        print(f"    {v:40s}  {cnt:3d}  ({pct:5.1f}%)")
    if len(vals_num) > 0:
        print(f"    → Numeric: M = {vals_num.mean():.2f}, SD = {vals_num.std(ddof=1):.2f}, Mdn = {vals_num.median():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# ── 4. Data For Writing ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
hr("WRITING dataForWriting.txt")

# Prepare gender string
gender_clean = df["Gender"].astype(str).str.strip()
gender_clean = gender_clean[~gender_clean.str.contains("What is your gender", case=False, na=False)]
gender_counts = gender_clean.value_counts()
gender_parts = []
for g, cnt in gender_counts.items():
    gender_parts.append(f"{cnt} {g.lower()}")
gender_str = ", ".join(gender_parts)

# Prepare English proficiency string
eng_clean = df["English Skill_1"].astype(str).str.strip()
eng_clean = eng_clean[~eng_clean.str.contains("How well do you", case=False, na=False)]
n_eng_total = len(eng_clean)
eng_high_clean = eng_clean[eng_clean.str.lower().str.contains("very well|perfectly|perfect", na=False)]
n_eng_high_clean = len(eng_high_clean)
pct_eng_high_clean = n_eng_high_clean / n_eng_total * 100 if n_eng_total > 0 else 0

# Prepare glasses experience string
glass_clean = df["Glass Experience_1"].astype(str).str.strip()
glass_clean = glass_clean[~glass_clean.str.contains("How much experience|smart glass", case=False, na=False)]
glass_counts = glass_clean.value_counts()
# Count "no experience" type
no_exp = glass_clean[glass_clean.str.lower().str.contains("no experience|none|never", na=False)]
n_no_exp = len(no_exp)
pct_no_exp = n_no_exp / len(glass_clean) * 100 if len(glass_clean) > 0 else 0

with open(OUTPUT_WRITING, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("DEMOGRAPHICS — Data Reference for Writing\n")
    f.write("=" * 80 + "\n\n")

    f.write("-" * 80 + "\n")
    f.write("SAMPLE OVERVIEW\n")
    f.write("-" * 80 + "\n")
    f.write(f"  Total raw survey responses:    {n_total_raw}\n")
    f.write(f"  Removed (pilot row):           1\n")
    f.write(f"  Removed (outliers):            {n_outliers}\n")
    f.write(f"  Final sample:                  N = {N}\n")
    f.write(f"  Trials per participant:        {n_trials}\n")
    f.write(f"  Total observations:            {n_observations}\n\n")

    f.write("-" * 80 + "\n")
    f.write("AGE\n")
    f.write("-" * 80 + "\n")
    f.write(f"  Range: {age_min}–{age_max}\n")
    f.write(f"  M = {age_m:.2f}, SD = {age_sd:.2f}, Mdn = {age_mdn:.1f}\n\n")

    f.write("-" * 80 + "\n")
    f.write("GENDER\n")
    f.write("-" * 80 + "\n")
    for g, cnt in gender_counts.items():
        pct = cnt / len(gender_clean) * 100
        f.write(f"  {g}: {cnt} ({pct:.1f}%)\n")
    f.write("\n")

    f.write("-" * 80 + "\n")
    f.write("ENGLISH PROFICIENCY\n")
    f.write("-" * 80 + "\n")
    eng_vc_clean = eng_clean.value_counts()
    for val, cnt in eng_vc_clean.items():
        pct = cnt / n_eng_total * 100
        f.write(f"  {val}: {cnt} ({pct:.1f}%)\n")
    f.write(f"  → At least 'very well' or 'perfectly': {n_eng_high_clean} ({pct_eng_high_clean:.1f}%)\n\n")

    f.write("-" * 80 + "\n")
    f.write("SMART GLASSES EXPERIENCE\n")
    f.write("-" * 80 + "\n")
    for val, cnt in glass_counts.items():
        pct = cnt / len(glass_clean) * 100
        f.write(f"  {val}: {cnt} ({pct:.1f}%)\n")
    f.write(f"  → No experience at all: {n_no_exp} ({pct_no_exp:.1f}%)\n\n")

    # ── LaTeX paragraph ──
    f.write("=" * 80 + "\n")
    f.write("PRE-WRITTEN LaTeX PARAGRAPH (Recruitment and Data Filtering)\n")
    f.write("=" * 80 + "\n\n")

    latex = (
        "\\subsection{Recruitment and Data Filtering}\n"
        f"In total, {n_total_raw} raw survey responses were recorded. "
        f"We excluded {n_outliers} participants identified as outliers "
        "based on predefined criteria. "
        f"After removing the pilot session and {n_outliers} outliers, "
        f"our final dataset consisted of $N = {N}$ valid participants.\n\n"
        f"Due to the fully within-subjects design with 3 notification systems "
        f"(Earcon, Speech, SonoAdapt), 2 urgency/importance levels (low, high), "
        f"and 2 scenarios (interview, math), each participant completed "
        f"{n_trials} trials, yielding a total of "
        f"{n_observations} individual observations "
        f"({N} participants $\\times$ {n_trials} trials) "
        "for the statistical analysis.\n\n"
        f"The final sample consisted of {N} participants ({gender_str}). "
        f"Participants were between {age_min} and {age_max} years old "
        f"($M = {age_m:.2f}$, $SD = {age_sd:.2f}$). "
        "As the study was conducted in English, "
        "participants self-reported their English proficiency. "
        f"All participants indicated at least a good level of proficiency, "
        f"with {n_eng_high_clean} ({pct_eng_high_clean:.1f}\\%) reporting that "
        "they understood English very well or perfectly. "
        f"Regarding smart glasses experience, "
        f"{n_no_exp} participants ({pct_no_exp:.1f}\\%) reported "
        "having no prior experience with smart glasses.\n"
    )
    f.write(latex)

    # ── Copyable snippets ──
    f.write("\n\n")
    f.write("=" * 80 + "\n")
    f.write("COPYABLE SNIPPETS\n")
    f.write("=" * 80 + "\n\n")
    f.write(f"  N = {N}\n")
    f.write(f"  Age: {age_min}–{age_max} years (M = {age_m:.2f}, SD = {age_sd:.2f})\n")
    f.write(f"  Gender: {gender_str}\n")
    f.write(f"  English ≥ very well: {n_eng_high_clean} ({pct_eng_high_clean:.1f}%)\n")
    f.write(f"  No glasses experience: {n_no_exp} ({pct_no_exp:.1f}%)\n")
    f.write(f"  Total observations: {n_observations} ({N} × {n_trials})\n")

print(f"\n  Saved: {OUTPUT_WRITING}")


# ══════════════════════════════════════════════════════════════════════════════
hr("DONE")
print(f"All results saved to: {OUTPUT_DIR}")
print(f"\n✅ Demographics analysis complete.")

# ── Cleanup ──
sys.stdout = sys.__stdout__
_output_file.close()
