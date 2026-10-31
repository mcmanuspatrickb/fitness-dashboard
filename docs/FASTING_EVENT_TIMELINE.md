# Fasting + exercise timeline integration (staged)

## Status
- Manual-only Hevy + Google Health event sync on \`.github/workflows/manual_health_event_sync.yml\`.
- Cronometer fasting-history **read-only proof of concept** in \`scripts/20_sync_cronometer_fasts.py\`, **not enabled** by any workflow.
- No recurring jobs, paid services, credentials in git, or changes to existing daily energy / coaching logic.
- Exercise dates are stored as UTC instants and converted to Europe/Berlin for reporting.
- BIA water, fat and lean mass must not be summed as independent compartments.
- Exercise calories must **not** be added to Google Health daily total calories (double counting).

## Running the manual exercise sync
After review/merge to main, use Actions > Manual Health Event Timeline Refresh > Run workflow.

It uses existing secret names: \`HEVY_API_KEY\`, \`GOOGLE_HEALTH_CLIENT_ID\`,
\`GOOGLE_HEALTH_CLIENT_SECRET\`, \`GOOGLE_HEALTH_REFRESH_TOKEN\`, \`WITHINGS_DATABASE_URL\`.

This creates/upserts three tables in the existing private Neon DB:
- \`hevy_workout_sessions\` (id, start/end, title)
- \`hevy_workout_sets\` (weights, repetitions, RPE, set type)
- \`google_health_exercise_sessions\` (activity type, start/end, source, mean HR when present)

No files containing health data are committed or uploaded as workflow artifacts.
Existing rows are upserted by deterministic IDs. A deleted set in Hevy is not yet
removed from Neon, so historical edits should be audited before analysis.
Activities from multiple sources may represent the same real workout; de-duplicate
overlapping sessions in reporting rather than summing their calories.

## Cronometer fasting-history proof of concept
Cronometer's supported CSV exports do not document fasting intervals.
The unofficial mobile API supports a date-range fasting-history read.
The adapter uses only login and retrieval, never delete/edit endpoints.
This is not an official supported interface and may change.

**Do not paste Cronometer passwords or 2FA seeds in chat or commit them.**
For testing, put \`CRONOMETER_USERNAME\` and \`CRONOMETER_PASSWORD\` in
a secure local environment; when adding GitHub Actions later, use encrypted
repository secrets. The optional \`CRONOMETER_TOTP_CODE\` is an ephemeral
6-digit code, not a stored authenticator seed.

Probe without exporting values:

\`\`\`bash
python scripts/20_sync_cronometer_fasts.py --days 30
\`\`\`

This prints only top-level field names and list counts. Inspect and
validate a real sample schema **privately** before enabling
\`--sync\`. Once validated, sync writes only ID/start/end/name to
\`cronometer_fasting_intervals\` in private Neon.

The adapter intentionally fails for unknown timestamp encodings,
naive datetimes, and malformed records, rather than guessing timestamps.
Timezone is passed as null during login so the call does not overwrite
the account's timezone. Sessions are not cached; avoid repeated logins
because Cronometer rate-limits authentication.

## Explicitly not done
- Real Cronometer login and timestamp validation (credentials unavailable).
- Production activation of Cronometer fast history ingestion.
- Any automatic schedule change or paid hosting.
- Merging this branch into main until the event import is validated.
- Claims that October 27/30 Hevy sets have been read before a successful sync.
