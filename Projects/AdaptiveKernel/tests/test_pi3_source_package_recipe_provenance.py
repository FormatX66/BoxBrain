from __future__ import annotations

import base64
import copy
import hashlib
import io
import sys
import tarfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi3_source_package_recipe_provenance import (
    AUTHORITY_FALSE,
    PROTECTED_PATHS,
    QUARANTINE_STATE,
    RPI_COMMIT,
    SOURCE_VERSION,
    STATE,
    _inventory,
    canonical_sha256,
    run_recipe_provenance,
)

FINGERPRINT = "D148028716CAA03283161E8873746DAF1817BDB0"
USBNET = b"static void usbnet_stop(void) { /* drain */ }\n"
URB = b"int usb_unlink_urb(void) { return -115; }\n"


def xz_tar(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:xz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def signature_armor(fingerprint: str = FINGERPRINT) -> str:
    issuer = bytes([22, 33, 4]) + bytes.fromhex(fingerprint)
    body = bytes([4, 1, 22, 10]) + len(issuer).to_bytes(2, "big") + issuer + b"\x00\x00\x00\x00"
    packet = bytes([0x88, len(body)]) + body
    encoded = base64.b64encode(packet).decode("ascii")
    return f"-----BEGIN PGP SIGNATURE-----\n\n{encoded}\n-----END PGP SIGNATURE-----\n"


def dsc(orig: bytes, debian: bytes, *, fingerprint: str = FINGERPRINT,
        orig_digest: str | None = None) -> bytes:
    payload = (
        "Format: 3.0 (quilt)\n"
        "Source: linux\n"
        f"Version: {SOURCE_VERSION}\n"
        "Vcs-Browser: https://github.com/RPi-Distro/linux-packaging/\n"
        "Vcs-Git: https://github.com/RPi-Distro/linux-packaging.git\n"
        "Checksums-Sha256:\n"
        f" {orig_digest or hashlib.sha256(orig).hexdigest()} {len(orig)} linux_6.18.34.orig.tar.xz\n"
        f" {hashlib.sha256(debian).hexdigest()} {len(debian)} linux_6.18.34-1+rpt1.debian.tar.xz\n"
    )
    return (
        "-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n"
        + payload + "\n" + signature_armor(fingerprint)
    ).encode("utf-8")


def upstream() -> dict:
    body = {
        "schema": "aurum.pi3.source-package-provenance.v1",
        "state": "running-package-protected-source-bound-to-rpi-git",
        "target": {"source_package": "linux", "source_version": SOURCE_VERSION},
        "raspberry_pi_reference": {"commit": RPI_COMMIT},
        "mismatch_count": 0,
        "protected_source_path_binding_proven": True,
        "full_source_package_git_commit_binding_proven": False,
        "authority": {key: False for key in AUTHORITY_FALSE},
    }
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def fixture(*, patch: bytes = b"diff --git a/Makefile b/Makefile\n--- a/Makefile\n+++ b/Makefile\n",
            fingerprint: str = FINGERPRINT, bad_dsc_orig_digest: bool = False):
    orig = xz_tar({
        "linux-6.18.34/" + PROTECTED_PATHS[0]: USBNET,
        "linux-6.18.34/" + PROTECTED_PATHS[1]: URB,
    })
    series = b"rpi/rpi.patch\n"
    debian = xz_tar({
        "debian/patches/series": series,
        "debian/patches/rpi/rpi.patch": patch,
    })
    dsc_bytes = dsc(
        orig, debian, fingerprint=fingerprint,
        orig_digest="0" * 64 if bad_dsc_orig_digest else None,
    )
    _, inventory = _inventory(debian, "debian/patches/series")
    manifest = {
        "schema": "aurum.pi3.source-package-recipe-manifest.v1",
        "target": {"source_package": "linux", "source_version": SOURCE_VERSION},
        "dsc": {
            "filename": "linux_6.18.34-1+rpt1.dsc",
            "url": "https://archive.raspberrypi.com/debian/pool/main/l/linux/linux_6.18.34-1+rpt1.dsc",
            "sha256": hashlib.sha256(dsc_bytes).hexdigest(), "size": len(dsc_bytes),
            "format": "3.0 (quilt)", "signature_issuer_fingerprint": FINGERPRINT,
            "vcs_git": "https://github.com/RPi-Distro/linux-packaging.git",
        },
        "archives": {
            "orig": {
                "filename": "linux_6.18.34.orig.tar.xz", "sha256": hashlib.sha256(orig).hexdigest(),
                "size": len(orig), "url": "https://archive.raspberrypi.com/orig",
            },
            "debian": {
                "filename": "linux_6.18.34-1+rpt1.debian.tar.xz", "sha256": hashlib.sha256(debian).hexdigest(),
                "size": len(debian), "url": "https://archive.raspberrypi.com/debian",
            },
        },
        "quilt": {
            "series_path": "debian/patches/series", "series_sha256": hashlib.sha256(series).hexdigest(),
            "series_size": len(series), "entry_count": len(inventory),
            "inventory_sha256": canonical_sha256(inventory), "protected_paths": list(PROTECTED_PATHS),
        },
        "protected_sources": {
            PROTECTED_PATHS[0]: hashlib.sha256(USBNET).hexdigest(),
            PROTECTED_PATHS[1]: hashlib.sha256(URB).hexdigest(),
        },
    }
    return manifest, dsc_bytes, orig, debian


def run_with(**kwargs):
    manifest, dsc_bytes, orig, debian = fixture(**kwargs)
    return run_recipe_provenance(
        upstream=upstream(), manifest=manifest, dsc_bytes=dsc_bytes,
        orig_archive=orig, debian_archive=debian,
    )


class Pi3SourcePackageRecipeProvenanceTests(unittest.TestCase):
    def test_exact_recipe_proves_only_protected_paths(self):
        receipt = run_with()
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["mismatch_count"], 0)
        self.assertTrue(receipt["protected_path_source_recipe_binding_proven"])
        self.assertTrue(receipt["quilt"]["protected_paths_unmodified_by_series"])
        self.assertFalse(receipt["dsc_signer_key_trust_binding_proven"])
        self.assertFalse(receipt["full_source_package_git_commit_binding_proven"])
        self.assertFalse(receipt["whole_tree_build_recipe_equivalence_proven"])
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertTrue(all(value is False for value in receipt["invariants"].values()))

    def test_receipt_is_deterministic(self):
        self.assertEqual(run_with(), run_with())

    def test_patch_touching_protected_path_is_quarantined(self):
        patch = (
            b"diff --git a/drivers/net/usb/usbnet.c b/drivers/net/usb/usbnet.c\n"
            b"--- a/drivers/net/usb/usbnet.c\n+++ b/drivers/net/usb/usbnet.c\n"
        )
        receipt = run_with(patch=patch)
        self.assertEqual(receipt["state"], QUARANTINE_STATE)
        self.assertFalse(receipt["protected_path_source_recipe_binding_proven"])
        self.assertEqual(receipt["quilt"]["protected_patch_hits"][0]["paths"], [PROTECTED_PATHS[0]])

    def test_archive_size_or_hash_drift_fails_closed(self):
        manifest, dsc_bytes, orig, debian = fixture()
        with self.assertRaisesRegex(ValueError, "immutable size/hash"):
            run_recipe_provenance(
                upstream=upstream(), manifest=manifest, dsc_bytes=dsc_bytes,
                orig_archive=orig + b"tamper", debian_archive=debian,
            )

    def test_dsc_checksum_set_mismatch_fails_closed(self):
        manifest, dsc_bytes, orig, debian = fixture(bad_dsc_orig_digest=True)
        with self.assertRaisesRegex(ValueError, "checksum set moved"):
            run_recipe_provenance(
                upstream=upstream(), manifest=manifest, dsc_bytes=dsc_bytes,
                orig_archive=orig, debian_archive=debian,
            )

    def test_signature_fingerprint_mismatch_fails_closed(self):
        manifest, dsc_bytes, orig, debian = fixture(fingerprint="A" * 40)
        with self.assertRaisesRegex(ValueError, "issuer fingerprint moved"):
            run_recipe_provenance(
                upstream=upstream(), manifest=manifest, dsc_bytes=dsc_bytes,
                orig_archive=orig, debian_archive=debian,
            )

    def test_quilt_inventory_drift_fails_closed(self):
        manifest, dsc_bytes, orig, debian = fixture()
        manifest["quilt"]["inventory_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "inventory moved"):
            run_recipe_provenance(
                upstream=upstream(), manifest=manifest, dsc_bytes=dsc_bytes,
                orig_archive=orig, debian_archive=debian,
            )

    def test_upstream_authority_regression_fails_closed(self):
        value = upstream()
        value["authority"]["usb_transfer_allowed"] = True
        body = copy.deepcopy(value)
        body.pop("receipt_sha256")
        value["receipt_sha256"] = canonical_sha256(body)
        manifest, dsc_bytes, orig, debian = fixture()
        with self.assertRaisesRegex(ValueError, "usb_transfer_allowed"):
            run_recipe_provenance(
                upstream=value, manifest=manifest, dsc_bytes=dsc_bytes,
                orig_archive=orig, debian_archive=debian,
            )


if __name__ == "__main__":
    unittest.main()
