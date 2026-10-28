# Test scenarios and requirement traceability

**Historical pre-authentication campaign.** The executed matrix below predates the subsequent username/password login change. Its 100-method result and source hashes remain historical evidence, not current certification of the added authentication. The [current authentication supplement](auth-test-report.md) records 117 passing Python methods containing 222 subtest checks, eleven JavaScript helper checks, eight browser scenarios, and authenticated portable verification separately.

This is the executed scenario matrix for the rigorous local verification campaign. The final Python run passed **100 test methods containing 196 recorded subtest checks**, with **zero failures, errors, or skips**, in **5.578703 seconds**. Eleven optional JavaScript checks also passed. The overall scoped conclusion and limitations are in the [test report](test-report.md).

The criteria below paraphrase the implementation expectations verified by the root reviewer. They do not reproduce private assessment correspondence, attachments, account details, or the original problem statement.

## Scope and result rules

The implementation under review is the local Stock Invento application: CSV reference data and movement ingestion, immutable revisions, postings, daily balances, reconciliation, audit/recovery, local browser operations, reproducible data, and supporting deliverables.

The result column distinguishes executed automated checks from source/document inspection and recorded browser/portable observations. Intentionally rejected records or an intentionally failed input attempt count as successful test scenarios only when the expected validation, rollback, and audit assertions pass. They do not conceal unexpected application failures.

The public GitHub upload and external challenge submission are outside this user-authorized local delivery. Candidate personal understanding/review cannot be established by automated tests. Native Windows/Linux execution is distinct from the recorded macOS runtime and launcher/syntax checks.

Evidence keys used below:

- **PY:** [per-method JSON](../evidence/rigorous/python-tests.json), [JUnit XML](../evidence/rigorous/junit.xml), and [execution log](../evidence/rigorous/unit-tests.txt). The subtests are parameterized checks inside the 100 methods, not 196 additional test methods.
- **JS:** [eleven source-level helper checks](../evidence/rigorous/ui-helpers.txt): six same-realm queue cases and five example-toggle cases. Node is optional and is not an application runtime dependency.
- **BENCH:** [fresh 100,000-row verification](../evidence/rigorous/verification.json), [performance](../evidence/rigorous/performance.json), [coverage](../evidence/rigorous/generator-coverage.json), and initial/corrected output folders. Measured ingestion/reconciliation was **4.832275 seconds**; 98,230 versions were accepted, 990 rows were duplicates, 780 deliberately invalid rows were rejected, and 71,839 daily rows were published. All fifteen reconciliation checks passed; replay preserved business output and added zero changes.
- **BROWSER / PORTABLE:** recorded [browser checks](../evidence/rigorous/browser-checks.json) and [clean-copy portable checks](../evidence/rigorous/portable-check.json). Runtime observation used macOS; other native operating systems remain explicitly unexecuted.
- **INSPECTED:** source, schemas, documents, or supporting files checked directly. Final ZIP integrity/content verification is a separate packaging step and is not counted as an automated application test.

The 100,000-row benchmark ran after both runtime fixes. The final Python rerun included the concurrent-export and report-reliability regressions; its 100-method result and source hashes are authoritative for the final Python count. The verification metadata explains this sequence.

## Ten implementation steps

| ID | Paraphrased implementation criterion | Source and review material | Scenario/evidence to verify | Current campaign |
| --- | --- | --- | --- | --- |
| I01 | Explain setup, data definitions, architecture, and assumptions | [README](../README.md), [portable setup](portable-setup.md), [data dictionary](data-dictionary.md), [design](design.md) | Check commands against launchers and CLI, keys/grains/nullability, correction policy, limits, and complete ZIP contents | Inspected + PORTABLE |
| I02 | Provide modular processing with configurable paths/parameters | [CLI](../inventory/cli.py), [launcher](../run_demo.py), [pipeline](../inventory/pipeline.py) | CLI init/run/report/export/serve; independent data folder; project-relative and absolute launcher paths; alternate port | Passed — PY + PORTABLE |
| I03 | Validate schema/business rules, handle duplicates, quarantine invalid rows | [model](../inventory/model.py), `Inventory.ingest`, `load_catalogs` in [pipeline](../inventory/pipeline.py) | Required fields, references, quantities, transfer rules, normalized duplicates, immutable-key conflicts, row versus batch failure | Passed — PY |
| I04 | Expose operational status, timing, counts, rejects, and errors | Run/raw-record storage and logging in [pipeline](../inventory/pipeline.py) | UUID run IDs, ISO UTC start/end, source filename/physical line, one outcome per consumed row, explicit failed audit and visible errors | Passed — PY |
| I05 | Automate happy, empty, malformed, duplicate, null, and domain-edge behavior | [pipeline tests](../tests/test_pipeline.py), [change tests](../tests/test_changes.py), [demo tests](../tests/test_demo.py) | Independent sample oracle, negative categories below, backdated propagation, transfer conservation, void/restore, exact fractional quantities | Passed — PY |
| I06 | Make loads safe to replay, retry, restart, and backfill | Transactional publication in [pipeline](../inventory/pipeline.py), checkpoint recovery in [demo](../inventory/demo.py) | Injected publication failure, malformed CSV after a valid prefix, hard process termination, retry, duplicate replay, late revisions and historical rebuild | Passed — PY |
| I07 | Supply reproducible synthetic samples and a configurable larger generator; keep answers separate | [small inputs](../data/sample/), [independent answers](../data/expected/), [interactive demo](../data/demo/), [generator](../inventory/generate.py) | Byte-identical seed/count output, exactly requested rows, separate coverage metadata, all four types and all source locations per item at 100,000 rows | Passed — PY |
| I08 | Demonstrate correctness through counts, aggregates, and reconciliation | `_reconcile` in [pipeline](../inventory/pipeline.py), [verification runner](../scripts/verify.py) | Source/posting mappings, transfer neutrality, daily equation/continuity, movement totals by grain, per-item closing totals, raw-row accounting, deliberate corruption detection | Passed — PY |
| I09 | Record performance and explain a reasonable optimization | [verification runner](../scripts/verify.py), [design trade-offs](design.md) | Fresh 100,000-row run with environment, measured duration and counts, replay equality; distinguish measured workload from current demo; describe affected-key/date rebuild as an optimization | Verified — BENCH + inspected design |
| I10 | Package runnable code, tests, sample inputs/outputs, schema, setup, and design notes | Project root, `inventory/`, `tests/`, `data/`, `docs/`, `evidence/` | Final archive manifest, clean extracted-copy start, evidence paths, no missing local assets or required packages, honest AI disclosure | Source/deliverables inspected |

## Nine required negative categories

| ID | Input/action | Expected behavior | Existing automated coverage inspected | Current campaign |
| --- | --- | --- | --- | --- |
| N01 | Malformed values, wrong row width, or invalid CSV structure | Invalid individual records are traceable rejects; a fatal parser error rolls back the batch and retains consumed-row audit | `test_malformed_rows_are_quarantined_while_valid_rows_commit`, `test_wrong_row_width_rejects_only_bad_rows`, `test_fatal_csv_after_valid_row_rolls_back_and_retains_raw_audit` in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| N02 | Missing required value/null-equivalent CSV field | Reject with a field/schema reason; valid neighboring rows may publish | `test_malformed_rows_are_quarantined_while_valid_rows_commit` in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| N03 | Identical duplicate or conflicting event/revision key | Equivalent normalized content adds no stock/version; conflicting content is quarantined and cannot overwrite history | Duplicate/conflict tests in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| N04 | Unexpected, missing, duplicate, or empty header/schema | Fail explicitly without replacing the prior inventory state; record the failed attempt | Header tests in [pipeline tests](../tests/test_pipeline.py), `test_bad_schema_fails_without_replacing_previous_balances` in [HTTP tests](../tests/test_web.py) | Passed — PY |
| N05 | Header-only empty batch | Succeed with zero inputs; preserve existing business balances and report explained counts | Header-only/empty-batch tests in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| N06 | Partial failure followed by retry | Versions, postings, balances, and impact rows publish together or roll back; prior state stays intact; retry applies new data once | Failpoint/mixed-batch tests in [pipeline tests](../tests/test_pipeline.py), failed-impact tests in [change tests](../tests/test_changes.py), hard-stop regression in [resilience tests](../tests/test_resilience_acceptance.py) | Passed — PY |
| N07 | Late or out-of-order events/revisions | Effective business dates control balances; maximum valid revision wins independently of arrival; rebuild agrees across shuffled/split ingestion | Older-revision, backdated-correction, transfer-correction, and shuffled-batch tests in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| N08 | Unknown item/location/destination or incompatible catalog change | Reject invalid references; catalog additions and unit validation are atomic | Invalid-reference and catalog rollback tests in [pipeline tests](../tests/test_pipeline.py), catalog endpoint test in [HTTP tests](../tests/test_web.py) | Passed — PY |
| N09 | Replay the same valid source | No extra current stock or versions; a new operational attempt is retained; business-only impact is empty | Duplicate/replay tests in [pipeline tests](../tests/test_pipeline.py), [change tests](../tests/test_changes.py), [demo tests](../tests/test_demo.py), and [HTTP tests](../tests/test_web.py) | Passed — PY |

## Domain and product scenarios

| ID | Scenario | Expected result and source/test coverage | Current campaign |
| --- | --- | --- | --- |
| S01 | Receipt, issue, transfer, and signed adjustment at exact decimal precision | Match separate hand-calculated CSV oracles and a distinct integer stock-transition reference model across six fixed seeds and split/shuffled batches; [pipeline tests](../tests/test_pipeline.py), [independent business acceptance](../tests/test_inventory_acceptance.py), [expected answers](../data/expected/) | Passed — PY |
| S02 | Transfer, changed transfer, cancellation, and restoration | Source/destination legs agree and conserve one item's stock; both affected locations rebuild; [pipeline tests](../tests/test_pipeline.py), [demo tests](../tests/test_demo.py) | Passed — PY |
| S03 | Backdated full replacement changes quantity/date/type/item/location/destination | Old contribution is removed, new contribution is applied once, later openings/closings update, unrelated series remain unchanged; [pipeline tests](../tests/test_pipeline.py), full replacement/arrival-order matrix in [independent business acceptance](../tests/test_inventory_acceptance.py) | Passed — PY |
| S04 | Void removes a series and a later revision restores it | Current postings/balances follow highest valid revision; immutable history and removed/added before-after snapshots remain traceable; [pipeline tests](../tests/test_pipeline.py), [change tests](../tests/test_changes.py) | Passed — PY |
| S05 | Gap dates, leap day, maximum supported calendar date, and non-shrinking horizon | Continuous carried balances, no date overflow, later publication horizon retained; calendar/horizon tests in [pipeline tests](../tests/test_pipeline.py) | Passed — PY |
| S06 | Valid negative stock and separate invalid records | Four seeded negative closing rows are accepted-data warnings, three bad source records are quarantined, and mathematical reconciliation still passes; [demo tests](../tests/test_demo.py), [demo notes](../data/demo/README.md) | Passed — PY |
| S07 | Retained correction comparisons | Added/removed/updated rows contain exact seven-quantity snapshots, same-closing measure changes remain visible, lineage-only replay adds no impact, failed/legacy runs are distinguished, pagination is stable; [change tests](../tests/test_changes.py) | Passed — PY |
| S08 | Local CSV/catalog HTTP workflow | Preview is non-mutating; explicit import publishes valid rows and visible rejects; origin/token/host, filename, type, UTF-8/JSON, size, and catalog atomicity checks operate; [web source](../inventory/web.py), [HTTP tests](../tests/test_web.py), [CLI/HTTP acceptance](../tests/test_interface_acceptance.py) | Passed — PY + BROWSER |
| S09 | Browser request queue and example toggle | Forced refresh follows earlier reads/failures; final tail alone releases busy; opening/closing example restores prior filters/page and respects later manual choices; [JavaScript](../inventory/static/app.js), [optional helper checks](../tests/ui_refresh.test.cjs) | Passed — JS + BROWSER |
| S10 | Fresh local package and persistent restart | Launch from copied path with spaces/different working directory, use a distinct data folder/port, perform real local correction/replay, export, stop and restart without losing data; [launcher tests](../tests/test_startup.py), final portable/browser proof supplied by root | Passed — PY + PORTABLE |
| S11 | Interrupted demo setup | Owned committed scenarios recover even before checkpoint save; unrelated filename collisions are not claimed; old completed markers work; user data is retained; [demo source](../inventory/demo.py), [demo tests](../tests/test_demo.py) | Passed — PY |
| S12 | Stable lineage, ordering, and extreme exact arithmetic | Deterministic posting IDs, ISO audit lineage, identical report/latest-impact ordering for timestamp ties, and no floating-point promotion at valid int64 equation boundaries; four [resilience regressions](../tests/test_resilience_acceptance.py) | Passed — PY |
| S13 | Concurrent export and import coordination | A held writer leaves readers on the prior complete publication and rejects a second browser import with 409; [CLI/HTTP acceptance](../tests/test_interface_acceptance.py). `test_export_keeps_one_snapshot_when_another_writer_commits_mid_export` in [business acceptance](../tests/test_inventory_acceptance.py) verifies that all exported datasets remain on the earlier snapshot while the live database advances | Passed — PY |
| S14 | Reliable conditional test reporting | A failed rerun removes stale PASS artifacts; a successful run writes matching JSON/JUnit and removes the old failure log; both [reporting regressions](../tests/test_reporting.py) passed | Passed — PY |

## Acceptance criteria

| ID | Criterion | Verification basis | Current campaign |
| --- | --- | --- | --- |
| A01 | Primary keys, nullability, uniqueness, and references are enforced | Input/model validation, SQLite keys/FKs, duplicate/conflict and catalog tests; [schema](data-dictionary.md), [pipeline](../inventory/pipeline.py) | Passed — PY |
| A02 | Transformation and business identities are deterministic | Integer arithmetic, explicit revision semantics, stable posting IDs, shuffled-input equivalence, independent sample oracle | Passed — PY |
| A03 | Source/target counts and key aggregates reconcile or explain differences | Reconciliation checks plus run-level accepted/duplicate/rejected/rolled-back accounting; history/current/posting/daily grains explicitly differ | Passed — PY |
| A04 | Invalid or anomalous records remain traceable | Source filename, ending physical CSV line, raw JSON, run ID, reason, visible quarantine/negative warnings and failed attempts | Passed — PY + BROWSER |
| A05 | Repeated input creates no unintended business duplicates | Existing versions and daily quantities remain unchanged; new audit runs and zero business-impact snapshots are intentional | Passed — PY |
| A06 | Required automated tests and verification checks pass | Refreshed full Python log, optional JavaScript log, sample/large-run verification outputs; no result inferred from test names alone | Passed — PY + JS + BENCH |
| A07 | Clean-environment setup and run instructions are reproducible | Python-only standard-library startup, complete extraction, portable path/port/persistence proof, documented platform limits | Verified — PORTABLE |

## Deliverable checklist

| ID | Deliverable | Expected archive content | Current campaign |
| --- | --- | --- | --- |
| D01 | Executable source and setup files | `inventory/`, `run_demo.py`, platform launchers, `pyproject.toml`, README and portable instructions | Source inspected; PORTABLE passed |
| D02 | Reproducible source data or generator | `data/sample/`, `data/demo/`, `data/expected/`, generator and separate coverage metadata | Inspected + BENCH passed |
| D03 | Automated tests and execution evidence | `tests/`, scenario matrix, refreshed execution logs, final conditional report | Executed evidence provided |
| D04 | Outputs and reconciliation | Initial/corrected/demo exports, exact before-after examples, reconciliation, measured larger-run result | Verified — PY + BENCH |
| D05 | Architecture, assumptions, limits, and reasoning | README, dictionary, design, walkthrough, portable guide, honest AI prompt/disclosure records | Inspected; personal review separate |

## Independent audit findings and resolution

1. **Run-order tie inconsistency — fixed and regression passed.** Report ordering and latest-impact selection now share the insertion-order tie-break. `test_same_millisecond_runs_share_one_latest_audit_order` passed in the final suite.
2. **Extreme integer-boundary equation check — fixed and regression passed.** The daily equation check now uses Python integers. `test_daily_equation_remains_exact_when_intermediate_sum_exceeds_int64` verifies both signs and still detects one-thousandth corruption.
3. **Concurrency coverage — executed.** Held-writer report/busy-import behavior and a concurrent commit during export passed their targeted regressions. No unexecuted concurrency claim is used as evidence.
4. **Stale PASS artifacts after a failed rerun — fixed and regression passed.** The structured test runner invalidates earlier success artifacts on failure and keeps success/failure outputs consistent. Both reporting self-checks passed in the final suite.

## Reproduce and interpret the result

From the project root, use fresh output folders:

```sh
python3 scripts/run_tests.py --out var/test-results-new
python3 scripts/verify.py --rows 100000 --out var/verification-new
```

The [structured runner](../scripts/run_tests.py) writes Python JSON/JUnit/log evidence on a clean run and invalidates stale success artifacts on a failed rerun. Choose unused output folders to retain earlier runs; inspect exit status, timestamps, and recorded source hashes. Optional JavaScript checks run with `node tests/ui_refresh.test.cjs`. Browser and package checks have separate evidence and are not implied by the Python runner alone.

No unresolved mandatory local implementation defect was identified after the fixes and final executed checks. This scoped result does not imply GitHub publication, external submission, candidate personal review, native execution on untested operating systems, or production hosting readiness. Repository/deadline/submission obligations remain separate from software test results.
