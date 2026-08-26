from __future__ import annotations

import unittest

from Projects.AdaptiveKernel.pi3_controller_fingerprint import validate_fingerprint


class Pi3ControllerFingerprintTests(unittest.TestCase):
    def identity(self):
        return {
            "schema": "aurum-pi3-pinned-identity-v1",
            "model_marker": "Raspberry Pi 3",
            "serial": "00000000a6a7df7f",
            "production_nodes_allowed": False,
        }

    def raw(self):
        return {
            "schema": "aurum.pi3.controller-link-fingerprint.raw.v1",
            "observed_at_utc": "2026-08-26T00:00:00Z",
            "source_commit": "abc",
            "source_run_id": "123",
            "target": {
                "model": "Raspberry Pi 3 Model B Rev 1.2",
                "serial": "00000000a6a7df7f",
                "kernel": "6.18.34+rpt-rpi-v8",
                "arch": "aarch64",
            },
            "ethernet": {
                "interface": "eth0",
                "driver": "smsc95xx",
                "carrier": "1",
                "speed_mbps": 100,
                "duplex": "full",
                "usb_vendor_id": "0424",
                "usb_product_id": "ec00",
                "usb_product": "SMSC9512/9514 Fast Ethernet Adapter",
                "usb_manufacturer": "Standard Microsystems Corp.",
                "device_path": "/sys/devices/example",
            },
            "provenance": {
                "proc_version": "Linux version 6.18.34+rpt-rpi-v8",
                "kernel_packages": ["linux-image-6.18.34+rpt-rpi-v8 1:6.18.34-1+rpt1 arm64"],
                "running_image_package": "linux-image-6.18.34+rpt-rpi-v8",
                "running_image_package_record": "install ok installed\t1:6.18.34-1+rpt1\tarm64",
                "modules_package_owner": "linux-image-rpi-v8: /lib/modules/6.18.34+rpt-rpi-v8",
                "headers_package_owner": "linux-headers-rpi-v8: /usr/src/linux-headers-6.18.34+rpt-rpi-v8",
                "driver_module_mode": "module",
                "driver_modinfo_filename": "/lib/modules/6.18.34+rpt-rpi-v8/kernel/drivers/net/usb/smsc95xx.ko.xz",
                "driver_kernel_config": "CONFIG_USB_NET_SMSC95XX=m",
            },
            "authority": {
                "mutation_allowed": False,
                "driver_binding_change_allowed": False,
                "kernel_module_load_allowed": False,
                "firmware_mutation_allowed": False,
                "network_configuration_change_allowed": False,
                "promotion_allowed": False,
                "write_authority": False,
            },
        }

    def test_complete_read_only_fingerprint(self):
        receipt = validate_fingerprint(self.raw(), self.identity())
        self.assertEqual(receipt["state"], "completed-read-only-fingerprint")
        self.assertEqual(receipt["gaps"], [])
        self.assertTrue(receipt["checks"]["pinned_identity_match"])
        self.assertTrue(receipt["checks"]["protected_driver_match"])
        self.assertTrue(receipt["checks"]["running_image_package_observed"])
        self.assertTrue(receipt["checks"]["driver_binary_provenance_observed"])
        self.assertFalse(receipt["authority"]["mutation_allowed"])
        self.assertFalse(receipt["authority"]["promotion_allowed"])

    def test_builtin_driver_uses_exact_running_kernel_package(self):
        raw = self.raw()
        raw["provenance"]["modules_package_owner"] = ""
        raw["provenance"]["driver_module_mode"] = "unknown"
        raw["provenance"]["driver_modinfo_filename"] = ""
        raw["provenance"]["driver_kernel_config"] = "CONFIG_USB_NET_SMSC95XX=y"
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "completed-read-only-fingerprint")
        self.assertTrue(receipt["checks"]["driver_builtin_observed"])
        self.assertTrue(receipt["checks"]["driver_binary_provenance_observed"])
        self.assertNotIn("running-driver-binary-provenance", receipt["gaps"])

    def test_missing_exact_package_provenance_is_gap_not_permission(self):
        raw = self.raw()
        raw["provenance"]["kernel_packages"] = []
        raw["provenance"]["running_image_package"] = ""
        raw["provenance"]["running_image_package_record"] = ""
        raw["provenance"]["modules_package_owner"] = ""
        raw["provenance"]["driver_module_mode"] = "unknown"
        raw["provenance"]["driver_modinfo_filename"] = ""
        raw["provenance"]["driver_kernel_config"] = ""
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "completed-with-read-only-gaps")
        self.assertIn("kernel-package-candidates", receipt["gaps"])
        self.assertIn("exact-running-image-package", receipt["gaps"])
        self.assertIn("running-driver-kernel-config", receipt["gaps"])
        self.assertIn("running-driver-binary-provenance", receipt["gaps"])
        self.assertFalse(receipt["authority"]["driver_binding_change_allowed"])

    def test_identity_mismatch_quarantines(self):
        raw = self.raw()
        raw["target"]["serial"] = "0000000000000000"
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "quarantined")
        self.assertIn("pinned-pi3-identity-mismatch", receipt["quarantine_reasons"])

    def test_driver_mismatch_quarantines(self):
        raw = self.raw()
        raw["ethernet"]["driver"] = "lan78xx"
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "quarantined")
        self.assertIn("protected-driver-mismatch", receipt["quarantine_reasons"])

    def test_fast_ethernet_envelope_is_fail_closed(self):
        raw = self.raw()
        raw["ethernet"]["speed_mbps"] = 1000
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "quarantined")
        self.assertIn(
            "observed-speed-outside-smsc95xx-fast-ethernet-envelope",
            receipt["quarantine_reasons"],
        )

    def test_invalid_driver_module_mode_quarantines(self):
        raw = self.raw()
        raw["provenance"]["driver_module_mode"] = "maybe"
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "quarantined")
        self.assertIn("invalid-driver-module-mode", receipt["quarantine_reasons"])

    def test_conflicting_kernel_config_and_module_mode_quarantines(self):
        raw = self.raw()
        raw["provenance"]["driver_module_mode"] = "module"
        raw["provenance"]["driver_kernel_config"] = "CONFIG_USB_NET_SMSC95XX=y"
        receipt = validate_fingerprint(raw, self.identity())
        self.assertEqual(receipt["state"], "quarantined")
        self.assertIn("driver-provenance-mode-conflict", receipt["quarantine_reasons"])

    def test_truthy_authority_is_rejected(self):
        raw = self.raw()
        raw["authority"]["mutation_allowed"] = "false"
        with self.assertRaises(ValueError):
            validate_fingerprint(raw, self.identity())


if __name__ == "__main__":
    unittest.main()
