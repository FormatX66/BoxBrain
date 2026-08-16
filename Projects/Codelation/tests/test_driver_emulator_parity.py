import copy
import unittest
from pathlib import Path

from Projects.Codelation.driver_emulator_parity import (
    PARITY_SCHEMA,
    build_models_and_virtual_dlab,
    verify_emulator_parity,
)
from Projects.Codelation.driver_qemu_uart_probe import PROBE_SCHEMA, parse_monitor_reads


REPO_ROOT = Path(__file__).parents[3]


def _probe_fixture():
    return {
        "schema": PROBE_SCHEMA,
        "origin": "qemu-hmp-live",
        "emulator": "qemu-system-x86_64",
        "emulator_version": "QEMU emulator version test-fixture",
        "physical_hardware_observation": False,
        "emulator_execution_observed": True,
        "base_port": 0x3F8,
        "selector_offsets": {
            "receiver_or_divisor_lsb": 0,
            "interrupt_enable_or_divisor_msb": 1,
            "line_control": 3,
            "line_status": 5,
        },
        "test_pattern": {"divisor_lsb": 0x34, "divisor_msb": 0x12, "dlab_mask": 0x80},
        "observations": {
            "line_status_reset": {"port": 0x3FD, "value": 0x60},
            "line_control_reset": {"port": 0x3FB, "value": 0x00},
            "line_control_dlab_set": {"port": 0x3FB, "value": 0x80},
            "divisor_lsb_readback": {"port": 0x3F8, "value": 0x34},
            "divisor_msb_readback": {"port": 0x3F9, "value": 0x12},
            "line_control_dlab_cleared": {"port": 0x3FB, "value": 0x00},
            "interrupt_enable_after_bank_restore": {"port": 0x3F9, "value": 0x00},
        },
        "safety": {
            "host_physical_io_performed": False,
            "host_device_file_io_performed": False,
            "physical_writes_performed": False,
            "firmware_changes_performed": False,
            "emulated_io_port_reads_performed": True,
            "emulated_io_port_writes_performed": True,
            "qemu_process_only": True,
        },
    }


class DriverEmulatorParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding_model, cls.transition_model, cls.virtual = build_models_and_virtual_dlab(REPO_ROOT)

    def test_qemu_monitor_read_parser_preserves_order(self):
        output = """
(qemu) i /b 0x3fd
portb[0x03fd] = 0x60
(qemu) i /b 0x3fb
portb[0x03fb] = 0x80
"""
        self.assertEqual(
            [{"port": 0x3FD, "value": 0x60}, {"port": 0x3FB, "value": 0x80}],
            parse_monitor_reads(output),
        )

    def test_independent_models_and_virtual_execution_match_emulator_fixture(self):
        result = verify_emulator_parity(
            self.binding_model,
            self.transition_model,
            _probe_fixture(),
            virtual_dlab_execution=self.virtual,
        )
        self.assertEqual(PARITY_SCHEMA, result["schema"])
        self.assertEqual("passed", result["status"])
        self.assertTrue(result["live_emulator_proof"])
        self.assertFalse(result["physical_hardware_proof"])
        self.assertEqual([], result["mismatches"])
        self.assertTrue(result["checks"]["aurum_virtual_dlab_matches_live_qemu"])
        self.assertFalse(result["safety"]["physical_writes_performed"])

    def test_counterfactual_emulator_mismatch_fails_closed(self):
        probe = _probe_fixture()
        probe["observations"]["line_status_reset"]["value"] = 0x00
        result = verify_emulator_parity(
            self.binding_model,
            self.transition_model,
            probe,
            virtual_dlab_execution=self.virtual,
        )
        self.assertEqual("failed", result["status"])
        self.assertIn("reset_line_status_exact", result["mismatches"])

    def test_virtual_execution_disagreement_fails_closed(self):
        virtual = copy.deepcopy(self.virtual)
        virtual["final_logical_registers"]["selector.line_control"] = 0
        result = verify_emulator_parity(
            self.binding_model,
            self.transition_model,
            _probe_fixture(),
            virtual_dlab_execution=virtual,
        )
        self.assertEqual("failed", result["status"])
        self.assertIn("aurum_virtual_dlab_matches_live_qemu", result["mismatches"])

    def test_physical_or_host_io_probe_is_rejected(self):
        probe = _probe_fixture()
        probe["physical_hardware_observation"] = True
        with self.assertRaises(ValueError):
            verify_emulator_parity(self.binding_model, self.transition_model, probe)
        probe = _probe_fixture()
        probe["safety"]["host_physical_io_performed"] = True
        with self.assertRaises(ValueError):
            verify_emulator_parity(self.binding_model, self.transition_model, probe)


if __name__ == "__main__":
    unittest.main()
