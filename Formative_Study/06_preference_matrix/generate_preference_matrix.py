"""
Generate Preference Matrix (Stacked Bar Charts per Scenario)
==============================================================
Creates stacked bar charts showing notification type × timing preference
for each of the 9 scenarios (Stage 3), plus a standalone legend.

These plots are combined in the thesis as the "PreferenceMatrix" figure.

Outputs:
  - Legend_Standalone.png
  - StackedBars_DualBrackets_Scene_1_Home_Alone_Computer.png ... (9 plots)

Originally: preferenceNew2Plot.py
"""
import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os
import textwrap

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "scenario_preferences_summary_othersmerged.json")
OUTPUT_DIR = SCRIPT_DIR

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Segoe UI Emoji', 'Tahoma', 'DejaVu Sans']

FORMAT_MAP = {
    "Earcon (V1)": "Earcon",
    "Short Speech (V2)": "Short Speech",
    "Rich Speech (V3)": "Rich Speech",
    "None / No Audio": "No Audio"
}

VERSION_ORDER = ['Earcon (V1)', 'Short Speech (V2)', 'Rich Speech (V3)', 'None / No Audio']
COLORS = {
    'Earcon (V1)':        '#D4AC0D',
    'Short Speech (V2)':  '#BB8FCE',
    'Rich Speech (V3)':   '#6A1B9A',
    'None / No Audio':    '#CCCCCC',
}

TIMING_MAP = {
    "Later, when I am done working": "After Task is Finished",
    "When I briefly pause while writing / thinking": "Micro-Break",
    "After I finish the current task (e.g., finish writing (part of the) code)": "Subtask Break",
    "Later, when the meeting is over": "After Task is Finished",
    "After the meeting segment I am currently involved in ends": "Subtask Break",
    "When I am not speaking and there is a natural break in conversation": "Micro-Break",
    "Later, when I am done with music and relaxing": "After Task is Finished",
    "When I am between songs / during a natural pause in music": "Subtask Break",
    "Later, when the whole tent is set up and we are done working": "After Task is Finished",
    "After I finish setting up the current part of the tent (e.g., finishing putting in a pole)": "Subtask Break",
    "When there is a brief pause in the physical setup (e.g., stopping to look at instructions or taking a breath)": "Micro-Break",
    "After I have finished cycling / reached my destination": "After Task is Finished",
    "After I reach a safe stopping point (e.g., at a traffic light)": "Subtask Break",
    "When I am not actively crossing a street or making a decision about movement": "Micro-Break",
    "After I am done shopping": "After Task is Finished",
    "Between picking up items on my shopping list": "Micro-Break",
    "Once I have collected all items and start walking to the checkout": "Subtask Break",
    "Later, when dinner is completely cooked and I am done in the kitchen": "After Task is Finished",
    "When there is a natural pause in the podcast or a brief break in cooking (e.g., waiting for water to boil)": "Micro-Break",
    "Later, when I am completely done studying": "After Task is Finished",
    "After I finish completing the current study task": "Subtask Break",
    "When I briefly pause my studying/reading to take a sip of coffee or look up": "Micro-Break",
    "Later, after Jessica has left / our hangout is over": "After Task is Finished",
    "After we completely conclude our current topic of conversation": "Subtask Break",
    "At the next natural pause in the conversation after we resume talking": "Micro-Break",
    "Other": "Other"
}

TIMING_ORDER = ['Immediate', 'Micro-Break', 'Subtask Break', 'After Task is Finished']


def get_top_format(macro_data):
    total = macro_data.get("Total", 0)
    format_counts = {k: v for k, v in macro_data.items() if k != "Total"}
    top_format_raw = max(format_counts, key=format_counts.get) if format_counts else "None"
    top_format_clean = FORMAT_MAP.get(top_format_raw, top_format_raw)
    return total, top_format_clean


def plot_stacked_bars_with_dual_brackets(scene_num, scene_name, timing_version_counts, macro_imm_data, macro_delayed_data, filename):
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)

    x_pos = range(len(TIMING_ORDER))
    bar_width = 0.6

    bottoms = [0] * len(TIMING_ORDER)
    for version in VERSION_ORDER:
        vals = [timing_version_counts[t].get(version, 0) for t in TIMING_ORDER]
        if sum(vals) == 0:
            continue
        bars = ax.bar(x_pos, vals, bottom=bottoms, width=bar_width,
                       color=COLORS[version], edgecolor='black', linewidth=0.8,
                       label=version, zorder=3)
        for i, (val, bot) in enumerate(zip(vals, bottoms)):
            if val > 0:
                ax.text(i, bot + val / 2, str(int(val)),
                        ha='center', va='center', color='white',
                        fontsize=10, fontweight='bold', zorder=4)
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    for i, total in enumerate(bottoms):
        if total > 0:
            ax.text(i, total + 0.5, f'n={int(total)}',
                    ha='center', va='bottom', color='black',
                    fontweight='bold', fontsize=11)

    ax.set_title(f'Notification Timing Flow\n(Scenario {scene_num}: {scene_name})', fontsize=14, weight='bold', pad=15)
    ax.set_ylabel('Number of Participants', fontsize=12, weight='bold')

    formatted_labels = [textwrap.fill(label, width=15) for label in TIMING_ORDER]
    ax.set_xticks(x_pos)
    ax.set_xticklabels(formatted_labels, fontsize=11, weight='bold')

    plt.ylim(0, 30)
    plt.xlim(-0.6, 3.5)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', linestyle='--', alpha=0.3, zorder=1)
    ax.grid(axis='x', linestyle='--', alpha=0.1, zorder=1)

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(out_path)
    plt.close()


def main():
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found. Run generate_preference_data.py first.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Generate standalone legend
    fig_leg, ax_leg = plt.subplots(figsize=(4, 2), dpi=300)
    ax_leg.axis('off')
    legend_order = ['None / No Audio', 'Earcon (V1)', 'Short Speech (V2)', 'Rich Speech (V3)']
    legend_labels = ['No Audio', 'Earcon', 'Short Speech', 'Rich Speech']
    legend_patches = [mpatches.Patch(color=COLORS[v], label=lbl, ec='black', lw=0.8)
                      for v, lbl in zip(legend_order, legend_labels)]
    ax_leg.legend(handles=legend_patches, title='Audio Type', loc='center',
                  fontsize=10, title_fontsize=11)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'Legend_Standalone.png'), bbox_inches='tight')
    plt.close()
    print("Legend saved.")

    for scene_key, scene_data in data.items():
        scene_name = scene_data["scenario_name"]
        scene_num = scene_key.split('_')[1]

        timing_version_counts = {t: {v: 0 for v in VERSION_ORDER} for t in TIMING_ORDER}

        macro_imm_data = scene_data.get("macro_timing", {}).get("Immediate", {})
        for version in VERSION_ORDER:
            timing_version_counts["Immediate"][version] = macro_imm_data.get(version, 0)

        delayed_breakdown_data = scene_data.get("micro_timing_delayed_breakdown", {})
        for raw_timing, timing_counts in delayed_breakdown_data.items():
            clean_timing = TIMING_MAP.get(raw_timing, "Other")
            if clean_timing in TIMING_ORDER:
                for version in VERSION_ORDER:
                    timing_version_counts[clean_timing][version] += timing_counts.get(version, 0)

        macro_delayed_data = scene_data.get("macro_timing", {}).get("Delayed", {})

        imm_total, top_imm_format = get_top_format(macro_imm_data)
        delayed_total, top_del_format = get_top_format(macro_delayed_data)

        print(f"\n{'=' * 50}")
        print(f"SCENARIO {scene_num}: {scene_name.upper()}")
        print(f"{'=' * 50}")

        safe_filename = f"StackedBars_DualBrackets_{scene_key}.png"
        plot_stacked_bars_with_dual_brackets(scene_num, scene_name, timing_version_counts, macro_imm_data, macro_delayed_data, safe_filename)
        print(f"  → Saved: {safe_filename}")

    print("\nAll preference matrix charts generated successfully!")


if __name__ == "__main__":
    main()
