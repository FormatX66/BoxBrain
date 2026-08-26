from __future__ import annotations

import hashlib
import json
import shutil
import unittest
from pathlib import Path

from Projects.AdaptiveKernel.pi3_smsc95xx_candidate_cloud import SCHEMA as CLOUD_SCHEMA
from Projects.AdaptiveKernel.pi3_smsc95xx_offline_stack import (
    _REQUIRED_FALSE,
    build_offline_stack,
)


def seal(value: dict) -> dict:
    body = dict(value)
    body.pop("receipt_sha256", None)
    value["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return value


HEADER = """
#define ID_REV (0x00)
#define INT_STS (0x08)
#define INT_STS_MAC_RTO_ (0x00040000)
#define INT_STS_TX_STOP_ (0x00020000)
#define INT_STS_RX_STOP_ (0x00010000)
#define INT_STS_PHY_INT_ (0x00008000)
#define INT_STS_TXE_ (0x00004000)
#define INT_STS_TDFU_ (0x00002000)
#define INT_STS_TDFO_ (0x00001000)
#define INT_STS_RXDF_ (0x00000800)
#define INT_STS_GPIOS_ (0x000007FF)
#define INT_STS_CLEAR_ALL_ (0xFFFFFFFF)
#define RX_CFG (0x0C)
#define TX_CFG (0x10)
#define HW_CFG (0x14)
#define RX_FIFO_INF (0x18)
#define TX_FIFO_INF (0x1C)
#define PM_CTRL (0x20)
#define INT_EP_CTL (0x68)
#define INT_EP_CTL_INTEP_ (0x80000000)
#define INT_EP_CTL_MAC_RTO_ (0x00080000)
#define INT_EP_CTL_RX_FIFO_ (0x00040000)
#define INT_EP_CTL_TX_STOP_ (0x00020000)
#define INT_EP_CTL_RX_STOP_ (0x00010000)
#define INT_EP_CTL_PHY_INT_ (0x00008000)
#define INT_EP_CTL_TXE_ (0x00004000)
#define INT_EP_CTL_TDFU_ (0x00002000)
#define INT_EP_CTL_TDFO_ (0x00001000)
#define INT_EP_CTL_RXDF_ (0x00000800)
#define INT_EP_CTL_GPIOS_ (0x000007FF)
#define MAC_CR (0x100)
#define MII_ADDR (0x114)
""".lstrip()


def functional_fixture() -> dict:
    return seal(
        {
            "schema": "aurum.pi3.smsc95xx.functional-model.v1",
            "state": "verified-offline-functional-model",
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
    )


def cloud_fixture(functional: dict) -> dict:
    return seal(
        {
            "schema": CLOUD_SCHEMA,
            "state": "verified-cloud-arm64-nonbinding-candidate",
            "inputs": {"functional_model_receipt_sha256": functional["receipt_sha256"]},
            "qpu": {
                "preserved_router_available": True,
                "used": False,
                "hardware_submission_performed": False,
            },
            "invariants": {
                "live_pi_contacted": False,
                "kernel_module_built": False,
                "kernel_module_loaded": False,
                "driver_binding_changed": False,
                "kernel_changed": False,
                "firmware_changed": False,
                "network_configuration_changed": False,
                "mutation_authority_granted": False,
                "promotion_authority_granted": False,
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
    )


def manifest_fixture() -> dict:
    digest = hashlib.sha256(HEADER.encode()).hexdigest()
    return {
        "schema": "aurum-pi3-hardware-reference-manifest-v1",
        "sources": [
            {"id": "raspberry-pi-linux-smsc95xx-h", "sha256": digest},
            {"id": "upstream-linux-v6.18-smsc95xx-h", "sha256": digest},
        ],
    }


class Pi3Smsc95xxOfflineStackTests(unittest.TestCase):
    def require_c_compiler(self) -> None:
        if not (shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")):
            self.skipTest("C compiler required")

    def test_full_stack_is_sealed_and_zero_authority(self) -> None:
        self.require_c_compiler()
        functional = functional_fixture()
        result = build_offline_stack(
            functional_model=functional,
            cloud_candidate=cloud_fixture(functional),
            reference_manifest=manifest_fixture(),
            rpi_smsc95xx_h=HEADER,
            upstream_smsc95xx_h=HEADER,
        )
        receipt = result["stack_receipt"]
        self.assertEqual(receipt["state"], "verified-offline-register-interrupt-packet-stack")
        self.assertEqual(receipt["verification"]["register_interrupt_differential_mismatches"], 0)
        self.assertGreaterEqual(receipt["verification"]["register_interrupt_differential_scenarios"], 10)
        self.assertEqual(receipt["verification"]["tx_packet_scenarios"], 6)
        self.assertEqual(receipt["verification"]["rx_packet_scenarios"], 3)
        for key in _REQUIRED_FALSE:
            self.assertFalse(receipt["authority"][key])
        self.assertFalse(receipt["invariants"]["live_pi_contacted"])
        self.assertFalse(receipt["invariants"]["usb_transfer_submitted"])
        self.assertTrue(receipt["invariants"]["last_known_good_preserved"])

    def test_tampered_cloud_candidate_fails_closed(self) -> None:
        functional = functional_fixture()
        cloud = cloud_fixture(functional)
        cloud["state"] = "tampered"
        with self.assertRaisesRegex(ValueError, "sealed receipt"):
            build_offline_stack(
                functional_model=functional,
                cloud_candidate=cloud,
                reference_manifest=manifest_fixture(),
                rpi_smsc95xx_h=HEADER,
                upstream_smsc95xx_h=HEADER,
            )

    def test_resealed_nonzero_cloud_authority_fails_closed(self) -> None:
        functional = functional_fixture()
        cloud = cloud_fixture(functional)
        cloud["authority"]["mutation_allowed"] = True
        seal(cloud)
        with self.assertRaisesRegex(ValueError, "mutation_allowed=false"):
            build_offline_stack(
                functional_model=functional,
                cloud_candidate=cloud,
                reference_manifest=manifest_fixture(),
                rpi_smsc95xx_h=HEADER,
                upstream_smsc95xx_h=HEADER,
            )


class Pi3Smsc95xxOfflineStackWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo = Path(__file__).resolve().parents[3]
        cls.workflow = (repo / ".github/workflows/aurum-pi3-smsc95xx-offline-stack.yml").read_text(
            encoding="utf-8"
        )

    def test_workflow_is_cloud_only_and_main_gated(self) -> None:
        lower = self.workflow.lower()
        self.assertIn("runs-on: ubuntu-24.04", lower)
        self.assertIn("if: github.ref == 'refs/heads/main'", self.workflow)
        self.assertNotIn("169.254.129.122", lower)
        self.assertNotIn("ssh ", lower)
        self.assertNotIn("id_ed25519", lower)
        self.assertNotIn("pi3_known_hosts", lower)

    def test_workflow_has_no_kernel_or_binding_path(self) -> None:
        lower = self.workflow.lower()
        for token in ("modprobe", "insmod", "modules_install", ".ko", "unbind", "register_netdev"):
            self.assertNotIn(token, lower)
        self.assertIn("python -m projects.adaptivekernel.pi3_smsc95xx_offline_stack", lower)
        self.assertIn("[skip ci]", lower)


if __name__ == "__main__":
    unittest.main()
