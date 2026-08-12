import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slush_query import SlushQuery


class SlushQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "slush.db"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE objects(id BLOB PRIMARY KEY, kind TEXT, payload BLOB, created INTEGER, updated INTEGER);
        CREATE TABLE tags(object_id BLOB, tag TEXT, PRIMARY KEY(object_id,tag));
        CREATE TABLE relations(src BLOB, rel TEXT, dst BLOB);
        """)
        self.a = bytes.fromhex("11" * 32)
        self.b = bytes.fromhex("22" * 32)
        con.execute("INSERT INTO objects VALUES(?,?,?,?,?)",
                    (self.a, "concept", json.dumps({"concept":"Slush","definition":"machine state"}).encode(), 1, 2))
        con.execute("INSERT INTO objects VALUES(?,?,?,?,?)",
                    (self.b, "task", json.dumps({"intent":"query Slush","status":"ready"}).encode(), 1, 3))
        con.execute("INSERT INTO tags VALUES(?,?)", (self.a, "slush"))
        con.execute("INSERT INTO tags VALUES(?,?)", (self.b, "task"))
        con.execute("INSERT INTO relations VALUES(?,?,?)", (self.b, "queries", self.a))
        con.commit()
        con.close()
        self.q = SlushQuery(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_query_by_kind(self):
        rows = self.q.objects(kind="concept")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["concept"], "Slush")

    def test_query_by_tag_and_text(self):
        rows = self.q.objects(tag="task", text="ready")
        self.assertEqual([r["kind"] for r in rows], ["task"])

    def test_id_prefix(self):
        rows = self.q.objects(id_prefix="11" * 4)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.a.hex())

    def test_relations(self):
        rows = self.q.relations(self.b.hex()[:12], direction="out")
        self.assertEqual(rows[0]["rel"], "queries")
        self.assertEqual(rows[0]["dst"], self.a.hex())

    def test_read_only(self):
        before = self.db.read_bytes()
        self.q.objects(limit=10)
        after = self.db.read_bytes()
        self.assertEqual(before, after)

    def test_limit_guard(self):
        with self.assertRaises(ValueError):
            self.q.objects(limit=0)


if __name__ == "__main__":
    unittest.main()
