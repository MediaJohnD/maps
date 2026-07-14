"""SQLite storage layer.

Local-first by design: a single file (`deal_screener.db` by default,
overridable via `DEAL_SCREENER_DB_PATH`) that holds every deal, its raw
pasted/parsed source text, and a config table seeded from config.py. No
external database dependency, trivially portable, correct for a single-user
tool.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from models import Candidate, Deal

DB_PATH = os.environ.get("DEAL_SCREENER_DB_PATH", "deal_screener.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL DEFAULT '',
    zip TEXT NOT NULL DEFAULT '',
    price REAL NOT NULL DEFAULT 0,
    beds REAL,
    baths REAL,
    sqft REAL,
    unit_count INTEGER NOT NULL DEFAULT 1,
    property_type TEXT NOT NULL DEFAULT 'SFH',
    listing_url TEXT NOT NULL DEFAULT '',
    rent_monthly_total REAL NOT NULL DEFAULT 0,
    tax_annual REAL NOT NULL DEFAULT 0,
    insurance_annual REAL NOT NULL DEFAULT 0,
    hoa_monthly REAL NOT NULL DEFAULT 0,
    condition_notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual_entry',
    pipeline_stage TEXT NOT NULL DEFAULT 'screening',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw_pasted_text TEXT NOT NULL DEFAULT '',
    fulton_county_lookup TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    zip TEXT NOT NULL DEFAULT '',
    amount REAL,
    sale_date TEXT,
    raw_snippet TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    imported_deal_id INTEGER,
    UNIQUE(source, external_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def _row_to_deal(row: sqlite3.Row) -> Deal:
    data = dict(row)
    lookup = data.pop("fulton_county_lookup", None)
    data["fulton_county_lookup"] = json.loads(lookup) if lookup else None
    return Deal(**data)


def create_deal(deal: Deal) -> Deal:
    now = _now()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO deals (
                address, zip, price, beds, baths, sqft, unit_count,
                property_type, listing_url, rent_monthly_total, tax_annual,
                insurance_annual, hoa_monthly, condition_notes, source,
                pipeline_stage, created_at, updated_at, raw_pasted_text,
                fulton_county_lookup
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deal.address, deal.zip, deal.price, deal.beds, deal.baths,
                deal.sqft, deal.unit_count, deal.property_type,
                deal.listing_url, deal.rent_monthly_total, deal.tax_annual,
                deal.insurance_annual, deal.hoa_monthly, deal.condition_notes,
                deal.source, deal.pipeline_stage, now, now,
                deal.raw_pasted_text,
                json.dumps(deal.fulton_county_lookup)
                if deal.fulton_county_lookup else None,
            ),
        )
        deal_id = cur.lastrowid
    return get_deal(deal_id)


def get_deal(deal_id: int) -> Optional[Deal]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM deals WHERE id = ?", (deal_id,)
        ).fetchone()
    return _row_to_deal(row) if row else None


def list_deals() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM deals ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_deal(row) for row in rows]


_EDITABLE_FIELDS = (
    "address", "zip", "price", "beds", "baths", "sqft", "unit_count",
    "property_type", "listing_url", "rent_monthly_total", "tax_annual",
    "insurance_annual", "hoa_monthly", "condition_notes", "pipeline_stage",
)


def update_deal(deal_id: int, fields: dict) -> Optional[Deal]:
    updates = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS}
    if not updates:
        return get_deal(deal_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE deals SET {set_clause} WHERE id = ?",
            (*updates.values(), deal_id),
        )
    return get_deal(deal_id)


def save_fulton_lookup(deal_id: int, lookup: dict) -> Optional[Deal]:
    with get_conn() as conn:
        conn.execute(
            "UPDATE deals SET fulton_county_lookup = ?, updated_at = ? "
            "WHERE id = ?",
            (json.dumps(lookup), _now(), deal_id),
        )
    return get_deal(deal_id)


def _row_to_candidate(row: sqlite3.Row) -> Candidate:
    return Candidate(**dict(row))


def upsert_candidates(candidates: list) -> dict:
    """Inserts new candidates, refreshes address/amount/sale_date/last_seen_at
    on ones already seen (matched by source+external_id). Leaves status,
    first_seen_at, and imported_deal_id untouched on an existing row, so
    re-scanning never resurrects something you've already dismissed or
    imported."""
    now = _now()
    new_count = 0
    updated_count = 0
    with get_conn() as conn:
        for c in candidates:
            existing = conn.execute(
                "SELECT id FROM candidates WHERE source = ? AND external_id = ?",
                (c["source"], c["external_id"]),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE candidates SET address = ?, zip = ?, amount = ?, "
                    "sale_date = ?, raw_snippet = ?, last_seen_at = ? "
                    "WHERE id = ?",
                    (
                        c["address"], c["zip"], c.get("amount"),
                        c.get("sale_date"), c.get("raw_snippet", ""), now,
                        existing["id"],
                    ),
                )
                updated_count += 1
            else:
                conn.execute(
                    """
                    INSERT INTO candidates (
                        source, external_id, address, zip, amount, sale_date,
                        raw_snippet, status, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
                    """,
                    (
                        c["source"], c["external_id"], c["address"], c["zip"],
                        c.get("amount"), c.get("sale_date"),
                        c.get("raw_snippet", ""), now, now,
                    ),
                )
                new_count += 1
    return {"new": new_count, "updated": updated_count}


def list_candidates(status: str = None) -> list:
    query = "SELECT * FROM candidates"
    params = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY first_seen_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_candidate(row) for row in rows]


def get_candidate(candidate_id: int) -> Optional[Candidate]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
    return _row_to_candidate(row) if row else None


def update_candidate_status(candidate_id: int, status: str) -> Optional[Candidate]:
    with get_conn() as conn:
        conn.execute(
            "UPDATE candidates SET status = ? WHERE id = ?",
            (status, candidate_id),
        )
    return get_candidate(candidate_id)


def mark_candidate_imported(candidate_id: int, deal_id: int) -> Optional[Candidate]:
    with get_conn() as conn:
        conn.execute(
            "UPDATE candidates SET status = 'imported', imported_deal_id = ? "
            "WHERE id = ?",
            (deal_id, candidate_id),
        )
    return get_candidate(candidate_id)


def get_config(key: str) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_config(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
