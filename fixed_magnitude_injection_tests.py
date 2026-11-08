"""Fixed-magnitude controlled tests for the four Floor 3 alert policies.

Adds +1, +5 or +10 kW to the original observed power on designated minutes.
The historical baseline and threshold stay on the unmodified series. A minute
counts as abnormal only when the new reading exceeds that threshold. This is
separate from controlled_injection_tests.py, which forces every scheduled
minute just past the threshold.

May-June and July-September only. October-December is not used. The original
CSV is not modified.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from controlled_injection_tests import (
    HOST_MINUTES,
    PERIODS,
    PLACEMENT_CAP,
    POLICIES,
    POLICY_LABELS,
    PRE_MINUTES,
    alerts_via_case_attribution,
    candidate_onsets,
    expand_pattern,
    first_delay,
    load_power,
    negative_control,
    period_index_bounds,
    prepare_unit,
    select_onsets,
    study_triggers,
)

DELTAS_KW = (1.0, 5.0, 10.0)
PAIRED_DELTA_KW = 10.0
FIXED_PATTERNS = (
    ("spike_1", "spike", (("on", 1),)),
    ("spike_5", "spike", (("on", 5),)),
    ("continuous_20", "continuous", (("on", 20),)),
    ("continuous_30", "continuous", (("on", 30),)),
    ("two_bursts", "intermittent", (("on", 10), ("off", 5), ("on", 10))),
)
PATTERN_MASKS = {name: expand_pattern(blocks) for name, _family, blocks in FIXED_PATTERNS}
PATTERN_FAMILY = {name: family for name, family, _blocks in FIXED_PATTERNS}


def logic_check():
    """Injections are added to observed power. A sub-threshold change is a miss."""
    n = HOST_MINUTES
    actual = np.full(n, 5.0)
    expected = np.full(n, 5.0)
    threshold = np.full(n, 2.0)
    valid = np.ones(n, dtype=bool)
    on = np.zeros(n, dtype=bool)
    on[PRE_MINUTES] = True
    injected = actual.copy()
    injected[on] = actual[on] + 1.0
    if not np.allclose(injected[on], actual[on] + 1.0):
        raise AssertionError("Fixed increase was not added to the original reading.")
    flag = valid & ((injected - expected) > threshold)
    if flag.any():
        raise AssertionError("+1 kW crossed a 2 kW threshold in the logic check.")
    triggers = study_triggers(flag, valid)
    if any(triggers[name].any() for name in POLICIES):
        raise AssertionError("A sub-threshold injection produced an alert.")

    injected[on] = actual[on] + 5.0
    flag = valid & ((injected - expected) > threshold)
    triggers = study_triggers(flag, valid)
    if first_delay(triggers["immediate"], PRE_MINUTES, PRE_MINUTES + 30) != 0:
        raise AssertionError("A 1-minute crossing was not alerted at onset.")
    for name in ("continuous20", "continuous30", "20of30"):
        if first_delay(triggers[name], PRE_MINUTES, PRE_MINUTES + 30) is not None:
            raise AssertionError(f"{name} alerted on a 1-minute spike.")

    on[:] = False
    on[PRE_MINUTES:PRE_MINUTES + 20] = True
    wide = threshold.copy()
    wide[PRE_MINUTES:PRE_MINUTES + 10] = 20.0
    injected = actual.copy()
    injected[on] = actual[on] + 5.0
    flag = valid & ((injected - expected) > wide)
    triggers = study_triggers(flag, valid)
    search_end = PRE_MINUTES + 20 + 29
    if first_delay(triggers["immediate"], PRE_MINUTES, search_end) != 10:
        raise AssertionError("Delay was not measured from the first injected minute.")
    if first_delay(triggers["continuous20"], PRE_MINUTES, search_end) is not None:
        raise AssertionError("Continuous20 alerted without 20 consecutive crossings.")

    bursts = np.zeros(n, dtype=bool)
    bursts[PRE_MINUTES:PRE_MINUTES + 10] = True
    bursts[PRE_MINUTES + 15:PRE_MINUTES + 25] = True
    injected = actual.copy()
    injected[bursts] = actual[bursts] + 5.0
    flag = valid & ((injected - expected) > threshold)
    triggers = study_triggers(flag, valid)
    search_end = PRE_MINUTES + 25 + 29
    if first_delay(triggers["continuous20"], PRE_MINUTES, search_end) is not None:
        raise AssertionError("Continuous20 alerted on two bursts of 10.")
    if first_delay(triggers["20of30"], PRE_MINUTES, search_end) != 24:
        raise AssertionError("20of30 delay on two fully crossing bursts was not 24 minutes.")
    attributed = alerts_via_case_attribution(flag, triggers["20of30"], valid)
    if attributed != [PRE_MINUTES + 24]:
        raise AssertionError("Case attribution disagreed with the 20of30 trigger.")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def onset_holds(onsets: np.ndarray, feasible: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if len(onsets) == 0:
        return np.zeros(0, dtype=bool)
    ok = np.ones(len(onsets), dtype=bool)
    for relative in np.flatnonzero(mask):
        ok &= feasible[onsets + relative]
    return ok


def power_feasible(actual: np.ndarray, delta: float) -> np.ndarray:
    updated = actual + delta
    return np.isfinite(actual) & np.isfinite(updated) & (updated >= 0) & (updated <= 100)


def evaluate_increase(series, onset: int, mask: np.ndarray, delta: float) -> dict:
    start = onset - PRE_MINUTES
    stop = start + HOST_MINUTES
    actual = series["actual"][start:stop]
    expected = series["expected"][start:stop]
    threshold = series["threshold"][start:stop]
    valid = series["valid"][start:stop]
    if len(actual) != HOST_MINUTES or not valid.all() or not series["quiet"][start:stop].all():
        raise AssertionError("Selected host was not fully quiet and observed.")
    if negative_control(series, onset):
        raise AssertionError("Unchanged host already produced an alert.")
    on = np.zeros(HOST_MINUTES, dtype=bool)
    on[PRE_MINUTES:PRE_MINUTES + len(mask)] = mask
    injected = actual.copy()
    injected[on] = actual[on] + delta
    if not np.allclose(injected[on], actual[on] + delta) or not np.array_equal(injected[~on], actual[~on]):
        raise AssertionError("Injection did not add the fixed increase to the original readings only.")
    if np.any(injected[on] < 0) or np.any(injected[on] > 100):
        raise AssertionError("An infeasible value was injected instead of being excluded.")
    high = valid & ((injected - expected) > threshold)
    if high[~on].any():
        raise AssertionError("A minute outside the injection became abnormal.")
    crossing = high & on
    any_crossing = bool(crossing.any())
    triggers = study_triggers(high, valid)
    search_end = PRE_MINUTES + len(mask) + 29
    delays = {}
    for policy in POLICIES:
        delay = first_delay(triggers[policy], PRE_MINUTES, search_end)
        attributed = [item for item in alerts_via_case_attribution(high, triggers[policy], valid)
                      if PRE_MINUTES <= item < search_end]
        if delay is None and attributed:
            raise AssertionError("Case attribution found an alert the trigger search missed.")
        if delay is not None and attributed[:1] != [PRE_MINUTES + delay]:
            raise AssertionError("Alert time disagrees with the comparison script's case attribution.")
        if not any_crossing and delay is not None:
            raise AssertionError("An alert was counted without a threshold crossing.")
        delays[policy] = delay
    if any_crossing and delays["immediate"] is None:
        raise AssertionError("Immediate missed a fully observed minute that crossed the threshold.")
    first_cross = int(np.flatnonzero(crossing)[0] - PRE_MINUTES) if any_crossing else None
    if delays["immediate"] != first_cross:
        raise AssertionError("Immediate delay is not the time from the first injected minute to the first crossing.")
    return {
        "n_injected_minutes": int(on.sum()),
        "n_crossing_minutes": int(crossing.sum()),
        "any_crossing": any_crossing,
        "first_crossing_offset_min": first_cross,
        "median_observed_kw": float(np.median(actual[on])),
        "median_expected_kw": float(np.median(expected[on])),
        "median_threshold_kw": float(np.median(threshold[on])),
        "median_injected_kw": float(np.median(injected[on])),
        "slot_expected_kw": float(series["slot_expected"][onset + 59]),
        "delays": delays,
    }


def summarise(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if events.empty:
        return pd.DataFrame()
    keys = ["period", "pattern", "family", "magnitude_kw"]
    for values, group in events.groupby(keys, sort=False):
        placed = len(group)
        crossed = int(group.any_crossing.sum())
        no_crossing = placed - crossed
        for policy in POLICIES:
            detected_mask = group[f"{policy}_detected"].astype(bool)
            detected = int(detected_mask.sum())
            delays = group.loc[detected_mask, f"{policy}_delay_min"]
            despite = int((group.any_crossing & ~detected_mask).sum())
            rows.append({
                "period": values[0],
                "pattern": values[1],
                "family": values[2],
                "magnitude_kw": values[3],
                "policy": policy,
                "placed": placed,
                "crossed": crossed,
                "crossed_rate": crossed / placed,
                "detected": detected,
                "detection_rate": detected / placed,
                "delay_min": float(delays.min()) if detected else np.nan,
                "delay_median_min": float(delays.median()) if detected else np.nan,
                "delay_max": float(delays.max()) if detected else np.nan,
                "miss_no_crossing": no_crossing,
                "miss_despite_crossing": despite,
            })
    summary = pd.DataFrame(rows)
    for _, group in summary.groupby(keys):
        if (group.detected + group.miss_no_crossing + group.miss_despite_crossing != group.placed).any():
            raise AssertionError("Summary counts do not add up to the placed windows.")
        if (group.crossed + group.miss_no_crossing != group.placed).any():
            raise AssertionError("Crossing counts do not add up to the placed windows.")
    return summary


def assert_summary_matches_events(summary: pd.DataFrame, events: pd.DataFrame):
    if events.empty:
        return
    for policy in POLICIES:
        for values, group in events.groupby(["period", "pattern", "magnitude_kw"], sort=False):
            row = summary[(summary.period == values[0]) & (summary.pattern == values[1])
                          & (summary.magnitude_kw == values[2]) & (summary.policy == policy)]
            if len(row) != 1:
                raise AssertionError("Summary is missing an event group.")
            detected = int(group[f"{policy}_detected"].sum())
            if int(row.placed.iloc[0]) != len(group) or int(row.detected.iloc[0]) != detected:
                raise AssertionError("Summary counts disagree with the event file.")
            if int(row.crossed.iloc[0]) != int(group.any_crossing.sum()):
                raise AssertionError("Crossing counts disagree with the event file.")
            delays = group.loc[group[f"{policy}_detected"].astype(bool), f"{policy}_delay_min"]
            if detected == 0:
                continue
            if float(row.delay_min.iloc[0]) != float(delays.min()) or float(row.delay_max.iloc[0]) != float(delays.max()):
                raise AssertionError("Delay range disagrees with the event file.")
            if float(row.delay_median_min.iloc[0]) != float(delays.median()):
                raise AssertionError("Median delay disagrees with the event file.")


def _same_feasibility(exclusions: pd.DataFrame) -> bool:
    if exclusions.empty:
        return True
    counts = exclusions.pivot_table(index=["unit", "period", "pattern"], columns="magnitude_kw",
                                    values="feasible_onsets", aggfunc="sum")
    return bool(counts.nunique(axis=1).max() == 1)


def _pct(rate: float) -> str:
    return f"{rate:.0%}"


def _delay_text(row) -> str:
    if int(row.detected) == 0 or pd.isna(row.delay_median_min):
        return ""
    low, mid, high = int(row.delay_min), row.delay_median_min, int(row.delay_max)
    if low == high:
        return f"{low}"
    return f"{mid:.0f} [{low}, {high}]"


def write_report(dest: Path, summary: pd.DataFrame, exclusions: pd.DataFrame, events: pd.DataFrame):
    lines = [
        "# Fixed-magnitude injection tests",
        "",
        "These are controlled sensitivity tests. A known increase was added to real power readings. They are not confirmed AC faults, and they are not an estimate of fault-detection accuracy.",
        "",
        "## How this differs from the threshold-crossing tests",
        "",
        "The threshold-crossing test moves each scheduled minute to 0.1 kW past the local threshold, so every scheduled minute is abnormal by construction. This test adds a fixed +1, +5 or +10 kW to the original observed power and leaves every other minute unchanged. The 28-day baseline and the threshold, the larger of three historical standard deviations and 0.5 kW, are computed from the unmodified series. An injected minute is abnormal only when the new reading is far enough above that expected power. A change that stays inside the band is a miss for every policy.",
        "",
        "The same quiet, fully observed May-September windows are used for +1, +5 and +10 kW. A window is kept only when every designated minute can accept +10 kW without leaving 0-100 kW. Smaller increases are then applied to those same windows. Values are not clipped into range. October-December is not used.",
        "",
        "## Windows and exclusions",
        "",
    ]
    if exclusions.empty:
        lines.append("No candidate windows were examined.")
    else:
        quiet = int(exclusions.drop_duplicates(["unit", "period", "pattern"]).quiet_onsets.sum())
        paired = exclusions[exclusions.magnitude_kw == PAIRED_DELTA_KW]
        lines.append(
            f"Quiet, fully observed start minutes across units, periods and patterns: {quiet}. "
            "These minutes overlap inside long quiet stretches, so this is not a count of separate events. "
            f"Of those starts, {int(paired.excluded_above_100.sum())} could not accept +10 kW because the original reading plus 10 kW would exceed 100 kW. "
            f"{int(paired.excluded_below_0.sum())} would have fallen below 0 kW. "
            f"The paired sample places {int(paired.placed.sum())} pattern-windows from the starts that can accept +10 kW, at most {PLACEMENT_CAP} per unit, period and pattern, spread across months, 6-hour bands and whether the hour's median expected power is at least 1 kW."
        )
        lines.extend([
            "",
            "| Period | Pattern | Quiet starts | Feasible at +1 kW | Feasible at +5 kW | Feasible at +10 kW | Excluded at +10 kW for exceeding 100 | Placed paired windows |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ])
        order = [name for name, _, _ in FIXED_PATTERNS]
        wide = exclusions.pivot_table(index=["period", "pattern"], columns="magnitude_kw",
                                      values=["quiet_onsets", "feasible_onsets", "excluded_above_100", "placed"],
                                      aggfunc="sum")
        for period, _, _ in PERIODS:
            for pattern in order:
                if (period, pattern) not in wide.index:
                    continue
                row = wide.loc[(period, pattern)]
                lines.append(
                    f"| {period} | {pattern} | {int(row[('quiet_onsets', 1.0)])} | "
                    f"{int(row[('feasible_onsets', 1.0)])} | {int(row[('feasible_onsets', 5.0)])} | "
                    f"{int(row[('feasible_onsets', 10.0)])} | {int(row[('excluded_above_100', 10.0)])} | "
                    f"{int(row[('placed', 10.0)])} |"
                )
        lines.append("")
        excluded_high = int(paired.excluded_above_100.sum())
        excluded_low = int(paired.excluded_below_0.sum())
        if _same_feasibility(exclusions) and excluded_high == 0 and excluded_low == 0:
            lines.append(
                "Every quiet start could accept +1, +5 and +10 kW without leaving 0-100 kW, so none were excluded for range. "
                "The detection tables use those same placed windows for every magnitude."
            )
        else:
            lines.append(
                "Feasible counts are reported separately because range limits can differ by magnitude. "
                "The detection tables use only the placed paired windows, so +1, +5 and +10 kW are compared on the same hosts. "
                "Starts that can accept a smaller increase but not +10 kW stay out of that comparison."
            )
        if not events.empty:
            hosts = [set(map(tuple, events.loc[events.pattern == name, ["unit", "period", "onset"]].to_numpy()))
                     for name, _, _ in FIXED_PATTERNS]
            if hosts and all(item == hosts[0] for item in hosts):
                lines.append(
                    f"All five patterns were placed on the same {len(hosts[0])} hosts. "
                    "Each host was tested at all three magnitudes."
                )
    lines.extend(["", "## Detection", ""])
    lines.append(
        "Crossed counts windows with at least one injected minute above the threshold. "
        "Detected counts windows that produced an alert. "
        "A detection rate of 100% means every placed window alerted. "
        "Misses with no crossing equal placed minus crossed, and they are misses for every policy. "
        "Misses despite a crossing are windows that did cross and still did not alert. "
        "Delay is minutes from the first injected minute to the first alert. The range is shown when the delay is not the same on every detection."
    )
    lines.extend([
        "",
        "| Period | Pattern | Added kW | Placed | Crossed | Immediate | Continuous20 | Continuous30 | 20of30 |",
        "|---|---|---:|---:|---:|---|---|---|---|",
    ])
    if not summary.empty:
        for period, _, _ in PERIODS:
            for pattern, _, _ in FIXED_PATTERNS:
                for delta in DELTAS_KW:
                    block = summary[(summary.period == period) & (summary.pattern == pattern) & (summary.magnitude_kw == delta)]
                    if block.empty:
                        continue
                    cells = []
                    for policy in POLICIES:
                        row = block[block.policy == policy].iloc[0]
                        delay = _delay_text(row)
                        text = f"{int(row.detected)}/{int(row.placed)} ({_pct(row.detection_rate)})"
                        if delay:
                            text += f", delay {delay} min"
                        if int(row.miss_despite_crossing):
                            text += f"; {int(row.miss_despite_crossing)} crossed but missed"
                        cells.append(text)
                    head = block.iloc[0]
                    lines.append(
                        f"| {period} | {pattern} | {delta:.0f} | {int(head.placed)} | "
                        f"{int(head.crossed)} ({_pct(head.crossed_rate)}) | " + " | ".join(cells) + " |"
                    )
    lines.extend(["", "## Whether a larger increase crosses and alerts more often", ""])
    lines.extend(magnitude_findings(summary))
    lines.extend(["", "## Short and intermittent changes", ""])
    lines.extend(shape_findings(summary))
    lines.extend(["", "## Development and validation", ""])
    lines.extend(period_findings(summary))
    lines.extend(["", "## Expected load", ""])
    lines.extend(load_findings(events))
    lines.extend([
        "",
        "## What this does not support",
        "",
        "The rates describe these added shapes on quiet, fully observed windows. They do not estimate how often a real fault has this size or duration, and they do not use October-December. Holidays, weather, occupancy and operating state are still outside the baseline. The unchanged windows produced no alert, which checks that these hosts were inside the band before the addition. It is not an operational false-alert rate.",
        "",
        "## Reproduction",
        "",
        "```",
        'py fixed_magnitude_injection_tests.py "2019Floor3.csv"',
        "```",
        "",
        "Outputs land in fixed_magnitude_results/. The threshold-crossing results stay in controlled_injection_results/.",
        "",
    ])
    dest.joinpath("FIXED_MAGNITUDE_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def magnitude_findings(summary: pd.DataFrame) -> list[str]:
    if summary.empty:
        return ["No paired windows were placed."]
    lines = []
    crossing_up = True
    alert_up = True
    details = []
    for (period, pattern, policy), group in summary.groupby(["period", "pattern", "policy"], sort=False):
        ordered = group.set_index("magnitude_kw").loc[list(DELTAS_KW)]
        cross = ordered.crossed_rate.tolist()
        alert = ordered.detection_rate.tolist()
        if cross != sorted(cross):
            crossing_up = False
            details.append(f"{period} {pattern} crossing rates {[round(item, 3) for item in cross]}")
        if alert != sorted(alert):
            alert_up = False
            details.append(f"{period} {pattern} {policy} detection rates {[round(item, 3) for item in alert]}")
    if crossing_up:
        lines.append("On the paired windows, the share with at least one threshold crossing rose or stayed the same as the added power went from +1 to +5 to +10 kW, for every pattern in both periods.")
    else:
        lines.append("Crossing rate did not rise with magnitude in every pattern and period.")
    if alert_up:
        lines.append("Alert detection for each policy also rose or stayed the same across those three magnitudes. A rate that stays at zero is a policy that misses the shape even after the larger increase.")
    else:
        lines.append("Alert detection did not rise with magnitude for every policy and pattern.")
    lines.extend(details)
    # Give the pooled immediate / crossing picture without hiding zeros.
    immediate = summary[summary.policy == "immediate"]
    bits = []
    for delta in DELTAS_KW:
        part = immediate[immediate.magnitude_kw == delta]
        bits.append(f"+{delta:.0f} kW crossed on {int(part.crossed.sum())} of {int(part.placed.sum())} pattern-windows ({part.crossed.sum() / part.placed.sum():.0%})")
    lines.append("Pooled across patterns and both periods, " + "; ".join(bits) + ".")
    return lines


def shape_findings(summary: pd.DataFrame) -> list[str]:
    if summary.empty:
        return ["No paired windows were placed."]
    lines = []
    for pattern in ("spike_1", "spike_5", "two_bursts"):
        part = summary[summary.pattern == pattern]
        for policy in ("continuous20", "continuous30", "20of30"):
            detected = int(part.loc[part.policy == policy, "detected"].sum())
            placed = int(part.loc[part.policy == policy, "placed"].sum())
            despite = int(part.loc[part.policy == policy, "miss_despite_crossing"].sum())
            lines.append(f"{pattern}, {POLICY_LABELS[policy]}: {detected} alerts out of {placed} windows, of which {despite} had at least one threshold crossing and still no alert.")
    return lines


def period_findings(summary: pd.DataFrame) -> list[str]:
    if summary.empty:
        return ["No paired windows were placed."]
    gaps = []
    for (pattern, delta, policy), group in summary.groupby(["pattern", "magnitude_kw", "policy"]):
        rates = group.set_index("period").detection_rate
        if "development" not in rates.index or "validation" not in rates.index:
            gaps.append(f"{pattern} +{delta:.0f} kW {policy} is missing a period")
            continue
        gap = float(rates["validation"] - rates["development"])
        if abs(gap) >= 0.05:
            gaps.append(
                f"{pattern}, +{delta:.0f} kW, {POLICY_LABELS[policy]}: development {_pct(rates['development'])}, validation {_pct(rates['validation'])}"
            )
    if not gaps:
        return ["Development and validation detection rates agreed within 5 percentage points for every pattern, magnitude and policy."]
    return ["Detection rates differed by at least 5 percentage points for:"] + [f"- {item}" for item in gaps]


def load_findings(events: pd.DataFrame) -> list[str]:
    if events.empty:
        return ["No paired windows were placed."]
    work = events.copy()
    work["load"] = np.where(work.slot_expected_kw >= 1, "expected at least 1 kW", "expected below 1 kW")
    lines = [
        "The paired sample mixes quiet hours whose expected power is near zero with hours whose expected power is at least 1 kW. Near zero, the threshold is often the 0.5 kW floor, so +1 kW already crosses. The split below uses the hour's median expected power.",
        "",
        "| Expected load | Added kW | Placed pattern-windows | Crossed | Immediate alerts |",
        "|---|---:|---:|---:|---:|",
    ]
    anchor = work[work.pattern == "continuous_30"]
    for load in ("expected below 1 kW", "expected at least 1 kW"):
        for delta in DELTAS_KW:
            part = anchor[(anchor.load == load) & (anchor.magnitude_kw == delta)]
            if part.empty:
                continue
            lines.append(
                f"| {load} | {delta:.0f} | {len(part)} | {int(part.any_crossing.sum())} ({part.any_crossing.mean():.0%}) | "
                f"{int(part.immediate_detected.sum())} ({part.immediate_detected.mean():.0%}) |"
            )
    lines.append("")
    lines.append("The continuous-30 row is one window per placed host. Spike and burst rows sit on their own hosts and are in the event file.")
    return lines


def plot_rates(summary: pd.DataFrame, dest: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if summary.empty:
        return
    patterns = [name for name, _, _ in FIXED_PATTERNS]
    periods = [name for name, _, _ in PERIODS]
    fig, axes = plt.subplots(len(POLICIES), len(periods), figsize=(10, 11), sharex=True, sharey=True)
    for row, policy in enumerate(POLICIES):
        for col, period in enumerate(periods):
            ax = axes[row, col]
            grid = np.full((len(patterns), len(DELTAS_KW)), np.nan)
            part = summary[(summary.policy == policy) & (summary.period == period)]
            for i, pattern in enumerate(patterns):
                for j, delta in enumerate(DELTAS_KW):
                    hit = part[(part.pattern == pattern) & (part.magnitude_kw == delta)]
                    if hit.empty or int(hit.placed.iloc[0]) == 0:
                        continue
                    grid[i, j] = float(hit.detection_rate.iloc[0])
                    ax.text(j, i, f"{grid[i, j]:.0%}", ha="center", va="center", fontsize=8, color="#1f2937")
            ax.imshow(np.ma.masked_invalid(grid), aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
            ax.set_xticks(range(len(DELTAS_KW)), [f"+{delta:.0f} kW" for delta in DELTAS_KW])
            ax.set_yticks(range(len(patterns)), patterns)
            ax.set_title(f"{POLICY_LABELS[policy]} / {period}")
    fig.suptitle("Share of paired windows that alerted", fontsize=12)
    fig.tight_layout()
    fig.savefig(dest / "fixed_magnitude_detection.png", dpi=150)
    plt.close(fig)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", default="2019Floor3.csv")
    parser.add_argument("--out", default="fixed_magnitude_results")
    parser.add_argument("--cap", type=int, default=PLACEMENT_CAP)
    args = parser.parse_args()
    logic_check()
    print("Fixed-magnitude logic check passed.", flush=True)
    csv_path = Path(args.csv)
    digest_before = file_sha256(csv_path)
    index, cols, data = load_power(csv_path)
    days = pd.date_range("2019-04-01", "2019-12-31", freq="D")
    bounds = period_index_bounds(index)
    dest = Path(args.out)
    if csv_path.resolve().parent == dest.resolve():
        raise SystemExit("Use a separate output folder from the input CSV.")
    dest.mkdir(parents=True, exist_ok=True)
    always = np.ones(len(index), dtype=bool)
    exclusion_rows = []
    event_rows = []
    for unit in cols:
        print("Processing", unit, flush=True)
        series = prepare_unit(data[unit].to_numpy(), days)
        actual = series["actual"]
        for period, (period_start, period_end) in bounds.items():
            for pattern, family, _blocks in FIXED_PATTERNS:
                mask = PATTERN_MASKS[pattern]
                quiet = candidate_onsets(series["quiet"], always, mask, period_start, period_end)
                feasible = {}
                excluded_above = {}
                excluded_below = {}
                for delta in DELTAS_KW:
                    updated = actual + delta
                    in_range = onset_holds(quiet, power_feasible(actual, delta), mask)
                    stays_nonnegative = onset_holds(quiet, np.isfinite(actual) & (updated >= 0), mask)
                    feasible[delta] = quiet[in_range]
                    excluded_below[delta] = int((~stays_nonnegative).sum())
                    # Remaining infeasible starts are those that would exceed 100 kW.
                    excluded_above[delta] = int((~in_range).sum() - excluded_below[delta])
                chosen = select_onsets(
                    feasible[PAIRED_DELTA_KW],
                    index,
                    series["slot_expected"][feasible[PAIRED_DELTA_KW] + 59] >= 1 if len(feasible[PAIRED_DELTA_KW]) else np.zeros(0, dtype=bool),
                    args.cap,
                )
                for delta in DELTAS_KW:
                    exclusion_rows.append({
                        "unit": unit,
                        "period": period,
                        "pattern": pattern,
                        "magnitude_kw": delta,
                        "quiet_onsets": int(len(quiet)),
                        "feasible_onsets": int(len(feasible[delta])),
                        "excluded_above_100": int(excluded_above[delta] - excluded_below[delta]),
                        "excluded_below_0": int(excluded_below[delta]),
                        "placed": int(len(chosen)),
                    })
                for onset in chosen:
                    if not (period_start <= int(onset) < period_end):
                        raise AssertionError("Placement left the development or validation period.")
                    stamp = index[int(onset)]
                    if stamp < pd.Timestamp("2019-05-01") or stamp >= pd.Timestamp("2019-10-01"):
                        raise AssertionError("Injection onset is outside May-September.")
                    for delta in DELTAS_KW:
                        result = evaluate_increase(series, int(onset), mask, delta)
                        row = {
                            "unit": unit,
                            "period": period,
                            "family": family,
                            "pattern": pattern,
                            "magnitude_kw": delta,
                            "onset": stamp,
                            "hour": int(stamp.hour),
                            "n_injected_minutes": result["n_injected_minutes"],
                            "n_crossing_minutes": result["n_crossing_minutes"],
                            "any_crossing": result["any_crossing"],
                            "first_crossing_offset_min": result["first_crossing_offset_min"],
                            "median_observed_kw": result["median_observed_kw"],
                            "median_expected_kw": result["median_expected_kw"],
                            "median_threshold_kw": result["median_threshold_kw"],
                            "median_injected_kw": result["median_injected_kw"],
                            "slot_expected_kw": result["slot_expected_kw"],
                        }
                        for policy in POLICIES:
                            delay = result["delays"][policy]
                            row[f"{policy}_detected"] = delay is not None
                            row[f"{policy}_delay_min"] = np.nan if delay is None else delay
                        event_rows.append(row)
    exclusions = pd.DataFrame(exclusion_rows)
    events = pd.DataFrame(event_rows)
    if not events.empty:
        events["onset"] = pd.to_datetime(events["onset"])
        sets = [set(map(tuple, events.loc[events.magnitude_kw == delta, ["unit", "period", "pattern", "onset"]].to_numpy()))
                for delta in DELTAS_KW]
        if not all(item == sets[0] for item in sets):
            raise AssertionError("Magnitudes were not compared on the same windows.")
        if events.onset.dt.month.isin([1, 2, 3, 10, 11, 12]).any():
            raise AssertionError("An injection was placed outside May-September.")
    summary = summarise(events)
    assert_summary_matches_events(summary, events)
    exclusions.to_csv(dest / "exclusions.csv", index=False)
    events.to_csv(dest / "events.csv", index=False)
    summary.to_csv(dest / "summary.csv", index=False)
    plot_rates(summary, dest)
    write_report(dest, summary, exclusions, events)
    digest_after = file_sha256(csv_path)
    if digest_before != digest_after:
        raise AssertionError("The original CSV changed during the run.")
    manifest = {
        "deltas_kw": list(DELTAS_KW),
        "paired_on_delta_kw": PAIRED_DELTA_KW,
        "periods": [name for name, _, _ in PERIODS],
        "october_to_december_used": False,
        "injection_relative_to": "original_observed_power",
        "events": int(len(events)),
        "csv_sha256": digest_after,
    }
    (dest / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("\nSaved", dest.resolve())
    print("CSV unchanged:", digest_before == digest_after)
    if summary.empty:
        print("No paired windows.")
        return
    view = summary.pivot_table(index=["period", "pattern", "magnitude_kw"], columns="policy",
                               values="detection_rate", aggfunc="first")
    print(view.to_string())


if __name__ == "__main__":
    main()
