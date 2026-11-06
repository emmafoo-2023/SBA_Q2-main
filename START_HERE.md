# Floor 3 alert comparison: four policies
## What changed
Continuous20 was added. All methods use the same raw excursion case boundaries, 15-minute grouping, and common valid monitoring windows. Grouping is a comparison convention, not a fault definition. Missing observations are not filled. The baseline is the preceding 28 calendar days at the same minute and weekday/weekend type, with at least five matching weekdays or three weekend days. This version does not model holidays, weather, operating state or occupancy. Threshold: maximum of three historical standard deviations and 0.5 kW.

## Counts: high and low cases combined across seven units

| Period | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---:|---:|---:|---:|
| May-June development |179|14|8|16|
| July-September validation |444|41|29|49|

Validation: reducing the continuous duration from 30 to 20 minutes adds 12 cases. Allowing interruptions with 20of30 adds eight more beyond Continuous20. The latter eight all have longest abnormal runs below 20 minutes. These are case counts, not confirmed faults or recall.

## Review now
1. Open OPEN_REVIEW.html in a browser (keep review_plots beside it).
2. Two reviewers independently fill review_form.csv. Use investigate / monitor / uncertain, with reasons.
3. Only after independent review, open review_answer_key.csv to see policy results and sample categories.
4. Compare judgements; check schedules/holidays, longer histories and temperature evidence where needed. Do not force uncertain cases into faulty/healthy labels.

There are 20 plots: four per detected-pattern category (two development and two validation) and four random daytime no-excursion windows. This is a stratified convenience review sample, not representative fault prevalence or population precision. Inspect all ten interruption-added cases in development_validation_case_comparison.csv if resources allow. None of the packets includes October-December case results.

## Initial observations from inspected plots
- R12, Zone 1 AC2 on 22 August: repeated power pulses around 2.7 kW separated by low-power intervals. The historical expectation is near zero. It is unusual use relative to history; neither abnormal cycling nor malfunction is established.
- R08, Zone 2 AC1 on 30 September: power alternates between roughly 15 and 25 kW while the historical band also changes. An investigation candidate; no cause established.
- R17, Zone 4 AC1 on 17 July: observed power stays at zero across the displayed interval. Its threshold status changes partly because the historical band changes. Apparent intermittency in flags is not necessarily intermittent physical operation. Legitimate closure/schedule effects or a data issue need checking before attributing a fault.
- R19, Zone 1 AC4 on 4 July: a short low-power interval is captured only by the immediate method. A similar interval appears nearby. Power alone does not establish whether this is acceptable control behaviour.

## Limits and next decision
Shorter/less restrictive rules retain more cases by design. Counts alone cannot select a winner. Current reference-case elapsed times begin at the first statistical excursion, not a verified fault onset. Do not claim confirmed recall, false-alert rate, saved energy or maintenance benefits yet. Review supplies preliminary candidate judgements; controlled injected patterns can later quantify sensitivity/delay to specified patterns. Final evaluation should remain separate from tuning. Coverage of only later 2019 does not establish year-round performance.

## Optional reproduction
Install dependencies: py -m pip install pandas numpy matplotlib
Run: py compare_floor3_alerts_v3.py "2019Floor3.csv"

The script produces full baseline files and all three period outputs, including evaluation; use development/validation only until settings are frozen. It overwrites named files in its output folder. Default folder: floor3_alert_results_v3. The original CSV is unchanged. April is warm-up; January-March is excluded.
