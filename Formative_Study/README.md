# SonoAdapt Formative Study — Analysis & Results

This folder contains all scripts, data, and generated plots for the formative study of the thesis.

## How to Run

All scripts require Python 3.9+ with the dependencies listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

Scripts should be run from their respective subdirectories, e.g.:
```bash
cd 01_main_effects
python generate_main_effects.py
```

For the Streamlit dashboard:
```bash
cd 09_dashboard
streamlit run streamlit_dashboard.py
```

---

## Folder Structure

### Root Files (Shared Data)

| File | Description |
|------|-------------|
| `data.xlsx` | Raw Qualtrics survey data (53 responses) |
| `listOfManuallyIdentifiedOutliers.txt` | 16 participant IDs excluded (failed headphone/attention checks) |
| `appDataLogs.json` | Processed survey logs (general preferences, per-scenario breakdowns) |
| `descriptive_statistics.csv` | Aggregated descriptive statistics (means & SDs) |
| `perScenarioLikertMeans.json` | Per-scenario Likert means for all 9 scenarios |
| `perScenarioNormalizedCosts.json` | Per-scenario normalized costs (0–1 scale) for SonoAdapt calibration |
| `requirements.txt` | Python package dependencies |
| `shared_utils.py` | Shared data-loading and transformation functions (imported by analysis scripts) |

---

### 01_main_effects/

**Box plots for the main LMM effects** (Disruption, Social Acceptability, Detectability),
each shown overall and broken down by notification type per factor level.

| File | Description |
|------|-------------|
| `generate_main_effects.py` | Generates all main effect and breakdown box plots |
| `main_effects/` | 7 plots: overall main effects by factor + combined notification type views |
| `main_effect_breakdown/` | 9 plots: per-factor-level breakdowns by notification type |

**Thesis figures:** `fig:box_disruption`, `fig:box_social`, `fig:box_detectability`

---

### 02_statistical_analysis/

**All statistical computations** — Linear Mixed Models, omnibus tests, pairwise comparisons,
per-scenario means, and thesis number verification.

| File | Description |
|------|-------------|
| `run_lmm_analysis.py` | Fits 4 LMMs + dominance analysis, saves output to `lmm_analysis_output.txt` |
| `run_omnibus_tests.py` | Type III Wald χ² omnibus tests for all factors × DVs |
| `run_pairwise_comparisons.py` | All pairwise LMM re-fits with shifted reference levels |
| `compute_per_scenario_means.py` | Per-scenario descriptive means + normalized cost JSON |
| `verify_all_numbers.py` | Cross-checks every number cited in the thesis |

**Thesis tables:** `tab:omnibus_tests`, `tab:lmm_pairwise`, `tab:descriptive_summary`, `tab:relative_importance`

---

### 03_general_preference/

**Pie chart: context-independent notification preference** (Fig. 3 in thesis).

| File | Description |
|------|-------------|
| `generate_general_preference.py` | Generates the preference pie chart |
| `01_General_Preference_Pie.png` | Output: 72.9% prefer speech for urgent/important messages |

**Thesis figure:** `fig:general_notification_preference`

---

### 04_preference_development/

**Flow chart: preference evolution across 3 stages** (context-independent → in-scenario → after timing).

| File | Description |
|------|-------------|
| `generate_preference_development.py` | Generates the stacked bar flow chart |
| `06_Preference_Development_Flow.png` | Output: speech drops to 45.6% in Stage 2, rebounds to 70.2% in Stage 3 |

**Thesis figure:** `fig:preference_flow`

---

### 05_overall_timing/

**Pie chart: overall timing preference** aggregated across all 9 scenarios.

| File | Description |
|------|-------------|
| `generate_overall_timing.py` | Generates the timing preference pie chart |
| `02_Overall_Timing_Preference.png` | Output: 45.6% immediate, 54.4% deferred |

**Thesis figure:** `fig:overall_timing_pref`

---

### 06_preference_matrix/

**Per-scenario stacked bar charts** showing type × timing preferences (Stage 3).
Combined as "PreferenceMatrix" in the thesis.

| File | Description |
|------|-------------|
| `generate_preference_data.py` | Extracts preference data from raw survey → JSON (run first!) |
| `generate_preference_matrix.py` | Generates all 9 stacked bar charts + legend |
| `scenario_preferences_summary_othersmerged.json` | Intermediate JSON data |
| `Legend_Standalone.png` | Shared legend for all 9 charts |
| `StackedBars_DualBrackets_Scene_*.png` | 9 per-scenario charts |

**Thesis figure:** `fig:preference_matrix`

---

### 07_intra_user_variance/

**Intra-user variance analysis** — how much participants change their preference across scenarios.

| File | Description |
|------|-------------|
| `generate_intra_user_variance.py` | Generates both variance plots |
| `01_Stage2_Type_Variance.png` | Output: ~89% of users adapt their type across scenarios |
| `02_Stage2_Speech_Profile.png` | Output: ~41% alternate between Rich and Short Speech |

**Thesis figures:** `fig:type_variance`, `fig:speech_profile`

---

### 08_message_priority/

**Message priority flow charts** — how type preference and delay tolerance shift with urgency/importance.

| File | Description |
|------|-------------|
| `generate_message_priority.py` | Generates both flow charts |
| `02_Preference_Flow_Matrix.png` | Output: type preference shifts across 4 priority levels |
| `03_Delay_Tolerance_Flow.png` | Output: delay tolerance shifts across 4 priority levels |

**Thesis figures:** `fig:urgency_type_shift`, `fig:urgency_delay_shift`

---

### 09_dashboard/

**Interactive Streamlit dashboard** for exploring the survey data.

| File | Description |
|------|-------------|
| `streamlit_dashboard.py` | Run with `streamlit run streamlit_dashboard.py` |

