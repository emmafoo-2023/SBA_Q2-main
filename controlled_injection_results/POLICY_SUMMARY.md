# Controlled tests of the four alert methods

These tests add known power changes to quiet, fully observed Floor 3 readings from May–September and score Immediate, Continuous20, Continuous30 and 20of30 on the same examples. They are controlled sensitivity tests, not confirmed AC faults and not a measure of fault-detection accuracy.

The original `2019Floor3.csv` was not modified. April is used only to warm up the 28-day baseline. October–December is not used. The baseline and the threshold (the larger of three historical standard deviations and 0.5 kW) stay on the unmodified readings. Each window was also scored with no change added. Those checks produced no alert, so an existing excursion was not counted as a detection.

## What was tested

| Requirement | Result |
|---|---|
| Copies of suitable May–September data; original unchanged | Done. Changes were applied in memory. |
| Continuous increases, repeated increases with gaps, and brief spikes, at different durations | Done. Durations run from 1 minute to 60 minutes, including gaps. |
| Different sizes | Done in the fixed-size test: +1, +5 and +10 kW added to the original reading. |
| All four methods on the same examples | Done. |
| Comparison with the unchanged data | Done. Unchanged windows produced no alert. |
| Table of how many added patterns each method detects, and the delay | This file. |

Two setups are reported separately because they answer different questions. In the first, every scheduled minute is placed just past the threshold, so the result is the timing rule alone. In the second, a fixed kilowatt increase is added to the original reading, and a minute counts only if it actually crosses the threshold.

## Results at a glance

Read this section first. The sections below repeat the same numbers with the placement rules.

Each cell is **how many placed windows alerted**, then **minutes from the first injected minute to the first alert**. `none` means that method never alerted on that pattern. A delay of 19 minutes is the alert on the 20th injected minute. A delay of 29 minutes is the alert on the 30th.

| Method | What it needs before it alerts |
|---|---|
| Immediate | One minute above the threshold. Delay is 0 when the first injected minute crosses. |
| Continuous20 | 20 uninterrupted minutes above the threshold. |
| Continuous30 | 30 uninterrupted minutes above the threshold. |
| 20of30 | 20 minutes above the threshold inside some 30-minute window. Gaps are allowed. |

### Timing rule only: every scheduled minute is forced just past the threshold

Development and validation agreed. High-power and low-power injections agreed. The delay did not vary. "All" means every placed window.

| Added pattern | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---|---|---|---|
| 1-minute spike | all, 0 min | none | none | none |
| 5-minute spike | all, 0 min | none | none | none |
| 10 continuous minutes | all, 0 min | none | none | none |
| 20 continuous minutes | all, 0 min | all, 19 min | none | all, 19 min |
| 25 continuous minutes | all, 0 min | all, 19 min | none | all, 19 min |
| 30 continuous minutes | all, 0 min | all, 19 min | all, 29 min | all, 19 min |
| 60 continuous minutes | all, 0 min | all, 19 min | all, 29 min | all, 19 min |
| 19 on, 1 off, 19 on | all, 0 min | none | none | all, 20 min |
| 10 on, 5 off, 10 on | all, 0 min | none | none | all, 24 min |
| 2 on / 1 off for 30 minutes | all, 0 min | none | none | all, 28 min |
| 3 on / 3 off pulses | all, 0 min | none | none | none |
| 5 on / 10 off cycles | all, 0 min | none | none | none |
| **Patterns detected** | **12 of 12** | **4 of 12** | **2 of 12** | **7 of 12** |

### Fixed size: +1, +5 or +10 kW added to the original reading

Each row is 504 windows (252 in May–June and 252 in July–September), the same hosts for every pattern and every size. The count is windows that alerted. Immediate misses only windows that never cross the threshold. A persistence method can still show none after a crossing. A range means the delay was not the same on every detection.

| Added pattern | Size | Crossed | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---:|---:|---|---|---|---|
| 1-minute spike | +1 kW | 408/504 | 408, 0 min | none | none | none |
| 1-minute spike | +5 kW | 428/504 | 428, 0 min | none | none | none |
| 1-minute spike | +10 kW | 430/504 | 430, 0 min | none | none | none |
| 5-minute spike | +1 kW | 418/504 | 418, 0–3 min | none | none | none |
| 5-minute spike | +5 kW | 429/504 | 429, 0–3 min | none | none | none |
| 5-minute spike | +10 kW | 433/504 | 433, 0–3 min | none | none | none |
| 20 continuous minutes | +1 kW | 420/504 | 420, 0–8 min | 404, 19 min | none | 404, 19 min |
| 20 continuous minutes | +5 kW | 429/504 | 429, 0–3 min | 427, 19 min | none | 427, 19 min |
| 20 continuous minutes | +10 kW | 437/504 | 437, 0–18 min | 428, 19 min | none | 428, 19 min |
| 30 continuous minutes | +1 kW | 423/504 | 423, 0–29 min | 407, 19–28 min | 392, 29 min | 410, 19–27 min |
| 30 continuous minutes | +5 kW | 431/504 | 431, 0–29 min | 427, 19 min | 419, 29 min | 427, 19 min |
| 30 continuous minutes | +10 kW | 439/504 | 439, 0–29 min | 428, 19 min | 426, 29 min | 428, 19 min |
| 10 on, 5 off, 10 on | +1 kW | 422/504 | 422, 0–24 min | none | none | 401, 24 min |
| 10 on, 5 off, 10 on | +5 kW | 430/504 | 430, 0–22 min | none | none | 426, 24 min |
| 10 on, 5 off, 10 on | +10 kW | 436/504 | 436, 0–18 min | none | none | 426, 24 min |
| **Windows detected** | **all 15 rows** | **—** | **6413 of 7560** | **2521 of 7560** | **1237 of 7560** | **3777 of 7560** |

7560 is 5 patterns × 3 sizes × 504 windows. Continuous20’s 2521 alerts are only the 20-minute and 30-minute runs (1259 + 1262). Continuous30’s 1237 alerts are only the 30-minute runs (392 + 419 + 426). 20of30’s 3777 alerts are those same runs plus the gapped bursts (1259 + 1265 + 1253). Spikes add alerts for Immediate only.

What this means for the next person: Immediate catches every shape as soon as one minute crosses, including 1-minute spikes. Continuous20 needs a solid 20-minute run and then waits 19 minutes; one gap (the 19-on/1-off/19-on pattern, and the 10-on/5-off/10-on pattern) makes it miss. Continuous30 needs a solid 30-minute run and then waits 29 minutes; it misses every shorter pattern and every gapped pattern. 20of30 catches the long runs at the same 19 minutes as Continuous20, and it also catches gapped bursts (20 min, 24 min, or 28 min depending on the gap pattern). It still misses spikes and the patterns that never put 20 abnormal minutes inside any 30-minute window (3-on/3-off, and 5-on/10-off).

A larger added kilowatt value raises how often the reading crosses. It does not change which shapes the persistence methods can see.

## 1. Every scheduled minute crosses the threshold

Delay is minutes from the first injected minute to the first alert. "All" means every placed window. "None" means no placed window. Development and validation agreed, and high-power and low-power injections agreed. The delay did not vary.

| Added pattern | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---|---|---|---|
| 1-minute spike | all, 0 min | none | none | none |
| 5-minute spike | all, 0 min | none | none | none |
| 10 continuous minutes | all, 0 min | none | none | none |
| 20 continuous minutes | all, 0 min | all, 19 min | none | all, 19 min |
| 25 continuous minutes | all, 0 min | all, 19 min | none | all, 19 min |
| 30 continuous minutes | all, 0 min | all, 19 min | all, 29 min | all, 19 min |
| 60 continuous minutes | all, 0 min | all, 19 min | all, 29 min | all, 19 min |
| 19 on, 1 off, 19 on | all, 0 min | none | none | all, 20 min |
| 10 on, 5 off, 10 on | all, 0 min | none | none | all, 24 min |
| 2 on / 1 off for 30 minutes | all, 0 min | none | none | all, 28 min |
| 3 on / 3 off pulses | all, 0 min | none | none | none |
| 5 on / 10 off cycles | all, 0 min | none | none | none |
| Patterns detected | 12 of 12 | 4 of 12 | 2 of 12 | 7 of 12 |

High-power versions of every pattern used 252 windows in May–June and 252 in July–September. Low-power versions exist only where expected power can fall without going below 0 kW, so Zone 1 AC1–AC3 have none. Where a low-power window could be placed, the same policy result held.

A delay of 19 minutes is the alert on the 20th injected minute. A delay of 29 minutes is the alert on the 30th.

## 2. Fixed increase of +1, +5 or +10 kW

The increase is added to the original observed power. It is not forced past the threshold. Each row uses 504 windows: 252 in May–June and 252 in July–September, the same hosts for every pattern and every size. No window was dropped for leaving 0–100 kW, and none was clipped. Development and validation differed by at most 4 percentage points, so the counts below add the two periods.

The count under each policy is windows that alerted. Immediate alerts on every window that crosses at least once, so its misses are the windows with no crossing. A persistence policy can still show none after the threshold has been crossed.

| Added pattern | Size | Crossed the threshold | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---:|---:|---|---|---|---|
| 1-minute spike | +1 kW | 408/504 | 408, 0 min | none | none | none |
| 1-minute spike | +5 kW | 428/504 | 428, 0 min | none | none | none |
| 1-minute spike | +10 kW | 430/504 | 430, 0 min | none | none | none |
| 5-minute spike | +1 kW | 418/504 | 418, 0–3 min | none | none | none |
| 5-minute spike | +5 kW | 429/504 | 429, 0–3 min | none | none | none |
| 5-minute spike | +10 kW | 433/504 | 433, 0–3 min | none | none | none |
| 20 continuous minutes | +1 kW | 420/504 | 420, 0–8 min | 404, 19 min | none | 404, 19 min |
| 20 continuous minutes | +5 kW | 429/504 | 429, 0–3 min | 427, 19 min | none | 427, 19 min |
| 20 continuous minutes | +10 kW | 437/504 | 437, 0–18 min | 428, 19 min | none | 428, 19 min |
| 30 continuous minutes | +1 kW | 423/504 | 423, 0–29 min | 407, 19–28 min | 392, 29 min | 410, 19–27 min |
| 30 continuous minutes | +5 kW | 431/504 | 431, 0–29 min | 427, 19 min | 419, 29 min | 427, 19 min |
| 30 continuous minutes | +10 kW | 439/504 | 439, 0–29 min | 428, 19 min | 426, 29 min | 428, 19 min |
| 10 on, 5 off, 10 on | +1 kW | 422/504 | 422, 0–24 min | none | none | 401, 24 min |
| 10 on, 5 off, 10 on | +5 kW | 430/504 | 430, 0–22 min | none | none | 426, 24 min |
| 10 on, 5 off, 10 on | +10 kW | 436/504 | 436, 0–18 min | none | none | 426, 24 min |

No fixed-size row is 504/504. A larger increase raises the number of crossings, from 408 to 430 of 504 for a 1-minute spike and from 423 to 439 of 504 for a 30-minute run. It does not make Continuous20 or Continuous30 detect a 1-minute spike, a 5-minute spike, or the gapped bursts. Continuous30 also misses every 20-minute run.

Most of these windows are quiet hours near 0 kW, where the threshold is often the 0.5 kW floor, so +1 kW already crosses. On the 98 hosts in the 30-minute test whose expected power was at least 1 kW, Immediate crossed 24/98 at +1 kW, 28/98 at +5 kW, and 35/98 at +10 kW. On the other 406 hosts, the same counts were 399, 403 and 404.

## How to read the two tests together

When a minute does cross, Immediate alerts on that minute. Its delay is 0 when the first injected minute crosses, and later when only a later minute crosses. Continuous20 needs 20 uninterrupted crossing minutes and then alerts at 19 minutes. Continuous30 needs 30 uninterrupted crossing minutes and then alerts at 29 minutes. 20of30 needs 20 crossing minutes inside some 30-minute window. It misses both spikes. It catches the 10-on/5-off/10-on pattern at 24 minutes when enough of those minutes cross.

Detail for the first test is in this folder. Detail for the fixed-size test is in `fixed_magnitude_results/`.
