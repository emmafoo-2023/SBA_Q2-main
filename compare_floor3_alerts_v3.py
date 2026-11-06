"""Floor 3 first-stage alert comparison. Requires pandas, numpy and matplotlib.
Run: py compare_floor3_alerts_v3.py "2019Floor3.csv"
Outputs workload/case tables, NOT fault recall or confirmed detection delay.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

WINDOW_DAYS = 28
SIGMA = 3
MIN_DEVIATION_KW = 0.5
# Starting settings, not industry requirements. Weekdays/weekends only;
# public holidays are not adjusted in this simple first version.


def runs(mask):
    d = np.diff(np.r_[False, mask, False].astype(int))
    return zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))


def policies(flag, valid):
    f = pd.Series(flag.astype(int))
    v = pd.Series(valid.astype(int))
    out = {'immediate': (flag, valid)}
    for minutes in (20, 30):
        enough = v.rolling(minutes, min_periods=minutes).sum().eq(minutes).to_numpy()
        out[f'continuous{minutes}'] = (
            f.rolling(minutes, min_periods=minutes).sum().eq(minutes).to_numpy() & enough,
            enough)
    enough = v.rolling(30, min_periods=30).sum().eq(30).to_numpy()
    out['20of30'] = (f.rolling(30, min_periods=30).sum().ge(20).to_numpy() & enough, enough)
    return out


def make_review(dest):
    """Stratified review sample, not a random prevalence/precision estimate."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    cases = pd.read_csv(dest/'cases.csv', parse_dates=['case_start', 'case_end_exclusive', 'alert_timestamp'])
    cases = cases[cases.period.isin(['development', 'validation'])]
    keys = ['unit', 'period', 'direction', 'case_start', 'case_end_exclusive']
    wide = cases.pivot_table(index=keys, columns='method', values='alert_timestamp', aggfunc='first').reset_index()
    for method in ['immediate', 'continuous20', 'continuous30', '20of30']:
        if method not in wide:
            wide[method] = pd.NaT
    cache = {}
    def baseline(unit):
        if unit not in cache:
            safe = unit.replace('(kW)', '').replace('/', '_')
            cache[unit] = pd.read_csv(dest/f'{safe}_baseline.csv.gz', parse_dates=['Date']).set_index('Date')
        return cache[unit]
    features = []
    for row in wide.to_dict('records'):
        d = baseline(row['unit']).loc[row['case_start']:row['case_end_exclusive']-pd.Timedelta(minutes=1)]
        deviation = d.observed_kw-d.expected_kw
        flag = ((deviation > d.threshold_kw) if row['direction']=='high' else (-deviation > d.threshold_kw)).fillna(False).to_numpy()
        lengths = [e-s for s,e in runs(flag)]
        row['span_minutes'] = len(d)
        row['abnormal_minutes'] = int(flag.sum())
        row['longest_abnormal_run'] = max(lengths, default=0)
        row['mean_observed_kw'] = d.observed_kw.mean()
        row['mean_expected_kw'] = d.expected_kw.mean()
        if pd.notna(row['20of30']) and pd.isna(row['continuous20']):
            group = 'interruption_tolerance_adds_case'
        elif pd.notna(row['continuous20']) and pd.isna(row['continuous30']):
            group = 'shorter_duration_adds_case'
        elif pd.notna(row['continuous30']):
            group = 'shared_sustained_case'
        else:
            group = 'immediate_only'
        row['review_group'] = group
        for method in ['immediate','continuous20','continuous30','20of30']:
            row[method+'_elapsed_min_from_case_start'] = ((row[method]-row['case_start']).total_seconds()/60
                                                        if pd.notna(row[method]) else np.nan)
        features.append(row)
    table = pd.DataFrame(features)
    table.to_csv(dest/'development_validation_case_comparison.csv', index=False)
    sample = []
    # Up to four per category: two from each period, fixed random seed.
    for group in ['interruption_tolerance_adds_case','shorter_duration_adds_case','shared_sustained_case','immediate_only']:
        for period in ['development','validation']:
            subset = table[table.review_group.eq(group) & table.period.eq(period)]
            sample.extend(subset.sample(n=min(2,len(subset)), random_state=42).to_dict('records'))
    # Four random daytime no-excursion windows, one per regularly used unit.
    # They are not assumed fault-free. Both high/low thresholds must be unexceeded.
    rng = np.random.default_rng(42)
    for unit in ['z1_AC4(kW)','z2_AC1(kW)','z4_AC1(kW)','z5_AC1(kW)']:
        if unit not in cases.unit.unique():
            continue
        d = baseline(unit)
        candidates = pd.date_range('2019-05-01 08:00', '2019-09-30 17:00', freq='h')
        candidates = candidates[(candidates.hour>=8) & (candidates.hour<=17)]
        for number in rng.permutation(len(candidates)):
            start = candidates[number]
            chunk = d.loc[start:start+pd.Timedelta(minutes=59)]
            if len(chunk)!=60:
                continue
            valid = chunk[['observed_kw','expected_kw','threshold_kw']].notna().all(axis=1)
            quiet = (chunk.observed_kw-chunk.expected_kw).abs().le(chunk.threshold_kw)
            if valid.all() and quiet.all():
                sample.append({'unit':unit,'period':'development' if start.month<=6 else 'validation',
                    'direction':'review_both','case_start':start,
                    'case_end_exclusive':start+pd.Timedelta(hours=1),
                    'review_group':'random_no_threshold_excursion'})
                break
    if not sample:
        print('No development/validation review samples available.')
        return
    # Randomise packet order; method/category information goes in a separate answer key.
    sample = pd.DataFrame(sample).sample(frac=1,random_state=42).reset_index(drop=True)
    sample.insert(0,'review_id',[f'R{i+1:02d}' for i in range(len(sample))])
    sample.to_csv(dest/'review_answer_key.csv',index=False)
    plot_dir = dest/'review_plots'
    plot_dir.mkdir(exist_ok=True)
    form = []
    for row in sample.to_dict('records'):
        start,end = row['case_start'], row['case_end_exclusive']
        d = baseline(row['unit']).loc[start-pd.Timedelta(minutes=45):end+pd.Timedelta(minutes=45)]
        fig,ax = plt.subplots(figsize=(10,4.2))
        ax.fill_between(d.index, d.expected_kw-d.threshold_kw, d.expected_kw+d.threshold_kw,
                        color='#cbd5e1',alpha=.6,label='Expected power +/- threshold')
        ax.plot(d.index,d.observed_kw,color='#0369a1',lw=1,label='Observed power')
        ax.plot(d.index,d.expected_kw,color='#c2410c',lw=1,label='Expected power')
        ax.axvspan(start,end,color='#fbbf24',alpha=.15,label='Review window')
        ax.set_title(f"{row['review_id']} | {row['unit']} | {start:%d %b %Y}")
        ax.set_ylabel('Power (kW)')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.legend(fontsize=8,loc='best')
        ax.grid(alpha=.2)
        fig.tight_layout()
        name = f"{row['review_id']}.png"
        fig.savefig(plot_dir/name,dpi=150)
        plt.close(fig)
        form.append({'review_id':row['review_id'],'unit':row['unit'],'period':row['period'],
            'window_start':start,'window_end_exclusive':end,'plot':'review_plots/'+name,
            'reviewer_1_rating':'','reviewer_1_reason':'','reviewer_2_rating':'',
            'reviewer_2_reason':'','agreed_rating':'','supporting_evidence_needed':''})
    pd.DataFrame(form).to_csv(dest/'review_form.csv',index=False)
    (dest/'REVIEW_INSTRUCTIONS.txt').write_text(
        'Review development/validation only; final evaluation is not part of this packet.\n'
        'Give reviewers the plots and review_form.csv BEFORE the answer key.\n'
        'Ratings: investigate / monitor / uncertain. These are judgements, not fault labels.\n'
        'Each reviewer independently records the visible pattern, magnitude, duration and recurrence evidence.\n'
        'Do not infer confirmed faults, occupancy, closure or avoidable energy from power alone.\n'
        'Check official holidays and legitimate schedule changes before interpreting low power.\n'
        'Expected power +/- threshold is a statistical comparison band, not a physical or comfort limit.\n'
        'Use longer histories and zone temperature when needed; this packet contains power only.\n'
        'All units in Zone 1 share zone-level temperature evidence, not unit-specific performance evidence.\n'
        'No-excursion windows are not assumed fault-free. Disagreement can reveal a weak baseline.\n'
        'The sample is stratified, small and enriched for disagreement: do not estimate population precision from it.\n'
        'Case boundaries use 15-minute grouping for comparison, not confirmed incident boundaries.\n'
        'Elapsed time from first power excursion is not confirmed-fault detection delay.\n'
        'Choose policy settings using development/validation; keep final evaluation separate.\n',encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv', nargs='?', default='2019Floor3.csv')
    p.add_argument('--out', default='floor3_alert_results_v3')
    args = p.parse_args()
    df = pd.read_csv(args.csv)
    dates = pd.to_datetime(df['Date'], errors='coerce')
    keep = dates.notna() & dates.eq(dates.dt.floor('min'))
    cols = [c for c in df if '_AC' in c and '(kW)' in c]
    if not cols:
        raise SystemExit('No AC channels found. Use the original Floor 3 CSV.')
    data = df.loc[keep, cols].apply(pd.to_numeric, errors='coerce')
    data.index = pd.DatetimeIndex(dates[keep])
    data = data.where(data.ge(0) & data.le(100)).groupby(level=0).mean()
    index = pd.date_range('2019-04-01', '2019-12-31 23:59', freq='min')
    data = data.reindex(index)  # no interpolation; January-March not used
    days = pd.date_range('2019-04-01', '2019-12-31', freq='D')
    weekend = days.dayofweek >= 5
    periods = [('development', '2019-05-01', '2019-06-30'),
               ('validation', '2019-07-01', '2019-09-30'),
               ('evaluation', '2019-10-01', '2019-12-31')]
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    if Path(args.csv).resolve().parent == dest.resolve():
        raise SystemExit('Use a separate output folder from your input CSV.')
    summaries, cases = [], []
    for unit in cols:
        print('Processing', unit, flush=True)
        grid = data[unit].to_numpy().reshape(len(days), 1440)
        mean = np.full_like(grid, np.nan)
        sd = np.full_like(grid, np.nan)
        for i in range(len(days)):
            previous = np.arange(max(0, i-WINDOW_DAYS), i)
            previous = previous[weekend[previous] == weekend[i]]
            if not len(previous):
                continue
            history = pd.DataFrame(grid[previous])
            enough = history.count().to_numpy() >= (3 if weekend[i] else 5)
            mean[i, enough] = history.mean().to_numpy()[enough]
            sd[i, enough] = history.std(ddof=1).to_numpy()[enough]
        actual, expected, spread = grid.ravel(), mean.ravel(), sd.ravel()
        valid = np.isfinite(actual) & np.isfinite(expected) & np.isfinite(spread)
        threshold = np.maximum(SIGMA * spread, MIN_DEVIATION_KW)
        details = pd.DataFrame({'Date': index, 'observed_kw': actual,
                                'expected_kw': expected, 'threshold_kw': threshold,
                                'baseline_available': valid})
        safe = unit.replace('(kW)', '').replace('/', '_')
        details.to_csv(dest / f'{safe}_baseline.csv.gz', index=False, compression='gzip')
        for direction, flag in [('high', valid & (actual-expected > threshold)),
                                ('low', valid & (expected-actual > threshold))]:
            # Define common case boundaries from raw abnormal runs, once per direction.
            # Merge gaps <=15 minutes only when observed/baselined throughout the gap.
            common_cases = []
            for s, e in runs(flag):
                if common_cases and s-common_cases[-1][1] <= 15 and valid[common_cases[-1][1]:s].all():
                    common_cases[-1][1] = e
                else:
                    common_cases.append([s, e])
            definitions = policies(flag, valid)
            # Compare workload on the SAME fully observed 30-minute windows.
            common_eligible = definitions['continuous30'][1]
            for method, (trigger, eligible) in definitions.items():
                trigger = trigger & common_eligible
                grouped = []
                for j, (s, e) in enumerate(common_cases):
                    # A rolling rule can first trigger just after the last abnormal minute.
                    # Attribute this to the most recent case, never a future case.
                    next_start = common_cases[j+1][0] if j+1 < len(common_cases) else len(flag)
                    limit = min(e+29, next_start, len(flag))
                    hits = np.flatnonzero(trigger[s:limit])
                    if len(hits):
                        first = s + int(hits[0])
                        grouped.append((s, e, first))
                eligible = common_eligible
                for period, start, end in periods:
                    mask = (index >= start) & (index < pd.Timestamp(end)+pd.Timedelta(days=1))
                    selected = [(s,e,t) for s,e,t in grouped if mask[s]]
                    weeks = int((eligible & mask).sum()) / (60*24*7)
                    summaries.append({'unit': unit, 'period': period, 'direction': direction,
                        'method': method, 'cases': len(selected),
                        'monitored_weeks': round(weeks, 3),
                        'cases_per_monitored_week': round(len(selected)/weeks, 2) if weeks else np.nan})
                    for s,e,t in selected:
                        cases.append({'unit': unit, 'period': period, 'direction': direction,
                                      'method': method, 'case_start': index[s],
                                      'case_end_exclusive': index[e-1]+pd.Timedelta(minutes=1),
                                      'alert_timestamp': index[t]})
    pd.DataFrame(summaries).to_csv(dest/'workload_summary.csv', index=False)
    pd.DataFrame(cases).to_csv(dest/'cases.csv', index=False)
    make_review(dest)
    print('\nSaved results in', dest)
    print('April: warm-up. May-June: development. July-September: validation. October-December: evaluation.')
    print('One-minute timestamps are treated as the times readings become available.')
    print('Shared case grouping: <=15-minute gaps with valid data; each method counts a case at most once.')
    print('Cases are assigned to the period of their common case start. All methods use common monitoring windows.')
    print('High and low deviations are separate. Neither is a confirmed fault.')
    print('These are fixed starting policies, not tuned winners. Workload alone cannot select the best method.')
    print('Recall and onset-to-alert delay require a shared reviewed/injected reference set, not included here.')


if __name__ == '__main__':
    main()
