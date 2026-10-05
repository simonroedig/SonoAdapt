"""
Generate Overall Timing Preference Pie Chart
===============================================
Creates the pie chart showing aggregate timing preferences across all 9 scenarios
(Immediate vs. Micro-Break vs. Break Between Subtasks vs. After Task is Finished).

Output: 02_Overall_Timing_Preference.png
Originally: furtherPlots322.py
"""
import json
import matplotlib.pyplot as plt
import os

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.dirname(SCRIPT_DIR)
JSON_FILE = os.path.join(FINAL_DIR, "06_preference_matrix", "scenario_preferences_summary_othersmerged.json")
OUTPUT_DIR = SCRIPT_DIR

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Segoe UI Emoji', 'Tahoma', 'DejaVu Sans']

COLORS = {
    'Immediate': '#E74C3C',
    'Micro-Break Within Task': '#85C1E9',
    'Break Between Subtasks': '#2E86C1',
    'After Task is Finished': '#1B4F72'
}

TIMING_MAP = {
    "Later, when I am done working": "After Task is Finished",
    "When I briefly pause while writing / thinking": "Micro-Break Within Task",
    "After I finish the current task (e.g., finish writing (part of the) code)": "Break Between Subtasks",
    "Later, when the meeting is over": "After Task is Finished",
    "After the meeting segment I am currently involved in ends": "Break Between Subtasks",
    "When I am not speaking and there is a natural break in conversation": "Micro-Break Within Task",
    "Later, when I am done with music and relaxing": "After Task is Finished",
    "When I am between songs / during a natural pause in music": "Break Between Subtasks",
    "Later, when the whole tent is set up and we are done working": "After Task is Finished",
    "After I finish setting up the current part of the tent (e.g., finishing putting in a pole)": "Break Between Subtasks",
    "When there is a brief pause in the physical setup (e.g., stopping to look at instructions or taking a breath)": "Micro-Break Within Task",
    "After I have finished cycling / reached my destination": "After Task is Finished",
    "After I reach a safe stopping point (e.g., at a traffic light)": "Break Between Subtasks",
    "When I am not actively crossing a street or making a decision about movement": "Micro-Break Within Task",
    "After I am done shopping": "After Task is Finished",
    "Between picking up items on my shopping list": "Micro-Break Within Task",
    "Once I have collected all items and start walking to the checkout": "Break Between Subtasks",
    "Later, when dinner is completely cooked and I am done in the kitchen": "After Task is Finished",
    "When there is a natural pause in the podcast or a brief break in cooking (e.g., waiting for water to boil)": "Micro-Break Within Task",
    "Later, when I am completely done studying": "After Task is Finished",
    "After I finish completing the current study task": "Break Between Subtasks",
    "When I briefly pause my studying/reading to take a sip of coffee or look up": "Micro-Break Within Task",
    "Later, after Jessica has left / our hangout is over": "After Task is Finished",
    "After we completely conclude our current topic of conversation": "Break Between Subtasks",
    "At the next natural pause in the conversation after we resume talking": "Micro-Break Within Task",
    "Other": "Other"
}


def plot_pie_chart(data_dict, title, filename):
    order = ['Immediate', 'Micro-Break Within Task', 'Break Between Subtasks', 'After Task is Finished']

    labels = []
    sizes = []
    colors = []

    for cat in order:
        if data_dict.get(cat, 0) > 0:
            labels.append(cat)
            sizes.append(data_dict[cat])
            colors.append(COLORS[cat])

    fig, ax = plt.subplots(figsize=(8, 6))

    # pyrefly: ignore [bad-unpacking]
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%\n(n={int(round(pct * sum(sizes) / 100))})",
        startangle=90,
        textprops=dict(color="black", fontsize=11)
    )

    for i, autotext in enumerate(autotexts):
        if labels[i] in ['Break Between Subtasks', 'After Task is Finished']:
            autotext.set_color('white')
        else:
            autotext.set_color('black')

        wedges[i].set_edgecolor('white')
        wedges[i].set_linewidth(1.5)
        autotext.set_weight('bold')

    plt.title(title, fontsize=14, weight='bold', pad=20)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {out_path}")
    plt.close()


def main():
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Reading data from {JSON_FILE}...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    aggregated_timing = {
        'Immediate': 0,
        'Micro-Break Within Task': 0,
        'Break Between Subtasks': 0,
        'After Task is Finished': 0
    }

    for scene_key, scene_data in data.items():
        if "Immediate" in scene_data.get("macro_timing", {}):
            aggregated_timing["Immediate"] += scene_data["macro_timing"]["Immediate"].get("Total", 0)

        if "micro_timing_delayed_breakdown" in scene_data:
            for specific_timing, counts in scene_data["micro_timing_delayed_breakdown"].items():
                mapped_category = TIMING_MAP.get(specific_timing)
                if mapped_category in aggregated_timing:
                    aggregated_timing[mapped_category] += counts.get("Total", 0)

    plot_pie_chart(
        aggregated_timing,
        "Overall Timing Preference\n(Aggregated across all 9 scenarios)",
        "02_Overall_Timing_Preference.png"
    )


if __name__ == "__main__":
    main()
