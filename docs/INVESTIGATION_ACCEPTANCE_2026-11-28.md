# Investigation and feedback acceptance, 2026-11-28

## Scope

This is acceptance evidence for the TG-T06 investigation slice, covering the event-review, case-correlation and replay-impact portions of E-09 and E-10. Validation ran a native FastAPI process, React development server and disposable PostgreSQL 16 database. A separate unseeded PostgreSQL database handled regression tests. No historical data volume or real telecom service participated.

## Paired replay

The authenticated `POST /api/scenarios/generate` API processed **300 synthetic events** with seed **8331** through the existing scoring path. PostgreSQL recorded **300 events, 300 predictions, 66 incidents and 205 unique alert links**. The authenticated `GET /api/analytics/impact?review_budget=25` API replayed the same stored events and scores under both incident policies. Correlation used the default operating threshold and bounds, including a 120-minute anchor lookback.

| Measure | One alert per event | Correlated |
|---|---:|---:|
| Investigations | 205 | 66 |
| Cases per 1,000 scored events | 683.33 | 220.00 |
| Detected synthetic episodes | 68 of 68 | 68 of 68 |
| Distinct synthetic episodes at a 25-case budget | 16 | 26 |
| Precision at a 25-case budget with known outcomes | 25 of 25 | 25 of 25 |
| Confirmed false-positive cases | 1 | 1 |
| Cases spanning multiple labeled episodes | 0 | 6 |
| Median synthetic seconds to first alert | 0 | 0 |

This replay yielded **67.80% fewer investigations**. Six correlated cases linked more than one synthetic subscriber/family episode, which is an observed consolidation trade-off. Episode IDs in this comparison are based on source dataset, subscriber, scenario family and time gap. They cannot establish whether two subscribers belong to the same outside campaign. The replay produced zero resolved cases, so duration appeared as unavailable. The small scenario replay is operational demonstration evidence for synthetic inputs. Independent real-world performance remains unverified.

## Test commands

- `py -3.11 -m alembic upgrade head` and `py -3.11 -m alembic current` against a new PostgreSQL 16 database. Migrations ran from the original schema through `0010_investigations (head)`.
- `py -3.11 -m pytest -q tests/test_investigations.py` passed all six tests against a fresh migrated PostgreSQL database by setting `TG_CASE_TEST_DATABASE_URL`. It covers transaction-backed correlation, correlation bounds, review correction/provenance, case merge reversal, risk-stratified sampling and concurrent case creation.
- `py -3.11 -m ruff check app/investigations.py tests/test_investigations.py migrations/versions/0010_investigations.py` passed.
- `npm run build` passed. Vite warned about the existing main chunk size.
- `npm run test:e2e -- e2e/investigations.spec.ts` passed against the seeded native stack. The browser authenticated, loaded measured replay impact, opened a persisted case timeline, recorded an adjudication and loaded the feedback sample. The first run surfaced an ambiguous column selector, which was fixed using the exact column name.

For reproduction on an isolated seeded stack, set the documented browser test credentials and base URL. For PostgreSQL regression set the URL of an empty disposable database, migrate it and run the narrow suite with no application server writing to that same database.

## Larger paired replay and resolution follow-up — 2026-11-28

The copied PostgreSQL acceptance data was re-evaluated through the same `replay_impact` path used by `/api/analytics/impact`, capped to its most recent 10,000 scored events and review budget 100. Current aggregate output is preserved in [incident-impact-2026-11-28.json](evidence/incident-impact-2026-11-28.json): 5,054 events crossed the alert threshold; correlated grouping yielded 4,520 investigations (10.57% reduction), detected 49 of 80 known synthetic episodes, missed 31, and reported 419 correlated false-positive cases plus 4,052 unlabeled cases. Precision at budget 100 was 0.4706. One reviewed synthetic case was resolved in 187.94 seconds. The sample was truncated to the endpoint's 10,000-event bound. This latest result is less favorable than the earlier 300-event paired replay; it exposes recall/workload trade-offs and does not establish real-world effectiveness.
