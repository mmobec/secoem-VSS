# VSS / VSSD Results: QHS vs HG

Sim `001`, market `DA`, day `2025-10-31`. Four runs compared, from the 2026-09-12 re-run of the VSS/VSSD batch (`HG/results_vss_same_ren.csv`, `QHS/results_vss_dif_ren.csv`):

| Label | Branch / dataset | `sc` (raw) | Retained (in-model) scenarios | Results dir |
|---|---|---:|---:|---|
| QHS sc100 | `15min_different_ren` (dif_ren) | 100 | **90** | `secoem-VSS/QHS/results/..._sc100_15min_different_ren` |
| QHS sc150 | `15min_different_ren` (dif_ren) | 150 | **130** | `secoem-VSS/QHS/results/..._sc150_15min_different_ren` |
| HG sc100 | `15min_ren_same` (same_ren) | 100 | **37** | `secoem-VSS/HG/results/..._sc100_15min_same_ren` |
| HG sc380 | `15min_ren_same` (same_ren) | 380 | **130** | `secoem-VSS/HG/results/..._sc380_15min_same_ren` |

**sc150 (QHS) and sc380 (HG) were chosen as the matched pair** — both reduce to 130 retained scenarios, the intended apples-to-apples comparison point between the two datasets. HG sc480 also reduces to 130 and is used as a robustness check in §3.3. The two `sc100` runs are *not* matched: the same raw count (100) reduces to very different retained counts under each dataset's own scenario-tree reduction (90 for QHS vs. 37 for HG — a ~2.4x gap) — so `sc100` should be read as "same generation budget, different outcome," not as a controlled comparison.

**Data caveat.** This re-run's underlying scenario data differs from the version behind the previous edition of this report: baseline objectives are now roughly `-17,000` to `-22,000` EUR (previously `-26,000` to `-40,000` EUR), and retained-scenario counts for the same raw `sc` shifted too (e.g. HG sc100: 29 → 37). The previous matched pair (QHS sc170 / HG sc560, both 146 retained) could not be reproduced: in this re-run, every QHS batch attempt at `sc >= 160` fails before the RP solve even completes (`ApplicationError: Solver (gurobi) did not exit normally` or `ValueError: ... bad status: aborted` — 61/61 error rows for `sc` in `[160, 300]`), which looks like solver/resource contention in the batch harness rather than a modelling issue, but it caps the usable QHS range at `sc150` (130 retained) for this comparison. See §3.6.

All four objectives (`RP`, `EV`, `EDEV_t`, `EEV_t`) are **maximization** objectives (`sense=pyo.maximize` in `ev_subproblem.py`), reported as negative numbers (net cost dominates revenue on this day in every run). `VSS_t = RP - EEV_t` and `VSSD_t = RP - EDEV_t`; standard theory requires both `>= 0` since `RP` is optimal and `EEV_t`/`EDEV_t` are feasible-but-suboptimal policies evaluated under full recourse.

Macro-stage order (`t=1..6`): `DA, RM, IM1, IM2, IM3, IB`.

---

## 1. Raw results

### QHS sc100 (90 retained scenarios)

`RP = -17285.6471`, `EV = -17336.6684`

**Static chain (EEV_t / VSS_t)** — `run_static_vss.py`, single classical-EV fixing source, all 90 real scenarios:

| t | stage | EEV_t | VSS_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -17285.6471 | 0.0000 | 0.0 |
| 2 | RM | -17586.3642 | 300.7171 | 0.0 |
| 3 | IM1 | -17731.0487 | 445.4015 | 0.0 |
| 4 | IM2 | -17770.1670 | 484.5198 | 0.0 |
| 5 | IM3 | -17847.0354 | 561.3883 | 0.0 |
| 6 | IB | -18010.0228 | 724.3757 | 0.0 |

**Dynamic chain (EDEV_t / VSSD_t)** — `run_vssd.py`, per-group conditional-average fixing:

| t | stage | EDEV_t | VSSD_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -16252.1523 | -1033.4948 | 0.0 |
| 2 | RM | -16287.2817 | -998.3655 | 0.0 |
| 3 | IM1 | -16298.7730 | -986.8742 | 0.0 |
| 4 | IM2 | -16298.7730 | -986.8742 | 0.0 |
| 5 | IM3 | -16760.0449 | -525.6022 | 0.0 |
| 6 | IB | -16802.9143 | **-482.7329** | 0.0 |

`EDEV_2_recourse = -16625.1795`, `VSSD_2_recourse = -660.4676`

---

### QHS sc150 (130 retained scenarios)

`RP = -16935.5229`, `EV = -17398.5012`

**Static chain:**

| t | stage | EEV_t | VSS_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -16935.5229 | 0.0000 | 0.0 |
| 2 | RM | -17442.7937 | 507.2708 | 0.0 |
| 3 | IM1 | -17639.0965 | 703.5736 | 0.0 |
| 4 | IM2 | -17758.4538 | 822.9309 | 0.0 |
| 5 | IM3 | -17853.3347 | 917.8118 | 0.0 |
| 6 | IB | -17982.6580 | 1047.1351 | 0.0 |

**Dynamic chain:**

| t | stage | EDEV_t | VSSD_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -15831.2570 | -1104.2660 | 0.0 |
| 2 | RM | -15858.8047 | -1076.7182 | 0.0 |
| 3 | IM1 | -15869.7693 | -1065.7536 | 0.0 |
| 4 | IM2 | -15869.7693 | -1065.7536 | 0.0 |
| 5 | IM3 | -16125.0371 | -810.4858 | 0.0 |
| 6 | IB | -16187.5434 | **-747.9795** | 0.0 |

`EDEV_2_recourse = -15929.6873`, `VSSD_2_recourse = -1005.8357`

---

### HG sc100 (37 retained scenarios)

`RP = -22344.7975`, `EV = -22828.9273`

**Static chain:**

| t | stage | EEV_t | VSS_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -22344.7975 | 0.0000 | 0.0 |
| 2 | RM | -22726.5939 | 381.7964 | 0.0 |
| 3 | IM1 | -22889.6439 | 544.8464 | 0.0 |
| 4 | IM2 | -23009.3913 | 664.5938 | 0.0 |
| 5 | IM3 | -23108.3051 | 763.5076 | 0.0 |
| 6 | IB | -23160.8313 | 816.0337 | 0.0 |

**Dynamic chain:**

| t | stage | EDEV_t | VSSD_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -20931.0681 | -1413.7294 | 0.0 |
| 2 | RM | -20931.0681 | -1413.7294 | 0.0 |
| 3 | IM1 | -20963.3816 | -1381.4159 | 0.0 |
| 4 | IM2 | -20963.3817 | -1381.4158 | 0.0 |
| 5 | IM3 | -21185.8405 | -1158.9570 | 0.0 |
| 6 | IB | -21187.7238 | **-1157.0737** | 0.0 |

`EDEV_2_recourse = -21205.3444`, `VSSD_2_recourse = -1139.4531`

---

### HG sc380 (130 retained scenarios)

`RP = -21774.3944`, `EV = -22107.3337`

**Static chain:**

| t | stage | EEV_t | VSS_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -21774.3944 | 0.0000 | 0.0 |
| 2 | RM | -21839.6546 | 65.2602 | 0.0 |
| 3 | IM1 | -22053.3856 | 278.9911 | 0.0 |
| 4 | IM2 | -22246.6241 | 472.2296 | 0.0 |
| 5 | IM3 | -22347.1992 | 572.8047 | 0.0 |
| 6 | IB | -22410.0970 | 635.7026 | 0.0 |

**Dynamic chain:**

| t | stage | EDEV_t | VSSD_t | excluded weight |
|---|---|---:|---:|---:|
| 1 | DA | -20449.1074 | -1325.2870 | 0.0 |
| 2 | RM | -20462.7665 | -1311.6280 | 0.0 |
| 3 | IM1 | -20558.5613 | -1215.8331 | 0.0 |
| 4 | IM2 | -20558.9095 | -1215.4850 | 0.0 |
| 5 | IM3 | -20680.9144 | -1093.4800 | 0.0 |
| 6 | IB | -20590.8956 | **-1183.4988** | 0.0237 |

`EDEV_2_recourse = -20582.8502`, `VSSD_2_recourse = -1191.5443`

---

## 2. Cross-run comparison

![VSS_t and VSSD_t trajectories across all four runs](vss_comparison_chart.png)

All four lines are complete across all six stages in this re-run — unlike the previous edition, none of the four pinned runs hits static-chain infeasibility (see §3.1 for the wider picture).

### RP / EV baselines

| Run | RP | EV | EV − RP (cost of ignoring uncertainty entirely) |
|---|---:|---:|---:|
| QHS sc100 | -17285.65 | -17336.67 | -51.02 |
| QHS sc150 | -16935.52 | -17398.50 | -462.98 |
| HG sc100 | -22344.80 | -22828.93 | -484.13 |
| HG sc380 | -21774.39 | -22107.33 | -332.94 |

### Final-stage VSS / VSSD (where defined)

| Run | VSS_6 (IB, static) | VSSD_6 (IB, dynamic) |
|---|---:|---:|
| QHS sc100 | 724.38 | -482.73 |
| QHS sc150 | 1047.14 | -747.98 |
| HG sc100 | 816.03 | -1157.07 |
| HG sc380 | 635.70 | -1183.50 |

---

## 3. Insights

### 3.1 The static (EEV_t) chain is clean on this particular pair, but HG's wider sweep still shows the same infeasibility pattern as before

Both HG runs pinned in this report (`sc100`, `sc380`) have `excluded_infeasible_weight = 0.0` at every stage — the theoretical guarantee (`VSS_t >= 0`, monotone in `t`) holds cleanly for all four runs shown here. That is a change from the previous edition, where HG's static chain hit 100% infeasibility at several stages for both of its pinned runs.

However, this looks like it depends on *which* HG run you land on, not a fix to the underlying mechanism: across HG's full batch sweep (56 successful runs, `sc in [50, 600]`), **19 of 56 (34%)** still show a fully infeasible (`NaN`) static chain at IB, while QHS shows **zero** infeasible static chains among its 11 successful runs. The dataset-level asymmetry flagged previously — HG's `same_ren` data far more prone to the `_cap20()`/`relax_im_bounds_for_fixed_da()` intraday-bound infeasibility than QHS's `dif_ren` data — persists in this re-run; it just happens not to hit the two specific scenario counts (`sc100`, `sc380`) chosen for the matched comparison here. **This confirms the fix noted in the project's open-items tracker is still not implemented**, not that the underlying issue went away.

### 3.2 The dynamic (EDEV_t) chain is negative at the final stage in *all four* runs — Prop. 5 keeps failing

`VSSD_6` is negative in every run, on entirely different underlying data than the previous edition of this report:

| QHS sc100 | QHS sc150 | HG sc100 | HG sc380 |
|---:|---:|---:|---:|
| -482.73 | -747.98 | -1157.07 | -1183.50 |

This is the same known open anomaly (`RP >= EDEV_T` should hold by Proposition 5, but doesn't), now reconfirmed on a fully re-generated dataset with materially different objective scales — strong evidence this is a structural property of the VSSD construction, not an artifact of one particular scenario tree. The same qualitative pattern from before still holds:
- **Magnitude scales with dataset, not scenario count**: HG's violation is roughly -1157 to -1184 regardless of `sc100` or `sc380`; QHS's own two counts (`sc100` → -482.73, `sc150` → -747.98) grow markedly with retained scenarios instead of staying flat.
- **QHS's violation more than 1.5x's** between `sc100` and `sc150` even though the underlying mechanism should, in principle, stabilise as more scenarios are retained.

### 3.3 Monotonicity of VSSD_t: clean in QHS and in HG sc100, but HG sc380 dips right where exclusion turns on — though a same-retained-count alternative (HG sc480) does not

Looking at the full `VSSD_t` trajectories (t=1..6):

- **QHS sc100**: -1033.49 → -998.37 → -986.87 → -986.87 → -525.60 → -482.73 — **monotonically improving** at every step.
- **QHS sc150**: -1104.27 → -1076.72 → -1065.75 → -1065.75 → -810.49 → -747.98 — **also monotonic.**
- **HG sc100**: -1413.73 → -1413.73 → -1381.42 → -1381.42 → -1158.96 → -1157.07 — **also monotonic** (flat steps at t1→t2 and t3→t4, no reversals). `excluded_weight = 0` throughout.
- **HG sc380**: -1325.29 → -1311.63 → -1215.83 → -1215.48 → -1093.48 → **-1183.50** — improving through t5, then a **dip at the final stage (t5→t6)**, landing back below the t4 value. This coincides exactly with `excluded_weight` turning on at IB (0 → 0.0237), the only nonzero exclusion anywhere in this report's four pinned runs.

As a robustness check, **HG sc480** (also 130 retained) was inspected: -1403.15 → -1403.15 → -1316.77 → -1316.77 → -1111.90 → -1000.00 — **strictly monotonic despite also excluding scenarios** at IM3 (0.0021) and IB (0.0083). So while HG sc380's dip does coincide with its exclusion turning on, HG sc480 shows that exclusion alone doesn't reliably break monotonicity in this re-run's data — the link between IIS-based exclusion and monotonicity violations is weaker/less deterministic here than the previous edition's data suggested. This nuance is worth carrying forward rather than restating the older, cleaner-looking correlation as settled.

### 3.4 Scale gap between datasets has narrowed

HG's baseline objectives now sit **~28–29% more negative** than QHS's at matched retained-scenario counts (HG sc100 vs QHS sc100: +29.3%; HG sc380 vs QHS sc150, both 130 retained: +28.6%) — down from the previous edition's ~45–50% gap. `EV - RP` no longer separates as cleanly by dataset either: HG's two runs give -484.13 and -332.94, while QHS's give -51.02 and -462.98 — QHS sc150's value actually falls inside HG's range. Read together with §3.2, the *VSSD_6*-based dataset separation still holds, but `EV - RP` alone is no longer a reliable dataset discriminator in this re-run — it looks more sensitive to retained-scenario count than to dataset identity here.

### 3.5 `sc100`'s retained-scenario gap (90 vs 37) still limits how much weight that comparison can carry

`sc100` reduces to 90 scenarios under QHS but only 37 under HG (a ~2.4x gap, versus ~3x in the previous edition). Any cross-dataset difference observed at `sc100` is confounded with "HG had ~2.4x fewer scenarios to reconcile." The `sc150`/`sc380` pair (both 130 retained) remains the only comparison here that isolates the dataset effect from the scenario-count effect, which is why §3.1/§3.4's dataset-level conclusions lean on that pair rather than on `sc100`.

### 3.6 New in this re-run: QHS's VSS batch is not reliably completing above `sc150`

Every QHS batch attempt at `sc >= 160` (`sc` in `{160, 170, ..., 300}`, 61 attempts total) failed before the RP solve finished — either `ApplicationError: Solver (gurobi) did not exit normally` or `ValueError: Cannot load a SolverResults object with bad status: aborted`, raised inside `solve_rp()` on the very first solve of the static chain. This pattern (100% failure rate, uniform error signature, failing at the earliest possible point) looks like batch-harness resource contention (16 concurrency lanes × 4 threads/solve competing for solver license/memory) rather than a model or data issue, but it is why this edition's matched pair tops out at 130 retained scenarios instead of the previous edition's 146: `sc170` (the run that previously worked) now fails outright. Worth a re-run with fewer concurrent lanes before concluding anything about QHS's behavior above 130 retained scenarios.

---

## 4. Known open items this data reinforces

- **`VSS_t`/`VSSD_t` infeasibility under the `_cap20()` DA-branch cap** — still not fixed. Not visible on this report's two pinned HG runs, but confirmed still present in 34% of HG's wider batch sweep (§3.1); QHS again shows zero infeasible static chains.
- **`VSSD >= 0` (Proposition 5) violation** — confirmed at the final stage in all four runs here, on a fully re-generated dataset with a different objective scale than the previous edition. Still an open, unresolved investigation, and now more clearly a structural property rather than a data artifact (§3.2).
- **New: QHS VSS-batch reliability above `sc150`** — 61/61 attempts at `sc >= 160` fail at the RP solve stage with solver crash/abort errors, most likely batch-harness concurrency contention rather than a modelling problem (§3.6). Not previously seen at `sc170` in the prior edition's data; needs a lower-concurrency re-run before drawing conclusions about QHS above 130 retained scenarios.
