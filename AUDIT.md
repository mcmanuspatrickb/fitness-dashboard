# fitness-dashboard audit

Audit date: 2026-09-18

## Executive summary

This repository is still useful as a **scheduled analytics and coaching engine**, but its original ingestion layer had aged out. The September 2026 GitHub Actions runs were rebuilding analytics from a DuckDB snapshot whose current health/nutrition data ended in March 2026. The scheduled workflow also failed in `110_build_coaching_summary.py` because it called `pandas.io.common.escape`, which is not available in the pinned Pandas 3.0.1.

The scheduled path has now been modernized around the same source-of-truth choices used by the current Health_Dashboard:

- **Withings:** direct Withings measurements from the persistent Withings database.
- **Google Health:** steps, recovery, sleep, and Cronometer nutrition.
- **Hevy:** current paginated workout API.
- **DuckDB:** retained as the local analytics/compatibility layer for this repository.

The old Fitbit, direct Withings OAuth, and Cronometer browser-automation code remains in the repository for historical reference/manual use, but it is no longer part of the scheduled weekly workflow.

## Root causes of the old weekly failure

1. `scripts/110_build_coaching_summary.py` used `pd.io.common.escape(...)`. Pandas 3.0.1 has no such function, so the summary step failed with `AttributeError`.
2. `scripts/100_run_weekly_coaching_stack.py` rebuilt only clean/analytics/report layers. It did not refresh external source data first.
3. The scheduled database therefore remained stale even though report generation itself continued to run.
4. The old workflow installed the full dependency set plus Playwright browsers even though the weekly coaching stack did not actually refresh Cronometer through that path.
5. The old stack runner recorded failed child scripts but still exited with status 0, which could hide internal failures.
6. A Cronometer browser storage-state file was tracked in Git. It has been removed from the current branch and `secrets/` is now ignored.

## Current scheduled architecture

The Monday workflow now runs in this order:

1. Install the lightweight weekly dependency set.
2. Refresh configured current sources with `05_refresh_current_sources.py`.
3. Rebuild clean tables and analytics with `100_run_weekly_coaching_stack.py`.
4. Validate freshness with `95_validate_data_freshness.py`.
5. Build the email body with `111_build_coaching_summary.py`.
6. Upload report artifacts.
7. Email the weekly summary plus diagnostics.

A source without configured GitHub Actions secrets is marked **SKIPPED**, not silently treated as current. Freshness is then assessed separately, so the email can report `FRESH`, `PARTIAL`, or `STALE`.

## Keep: scheduled/core

These files are useful in the current weekly system:

- `scripts/05_refresh_current_sources.py` — current-source orchestrator.
- `scripts/12_sync_withings_persistent.py` — current direct Withings data from persistent database.
- `scripts/15_ingest_hevy_current.py` — current paginated Hevy ingestion.
- `scripts/18_ingest_google_health.py` — Google Health activity/recovery/sleep and Cronometer nutrition.
- `scripts/20_build_clean_interventions.py`
- `scripts/21_build_clean_body_composition.py`
- `scripts/22_build_clean_fitbit_daily.py` — compatibility table; current rows may be sourced from Google Health despite the legacy name.
- `scripts/23_build_clean_training_summary.py`
- `scripts/24_build_clean_nutrition_daily.py`
- `scripts/30_build_daily_metrics.py`
- `scripts/31_build_daily_trends.py`
- `scripts/40_build_weekly_metrics.py`
- `scripts/41_build_historical_daily_metrics.py`
- `scripts/71_strength_progress_analysis.py`
- `scripts/72_strength_adjusted_coaching.py`
- `scripts/73_adaptive_calorie_recommendation.py`
- `scripts/80_weekly_coaching_report.py`
- `scripts/81_build_weekly_coaching_packet.py`
- `scripts/90_export_data_audit_snapshot.py`
- `scripts/95_validate_data_freshness.py`
- `scripts/100_run_weekly_coaching_stack.py`
- `scripts/111_build_coaching_summary.py`

## Keep: useful but primarily on-demand/historical

These analyses can still be valuable, but should not be treated as always-current weekly signals unless their inputs are fresh and the specific analysis is wanted:

- `42_historical_fasting_comparison.py`
- `43_identify_fasting_blocks.py`
- `44_filtered_fasting_blocks.py`
- `45_block_bodycomp_analysis.py`
- `46_block_bodycomp_quality.py`
- `47_fat_loss_efficiency.py`
- `48_estimate_tdee_blocks.py`
- `52_generate_intervention_insights.py`
- `60_fasting_effectiveness_analysis.py`
- `61_extended_fast_block_analysis.py`
- `62_post_fast_recovery_analysis.py`
- `63_pre_fast_prep_analysis.py`
- `64_optimal_fast_playbook_generator.py`
- `65_pre_fast_readiness_check.py`
- `66_should_i_break_fast_early.py`
- `67_audit_nutrition_pipeline.py`
- `70_should_i_fast.py`

The current weekly stack still runs `70_should_i_fast.py` because it was part of the existing coaching packet. A future cleanup can move all fasting-specific recommendations to an explicitly on-demand workflow if desired.

## Legacy/replaced ingestion paths

These are no longer the preferred current-data route:

- `11_withings_oauth.py` and `12_ingest_withings_history.py` — replaced for scheduled use by the persistent Withings database.
- `13_fitbit_oauth.py` and `14_ingest_fitbit_daily.py` — replaced for scheduled use by Google Health.
- Fitbit historical import scripts — preserve only for historical backfill/reference.
- `15_ingest_hevy.py` — replaced for scheduled use by `15_ingest_hevy_current.py`.
- `61_cronometer_export.py` — browser automation no longer needed for scheduled nutrition because Cronometer arrives through Google Health.
- `62_import_cronometer_export.py` — keep only for manual historical imports if needed.
- MFP import scripts — historical only.
- `110_build_coaching_summary.py` — retired from the scheduled workflow; replaced by `111_build_coaching_summary.py`.

## One-time migration/setup scripts

The early numbered schema/setup scripts are mostly migration history. Keep them while the existing DuckDB is still the compatibility layer, but they should not be part of the normal weekly run.

## Cleanup candidates

Safe candidates for later deletion after one or two successful weekly runs:

- `scripts/temp_fitbit.py`
- `scripts/test_google_sheets.py`
- historical tracked `logs/`
- duplicate `.github/workflows/requirements.txt`
- retired `scripts/110_build_coaching_summary.py`

The committed `db/fitness.duckdb` is currently acting as a historical seed database. The workflow refreshes recent source data into the runner's copy before analysis; it does not need to commit the modified database back to Git.

## Security notes

- `secrets/cronometer_storage_state.json` has been removed from the current branch.
- `.gitignore` now excludes `secrets/`, `private/`, `.env`, and DuckDB sidecar files.
- Removing a secret/session file from the current branch does **not** erase it from Git history. If the old browser session or any tokens are still reusable, rotate/revoke them; a history rewrite can be done later if desired.
- The tracked DuckDB may contain legacy OAuth token tables from the old architecture. The modern weekly workflow does not depend on those old tokens. Sanitizing the historical database is a separate cleanup task.

## Required GitHub Actions secrets for the modern weekly workflow

Email:

- `EMAIL_USER`
- `EMAIL_PASSWORD`
- `EMAIL_TO`

Current data sources:

- `WITHINGS_DATABASE_URL`
- `GOOGLE_HEALTH_CLIENT_ID`
- `GOOGLE_HEALTH_CLIENT_SECRET`
- `GOOGLE_HEALTH_REFRESH_TOKEN`
- `HEVY_API_KEY`

Do not store these values in source files.

## Validation checklist

Before considering the migration complete:

1. Configure the current-source Actions secrets.
2. Manually run **Weekly Coaching Pipeline** once from GitHub Actions.
3. Confirm `source_refresh_status.txt` shows the intended sources as `SUCCESS`.
4. Confirm `data_freshness.txt` reports sensible recent dates.
5. Confirm the email subject reports `FRESH` or an understood `PARTIAL` state.
6. Check that the emailed metrics match the current Health_Dashboard for the same dates.
7. After one or two successful weeks, remove the cleanup candidates listed above.
