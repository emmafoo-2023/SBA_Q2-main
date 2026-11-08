"""Controlled detection tests for the four Floor 3 alert policies.

Adds known continuous and intermittent deviations to quiet, fully observed
host windows in May-June (development) and July-September (validation).
October-December is not used. The original CSV is not modified.

The historical baseline and threshold are computed once from the unmodified
series, using the same rules as compare_floor3_alerts_v3.py. Injected minutes
do not enter the baseline. Each scheduled abnormal minute is set just far
enough past the local threshold to count as abnormal under that rule
(threshold + 0.1 kW). Off minutes inside a pattern are left unchanged.

Detection uses the same policy triggers as the comparison, including the
shared fully observed 30-minute window. Delay is the number of minutes from
the first injected abnormal timestamp to the first alert timestamp.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_floor3_alerts_v3 import policies, runs  # noqa: E402

WINDOW_DAYS = 28
SIGMA = 3
MIN_DEVIATION_KW = 0.5
MARGIN_KW = 0.1
PRE_MINUTES = 30
SLOT_MINUTES = 60
POST_MINUTES = 30
HOST_MINUTES = PRE_MINUTES + SLOT_MINUTES + POST_MINUTES  # 120
# Cap per unit, period, direction and pattern. Windows are not independent:
# nearby days share baseline history. The cap spreads placement; it is not a sample size for a confidence interval.
PLACEMENT_CAP = 36
SEPARATION_MINUTES = HOST_MINUTES

PERIODS = (
    ("development", "2019-05-01", "2019-07-01"),
    ("validation", "2019-07-01", "2019-10-01"),
)
POLICIES = ("immediate", "continuous20", "continuous30", "20of30")
POLICY_LABELS = {
    "immediate": "Immediate",
    "continuous20": "Continuous20",
    "continuous30": "Continuous30",
    "20of30": "20of30",
}

# (state, minutes) blocks. Every pattern starts with abnormal minutes and fits in the 60-minute slot.
# Gaps are at most 10 minutes, so the comparison's 15-minute case merge keeps each injection as one case.
PATTERNS = (
    ("continuous_10", "continuous", (("on", 10),)),
    ("continuous_20", "continuous", (("on", 20),)),
    ("continuous_25", "continuous", (("on", 25),)),
    ("continuous_30", "continuous", (("on", 30),)),
    ("continuous_60", "continuous", (("on", 60),)),
    ("spike_1", "spike", (("on", 1),)),
    ("spike_5", "spike", (("on", 5),)),
    ("one_minute_gap", "intermittent", (("on", 19), ("off", 1), ("on", 19))),
    ("two_bursts", "intermittent", (("on", 10), ("off", 5), ("on", 10))),
    ("duty_2on_1off", "intermittent", (("on", 2), ("off", 1)) * 10),
    ("pulses_3on_3off", "intermittent", (("on", 3), ("off", 3)) * 10),
    ("sparse_5on_10off", "intermittent", (("on", 5), ("off", 10)) * 4),
)

# Delays, in minutes after the onset timestamp, when the host is already fully observed and quiet.
# None means the policy does not alert. These are checked against both implementations before any data are read.
EXPECTED_DELAY = {
    "continuous_10": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": None},
    "continuous_20": {"immediate": 0, "continuous20": 19, "continuous30": None, "20of30": 19},
    "continuous_25": {"immediate": 0, "continuous20": 19, "continuous30": None, "20of30": 19},
    "continuous_30": {"immediate": 0, "continuous20": 19, "continuous30": 29, "20of30": 19},
    "continuous_60": {"immediate": 0, "continuous20": 19, "continuous30": 29, "20of30": 19},
    "spike_1": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": None},
    "spike_5": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": None},
    "one_minute_gap": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": 20},
    "two_bursts": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": 24},
    "duty_2on_1off": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": 28},
    "pulses_3on_3off": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": None},
    "sparse_5on_10off": {"immediate": 0, "continuous20": None, "continuous30": None, "20of30": None},
}


def expand_pattern(blocks) -> np.ndarray:
    parts = [np.full(n, state == "on", dtype=bool) for state, n in blocks]
    mask = np.concatenate(parts) if parts else np.zeros(0, dtype=bool)
    if len(mask) == 0 or len(mask) > SLOT_MINUTES or not mask[0]:
        raise ValueError(f"Pattern must start with an abnormal minute and fit in {SLOT_MINUTES} minutes.")
    return mask


PATTERN_MASKS = {name: expand_pattern(blocks) for name, _family, blocks in PATTERNS}
PATTERN_FAMILY = {name: family for name, family, _blocks in PATTERNS}


def pattern_features(mask: np.ndarray) -> dict:
    lengths = [e - s for s, e in runs(mask)]
    # Maximum abnormal minutes inside any 30-minute window of the isolated pattern, with quiet minutes outside it.
    padded = np.concatenate([np.zeros(29, dtype=int), mask.astype(int), np.zeros(29, dtype=int)])
    window = np.convolve(padded, np.ones(30, dtype=int), mode="valid")
    return {
        "span_minutes": int(len(mask)),
        "abnormal_minutes": int(mask.sum()),
        "longest_abnormal_run": int(max(lengths, default=0)),
        "max_abnormal_in_30": int(window.max() if len(window) else 0),
        "internal_gap_max": int(max((s2 - e1 for (_, e1), (s2, _) in zip(runs(mask), list(runs(mask))[1:])), default=0)),
    }


def study_triggers(flag, valid) -> dict[str, np.ndarray]:
    """Policy triggers as used in the comparison, on the shared 30-minute valid window."""
    definitions = policies(np.asarray(flag, dtype=bool), np.asarray(valid, dtype=bool))
    common = np.asarray(definitions["continuous30"][1], dtype=bool)
    return {name: np.asarray(trigger, dtype=bool) & common for name, (trigger, _eligible) in definitions.items()}


def window_sum(prefix: np.ndarray, i: int, width: int) -> int:
    if i - width + 1 < 0:
        return -1
    before = prefix[i - width] if i >= width else 0
    return int(prefix[i] - before)


def independent_triggers(flag, valid) -> dict[str, np.ndarray]:
    """Separate implementation of the same four rules, used only as a check."""
    mask = np.asarray(flag, dtype=bool)
    ok = np.asarray(valid, dtype=bool)
    n = len(mask)
    prefix_m = np.cumsum(mask.astype(np.int32))
    prefix_v = np.cumsum(ok.astype(np.int32))
    out = {name: np.zeros(n, dtype=bool) for name in POLICIES}
    for i in range(n):
        if window_sum(prefix_v, i, 30) != 30:
            continue
        if mask[i]:
            out["immediate"][i] = True
        if window_sum(prefix_m, i, 20) == 20 and window_sum(prefix_v, i, 20) == 20:
            out["continuous20"][i] = True
        if window_sum(prefix_m, i, 30) == 30:
            out["continuous30"][i] = True
        if window_sum(prefix_m, i, 30) >= 20:
            out["20of30"][i] = True
    return out


def first_delay(trigger: np.ndarray, onset: int, search_end: int):
    hits = np.flatnonzero(trigger[onset:search_end])
    if len(hits) == 0:
        return None
    return int(hits[0])


def alerts_via_case_attribution(flag, trigger, valid) -> list[int]:
    """First alert per merged case, using the comparison script's attribution."""
    common_cases = []
    for start, end in runs(np.asarray(flag, dtype=bool)):
        if common_cases and start - common_cases[-1][1] <= 15 and np.asarray(valid[common_cases[-1][1]:start]).all():
            common_cases[-1][1] = end
        else:
            common_cases.append([start, end])
    alerts = []
    n = len(flag)
    trigger = np.asarray(trigger, dtype=bool)
    for j, (start, end) in enumerate(common_cases):
        next_start = common_cases[j + 1][0] if j + 1 < len(common_cases) else n
        limit = min(end + 29, next_start, n)
        hits = np.flatnonzero(trigger[start:limit])
        if len(hits):
            alerts.append(start + int(hits[0]))
    return alerts


def ideal_slice(mask: np.ndarray):
    """Quiet, fully valid host. Onset is index PRE_MINUTES. Values make the on-mask the high-flag mask."""
    n = HOST_MINUTES
    expected = np.full(n, 5.0)
    threshold = np.full(n, 1.0)
    valid = np.ones(n, dtype=bool)
    actual = expected.copy()
    injected = actual.copy()
    on = np.zeros(n, dtype=bool)
    on[PRE_MINUTES:PRE_MINUTES + len(mask)] = mask
    injected[on] = expected[on] + threshold[on] + MARGIN_KW
    flag = valid & ((injected - expected) > threshold)
    return flag, valid, on


def self_check():
    rng = np.random.default_rng(7)
    for _ in range(30):
        n = 240
        flag = rng.random(n) < 0.2
        valid = rng.random(n) < 0.95
        a = study_triggers(flag, valid)
        b = independent_triggers(flag, valid)
        for name in POLICIES:
            if not np.array_equal(a[name], b[name]):
                raise AssertionError(f"Policy implementations disagree on {name}.")

    # Without a valid 30-minute history, a 20-minute run does not alert at its first minute.
    flag = np.zeros(40, dtype=bool)
    flag[:20] = True
    valid = np.ones(40, dtype=bool)
    early = study_triggers(flag, valid)
    if early["immediate"][:20].any() or first_delay(early["20of30"], 0, 40) != 29:
        raise AssertionError("Eligibility timing at the start of a series is not what the comparison uses.")

    catalogue_rows = []
    for name, family, _blocks in PATTERNS:
        mask = PATTERN_MASKS[name]
        features = pattern_features(mask)
        if features["internal_gap_max"] > 15:
            raise AssertionError(f"{name} has a gap above the 15-minute merge.")
        flag, valid, on = ideal_slice(mask)
        if not np.array_equal(flag, on):
            raise AssertionError(f"{name} did not reproduce its abnormal mask.")
        triggers = study_triggers(flag, valid)
        independent = independent_triggers(flag, valid)
        search_end = PRE_MINUTES + len(mask) + 29
        row = {"pattern": name, "family": family, **features}
        for policy in POLICIES:
            if not np.array_equal(triggers[policy], independent[policy]):
                raise AssertionError(f"{name} {policy} implementations disagree.")
            delay = first_delay(triggers[policy], PRE_MINUTES, search_end)
            delay = None if delay is None else delay
            expected = EXPECTED_DELAY[name][policy]
            if delay != expected:
                raise AssertionError(f"{name} {policy}: delay {delay} != expected {expected}.")
            attributed = alerts_via_case_attribution(flag, triggers[policy], valid)
            if expected is None:
                if attributed:
                    raise AssertionError(f"{name} {policy}: case attribution alerted unexpectedly.")
            elif attributed != [PRE_MINUTES + expected]:
                raise AssertionError(f"{name} {policy}: attribution {attributed} != first trigger.")
            row[f"{policy}_delay_min"] = expected if expected is not None else np.nan
            row[f"{policy}_detected"] = expected is not None
            if expected is None:
                row[f"{policy}_abnormal_minutes_by_alert"] = np.nan
            else:
                row[f"{policy}_abnormal_minutes_by_alert"] = int(mask[: expected + 1].sum())
        catalogue_rows.append(row)
    return pd.DataFrame(catalogue_rows)


def load_power(csv_path: Path) -> tuple[pd.DatetimeIndex, list[str], pd.DataFrame]:
    df = pd.read_csv(csv_path)
    dates = pd.to_datetime(df["Date"], errors="coerce")
    keep = dates.notna() & dates.eq(dates.dt.floor("min"))
    cols = [c for c in df.columns if "_AC" in c and "(kW)" in c]
    if not cols:
        raise SystemExit("No AC channels found. Use the original Floor 3 CSV.")
    data = df.loc[keep, cols].apply(pd.to_numeric, errors="coerce")
    data.index = pd.DatetimeIndex(dates[keep])
    data = data.where(data.ge(0) & data.le(100)).groupby(level=0).mean()
    index = pd.date_range("2019-04-01", "2019-12-31 23:59", freq="min")
    data = data.reindex(index)
    return index, cols, data


def baseline_grid(values: np.ndarray, days: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    grid = values.reshape(len(days), 1440)
    weekend = days.dayofweek >= 5
    mean = np.full(grid.shape, np.nan)
    sd = np.full(grid.shape, np.nan)
    for i in range(len(days)):
        previous = np.arange(max(0, i - WINDOW_DAYS), i)
        previous = previous[weekend[previous] == weekend[i]]
        if len(previous) == 0:
            continue
        history = grid[previous]
        count = np.isfinite(history).sum(axis=0)
        need = 3 if weekend[i] else 5
        enough = count >= need
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            minute_mean = np.nanmean(history, axis=0)
            minute_sd = np.nanstd(history, axis=0, ddof=1)
        mean[i, enough] = minute_mean[enough]
        sd[i, enough] = minute_sd[enough]
    return mean, sd


def audit_baseline(values: np.ndarray, days: pd.DatetimeIndex, fast_mean: np.ndarray, fast_sd: np.ndarray):
    """Check the vectorised baseline against the comparison script's day loop."""
    grid = values.reshape(len(days), 1440)
    weekend = days.dayofweek >= 5
    for i in (40, 120, 200):
        previous = np.arange(max(0, i - WINDOW_DAYS), i)
        previous = previous[weekend[previous] == weekend[i]]
        history = pd.DataFrame(grid[previous])
        enough = history.count().to_numpy() >= (3 if weekend[i] else 5)
        slow_mean = np.full(1440, np.nan)
        slow_sd = np.full(1440, np.nan)
        slow_mean[enough] = history.mean().to_numpy()[enough]
        slow_sd[enough] = history.std(ddof=1).to_numpy()[enough]
        if not np.allclose(slow_mean, fast_mean.reshape(len(days), 1440)[i], equal_nan=True):
            raise AssertionError(f"Baseline mean mismatch on day index {i}.")
        if not np.allclose(slow_sd, fast_sd.reshape(len(days), 1440)[i], equal_nan=True):
            raise AssertionError(f"Baseline SD mismatch on day index {i}.")


def rolling_count(mask: np.ndarray, width: int) -> np.ndarray:
    prefix = np.cumsum(mask.astype(np.int32))
    out = np.zeros(len(mask), dtype=np.int32)
    out[width - 1 :] = prefix[width - 1 :] - np.concatenate(([0], prefix[: -width]))
    return out


def period_index_bounds(index: pd.DatetimeIndex) -> dict[str, tuple[int, int]]:
    bounds = {}
    for name, start, end in PERIODS:
        start_i = int(index.searchsorted(pd.Timestamp(start)))
        end_i = int(index.searchsorted(pd.Timestamp(end)))
        bounds[name] = (start_i, end_i)
    return bounds


def candidate_onsets(quiet: np.ndarray, feasible: np.ndarray, on_mask: np.ndarray,
                     period_start: int, period_end: int) -> np.ndarray:
    """Onsets whose full host is quiet and inside the period, and whose on-minutes can accept the deviation."""
    host_end_count = rolling_count(quiet, HOST_MINUTES)
    ok = np.zeros(len(quiet), dtype=bool)
    # Host occupies [i - PRE, i - PRE + HOST). Its last minute is i + SLOT + POST - 1 = i + 89.
    last_offset = SLOT_MINUTES + POST_MINUTES - 1
    feas_ok = np.ones(len(quiet), dtype=bool)
    for relative in np.flatnonzero(on_mask):
        shifted = np.zeros(len(quiet), dtype=bool)
        shifted[: len(quiet) - relative] = feasible[relative:]
        feas_ok &= shifted
    earliest = max(period_start + PRE_MINUTES, PRE_MINUTES)
    # Onset i uses [i - 30, i + 90). Keep that half-open interval inside the period.
    latest = period_end - (SLOT_MINUTES + POST_MINUTES)
    if latest < earliest:
        return np.zeros(0, dtype=int)
    idx = np.arange(earliest, latest + 1)
    host_last = idx + last_offset
    inside = host_last < len(quiet)
    idx = idx[inside]
    host_last = host_last[inside]
    keep = (host_end_count[host_last] == HOST_MINUTES) & feas_ok[idx]
    return idx[keep]


def select_onsets(onsets: np.ndarray, index: pd.DatetimeIndex, operating: np.ndarray, cap: int) -> np.ndarray:
    """Spread placements across months, 6-hour bands and expected-load level. Non-overlapping hosts."""
    if len(onsets) == 0:
        return onsets
    stamps = index[onsets]
    groups: dict[tuple[int, int, bool], list[int]] = {}
    for position, stamp, is_operating in zip(onsets, stamps, operating):
        groups.setdefault((int(stamp.month), int(stamp.hour) // 6, bool(is_operating)), []).append(int(position))
    keys = sorted(groups)
    pointers = {key: 0 for key in keys}
    chosen: list[int] = []
    while len(chosen) < cap:
        progress = False
        for key in keys:
            pointer = pointers[key]
            while pointer < len(groups[key]):
                position = groups[key][pointer]
                pointer += 1
                if all(abs(position - earlier) >= SEPARATION_MINUTES for earlier in chosen):
                    chosen.append(position)
                    progress = True
                    break
            pointers[key] = pointer
            if len(chosen) >= cap:
                break
        if not progress:
            break
    return np.array(sorted(chosen), dtype=int)


def prepare_unit(values: np.ndarray, days: pd.DatetimeIndex):
    mean, sd = baseline_grid(values, days)
    audit_baseline(values, days, mean, sd)
    actual = values.astype(float)
    expected = mean.ravel()
    spread = sd.ravel()
    valid = np.isfinite(actual) & np.isfinite(expected) & np.isfinite(spread)
    threshold = np.maximum(SIGMA * spread, MIN_DEVIATION_KW)
    deviation = actual - expected
    high = valid & (deviation > threshold)
    low = valid & ((-deviation) > threshold)
    quiet = valid & ~high & ~low
    high_feasible = np.isfinite(expected) & np.isfinite(threshold) & ((expected + threshold + MARGIN_KW) <= 100)
    low_feasible = np.isfinite(expected) & np.isfinite(threshold) & ((expected - threshold - MARGIN_KW) >= 0)
    # Median expected power over the 60-minute slot, aligned to the slot's last minute.
    slot_expected = pd.Series(expected).rolling(SLOT_MINUTES, min_periods=SLOT_MINUTES).median().to_numpy()
    return {
        "actual": actual,
        "expected": expected,
        "threshold": threshold,
        "valid": valid,
        "quiet": quiet,
        "feasible": {"high": high_feasible, "low": low_feasible},
        "slot_expected": slot_expected,
    }


def evaluate_onset(series, onset: int, mask: np.ndarray, direction: str):
    start = onset - PRE_MINUTES
    stop = onset - PRE_MINUTES + HOST_MINUTES
    actual = series["actual"][start:stop].copy()
    expected = series["expected"][start:stop]
    threshold = series["threshold"][start:stop]
    valid = series["valid"][start:stop]
    if len(actual) != HOST_MINUTES or not valid.all() or not series["quiet"][start:stop].all():
        raise AssertionError("Selected host was not fully quiet and observed.")
    on = np.zeros(HOST_MINUTES, dtype=bool)
    on[PRE_MINUTES:PRE_MINUTES + len(mask)] = mask
    injected = actual.copy()
    if direction == "high":
        injected[on] = expected[on] + threshold[on] + MARGIN_KW
        crossed = (injected - expected) > threshold
    else:
        injected[on] = expected[on] - threshold[on] - MARGIN_KW
        crossed = (expected - injected) > threshold
    if np.any(injected[on] < 0) or np.any(injected[on] > 100) or not np.array_equal(crossed, on):
        raise AssertionError("Injection did not create the designed abnormal mask inside 0-100 kW.")
    # Off minutes, the pre-window and the post-window stay at the original power and stay inside the band.
    if not np.array_equal(injected[~on], actual[~on]):
        raise AssertionError("Injection changed a minute outside the designed pattern.")
    flag = crossed  # valid is all True in the host, and only on-minutes cross
    if flag[:PRE_MINUTES].any() or flag[PRE_MINUTES + len(mask):].any():
        raise AssertionError("Abnormal minutes appeared outside the designed pattern.")
    triggers = study_triggers(flag, valid)
    search_end = PRE_MINUTES + len(mask) + 29
    delays = {}
    for policy in POLICIES:
        delay = first_delay(triggers[policy], PRE_MINUTES, search_end)
        attributed = alerts_via_case_attribution(flag, triggers[policy], valid)
        if delay is None:
            if attributed:
                raise AssertionError("Case attribution found an alert the first-trigger rule missed.")
        elif attributed != [PRE_MINUTES + delay]:
            raise AssertionError("Case attribution and first-trigger delay disagree.")
        delays[policy] = delay
    on_threshold = threshold[on]
    return {
        "median_expected_kw": float(np.median(expected[on])),
        "median_threshold_kw": float(np.median(on_threshold)),
        "min_injected_excess_kw": float(MARGIN_KW),
        "median_injected_kw": float(np.median(injected[on])),
        "delays": delays,
    }


def negative_control(series, onset: int) -> bool:
    start = onset - PRE_MINUTES
    stop = start + HOST_MINUTES
    valid = series["valid"][start:stop]
    high = series["actual"][start:stop] - series["expected"][start:stop] > series["threshold"][start:stop]
    low = series["expected"][start:stop] - series["actual"][start:stop] > series["threshold"][start:stop]
    flagged = False
    for flag in (high, low):
        triggers = study_triggers(valid & flag, valid)
        for policy in POLICIES:
            if triggers[policy].any():
                flagged = True
    return flagged


def summarise(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if events.empty:
        return pd.DataFrame()
    group_cols = ["period", "direction", "family", "pattern"]
    for keys, group in events.groupby(group_cols, sort=False):
        for policy in POLICIES:
            detected = group[f"{policy}_detected"].astype(bool)
            delays = group.loc[detected, f"{policy}_delay_min"]
            rows.append({
                "period": keys[0],
                "direction": keys[1],
                "family": keys[2],
                "pattern": keys[3],
                "policy": policy,
                "placed": int(len(group)),
                "detected": int(detected.sum()),
                "detection_rate": float(detected.mean()) if len(group) else np.nan,
                "delay_min": float(delays.min()) if len(delays) else np.nan,
                "delay_median_min": float(delays.median()) if len(delays) else np.nan,
                "delay_max": float(delays.max()) if len(delays) else np.nan,
                "mismatches": int((~group[f"{policy}_matches_theory"]).sum()),
                "operating_placed": int(group["expected_at_least_1kw"].sum()),
                "operating_detection_rate": float(group.loc[group["expected_at_least_1kw"], f"{policy}_detected"].mean())
                if group["expected_at_least_1kw"].any() else np.nan,
            })
    return pd.DataFrame(rows)


def plot_delay_table(summary: pd.DataFrame, dest: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if summary.empty:
        return
    periods = [p for p, _, _ in PERIODS]
    directions = ["high", "low"]
    pattern_names = [name for name, _, _ in PATTERNS]
    fig, axes = plt.subplots(len(periods), len(directions), figsize=(11, 10.5), sharex=True, sharey=True)
    for row, period in enumerate(periods):
        for col, direction in enumerate(directions):
            ax = axes[row, col]
            grid = np.full((len(pattern_names), len(POLICIES)), np.nan)
            annot = [["" for _ in POLICIES] for _ in pattern_names]
            part = summary[(summary.period == period) & (summary.direction == direction)]
            for i, pattern in enumerate(pattern_names):
                for j, policy in enumerate(POLICIES):
                    hit = part[(part.pattern == pattern) & (part.policy == policy)]
                    if hit.empty or int(hit.placed.iloc[0]) == 0:
                        annot[i][j] = "n=0"
                        continue
                    rate = float(hit.detection_rate.iloc[0])
                    if rate == 0:
                        grid[i, j] = 0
                        annot[i][j] = "miss"
                    else:
                        delay = float(hit.delay_median_min.iloc[0])
                        grid[i, j] = delay
                        note = f"{delay:.0f}"
                        if rate < 1:
                            note = f"{rate:.0%}\n{delay:.0f}"
                        annot[i][j] = note
            shown = np.ma.masked_invalid(grid)
            ax.imshow(shown, aspect="auto", cmap="YlOrRd", vmin=0, vmax=30)
            ax.set_xticks(range(len(POLICIES)), [POLICY_LABELS[p] for p in POLICIES], rotation=30, ha="right")
            ax.set_yticks(range(len(pattern_names)), pattern_names, fontsize=8)
            for i in range(len(pattern_names)):
                for j in range(len(POLICIES)):
                    ax.text(j, i, annot[i][j], ha="center", va="center", fontsize=7, color="#1f2937")
            title = f"{period} / {direction}"
            ax.set_title(title)
    fig.suptitle("Minutes from injection onset to first alert (miss = not detected)", fontsize=12)
    fig.tight_layout()
    fig.savefig(dest / "detection_delay.png", dpi=150)
    plt.close(fig)


def plot_example(index, series, unit, onset, mask, direction, dest: Path, filename: str, title: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    start = onset - PRE_MINUTES
    stop = start + HOST_MINUTES
    expected = series["expected"][start:stop]
    threshold = series["threshold"][start:stop]
    actual = series["actual"][start:stop].copy()
    on = np.zeros(HOST_MINUTES, dtype=bool)
    on[PRE_MINUTES:PRE_MINUTES + len(mask)] = mask
    injected = actual.copy()
    if direction == "high":
        injected[on] = expected[on] + threshold[on] + MARGIN_KW
        flag = (injected - expected) > threshold
    else:
        injected[on] = expected[on] - threshold[on] - MARGIN_KW
        flag = (expected - injected) > threshold
    valid = series["valid"][start:stop]
    triggers = study_triggers(flag, valid)
    times = index[start:stop]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.fill_between(times, expected - threshold, expected + threshold, color="#cbd5e1", alpha=0.7,
                    label="Expected power +/- threshold")
    ax.plot(times, actual, color="#94a3b8", lw=1, label="Original power")
    ax.plot(times, injected, color="#0369a1", lw=1.2, label="Power with added deviation")
    ax.plot(times, expected, color="#c2410c", lw=1, label="Expected power")
    onset_time = index[onset]
    colors = {"immediate": "#0f766e", "continuous20": "#b45309", "continuous30": "#9f1239", "20of30": "#1d4ed8"}
    for policy in POLICIES:
        delay = first_delay(triggers[policy], PRE_MINUTES, PRE_MINUTES + len(mask) + 29)
        if delay is None:
            continue
        when = index[onset + delay]
        ax.axvline(when, color=colors[policy], lw=1, label=f"{POLICY_LABELS[policy]} alert (+{delay} min)")
    ax.axvline(onset_time, color="#111827", lw=1, ls="--", label="Injection onset")
    ax.set_title(title)
    ax.set_ylabel("Power (kW)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.legend(fontsize=7, loc="best")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(dest / filename, dpi=150)
    plt.close(fig)


def _delay_cell(value) -> str:
    return "miss" if pd.isna(value) else f"{int(value)} min"


def _size_phrase(frame: pd.DataFrame, column: str) -> str:
    if frame.empty:
        return "not available"
    low, mid, high = frame[column].quantile([0.25, 0.5, 0.75])
    return f"median {mid:.2f} kW (lower quartile {low:.2f}, upper quartile {high:.2f})"


def placement_lines(suitability: pd.DataFrame, events: pd.DataFrame) -> list[str]:
    if suitability.empty:
        return ["No placement table was produced."]
    lines = [
        "A feasible onset is a minute at which that pattern can start. The surrounding 120 minutes are fully observed and inside the threshold band, and every designed abnormal minute can cross the threshold while staying inside 0 to 100 kW. "
        "Minutes inside one quiet stretch are counted separately, so the feasible-onset count is not a count of separate events. "
        f"Placed windows do not overlap. They are spread across months, 6-hour bands, and whether the slot's median expected power is at least 1 kW, with at most {PLACEMENT_CAP} per unit, period, direction and pattern. "
        "Nearby days share baseline history. The placed count is not an independent sample size and is not treated as one.",
        "",
        "### High-power deviations",
        "",
    ]
    high = suitability[suitability.direction == "high"]
    anchor = high[high.pattern == "continuous_30"]
    same_hosts = False
    if not events.empty:
        high_events = events[events.direction == "high"]
        placed_sets = [
            set(map(tuple, high_events.loc[high_events.pattern == name, ["unit", "onset"]].to_numpy()))
            for name, _family, _blocks in PATTERNS
        ]
        same_hosts = bool(placed_sets) and all(item == placed_sets[0] for item in placed_sets)
    if same_hosts:
        lines.append(
            "Upward crossings stayed within 100 kW on every fully quiet host that was placed, and every high-power pattern was added to the same windows."
        )
    lines.extend([
        "",
        "| Period | Units with a window | Feasible start minutes | Of which expected load >= 1 kW | Placed windows | Placed with expected load >= 1 kW |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for period, group in anchor.groupby("period", sort=False):
        lines.append(
            f"| {period} | {int((group.placed > 0).sum())} | {int(group.feasible_onsets.sum())} | "
            f"{int(group.feasible_operating_onsets.sum())} | {int(group.placed.sum())} | {int(group.placed_operating.sum())} |"
        )
    if not events.empty:
        sample = events[(events.direction == "high") & (events.pattern == "continuous_30")]
        lines.extend([
            "",
            f"On those continuous-30 windows the expected power was {_size_phrase(sample, 'median_expected_kw')}, "
            f"the threshold was {_size_phrase(sample, 'median_threshold_kw')}, and the injected power was {_size_phrase(sample, 'median_injected_kw')}. "
            "The threshold floor is 0.5 kW, so a quiet hour whose baseline is near zero is crossed by setting power to 0.60 kW. That is a threshold crossing, not a large operating load.",
        ])
    missed = sorted(set(suitability.unit) - set(anchor.loc[anchor.placed_operating > 0, "unit"]))
    if missed:
        lines.append(
            "No placed high-power window had slot-median expected power of at least 1 kW for: " + ", ".join(missed) + "."
        )
    lines.extend(["", "### Low-power deviations", ""])
    low = suitability[suitability.direction == "low"]
    units_with = sorted(low.loc[low.placed > 0, "unit"].unique())
    units_without = sorted(set(low.unit) - set(units_with))
    if units_without:
        lines.append(
            "A low-power minute has to move to expected - threshold - 0.1 kW without going below zero, so the baseline must sit at least 0.1 kW above the threshold. "
            "No such quiet host existed for: " + ", ".join(units_without) + "."
        )
    if units_with:
        lines.append("Low-power patterns were placed on: " + ", ".join(units_with) + ".")
    lines.extend([
        "",
        "| Period | Pattern | Feasible start minutes | Placed windows | Placed with expected load >= 1 kW |",
        "|---|---|---:|---:|---:|",
    ])
    brief = (low.groupby(["period", "pattern"], sort=False)[["feasible_onsets", "placed", "placed_operating"]]
             .sum().reset_index())
    for _, row in brief.iterrows():
        lines.append(
            f"| {row['period']} | {row['pattern']} | {int(row['feasible_onsets'])} | {int(row['placed'])} | {int(row['placed_operating'])} |"
        )
    if not events.empty:
        sample = events[(events.direction == "low") & (events.pattern == "continuous_30")]
        if len(sample):
            lines.extend([
                "",
                f"On the continuous-30 low windows the expected power was {_size_phrase(sample, 'median_expected_kw')}, "
                f"the threshold was {_size_phrase(sample, 'median_threshold_kw')}, and the injected power was {_size_phrase(sample, 'median_injected_kw')}. "
                "The drop is exactly 0.1 kW past the local threshold. Where that threshold is wide, the kilowatt change is large even though the rule only requires a crossing.",
            ])
    return lines


def write_results_markdown(dest: Path, summary: pd.DataFrame, suitability: pd.DataFrame,
                           negatives: pd.DataFrame, catalogue: pd.DataFrame, events: pd.DataFrame):
    lines = [
        "# Controlled injection tests",
        "",
        "These tests measure whether the four fixed policies alert on specified patterns, and how many minutes after the pattern starts. They are not estimates of fault recall, false-alert rate, saved energy or maintenance benefit.",
        "",
        "## What was held fixed",
        "",
        "Baseline: preceding 28 calendar days, same minute of day, weekday with weekday and weekend with weekend, at least five weekday or three weekend values. Threshold: maximum of three historical standard deviations and 0.5 kW. Missing minutes were not filled. April supplies baseline history only. January-March and October-December were not used as injection periods. The baseline was fit to the original series. Injected values were not written back into it or into the CSV.",
        "",
        "A host window was used only when all 120 minutes were observed, baseline-backed and inside the threshold band: 30 minutes before the onset, a 60-minute slot, and 30 minutes after that slot. The opening 30 minutes make the shared fully observed window available at onset, which is how the four policies are compared for workload. Patterns were not added on top of minutes that were already abnormal.",
        "",
        f"Each designed abnormal minute was moved to expected power +/- (threshold + {MARGIN_KW:.1f} kW), staying within 0 to 100 kW. Other minutes, including the normal minutes inside an intermittent pattern, kept their original power. A larger crossing on the same minutes would produce the same alerts. All four policies read the abnormal/not-abnormal minute mask, not the size of the excess.",
        "",
        "## How an alert was scored",
        "",
        "Onset is the timestamp of the first injected abnormal minute. Delay is alert timestamp minus onset timestamp, in minutes. Immediate has delay 0 when it alerts on the onset minute: that is when the one-minute reading is treated as available. Continuous20 alerts on the 20th consecutive abnormal minute, which is delay 19. A policy that does not trigger during the pattern, or in the following 29 minutes, misses that pattern.",
        "",
        "Triggers are taken from the comparison script, including the requirement that the trailing 30 minutes are fully observed. The first alert also matches that script's case attribution. Internal gaps in these patterns are 1 to 10 minutes, so the 15-minute case merge keeps each injection as one case.",
        "",
        "## Catalogue, confirmed on the placed windows",
        "",
        "The delays below are properties of the rules. Two implementations agreed before any Floor 3 window was scored. On every window that could host a pattern, the measured detection and delay matched this table. `miss` means the pattern does not satisfy that rule.",
        "",
        "| Pattern | Family | Abnormal minutes | Longest run | Max in any 30 | Immediate | Continuous20 | Continuous30 | 20of30 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in catalogue.iterrows():
        lines.append(
            f"| {row['pattern']} | {row['family']} | {int(row['abnormal_minutes'])} | {int(row['longest_abnormal_run'])} | "
            f"{int(row['max_abnormal_in_30'])} | {_delay_cell(row['immediate_delay_min'])} | {_delay_cell(row['continuous20_delay_min'])} | "
            f"{_delay_cell(row['continuous30_delay_min'])} | {_delay_cell(row['20of30_delay_min'])} |"
        )
    lines.extend(["", "## Where the patterns could be added", ""])
    lines.extend(placement_lines(suitability, events))
    lines.extend(["", "## Agreement across periods and operating level", ""])
    if summary.empty:
        lines.append("No pattern could be placed.")
    else:
        conflict = False
        for _, group in summary.groupby(["direction", "pattern", "policy"]):
            if group.detection_rate.nunique(dropna=False) > 1 or group.delay_median_min.nunique(dropna=False) > 1:
                conflict = True
                break
        mismatch_events = int(summary.mismatches.sum())
        if conflict or mismatch_events:
            lines.append(
                f"Development and validation, or individual windows, did not all match. Mismatch count in the summary table: {mismatch_events}. See detection_delay_summary.csv."
            )
        else:
            lines.append(
                "Development and validation agreed for every pattern and policy that could be placed. Where the expected power on the abnormal minutes was at least 1 kW, detection and delay were unchanged. That 1 kW cut only says the baseline expected more than a small load. It is not a fault label."
            )
    lines.extend(["", "## Negative control", ""])
    if negatives.empty:
        lines.append("No negative-control windows were checked.")
    else:
        bad = int(negatives.false_trigger.sum())
        lines.append(
            f"The same hosts were scored with no deviation added. {bad} of {len(negatives)} hosts produced an alert. "
            "The hosts were selected because they sat inside the band, so this checks the placement filter. It is not an operational false-alert rate."
        )
    lines.extend([
        "",
        "## Reading the delays",
        "",
        "Immediate detects every pattern in the catalogue, on the onset minute, because each pattern begins with a threshold crossing inside an already valid 30-minute window.",
        "",
        "The 1-minute and 5-minute spikes are detected only by Immediate, at the onset minute.",
        "",
        "Continuous20 detects only the uninterrupted runs of at least 20 minutes (20, 25, 30 and 60). Its delay is 19 minutes. It misses both spikes, the 10-minute run and every intermittent pattern, including 19 abnormal minutes, one normal minute, then 19 abnormal minutes.",
        "",
        "Continuous30 detects only the uninterrupted runs of at least 30 minutes (30 and 60). Its delay is 29 minutes. A clean 25-minute run is a miss. Both spikes are misses.",
        "",
        "20of30 detects every catalogue pattern that puts at least 20 abnormal minutes inside some 30-minute window. On a continuous run its delay matches Continuous20 (19 minutes). With a one-minute gap the delay is 20 minutes. Two bursts of 10 separated by 5 normal minutes alert at 24 minutes. A 2-on/1-off duty cycle over 30 minutes alerts at 28 minutes. The 1-minute spike, the 5-minute spike, repeated 3-minute pulses, and 5-on/10-off cycles stay below 20 abnormal minutes in every 30-minute window, so 20of30 misses them and only Immediate alerts.",
        "",
        "## What this does not support",
        "",
        "The results do not choose a policy. They do not estimate how often a real fault has these shapes, and they do not use October-December. They do not test a deviation that stays inside the threshold: those minutes are not abnormal under the shared rule, so none of the four policies can alert on them. They do not test the first 29 minutes after a gap, because every host was fully observed before onset. A low-power injection requires expected power at least 0.1 kW above the threshold; a near-zero baseline cannot host one. Holidays, weather, occupancy and operating state are still not in the baseline.",
        "",
        "## Reproduction",
        "",
        "```",
        'py controlled_injection_tests.py "2019Floor3.csv"',
        "```",
        "",
        "Outputs land in controlled_injection_results/. The script stops if a placed window disagrees with the catalogue or with the comparison script's case attribution.",
        "",
    ])
    dest.joinpath("CONTROLLED_TEST_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", default="2019Floor3.csv")
    parser.add_argument("--out", default="controlled_injection_results")
    parser.add_argument("--cap", type=int, default=PLACEMENT_CAP)
    args = parser.parse_args()
    catalogue = self_check()
    print("Policy self-check passed.", flush=True)

    csv_path = Path(args.csv)
    index, cols, data = load_power(csv_path)
    days = pd.date_range("2019-04-01", "2019-12-31", freq="D")
    if len(index) != len(days) * 1440:
        raise AssertionError("Minute index does not match the April-December day grid.")
    bounds = period_index_bounds(index)
    dest = Path(args.out)
    if csv_path.resolve().parent == dest.resolve():
        raise SystemExit("Use a separate output folder from the input CSV.")
    dest.mkdir(parents=True, exist_ok=True)

    suitability_rows = []
    event_rows = []
    negative_rows = []
    checked_negative = set()
    prepared = {}

    for unit in cols:
        print("Processing", unit, flush=True)
        series = prepare_unit(data[unit].to_numpy(), days)
        prepared[unit] = series
        for period, (period_start, period_end) in bounds.items():
            for direction in ("high", "low"):
                for pattern, family, _blocks in PATTERNS:
                    mask = PATTERN_MASKS[pattern]
                    onsets = candidate_onsets(
                        series["quiet"], series["feasible"][direction], mask, period_start, period_end
                    )
                    if len(onsets):
                        operating = series["slot_expected"][onsets + SLOT_MINUTES - 1] >= 1
                    else:
                        operating = np.zeros(0, dtype=bool)
                    chosen = select_onsets(onsets, index, operating, args.cap)
                    chosen_operating = 0
                    if len(chosen):
                        operating_by_onset = dict(zip(onsets.tolist(), operating.tolist()))
                        chosen_operating = sum(bool(operating_by_onset[int(item)]) for item in chosen)
                    suitability_rows.append({
                        "unit": unit,
                        "period": period,
                        "direction": direction,
                        "pattern": pattern,
                        "family": family,
                        "feasible_onsets": int(len(onsets)),
                        "feasible_operating_onsets": int(operating.sum()) if len(operating) else 0,
                        "placed": int(len(chosen)),
                        "placed_operating": int(chosen_operating),
                    })
                    for onset in chosen:
                        key = (unit, period, direction, int(onset))
                        if key not in checked_negative:
                            false_trigger = negative_control(series, int(onset))
                            negative_rows.append({
                                "unit": unit, "period": period, "direction": direction,
                                "onset": index[int(onset)], "false_trigger": bool(false_trigger),
                            })
                            checked_negative.add(key)
                            if false_trigger:
                                raise AssertionError(f"Quiet host produced an alert: {unit} {index[int(onset)]}")
                        result = evaluate_onset(series, int(onset), mask, direction)
                        stamp = index[int(onset)]
                        row = {
                            "unit": unit,
                            "period": period,
                            "direction": direction,
                            "family": family,
                            "pattern": pattern,
                            "onset": stamp,
                            "hour": int(stamp.hour),
                            "weekend": bool(stamp.dayofweek >= 5),
                            "median_expected_kw": result["median_expected_kw"],
                            "median_threshold_kw": result["median_threshold_kw"],
                            "median_injected_kw": result["median_injected_kw"],
                            "expected_at_least_1kw": result["median_expected_kw"] >= 1,
                        }
                        for policy in POLICIES:
                            delay = result["delays"][policy]
                            expected = EXPECTED_DELAY[pattern][policy]
                            row[f"{policy}_detected"] = delay is not None
                            row[f"{policy}_delay_min"] = np.nan if delay is None else delay
                            row[f"{policy}_matches_theory"] = delay == expected
                            if delay != expected:
                                raise AssertionError(
                                    f"{unit} {stamp} {pattern} {direction} {policy}: delay {delay} != {expected}"
                                )
                        event_rows.append(row)

    suitability = pd.DataFrame(suitability_rows)
    events = pd.DataFrame(event_rows)
    negatives = pd.DataFrame(negative_rows)
    summary = summarise(events)
    catalogue.to_csv(dest / "pattern_catalogue.csv", index=False)
    suitability.to_csv(dest / "suitability.csv", index=False)
    events.to_csv(dest / "events.csv", index=False)
    negatives.to_csv(dest / "negative_control.csv", index=False)
    summary.to_csv(dest / "detection_delay_summary.csv", index=False)
    plot_delay_table(summary, dest)

    illustrated = []

    def pick_example(pattern, direction):
        part = events[(events.pattern == pattern) & (events.direction == direction) & (events.period == "validation")].copy()
        if part.empty:
            return None
        daytime = part[part.expected_at_least_1kw & part.hour.between(9, 16)]
        if len(daytime):
            part = daytime
        target = part.median_threshold_kw.median()
        part = part.assign(distance=(part.median_threshold_kw - target).abs()).sort_values(["distance", "onset"])
        return part.iloc[0]

    high_example = pick_example("continuous_30", "high") if len(events) else None
    low_example = pick_example("continuous_30", "low") if len(events) else None
    for example, pattern_name, filename, label in (
        (high_example, "continuous_30", "example_continuous_30.png", "continuous 30 min, high"),
        (high_example, "one_minute_gap", "example_one_minute_gap.png", "19 on, 1 off, 19 on, high"),
        (low_example, "continuous_30", "example_continuous_30_low.png", "continuous 30 min, low"),
    ):
        if example is None:
            continue
        onset = int(index.searchsorted(pd.Timestamp(example.onset)))
        plot_example(
            index, prepared[example.unit], example.unit, onset, PATTERN_MASKS[pattern_name],
            "low" if "low" in label else "high", dest, filename,
            f"{example.unit} | {pd.Timestamp(example.onset):%d %b %Y %H:%M} | {label} | "
            f"median threshold {example.median_threshold_kw:.2f} kW",
        )
        illustrated.append(filename)
    manifest = {
        "margin_kw": MARGIN_KW,
        "placement_cap_per_unit_period_direction_pattern": args.cap,
        "periods": [name for name, _, _ in PERIODS],
        "evaluation_period_used": False,
        "units": cols,
        "events": int(len(events)),
        "negative_controls": int(len(negatives)),
        "example_plots": illustrated,
    }
    (dest / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_results_markdown(dest, summary, suitability, negatives, catalogue, events)
    print("\nSaved", dest.resolve())
    if summary.empty:
        print("No suitable windows.")
        return
    view = summary.groupby(["direction", "pattern", "policy"], sort=False)[["placed", "detection_rate", "delay_median_min", "mismatches"]].mean()
    print(view.to_string())
    print("Mismatches:", int(summary.mismatches.sum()), "Negative-control alerts:", int(negatives.false_trigger.sum()) if len(negatives) else 0)


if __name__ == "__main__":
    main()
