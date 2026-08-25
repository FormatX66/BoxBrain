from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from Admin.checkpoint_farmer_runtime import FarmerProjectionError, project_farmer_checkpoint


class FarmerRuntimeCheckpointProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(cls.root / "Projects/AurumFarmer"))
        from aurum_farmer.ledger import Ledger
        from aurum_farmer.models import BranchSpec, JobSpec

        cls.Ledger = Ledger
        cls.BranchSpec = BranchSpec
        cls.JobSpec = JobSpec

    def test_farmer_ledger_projects_as_zero_authority_runtime_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ledger_path = base / "farmer.sqlite3"
            key_path = base / "farmer.key"
            output = base / "runtime-checkpoint.json"
            ledger = self.Ledger(ledger_path, signing_key_path=key_path)
            job_id, created = ledger.submit(
                self.JobSpec(
                    goal="persist Farmer operational state",
                    branches=(
                        self.BranchSpec(
                            id="safe",
                            label="safe branch",
                            executor="noop",
                        ),
                    ),
                )
            )
            self.assertTrue(created)

            value = project_farmer_checkpoint(
                root=self.root,
                ledger_path=ledger_path,
                signing_key_path=key_path,
                output=output,
            )

            self.assertEqual(value["runtime"]["operational_state_source"], "aurum-farmer-ledger")
            self.assertTrue(value["runtime"]["source_metadata"]["event_chain_valid"])
            self.assertEqual(value["runtime"]["jobs"][0]["id"], job_id)
            self.assertEqual(value["runtime"]["jobs"][0]["state"], "runnable")
            self.assertEqual(
                value["runtime"]["jobs"][0]["checkpoint"]["source"],
                "aurum-farmer-ledger",
            )
            self.assertFalse(value["authority"]["authority_granted"])
            self.assertFalse(value["authority"]["candidate_promotion_allowed"])
            self.assertFalse(value["authority"]["lkg_mutation_allowed"])

    def test_projection_refuses_missing_signing_key_instead_of_creating_one(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            ledger_path = base / "farmer.sqlite3"
            key_path = base / "farmer.key"
            self.Ledger(ledger_path, signing_key_path=key_path)
            key_path.unlink()

            with self.assertRaisesRegex(FarmerProjectionError, "signing key missing"):
                project_farmer_checkpoint(
                    root=self.root,
                    ledger_path=ledger_path,
                    signing_key_path=key_path,
                    output=base / "runtime-checkpoint.json",
                )
            self.assertFalse(key_path.exists())


if __name__ == "__main__":
    unittest.main()
