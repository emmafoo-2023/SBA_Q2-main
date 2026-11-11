"""Step 3: compare Immediate, Continuous20, Continuous30 and 20of30 on development and validation.
Requires pandas, numpy and matplotlib.

Run from the repo folder (no other script needs to run first):
    py step3_policy_comparison.py

Inputs (all already in the repo; names and columns are the team's own):
  development_validation_case_comparison.csv
  development_validation_workload.csv
  review_answer_key.csv
  step3_inputs/reviewer1_ratings.csv
  controlled_injection_results/policy_summary.csv

Outputs (step3_results/):
  table1_cases_missed_delay.csv      per period and policy: cases, cases missed (vs Immediate) and delay,
                                     per monitored week
  table1b_cases_missed_delay_combined.csv   the same per policy, development and validation pooled
                                     (counts and delays added, divided by the total monitored weeks)
  table2_reviewer_alerts.csv
  table3_step2_threshold_crossing.csv
  table3b_step2_fixed_magnitude.csv
  table4_missed_severity.csv
  table4b_missed_severity_totals.csv  the same estimate totalled per period and policy
  table4c_missed_severity_combined.csv  the same estimate per policy, development and validation pooled
  chart_tradeoff.png, chart_missed_severity.png, STEP3_SUMMARY.md

Definitions used (agreed with the team member running step 3):
  cases missed          cases Immediate alerts on that the policy does not (Immediate alerts on every case)
  estimated missed cases worth investigating
                        sum over review_groups of (missed cases in the group x investigate share of the group)

Development (May-June) and validation (July-September) only; October-December is never read.
Cases are excursion cases, not confirmed faults. This step compares; it does not select a policy.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

POLICIES = ['immediate', 'continuous20', 'continuous30', '20of30']
LABEL = {'immediate': 'Immediate', 'continuous20': 'Continuous20',
         'continuous30': 'Continuous30', '20of30': '20of30'}
PERIODS = ['development', 'validation']
GROUPS = ['immediate_only', 'shorter_duration_adds_case', 'interruption_tolerance_adds_case',
          'shared_sustained_case']
COLOR = {'immediate': '#2a78d6', 'continuous20': '#eb6834', 'continuous30': '#1baf7a', '20of30': '#eda100'}
GROUP_COLOR = {'immediate_only': '#2a78d6', 'shorter_duration_adds_case': '#1baf7a',
               'interruption_tolerance_adds_case': '#eda100', 'shared_sustained_case': '#8a5cd0'}
INK, MUTED, GRID = '#1f1f1e', '#6b6a65', '#e4e3de'


def read_inputs(repo, ratings_path):
    cases = pd.read_csv(repo/'development_validation_case_comparison.csv')
    workload = pd.read_csv(repo/'development_validation_workload.csv')
    key = pd.read_csv(repo/'review_answer_key.csv')
    ratings = pd.read_csv(ratings_path)
    ctrl = pd.read_csv(repo/'controlled_injection_results'/'policy_summary.csv')
    for name, df in [('case table', cases), ('workload table', workload), ('answer key', key)]:
        bad = set(df.period.dropna()) - set(PERIODS)
        if bad:
            raise SystemExit(f'{name} contains periods other than development/validation: {bad}')
    if cases.immediate.isna().any():
        raise SystemExit('Some cases have no Immediate alert; "missed vs Immediate" would not be defined.')
    return cases, workload, key, ratings, ctrl


def monitored_weeks(workload):
    # monitored_weeks is per unit and period (identical across directions and policies); sum over units.
    w = workload.drop_duplicates(['unit', 'period']).groupby('period').monitored_weeks.sum()
    return w


def table1(cases, workload, weeks):
    rows = []
    for period in PERIODS:
        c = cases[cases.period == period]
        imm = len(c)
        wk = weeks[period]
        for p in POLICIES:
            alerted = c[p].notna()
            n = int(workload[(workload.period == period) & (workload.method == p)].cases.sum())
            if n != int(alerted.sum()):
                raise SystemExit(f'{period} {p}: workload table and case table disagree ({n} vs {int(alerted.sum())}).')
            missed = imm - n
            delay = c.loc[alerted, f'{p}_elapsed_min_from_case_start']
            rows.append({'period': period, 'policy': LABEL[p], 'monitored_weeks': round(wk, 1),
                         'cases': n, 'cases_per_monitored_week': round(n / wk, 2),
                         'cases_missed': missed, 'cases_missed_per_monitored_week': round(missed / wk, 2),
                         'cases_missed_%_of_immediate': round(missed / imm * 100, 1),
                         'average_delay_min': round(delay.mean(), 1),
                         'median_delay_min': round(delay.median(), 1),
                         'total_delay_min': int(delay.sum()),
                         'total_delay_min_per_monitored_week': round(delay.sum() / wk, 1)})
    return pd.DataFrame(rows)


def table1b(cases, weeks):
    """Table 1 with development and validation pooled: counts and delays added, divided by total weeks."""
    wk = weeks[PERIODS].sum()
    imm = len(cases)
    rows = []
    for p in POLICIES:
        alerted = cases[p].notna()
        n = int(alerted.sum())
        missed = imm - n
        delay = cases.loc[alerted, f'{p}_elapsed_min_from_case_start']
        rows.append({'policy': LABEL[p], 'monitored_weeks': round(wk, 1),
                     'cases': n, 'cases_per_monitored_week': round(n / wk, 2),
                     'cases_missed': missed, 'cases_missed_per_monitored_week': round(missed / wk, 2),
                     'cases_missed_%_of_immediate': round(missed / imm * 100, 1),
                     'average_delay_min': round(delay.mean(), 1),
                     'median_delay_min': round(delay.median(), 1),
                     'total_delay_min': int(delay.sum()),
                     'total_delay_min_per_monitored_week': round(delay.sum() / wk, 1)})
    return pd.DataFrame(rows)


def rated_key(key, ratings):
    k = key.merge(ratings[['review_id', 'reviewer_1_rating', 'reviewer_1_reason']], on='review_id', how='left')
    if k.reviewer_1_rating.isna().any():
        raise SystemExit('Some review plots have no rating in the ratings file.')
    return k


def table2(k):
    case_plots = k[k.review_group != 'random_no_threshold_excursion']
    controls = k[k.review_group == 'random_no_threshold_excursion']
    rows = []
    for p in POLICIES:
        a = case_plots[case_plots[p].notna()]
        inv = int((a.reviewer_1_rating == 'investigate').sum())
        mon = int((a.reviewer_1_rating == 'monitor').sum())
        unc = int((~a.reviewer_1_rating.isin(['investigate', 'monitor'])).sum())
        n = len(a)
        rows.append({'policy': LABEL[p], 'plots_alerted': n,
                     'rated_investigate': inv, 'rated_investigate_%': round(inv / n * 100, 1) if n else np.nan,
                     'rated_monitor': mon, 'rated_monitor_%': round(mon / n * 100, 1) if n else np.nan,
                     'rated_uncertain': unc,
                     'review_ids_alerted': ' '.join(a.review_id),
                     'control_windows_alerted': int(controls[p].notna().sum())})
    return pd.DataFrame(rows)


def table3(ctrl):
    thr = ctrl[ctrl.test == 'threshold_crossing']
    order = list(dict.fromkeys(thr.pattern))
    t = []
    for pat in order:
        row = {'pattern': pat}
        for p in POLICIES:
            r = thr[(thr.pattern == pat) & (thr.policy == p)].iloc[0]
            if r.detected == 'all':
                d = f'{int(r.delay_min)}' if r.delay_min == r.delay_max else f'{int(r.delay_min)}-{int(r.delay_max)}'
                row[LABEL[p]] = f'detected, {d} min'
            else:
                row[LABEL[p]] = 'not detected' if r.detected == 'none' else f'{r.detected} detected'
        t.append(row)
    total = {'pattern': 'patterns detected'}
    for p in POLICIES:
        total[LABEL[p]] = f"{int((thr[thr.policy == p].detected == 'all').sum())} of {len(order)}"
    t.append(total)
    fix = ctrl[ctrl.test == 'fixed_kw'][['pattern', 'size', 'windows', 'crossed', 'policy', 'detected',
                                         'delay_min', 'delay_max']].copy()
    fix['policy'] = fix.policy.map(LABEL)
    return pd.DataFrame(t), fix


def table4(cases, k, weeks):
    case_plots = k[k.review_group != 'random_no_threshold_excursion']
    share = case_plots.groupby('review_group').apply(
        lambda d: pd.Series({'plots': len(d), 'rated_investigate': int((d.reviewer_1_rating == 'investigate').sum())}),
        include_groups=False)
    share['investigate_share'] = share.rated_investigate / share.plots
    rows, totals = [], []
    for period in PERIODS:
        c = cases[cases.period == period]
        wk = weeks[period]
        for p in POLICIES[1:]:
            miss = c[c[p].isna()]
            est_total = 0.0
            for g in GROUPS:
                m = miss[miss.review_group == g]
                if not len(m):
                    continue
                s = share.loc[g]
                est = len(m) * s.investigate_share
                est_total += est
                rows.append({'period': period, 'policy': LABEL[p], 'review_group': g,
                             'cases_missed': len(m),
                             'cases_missed_per_monitored_week': round(len(m) / wk, 2),
                             'abnormal_minutes_median': m.abnormal_minutes.median(),
                             'abnormal_minutes_max': int(m.abnormal_minutes.max()),
                             'longest_abnormal_run_median': m.longest_abnormal_run.median(),
                             'longest_abnormal_run_max': int(m.longest_abnormal_run.max()),
                             'reviewer_plots_in_group': int(s.plots),
                             'reviewer_rated_investigate': int(s.rated_investigate),
                             'investigate_share': round(s.investigate_share, 2),
                             'estimated_missed_worth_investigating': round(est, 1)})
            totals.append({'period': period, 'policy': LABEL[p], 'cases_missed': len(miss),
                           'estimated_missed_worth_investigating': round(est_total, 1),
                           'estimated_missed_worth_investigating_per_monitored_week': round(est_total / wk, 2)})
    return pd.DataFrame(rows), pd.DataFrame(totals), share


def table4c(cases, share, weeks):
    """Missed-pattern severity with development and validation pooled."""
    wk = weeks[PERIODS].sum()
    rows = []
    for p in POLICIES[1:]:
        miss = cases[cases[p].isna()]
        row = {'policy': LABEL[p], 'cases_missed': len(miss)}
        est = 0.0
        groups = ['immediate_only', 'interruption_tolerance_adds_case', 'shorter_duration_adds_case']
        for g in groups:
            row[f'{g}_missed'] = int((miss.review_group == g).sum())
        for g in groups:
            part = row[f'{g}_missed'] * share.loc[g].investigate_share
            row[f'{g}_missed_x_investigate_share'] = round(part, 1)
            est += part
        row['estimated_missed_worth_investigating'] = round(est, 1)
        row['estimated_missed_worth_investigating_per_monitored_week'] = round(est / wk, 2)
        rows.append(row)
    return pd.DataFrame(rows)


def charts(t1, t4b, t1b, t4c, cases, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.dpi': 130, 'font.size': 9, 'axes.edgecolor': GRID,
                         'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                         'axes.titlecolor': INK, 'axes.grid': True, 'grid.color': GRID,
                         'grid.linewidth': 0.6, 'axes.spines.top': False,
                         'axes.spines.right': False, 'legend.frameon': False})
    # 1. Trade-off: cases per monitored week vs estimated missed cases worth investigating per monitored week
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
    titles = {'development': 'Development (May-June)', 'validation': 'Validation (July-September)',
              'combined': 'Both periods combined'}
    yc = 'estimated_missed_worth_investigating_per_monitored_week'
    for ax, period in zip(axes, PERIODS + ['combined']):
        for p in POLICIES:
            if period == 'combined':
                x = t1b[t1b.policy == LABEL[p]].cases_per_monitored_week.iloc[0]
                y = 0.0 if p == 'immediate' else t4c[t4c.policy == LABEL[p]][yc].iloc[0]
            else:
                x = t1[(t1.period == period) & (t1.policy == LABEL[p])].cases_per_monitored_week.iloc[0]
                y = 0.0 if p == 'immediate' else \
                    t4b[(t4b.period == period) & (t4b.policy == LABEL[p])][yc].iloc[0]
            ax.scatter(x, y, s=70, color=COLOR[p], edgecolor='white', linewidth=1.5, zorder=3)
            off = {'immediate': (-10, 10, 'right'), 'continuous30': (8, 6, 'left'),
                   'continuous20': (-2, -18, 'center'), '20of30': (10, -4, 'left')}[p]
            ax.annotate(LABEL[p], (x, y), textcoords='offset points', xytext=off[:2], ha=off[2],
                        fontsize=8.5, color=INK)
        ax.set_xscale('log'); ax.set_xlim(0.1, 15)
        ax.set_xticks([0.1, 0.2, 0.5, 1, 2, 5, 10]); ax.set_xticklabels(['0.1', '0.2', '0.5', '1', '2', '5', '10'])
        ax.minorticks_off()
        ax.set_title(titles[period], loc='left', fontweight='bold')
        ax.set_xlabel('Cases per monitored week (log scale)')
    axes[0].set_ylabel('Estimated missed cases worth investigating\nper monitored week')
    axes[0].set_ylim(-0.08, 1.5)
    fig.suptitle('Alert workload against estimated missed cases worth investigating',
                 x=0.01, y=1.02, ha='left', color=INK, fontweight='bold')
    fig.tight_layout(); fig.savefig(out/'chart_tradeoff.png', bbox_inches='tight'); plt.close(fig)

    # 2. Missed cases: abnormal_minutes of every case each persistence policy misses, by review_group
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), sharey=True)
    rng = np.random.default_rng(0)
    for ax, period in zip(axes, PERIODS + ['combined']):
        c = cases if period == 'combined' else cases[cases.period == period]
        for i, p in enumerate(POLICIES[1:]):
            miss = c[c[p].isna()]
            for g in GROUPS:
                m = miss[miss.review_group == g]
                if not len(m):
                    continue
                x = i + rng.uniform(-0.2, 0.2, len(m))
                big = g != 'immediate_only'
                ax.scatter(x, m.abnormal_minutes, s=30 if big else 9, color=GROUP_COLOR[g],
                           alpha=0.9 if big else 0.4, edgecolor=INK if big else 'none',
                           linewidth=0.6, zorder=3 if big else 2,
                           label=g if (i == 0 or g == 'shorter_duration_adds_case') else None)
            ax.text(i, 330, f'{len(miss)} missed', ha='center', fontsize=8, color=INK)
        ax.axhline(20, color=MUTED, linewidth=0.8, linestyle='--')
        ax.text(-0.45, 21, '20 abnormal min', fontsize=7, color=MUTED, ha='left', va='bottom')
        ax.set_yscale('log'); ax.set_ylim(0.8, 500)
        ax.set_yticks([1, 2, 5, 10, 20, 50, 100, 200]); ax.set_yticklabels(['1', '2', '5', '10', '20', '50', '100', '200'])
        ax.minorticks_off()
        ax.set_xticks(range(3)); ax.set_xticklabels([LABEL[p] for p in POLICIES[1:]])
        ax.set_title(titles[period], loc='left', fontweight='bold')
        ax.grid(axis='x', visible=False)
    axes[0].set_ylabel('abnormal_minutes of each missed case (log scale)')
    h, l = [], []
    for ax in axes:
        for hh, ll in zip(*ax.get_legend_handles_labels()):
            if ll not in l:
                h.append(hh); l.append(ll)
    fig.legend(h, l, loc='lower center', ncol=3, fontsize=8, bbox_to_anchor=(0.5, -0.12), title='review_group')
    fig.suptitle('Cases Immediate alerts on that each persistence policy misses',
                 x=0.01, y=1.02, ha='left', color=INK, fontweight='bold')
    fig.tight_layout(); fig.savefig(out/'chart_missed_severity.png', bbox_inches='tight'); plt.close(fig)


def md(df):
    cols = list(df.columns)
    lines = ['| ' + ' | '.join(map(str, cols)) + ' |', '|' + '---|' * len(cols)]
    for r in df.itertuples(index=False):
        lines.append('| ' + ' | '.join('' if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + ' |')
    return '\n'.join(lines)


def write_summary(out, t1, t1b, t2, t3, t4, t4b, t4c, share):
    sh = share.reset_index()[['review_group', 'plots', 'rated_investigate', 'investigate_share']].round(2)
    text = f"""# Step 3: four alert policies side by side (development and validation)

Generated by `step3_policy_comparison.py`; the written trade-off analysis is in `STEP3_TRADEOFFS.md`.
Development is May-June, validation July-September; October-December is not read. Cases are excursion
cases, not confirmed faults. This step compares; it does not select a policy (step 4).

## Table 1. Cases, cases missed and delay per monitored week

Cases missed are cases Immediate alerts on that the policy does not.

{md(t1)}

### Table 1b. The same, development and validation combined

Pooled: cases, cases missed and delay minutes are added across both periods and divided by the total
monitored weeks.

{md(t1b)}

## Table 2. Step-1 plots each policy alerts on, by step 1 rating

Case plots only (16); the 4 random_no_threshold_excursion control windows are counted separately.

{md(t2)}

## Table 3. Step-2 controlled tests (threshold-crossing test)

{md(t3)}

Fixed +1/+5/+10 kW results: `table3b_step2_fixed_magnitude.csv`.

## Table 4. Missed-pattern severity, by review_group (full data)

Step 1 investigate share per review_group (each rests on 4 plots):

{md(sh)}

{md(t4)}

Totals:

{md(t4b)}

Both periods combined (pooled over the total monitored weeks):

{md(t4c)}

![trade-off](chart_tradeoff.png)

![missed](chart_missed_severity.png)
"""
    (out/'STEP3_SUMMARY.md').write_text(text, encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--ratings', default='step3_inputs/reviewer1_ratings.csv')
    ap.add_argument('--out', default='step3_results')
    a = ap.parse_args()
    repo, out = Path(a.repo), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases, workload, key, ratings, ctrl = read_inputs(repo, repo/a.ratings)
    weeks = monitored_weeks(workload)
    k = rated_key(key, ratings)
    t1 = table1(cases, workload, weeks)
    t1b = table1b(cases, weeks)
    t2 = table2(k)
    t3, t3b = table3(ctrl)
    t4, t4b, share = table4(cases, k, weeks)
    t4c = table4c(cases, share, weeks)
    t1.to_csv(out/'table1_cases_missed_delay.csv', index=False)
    t1b.to_csv(out/'table1b_cases_missed_delay_combined.csv', index=False)
    t2.to_csv(out/'table2_reviewer_alerts.csv', index=False)
    t3.to_csv(out/'table3_step2_threshold_crossing.csv', index=False)
    t3b.to_csv(out/'table3b_step2_fixed_magnitude.csv', index=False)
    t4.to_csv(out/'table4_missed_severity.csv', index=False)
    t4b.to_csv(out/'table4b_missed_severity_totals.csv', index=False)
    t4c.to_csv(out/'table4c_missed_severity_combined.csv', index=False)
    charts(t1, t4b, t1b, t4c, cases, out)
    write_summary(out, t1, t1b, t2, t3, t4, t4b, t4c, share)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
    for name, t in [('Table 1', t1), ('Table 1b', t1b), ('Table 2', t2), ('Table 4', t4), ('Table 4 totals', t4b), ('Table 4 combined', t4c)]:
        print(f'\n{name}\n{t.to_string(index=False)}')
    print(f'\nSaved in {out}/. Development and validation only; October-December not read.')


if __name__ == '__main__':
    main()
