# fitness-dashboard audit

Audit date: 2026-09-19

## Executive summary

The repository is now a **scheduled analytics and coaching engine** that uses the same current source-of-truth choices as the Health_Dashboard while preserving historical Fitbit-era data for backfill.

Current scheduled sources:

Daily source persistence (added 2026-10-28): GitHub Actions now runs `.github/workflows/daily_google_health_sync.yml` each day (07:10 UTC) as well as the existing Monday coaching refresh. `scripts/18_ingest_google_health.py` normalizes Google Health data, then `scripts/sync_google_health_to_neon.py` mirrors verified daily nutrition/activity into the private Neon health-dashboard database. The public repository contains code only, not exported personal measurements or OAuth credentials.

- **Withings persistent database:** body weight and body composition.
- **Google Health:** activity, resting HR/HRV, sleep, and Cronometer nutrition.
- **Hevy:** workouts, sets, and body measurements such as waist circumference.
- **Health_Dashboard grip storage:** grip-strength measurements, read from the same persistent Postgres database used by the dashboard.
- **DuckDB:** local analytical/compatibility layer and historical seed database.

Direct legacy Fitbit OAuth, direct legacy Withings OAuth, browser-driven Cronometer export, and fasting-specific coaching are not part of the automatic weekly decision path.

## Current weekly architecture

The Monday workflow runs in this order:

1. Install the lightweight weekly requirements.
2. Refresh Withings, grip, Google Health, and Hevy current data.
3. Rebuild clean body, activity/recovery, nutrition, training, and performance-marker tables.
4. Rebuild daily/weekly historical analytics.
5. Rebuild strength and personal-response analysis.
6. Determine the configured coaching phase (`cut`, `maintenance`, or `lean_gain`).
7. Build the Cut Stress / Recovery Guardrail.
8. Produce the phase-aware adaptive calorie recommendation.
9. Evaluate prior coaching decisions and log the current decision for 7-day and 14-day feedback.
10. Build lean-mass preservation, weekly report, coaching packet, and email summary.
11. Validate data freshness.
12. Persist adaptive coaching history back to the repository.
13. Upload reports and email the weekly summary.

The pipeline fails visibly when a required internal stage fails.

## Coaching architecture

### Phase handling

`coaching_state/phase_config.json` is the explicit phase configuration. Phase changes are intentionally not automatic. `77_phase_detection.py` may suggest reviewing a transition, but it does not silently move from a cut to maintenance or lean gain.

### Recovery guardrail

`78_cut_stress_guardrail.py` combines sleep, RHR, HRV, multi-week strength, BIA lean-mass trend, calorie undershoot, loss rate, and — once sufficient data exist — grip trend. It reports `STABLE`, `WATCH`, or `RECOVERY_CONCERN`. One isolated noisy signal is not enough to escalate the status.

### Performance markers

`16_sync_grip_persistent.py` imports grip measurements stored by the Health_Dashboard. Hevy ingestion also imports body measurements such as waist circumference. `25_build_performance_markers.py` creates the coaching-facing daily performance-marker table.

Grip is deliberately withheld from trend interpretation until repeated measurements exist. Waist is supportive body-composition context, not a recovery metric.

### Adaptive calorie model

`73_adaptive_calorie_recommendation.py` estimates rolling maintenance/TDEE from 28-day calorie intake plus the scale-weight trend, then applies phase-specific logic:

- **cut:** moderate deficit, adjusted conservatively for recovery/muscle-preservation signals;
- **maintenance:** target estimated maintenance;
- **lean_gain:** small configured surplus.

Weekly calorie changes remain capped at 150 kcal/day.

### Adaptive feedback loop

`76_adaptive_coaching_feedback.py` stores each weekly decision and evaluates later outcomes. It separates **adherence** from **effectiveness**.

Tracked adherence includes:

- calorie direction/change;
- protein target;
- sleep target;
- resistance-training frequency;
- daily steps.

Outcome context includes weight/fat/lean trends, RHR, HRV, strength, and grip/waist when follow-up measurements exist. A recommendation that was not followed is not counted as evidence that the recommendation itself failed.

At least four eligible, followed, unconfounded 7-day outcomes for the same calorie action are required before the history can dampen a future step.

### Personal Response Analysis

`75_personal_response_analysis.py` compares qualifying 14-day resistance-training, normal-diet blocks. Personalized associations remain withheld until at least eight comparable blocks exist. Associations are treated as hypothesis-level N=1 evidence, not causal proof.

## Daily Neon health records

- `google_health_nutrition_daily`: one record per day containing Cronometer Health Connect **only**: calories, protein, **total** carbohydrates, and fat. Fitbit web summaries and other nutrition providers are excluded rather than summed. Unlogged days are absent (NULL when joined), not inferred to be fasting/zero intake.
- `google_health_activity_daily`: one record per day for Google Health steps, total calories expended (where available), resting HR, HRV, total sleep and sleep stages. Energy is the derived Google Health `total-calories` daily rollup, not added to active calories again. This source is an estimate, not calorimetry.
- `health_daily_summary`: a read-friendly Neon view joining these daily sources to latest local-calendar-date Withings body composition using Europe/Berlin time. The estimated calorie gap is displayed only when food and expenditure both exist.
- Idempotent UPSERT by date prevents duplicate days and supports corrected values on previously logged days. The daily job rereads 60 completed days. Data removed entirely from Google Health are not automatically deleted from Neon; absence of a new reading must not be treated as proof of a zero.
- Regression tests are in `tests/test_google_health_neon_mirror.py`; they check Cronometer-only selection, 14-day Google Health total calorie windows, and source filtering. CI workflow: `.github/workflows/google_health_mirror_tests.yml`.
- The daily sync uses existing GitHub Actions secrets `GOOGLE_HEALTH_CLIENT_ID`, `GOOGLE_HEALTH_CLIENT_SECRET`, `GOOGLE_HEALTH_REFRESH_TOKEN`, and `WITHINGS_DATABASE_URL`. No user interaction or new credential is required if these existing secrets remain valid.
- A normal meal day appears in the next scheduled sync after the day completes; the current day is never silently interpreted as complete.

## Neutral activity/recovery naming

The historical table `clean.fitbit_daily` remains for compatibility with old scripts and historical backfill. New code/documentation can use the neutral view:

`clean.activity_recovery_daily`

Current rows in the compatibility table are sourced from Google Health where available; the old table name does not imply current Fitbit API use.

## Fasting tools

The historical fasting scripts remain available for explicit on-demand analysis, but they are not part of the automatic weekly coaching path. This keeps useful historical logic without letting fasting dominate routine fat-loss/muscle-preservation coaching.

## Current core scripts

- `scripts/05_refresh_current_sources.py`
- `scripts/12_sync_withings_persistent.py`
- `scripts/15_ingest_hevy_current.py`
- `scripts/16_sync_grip_persistent.py`
- `scripts/18_ingest_google_health.py`
- `scripts/20_build_clean_interventions.py`
- `scripts/21_build_clean_body_composition.py`
- `scripts/22_build_clean_fitbit_daily.py`
- `scripts/23_build_clean_training_summary.py`
- `scripts/24_build_clean_nutrition_daily.py`
- `scripts/25_build_performance_markers.py`
- `scripts/30_build_daily_metrics.py`
- `scripts/31_build_daily_trends.py`
- `scripts/40_build_weekly_metrics.py`
- `scripts/41_build_historical_daily_metrics.py`
- `scripts/71_strength_progress_analysis.py`
- `scripts/72_strength_adjusted_coaching.py`
- `scripts/73_adaptive_calorie_recommendation.py`
- `scripts/74_lean_mass_preservation.py`
- `scripts/75_personal_response_analysis.py`
- `scripts/76_adaptive_coaching_feedback.py`
- `scripts/77_phase_detection.py`
- `scripts/78_cut_stress_guardrail.py`
- `scripts/80_weekly_coaching_report.py`
- `scripts/81_build_weekly_coaching_packet.py`
- `scripts/95_validate_data_freshness.py`
- `scripts/100_run_weekly_coaching_stack.py`
- `scripts/111_build_coaching_summary.py`

## Security / persistence

GitHub Actions secrets contain the current external credentials; secret values are not stored in source files. The weekly workflow persists only the adaptive coaching history CSV, not the refreshed DuckDB database.

The committed DuckDB remains a sanitized historical seed/compatibility database. Historical Git commits can still contain previously deleted material; current production logic does not rely on legacy Fitbit OAuth tokens.

## Validation expectations

A healthy weekly run should show:

- Withings, grip, Google Health, and Hevy refreshes succeeding or an understood supplemental-source limitation;
- core freshness checks passing;
- all coaching stack stages succeeding;
- a current phase report;
- a recovery-guardrail report;
- a phase-aware calorie recommendation;
- adaptive feedback history being updated;
- the email summary surfacing the important coaching decision without requiring the attachment to be opened.
