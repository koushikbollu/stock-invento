# Review walkthrough

This walkthrough helps a reviewer verify behavior and helps the candidate prepare to explain the implementation. Running it is necessary before claiming personal validation.

## Reproduce a fresh result

1. Use Python 3.10 or later and start in the repository root.
2. Run `python3 -m unittest discover -s tests -v` and inspect failures, if any.
3. Choose an unused output folder and run `python3 run_demo.py --data-dir var/final-review --port 8766`. It starts a separate demo and opens `http://127.0.0.1:8766`, preserving any existing `var/demo` data. At `/login`, enter **Username `admin`**, **Password `admin123`**, then select **Sign in**. A new folder is required to see the updated negative-stock examples if an older demo already contains the original immutable revision-1 values.
4. Inspect the generated reports in `var/final-review/export` and the row-outcome counts. A fresh demo starts with the 50 distinct revision-1 records in `data/demo/movements.csv`, then applies the receipt correction and seeded learning examples: 50 current events, 53 historical versions, 47 daily rows, four intentionally negative closing rows, three deliberately quarantined example rows, and seven scenario runs. The hand-calculated files under `data/expected` cover the separate original seven-event fixture, rather than every row in the larger demo.
5. Keep the terminal open while reviewing. Stop with `Ctrl+C`; rerunning the same command preserves the database and adds safe replay audit attempts rather than resetting it.

The local ZIP also includes platform launchers; see `START_HERE.txt` for quick startup or the [portable setup guide](portable-setup.md) for exact Windows/macOS/Linux commands, path rules, troubleshooting, password changes, and safe backup. Python 3.10+ is the only runtime requirement; no package downloads, private secrets, or external account access are needed after Python is installed. Relative `run_demo.py --data-dir` paths start at the project folder, independently of the invoking working directory.

The password starts masked; **Show** and **Hide** switch its visibility. An incorrect password keeps you on the login page with a generic error. After reviewing, choose **Sign out** at the top right: returning to a protected route requires another sign-in. Restarting also requires sign-in but preserves inventory. Sessions expire after thirty idle minutes or eight hours from login. Existing workspaces retain a changed password rather than restoring `admin123`; use the portable guide's local password command if needed. HTTP authentication does not restrict the operating-system user's direct file or CLI access.

The recorded [authentication test report](auth-test-report.md) and [browser evidence](../evidence/authentication/browser-checks.json) describe executed checks; repeating this walkthrough is the candidate's own review.

The dashboard uses a green theme and opens at **Inventory overview**. The main header's **Import CSV** button opens the import drawer. Use its **Close import movements** control (×) or `Escape` to close it; closing and reopening retains the selected files, preview, and draft date while the page stays open. The sidebar links to **Overview**, **Inventory ledger**, and **Verification**, with **View process guide** below. **Process guide** and **Achievements & verification** are together below the ledger, and both start collapsed; selecting **Verification** opens achievements there.

The **Seeded demo** and **Review required** panels below the metric cards, when present, start collapsed with their headings visible. Expand them to read the seeded-case context and current warnings. In the import drawer, expand **Valid rows commit. Invalid rows go to quarantine.** to read the commit, replay, and fatal-error guidance.

The default movement source covers ITEM-A–ITEM-E, WH-A–WH-C, January 1–4, and all four movement types. Its 50 movement records are not 50 daily balance rows: the latter are derived for each item/location/day. The extra 43 events use only ITEM-C, ITEM-D, and ITEM-E, preserving the original ITEM-A/ITEM-B correction exercise.

Expand **Process guide** to download **Demo movements CSV · 50 records** and its matching five-item/three-location catalogs. These downloads use `/api/demo/`. The separate original seven-event fixture under `data/sample` and `/api/sample/` remains unchanged for hand-calculated tests; the review and original correction files work with either dataset.

## Follow the examples through every view

Each of the six ledger tabs has a **Demo example** drop-down, collapsed by default; expand it to see the note and any example action. You can also expand the bottom **Process guide** and choose **Daily balances**, **Receipt correction**, **Reconciliation**, **Failure & recovery**, **Quarantined rows**, or **Cancellation history**. These open real ledger/audit records created during demo setup rather than display-only illustrations.

The scenario runs execute copies based on the templates in `data/demo`; their recorded filenames include generated token suffixes. Use the actual run selected by a guide button instead of matching only an exact unsuffixed template filename.

1. In **Daily balances**, inspect the 47 item/location/day rows and compare their quantities with the movement source. Expand **Demo example**: **View this example** focuses ITEM-A/WH-A for January 1–4; **Close example** restores your previous filters and page. A manual filter change exits the example and keeps that new choice. Then filter ITEM-D/WH-C on January 2–4 to see `-9.875`, `-14.000`, and `-14.000` KG, or ITEM-E/WH-B on January 4 to see `-3.625` L. The negative-stock metric counts four item/location/day rows across two series, rather than distinct calendar dates. These view controls change no underlying data.
2. In **Correction impact**, inspect the receipt correction and the transfer cancellation/restoration runs. `demo-c-transfer-1` moves `20.000` of ITEM-C from WH-A to WH-B on January 1. Revision 2 cancels it; revision 3 restores it. The cancellation temporarily changes both locations, while restoration returns the active transfer contribution. All before/after comparisons remain available after the final state has been restored.
3. In **Reconciliation**, verify the current accepted movements, postings, and daily equations. The four negative closing rows come from valid accepted issue movements and are warnings, not rejects. The three separate rejected source examples have no inventory contribution. Passing arithmetic reconciliation can therefore coexist with both negative-stock warnings and quarantine records; it proves the arithmetic, not that every operational condition is desirable.
4. In **Pipeline runs**, locate the deliberately invalid schema attempt and the subsequent successful replay. The failed attempt published no new inventory state; the valid replay recognizes all 50 source events as duplicates and safely continues. A historical failed input run does not mean that the server is currently failing.
5. In **Quarantine**, expand each of the three intentional invalid rows and inspect its raw values, source filename, line number, and reason. The examples are quantity `1.0001`, unknown item `ITEM-UNKNOWN`, and a transfer from WH-A to WH-A. A reject count is evidence to inspect, not a quantity silently omitted from reconciliation.
6. In **Event history**, inspect superseded, cancelled, restored, and current versions. The 53 historical versions describe 50 current events; each revision is not an extra stock movement.

After completed setup, the `demo_examples_v1` marker prevents the extra scenario files from being seeded repeatedly and preserves existing user data. New interrupted setups also keep private progress checkpoints to recover their own committed scenario runs. Restarting can record normal duplicate startup attempts, but it does not add another copy of the owned supplied invalid examples. Manually importing a downloaded example still creates another ordinary audit attempt. Older incomplete setups without progress tracking retain their prior audit records; see the [portable guide's limits](portable-setup.md#7-verify-the-checkout-and-understand-its-limits). Only the identified supplied examples are intentional; investigate new unexpected errors normally.

## Preview and import a correction in the browser

For the standard fresh demo, use the review correction supplied with version 1.1:

1. Open **Process guide** below the ledger, then select **Download correction**.
2. Select **Import CSV** in the main header. In the drawer, choose the downloaded `review_correction.csv` in **Choose a movement CSV**. Inspect the first-six-line preview; the file replaces `receipt-a` with complete revision 3 at `120.000`.
3. Select **Import & publish**. Previewing alone does not change the ledger.
4. Select **View this run’s balance impact** in the result to close the drawer and open that run in **Correction impact**. In a fresh standard demo, ITEM-A/WH-A changes from `75.000` to `85.000` on January 4. The daily closing delta is `10.000` on each affected date.
5. Reopen the drawer and reimport the same file. The retained draft is still available; the new run records a duplicate and a retained comparison with zero business changes.

The standard demo already applies revision 2 at `110.000`; the review file is revision 3. If revision 3 or a higher revision is already present in your database, the result depends on that history. Do not change an existing revision's contents to force another correction.

To hand-check the original seven-event fixture and its revision-2 correction instead, choose an unused database path and load only that fixture's movements:

```sh
python3 -m inventory init --db var/browser-review/inventory.db \
  --items data/sample/items.csv --locations data/sample/locations.csv
python3 -m inventory run --db var/browser-review/inventory.db \
  --input data/sample/movements.csv --through 2026-01-04
python3 -m inventory serve --db var/browser-review/inventory.db --port 8765
```

Use another port if a demo server is already running. Do not reuse a database where revision 2 has already been loaded for this before/after exercise.

1. In the dashboard, inspect ITEM-A at WH-A on January 4. Its closing quantity is `65.000`.
2. Open **Process guide** below the ledger and select **Original correction CSV** under the starter-file links, or locate `data/sample/corrections.csv` in the extracted ZIP. Open the import drawer with the main header's **Import CSV** button, then choose that CSV in the movement-file picker. This is the revision-2 file, rather than the revision-3 review correction.
3. Inspect the preview and optional reporting date. Confirm that previewing alone has not added a run or changed stock.
4. Select **Import & publish**. Inspect the run status and accepted, duplicate, and rejected counts. The correction is a complete revision-2 replacement of the original receipt.
5. Select **View this run’s balance impact** to close the drawer and open the new run in **Correction impact**. ITEM-A at WH-A has a closing delta of `10.000` on each affected day through January 4, with its later opening quantities carried forward. Its January 4 closing is `75.000`; the other sample series retain their previous quantities.
6. Reimport the same correction CSV. The new operational attempt is visible, but it has no new accepted version and zero business balance changes.

The repeated daily `10.000` delta describes the same stock correction carried through time; adding those days together does not produce an inventory quantity. Choose a single date and an item's unit when interpreting impact.

If using the already-corrected standard demo, inspect the original correction run's recorded impact or submit a complete revision greater than the current one. Do not alter an existing revision's payload and expect it to overwrite history; that is a conflict.

## Add catalogs before new movement references

Open the import drawer for the optional catalog import, which accepts item and location CSVs using the documented schemas. Preview them, then explicitly add both catalogs as one atomic catalog step. If either catalog is invalid, that step must not partially add the other. Existing item units cannot change silently.

After the catalog step succeeds, import movements referencing those identifiers. Movement ingestion is a separate transaction: a later invalid movement or failed movement publication does not undo the earlier catalog addition. Inspect quarantined rows and reasons rather than assuming every uploaded movement was accepted.

## Inspect what was built and verified

Select **Verification** in the sidebar to open **Achievements & verification** below the ledger, or expand that disclosure directly. Identify which numbers describe the current open ledger above and which describe the saved larger benchmark. Read the benchmark environment, row count, measured duration, coverage, reconciliation, and replay result. Review the linked recorded evidence rather than inferring performance from the small demo's response time.

Capabilities such as revision history, exact quantity arithmetic, guarded CSV import, and persisted correction impact describe implemented features. They are separate from measured benchmark results. There is no speedup claim unless comparable before-and-after measurements support one.

## Explain one daily balance

Select one item/location series. Locate its first receipt, issue, transfer, and adjustment in the source fixture. Compute the daily values by hand using the balance equation. Check that the next day's opening equals the prior day's closing, including a gap day. Quantities are decimal strings in exports and integer thousandths internally, so fractional examples remain exact.

## Explain a transfer

Find both legs of the same transfer. The source loses the same quantity the destination gains, on the same effective date. Compare the all-location total before and after: the transfer must contribute zero net stock. Both legs are derived and published together.

## Explain a correction

Find the original event and its higher revision. A revision is a complete replacement, so applying a corrected receipt of 110 to replace 100 changes stock by 10, rather than adding another 110. Read the current-event selection and verify that the old version remains in history. Confirm the changed closing quantity propagates forward into subsequent days' openings and closings.

Then explain why changing the event's date, location, item, movement type, or transfer destination is safe under a full rebuild. A cancellation uses a higher void revision and removes the current contribution while retaining the original event history.

## Explain reruns and rejects

Rerun a sample file. The new run is recorded, identical normalized event versions are duplicates, and stock remains unchanged. Contrast that with different data under an existing version key, which must be rejected as a conflict. Open the reject view and trace a malformed row from its reason to its run, source file, and line number.

A successful reconciliation result and a nonzero reject count can coexist. The former checks accepted current data; the latter means some source data still needs attention.

## Explain atomic recovery

Read the failure/retry test. It deliberately fails before publication and verifies that the prior state remains published, the failed attempt is visible, and a retry accepts the previously rolled-back versions once. A failed attempt must leave no successful before/after change records. Explain the distinction between a failed publication and a successful batch containing quarantined invalid rows.

## Measure a larger batch

Generate 100,000 rows with the fixed seed, initialize a fresh database using the generated catalogs, and ingest the generated movements. Inspect `coverage.json` separately from the input CSVs and confirm every item has all four movement types in that workload. Inspect the recorded duration and source/target counts. Explain why deliberate duplicates and invalid rows mean input count differs from accepted unique event count. Compare a replay with the initial ingestion, and discuss full rebuild and persisted change-history costs as current history or the output date grid grows.

## Candidate review record

Candidate personal review is pending. Replace this statement only after actually reviewing and running the application. Record what you understood, changed, validated, and still regard as a limitation. AI-generated test success is useful evidence, but it is not a statement of personal understanding.

Be prepared to explain:

- The source, posting, and daily-balance grains and keys.
- Why effective date differs from ingestion time.
- Full replacement corrections, maximum-revision selection, and voids.
- How a transfer preserves stock across locations.
- Integer quantity arithmetic and its precision limits.
- Which errors quarantine a row and which fail a batch.
- Why catalog upload and movement import are separate transactions.
- How before/after changes represent added, removed, and modified daily rows.
- Why a replay can add an audit run without adding balance changes.
- Why legacy runs have no reconstructed change snapshots.
- How login sessions, token and origin checks protect local HTTP access, and why local files/CLI remain accessible.
- How recorded benchmark evidence differs from the open demo's current metrics.
- Why SQLite and a full rebuild are appropriate for this local workload.
- What changes would be needed for scheduling, multi-user roles, concurrency, larger history, or production deployment.
