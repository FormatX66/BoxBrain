#!/usr/bin/env python3
"""Deterministic, read-only query surface for Aurum Slush."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def _decode_payload(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class SlushQuery:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path.resolve().as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def objects(self, *, kind: str | None = None, tag: str | None = None,
                text: str | None = None, id_prefix: str | None = None,
                limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if id_prefix is not None:
            id_prefix = id_prefix.strip().lower()
            if not id_prefix or any(c not in "0123456789abcdef" for c in id_prefix):
                raise ValueError("id_prefix must be hexadecimal")

        joins = []
        where = []
        params: list[Any] = []
        if tag is not None:
            joins.append("JOIN tags t ON t.object_id = o.id")
            where.append("t.tag = ?")
            params.append(tag)
        if kind is not None:
            where.append("o.kind = ?")
            params.append(kind)
        if text is not None:
            where.append("CAST(o.payload AS TEXT) LIKE ?")
            params.append(f"%{text}%")
        if id_prefix is not None:
            where.append("lower(hex(o.id)) LIKE ?")
            params.append(f"{id_prefix}%")

        sql = """
            SELECT DISTINCT lower(hex(o.id)) AS id, o.kind, o.payload, o.created, o.updated
            FROM objects o
            {joins}
            {where}
            ORDER BY o.updated DESC, id ASC
            LIMIT ?
        """.format(
            joins=" ".join(joins),
            where=("WHERE " + " AND ".join(where)) if where else "",
        )
        params.append(limit)

        with self._connect() as con:
            rows = con.execute(sql, params).fetchall()
            result = []
            for row in rows:
                tags = [
                    r[0] for r in con.execute(
                        "SELECT tag FROM tags WHERE object_id = ? ORDER BY tag",
                        (bytes.fromhex(row["id"]),),
                    ).fetchall()
                ]
                result.append({
                    "id": row["id"],
                    "kind": row["kind"],
                    "payload": _decode_payload(row["payload"]),
                    "tags": tags,
                    "created": row["created"],
                    "updated": row["updated"],
                })
            return result

    def relations(self, object_id: str, *, direction: str = "both",
                  rel: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if direction not in {"in", "out", "both"}:
            raise ValueError("direction must be in, out, or both")
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        object_id = object_id.strip().lower()
        if not object_id or any(c not in "0123456789abcdef" for c in object_id):
            raise ValueError("object_id must be a hexadecimal id or prefix")

        with self._connect() as con:
            ids = [
                bytes(row[0]) for row in con.execute(
                    "SELECT id FROM objects WHERE lower(hex(id)) LIKE ? ORDER BY hex(id) LIMIT 2",
                    (f"{object_id}%",),
                ).fetchall()
            ]
            if not ids:
                return []
            if len(ids) > 1:
                raise ValueError("object_id prefix is ambiguous")
            oid = ids[0]
            clauses = []
            params: list[Any] = []
            if direction in {"out", "both"}:
                q = "SELECT src, rel, dst, 'out' AS direction FROM relations WHERE src = ?"
                p: list[Any] = [oid]
                if rel is not None:
                    q += " AND rel = ?"
                    p.append(rel)
                clauses.append(q)
                params.extend(p)
            if direction in {"in", "both"}:
                q = "SELECT src, rel, dst, 'in' AS direction FROM relations WHERE dst = ?"
                p = [oid]
                if rel is not None:
                    q += " AND rel = ?"
                    p.append(rel)
                clauses.append(q)
                params.extend(p)
            sql = " UNION ALL ".join(clauses) + " ORDER BY rel, src, dst LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, params).fetchall()
            return [{
                "src": bytes(row["src"]).hex(),
                "rel": row["rel"],
                "dst": bytes(row["dst"]).hex(),
                "direction": row["direction"],
            } for row in rows]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Read-only Aurum Slush query")
    p.add_argument("--db", type=Path, default=Path("slush.db"))
    sub = p.add_subparsers(dest="command", required=True)
    objects = sub.add_parser("objects")
    objects.add_argument("--kind")
    objects.add_argument("--tag")
    objects.add_argument("--text")
    objects.add_argument("--id-prefix")
    objects.add_argument("--limit", type=int, default=20)
    relations = sub.add_parser("relations")
    relations.add_argument("object_id")
    relations.add_argument("--direction", choices=("in", "out", "both"), default="both")
    relations.add_argument("--rel")
    relations.add_argument("--limit", type=int, default=50)
    return p


def main() -> int:
    args = build_parser().parse_args()
    query = SlushQuery(args.db)
    if args.command == "objects":
        result = query.objects(kind=args.kind, tag=args.tag, text=args.text,
                               id_prefix=args.id_prefix, limit=args.limit)
    else:
        result = query.relations(args.object_id, direction=args.direction,
                                 rel=args.rel, limit=args.limit)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
