# Browser acceptance fixture

`browser_mixed.csv` is a synthetic two-row test input. On a fresh standard demo
after the bundled review correction, its first import must accept the valid
`qa-browser-valid` receipt of 0.001 ITEM-C units in WH-C and quarantine the
HTML-like invalid event ID. The invalid payload must appear as literal text in
the quarantine details; it must never create an image or execute script.

Expected totals after that sequence: 51 current events, 55 versions, 47 daily
rows, 4 negative closing rows, and 4 quarantined rows. Reimporting changes the
valid event into a duplicate and records another rejection of the invalid row.
Use an isolated test database; this is not part of the default 50-event seed.

For a fatal file-schema test, use `data/demo/demo_expected_schema_failure.csv`.
The UI must show failure, retain the previously published ledger, and continue
to serve the report tabs. See the test scenario matrix and executed test report.
