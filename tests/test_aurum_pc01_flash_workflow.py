import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-pc01-flash-authorized.yml"


class Pc01FlashWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_removable_cleanup_revalidates_exact_usb_before_clean(self):
        serial_guard = "[string]$live.SerialNumber).Trim() -ne $expectedSerial"
        diskpart_select = '"select disk $diskNumber"'
        self.assertIn("AURUM_FLASH_PREP_FAILURE reason=missing-target-serial", self.text)
        self.assertIn(serial_guard, self.text)
        self.assertIn(diskpart_select, self.text)
        self.assertIn('"clean"', self.text)
        self.assertLess(self.text.index(serial_guard), self.text.index(diskpart_select))

    def test_removable_cleanup_proves_raw_state_before_write(self):
        partition_guard = "$remainingPartitions.Count -ne 0"
        raw_write = "$target = New-Object System.IO.FileStream($physicalPath"
        self.assertIn("AURUM_FLASH_DEVICE_PREP mode=removable-clean", self.text)
        self.assertIn(partition_guard, self.text)
        self.assertIn("raw-readback-hash-mismatch", self.text)
        self.assertLess(self.text.index(partition_guard), self.text.index(raw_write))


if __name__ == "__main__":
    unittest.main()
