import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "field"))
from morris_slush_extent import GIB, HostStorageObservation, SlushExtentError, plan_morris_slush_extent, provisioning_contract

class MorrisSlushExtentTests(unittest.TestCase):
    def obs(self, free):
        return HostStorageObservation("Aurum-Morris", "system-volume", "NTFS", 512*GIB, free*GIB, True)

    def test_prefers_64_gib(self):
        self.assertEqual(plan_morris_slush_extent(self.obs(128)).capacity_bytes, 64*GIB)

    def test_falls_back_to_32_gib(self):
        self.assertEqual(plan_morris_slush_extent(self.obs(64)).capacity_bytes, 32*GIB)

    def test_low_space_rejected(self):
        with self.assertRaises(SlushExtentError):
            plan_morris_slush_extent(self.obs(60))

    def test_contract_never_mutates_host_partitions(self):
        c = provisioning_contract(plan_morris_slush_extent(self.obs(128)))
        self.assertFalse(c["host_partition_change_allowed"])
        self.assertFalse(c["host_partition_shrink_allowed"])
        self.assertFalse(c["raw_physical_disk_write_allowed"])
        self.assertFalse(c["existing_file_overwrite_allowed"])

if __name__ == "__main__":
    unittest.main()
