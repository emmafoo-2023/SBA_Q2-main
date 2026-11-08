# Fixed-magnitude injection tests

These are controlled sensitivity tests. A known increase was added to real power readings. They are not confirmed AC faults, and they are not an estimate of fault-detection accuracy.

## How this differs from the threshold-crossing tests

The threshold-crossing test moves each scheduled minute to 0.1 kW past the local threshold, so every scheduled minute is abnormal by construction. This test adds a fixed +1, +5 or +10 kW to the original observed power and leaves every other minute unchanged. The 28-day baseline and the threshold, the larger of three historical standard deviations and 0.5 kW, are computed from the unmodified series. An injected minute is abnormal only when the new reading is far enough above that expected power. A change that stays inside the band is a miss for every policy.

The same quiet, fully observed May-September windows are used for +1, +5 and +10 kW. A window is kept only when every designated minute can accept +10 kW without leaving 0-100 kW. Smaller increases are then applied to those same windows. Values are not clipped into range. October-December is not used.

## Windows and exclusions

Quiet, fully observed start minutes across units, periods and patterns: 7157180. These minutes overlap inside long quiet stretches, so this is not a count of separate events. Of those starts, 0 could not accept +10 kW because the original reading plus 10 kW would exceed 100 kW. 0 would have fallen below 0 kW. The paired sample places 2520 pattern-windows from the starts that can accept +10 kW, at most 36 per unit, period and pattern, spread across months, 6-hour bands and whether the hour's median expected power is at least 1 kW.

| Period | Pattern | Quiet starts | Feasible at +1 kW | Feasible at +5 kW | Feasible at +10 kW | Excluded at +10 kW for exceeding 100 | Placed paired windows |
|---|---|---:|---:|---:|---:|---:|---:|
| development | spike_1 | 580200 | 580200 | 580200 | 580200 | 0 | 252 |
| development | spike_5 | 580200 | 580200 | 580200 | 580200 | 0 | 252 |
| development | continuous_20 | 580200 | 580200 | 580200 | 580200 | 0 | 252 |
| development | continuous_30 | 580200 | 580200 | 580200 | 580200 | 0 | 252 |
| development | two_bursts | 580200 | 580200 | 580200 | 580200 | 0 | 252 |
| validation | spike_1 | 851236 | 851236 | 851236 | 851236 | 0 | 252 |
| validation | spike_5 | 851236 | 851236 | 851236 | 851236 | 0 | 252 |
| validation | continuous_20 | 851236 | 851236 | 851236 | 851236 | 0 | 252 |
| validation | continuous_30 | 851236 | 851236 | 851236 | 851236 | 0 | 252 |
| validation | two_bursts | 851236 | 851236 | 851236 | 851236 | 0 | 252 |

Every quiet start could accept +1, +5 and +10 kW without leaving 0-100 kW, so none were excluded for range. The detection tables use those same placed windows for every magnitude.
All five patterns were placed on the same 504 hosts. Each host was tested at all three magnitudes.

## Detection

Crossed counts windows with at least one injected minute above the threshold. Detected counts windows that produced an alert. A detection rate of 100% means every placed window alerted. Misses with no crossing equal placed minus crossed, and they are misses for every policy. Misses despite a crossing are windows that did cross and still did not alert. Delay is minutes from the first injected minute to the first alert. The range is shown when the delay is not the same on every detection.

| Period | Pattern | Added kW | Placed | Crossed | Immediate | Continuous20 | Continuous30 | 20of30 |
|---|---|---:|---:|---:|---|---|---|---|
| development | spike_1 | 1 | 252 | 206 (82%) | 206/252 (82%), delay 0 min | 0/252 (0%); 206 crossed but missed | 0/252 (0%); 206 crossed but missed | 0/252 (0%); 206 crossed but missed |
| development | spike_1 | 5 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed |
| development | spike_1 | 10 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed |
| development | spike_5 | 1 | 252 | 214 (85%) | 214/252 (85%), delay 0 [0, 3] min | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed |
| development | spike_5 | 5 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed |
| development | spike_5 | 10 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed |
| development | continuous_20 | 1 | 252 | 214 (85%) | 214/252 (85%), delay 0 [0, 3] min | 205/252 (81%), delay 19 min; 9 crossed but missed | 0/252 (0%); 214 crossed but missed | 205/252 (81%), delay 19 min; 9 crossed but missed |
| development | continuous_20 | 5 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 216/252 (86%), delay 19 min | 0/252 (0%); 216 crossed but missed | 216/252 (86%), delay 19 min |
| development | continuous_20 | 10 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 216/252 (86%), delay 19 min | 0/252 (0%); 216 crossed but missed | 216/252 (86%), delay 19 min |
| development | continuous_30 | 1 | 252 | 215 (85%) | 215/252 (85%), delay 0 [0, 29] min | 207/252 (82%), delay 19 [19, 28] min; 8 crossed but missed | 197/252 (78%), delay 29 min; 18 crossed but missed | 208/252 (83%), delay 19 [19, 27] min; 7 crossed but missed |
| development | continuous_30 | 5 | 252 | 217 (86%) | 217/252 (86%), delay 0 [0, 29] min | 216/252 (86%), delay 19 min; 1 crossed but missed | 210/252 (83%), delay 29 min; 7 crossed but missed | 216/252 (86%), delay 19 min; 1 crossed but missed |
| development | continuous_30 | 10 | 252 | 218 (87%) | 218/252 (87%), delay 0 [0, 29] min | 216/252 (86%), delay 19 min; 2 crossed but missed | 216/252 (86%), delay 29 min; 2 crossed but missed | 216/252 (86%), delay 19 min; 2 crossed but missed |
| development | two_bursts | 1 | 252 | 214 (85%) | 214/252 (85%), delay 0 [0, 3] min | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed | 203/252 (81%), delay 24 min; 11 crossed but missed |
| development | two_bursts | 5 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 216/252 (86%), delay 24 min |
| development | two_bursts | 10 | 252 | 216 (86%) | 216/252 (86%), delay 0 min | 0/252 (0%); 216 crossed but missed | 0/252 (0%); 216 crossed but missed | 216/252 (86%), delay 24 min |
| validation | spike_1 | 1 | 252 | 202 (80%) | 202/252 (80%), delay 0 min | 0/252 (0%); 202 crossed but missed | 0/252 (0%); 202 crossed but missed | 0/252 (0%); 202 crossed but missed |
| validation | spike_1 | 5 | 252 | 212 (84%) | 212/252 (84%), delay 0 min | 0/252 (0%); 212 crossed but missed | 0/252 (0%); 212 crossed but missed | 0/252 (0%); 212 crossed but missed |
| validation | spike_1 | 10 | 252 | 214 (85%) | 214/252 (85%), delay 0 min | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed |
| validation | spike_5 | 1 | 252 | 204 (81%) | 204/252 (81%), delay 0 [0, 2] min | 0/252 (0%); 204 crossed but missed | 0/252 (0%); 204 crossed but missed | 0/252 (0%); 204 crossed but missed |
| validation | spike_5 | 5 | 252 | 213 (85%) | 213/252 (85%), delay 0 [0, 3] min | 0/252 (0%); 213 crossed but missed | 0/252 (0%); 213 crossed but missed | 0/252 (0%); 213 crossed but missed |
| validation | spike_5 | 10 | 252 | 217 (86%) | 217/252 (86%), delay 0 [0, 3] min | 0/252 (0%); 217 crossed but missed | 0/252 (0%); 217 crossed but missed | 0/252 (0%); 217 crossed but missed |
| validation | continuous_20 | 1 | 252 | 206 (82%) | 206/252 (82%), delay 0 [0, 8] min | 199/252 (79%), delay 19 min; 7 crossed but missed | 0/252 (0%); 206 crossed but missed | 199/252 (79%), delay 19 min; 7 crossed but missed |
| validation | continuous_20 | 5 | 252 | 213 (85%) | 213/252 (85%), delay 0 [0, 3] min | 211/252 (84%), delay 19 min; 2 crossed but missed | 0/252 (0%); 213 crossed but missed | 211/252 (84%), delay 19 min; 2 crossed but missed |
| validation | continuous_20 | 10 | 252 | 221 (88%) | 221/252 (88%), delay 0 [0, 18] min | 212/252 (84%), delay 19 min; 9 crossed but missed | 0/252 (0%); 221 crossed but missed | 212/252 (84%), delay 19 min; 9 crossed but missed |
| validation | continuous_30 | 1 | 252 | 208 (83%) | 208/252 (83%), delay 0 [0, 24] min | 200/252 (79%), delay 19 [19, 26] min; 8 crossed but missed | 195/252 (77%), delay 29 min; 13 crossed but missed | 202/252 (80%), delay 19 [19, 25] min; 6 crossed but missed |
| validation | continuous_30 | 5 | 252 | 214 (85%) | 214/252 (85%), delay 0 [0, 22] min | 211/252 (84%), delay 19 min; 3 crossed but missed | 209/252 (83%), delay 29 min; 5 crossed but missed | 211/252 (84%), delay 19 min; 3 crossed but missed |
| validation | continuous_30 | 10 | 252 | 221 (88%) | 221/252 (88%), delay 0 [0, 18] min | 212/252 (84%), delay 19 min; 9 crossed but missed | 210/252 (83%), delay 29 min; 11 crossed but missed | 212/252 (84%), delay 19 min; 9 crossed but missed |
| validation | two_bursts | 1 | 252 | 208 (83%) | 208/252 (83%), delay 0 [0, 24] min | 0/252 (0%); 208 crossed but missed | 0/252 (0%); 208 crossed but missed | 198/252 (79%), delay 24 min; 10 crossed but missed |
| validation | two_bursts | 5 | 252 | 214 (85%) | 214/252 (85%), delay 0 [0, 22] min | 0/252 (0%); 214 crossed but missed | 0/252 (0%); 214 crossed but missed | 210/252 (83%), delay 24 min; 4 crossed but missed |
| validation | two_bursts | 10 | 252 | 220 (87%) | 220/252 (87%), delay 0 [0, 18] min | 0/252 (0%); 220 crossed but missed | 0/252 (0%); 220 crossed but missed | 210/252 (83%), delay 24 min; 10 crossed but missed |

## Whether a larger increase crosses and alerts more often

On the paired windows, the share with at least one threshold crossing rose or stayed the same as the added power went from +1 to +5 to +10 kW, for every pattern in both periods.
Alert detection for each policy also rose or stayed the same across those three magnitudes. A rate that stays at zero is a policy that misses the shape even after the larger increase.
Pooled across patterns and both periods, +1 kW crossed on 2091 of 2520 pattern-windows (83%); +5 kW crossed on 2147 of 2520 pattern-windows (85%); +10 kW crossed on 2175 of 2520 pattern-windows (86%).

## Short and intermittent changes

spike_1, Continuous20: 0 alerts out of 1512 windows, of which 1266 had at least one threshold crossing and still no alert.
spike_1, Continuous30: 0 alerts out of 1512 windows, of which 1266 had at least one threshold crossing and still no alert.
spike_1, 20of30: 0 alerts out of 1512 windows, of which 1266 had at least one threshold crossing and still no alert.
spike_5, Continuous20: 0 alerts out of 1512 windows, of which 1280 had at least one threshold crossing and still no alert.
spike_5, Continuous30: 0 alerts out of 1512 windows, of which 1280 had at least one threshold crossing and still no alert.
spike_5, 20of30: 0 alerts out of 1512 windows, of which 1280 had at least one threshold crossing and still no alert.
two_bursts, Continuous20: 0 alerts out of 1512 windows, of which 1288 had at least one threshold crossing and still no alert.
two_bursts, Continuous30: 0 alerts out of 1512 windows, of which 1288 had at least one threshold crossing and still no alert.
two_bursts, 20of30: 1253 alerts out of 1512 windows, of which 35 had at least one threshold crossing and still no alert.

## Development and validation

Development and validation detection rates agreed within 5 percentage points for every pattern, magnitude and policy.

## Expected load

The paired sample mixes quiet hours whose expected power is near zero with hours whose expected power is at least 1 kW. Near zero, the threshold is often the 0.5 kW floor, so +1 kW already crosses. The split below uses the hour's median expected power.

| Expected load | Added kW | Placed pattern-windows | Crossed | Immediate alerts |
|---|---:|---:|---:|---:|
| expected below 1 kW | 1 | 406 | 399 (98%) | 399 (98%) |
| expected below 1 kW | 5 | 406 | 403 (99%) | 403 (99%) |
| expected below 1 kW | 10 | 406 | 404 (100%) | 404 (100%) |
| expected at least 1 kW | 1 | 98 | 24 (24%) | 24 (24%) |
| expected at least 1 kW | 5 | 98 | 28 (29%) | 28 (29%) |
| expected at least 1 kW | 10 | 98 | 35 (36%) | 35 (36%) |

The continuous-30 row is one window per placed host. Spike and burst rows sit on their own hosts and are in the event file.

## What this does not support

The rates describe these added shapes on quiet, fully observed windows. They do not estimate how often a real fault has this size or duration, and they do not use October-December. Holidays, weather, occupancy and operating state are still outside the baseline. The unchanged windows produced no alert, which checks that these hosts were inside the band before the addition. It is not an operational false-alert rate.

## Reproduction

```
py fixed_magnitude_injection_tests.py "2019Floor3.csv"
```

Outputs land in fixed_magnitude_results/. The threshold-crossing results stay in controlled_injection_results/.
