# Coaching evidence safeguards — isolated development, not deployed

**Scope:** fitness-dashboard and Health_Dashboard branches named
`feature/coaching-evidence-safeguards-20261101`.
No production workflow configuration, stored coaching state or live data is
changed simply by creating these branches.

## Data contracts

- Cronometer fast intervals are read with a **SELECT** from the existing
  `cronometer_fasting_intervals` table in private Neon. The manual upstream sync
  remains separately controlled; these changes **do not** invoke it.
- `fetch_intervals()` fails closed with `UNAVAILABLE`; a missing record does
  not establish an eating day. All time intervals are UTC-aware and split
  into Europe/Berlin calendar days, including DST transitions.
- A verified fast lasting at least 24 hours, plus the next 24 hours of
  refeeding, confounds short-term energy-response interpretation. Ordinary
  intermittent fasting is tracked separately, rather than classified as a
  multi-day fast. Historical legacy intervention labels remain in the
  personal-response calculation; old unobserved periods have limited
  historical certainty.
- No inference of fasting from missing nutrition entries; no duplicate
  calorie expenditure; no automatic deletion of manually imported history.

## Model outputs

- `fasting.evidence_quality` may be `FASTING_CONFOUNDED`,
  `LIMITED_HISTORY` or `UNKNOWN`.
- `energy.stability` remains the older 28/42-day **agreement** label.
  `energy.confidence` explicitly notes overlapping-window uncertainty;
  agreement must not be presented as independent accuracy confirmation.
- `decision.review_required` and `decision.actionable` separate the
  generated operational target from a cleared recommendation; a review
  flag means the target is **provisional, not automatically actionable**.
  Neither the requested adjustment nor the operational target is silently
  recalculated by this reporting guard.
- `adaptive_feedback_revisions.csv` receives an append-only revision row
  only when a previously evaluated status/confounding flag changes.
  Pending states can be evaluated again as evidence arrives.
- Training dose counts resistance sets as a transparent, primary-muscle
  heuristic; it does not equate jumps/mobility to hypertrophy working sets.

## Canonical consistency

The weekly email renders the same canonical JSON that the Streamlit app loads
from `coaching_snapshots`. Streamlit independently labels the snapshot's
analysis and generation dates; *live charts remain exploratory*. The two
maintenance numbers have different provenance, not competing authoritative
coaching decisions.

## QA before merge/deploy

1. Run fictional-only offline `unittest` suites for timestamp/DST handling,
   extended fast/refeeding, uncertain sources, 14-day blocks, delayed feedback
   reassessment/idempotence, muscle mapping and email actionability.
2. Test Streamlit freshness with an artificial old canonical snapshot; ensure
   the payload itself does not change.
3. Review the **branch diffs** and run the weekly report in a sandbox with
   dummy credentials and fake records. Do not run the real weekly pipeline
   against the production Neon database before approval.
4. Validate after deployment approval that weekly email and Streamlit show
   identical analysis dates, states, decisions and review flags.
5. **Do not merge, deploy, enable additional schedules, or alter live calorie
   settings without separate user approval.**

## Limits requiring future review

- Manual Cronometer synchronization is not continuous. No intervals in a
  historical 14-day window do **not** prove the window was fasting-free.
  The existing 12-block personal-association threshold stays in place; its
  underlying historical evidence needs verification before automated
  influence is enabled.
- TDEE estimation still applies a 7,700 kcal/kg slope assumption. New evidence
  flags identify potential fasting bias; this branch does not claim a precise
  causal correction for water/glycogen or prescribe an adjusted calorie target.
- A stale or missing fasting sync produces a review-required recommendation.
  This conservative guard is intentional and should be evaluated before any
  production deployment.
