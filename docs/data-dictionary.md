# Data dictionary

Names use `snake_case`. Business IDs come from source data. Event revision keys and posting leg IDs are deterministic; `run_id` identifies a particular processing attempt and is intentionally different for a retry. Daily-balance CSV and report quantities are exact decimal strings with three places. Quantity columns ending in `_milli` contain signed integer thousandths of the item's catalog unit, including in event-version and posting audit exports.

## Source CSVs

All files use UTF-8 CSV with a header; a UTF-8 byte-order mark is accepted. The set of movement columns must match the documented schema exactly; their order may vary. Surrounding field whitespace is removed. Empty strings are missing values except for the permitted blank destination.

Identifiers and catalog units contain 1–64 characters, begin with a letter or digit, and then use letters, digits, underscore, period, colon, or hyphen. Movement types are case sensitive; boolean text is case insensitive. Quantities use ordinary decimal notation, without an exponent or a leading plus sign.

### Items: one row per inventory item

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `item_id` | String | Yes | Stable unique item key |
| `unit` | String | Yes | Nonempty unit identifier; one unit per item; no conversion |

### Locations: one row per inventory location

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `location_id` | String | Yes | Stable unique location key |

Catalog rows establish referential integrity before movements are loaded. An existing item cannot silently acquire a different unit.

### Movements: one row per full event revision

| Field | Type | Required | Rule |
| --- | --- | --- | --- |
| `event_id` | String | Yes | Stable event key; shared by all revisions of an event |
| `revision` | Integer | Yes | Positive, at most nine digits; combined with `event_id` forms the immutable version key |
| `effective_date` | Date | Yes | Strict ISO `YYYY-MM-DD`; independent of ingestion time |
| `movement_type` | Enum | Yes | `RECEIPT`, `ISSUE`, `TRANSFER`, or `ADJUSTMENT` |
| `item_id` | String | Yes | Foreign key to items |
| `location_id` | String | Yes | Source/owning location; foreign key to locations |
| `to_location_id` | String | Transfer only | Known, distinct location for transfers; blank otherwise |
| `quantity` | Decimal text | Yes | Nonzero, at most three decimal places, absolute value ≤ 1,000,000,000; positive except signed adjustments |
| `is_void` | Boolean text | Yes | `true` or `false`, case insensitive; a void version still carries a full valid payload |

Expected-answer labels and manually calculated balances belong outside these source files so validation does not accidentally consume its own answer.

## Persistent and derived data

### `items` and `locations`

Catalog grains and keys match their CSV definitions. They are referenced by event versions and postings. A quantity is meaningful only with its item and catalog unit.

### `settings`: persisted configuration and demo checkpoints

`key` is unique and `value` is required text. `published_through` stores the ISO business date of the publication horizon so a later run cannot accidentally shorten it.

`demo_examples_v1` stores JSON metadata after the teaching scenarios complete and recover successfully. It records their real run identifiers so the interface can open the actual audit and impact records. Later normal startup reads the marker and skips extra scenario seeding, preserving existing user events and avoiding repeated quarantine examples. The marker does not suppress ordinary audit records from manual imports.

The private `demo_examples_v1_progress` checkpoint tracks owned scenario intents and committed run identifiers during setup, allowing restart recovery without treating unrelated user imports as demo runs. It is operational metadata, not a movement source or expected-answer label.

### `web_users`: local HTTP account credentials

This table is created when local web authentication is initialized, or by the password-change command. The supported account is `admin`; its new-workspace demonstration password is `admin123`.

| Field | Storage/type | Meaning |
| --- | --- | --- |
| `username` | Required text primary key | Local account name, currently `admin` |
| `salt` | Required BLOB | Per-workspace random 32-byte salt |
| `password_hash` | Required BLOB | PBKDF2-HMAC-SHA256 derived password value, not plaintext |
| `iterations` | Required integer | Hash work factor, currently `600000` |

Existing credential records are retained across startup. Login sessions and failure-window counters exist only in server memory, not this table. Full SQLite backups retain the workspace password hash; analysis exports do not export `web_users` or session cookies. No generated credential database or session cookie is included in the source ZIP.

### `runs`: one row per processing attempt

| Field | Meaning |
| --- | --- |
| `run_id` | Unique attempt identifier; links row outcomes and published lineage |
| `source_file` | Source path/name used for this attempt |
| `started_at`, `finished_at` | UTC ISO-8601 processing timestamps; an unfinished attempt may have no finish time |
| `status` | Processing state, including `succeeded`, `succeeded_with_rejects`, or `failed` |
| `input_count` | Number of source data records encountered, excluding the header |
| `accepted_count` | Newly persisted valid versions in this attempt |
| `duplicate_count` | Identical previously known normalized versions ignored |
| `rejected_count` | Invalid records retained in quarantine |
| `rolled_back_count` | Otherwise valid new records not published because the attempt failed |
| `output_count` | Published daily rows attributed to the completed attempt |
| `duration_ms` | Measured attempt duration, in milliseconds |
| `error` | Fatal failure reason, when present |
| `published_through` | Inclusive publication horizon for a successful attempt |
| `impact_recorded` | `1` when a successful before/after comparison was captured, including zero-change runs; `0` for unsuccessful or legacy runs |

### `raw_records`: one source row outcome per run and row number

The `(run_id, row_number)` key identifies a specific input occurrence. The row number is the physical ending CSV line, including the header and any multiline fields. `raw_json` preserves its source values. `outcome` distinguishes accepted, duplicate, rejected, and rolled-back records. `reason` explains a rejection or failure outcome. `source_file` records the source basename. This table is an audit record; it is not counted as current inventory.

### `movement_versions`: one immutable event revision

The primary key is `(event_id, revision)`. Business fields match the normalized movement contract, with `quantity_milli` replacing decimal text. `run_id`, `source_file`, and `row_number` identify the ingestion origin. Normalized payload content enables semantic duplicate detection. Neither a later correction nor a replay deletes prior valid versions.

### `current_movements`: greatest valid revision per event

This view selects one version per `event_id`, using maximum revision rather than latest arrival timestamp. It includes voided current versions for auditability; voided events generate no inventory postings.

### `postings`: one current event leg

Each non-void receipt, issue, or adjustment has one posting. A transfer has a source leg and a destination leg linked to the same event version. Posting identifiers derive deterministically from the event version and leg. Fields identify effective date, item, location, event revision, and the relevant movement component in integer thousandths. Postings are rebuilt from current events and can be reproduced from immutable history.

### `daily_balances`: one item/location/business date

The primary key is `(balance_date, item_id, location_id)`. All quantity columns use `_milli` internally; exports omit that suffix and format decimal strings.

| Export field | Meaning |
| --- | --- |
| `balance_date` | Effective business date |
| `item_id`, `location_id` | Catalog references defining the inventory series |
| `opening` | Previous day's closing; zero before the first movement |
| `receipts` | Positive receipt quantity on this day |
| `issues` | Positive issue magnitude, subtracted from stock |
| `transfers_in` | Positive quantity arriving from other locations |
| `transfers_out` | Positive quantity leaving for other locations |
| `adjustments` | Signed change from adjustment events |
| `closing` | Derived daily closing quantity |
| `is_negative` | Whether closing stock is below zero; a review warning |
| `last_run_id` | Publication lineage, where exposed |

Every date between a series' first current posting and the publication horizon is materialized. The horizon carries forward across runs. A correction can remove a series entirely when no current posting remains.

### `balance_changes`: one changed daily row per successful run

The business key is the successful `run_id` together with the daily row's date, item, and location. Change records are inserted atomically with target publication. They are retained across later runs.

| Field | Meaning |
| --- | --- |
| `run_id` | Successful publication that produced this change |
| `balance_date`, `item_id`, `location_id` | Identify the affected daily-balance row |
| `before_json` | Prior snapshot with exact decimal quantity strings; null when the row was added |
| `after_json` | Replacement snapshot with exact decimal quantity strings; null when the row was removed |
| `closing_delta_milli` | Decimal integer text containing after closing minus before closing in exact thousandths, treating an absent side as zero; text preserves differences wider than signed 64-bit |

Each present snapshot contains seven exact three-decimal strings: `opening`, `receipts`, `issues`, `transfers_in`, `transfers_out`, `adjustments`, and `closing`. A null snapshot encodes absence of that row. Publication lineage alone does not create a change record. Changes can therefore reveal a movement-field change even when the closing quantity is equal.

A replay with identical business balances creates a run and zero new change rows. A failed publication retains no changes for that run. Runs created before the feature existed have no captured change history; absence of their snapshots does not establish their historical impact.

The `GET /api/changes` endpoint returns change rows in pages for the correction view. Deltas are quantities for one item/location/day. They must not be summed across days as if they were stock, or across different item units. Full `balance_changes.csv` exports retain every captured change; the main report does not embed the entire change history.

## Report objects

`metrics` summarizes current non-void events, preserved historical versions, daily rows, negative-balance days, rejected rows, and currently voided events. `reconciliation` contains named checks with `expected`, `actual`, `variance`, `passed`, and explanatory details. Runs and rejects remain independently visible even when arithmetic reconciliation passes: correct aggregation does not mean every source row was accepted.

The JSON report and dashboard include all daily balances and runs, but cap the displayed rejected records and historical event versions at the most recent 500 each. `display_limits` declares those caps. Full audit CSV exports include every raw record and event version. `generated_at` is the UTC report-generation time; `published_through` is its business-date horizon.

### `demo_examples`: real teaching-run metadata

The report includes `demo_examples` when the database has the completed demo marker; it is null for a database without that setup. This object identifies seeded examples rather than changing inventory metrics.

| Field | Meaning |
| --- | --- |
| `version` | Teaching metadata version, currently `1` |
| `initial_movement_count` | `50`, the distinct valid revision-1 source events in the default demo |
| `expected_rejected_rows` | `3`, the separately seeded intentional row-level rejects; later user imports can change actual totals |
| `transfer_event_id` | `demo-c-transfer-1`, cancelled at revision 2 and restored at revision 3 |
| `runs` | Actual run IDs keyed by `initial`, `correction`, `cancellation`, `restoration`, `validation`, `failure`, and `recovery` |

The quality example file contains an over-precision quantity (`1.0001`), an unknown item (`ITEM-UNKNOWN`), and a transfer with the same source and destination. These three records are quarantined without contributing to inventory. The separate expected schema failure has an invalid header, fails at file level before publishing, and is followed by a valid safe replay of all 50 already-recorded events. A passing current reconciliation and these three rejects are compatible: mathematical checks apply to accepted current data, while quarantine exposes excluded source data.

The stored failed run is a deliberately supplied historical input example, not evidence that the browser server is currently failing. Only the identified supplied examples are intentional; later unexpected failures and rejected user records require normal review. A fresh default database finishes with 50 current events, 53 historical versions, 47 daily rows, and four intentionally negative closing rows. These are distinct grains, and user imports can change them.

The negative rows are ITEM-D/WH-C on January 2–4 (`-9.875`, `-14.000`, `-14.000` KG) and ITEM-E/WH-B on January 4 (`-3.625` L). Valid issue quantities create these conditions; they are accepted movements and affect balances. `is_negative` is a derived warning, separate from the three quarantined invalid records. Reconciliation can pass while negative-stock warnings remain. The count is at item/location/day grain, not a count of distinct calendar dates or a total quantity.

## Browser input and verification evidence

Movement imports submit a filename, the selected file's CSV text, and an optional inclusive reporting date. They use the movement contract above; selecting or previewing a file alone does not publish it. Optional item/location catalog uploads are a separate atomic request and use the two catalog contracts.

| Local endpoint | Request or response |
| --- | --- |
| `GET /api/login-session` | Public login preparation: returns `csrf_token` and sets a ten-minute pre-login cookie |
| `POST /api/login` | JSON `username`, `password`; valid pre-login cookie, token, and matching origin required; success sets the authenticated cookie |
| `GET /api/session` | Authenticated session: `username`, `csrf_token`, and `expires_in` |
| `POST /api/logout` | Authenticated JSON request with session CSRF/origin checks; revokes the current session and clears its cookie |
| `GET /api/report` | Current ledger metrics, balances, runs, capped rejects/history, reconciliation, and optional real-run `demo_examples` metadata |
| `GET /api/catalogs` | Loaded item and location rows |
| `POST /api/import` | JSON `filename`, `csv_text`, optional `through`; returns `run` and first-page `impact` on success |
| `POST /api/catalogs` | JSON `items_filename`, `items_csv`, `locations_filename`, `locations_csv`; validates and adds both catalogs atomically |
| `GET /api/changes?run_id=…&limit=100&offset=0` | Comparison for the selected run; omitted `run_id` selects the latest attempt; `limit` is 1–500 and `offset` is nonnegative |
| `GET /api/showcase` | Version, implemented capabilities, recorded test/benchmark/coverage evidence, and limitations |
| `GET /api/sample/review_correction.csv` | Downloadable revision-3 correction for the standard demo; other starter CSVs are also available under `/api/sample/` |
| `GET /api/demo/movements.csv` | Default 50-event source; matching `items.csv` and `locations.csv` are also available under `/api/demo/` |
| `GET /api/demo/demo_quality_examples.csv` | Three intentionally invalid row-level examples |
| `GET /api/demo/demo_cancel_transfer.csv`, `GET /api/demo/demo_restore_transfer.csv` | Full revision-2 void and revision-3 restoration for the demo transfer |
| `GET /api/demo/demo_expected_schema_failure.csv` | Deliberately invalid schema example, recorded as a failed input run during setup |

Protected data/download routes require a valid login. Unauthenticated data API reads return 401, while a dashboard navigation redirects to `/login` with 302. The public resources are the login page/assets and login preparation endpoint. POST requests use `Content-Type: application/json`, the matching local `Origin`, and `X-Stockline-Token`: the pre-login token for login, or authenticated session token otherwise. Invalid host/origin/token checks can return 403 before any mutation. Login/logout JSON bodies are limited to 8 KiB.

The port-specific cookies are `StockInventoLogin_<port>` and `StockInventoSession_<port>`, with `Path=/`, `HttpOnly`, and `SameSite=Strict`. The login-preparation cookie lasts ten minutes; the authenticated cookie has an eight-hour maximum age, with server-side expiry after thirty minutes idle or eight hours absolute. Logout and server restart invalidate sessions. Plain loopback HTTP is used; the cookies are not marked `Secure`. After five failed credential checks per client within sixty seconds, subsequent login requests return 429 with `Retry-After`.

Each UTF-8 CSV is limited to 10 MiB, the full import JSON request to 32 MiB, and filenames to 128 characters without directories or control characters. Use the CLI for larger batches. The preview shows the first six physical lines; server validation reads the full CSV. A valid batch containing rejects still returns its published run; a fatal batch error returns an error and remains visible in the run audit. Concurrent browser imports return a busy response. The login does not restrict direct local-file or CLI access by the operating-system user.

The changes response contains `run_id`, the run metadata, `has_snapshot`, `total`, `limit`, `offset`, a `summary` of changed rows/affected series/date range, and the current page's `rows`. A row includes `change_type` (`added`, `removed`, or `updated`), exact before/after opening and closing values, `closing_delta`, `changed_fields`, and full nullable `before`/`after` snapshots. `has_snapshot=true` with `total=0` means a retained comparison found no business changes; `false` means a successful comparison is not available.

The local server's token and origin checks are required for mutating POST requests. Reports and the paginated changes view remain read operations. The dashboard is intended for the local loopback server, rather than cross-origin or public use.

The generator's `coverage.json` is a supporting report separate from source inputs. It describes observed item/type/location coverage and must not be included as an input column or expected-answer label. Its `normal_coverage` uses new revision-1 rows only, excluding deliberate duplicates, invalid-precision rows, and revisions. It reports per-item movement types/counts, source locations, transfer destinations, adjustment signs, date range, and out-of-order arrival evidence. The verification process saves it as `evidence/generator-coverage.json`.

Recorded files under `evidence/` describe the workload on which they were produced. `GET /api/showcase` reads the test log, performance report, and generator coverage; the Achievements & verification view distinguishes those saved results from current database counts and static capability descriptions.
