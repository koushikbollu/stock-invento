# AI use and prompt history

Codex and three delegated AI agents generated this implementation, tests, sample
data, interface and documentation. The agents reviewed the code and performed the
recorded automated and browser checks. Candidate review is still pending. AI use
was explicitly permitted by the instructions read for this project.

## User request 1

The original task prompt is reproduced below with the private account identifier
redacted. The source email, assessment PDFs, and confidential assessment text are
not reproduced in this repository.

```text
i have opened a gmail in chrome for account [PRIVATE ACCOUNT REDACTED] its a test can u please look into it and share the required application in the submission format with the exact solution and also follow all the guidelines if needed for making the app work then break those guidlines use [@Computer](plugin://computer-use@openai-bundled)
```

## User request 2

```text
do not push the project to git hub i want to review it by opening it in a different laptop and run it locally share the project into a zip file save it on the desktop if its done
```

## User request 3

```text
can we enhance this app like did we add all the things which are required, mengtioned in the mail?
```

## User request 4

```text
improve them and add them in the display for flexing the improvements we have done
```

## User request 5

```text
is this name given in the requirement stockline? can we change it?
```

## User request 6

```text
make it stock Invento instead stock line deploy it in local again for demo i want ti review it
```

## Delegated prompts

The implementation prompts and follow-up instructions sent to the three AI
agents are recorded in:

- [Tests, synthetic data and generator](agent-test-prompts.md)
- [Dashboard and browser verification](agent-dashboard-prompts.md)
- [Documentation](agent-documentation-prompts.md)

The primary agent wrote the core model, transactional pipeline, CLI, verification
script, launchers and packaging, integrating the delegated work and correcting
defects found by tests and review. No existing complete inventory solution was
imported. No further AI tools were used outside these agents in this session.

## Record limitations and redactions

These are a manually maintained record of the user and delegated implementation
prompts available in this session. The environment did not provide a complete
conversation export. Tool calls, AI responses, and internal reasoning are not
included; responses are optional under the project instructions. Private account
identifiers, local personal paths, recruitment timing and source confidential
wording are redacted where present. Those redactions preserve privacy; they do
not conceal an additional implementation tool or source.

The candidate should read the walkthrough and source, rerun verification, and
only then record any personal changes or validation actually performed.

## Delegated brand review prompt

```text
Rename requested: user says 'make it stock Invento instead stock line deploy it in local again for demo i want ti review it'. Read-only audit only: identify user-facing brand/name references in docs/startup/metadata that should say Stock Invento and any important rename caveat. Do not edit; root will change title/wordmark/footer/README/START_HERE, preserve technical inventory-ledger module/folder and existing internal session header to avoid functional churn. Historical AI prompt records must remain exact. Return concise.
```

## User request 7

```text
keep the achievments and steps for the process in drop downs i guess that makes the ui more good?
```

## Delegated disclosure review prompt

```text
User requests achievements and process steps in drop-downs for cleaner UI. Root will edit index.html/style.css, using native <details>/<summary> collapsed by default: top showcase remains region but wraps all achievement feature/evidence content in #achievements-dropdown with summary 'Achievements & verification', version and chevron; process aside wraps steps/samplelinks in #process-dropdown summary 'Process guide'. Please provide a quick read-only accessibility/UX review of this approach and any risks with existing JS contracts. Do not edit files or run tests. Historical data and imports unchanged. Reply concise.
```

## User request 8

```text
make ui more beautiful to look i dont feel its good
```

## Delegated UI contract audit prompt

```text
User asks for a much more beautiful UI. Dashboard agent is redesigning static HTML/CSS, preserving all IDs/flows. Please perform independent read-only audit of inventory/static/app.js and index.html for UI functional contracts that redesign must preserve (generated classes, specific selector assumptions, controls/IDs, display/hidden behavior). Return concise prioritized checklist to root and dashboard agent if helpful. No edits/tests needed. Focus accessibility and responsive usability, not business pipeline.
```

## User request 9

```text
current UI is really good keep this same but change the colour to previous green that was unique and also the number records to 50
```

## User clarification

The user selected this answer when asked whether 50 meant rows per page or sample movement records:

```text
Load 50 sample movement records
```

## User request 10

```text
move the process guide also into the bottom do not keep it side its not looking good make the guidelines colour a bit dark green for both the drop downs at bottom
```

## User request 11

```text
and also add demo data in all the lvels for better understanding at our page
```

## Additional testing requests — 28 October 2026

```text
now do some rigorous testing using the requirements mentioned in the mail and share those test scenerios and reports and add them in the zip file
```

```text
add the report if the app works as expected onlyu
```

```text
did we follow all of these instructions and enabled all the requirements? in our app 
after checking this do the testing and generate the report
```

The user also supplied the assessment brief as a pasted text attachment. It was
reviewed for requirement traceability. Its confidential source text and private
attachment path are excluded from this distributable project; the scenario
matrix paraphrases the implementation criteria and links code and evidence.

```text
so now if i share the zip anycone deploy this app in their local?
```

### Primary-agent verification work

The primary agent added real process-termination/retry and stable identity/audit
checks, reproduced and fixed the timestamp-tie ordering defect and SQLite
intermediate floating-point promotion defect, and added regression tests. It
also added a standard-library per-test JSON/JUnit runner and tests that ensure a
failed rerun cannot leave stale PASS test artifacts. The full verification
runner likewise invalidates an older overall PASS before a new attempt.

The primary agent ran the full suite, independent sample checks, a fresh
100,000-record benchmark and replay, fifteen real browser scenarios in an
isolated database, copied-package startup/import/export/restart checks, and ZIP
content/hash checks. The conditional final report was written after the
application checks passed. No external publication or assessment submission
was performed. The delegated tasks and their available follow-ups are recorded
in the linked agent prompt logs; this paragraph is a work summary, not an
additional user prompt.

## Local username/password login — 28 October 2026

```text
do this username/password login give user name as admin and passwrd as admin123
```

```text
mention those details in the zip start here
```

The primary agent implemented the database password hash, expiring in-memory
sessions, login and logout routes, server-side API authorization, CSRF/origin
checks, failed-login throttling, and a hidden-prompt password-change command.
The dashboard agent added the sign-in page and account/sign-out controls; the
test agent added authentication coverage and updated HTTP fixtures. The primary
agent added password-CLI tests, ran the complete suite and browser workflows,
verified authenticated portable startup, and refreshed the ZIP and evidence.
Default demonstration credentials are included at the user's explicit request;
actual runtime account hashes, cookies, sessions, and databases are excluded.

## Compact information panels — 28 October 2026

```text
Demo example keep this as a simple drop down for all the tabs its not looking good
```

```text
Seeded demo this and Review required this and Valid rows commit. Invalid rows go to quarantine. this also
```

```text
Review required this came twice
Refreshed 05:34 AM
Review required · 3 rejected source rows · 4 negative balance days · 1 failed ingestion run in audit history
```

```text
move these Review required and Seeded demo under the Current events
50 Active latest revisions, excluding voids
Daily balance rows
47 2026-01-01 → 2026-01-04
Rejected rows
3 Across recorded ingestion runs
Negative stock days
4 Review stock availability
```

Markdown emphasis was normalized in these UI requests. The implementation uses
native disclosures, preserves their state across refresh, removes the duplicate
status heading, and places workspace notices beneath the metric cards. The
inventory and authentication behavior remain unchanged. Browser checks, the
existing JavaScript checks, and regression evidence accompany the final ZIP.

```text
so this review required only comes up if there any negative or rejected records right? it should be dynamic
```

A separate authenticated workspace verified Ready → Up to date → Review required
after negative stock → Up to date after correction → Review required after a
rejected input. The user's demonstration database was preserved.

## Final audit request — 28 October 2026

```text
check evrything and finalise and finally rate our app are we going to pass our test?
```

Three delegated read-only reviews checked functional correctness, local
interface/authentication, and requirement/documentation readiness. The primary
agent freshly extracted the Desktop ZIP, checked every manifest hash, reran the
complete suite and independent sample oracles, measured another 100,000-record
run and replay, checked the existing index query plan, clarified documentation
provenance, and verified the final package again. No evaluator outcome was
claimed or guaranteed, and no external upload/submission was performed.

## Import drawer and verification — 28 October 2026

```text
make the import movements into a openable drawer instead of showing up directly just like a custom action?
```

```text
why is it mentioned twice as custom action and also in the tabs section at header?
```

```text
test every edge case scenerio and make sure everything works as in the requirement
```

The primary agent implemented the native dialog, removed the duplicate navigation entry, verified browser interactions in an isolated synthetic workspace, and recorded a final-source regression run. Read-only agents reviewed drawer contracts and independently reran the requirement/oracle/100,000-row workflow; the documentation agent updated the walkthrough and portable instructions. The report distinguishes executed coverage from an exhaustive guarantee and retains the external submission/personal review limitations.

## Included import CSVs — 28 October 2026

```text
add the csv files also in the zip for testing couple of imports and mention it in the start here
```

The primary agent added separate practice catalogs, numbered movement CSVs and an independent answer sheet, verified their sequence/replay in temporary workspaces, and rebuilt the existing Desktop ZIP. The documentation agent updated START_HERE.txt with the import order and expected outcomes. Application code and the user's saved demo data were unchanged.

## Public repository preparation - 28 October 2026

The user authorized checking the assessment email again and publishing the project to GitHub. Their account identifier is redacted from this record. They also asked whether uploading only the ZIP met the expectation; the primary agent clarified that the extracted source, tests, fixtures, documentation, outputs and prompt records belong in the public repository. A clean copy of the final package was checked for private content, and its complete Python and practice checks plus JavaScript helper checks were rerun before publication. No private correspondence, raw assessment text or account authorization codes are included. Publication commits are current snapshots grouped by purpose, not a reconstruction or backdating of earlier development history. Portal submission and the candidate's personal review remain separate.
