"""
Generate General Notification Preference Pie Chart
====================================================
Creates the pie chart showing the general preference for notification type
when receiving an urgent/important message, independent of scenario context.

Output: 01_General_Preference_Pie.png
Originally: furtherPlots3.py
"""
import json
import matplotlib.pyplot as plt
import os
import numpy as np

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.dirname(SCRIPT_DIR)
JSON_FILE = os.path.join(FINAL_DIR, "appDataLogs.json")
OUTPUT_DIR = SCRIPT_DIR

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'Segoe UI Emoji', 'Tahoma', 'DejaVu Sans']

COLORS = {
    'No Audio': '#A6A6A6',
    'Earcon': '#FFC300',
    'Short Speech': '#AF7AC5',
    'Rich Speech': '#694487'
}


def map_category(raw_name):
    """Map raw JSON categories to clean display categories."""
    if "Version 1" in raw_name:
        return 'Earcon'
    elif "Version 2" in raw_name:
        return 'Short Speech'
    elif "Version 3" in raw_name:
        return 'Rich Speech'
    elif "don't want" in raw_name or "No" in raw_name:
        return 'No Audio'
    else:
        return 'No Audio'


def plot_pie_chart(data_dict, title, filename):
    labels = []
    sizes = []
    colors = []

    order = ['No Audio', 'Earcon', 'Short Speech', 'Rich Speech']

    agg_data = {k: 0 for k in order}
    for raw_name, stats in data_dict.items():
        clean_name = map_category(raw_name)
        agg_data[clean_name] += stats['n']

    for cat in order:
        if agg_data[cat] > 0:
            labels.append(cat)
            sizes.append(agg_data[cat])
            colors.append(COLORS[cat])

    fig, ax = plt.subplots(figsize=(8, 6))

    # pyrefly: ignore [bad-unpacking]
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        colors=colors,
        autopct=lambda pct: f"{pct:.1f}%\n(n={int(round(pct * sum(sizes) / 100))})",
        startangle=90,
        textprops=dict(color="black", fontsize=12)
    )

    for i, autotext in enumerate(autotexts):
        if labels[i] == 'Earcon' or labels[i] == 'No Audio':
            autotext.set_color('black')
            wedges[i].set_edgecolor('white')
            wedges[i].set_linewidth(1.5)
        else:
            autotext.set_color('white')
            wedges[i].set_edgecolor('#4A235A')
            wedges[i].set_linewidth(2)
        autotext.set_weight('bold')

    speech_n = agg_data['Short Speech'] + agg_data['Rich Speech']
    total_n = sum(agg_data.values())

    short_speech_pct = round((agg_data['Short Speech'] / total_n) * 100, 1)
    rich_speech_pct = round((agg_data['Rich Speech'] / total_n) * 100, 1)
    speech_pct = short_speech_pct + rich_speech_pct

    speech_wedges = [w for i, w in enumerate(wedges) if labels[i] in ['Short Speech', 'Rich Speech']]
    if len(speech_wedges) == 2:
        theta1 = speech_wedges[0].theta1
        theta2 = speech_wedges[1].theta2

        if theta2 < theta1:
            theta2 += 360

        mid_angle = (theta1 + theta2) / 2
        mid_angle_rad = np.deg2rad(mid_angle)

        x_target = 1.0 * np.cos(mid_angle_rad)
        y_target = 1.0 * np.sin(mid_angle_rad)

        x_text = 1.15 * np.cos(mid_angle_rad)
        y_text = 1.15 * np.sin(mid_angle_rad)

        ha = 'left' if x_text > 0 else 'right'

        ax.annotate(
            f"{speech_pct:.1f}%\n(n={speech_n})",
            xy=(x_target, y_target),
            xytext=(x_text, y_text),
            ha=ha, va='center',
            fontsize=12, weight='bold', color='#4A235A',
            bbox=dict(boxstyle="round,pad=0.4", fc="#F5EEF8", ec="#4A235A", lw=1.5),
            arrowprops=dict(arrowstyle="-|>", color="#4A235A", lw=1.5)
        )

    plt.title(title, fontsize=14, weight='bold', pad=20)
    plt.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {out_path}")
    plt.close()


def main():
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found. Please ensure appDataLogs.json is in the final/ folder.")
        return

    print(f"Reading data from {JSON_FILE}...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        log_data = json.load(f)

    if "general_notification_preference" in log_data:
        pref_data = log_data["general_notification_preference"]["breakdown"]
        plot_pie_chart(
            pref_data,
            "Important/Urgent Notification Preference\n(Independent of Scenarios)",
            "01_General_Preference_Pie.png"
        )
    else:
        print("general_notification_preference not found in JSON data.")


if __name__ == "__main__":
    main()
