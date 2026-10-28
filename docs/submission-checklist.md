# Local review and submission readiness

The project includes a portable local application and its source. Public GitHub publication has been authorized; see [submission status](submission-status.md) for the current repository and portal state. This checklist distinguishes supplied artifacts from candidate review and external submission. Do not mark a task complete unless its evidence exists.

| Review area | Artifact or verification | State |
| --- | --- | --- |
| Runnable source and setup | `inventory/`, `README.md`, Python standard library | Implemented with documented commands |
| Source and target schemas | `docs/data-dictionary.md` | Reconciled with implementation |
| Architecture, assumptions, trade-offs | `README.md`, `docs/design.md` | Documented |
| Starter synthetic inputs | `data/sample/` | Provided |
| Interactive teaching demo | `data/demo/`, `evidence/demo-50/` | 50 current events, 53 versions, 47 daily rows, 4 intentional negative closings, 3 rejects, 7 scenario runs on a fresh database |
| Separate expected answers | `data/expected/` | Hand-calculated initial and corrected fixtures provided |
| Another-laptop startup | `START_HERE.txt`, `run_demo.py`, platform launchers | Python standard library; local admin credentials supplied; no external account or package downloads |
| Preview and explicit browser import | Local dashboard and import endpoint | Same validation, quarantine, and publication pipeline as CLI |
| Optional catalog upload | Item/location CSV contracts and guarded local endpoint | Separate atomic step before referenced movements |
| Persisted correction impact | `balance_changes`, paginated changes API, correction view | Before/after business values; added and removed rows; no lineage-only changes |
| Local HTTP access and write controls | Admin login, loopback binding, session cookies, token and origin checks | `admin` / `admin123` documented in `START_HERE.txt`; protected reads and writes verified; local files/CLI remain OS-accessible |
| Larger deterministic generator | `inventory/generate.py`, `evidence/performance.json` | Provided with fixed seed and observed run metrics |
| Generator coverage | Separate `coverage.json`, `evidence/generator-coverage.json` | Recorded 100,000-row workload covers four types and eight source locations for every item |
| Validation and quarantine | Tests, run reports, reject output | Implemented and covered by tests |
| Corrections and safe reruns | Tests and demo report | Implemented and covered by tests |
| Failure and retry | Atomic rollback/retry test | Covered by injected-failure and retry checks |
| Current automated tests | `tests/`, `scripts/run_tests.py`, `evidence/final-review/python-tests.json`, `junit.xml`, `ui-helpers.txt` | 117 Python methods containing 222 subtest checks passed; 11 optional JavaScript checks and both browser-script syntax checks passed; zero failures/errors/skips |
| Authentication verification | `docs/auth-test-report.md`, `evidence/authentication/browser-checks.json` | Eight real-browser scenarios passed, including correction import after login, logout, browser Back, and retained data on re-login |
| Requirements and scenario traceability | `docs/test-scenarios.md`, `docs/test-report.md` | Ten implementation steps, nine negative categories, acceptance criteria, deliverables, and scoped execution evidence mapped |
| Portable clean-copy check | `docs/portable-setup.md`, `evidence/authentication/portable-check.json`; historical `evidence/rigorous/portable-check.json` | Authenticated copied-path startup/login/restart verified on macOS; earlier import/replay/export checks retained; Windows/Linux launchers reviewed |
| Output and reconciliation | `evidence/rigorous/initial/`, `corrected/`, `verification.json`, `browser-checks.json`; current authentication evidence | Historical requirements campaign plus the current authentication supplement; scopes and source snapshots identified separately |
| Performance evidence | `evidence/final-review/performance.json` | Final extracted-ZIP 100,000-row run: 4.49 seconds; 71,839 daily rows; earlier 4.83/4.60-second records retained separately; no speedup claim |
| Evidence displayed in app | Achievements & verification drop-down | Current ledger, recorded benchmark, and capabilities distinguished |
| AI disclosure and prompt records | README and AI prompt-history files in `docs/` | Candidate must inspect for completeness |
| Candidate understanding and personal review | `docs/walkthrough.md` | Pending candidate review |
| Local ZIP content review | Dedicated project, synthetic data, source, tests, safe evidence, docs | Keep runtime/personal data outside the package |
| Public repository content audit | Dedicated repository only; synthetic data; no secrets or correspondence | Required only before any later publication |
| Dedicated public GitHub repository | Public repository URL | See current submission status |
| Anonymous access verification | Open repository URL without authentication | Relevant only after any later publication |
| Final submission | Verified repository URL through the required destination | Pending final portal submission |

## Package and public content review

Share only this application's dedicated directory in the ZIP or any later public repository. Exclude the parent workspace, runtime databases, generated bulk inputs, personal information, private credentials, private recruitment correspondence, assessment PDFs, private browser screenshots, and copied confidential problem text. The user explicitly requested the shared demonstration credentials `admin` / `admin123` in `START_HERE.txt`; these known defaults are intentionally included, while generated workspace password hashes and session cookies are excluded. Retain useful source code, synthetic fixtures, safe generated evidence, and honest AI disclosure. The included dashboard/login evidence shows only the synthetic local application. The recipient's launcher creates a fresh local demo database.

Prompt history should preserve all implementation prompts available to this project while redacting private identifiers and confidential correspondence. Any gap or export limitation must be stated rather than hidden. AI responses are not necessary for the prompt record.

## Before the final submission

Confirm the repository URL is public, points to this dedicated project, and contains the intended final files. Run the README commands from a fresh checkout and compare results with the expected fixture. Review known limitations and AI disclosure. The candidate should perform the walkthrough and honestly record personal review before making any claim of personal validation.

Repository publication and final submission are external actions. Preparing this folder or starting its local dashboard does not mean either action has happened.
