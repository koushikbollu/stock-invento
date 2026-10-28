"""CSV contract and exact quantity conversion. No business arithmetic uses floats."""

import re
from datetime import date
from decimal import Decimal

FIELDS = (
    "event_id", "revision", "effective_date", "movement_type", "item_id",
    "location_id", "to_location_id", "quantity", "is_void",
)
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")
QUANTITY = re.compile(r"-?[0-9]+(?:\.[0-9]{1,3})?\Z")
SQLITE_LIMIT = 2**63 - 1


def identifier(value, field):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field}: expected 1–64 letters, digits, _, ., :, or -")
    return value


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("effective_date: expected YYYY-MM-DD")
    return value


def format_quantity(milli):
    """Format signed integer milli-units without float or Decimal rounding."""
    n = int(milli)
    return f"{'-' if n < 0 else ''}{abs(n) // 1000}.{abs(n) % 1000:03d}"


def parse_event(raw, items, locations):
    if set(raw) != set(FIELDS) or any(v is None for v in raw.values()):
        raise ValueError("row does not match the declared CSV schema")
    row = {k: v.strip() for k, v in raw.items()}
    for key in ("event_id", "item_id", "location_id"):
        identifier(row[key], key)
    if not re.fullmatch(r"[1-9][0-9]{0,8}", row["revision"]):
        raise ValueError("revision: expected a positive integer of at most 9 digits")
    iso_date(row["effective_date"])
    kind = row["movement_type"]
    if kind not in {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"}:
        raise ValueError("movement_type: expected RECEIPT, ISSUE, TRANSFER, or ADJUSTMENT")
    if row["item_id"] not in items:
        raise ValueError("item_id: unknown reference")
    if row["location_id"] not in locations:
        raise ValueError("location_id: unknown reference")
    destination = row["to_location_id"]
    if kind == "TRANSFER":
        if destination not in locations:
            raise ValueError("to_location_id: unknown reference")
        if destination == row["location_id"]:
            raise ValueError("transfer source and destination must differ")
    elif destination:
        raise ValueError("to_location_id must be blank for non-transfer events")
    if not QUANTITY.fullmatch(row["quantity"]):
        raise ValueError("quantity: expected a decimal number with at most 3 decimal places")
    amount = Decimal(row["quantity"])
    if amount == 0 or abs(amount) > 1_000_000_000:
        raise ValueError("quantity: must be nonzero and at most 1000000000 in magnitude")
    if kind != "ADJUSTMENT" and amount < 0:
        raise ValueError("quantity: must be positive for receipts, issues and transfers")
    if row["is_void"].lower() not in {"true", "false"}:
        raise ValueError("is_void: expected true or false")
    return {
        "event_id": row["event_id"], "revision": int(row["revision"]),
        "effective_date": row["effective_date"], "movement_type": kind,
        "item_id": row["item_id"], "location_id": row["location_id"],
        "to_location_id": destination, "quantity_milli": int(amount * 1000),
        "is_void": int(row["is_void"].lower() == "true"),
    }
