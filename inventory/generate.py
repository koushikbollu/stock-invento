"""Generate deterministic, synthetic inventory data without external dependencies."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import random


HEADER = (
    "event_id", "revision", "effective_date", "movement_type", "item_id",
    "location_id", "to_location_id", "quantity", "is_void",
)
KINDS = ("RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT")
GENERATOR_VERSION = "2"


def _quantity(milli: int) -> str:
    sign = "-" if milli < 0 else ""
    whole, fraction = divmod(abs(milli), 1000)
    return f"{sign}{whole}.{fraction:03d}"


def generate(directory: str | Path, rows: int = 100_000, seed: int = 42) -> dict[str, str]:
    """Write catalogs and exactly ``rows`` synthetic movement records.

    Ordinal rules, in priority order: multiples of 101 repeat the preceding
    valid record; multiples of 127 have invalid four-place precision; multiples
    of 503 revise the preceding valid event. All other records are new events.
    New events use shuffled cycles of all 400 item/type pairs. Each cycle
    rotates source locations, while dates and quantities use a seeded RNG.
    Output is streamed; coverage.json is metadata, never a pipeline input.
    """
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        raise ValueError("rows must be a non-negative integer")
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    paths = {key: directory / f"{key}.csv" for key in ("items", "locations", "movements")}
    with paths["items"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("item_id", "unit"))
        writer.writerows((f"ITEM-{i:03d}", ("EA", "KG", "L", "BOX")[i % 4]) for i in range(100))
    with paths["locations"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("location_id",))
        writer.writerows((f"WH-{i:02d}",) for i in range(8))
    rng = random.Random(seed)
    start = date(2026, 1, 1)
    item_offsets = [rng.randrange(8) for _ in range(100)]

    def combinations():
        cycle = 0
        while True:
            pairs = [(item, kind) for item in range(100) for kind in range(4)]
            rng.shuffle(pairs)
            for item, kind in pairs:
                yield item, kind, cycle
            cycle += 1

    sequence = combinations()
    counts = Counter(new=0, duplicate=0, invalid_precision=0, revision=0)
    item_types = [Counter() for _ in range(100)]
    item_sources = [set() for _ in range(100)]
    item_destinations = [set() for _ in range(100)]
    adjustment_signs = Counter(positive=0, negative=0)
    dates = set()
    previous_date = None
    out_of_order = 0

    def new_record(ordinal, item, kind_index, cycle):
        kind = KINDS[kind_index]
        milli = rng.randint(1, 50_000)
        if kind == "ADJUSTMENT" and cycle % 2:
            milli = -milli
        location = (cycle + item_offsets[item] + kind_index) % 8
        destination = (location + rng.randint(1, 7)) % 8
        return {
            "event_id": f"EVT-{ordinal:09d}",
            "revision": "1",
            "effective_date": (start + timedelta(days=rng.randrange(90))).isoformat(),
            "movement_type": kind,
            "item_id": f"ITEM-{item:03d}",
            "location_id": f"WH-{location:02d}",
            "to_location_id": f"WH-{destination:02d}" if kind == "TRANSFER" else "",
            "quantity": _quantity(milli),
            "is_void": "false",
        }

    last_valid: dict[str, str] | None = None
    with paths["movements"].open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER)
        writer.writeheader()
        for i in range(rows):
            ordinal = i + 1
            if ordinal % 101 == 0 and last_valid is not None:
                row = dict(last_valid)
                counts["duplicate"] += 1
            elif ordinal % 127 == 0:
                row = new_record(ordinal, rng.randrange(100), rng.randrange(4), rng.randrange(8))
                row["quantity"] = "1.0001"
                counts["invalid_precision"] += 1
            elif ordinal % 503 == 0 and last_valid is not None:
                row = dict(last_valid)
                row["revision"] = str(int(row["revision"]) + 1)
                row["effective_date"] = (start + timedelta(days=rng.randrange(90))).isoformat()
                row["quantity"] = "12.345"
                last_valid = dict(row)
                counts["revision"] += 1
            else:
                item, kind_index, cycle = next(sequence)
                row = new_record(ordinal, item, kind_index, cycle)
                last_valid = dict(row)
                counts["new"] += 1
                item_types[item][row["movement_type"]] += 1
                item_sources[item].add(row["location_id"])
                if row["to_location_id"]:
                    item_destinations[item].add(row["to_location_id"])
                if row["movement_type"] == "ADJUSTMENT":
                    adjustment_signs["negative" if row["quantity"].startswith("-") else "positive"] += 1
            dates.add(row["effective_date"])
            if previous_date is not None and row["effective_date"] < previous_date:
                out_of_order += 1
            previous_date = row["effective_date"]
            writer.writerow(row)
    coverage = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "physical_rows": rows,
        "catalog_items": 100,
        "catalog_locations": 8,
        "counts": dict(counts),
        "arrival_order": {"adjacent_date_inversions": out_of_order},
        "date_range": {"first": min(dates) if dates else None, "last": max(dates) if dates else None},
        "normal_coverage": {
            "basis": "New revision-1 rows only; excludes intentional duplicates, invalid-precision rows, and revisions.",
            "items_with_normal_rows": sum(bool(types) for types in item_types),
            "items_with_all_movement_types": sum(len(types) == len(KINDS) for types in item_types),
            "items_with_all_source_locations": sum(len(locations) == 8 for locations in item_sources),
            "distinct_item_source_locations": sum(map(len, item_sources)),
            "adjustment_signs": dict(adjustment_signs),
            "per_item": {
                f"ITEM-{item:03d}": {
                    "movement_types": sorted(item_types[item]),
                    "type_counts": {kind: item_types[item][kind] for kind in KINDS},
                    "source_locations": sorted(item_sources[item]),
                    "transfer_destinations": sorted(item_destinations[item]),
                    "normal_rows": sum(item_types[item].values()),
                } for item in range(100)
            },
        },
    }
    paths["coverage"] = directory / "coverage.json"
    paths["coverage"].write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}
