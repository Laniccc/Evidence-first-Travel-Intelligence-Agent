"""SQLite-backed historical ticket price snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from app.schemas.ticket_info import TicketSnapshot


class TicketSnapshotStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    place_name TEXT NOT NULL,
                    normalized_place_id TEXT,
                    provider TEXT NOT NULL,
                    ticket_type TEXT,
                    price REAL,
                    currency TEXT,
                    price_text TEXT,
                    source_url TEXT,
                    captured_at TEXT NOT NULL,
                    raw_hash TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_place ON ticket_snapshots(place_name, provider, captured_at)"
            )
            conn.commit()

    @staticmethod
    def _hash_raw(data: dict) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

    def save_snapshot(self, snapshot: TicketSnapshot) -> str:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ticket_snapshots (
                    snapshot_id, place_name, normalized_place_id, provider, ticket_type,
                    price, currency, price_text, source_url, captured_at, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.place_name,
                    snapshot.normalized_place_id,
                    snapshot.provider,
                    snapshot.ticket_type,
                    snapshot.price,
                    snapshot.currency,
                    snapshot.price_text,
                    snapshot.source_url,
                    snapshot.captured_at,
                    snapshot.raw_hash,
                ),
            )
            conn.commit()
        return snapshot.snapshot_id

    def save_from_item(
        self,
        place_name: str,
        provider: str,
        item: dict,
        *,
        normalized_place_id: str | None = None,
    ) -> str | None:
        price = item.get("price")
        price_text = item.get("price_text")
        if price is None and not price_text:
            return None
        captured = item.get("captured_at") or item.get("capturedAt")
        if not captured:
            from datetime import datetime, timezone

            captured = datetime.now(timezone.utc).isoformat()
        snap = TicketSnapshot(
            snapshot_id=str(uuid4()),
            place_name=place_name,
            normalized_place_id=normalized_place_id,
            provider=provider,
            ticket_type=item.get("ticket_type"),
            price=float(price) if price is not None else None,
            currency=item.get("currency") or "CNY",
            price_text=str(price_text) if price_text else None,
            source_url=item.get("url") or item.get("source_url"),
            captured_at=str(captured),
            raw_hash=self._hash_raw(item),
        )
        return self.save_snapshot(snap)

    def query_latest(self, place_name: str, provider: str | None = None) -> TicketSnapshot | None:
        sql = (
            "SELECT snapshot_id, place_name, normalized_place_id, provider, ticket_type, "
            "price, currency, price_text, source_url, captured_at, raw_hash "
            "FROM ticket_snapshots WHERE place_name = ?"
        )
        params: list = [place_name]
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        sql += " ORDER BY captured_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        return TicketSnapshot(
            snapshot_id=row[0],
            place_name=row[1],
            normalized_place_id=row[2],
            provider=row[3],
            ticket_type=row[4],
            price=row[5],
            currency=row[6],
            price_text=row[7],
            source_url=row[8],
            captured_at=row[9],
            raw_hash=row[10],
        )

    def query_history(
        self,
        place_name: str,
        provider: str | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[TicketSnapshot]:
        sql = (
            "SELECT snapshot_id, place_name, normalized_place_id, provider, ticket_type, "
            "price, currency, price_text, source_url, captured_at, raw_hash "
            "FROM ticket_snapshots WHERE place_name = ?"
        )
        params: list = [place_name]
        if provider:
            sql += " AND provider = ?"
            params.append(provider)
        if since:
            sql += " AND captured_at >= ?"
            params.append(since)
        sql += " ORDER BY captured_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            TicketSnapshot(
                snapshot_id=r[0],
                place_name=r[1],
                normalized_place_id=r[2],
                provider=r[3],
                ticket_type=r[4],
                price=r[5],
                currency=r[6],
                price_text=r[7],
                source_url=r[8],
                captured_at=r[9],
                raw_hash=r[10],
            )
            for r in rows
        ]

    def compare_latest_prices(self, place_name: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT provider, price, price_text, captured_at
                FROM ticket_snapshots s1
                WHERE place_name = ?
                AND captured_at = (
                    SELECT MAX(captured_at) FROM ticket_snapshots s2
                    WHERE s2.place_name = s1.place_name AND s2.provider = s1.provider
                )
                """,
                (place_name,),
            ).fetchall()
        return [
            {
                "provider": r[0],
                "price": r[1],
                "price_text": r[2],
                "captured_at": r[3],
            }
            for r in rows
        ]
