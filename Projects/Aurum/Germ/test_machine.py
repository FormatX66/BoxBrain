import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import installer
import machine


class MachineSpeciesTests(unittest.TestCase):
    def test_pi3_observation_selects_a_pi3_arm64_first_boot_profile(self) -> None:
        receipt = machine.species_from_observation(
            {
                "architecture": "arm64",
                "kernel_machine": "aarch64",
                "firmware": "raspberry-pi",
                "model": "Raspberry Pi 3 Model B Plus Rev 1.3",
                "vendor": None,
            }
        )
        self.assertEqual(receipt["family"], "raspberry-pi-3")
        self.assertEqual(receipt["first_boot_profile"], "raspberry-pi-3-arm64")
        self.assertIn("vendor", receipt["missing"])

    def test_species_identity_is_coarse_not_a_kernel_or_node_identity(self) -> None:
        base = {
            "architecture": "x86_64",
            "firmware": "uefi",
            "model": "Example Workstation",
            "vendor": "Example",
        }
        first = machine.species_from_observation(
            {**base, "kernel_machine": "x86_64"}
        )
        second = machine.species_from_observation(
            {**base, "kernel_machine": "amd64"}
        )
        self.assertEqual(first["species_id"], second["species_id"])
        self.assertEqual(first["family"], "generic-x86-64-pc")
        self.assertIn("not-node-identity", first["scope"])

    def test_different_pi_generations_do_not_share_a_species_identity(self) -> None:
        common = {
            "architecture": "arm64",
            "kernel_machine": "aarch64",
            "firmware": "raspberry-pi",
            "vendor": None,
        }
        pi3 = machine.species_from_observation(
            {**common, "model": "Raspberry Pi 3 Model B Rev 1.2"}
        )
        pi4 = machine.species_from_observation(
            {**common, "model": "Raspberry Pi 4 Model B Rev 1.5"}
        )
        self.assertNotEqual(pi3["species_id"], pi4["species_id"])

    def test_installer_persists_species_for_the_internal_first_boot(self) -> None:
        receipt = machine.species_from_observation(
            {
                "architecture": "arm64",
                "kernel_machine": "aarch64",
                "firmware": "raspberry-pi",
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "vendor": None,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer._write_common(
                root,
                root_uuid="00000000-0000-0000-0000-000000000001",
                boot_line="raspberry-pi-firmware",
                species=receipt,
            )
            installed = json.loads(
                (root / "var/lib/aurum/bootstrap/machine-species.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(installed, receipt)

    def test_installer_refuses_an_unknown_species_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(installer.InstallError):
                installer._write_common(
                    Path(temporary),
                    root_uuid="root",
                    boot_line="test",
                    species={"schema": "future"},
                )


if __name__ == "__main__":
    unittest.main()
