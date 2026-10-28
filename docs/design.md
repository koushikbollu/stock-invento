# Design, correctness, and recovery

## Processing flow

Catalog files define known item and location identifiers. A movement batch is validated against the exact input schema and those references. The pipeline records source file, row number, run identifier, normalized event version, and a row outcome so an operator can trace rejected and accepted data.

Accepted event versions are immutable. A current-event view chooses the greatest revision for every event identifier. Each non-void current event expands into one posting for a receipt, issue, or adjustment, or two postings for a transfer. Daily aggregation then publishes the opening, movement components, and closing quantity for every day of each item/location series. Before publication, the pipeline compares the prior daily rows with the replacement rows and persists every business-value change for that successful run.

The business grain is one event version at ingestion, one event leg in postings, and one `(balance_date, item_id, location_id)` in daily balances. A run is an operational attempt, so rerunning the same file intentionally creates a new run record while leaving current stock unchanged.

## Why these choices

| Choice | Benefit | Cost or limitation |
| --- | --- | --- |
| Python standard library | Easy clean-environment execution without dependency installation | Fewer conveniences than a dataframe or orchestration framework |
| SQLite | Transactional local storage and ordinary SQL inspection | One writer; unsuitable as a distributed processing engine |
| Integer thousandths | Exact quantities and deterministic reconciliation | At most three fractional digits; no unit conversions |
| Immutable full event revisions | Auditable corrections and arrival-order independence | Sources must supply stable identifiers and explicit revisions |
| Full rebuild after ingestion | Handles changed item, location, date, type, quantity, or cancellation consistently | Work grows with all current events and the item/location/date grid |
| Quarantine invalid individual rows | Good data can publish while bad data stays visible | Operators must inspect reject metrics and exit code `2` |
| Local dashboard import | Preview, explicit import, and the same validated ingestion path as the CLI | The local server needs guarded write endpoints; it is not a hosted application |
| Persisted daily changes | Exact before/after correction evidence, including added and removed rows | Storage grows with the number of changed daily rows across runs |

An indexed incremental implementation could find both old and new affected item/location keys, determine the earliest impacted date, retain the preceding closing balance, and rebuild forward through the published horizon. That optimization should be verified against the full rebuild as an oracle, especially for transfers, voids, and changes of key or date.

## Correction semantics

`(event_id, revision)` is unique. The same normalized payload with the same key is a safe duplicate. A conflicting payload under that key is rejected rather than silently overwriting history. Revision numbers need not arrive consecutively: revision 3 can arrive before revision 2, and revision 3 remains current.

A higher revision replaces the full prior event; it is not a quantity delta. A void version removes the event's current contribution but preserves its history. To restore a voided event, submit another higher, non-void version. A replacement can change the effective date, item, location, destination, movement type, or quantity. Rebuilding from the current view removes obsolete postings and recalculates all downstream balances.

The distinction between effective date and processing time is deliberate. A late event affects its business date even though its ingestion timestamp is later. Corrections retain both histories.

## Before/after impact history

The change grain is one successful run and one item/location/business date. A change record stores nullable before and after snapshots and an exact closing delta in integer thousandths. A missing before row means an addition; a missing after row means a removal. Each present snapshot contains the seven exact three-decimal quantity strings; null encodes an absent row. The comparison excludes `last_run_id` and other publication lineage.

`closing_delta_milli` is stored as decimal integer text. Two individually valid signed 64-bit balances can have a difference wider than signed 64-bit, so Python integer arithmetic computes the difference and text preserves it without float conversion or overflow.

An initial load therefore records added rows. A backdated correction records both its immediate impact and any later daily opening/closing changes. A change of date or location can add or remove rows. A run that merely changes lineage by replaying identical business data records no changes. The operational run itself is still retained.

The change rows commit in the same transaction as the target publication. A failed or rolled-back run retains no successful before/after changes. `runs.impact_recorded` is set to `1` when a successful run's comparison was captured, including a zero-change replay. It is `0` for unsuccessful runs and legacy runs. Existing runs created before this feature was introduced have no captured snapshots; an empty result for such a run is not proof that it originally changed nothing.

The correction view requests change rows in pages of at most 500 so the browser need not load an entire large change history at once. The API's `has_snapshot` flag distinguishes a retained zero-change comparison from unavailable legacy history. A closing delta is meaningful for the selected item, location, and day. Summing days double-counts carried inventory; combining different item units is not a meaningful inventory total.

Change retention adds audit storage. This implementation keeps captured changes rather than applying an automatic purge policy. A production retention or archival policy should be chosen alongside business audit requirements.

## Browser import workflow

The dashboard previews the first six physical lines of a selected CSV, then sends its filename, CSV text, and optional reporting horizon only when the operator chooses **Import & publish**. The preview does not publish data or replace server-side validation. The server ingests the complete uploaded movement content through the same pipeline as a CLI file, including source lineage, duplicate checks, quarantine, run summaries, rollback, reconciliation, and persisted changes. Each CSV is limited to 10 MiB, with a 32 MiB JSON request limit; the CLI handles larger files.

Item and location catalog uploads are an optional separate atomic operation. Both catalogs must validate before that operation commits; a later movement failure does not undo an earlier catalog addition. Unknown movement references remain invalid until their catalogs have been added. Existing units cannot be changed through an upload.

The server binds to loopback. Protected HTTP data routes require the local admin login; POST requests additionally require the matching `Origin`, JSON content, and `X-Stockline-Token`. The login form first obtains its own short-lived token from `GET /api/login-session`; authenticated requests obtain the session token from `GET /api/session`. A concurrent browser import receives a busy response rather than starting another browser write at the same time.

## Local username/password authentication

The supplied demonstration credentials are `admin` / `admin123`. On first web use, each workspace stores its own 32-byte random salt and PBKDF2-HMAC-SHA256 password hash with 600,000 iterations in `web_users`. The database does not store the plaintext password. Existing workspace hashes are preserved on later startup, including a password changed by the local owner. No external identity provider or internet account is involved.

Successful login rotates to a new opaque server-side session and consumes the pre-login session. Browser cookies are port-specific, `HttpOnly`, `SameSite=Strict`, and scoped to `/`; the authenticated cookie has an eight-hour maximum age. The server expires a session after thirty minutes without activity or eight hours from creation. Logout revokes the current session, and restarting the server invalidates all in-memory sessions. Login preparation expires after ten minutes.

After five failed credential checks from the same client in a rolling sixty-second window, subsequent login attempts receive HTTP 429 with `Retry-After`. Incorrect usernames/passwords use a generic response. Authentication state, throttling, and inventory run audits are separate: a failed sign-in does not create an inventory movement attempt.

The implementation references selected practices described in the [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). This is a local demonstration design, not a claim of full OWASP compliance or production readiness. It uses plain loopback HTTP, so the cookies do not have the HTTPS-only `Secure` attribute.

The login protects HTTP access. Local files and CLI commands remain accessible to the operating-system user; it does not encrypt the SQLite database or establish multi-user roles. The defaults are intentionally shared in the package. To change the local admin password, use `python3 -m inventory set-password --db var/demo/inventory.db` from the project root, enter and confirm an 8–1024-character password at the hidden prompts, then restart the server to revoke existing sessions. Substitute the selected workspace database path. The CLI does not reset inventory or print the chosen password.

## Invariants and reconciliation

1. Every item and location reference is present in its catalog.
2. A current non-transfer event contributes one posting; a transfer contributes two linked legs.
3. Transfer-in and transfer-out quantities agree, so transfers preserve inventory across locations for the same item.
4. Every daily row satisfies `closing = opening + receipts - issues + transfers_in - transfers_out + adjustments`.
5. A series' opening equals the preceding day's closing, and gap days carry quantities forward.
6. Current source movement totals reconcile with posting totals at their date/item/location grain and each item's final stock across locations. Voided and superseded versions are excluded from current totals. The cross-item arithmetic checksum is not a physical sum of different catalog units.
7. Rerunning an identical batch does not multiply current events, postings, or balances.
8. Run input counts are explained by accepted, duplicate, rejected, and, on a failed publication, rolled-back outcomes.

Negative stock is a visible warning rather than an invariant failure. The system cannot infer whether an oversold balance is a source timing issue, an operational error, or permitted business behavior.

## Failure, retry, and restart

The pipeline records the attempt before ingestion. Inventory changes, derived publication, and new before/after change rows occur together in a SQLite transaction. A fatal error rolls back newly accepted versions, the replacement publication, and its change rows, preserving the previously published inventory state. Failure metadata and row outcomes remain available for diagnosis.

After a failed attempt, correct the file or operational cause and rerun the same input. Already committed versions from earlier attempts are duplicates; rolled-back versions can be accepted on retry. A crash or process termination must not leave a half-published ledger because SQLite commits atomically. An interrupted run record can remain unfinished and should be investigated rather than treated as a successful load.

Header-only input is a valid empty batch. A malformed header, unexpected schema, unreadable file, or fatal storage/publication error fails the batch. A malformed individual record is quarantined with its row number and reason. A source may therefore fix rejected rows and submit them again with their original version keys if no valid version was committed for those keys.

Backfill uses the normal `run` command with older effective dates or higher correction revisions. No special destructive repair command is required. The publication horizon does not shrink when a later run supplies an earlier `--through` date.

## Operational boundaries

Business dates are source-provided dates. Operational times use UTC ISO-8601 format. Quantities have a documented upper bound, avoiding unbounded values that could threaten storage or aggregate arithmetic. Catalog identifiers are stable and consistent across inputs; changing an existing item's unit is not an implicit conversion.

The server binds to loopback and exposes reports plus guarded local CSV import operations. It is intended for trusted local data, not public hosting. The supplied data is synthetic and requires no external credentials. Keep real operational or personal data out of any shared ZIP, evidence export, or later public repository.

## Performance measurement

Generate a reproducible batch with a fixed seed, ingest it into a fresh database, and retain the run summary with input count, duration, accepted/rejected/duplicate counts, current-event count, posting count, and daily-output count. Report hardware and Python version with the measurement. A count of 100,000 source rows is distinct from 100,000 accepted unique events because the generator deliberately includes duplicate and invalid scenarios.

The full rebuild is approximately linear in current events plus generated daily rows, with sorting/indexing overhead. Long date horizons and many item/location combinations can produce more output rows than source rows. Partitioning and rebuilding affected keys are reasonable next steps; distributed infrastructure is unnecessary until measured workload demands it.

The generator independently varies items, movement types, and locations rather than letting one cycling field determine another. Its 100,000-row workload covers all four movement types for every item; a separate `coverage.json` reports actual coverage and is not consumed as source data.

The supplied [performance evidence](../evidence/performance.json) identifies the measured row count, environment, observed counts, reconciliation results, and replay check. Hardware, cache, date horizon, output grain, and the additional change audit affect timing. A measurement from the previous generator or feature set is not a direct performance comparison with version 1.1.

The recorded version 1.1 execution used 100,000 source rows and took 4.60 seconds externally on arm64 macOS/Python 3.14.6. It produced 71,839 daily rows and retained their initial additions as change records. Replay preserved the business balances and retained zero new changes. The [coverage report](../evidence/generator-coverage.json) confirms all four movement types and all eight source locations for each of the 100 items, based on new revision-1 rows rather than duplicates or invalid records.

The dashboard's Achievements & verification section reads recorded evidence. Its current-ledger metrics describe the open database; benchmark metrics describe the saved workload; capability descriptions explain implemented behavior. These are labeled separately so a small sample, a benchmark, and a feature claim do not appear to be interchangeable evidence.

## Rigorous verification refinements

Runs with identical millisecond timestamps use audit insertion order as the
shared report/latest-comparison tie-break. Daily equation reconciliation uses
Python integers so offsetting movements near SQLite's signed-integer boundary
cannot cause an intermediate expression to become a rounded real number.
Both behaviors have regression tests in `tests/test_resilience_acceptance.py`.
The [test report](test-report.md) and [scenario matrix](test-scenarios.md) explain
the executed acceptance, recovery, concurrency, and performance checks.

## Applied lookup indexes

`balances_account_date(item_id, location_id, balance_date)` supports the
correlated continuity, first-day, and latest-balance lookups at the ledger
series grain. The final review's `EXPLAIN QUERY PLAN` confirmed a covering-index
search for the first-day reconciliation subquery; see
[the recorded plan](../evidence/final-review/index-plan.txt).
`postings_grain(item_id, location_id, effective_date)` also defines the intended
item/location/date access path for posting inspection. These indexes are
implemented. No index-on/index-off benchmark was run, so no measured speedup is
claimed. Rebuilding only affected series/date partitions remains a proposed
next optimization rather than an implemented incremental pipeline.
