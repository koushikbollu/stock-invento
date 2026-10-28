# Synthetic fixtures

`sample/` is a seven-event fixture with two items and two warehouses. The
`expected/initial_balances.csv` is a hand-calculated oracle, kept separate from the
input. ITEM-A closes at WH-A = 65.000 and WH-B = 24.500 on January 4;
ITEM-B closes at WH-A = 10.000. The transfer moves 20.000 between warehouses
and contributes zero to total ITEM-A stock. Blank days carry the prior closing.

`sample/corrections.csv` replaces the January 1 ITEM-A receipt with 110.000.
`expected/corrected_balances.csv` independently records the resulting daily
balances: WH-A closes at 75.000 on January 4; all other accounts are unchanged.

Generator version **2** writes exactly the requested number of CSV data rows,
100 items, 8 locations, and a separate `coverage.json` metadata file. It uses a
local seeded random number generator, streams rows, and never uses real employee,
customer, or company data. With the same seed and row count, all four files are
byte-for-byte reproducible.

Normal new events use shuffled cycles of all 400 `(item, movement_type)` pairs.
The first 400 normal events therefore include all four types for each of the
100 items, independent of intentional quality cases interspersed in the file.
Each cycle rotates the source location with an item-specific seeded offset and
the type index. Across eight complete cycles, every item uses all eight source
locations. Transfer destinations are selected independently from the other seven
locations. This avoids tying an item's identity to a single movement type or
warehouse. Positive and negative adjustment cycles alternate.

Quantities range from 0.001 to 50.000; effective dates are sampled independently
between January 1 and March 31, 2026, producing out-of-order arrival. Negative
inventory is intentional in the stress data. A correction uses quantity 12.345.

For one-based physical row ordinal `n`, special cases take priority:

1. `n % 101 == 0`: exact duplicate of the most recent valid record.
2. Otherwise `n % 127 == 0`: invalid quantity `1.0001`, quarantined.
3. Otherwise `n % 503 == 0`: full revision of the most recent valid event,
   with its revision increased, date resampled, and quantity set to 12.345.
4. Otherwise: new revision-1 event with unique ID.

For 100,000 rows this produces 990 duplicates, 780 invalid rows, and 196
corrections. The remaining 98,034 rows are new events. Run summaries expose
the observed counts; valid revisions plus new events total 98,230 accepted
records. A different row count follows the same precedence formula. Header-only
generation is supported with zero rows.

`coverage.json` reports generator version, seed, physical row count, the four
quality-case counts, date range, adjacent date inversions, and per-item type
counts/source locations/transfer destinations. `normal_coverage` excludes the
intentional duplicate, invalid-precision, and revision rows; these are counted
separately. Its totals are descriptive generation evidence, not an independent
inventory balance oracle or proof that the pipeline accepted a record.

The 100,000-row generator test parses the CSV independently, reconstructs those
quality cases by row ordinal, verifies every item's four types and eight source
locations, and compares the measured coverage with the metadata. Small requested
row counts may cover only part of a cycle, which the metadata shows honestly.

## Ready-to-import practice files

[import-practice/](import-practice/README.md) contains two catalogs and six numbered movement CSVs for receipts, issues/transfers/adjustments, a backdated correction, mixed valid/invalid rows, negative stock and its correction. START_HERE.txt gives the quick sequence. The separate [practice answer sheet](expected/import_practice_balances.csv) is not an upload file.
