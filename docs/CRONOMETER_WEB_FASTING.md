# Cronometer web fasting history → Neon (manual-only)

## Status (2026-10-31)

The initial live read-only web fetch and Neon upsert passed:
- Cronometer web GWT getUserFasts returned 8 fasting sessions.
- The web range operation also returned 8 records for Oct 20–Nov 1.
- GWT 64-bit longs decoded to valid UTC epoch milliseconds.
- Four start/end pairs independently matched user-supplied Cronometer screenshots within five minutes.
- All 8 records had unique IDs and were written to the private Neon table cronometer_fasting_intervals.
- Direct Neon queries verified 8 records with local dates from Oct 21–31.
- No Cronometer data was edited or deleted.

The earlier mobile probe (scripts/20_sync_cronometer_fasts.py) is intentionally left disabled: it returned an empty fasting list despite positive stats.

## Manual sync

Open Actions → Manual Cronometer Web Fasting Sync → Run workflow (main).
Workflow: .github/workflows/manual_cronometer_web_sync.yml.

The workflow:
1. Installs pinned upstream reader cphoskins/cronometer-mcp@0f11757011f8e9a94e5ae3572cfe7cdeff419d7d (unofficial GWT API).
2. Runs fictional-only timestamp parsing tests.
3. Uses existing repository secrets CRONOMETER_USERNAME or CRONOMETER_EMAIL, CRONOMETER_PASSWORD, and WITHINGS_DATABASE_URL.
4. Calls only get_user_fasts; never edits Cronometer.
5. Strictly validates decoded timestamps, unique IDs, durations and active/completed status.
6. Idempotently upserts fasting intervals into private Neon by Cronometer fast ID.
7. Does not upload health data artifacts or log individual fasting records.

Upstream cookies are stored only in the ephemeral GitHub runner and aren't uploaded. Never paste credentials in chat, code or GitHub Actions logs.

## Reporting rules

- Store timestamps as TIMESTAMPTZ; query with AT TIME ZONE 'Europe/Berlin' for local time.
- The October 25 DST fall-back adds one elapsed hour to the fast spanning Oct 24–26.
- Fast intervals span calendar days; do not infer intervals from absent food logs.
- Do not double-count calories already in Google Health daily expenditure.
- Exercise records are persisted separately in hevy_workout_sessions, hevy_workout_sets, and google_health_exercise_sessions.
- Deleted fasting records are NOT automatically removed from Neon to avoid destructive inferences after partial API results. Reconcile explicitly if needed.
- If the unofficial GWT API changes, fail closed instead of importing unknown timestamps.
- No new paid hosting or recurring schedule; manually refresh for occasional reporting.
