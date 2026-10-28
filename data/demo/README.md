# Fifty-event interactive demonstration

`movements.csv` contains exactly 50 distinct valid revision-1 events for five
items and three warehouses over January 1–4, 2026. All four movement types,
fractional quantities, and signed adjustments are represented. Two intentionally
large issue quantities demonstrate accepted movements that overdraw stock.

The first seven events are the original `data/sample/movements.csv` records,
unchanged and in the same order. The additional 43 events use only ITEM-C,
ITEM-D, and ITEM-E, so the independently calculated ITEM-A/B sample results and
correction behavior remain intact. The seven-event fixture and its expected
answers remain a separate focused test case.

The default CLI demo loads these catalogs and all 50 events, then applies the
original `data/sample/corrections.csv` revision-2 receipt of 110.000. A fresh
run has 50 current events, 53 archived versions, 47 daily balance rows, and
four intentionally negative closing rows. The full teaching setup also retains three deliberately
quarantined rows and an expected schema-failure run followed by a successful replay. The correction changes only ITEM-A / WH-A on four
dates, adding 10.000 to each day's closing quantity. Repeating the demo retains
the existing database and safely ignores identical previously recorded versions.

Hand-calculated closing quantities on January 4 after that correction:

| Item | WH-A | WH-B | WH-C |
| --- | ---: | ---: | ---: |
| ITEM-A | 75.000 | 24.500 | No movements |
| ITEM-B | 10.000 | No movements | No movements |
| ITEM-C | 186.125 | 57.500 | 32.625 |
| ITEM-D | 82.625 | 38.000 | -14.000 |
| ITEM-E | 129.125 | -3.625 | 27.000 |

The downloadable review correction supplied by the app uses revision 3 and
quantity 120.000. Applying it to this fresh demo raises ITEM-A / WH-A's January
4 closing from 75.000 to 85.000. Other series remain unchanged.

## Intentional negative stock

Two existing revision-1 records provide these warnings without increasing the
50-record source count: `demo-d-issue-c-2` issues `40.000` KG and
`demo-e-issue-b-4` issues `60.000` L.

| Item | Location | Date | Closing | Unit |
| --- | --- | --- | ---: | --- |
| ITEM-D | WH-C | 2026-01-02 | -9.875 | KG |
| ITEM-D | WH-C | 2026-01-03 | -14.000 | KG |
| ITEM-D | WH-C | 2026-01-04 | -14.000 | KG |
| ITEM-E | WH-B | 2026-01-04 | -3.625 | L |

The negative-stock metric counts these four item/location/day rows across two
series, not four distinct calendar dates. The issues are schema-valid accepted
movements: negative stock is a warning rather than a quarantine rule. Source,
posting, and balance arithmetic still reconcile. These examples are separate
from the three intentionally invalid quarantined rows. Do not sum carried daily
stock or combine KG and L into one quantity; later user-data warnings require
normal operational review.

Use an unused `--data-dir` folder to see this updated fixture. Earlier demo
databases retain their original immutable revision-1 quantities; restarting does
not overwrite them and can report conflicts with this updated source. Existing
user data and audit history should be preserved rather than reset.

## Examples across the report tabs

After the receipt correction, the demo cancels transfer `demo-c-transfer-1`
at revision 2 and restores it at revision 3. These historical versions explain
cancellation without changing the final closing quantities listed above.

`demo_quality_examples.csv` contains three deliberately invalid records: excessive
precision, an unknown item reference, and a transfer within the same warehouse.
They remain in quarantine and do not become active inventory movements.
`demo_expected_schema_failure.csv` deliberately uses an unexpected header. The
following recovery run replays the correct 50-event file as duplicates, without
changing balances. Other failures and rejected imports must still be investigated.

The actual scenario run IDs are retained in the `demo_examples_v1` settings
marker after recovery completes. Completed setup seeds these examples once; later
starts replay the base inputs but do not add more teaching rejects or expected
failures. New interrupted setups retain private per-scenario progress and recover
their own matching committed audits before retrying. Execution copies have token
suffixes; the original template/download filenames above remain unchanged. Older
incomplete setups without progress retain prior audit records and may add new
owned examples. Existing user events and history are never reset.
