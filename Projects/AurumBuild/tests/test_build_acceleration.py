from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


BUILD_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = BUILD_ROOT.parents[1]
sys.path.insert(0, str(BUILD_ROOT))

from build_acceleration import (  # noqa: E402
    BUILD_CONFIGURATION_PATHS,
    DEPENDENCY_DEFINITION_PATHS,
    compute_identities,
    converge_verification,
    create_verification_evidence,
    select_proven_route,
    timing_evidence,
)


BUILDER_A = "ghcr.io/formatx66/boxbrain/aurum-builder@sha256:" + "a" * 64
BUILDER_B = "ghcr.io/formatx66/boxbrain/aurum-builder@sha256:" + "b" * 64
SOURCE_A = "1" * 40
SOURCE_B = "2" * 40


def artifact() -> dict:
    return {
        "schema": "aurum-pc-artifact-v1",
        "artifact_identity": "3" * 64,
        "source_sha": SOURCE_A,
        "architecture": "x86_64",
        "builder_image": BUILDER_A,
        "iso_sha256": "4" * 64,
        "promotion_state": "unverified",
        "cache": {"hit": True},
        "timing": {
            "pipeline_started_epoch": 100,
            "validation_seconds": 5.0,
            "builder_pull_seconds": 7.0,
            "container_start_seconds": 1.0,
            "iso_build_seconds": 200.0,
        },
    }


def evidence(profile: str) -> dict:
    item = artifact()
    return {
        "schema": "aurum-pc-verification-v1",
        "profile": profile,
        "work_type": "vm-topology-verification",
        "architecture": "x86_64",
        "execution_environment": "qemu-uefi-tcg",
        "source_sha": item["source_sha"],
        "artifact_identity": item["artifact_identity"],
        "iso_sha256": item["iso_sha256"],
        "builder_image": item["builder_image"],
        "verified": True,
        "duration_seconds": 10.0,
        "state_authority": "ephemeral-vm",
        "physical_state_mutated": False,
    }


class BuildAccelerationTests(unittest.TestCase):
    def _identity_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in (*BUILD_CONFIGURATION_PATHS, *DEPENDENCY_DEFINITION_PATHS):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative + "\n", encoding="utf-8")
        return root

    def test_cache_identity_changes_when_important_configuration_changes(self) -> None:
        root = self._identity_root()
        first = compute_identities(
            root=root,
            source_sha=SOURCE_A,
            architecture="x86_64",
            builder_image=BUILDER_A,
        )
        changed = root / BUILD_CONFIGURATION_PATHS[0]
        changed.write_text("changed build configuration\n", encoding="utf-8")
        second = compute_identities(
            root=root,
            source_sha=SOURCE_A,
            architecture="x86_64",
            builder_image=BUILDER_A,
        )
        self.assertNotEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertNotEqual(first["live_build_cache_identity"], second["live_build_cache_identity"])

    def test_source_changes_artifact_identity_but_keeps_compatible_package_cache(self) -> None:
        root = self._identity_root()
        first = compute_identities(
            root=root, source_sha=SOURCE_A, architecture="x86_64", builder_image=BUILDER_A
        )
        second = compute_identities(
            root=root, source_sha=SOURCE_B, architecture="x86_64", builder_image=BUILDER_A
        )
        self.assertNotEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertEqual(first["live_build_cache_identity"], second["live_build_cache_identity"])

    def test_builder_image_change_invalidates_artifact_and_package_cache(self) -> None:
        root = self._identity_root()
        first = compute_identities(
            root=root, source_sha=SOURCE_A, architecture="x86_64", builder_image=BUILDER_A
        )
        second = compute_identities(
            root=root, source_sha=SOURCE_A, architecture="x86_64", builder_image=BUILDER_B
        )
        self.assertNotEqual(first["artifact_identity"], second["artifact_identity"])
        self.assertNotEqual(first["live_build_cache_identity"], second["live_build_cache_identity"])

    def test_mandatory_verification_cannot_be_skipped(self) -> None:
        with self.assertRaisesRegex(ValueError, "mandatory verification is missing"):
            converge_verification(artifact(), [evidence("generic-uefi-install")])

    def test_all_verifiers_must_consume_one_iso_digest(self) -> None:
        generic = evidence("generic-uefi-install")
        hopper = evidence("hopper-hp-topology-twin")
        hopper["iso_sha256"] = "5" * 64
        with self.assertRaisesRegex(ValueError, "does not match artifact iso_sha256"):
            converge_verification(artifact(), [generic, hopper])

    def test_failed_verifier_prevents_promotion(self) -> None:
        generic = evidence("generic-uefi-install")
        hopper = evidence("hopper-hp-topology-twin")
        hopper["verified"] = False
        with self.assertRaisesRegex(ValueError, "verifier did not pass"):
            converge_verification(artifact(), [generic, hopper])

    def test_proven_kvm_and_safe_tcg_fallback_are_both_valid_vm_evidence(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        log = Path(temporary.name) / "qemu.log"
        log.write_text("required-marker\n", encoding="utf-8")
        item = create_verification_evidence(
            artifact=artifact(),
            profile="generic-uefi-install",
            log_path=log,
            required_markers=["required-marker"],
            duration_seconds=2,
            execution_environment="qemu-uefi-kvm",
        )
        self.assertEqual(item["execution_environment"], "qemu-uefi-kvm")
        promotion = converge_verification(
            artifact(), [item, evidence("hopper-hp-topology-twin")]
        )
        self.assertEqual(promotion["promotion_state"], "verified")
        with self.assertRaisesRegex(ValueError, "unsupported execution environment"):
            create_verification_evidence(
                artifact=artifact(),
                profile="generic-uefi-install",
                log_path=log,
                required_markers=["required-marker"],
                duration_seconds=2,
                execution_environment="unproven-fast-path",
            )

    def test_speculative_verifier_cannot_mutate_trusted_physical_state(self) -> None:
        generic = evidence("generic-uefi-install")
        hopper = evidence("hopper-hp-topology-twin")
        hopper["state_authority"] = "Hopper"
        hopper["physical_state_mutated"] = True
        with self.assertRaisesRegex(ValueError, "physical-state boundary"):
            converge_verification(artifact(), [generic, hopper])

    def test_optimizer_cannot_override_user_intent_or_safety(self) -> None:
        routes = [
            {
                "name": "unsafe-fast",
                "proven": True,
                "correctness": True,
                "safety": False,
                "user_intent": True,
                "mandatory_verification": True,
                "verification_strength": 10,
                "latency_seconds": 1,
                "compute_units": 1,
                "cost_units": 1,
            },
            {
                "name": "requested-safe",
                "proven": True,
                "correctness": True,
                "safety": True,
                "user_intent": True,
                "mandatory_verification": True,
                "verification_strength": 10,
                "latency_seconds": 20,
                "compute_units": 2,
                "cost_units": 2,
            },
        ]
        selected = select_proven_route(routes, requested_route="requested-safe")
        self.assertEqual(selected["name"], "requested-safe")
        with self.assertRaisesRegex(ValueError, "no route satisfies"):
            select_proven_route(routes, requested_route="unsafe-fast")

    def test_timing_uses_observed_baseline_and_can_report_regression(self) -> None:
        promotion = converge_verification(
            artifact(),
            [evidence("generic-uefi-install"), evidence("hopper-hp-topology-twin")],
        )
        baseline = {
            "source": {"run_id": 42, "run_url": "https://example.invalid/42"},
            "measurement": {"critical_path_seconds": 50},
        }
        timing = timing_evidence(
            artifact=artifact(), promotion=promotion, baseline=baseline, pipeline_finished_epoch=200
        )
        self.assertEqual(timing["critical_path_seconds"], 100)
        self.assertEqual(timing["time_saved_seconds"], -50)

    def test_workflows_encode_prepared_build_once_and_fail_closed_fan_in(self) -> None:
        builder = (REPOSITORY_ROOT / ".github/workflows/aurum-builder.yml").read_text(
            encoding="utf-8"
        )
        pc = (REPOSITORY_ROOT / ".github/workflows/aurum-pc-v001.yml").read_text(
            encoding="utf-8"
        )
        build_script = (REPOSITORY_ROOT / "Projects/AurumPC/build-iso.sh").read_text(
            encoding="utf-8"
        )
        image_verifier = (REPOSITORY_ROOT / "Projects/AurumBuild/verify-pc-image.sh").read_text(
            encoding="utf-8"
        )
        qemu_acceleration = (
            REPOSITORY_ROOT / "Projects/AurumVirtualLab/qemu-acceleration.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("Projects/AurumBuild/Dockerfile.builder", builder)
        self.assertIn("packages: write", builder)
        self.assertNotIn("pull_request_target", builder)
        self.assertEqual(pc.count("sh Projects/AurumPC/build-iso.sh"), 1)
        self.assertIn("needs: [build-image, generic-uefi-smoke, hp-twin-smoke]", pc)
        self.assertIn("needs.build-image.outputs.builder_image", pc)
        self.assertIn("live_build_cache_identity", pc)
        self.assertIn("verify-pc-image.sh", build_script)
        self.assertIn("AURUM_PC_ISO_PROVENANCE verified=true", image_verifier)
        self.assertNotIn("| grep -Fq", pc)
        self.assertNotIn("| grep -Fq", image_verifier)
        self.assertNotIn("apt-get install", pc)
        self.assertIn("source/image provenance mismatch", image_verifier)
        self.assertIn("bash -n Projects/AurumBuild/verify-pc-image.sh", pc)
        self.assertNotIn("AURUM_PC_READY version=0.01 arch=x86_64", image_verifier)
        self.assertIn("--device /dev/kvm", qemu_acceleration)
        self.assertIn("AURUM_QEMU_EXECUTION_ENVIRONMENT", pc)
        self.assertIn("compression-level: 0", pc)

    def test_live_build_cache_is_copy_on_write_and_committed_only_after_checksum(self) -> None:
        script = (REPOSITORY_ROOT / "Projects/AurumPC/build-iso.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('cp -a --reflink=auto "$PERSISTENT_CACHE_ROOT/."', script)
        self.assertNotIn("cp -al", script)
        checksum = script.index('sha256sum "dist/$IMAGE_NAME"')
        provenance = script.index("verify-pc-image.sh")
        commit = script.index("rsync -a --delete --delete-excluded")
        self.assertLess(checksum, provenance)
        self.assertLess(provenance, commit)
        self.assertLess(checksum, commit)
        self.assertIn("--include='/packages.*/***'", script)
        self.assertIn("--exclude='*'", script)

        packages = (BUILD_ROOT / "packages.builder.txt").read_text(encoding="utf-8")
        self.assertIn("\ncpio\n", packages)

    def test_baseline_is_traceable_to_actual_github_run(self) -> None:
        baseline = json.loads(
            (BUILD_ROOT / "baselines/pc-v001-before-builder.json").read_text(encoding="utf-8")
        )
        self.assertEqual(baseline["source"]["run_id"], 32368078169)
        self.assertEqual(baseline["measurement"]["critical_path_seconds"], 860)
        self.assertIn("no values are estimated", baseline["provenance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
