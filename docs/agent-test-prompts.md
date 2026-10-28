# Test and sample agent prompt history

This records the exact task prompts received by the delegated test/sample
agent. It did not generate prompts for further agents. Responses, tool calls,
and code are represented by the committed files and the main session history.
Personal local workspace paths are replaced with `[LOCAL WORKSPACE]` for privacy.

## Prompt 1

```text
We are preparing a local application for a 72-hour coding assessment. Observed brief: [confidential source wording redacted; functional requirements are documented independently in README.md]. AI use is explicitly allowed. Independently propose key correctness invariants, edge cases and focused tests for such a pipeline, without browsing the assessment site or making filesystem changes. Requirements may be refined once I read attached submission PDFs. Return concise recommendations.
```

## Prompt 2

```text
Implement tests, synthetic samples, and scalable generator under [LOCAL WORKSPACE]/inventory-ledger. Own tests/, data/, inventory/generate.py only. Core root API will be from inventory.pipeline import Inventory, PipelineError. Inventory(db_path) initializes; load_catalogs(items_csv, locations_csv); ingest(movements_csv, through='2026-01-04', fail_before_publish=False) returns run summary with run_id/status/input_count/accepted_count/duplicate_count/rejected_count/rolled_back_count/output_count; failure raises PipelineError and persists failed run. report() returns balances (all rows), runs, rejects, metrics, reconciliation. Balances columns balance_date,item_id,location_id,opening,receipts,issues,transfers_in,transfers_out,adjustments,closing as EXACT strings e.g '100.000'. SQLite internal *_milli columns. Event CSV STRICT header event_id,revision,effective_date,movement_type,item_id,location_id,to_location_id,quantity,is_void. Types RECEIPT/ISSUE/TRANSFER positive quantity; ADJUSTMENT signed nonzero. quantity max 1e9, max3dp. is_void true/false. All full payloads required even void; transfer destination distinct; references catalogs. Catalog items header item_id,unit; locations header location_id. Immutable versions (event_id,revision); identical canonical duplicate ignored; conflicting same key rejected. Highest revision wins regardless arrival, allowing late older revision. Corrections full replacements, void removes contribution. Full rebuild current view each accepted batch with continuous gap days from first posting per item/location through max(prior published horizon, --through, latest event date). Negative balances allowed flagged. Valid rows commit with rejects quarantine status succeeded_with_rejects, otherwise succeeded. CSV structural schema errors fail run; malformed individual rows reject. Empty header-only succeeds. Add focused comprehensive unittest tests happy+empty+malformed+duplicates+nulls+schema change+unknown refs+precision+backdated type/date/location corrections+void+atomic failure/retry. Use fixtures with independently hand computed expected CSV separate from input. Generator function generate(directory, rows=100000, seed=42) returns paths; creates catalogs and movements.csv with all types+out-of-order+invalid+duplicates, deterministic, use stdlib. Document its formula/counts in a short data/README.md. Root handles CLI/docs/UI. Do not touch root package/pipeline files. Log the exact prompts you've received and tasks you generate in docs/agent-test-prompts.md (allowed exception to owned dirs for transparency).
```

## Prompt 3

```text
Core exists and insert placeholder fixed. All 20 tests pass locally as of just now (with changes). Please add meaningful robustness tests for malformed CSV fatal after one accepted row (rollback+audit counts), invalid through date failure no mutation, full raw_records outcomes and run accounting on fail+retry; and reference catalog duplicate/unit change atomic rollback if useful. Review core for actual correctness gaps (read-only) while I run CLI and performance. Keep appended prompt log.
```

## Prompt 4

```text
Thanks findings all fixed including empty CSV headers; tests now29 all pass. Please final read-only audit of modified reconciliation/export and test any major gaps, and can add test for empty export headers or posting-location corruption if useful. We have server and perf run in progress. No need repeated full suite after passes unless changes. Keep prompt log updated.
```

## Prompt 5

```text
User asks whether app includes all email/challenge requirements and can be enhanced. Perform read-only independent audit of current [LOCAL WORKSPACE]/inventory-ledger against known brief and guidelines from prior context: receipts/issues/transfers/adjustments daily inventory, reconciliation, backdated corrections; runnable local; defined schemas keys relationships grain constraints; small synthetic sample plus configurable100k generator; ingestion/validation/transform/publish; rerun safe operational audit/rejects/errors; automated happy/empty/malformed/duplicate/null/reference/schema/late/partialfailure/retry domain tests; performance measurement+optimization; supporting docs/tests/outputs/prompt history/transparent AI. Find actual technical gaps or requirements not covered. No changes or test expansion yet. Return concise evidence-backed blockers vs optional enhancements. User explicitly doesn't want GitHub push; local ZIP only.
```

## Prompt 6

```text
Implement generator improvement under inventory/generate.py plus tests/test_pipeline.py/data/README.md only. User wants varied stressdata generator and showcased proof, all3 enhancements approved. Decouple item,type,location using deterministic rng / shuffled cycles so 100k contains all4 types for EACH of100items, across8locations, varieddate/lateorder, signedadjustments; keep rows exact requestedcount, fixedseed deterministic, current duplicate127precision503revision cadence/counts canpreserve existing101duplicate127invalid503revision precedence. Add dedicated generator coverage metadata file separate from input e.g coverage.json describing input types per item, counts, per-item alltypes coverage, distinctitemlocations, counts of intentionalqualitycases, generatorversion '2', fixedseed. API generate returns keys items,locations,movements plus coverage allowed existing tests may assert exact? adaptmeaningful tests. Better require per-itemall4 at100k assertions, peritemrotation can guarantee across first400 legitimate regular rows; randomat100k chance negligible but want deterministic guarantee. Keep tests rowcounts reproducibility/emptyinvalid. Root owns pipeline changes and tests/test_changes.py; do not altercore. Rootwill rerun scripts/verify.py benchmark and update oldevidence, no inventednumbers. Tests can read metadata validnormal rows (qualitycases excluded separatelylabelled). Record exactthisprompt and anyfollowups in docs/agent-test-prompts.md with localpersonalpathsredacted. Summarize newgenerator contractcounts and coverageavailable.
```

## Prompt 7

```text
Please now implement focused tests in NEW tests/test_changes.py only against root-added Inventory.changes(run_id=None,limit=100,offset=0) and balance_changes. Root owns tests/test_web.py. API schemas actual source inventory/impact.py and pipeline. Verify initial publication addedrows; correctionreceipt100to110 changes4days+10; unrelatedseries excluded; identicalrerun has_snapshot true total0; before/after retained after subsequentruns; moveddate/location removed+added; void removals; changeswithsamennetclosing but differentmovementfields included (beforeafter all7quantitycolumns); failpoint leaves noimpacts has_snapshotfalse; paginationlimitvalidation; migrations legacy runimpact_recorded0 semantics; exportheaderincludesbalancechanges. Can reviewactualsource avoidmirroringimplementation focusedbehavior. Do not change core, report any defects. Eachdelta uses textsignedinteger *_milli (two int64closesdifference canexceedint64). Newnormal snapshots may needreaderheader counts added. Fulltests expectednow30generator. Record thisexacttask docs/agent-test-prompts.md redactedpersonalpath.
```

## Prompt 8

```text
User now explicitly wants50samplemovementrecords in demo (notpagination). Implement curated default demo under data/demo/ + inventory/cli.py demo branch + NEW tests/test_demo.py; own onlythosefiles. Preserve pipeline/model/generator and existing data/sample fixtures/oracles unchanged. Requirements: movements.csv EXACTLY50distinct valid revision1 events; current_events50 afterdemo; all4movementtypes,5items ITEM-A..ITEM-E and3locationsWH-A/B/C, fractionalquantities, transferconservation,no negativestock. Preserve original data/sample7events as first7 ofnewdemo dataset and add43events ONLYforITEM-C/D/E so existing ITEM-A/B sample arithmetic/Jan4correction remains unchanged. All additionaldates2026-01-01..04; throughJan4. Enoughreceipts beforeissues/transfers to keepnonnegative. Keep event receipt-a initial100, defaultdemo stillapplies original corrections.csv rev2quantity110 (copy file into data/demo orpointsamplecorrection), making50currentevents/history51 and retained4day correction+10. Downloaded review_correction.csv rev3 120 stillraisesJan4A/WH-A75to85. Add demo catalog5items3locations. CLI demo defaultuses data/demo instead data/sample; defaultoutvar/demo remains, rerunsidempotent anddoesnot reset/deletedata. Tests meaningful: defaultdemofreshcurrent50/input50/negative0/all4types; originalA/BexpectedJan4 unchanged; repeatdemozeroacceptedbusinessunchanged; samplefixtureoriginaltestsstillpass. Record exactprompt docs/agent-test-prompts.md withpersonalpathsredacted. Reporttestcounts & rowcounts. No sample secrets, onlysynthetic. Rootwilllaunchfreshvar/stock-invento-50DB rather thanoverwriteuserexistingdb.
```

## Prompt 9

```text
Latest user: 'and also add demo data in all the levels for better understanding at our page'. Implement REAL examples for every tab while keeping50currentactive movements. Own inventory/demo.py NEW, inventory/cli.py demo branch, data/demo scenarioCSVs, tests/test_demo.py only. Root owns pipeline.report metadata plumbing. UIagent ownsallstatic. Sequence on freshdemo: current50initial andreceipt-a correctionrev2asbefore; cancel ONE existingC/D/Etransfer via higherrev2is_voidtrue, then restore sameeventviarev3nonvoid; ingest demo_quality_examples.csv with exactly3 invalid rows (excessprecision,unknownitem,same-source/destinationtransfer) and noacceptedrows; ingest demo_expected_schema_failure.csv wrongheader, catch ONLYexpected PipelineError, retainfailedrun; recover by reingesting original50movementfile ->duplicates50/nochanges. Finalcurrent50, history53,47dailyrows,0negatives,3quarantines,1intentionallyfailedrun,allreconciliationpasses. MarkerJSON under settings key 'demo_examples_v1' ensures scenarios seeded once onrerun (no duplicatebadrows/failures eachstartup), no deleting/resettinguserdata. Base two demo ingests can stillreplay eachstartup ascurrently. If crashpartial markeronlywrittenatend and retry idempotentbusiness. Metadata exactcontract JSON: {version:1,initial_movement_count:50,expected_rejected_rows:3,transfer_event_id:'actualid',runs:{initial:'uuid',correction:'uuid',cancellation:'uuid',restoration:'uuid',validation:'uuid',failure:'uuid',recovery:'uuid'}}. Rootreportreturns this as demo_examples ornull. Persist IDsactualfromingests, failureID via latest matchingDBqueryifPipelineErrorlacksattr (do not touch core). Return metadata as result.demo_examples from CLI demo too; result.runs can remainoriginaltwo to preserveexistingcontract. Filenames data/demo/demo_cancel_transfer.csv, demo_restore_transfer.csv, demo_quality_examples.csv, demo_expected_schema_failure.csv. Testsupdatehonestlyforcounts53history,rejects3,sevenexpectedrunsfresh etc, finalABsame, rerunpreservesbadcount3/noextraexpectedfailure; deliberatefailurerecovered; highesttransfer3current; originalsampletestsunchanged. Need no fakeUIplaceholder. Logexactprompt docs/agent-test-prompts.md redactedpaths. Please coordinatemetadataandcounts early withroot; do notchangefileownership.
```

## Prompt 10

```text
Please fix the confirmed interrupted-demo seeding gap. Own inventory/demo.py and tests/test_demo.py only. Keep the public completed metadata contract demo_examples_v1 unchanged and all fresh demo counts unchanged.

Retain per-scenario progress so interruption after validation/failure but before recovery does not duplicate the 3 quarantines or expected failed run. Prefer durable scenario intent/checkpoints with recovery of an already committed matching run; account for interruption between ingestion commit and progress save, not only before the next stage. Reuse only demonstrably matching seeded runs, never unrelated user runs with a coincidental filename. Preserve user data and immutable business versions. Unexpected failures must still propagate. Completed normal reruns must retain the original scenario IDs.

Add meaningful tests for interruption immediately before recovery (the reproduced gap), interruption between a scenario commit and checkpoint if the design can encounter that window, and recovery without extra rejects/failures/versions. Existing50/53/47 counts and all original tests remain. Do not edit CLI, pipeline, startup, static UI or docs. Send root the exact progress-setting contract so documentation can be updated. Record exact prompt in docs/agent-test-prompts.md, redacting personal paths.
```

## Prompt 11

```text
That robust progress design sounds good. Please use reasonably short token suffixes for readable audit filenames. Let root/UI/docs know actual naming pattern. UI and docs currently name template demo_quality_examples.csv / demo_expected_schema_failure.csv literally; we'll clarify 'based on' template because executed copies will have token suffixes. Ensure old completed markers still work unchanged, and existing incomplete setups without private progress can resume safely (new intent shouldn't reuse an unrelated filename). Keep original interruption tests updated to target the intended stage under tokenized names.
```

## Prompt 12

```text
User now requests rigorous testing against assessment mail, share scenarios/reports and include in ZIP. Build substantial independent acceptance tests in NEW tests/test_inventory_acceptance.py only (read source/tests first). Cover independent integer-thousandths oracle against daily rows over shuffled receipts/issues/transfers/signed adjustments; backdated full replacement revisions changing date/item/source/destination/type, out-of-order arrival, void/restore, duplicates/conflicts; negative balances and carry-forward; cross-item conservation and no summing units. Prefer deterministic seeded randomized scenarios, compute expected from your own event model, never call pipeline derivation helpers for oracle. Include exact corruption/reconciliation or transactional edge if useful. Do not edit runtime code unless report root a concrete failure first; root coordinates fixes. Run your new tests, report exact test IDs, assertions, iterations, result and any defects. Keep standard library only, no network needed. Log this task under docs/agent-test-prompts.md append-only. Do not run full suite or alter existing evidence/docs elsewhere.
```

## Prompt 13

```text
Additional useful rigorous test: please add one export snapshot test to YOUR tests/test_inventory_acceptance.py. Recipe from audit: wrap Inventory.report only for exporting instance so calls original with passed _connection first, then synchronously commit another ingestion via separate Inventory instance before export reads remaining raw/history/postings tables. ExportCSV/JSON must allreflectolder snapshot while liveDBnewer; check balanced quantities,currentversion/raw rows/run IDs/changes no mix. No productionedits. Runonlynewtest then report. Full verification inprogress may have discoveredearlier7; addingtest requires rootfulltestrunner rerun but canleave100kbenchmarkresultvalid. Stdlibonly.
```

## Prompt 14

```text
Newuserrequestaddnormalusername/passwordloginwithadmin/admin123, writecredentialsinSTART_HERE. Rootimplementsauth backend. Pleaseown testadaptation tests/test_web.py andtests/test_interface_acceptance.py to authenticate existingHTTPfixtures withcookie/login+CSRF so priorbehaviorcoveragecontinues. Add NEW tests/test_auth.py withmeaningful auth acceptance. Contractproposed root: GET/api/login-session returnscsrf_tokenandsetsHttpOnlypreauthcookie; POST/api/login JSONusername/password,Originlocal,X-Stockline-Tokenfrompreauthsession ->200usernameadmin andHttpOnlyauthcookie; GET/api/session authenticated{csrf_token,username,expires_in}; allreport/catalogs/showcase/changes/sample/demoGETblocked401whenloggedout; / and/index.html redirect302/login; POST/api/logout needsauthcookie+sessiontokenOrigin ->200 clears/invalidate; credentialsbootstrapadmin/admin123 PBKDF2SHA256600k iterationsrandomsaltDBtable; memorysessionsrestartinvalidate, idle30min absolute8h, rotateonlogin, throttle5failures/clientper60seconds with429RetryAfter; POSTmutationauthcheckedbeforetoken. Authclassinterface rootwillsharewhendone. ExistingtesthelpersstoreCookiefromSet-Cookie,requestusebydefaultbutguardtestanonymousneedsomitcookie. Add testsanonymousroutes/loginwrong/correct/logout/reusedcookie,missingcsrf/crossOrigin/forgedcookie,expiry+throttle via mockclock ifauthclasssupports. Do noteditproduction. NeedcoordinateowninterfaceCLItestsunchanged. Runfocusedauth/web/interfacesrequirelocalbindescalation. Report newtestcounts. Rootnewfullrun+ZIPpackaginglater.
```

## Prompt 15

```text
Backendlanded inventory/auth.py +web routes. Class AuthManager(inventory,clock=None), .begin_login()->(cookieSecret,csrf); .valid_login_token(secret,token); .authenticate(username,password,client,login_secret,old_session=None)->cookieSecret|None raisesLoginThrottled(retry_after); .session(secret)->{username,csrf_token,expires_in}|None toucheslastseen; .logout(secret). ConstantsPASSWORD_ITERATIONS600000,IDLE_SECONDS1800,ABSOLUTE_SECONDS28800,LOGIN_SECONDS600,FAILURE_WINDOW60,FAILURE_LIMIT5. HTTPserver.auth manager accessible,.auth_cookie_name=StockInventoSession_<port>,login_cookie_name=StockInventoLogin_<port>. web_usersSQLite(username,saltBLOB,password_hashBLOB,iterations), createdonlyonserver firststart, random32byte salt, normalInventoryexports omitit. BothcookiesPath/,HttpOnly,SameSiteStrict,MaxAge. Loginheadersemptylogout200accepted. Rootaddedset-password CLIhiddengetpass twice min8max1024, restartserverrevokeexisting. Addunitpasswordhashpersist/set tests+expiry/restart checks feasible. Productionnowready forfocusedtests.
```

## Final review follow-up

```text
Thanks findings all fixed including empty CSV headers; tests now29 all pass. Please final read-only audit of modified reconciliation/export and test any major gaps, and can add test for empty export headers or posting-location corruption if useful. We have server and perf run in progress. No need repeated full suite after passes unless changes. Keep prompt log updated.
```

## Import drawer update — 28 October 2026

```text
User explicitly asks every edge-case scenario / requirements verification after new import drawer. Independently run backend verification/oracles/100k/replay using existing scripts/verify.py output in var/drawer-independent-verify (do NOT overwrite current evidence until pass). Inspect supplied requirement mapping docs and any missing critical tests. No source edits unless reporting specific bug root can fix. Run necessary escalated local-server permission if needed. Report exact totals/output paths. Do not mutate var/final-review demo DB.
```
