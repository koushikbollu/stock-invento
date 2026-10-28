# Practice CSV imports

These eight small UTF-8 CSV files are included in the ZIP. Two reference catalogs and three basic movement uploads are enough to try the workflow; the last three movement files are optional validation/negative-stock exercises. All records are synthetic.

Use the extracted project folder. For repeatable results, start an unused workspace:

```sh
python3 run_demo.py --data-dir var/practice-new --port 8766
```

On Windows, use `py -3` instead of `python3`. If that data folder was already used, choose another unused name. Sign in using the credentials in START_HERE.txt. Practice imports change only the workspace you choose; its counts will increase above the original 50-event demo.

## 1. Load the two practice catalogs

Click the main header's **Import CSV** button. Expand **Using new item or location IDs?**. Select `00_items.csv` for Item catalog CSV and `00_locations.csv` for Location catalog CSV, then click **Validate & load catalogs**. These are catalog files: do not upload them in the movement picker. Both are loaded together; loading them again is safe.

The catalogs add `PRACTICE-ITEM` (unit EA) and locations `PRACTICE-MAIN` and `PRACTICE-BRANCH`. They are separate from the seeded demo accounts, so existing demo quantities do not affect the expected results below. Importing the movement files before loading these catalogs will quarantine their unknown references; load the catalogs and retry.

## 2. Import the basic movement files in order

Use **Choose a movement CSV**, inspect the preview, and click **Import & publish** once per file. Leave **Publish through date** blank; the fresh demo already publishes through 2026-01-04. After an import, **View this run’s balance impact** opens Correction impact.

| File | Expected first-import result | Closing on 2026-01-04: MAIN / BRANCH |
| --- | --- | --- |
| `01_receipts.csv` | 2 accepted; receipts of 100 MAIN and 25 BRANCH | 100.000 / 25.000 |
| `02_issues_transfers_adjustments.csv` | 3 accepted; MAIN issue15, transfer20 to BRANCH, adjustment−2.500 | 62.500 / 45.000 |
| `03_backdated_correction.csv` | 1 accepted; MAIN's Jan1 receipt is replaced by revision2, quantity120 | 82.500 / 45.000 |

Select **Daily balances**, filter Item to `PRACTICE-ITEM`, and inspect 2026-01-04 for both locations. The backdated correction increases MAIN's closing by 20.000 on all four days, keeping the revision1 receipt in Event history. BRANCH is unaffected by that correction. After step3: MAIN = 120 − 15 − 20 − 2.500 = 82.500; BRANCH = 25 + 20 = 45.000.

Try importing the same valid file again: accepted0, duplicate count equal to its row count, and zero balance changes. Reopening the drawer retains your selection; previewing alone does not import it.

## 3. Optional edge-case exercises

Run these only after steps1–3, in this order:

| File | Expected first-import result | Closing on 2026-01-04: MAIN / BRANCH |
| --- | --- | --- |
| `04_mixed_valid_and_invalid.csv` | 1 accepted + 3 quarantined; valid BRANCH receipt10 publishes | 82.500 / 55.000 |
| `05_negative_stock.csv` | 1 accepted; MAIN issue100 causes negative stock on Jan3 and Jan4 | −17.500 / 55.000 |
| `06_fix_negative_stock.csv` | 1 accepted; revision2 replaces that issue with quantity60 | 22.500 / 55.000 |

File04 intentionally contains an unknown item, quantity precision1.0001, and a transfer to the same location. Review the three reasons in **Quarantine**; invalid rows have no stock effect. Replaying file04 yields accepted0, duplicates1 and three newly recorded quarantined rows, with unchanged stock. This is expected audit history.

File05 produces an accepted-data warning, not quarantine. File06 fixes the practice negative balances while retaining both issue revisions. The seeded demo already has rejected rows, negative-stock examples and a failed teaching run, so the global **Review required** notice can remain after the practice balance is corrected. Filter `PRACTICE-ITEM` to review this exercise specifically.

## Expected answers and verification

The hand-calculated [expected balances](../expected/import_practice_balances.csv) are stored separately from input. That CSV is an answer sheet, not a movement upload. It contains all eight practice daily rows after each stage (Jan1–4 at two locations). Results assume this sequence starts with unused practice IDs and no unrelated practice changes.

The [recorded verification](../../evidence/import-practice/verification.json) executes the actual files in isolated fresh seeded workspaces, checks the answer sheet, accepted/rejected counts, reconciliation, replay, and preservation of the original demo balances. The runtime application code is unchanged by these additional fixtures.

Re-run this file-sequence check from the project folder (no packages required):

```sh
python3 scripts/verify_practice_imports.py --out var/practice-file-verification.json
```

It uses a temporary database and leaves your saved workspace intact. The seeded demo intentionally records its teaching failure before recovery; the verifier writes `passed: true` only after the practice checks succeed.
