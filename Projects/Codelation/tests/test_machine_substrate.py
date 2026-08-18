from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Projects.Codelation.machine_substrate import (
    Capsule,
    ComputeNode,
    EvidenceLedger,
    ObjectStore,
    ProcessorFarm,
    bootstrap_capsules,
    default_farm,
)


class ObjectStoreTests(unittest.TestCase):
    def test_content_addressing_is_stable_and_integrity_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            a = store.put_bytes(b"same")
            b = store.put_bytes(b"same")
            self.assertEqual(a, b)
            self.assertEqual(store.get_bytes(a), b"same")

            path = store.objects / a[:2] / a[2:]
            path.write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                store.get_bytes(a)

    def test_tree_commit_and_ref_form_machine_native_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            first_tree = store.snapshot({"a": b"one"})
            first = store.commit(first_tree, message="first")
            second_tree = store.snapshot({"a": b"two", "b": b"three"})
            second = store.commit(second_tree, parents=(first,), message="second")
            store.update_ref("heads/test", second)

            self.assertEqual(store.read_ref("heads/test"), second)
            payload = store.get_object(second)["payload"]
            self.assertEqual(payload["parents"], [first])
            self.assertEqual(payload["tree"], second_tree)

    def test_snapshot_rejects_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            with self.assertRaises(ValueError):
                store.snapshot({"../escape": b"no"})


class ProcessorFarmTests(unittest.TestCase):
    def test_default_farm_places_boot_arm_and_analysis_work(self) -> None:
        plan = default_farm().plan(bootstrap_capsules())
        self.assertTrue(plan.complete)
        assignments = {assignment.capsule: assignment.node for assignment in plan.assignments}
        self.assertIn(assignments["pc-direct-uefi"], {"github-x64-a", "github-x64-b"})
        self.assertIn(assignments["pc-qemu-boot"], {"github-x64-a", "github-x64-b"})
        self.assertEqual(assignments["arm-portability"], "github-arm64")
        self.assertEqual(assignments["state-space-analysis"], "gpt-python")

    def test_scheduler_preserves_specialized_capacity(self) -> None:
        farm = ProcessorFarm(
            (
                ComputeNode("generic", frozenset({"python"}), slots=1),
                ComputeNode("special", frozenset({"python", "qemu"}), slots=1),
            )
        )
        capsules = (
            Capsule("generic-job", "python", ("x",), frozenset({"python"})),
            Capsule("qemu-job", "native", ("y",), frozenset({"python", "qemu"})),
        )
        plan = farm.plan(capsules)
        assigned = {assignment.capsule: assignment.node for assignment in plan.assignments}
        self.assertEqual(assigned["generic-job"], "generic")
        self.assertEqual(assigned["qemu-job"], "special")

    def test_scheduler_reports_missing_capability_instead_of_guessing(self) -> None:
        farm = ProcessorFarm((ComputeNode("cpu", frozenset({"python"}), slots=1),))
        plan = farm.plan((Capsule("gpu", "native", ("x",), frozenset({"gpu"})),))
        self.assertFalse(plan.complete)
        self.assertEqual(plan.blocked["gpu"], ("gpu",))

    def test_capsule_identity_changes_when_machine_intent_changes(self) -> None:
        a = Capsule("x", "python", ("python3", "a.py"), frozenset({"python"}))
        b = Capsule("x", "python", ("python3", "b.py"), frozenset({"python"}))
        self.assertNotEqual(a.identity, b.identity)


class EvidenceLedgerTests(unittest.TestCase):
    def test_result_is_immutable_evidence_with_mutable_machine_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObjectStore(tmp)
            ledger = EvidenceLedger(store)
            capsule = Capsule("probe", "python", ("probe.py",), frozenset({"python"}))
            node = ComputeNode("test-node", frozenset({"python"}))
            commit = ledger.record_result(
                capsule=capsule,
                node=node,
                status="passed",
                observations={"ready": True},
                artifacts={"proof.txt": b"proved\n"},
            )
            self.assertEqual(store.read_ref("results/probe"), commit)
            self.assertEqual(store.get_object(commit)["kind"], "commit")


if __name__ == "__main__":
    unittest.main()
