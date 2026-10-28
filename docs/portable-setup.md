# Run Stock Invento on another computer

This guide covers local setup, sign-in, persistent data, clean review databases, imports, exports, and troubleshooting. The application runs on the receiving computer. It does not require GitHub, an external account, API keys, cloud hosting, or `pip install`.

## 1. Extract and check Python

Copy the complete ZIP and extract it fully into a writable folder. Open the extracted folder containing `run_demo.py`, `inventory/`, `data/`, `docs/`, and `evidence/`. Keep those files together; running a script from inside the ZIP or copying only its HTML file will not start the application.

Python **3.10 is the compatibility minimum**, not the recommended release for a new installation. Choose a currently supported release from the [official Python downloads page](https://www.python.org/downloads/); that page identifies supported and end-of-life versions. Installation details are available in the official [Windows](https://docs.python.org/3/using/windows.html), [macOS](https://docs.python.org/3/using/mac.html), and [Unix/Linux](https://docs.python.org/3/using/unix.html) guides.

Python's normal standard library, including `sqlite3`, is required. Once Python is available, no package downloads or internet connection are needed. Node.js and npm are not required to run the app. A browser and a writable local folder are sufficient. The application uses the local address `127.0.0.1`; no network deployment is needed.

Check the interpreter you will use:

| System | Version check | Start from the project folder |
| --- | --- | --- |
| Windows, PowerShell or Command Prompt | `py -3 --version` | `py -3 run_demo.py` |
| macOS, Terminal | `python3 --version` | `python3 run_demo.py` |
| Linux, terminal | `python3 --version` | `python3 run_demo.py` |

On Windows, use `python` instead of `py -3` if the launcher is unavailable and `python --version` reports Python 3.10+. In the commands below, Windows users should likewise replace `python3` with their working `py -3` or `python` command. Do not install third-party Python packages for this project.

## 2. Start the local demo

The included launchers perform the same startup and forward additional arguments to `run_demo.py`:

- **Windows:** double-click `START_WINDOWS.bat`.
- **macOS:** double-click `START_MAC.command`, or run `sh START_MAC.command` from Terminal in the project folder.
- **Linux:** run `sh START_LINUX.sh` from the project folder.

If double-clicking a script is blocked or unavailable, use the Python command in the table above. There is no need to change system security settings.

Startup creates the demo database if necessary and tries to open your default browser. If the browser does not open, visit [http://127.0.0.1:8765/login](http://127.0.0.1:8765/login). Enter **Username `admin`**, **Password `admin123`**, then select **Sign in**. These shared defaults are also listed in `START_HERE.txt`; no external account registration is needed. Keep the terminal open while using the app.

To select another port or open the browser yourself:

```sh
python3 run_demo.py --port 8766 --no-browser
```

Then open [http://127.0.0.1:8766/login](http://127.0.0.1:8766/login). The port must be between 1 and 65535. Stop the server with `Ctrl+C` in its terminal; closing the browser alone does not stop it. Restarting requires a new sign-in because server sessions are held in memory.

### Login lifetime, sign-out, and changing the local password

The HTTP session expires after thirty minutes without activity or eight hours after login. Use **Sign out** at the top right when finished; it revokes the current session, and a server restart invalidates all sessions. The password field starts masked; the login form's **Show**/**Hide** control changes its visibility. A new workspace starts with `admin` / `admin123`, while an existing workspace retains its saved password hash. The defaults are intentionally shared for demonstration, not private production credentials.

To change the workspace's admin password, stop its server, run the following from the project root, then restart:

```sh
python3 -m inventory set-password --db var/demo/inventory.db
```

Substitute the database in your selected data folder. Enter and confirm the new password at the hidden prompts; it must be 8–1024 characters. Restarting revokes earlier sessions. Later startup preserves the changed password instead of restoring `admin123`. This command is an operating-system owner's local operation and does not alter inventory.

The login gates HTTP access, not the local filesystem or CLI. Full database copies retain the chosen password hash, so a copied workspace may no longer use the default password. The source ZIP contains no generated workspace hash, database, or session cookie. The app remains loopback-only and uses local HTTP; it is not a public-hosting or multi-user authorization system.

### Running from another working directory

An absolute path to `run_demo.py` works without first changing directories:

```sh
python3 "/path/to/stock-invento/run_demo.py" --port 8766
```

Windows equivalent:

```powershell
py -3 "C:\path\to\stock-invento\run_demo.py" --port 8766
```

The script locates its source files and default data directory relative to itself. In contrast, `python3 -m inventory ...` commands must run from the project root, where the `inventory` folder is visible. Relative paths in those CLI commands refer to that working directory.

## 3. Understand the saved data and clean-review option

The default database is `<project>/var/demo/inventory.db`. CSV imports change this local database and survive a restart. Startup preserves existing events and history; it does not reset the database. It records safe replay attempts, and completed demo setup is marked so the extra teaching scenarios are not repeatedly seeded.

For a clean review without deleting an existing database, choose an unused output folder:

```sh
python3 run_demo.py --data-dir var/final-review --port 8766
```

Relative `--data-dir` paths start at the project folder, independently of the invoking working directory. Absolute paths and `~` home-directory paths are supported. The flag selects a folder containing `inventory.db` and `export/`; it does not reset or delete an existing folder. Choose a genuinely unused name for a fresh baseline.

The equivalent two-step CLI commands, run from the project root, are:

```sh
python3 -m inventory demo --out var/final-review
python3 -m inventory serve --db var/final-review/inventory.db --port 8766
```

This creates a separate database and leaves `var/demo` intact. Choose another unused name if `var/final-review` already contains a database. The `serve` command opens an existing database without replaying demo setup. It prints its local URL; open that URL manually.

An earlier demo may contain the old revision-1 quantities for the two issue events now used to demonstrate negative stock. Restarting preserves those immutable versions and can report conflicts with the updated source; it does not replace them. Use a new folder for the current negative-stock baseline, keeping the earlier database intact.

A newly created standard demo has:

| Record type | Expected count |
| --- | ---: |
| Distinct valid source movements | 50 |
| Current movement events | 50 |
| Historical event versions | 53 |
| Daily item/location/date balance rows | 47 |
| Intentional quarantined rows | 3 |
| Negative closing rows (item/location/day) | 4 |
| Recorded scenario runs | 7 |

The seven runs cover initial ingestion, receipt correction, transfer cancellation, transfer restoration, invalid-row validation, expected schema failure, and successful recovery. A restart or user import adds ordinary audit runs, so seven is a fresh-database expectation rather than a permanent total.

The intentional negative rows are ITEM-D/WH-C on January 2 (`-9.875` KG), January 3 and 4 (`-14.000` KG each), and ITEM-E/WH-B on January 4 (`-3.625` L). Their issue movements are valid accepted data. Negative stock is a visible warning, not a quarantine rule, so current mathematical reconciliation still passes. The metric counts four item/location/day rows; do not sum their quantities across days or different item units. Later negative-stock conditions in user imports still require normal review.

Only the named teaching examples are intentional. `demo_quality_examples.csv` contains three rejected rows: excessive quantity precision, an unknown item, and a transfer within the same warehouse. `demo_expected_schema_failure.csv` deliberately fails header validation, after which a valid replay identifies all 50 movements as duplicates. That historical failed input run is not a failed server. Other unexpected errors still require investigation.

Those names identify the source templates in `data/demo`. Seeded execution copies have generated suffixes such as `demo_quality_examples.<token>.csv`; use the guide's actual run links rather than expecting audit filenames to equal the template name exactly.

The original seven-event fixture in `data/sample` and its hand-calculated answers in `data/expected` remain separate from the 50-event demo. The recorded 100,000-row benchmark is a third workload, not the live demo.

## 4. Review, import, correct, and export

The green dashboard opens at **Inventory overview**. **Inventory ledger** contains the report tabs. The main header's **Import CSV** button opens the import drawer. Close (×) or `Escape` dismisses it; closing and reopening retains the files, preview, and draft date while the page stays open. **Process guide** and **Achievements & verification** are below the ledger and start collapsed; the sidebar's **Verification** link opens achievements, and **View process guide** opens the guide.

Each of the six ledger tabs has a **Demo example** drop-down, collapsed by default; expand it to see its note and any example action. In **Daily balances**, **View this example** temporarily focuses ITEM-A/WH-A for January 1–4. **Close example** restores the previous filters and page. Manually changing a filter exits the example and keeps the new choice. These actions change the displayed view, not the underlying data.

The **Seeded demo** and **Review required** headings below the metric cards, when present, also expand to show their details. The import drawer's **Valid rows commit. Invalid rows go to quarantine.** heading opens its guidance. These panels start collapsed, with their headings visible.

Open **Import CSV** in the main header, then follow this sequence for your own CSVs:

1. **Catalogs:** if you use new item or location IDs, expand **Using new item or location IDs?** and choose both reference files. Item columns are `item_id,unit`; location columns are `location_id`. **Validate & load catalogs** adds both as one atomic step. Existing item units cannot change silently.
2. **Movements:** choose a UTF-8 CSV with the exact [movement schema](data-dictionary.md). Inspect its first-six-line preview and optional **Publish through date**, then choose **Import & publish**. Previewing alone changes nothing. The complete file is validated on import.
3. **Outcomes:** inspect accepted, duplicate, rejected, and rolled-back counts. Valid rows can publish while invalid individual rows enter **Quarantine**. A structural schema or fatal publication error fails the batch and preserves the previous inventory state. Earlier catalog additions are a separate transaction and remain available.
4. **Rejects:** expand a quarantined row to read its source values and reason. Fix those values and reimport. Identical committed versions are duplicates, while conflicting contents under the same event/revision key are rejected.
5. **Corrections:** submit a complete replacement with a higher revision. **View this run’s balance impact** closes the drawer and opens that run in **Correction impact** to inspect exact before/after values for the affected dates. A higher void revision cancels an event; a later non-void revision can restore it. Do not add daily deltas across time or combine different item units as a stock total.
6. **Exports:** **Export view** downloads the currently filtered daily-balance view. For the complete analysis/audit snapshot, run the CLI export command below.

Each browser CSV is limited to 10 MiB and the JSON request to 32 MiB; use the CLI for larger files. The [walkthrough](walkthrough.md) explains the supplied receipt correction and every seeded scenario. The [data dictionary](data-dictionary.md) defines keys, precision, lineage, and API fields.

From the project root, export the default database:

```sh
python3 -m inventory export --db var/demo/inventory.db --out var/export-review
```

If you selected a different data folder, substitute its database path in export and backup commands, for example `var/final-review/inventory.db`.

The export reads a consistent database snapshot and writes daily balances, runs, reconciliation, raw outcomes, event versions, postings, balance changes, and `report.json`. It includes full audit CSVs beyond the dashboard's 500-row history/reject display caps. It is an analysis snapshot, not an automatic database restore format: catalogs and internal settings are not included. Keep original catalog/input files as well.

Startup writes a demo export, but later browser imports do not automatically refresh those exported files. Run export again when you want a current snapshot, preferably into a new output folder to retain earlier reports.

## 5. Back up or move a database safely

To give someone a clean demonstration, share the complete source ZIP without your runtime `var` data; their startup creates a fresh demo. To preserve your current state, back up the actual SQLite database, including its catalogs, settings, audit history, and user imports.

Do not copy a live `inventory.db` file by itself. SQLite uses WAL mode, and recent committed data may be in `inventory.db-wal`. Use the export command for live review reports. For a full file copy, first stop every server/CLI writer using that database, wait for the processes to exit, and copy the entire data folder, including any remaining SQLite sidecar files. Keep filenames together; do not delete sidecars to make a copy look simpler.

An optional consistent database backup while the app is running uses Python's standard-library SQLite backup API. From the project root, choose an unused backup filename:

```sh
python3 -c "import sqlite3; from pathlib import Path; p=Path('var/backups/demo-backup.db'); p.parent.mkdir(parents=True,exist_ok=True); assert not p.exists(), 'Choose a new backup filename'; s=sqlite3.connect('file:var/demo/inventory.db?mode=ro',uri=True); d=sqlite3.connect(p); s.backup(d); d.close(); s.close()"
```

This creates a self-contained database snapshot rather than a raw live-file copy. To inspect it without replaying setup:

```sh
python3 -m inventory serve --db var/backups/demo-backup.db --port 8766
```

You can move that backup together with the complete source project to another computer and serve its copied path. There is no cloud synchronization or account transfer. Database files and exports can contain everything you imported; share only the data you intend the recipient to receive.

## 6. Troubleshooting

| Symptom | Action |
| --- | --- |
| Python is missing, or the version is below 3.10 | Install/use Python 3.10+ and reopen the terminal; verify the same command used by the launcher |
| `No module named inventory` | Run `-m inventory` commands from the extracted project root, or use an absolute path to `run_demo.py` |
| `run_demo.py` or a static/data file cannot be found | Extract the entire ZIP; keep its folder structure intact |
| `sqlite3` cannot be imported | Use a complete Python installation with its standard SQLite module; no pip dependency is expected |
| Permission denied or read-only database | Move/extract the project into a writable folder, or use `run_demo.py --data-dir` with a writable local folder |
| Port 8765 is occupied | Stop the previous server or use `--port 8766`; open the URL with that same port |
| Browser did not open, or its old tab cannot connect | Confirm the terminal is still running and open the printed `http://127.0.0.1:PORT` address |
| Redirected to login or an API returns 401 | Sign in; sessions expire after thirty idle minutes, eight hours absolute, logout, or server restart |
| Sign-in returns 429 | Wait for the indicated retry interval; five failed credential checks within sixty seconds throttle subsequent attempts |
| Default password no longer works | An existing workspace may have a changed password; use the local `set-password` command for that database, then restart |
| Login preparation or CSRF token expired | Refresh the sign-in page or authenticated dashboard, then retry the intended action |
| Schema failure or quarantined rows | Inspect the named run and reason; only the identified seeded examples are intentional |
| Import reports another import is running | Wait for that operation to finish, then retry |
| File exceeds the browser limit | Use the `run` CLI with a local CSV path |
| Counts differ from the fresh-demo table | Existing data/restarts/imports change history; use a new separate demo folder for a clean baseline |
| A script does not launch by double-click | Run its Python command in a terminal; do not disable system protections |

## 7. Verify the checkout and understand its limits

From the project root:

```sh
python3 scripts/run_tests.py --out var/test-results-new
python3 scripts/verify.py --rows 100000 --out var/verification-local
```

The first command writes per-method Python JSON, JUnit XML, and an execution log on a clean pass. A failed rerun invalidates stale success artifacts and saves a failure log. Use an unused output folder to preserve earlier runs. The second command reruns tests, compares the independent seven-event oracles, checks corrections/replay, generates synthetic data, and records a local benchmark. Writing to `var/verification-local` preserves the shipped evidence. Its results describe that execution and computer; the dashboard continues to read included evidence unless deliberately regenerated there.

Developers who already have Node.js can optionally run `node tests/ui_refresh.test.cjs` to check the report-refresh queue and example-view toggle using the actual JavaScript source. The current [helper log](../evidence/authentication/ui-helpers.txt) records eleven checks: six queue cases and five toggle cases. The [authentication report](auth-test-report.md) also records syntax checks for the dashboard and login scripts. The harness uses Node built-ins, needs no npm install, and is separate from normal app startup and Python verification. It is not a replacement for the browser walkthrough.

The current [authentication test report](auth-test-report.md) and [Python evidence](../evidence/authentication/python-tests.json) record **117 passing methods containing 222 subtest checks**, with zero failures/errors/skips, in 11.136807 seconds. The [authentication browser evidence](../evidence/authentication/browser-checks.json) records eight passed scenarios, including masked/show-hide password entry, incorrect and correct credentials, a real correction import, logout, browser Back after logout, and retained corrected data after re-login.

The historical [requirements test report](test-report.md), [scenario matrix](test-scenarios.md), and [Python evidence](../evidence/rigorous/python-tests.json) retain the pre-authentication campaign: 100 passing methods containing 196 subtest checks. They do not independently certify the later login. The historical [100,000-row benchmark](../evidence/rigorous/performance.json) measured 4.83 seconds on arm64 macOS/Python 3.14.6; the still older [4.60-second measurement](../evidence/performance.json) is also retained. Those timings were not regenerated for the authentication supplement. Neither is a timing promise for another computer or proof of native Windows/Linux execution.

The historical [browser campaign](../evidence/rigorous/browser-checks.json) exercised fifteen actual UI scenarios before authentication, including file preview, correction/replay, quarantine, fatal schema rollback, filter restoration, and downloaded CSV inspection. It used an isolated test database; the reviewed demo's saved data was not replaced by those test imports.

The current [authenticated portable clean-copy proof](../evidence/authentication/portable-check.json) records startup from a copied path containing spaces and a different invoking directory, login, real local correction/replay requests, a consistent export, and persistent restart with a new login. Execution used macOS/Python 3.14.6. Python 3.10 syntax compatibility was checked for 26 files, along with launcher syntax/argument handling; Windows and Linux launchers were reviewed rather than executed on those systems. The earlier [portable proof](../evidence/rigorous/portable-check.json) is retained separately.

The application is a local, single-writer workflow with one local admin account. It has no public hosting setup, multi-user roles, external identity service, scheduler, distributed processing, or stock valuation. Quantities have at most three decimal places and a per-event absolute limit of 1,000,000,000 units; item units are not converted. The pipeline rebuilds current balances and retains correction snapshots, so long date grids and growing history increase processing/storage. Negative stock is permitted and flagged. See [design and recovery](design.md) for the trade-offs.

Demo setup retains private progress checkpoints so an interrupted new setup can recover its own already-committed scenarios without duplicating their rejects or expected failures. The completed public demo marker remains compatible with earlier completed setups. Older incomplete setups created before progress tracking cannot safely identify prior runs from filenames alone: their audit records are preserved, and new owned examples may appear additionally. Use an unused data folder when the exact fresh baseline is needed; do not delete prior audit data to force the counts.

No secrets, GitHub upload, or final assessment submission are needed to run this package. AI generated implementation and recorded verification; candidate personal review remains pending until actually performed.

The latest [compact guidance and dynamic-status review](ui-review.md) records the final disclosure layout and status transitions.
