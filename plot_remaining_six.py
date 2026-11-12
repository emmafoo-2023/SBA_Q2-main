"""Plot unreviewed validation cases caught by 20-of-30 but missed by Continuous20.

Run from the extracted project folder:
    python plot_remaining_six.py
Use --baseline-dir if the existing comparison script wrote to another folder.
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=Path("floor3_alert_results_v3"))
    parser.add_argument("--out", type=Path, default=Path("remaining_case_review"))
    args = parser.parse_args()

    keys = ["unit", "period", "direction", "case_start", "case_end_exclusive"]
    dates = ["case_start", "case_end_exclusive"]
    cases = pd.read_csv("development_validation_case_comparison.csv", parse_dates=dates)
    key = pd.read_csv("review_answer_key.csv", parse_dates=dates)
    ratings = pd.read_csv("step3_inputs/reviewer1_ratings.csv")
    reviewed_ids = ratings.loc[ratings.reviewer_1_rating.fillna("").str.strip().ne(""), "review_id"]
    reviewed = key.loc[key.review_id.isin(reviewed_ids), keys].drop_duplicates()

    selected = cases.loc[
        cases.period.eq("validation") & cases["20of30"].notna() & cases.continuous20.isna(), keys
    ].merge(reviewed, on=keys, how="left", indicator=True)
    remaining = selected.loc[selected["_merge"].eq("left_only"), keys].sort_values(["unit", "case_start"])

    if remaining.empty:
        print("All matching validation cases already have a recorded review.")
        return

    baselines = {}
    for unit in remaining.unit.unique():
        file = args.baseline_dir / f"{unit.removesuffix('(kW)')}_baseline.csv.gz"
        if not file.is_file():
            parser.exit(1, f"Missing {file}. Run compare_floor3_alerts_v3.py first or set --baseline-dir.\n")
        baselines[unit] = pd.read_csv(file, parse_dates=["Date"]).set_index("Date")

    args.out.mkdir(parents=True, exist_ok=True)
    review_rows = []
    for number, row in enumerate(remaining.itertuples(index=False), start=1):
        review_id = f"V{number:02d}"
        start, end = row.case_start, row.case_end_exclusive
        padding = pd.Timedelta(minutes=45)
        power = baselines[row.unit].loc[start - padding:end + padding]
        expected, threshold = power.expected_kw, power.threshold_kw

        fig, ax = plt.subplots(figsize=(10, 4.2))
        ax.fill_between(power.index, (expected - threshold).to_numpy(),
                        (expected + threshold).to_numpy(), color="#cbd5e1", alpha=.6,
                        label="Expected power ± threshold")
        ax.plot(power.index, power.observed_kw, color="#0369a1", label="Observed power")
        ax.plot(power.index, expected, color="#c2410c", label="Expected power")
        ax.axvspan(start, end, color="#fbbf24", alpha=.15, label="Review window")
        ax.set_title(f"{review_id} | {row.unit} | {start:%d %b %Y}")
        ax.set_ylabel("Power (kW)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
        fig.tight_layout()
        image = f"{review_id}.png"
        fig.savefig(args.out / image, dpi=150)
        plt.close(fig)
        review_rows.append({"review_id": review_id, "unit": row.unit, "direction": row.direction,
                            "window_start": start, "window_end_exclusive": end, "plot": image,
                            "rating": "", "reason": "", "supporting_evidence_needed": ""})

    form = args.out / "review_remaining_cases.csv"
    if form.exists():
        form = args.out / "review_remaining_cases_blank.csv"
    pd.DataFrame(review_rows).to_csv(form, index=False)
    print(f"Created {len(review_rows)} plots in {args.out} and review form {form}.")


if __name__ == "__main__":
    main()
