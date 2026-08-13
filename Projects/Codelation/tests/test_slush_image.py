from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "field"))

from slush_image import (  # noqa: E402
    ANCHOR_BYTES,
    AURUM_SLUSH_RAW_TYPE,
    FAT32_LBA_TYPE,
    MBR_SIGNATURE,
    PARTITION_ENTRY_BYTES,
    PARTITION_TABLE_OFFSET,
    SECTOR_BYTES,
    assemble_sparse_image,
    build_mbr,
    build_slush_anchor,
    parse_slush_anchor,
    verify_sparse_image,
)
from slush_media import GIB, SlushMediaError, plan_pi3_slush_media  # noqa: E402


class SlushImageTests(unittest.TestCase):
    def test_mbr_describes_boot_and_raw_slush_regions(self):
        plan = plan_pi3_slush_media(2 * GIB)
        mbr = build_mbr(plan)
        self.assertEqual(len(mbr), SECTOR_BYTES)
        self.assertEqual(mbr[-2:], MBR_SIGNATURE)
        first = mbr[PARTITION_TABLE_OFFSET : PARTITION_TABLE_OFFSET + PARTITION_ENTRY_BYTES]
        second_offset = PARTITION_TABLE_OFFSET + PARTITION_ENTRY_BYTES
        second = mbr[second_offset : second_offset + PARTITION_ENTRY_BYTES]
        self.assertEqual(first[4], FAT32_LBA_TYPE)
        self.assertEqual(second[4], AURUM_SLUSH_RAW_TYPE)

    def test_primary_and_mirror_anchors_share_plan_identity(self):
        plan = plan_pi3_slush_media(2 * GIB)
        primary = parse_slush_anchor(build_slush_anchor(plan, mirror=False))
        mirror = parse_slush_anchor(build_slush_anchor(plan, mirror=True))
        self.assertEqual(primary["plan_identity"], plan.identity)
        self.assertEqual(mirror["plan_identity"], plan.identity)
        self.assertFalse(primary["mirror"])
        self.assertTrue(mirror["mirror"])

    def test_corrupted_anchor_is_rejected(self):
        plan = plan_pi3_slush_media(2 * GIB)
        anchor = bytearray(build_slush_anchor(plan, mirror=False))
        anchor[100] ^= 0x01
        with self.assertRaises(SlushMediaError):
            parse_slush_anchor(bytes(anchor))

    def test_sparse_image_round_trip_without_boot_payload(self):
        plan = plan_pi3_slush_media(2 * GIB)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aurum-slush.img"
            evidence = assemble_sparse_image(path, plan)
            self.assertEqual(evidence.logical_bytes, 2 * GIB)
            self.assertEqual(path.stat().st_size, 2 * GIB)
            verified = verify_sparse_image(path, plan)
            self.assertEqual(verified.plan_identity, plan.identity)
            self.assertEqual(verified.primary_anchor_digest, evidence.primary_anchor_digest)
            self.assertEqual(verified.mirror_anchor_digest, evidence.mirror_anchor_digest)
            # Sparse creation should not require physically writing the full logical image.
            if hasattr(path.stat(), "st_blocks"):
                self.assertLess(path.stat().st_blocks * 512, 8 * 1024 * 1024)

    def test_existing_output_is_not_overwritten(self):
        plan = plan_pi3_slush_media(2 * GIB)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "existing.img"
            path.write_bytes(b"do-not-overwrite")
            with self.assertRaises(SlushMediaError):
                assemble_sparse_image(path, plan)
            self.assertEqual(path.read_bytes(), b"do-not-overwrite")

    def test_boot_payload_is_bounded_to_boot_region(self):
        plan = plan_pi3_slush_media(2 * GIB)
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            boot = temp_path / "boot.fat"
            boot.write_bytes(b"BOOT-SHIM")
            image = temp_path / "with-boot.img"
            assemble_sparse_image(image, plan, boot_partition_image=boot)
            with image.open("rb") as handle:
                handle.seek(plan.regions[0].offset)
                self.assertEqual(handle.read(9), b"BOOT-SHIM")

    def test_verify_rejects_wrong_plan_capacity(self):
        plan = plan_pi3_slush_media(2 * GIB)
        other = plan_pi3_slush_media(3 * GIB)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aurum-slush.img"
            assemble_sparse_image(path, plan)
            with self.assertRaises(SlushMediaError):
                verify_sparse_image(path, other)

    def test_anchors_live_at_both_edges_of_slush(self):
        plan = plan_pi3_slush_media(2 * GIB)
        slush = plan.regions[1]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aurum-slush.img"
            assemble_sparse_image(path, plan)
            with path.open("rb") as handle:
                handle.seek(slush.offset)
                primary = handle.read(ANCHOR_BYTES)
                handle.seek(slush.offset + slush.size - ANCHOR_BYTES)
                mirror = handle.read(ANCHOR_BYTES)
            self.assertFalse(parse_slush_anchor(primary)["mirror"])
            self.assertTrue(parse_slush_anchor(mirror)["mirror"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
