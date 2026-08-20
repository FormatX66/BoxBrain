from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
REPOSITORY = ROOT.parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(ROOT / "field"))

from capacity_mesh import Node, WorkItem  # noqa: E402
from distributed_build import (  # noqa: E402
    ProviderMetrics,
    available_nodes,
    provider_is_helpful,
    select_providers,
    validate_provider_policy,
)
from Projects.AurumBuild.cache_identity import cache_identity, cache_matches  # noqa: E402
from Projects.AurumBuild.evidence import EvidenceError, converge_evidence, evidence_document  # noqa: E402


POLICY = ROOT / "autobuild" / "capacity_mesh_policy.json"
SOURCE = "1" * 40
ARTIFACT = "2" * 64
CONFIG = "3" * 64
BUILDER = "sha256:" + "4" * 64


def evidence(provider: str, lane: str, authority: str, *, artifact: str = ARTIFACT):
    return evidence_document(
        source_sha=SOURCE,
        architecture="x86_64",
        builder_image_digest=BUILDER,
        build_config_hash=CONFIG,
        artifact_sha256=artifact,
        provider=provider,
        lane_identity=lane,
        verification_result="passed",
        authority_level=authority,
        timestamp="2026-08-20T00:00:00Z",
    )


class DistributedBuildTests(unittest.TestCase):
    def policy(self):
        return json.loads(POLICY.read_text(encoding="utf-8"))

    def test_provider_policy_preserves_authority_and_physical_roles(self):
        policy = self.policy()
        validate_provider_policy(policy)
        nodes = {node["name"]: node for node in policy["nodes"]}
        self.assertEqual(nodes["contributor-fork"]["authority_level"], "VERIFY-ONLY")
        self.assertNotEqual(nodes["oci-arm"]["authority_level"], "PHYSICAL-EVIDENCE")
        self.assertEqual(nodes["bbpi4-physical"]["authority_level"], "PHYSICAL-EVIDENCE")

    def test_external_provider_cannot_promote(self):
        with self.assertRaisesRegex(EvidenceError, "only Aurum convergence"):
            evidence("circleci-verifier", "illegal", "PROMOTION")

    def test_missing_optional_providers_do_not_block_github(self):
        nodes = available_nodes(self.policy(), {"github-x64", "github-arm64", "aurum-convergence"})
        decision = select_providers(
            [WorkItem("build", frozenset({"build", "x86_64"}), required_authority="BUILD-ONLY")],
            nodes,
        )
        self.assertEqual(decision.plan.unassigned, ())
        self.assertIn("github-x64", decision.plan.assignments)

    def test_exact_source_and_artifact_hash_are_enforced(self):
        inputs = [
            evidence("github-x64", "build", "BUILD-ONLY"),
            evidence("github-x64", "generic", "VERIFY-ONLY"),
            evidence("github-x64", "hopper-twin", "VERIFY-ONLY"),
        ]
        with self.assertRaisesRegex(EvidenceError, "source SHA mismatch"):
            converge_evidence(inputs, expected_source_sha="a" * 40, expected_artifact_sha256=ARTIFACT)
        inputs[-1] = evidence("github-x64", "hopper-twin", "VERIFY-ONLY", artifact="9" * 64)
        with self.assertRaisesRegex(EvidenceError, "artifact hash mismatch"):
            converge_evidence(inputs, expected_source_sha=SOURCE, expected_artifact_sha256=ARTIFACT)

    def test_verification_lanes_remain_mandatory(self):
        with self.assertRaisesRegex(EvidenceError, "mandatory independent verifier"):
            converge_evidence(
                [
                    evidence("github-x64", "build", "BUILD-ONLY"),
                    evidence("github-x64", "generic", "VERIFY-ONLY"),
                ],
                expected_source_sha=SOURCE,
                expected_artifact_sha256=ARTIFACT,
            )

    def test_circleci_evidence_is_independent_but_not_promotion(self):
        result = converge_evidence(
            [
                evidence("github-x64", "build", "BUILD-ONLY"),
                evidence("github-x64", "generic", "VERIFY-ONLY"),
                evidence("circleci-verifier", "alternate-container", "VERIFY-ONLY"),
            ],
            expected_source_sha=SOURCE,
            expected_artifact_sha256=ARTIFACT,
        )
        self.assertEqual(result["provider"], "aurum-convergence")
        self.assertIn("circleci-verifier:alternate-container", result["verified_lanes"])

    def test_cache_mismatch_forces_miss(self):
        expected = cache_identity(
            source_hash=hashlib.sha256(b"source").hexdigest(),
            architecture="x86_64",
            toolchain="gcc-12.2",
            build_config_hash=CONFIG,
            dependency_manifest_hash="5" * 64,
            builder_image_digest=BUILDER,
        )
        observed = dict(expected)
        observed["builder_image_digest"] = "sha256:" + "6" * 64
        self.assertFalse(cache_matches(expected, observed))

    def test_cost_class_prevents_scheduling(self):
        decision = select_providers(
            [
                WorkItem(
                    "free-only",
                    frozenset({"build"}),
                    allowed_cost_classes=frozenset({"free"}),
                )
            ],
            [Node("paid", frozenset({"build"}), external_cost_class="paid")],
        )
        self.assertEqual(decision.plan.unassigned, ("free-only",))

    def test_correctness_safety_and_user_intent_outrank_speed(self):
        nodes = [
            Node(
                "unsafe-fast",
                frozenset({"build"}),
                estimated_runtime_seconds=1,
                verification_strength=99,
                safe=False,
            ),
            Node(
                "intent-changing-fast",
                frozenset({"build"}),
                estimated_runtime_seconds=1,
                verification_strength=99,
                intent_compatible=False,
            ),
            Node("safe", frozenset({"build"}), estimated_runtime_seconds=100),
        ]
        decision = select_providers([WorkItem("build", frozenset({"build"}))], nodes)
        self.assertEqual(decision.plan.assignments, {"safe": ("build",)})

    def test_unhelpful_provider_is_automatically_reduced(self):
        metrics = ProviderMetrics(
            observations=5,
            queue_wait_seconds=100,
            startup_delay_seconds=100,
            execution_seconds=1000,
            failure_rate=0.5,
            verification_usefulness=0.1,
        )
        self.assertFalse(provider_is_helpful(metrics, baseline_critical_path_seconds=812))
        decision = select_providers(
            [WorkItem("build", frozenset({"build"}))],
            [Node("slow", frozenset({"build"}), optional=True)],
            metrics={"slow": metrics},
            baseline_critical_path_seconds=812,
        )
        self.assertEqual(decision.excluded["slow"], "does-not-shorten-path-or-add-useful-evidence")

    def test_primary_github_path_is_not_auto_reduced(self):
        metrics = ProviderMetrics(
            observations=5,
            execution_seconds=1000,
            failure_rate=0.5,
        )
        decision = select_providers(
            [WorkItem("build", frozenset({"build"}))],
            [Node("github-x64", frozenset({"build"}))],
            metrics={"github-x64": metrics},
            baseline_critical_path_seconds=812,
        )
        self.assertEqual(decision.plan.assignments, {"github-x64": ("build",)})

    def test_exhausted_free_tier_reduces_optional_provider(self):
        metrics = ProviderMetrics(
            observations=5,
            execution_seconds=10,
            verification_usefulness=1.0,
            free_tier_fraction=1.01,
        )
        self.assertFalse(provider_is_helpful(metrics, baseline_critical_path_seconds=812))


if __name__ == "__main__":
    unittest.main(verbosity=2)
