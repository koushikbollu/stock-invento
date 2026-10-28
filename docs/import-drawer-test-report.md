# Import drawer and requirements verification

**PASS for all executed checks.** Reviewed on 28 October 2026 (India Standard Time).

Import movements is now a right-side modal drawer opened by the single **Import CSV** button in the page header. The duplicate navigation entry was removed. Close, Escape, and a backdrop click dismiss it; the same form stays mounted so files, dates, previews, disclosure state and results survive closing/reopening and Refresh data. View this run’s balance impact closes the drawer and focuses Correction impact. The main 50-event demo was preserved.

## Executed verification

| Check | Result |
| --- | --- |
| Final-source Python suite | 117 methods / 222 subtest checks, zero failures, errors or skips |
| JavaScript helper suite | 11 passed (refresh sequencing and example toggle) |
| Browser drawer scenarios | 14 passed, detailed below |
| Independent initial and corrected sample oracles | Exact matches; 15 reconciliation checks passed |
| Backdated receipt correction | Four daily changes, each +10.000; closing 75.000 → 85.000 |
| Fresh 100,000-row generator workload | 98,230 accepted versions, 990 duplicates, 780 intentional rejects |
| Large-run publication | 98,034 current events, 71,839 daily rows; all 15 reconciliation checks passed |
| Measured ingestion plus reconciliation | 5.120468 seconds on this macOS/arm64/Python 3.14.6 run |
| Replay | Zero accepted versions and zero changed daily rows; exact business outputs preserved |
| Closing a pending browser import | A real 50,000-row upload completed exactly once after closing/reopening |
| Fresh extracted ZIP startup and restart | Passed login, 50-record seeding, correction/replay, persistence and session revocation |

See [final-source Python results](../evidence/import-drawer/final-source/python-tests.json), [JUnit](../evidence/import-drawer/final-source/junit.xml), [execution log](../evidence/import-drawer/final-source/unit-tests.txt), [JavaScript results](../evidence/import-drawer/ui-helpers.txt), [browser scenarios](../evidence/import-drawer/browser-checks.json), and [browser run counts](../evidence/import-drawer/browser-audit-counts.json). The [fresh extracted-package check](../evidence/import-drawer/portable-check.json) verified a path containing spaces and a different invoking directory, documented login, the final drawer source, correction/replay, persisted data, and session revocation on restart. This check preceded only the addition of its own proof artifact and this report note; the final rebuild verifies archive integrity and source identity again.

The separate [requirements verification](../evidence/import-drawer/requirements-check/verification.json), [measured workload](../evidence/import-drawer/requirements-check/performance.json), [coverage](../evidence/import-drawer/requirements-check/generator-coverage.json), and initial/corrected exports are included.

The independent requirements run finished before the final small drawer event-handler refinement. Backend files were unchanged. The later final-source suite and browser checks identify the final UI revision; historical evidence is retained with its own source hashes.

## Browser scenarios

| ID | Scenario | Result |
| --- | --- | --- |
| DRAWER-01 | One header Import CSV action; import form hidden at initial load | PASS |
| DRAWER-02 | Open drawer, focus Close, choose CSV, show literal preview | PASS |
| DRAWER-03 | Keyboard stays within modal; Escape returns focus to Import CSV; draft date/file preview remain on reopening | PASS |
| DRAWER-04 | Actual correction import: accepted1, no rejects, four changed days; View balance impact closes drawer and focuses selected Correction impact tab | PASS |
| DRAWER-05 | Client rejects empty, malformed UTF-8 and >10MiB files; submit disabled; clear messages | PASS |
| DRAWER-06 | Bad CSV schema returns visible failed run; drawer remains usable and no version published | PASS |
| DRAWER-07 | Retry after fatal failure succeeds; duplicate correction accepts0 and changes0; Close -> Refresh data -> reopen preserves file and result | PASS |
| DRAWER-08 | Mixed upload publishes valid0.001 record, quarantines HTML-like ID literally, warning+counts visible | PASS |
| DRAWER-09 | Single catalog disables submit; selected item catalog and disclosure survive close; both files load atomically (5 items/3 locations) | PASS |
| DRAWER-10 | Close/reopen during real 50,000-row import preserves request: Working remains, controls locked, Close enabled; final result accepted50,000, no duplicated submission | PASS |
| DRAWER-11 | Desktop1280x900 drawer right-aligned660px, no horizontal overflow; backdrop click closes and restores opener focus | PASS |
| DRAWER-12 | Mobile390x844 full-width drawer has no horizontal overflow; reference forms scroll; sticky Close remains in viewport | PASS |
| DRAWER-13 | Legacy #import-section link opens drawer; close normalizes to #main; five repeated open/Escape cycles preserve closed state and aria-expanded=false | PASS |
| DRAWER-14 | HTML-like quarantined payload remains literal text (zero inserted images); Sign out revokes access and legacy import link redirects to login | PASS |

The desktop viewport was 1280×900 and the mobile viewport was 390×844. The drawer had no horizontal overflow at either size; on mobile, catalogs scrolled while Close remained reachable. Preview and quarantine render HTML-like content as literal text. [Desktop](../evidence/import-drawer/desktop.png) and [mobile](../evidence/import-drawer/mobile.png) screenshots are included.

## Requirement coverage

The [requirement traceability matrix](test-scenarios.md) maps ten implementation steps, nine negative-input categories, acceptance criteria and deliverables. This campaign reran the complete current Python suite, including its added authentication checks, together with the independent balance oracles and larger workload. It covers receipts, issues, transfers, signed adjustments, precision and negative stock, missing/invalid references, schema changes, malformed/null/duplicate input, conflicting revisions, late/out-of-order revisions, void/restore, backfill, failed atomic publication, rollback and retry, replay, hard interruption recovery, concurrent readers/writers, consistent exports, HTTP validation/size/origin/token rules, login/session expiry/logout, and conditional test reporting. No unresolved local functional defect was found in this scope.

No finite suite proves every possible input, browser or operating system. Runtime checks were on macOS; Windows/Linux native execution and physical mobile devices remain untested. Benchmark timing is one measurement, not a capacity guarantee. Public GitHub/portal submission and the candidate’s personal walkthrough remain separate pending steps. Earlier reports remain historical records, not proof that those external steps occurred.

## Reproduce

From the extracted project folder:

```sh
python3 scripts/run_tests.py --out var/new-test-results
node tests/ui_refresh.test.cjs
python3 scripts/verify.py --rows 100000 --out var/new-verification
```

Node is only needed for the optional helper checks. The app and Python tests use the standard library. Follow the scenario table in an isolated demo workspace for browser checks; use the normal launcher and its documented username/password for review. Closing the drawer does not cancel an import already submitted.
