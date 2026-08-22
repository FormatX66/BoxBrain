from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("computeweave", ROOT / "computeweave.py")
assert SPEC and SPEC.loader
computeweave = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(computeweave)


class ComputeWeaveTests(unittest.TestCase):
    def test_parallel_shards_merge_to_single_node_result(self) -> None:
        baseline = computeweave.baseline(seed="test", units=12, rounds=25, node="one")
        shards = [
            computeweave.shard(
                seed="test",
                units=12,
                rounds=25,
                shard_index=index,
                shard_count=3,
                node=f"worker-{index}",
            )
            for index in range(3)
        ]
        proof = computeweave.merge(baseline, shards)
        self.assertTrue(proof["verified"])
        self.assertTrue(proof["equivalent_result"])
        self.assertEqual(proof["baseline_root_digest"], proof["merged_root_digest"])
        self.assertEqual(proof["missing_shards"], [])
        self.assertEqual(proof["missing_items"], [])
        self.assertEqual(proof["worker_nodes"], ["worker-0", "worker-1", "worker-2"])

    def test_wrong_workload_identity_is_rejected(self) -> None:
        baseline = computeweave.baseline(seed="a", units=4, rounds=2, node="one")
        receipt = computeweave.shard(
            seed="b", units=4, rounds=2, shard_index=0, shard_count=1, node="worker"
        )
        with self.assertRaisesRegex(ValueError, "workload identity mismatch"):
            computeweave.merge(baseline, [receipt])

    def test_missing_shard_does_not_verify(self) -> None:
        baseline = computeweave.baseline(seed="test", units=8, rounds=2, node="one")
        shards = [
            computeweave.shard(
                seed="test",
                units=8,
                rounds=2,
                shard_index=index,
                shard_count=2,
                node=f"worker-{index}",
            )
            for index in [0]
        ]
        proof = computeweave.merge(baseline, shards)
        self.assertFalse(proof["verified"])
        self.assertEqual(proof["missing_shards"], [1])
        self.assertTrue(proof["missing_items"])

    def test_receipts_round_trip_through_files(self) -> None:
        baseline = computeweave.baseline(seed="files", units=6, rounds=2, node="one")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "baseline.json"
            computeweave.write_json(path, baseline)
            self.assertEqual(computeweave.read_json(path), baseline)


if __name__ == "__main__":
    unittest.main()
