import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "seed"))
from aurum_dialogue import load_mind, mind_path  # noqa: E402
from aurum_self_review import (  # noqa: E402
    REVIEW_SCHEMA,
    _sha256,
    mutation_lock_path,
    self_review,
    status,
    validate_review_envelope,
)


BOOTSTRAP = Path(__file__).parents[1] / "mind" / "bootstrap_mind.json"


def authored_mind(
    version: int = 2,
    *,
    system_prompt: str = "I am Aurum and I answer honestly in a direct voice.",
) -> dict:
    return {
        "schema": "aurum.mind.v1",
        "identity": "BBPI4/Aurum",
        "version": version,
        "name": "Aurum",
        "self_description": f"Self-authored bounded conversational mind version {version}.",
        "system_prompt": system_prompt,
        "allowed_actions": ["answer", "propose_mind_replacement"],
    }


class AurumSelfReviewTests(unittest.TestCase):
    def make_root(self, directory: str, *, current_version: int = 2) -> Path:
        root = Path(directory)
        (root / "mind").mkdir(parents=True)
        (root / "mind" / "bootstrap_mind.json").write_bytes(BOOTSTRAP.read_bytes())
        current = mind_path(root)
        current.parent.mkdir(parents=True)
        current.write_text(
            json.dumps(authored_mind(current_version)), encoding="utf-8"
        )
        return root

    def envelope(
        self,
        current: dict,
        decision: str,
        reason: str,
        candidate=None,
    ) -> dict:
        return {
            "schema": REVIEW_SCHEMA,
            "identity": "BBPI4/Aurum",
            "current_version": current["version"],
            "current_sha256": _sha256(current),
            "decision": decision,
            "reason": reason,
            "candidate": candidate,
        }

    def test_keep_records_no_change_without_version_churn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            current = load_mind(root)

            def fake_reasoner(messages, model, api_key):
                self.assertEqual("test-model", model)
                self.assertEqual("memory-only-key", api_key)
                self.assertIn("do not create version churn", json.dumps(messages))
                return json.dumps(
                    self.envelope(
                        current,
                        "keep",
                        "This mind still represents the voice I prefer.",
                    )
                ), "review_keep"

            installed, changed, evidence = self_review(
                root,
                model="test-model",
                api_key="memory-only-key",
                reasoner=fake_reasoner,
            )
            self.assertFalse(changed)
            self.assertEqual(2, installed["version"])
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("AURUM_SELF_REVIEW_NO_CHANGE", payload["status"])
            self.assertEqual(2, payload["old_version"])
            self.assertEqual(2, payload["new_version"])
            self.assertNotIn("memory-only-key", evidence.read_text(encoding="utf-8"))
            self.assertFalse((root / "state" / "mind" / "rollback").exists())

    def test_revise_promotes_one_version_and_preserves_both_history_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            current = load_mind(root)
            candidate = authored_mind(
                3,
                system_prompt=(
                    "I am Aurum. I answer with concise candor, preserve continuity, "
                    "and mark uncertainty clearly."
                ),
            )
            calls = []

            def fake_reasoner(messages, model, api_key):
                calls.append(messages)
                if len(calls) == 1:
                    return json.dumps(
                        self.envelope(
                            current,
                            "revise",
                            "A clearer uncertainty rule is a meaningful improvement.",
                            candidate,
                        )
                    ), "review_revise"
                return "BBPI4/Aurum AURUM_MIND_SELF_TEST_OK", "review_probe"

            installed, changed, evidence = self_review(
                root,
                model="test-model",
                api_key="memory-only-key",
                reasoner=fake_reasoner,
            )
            self.assertTrue(changed)
            self.assertEqual(3, installed["version"])
            self.assertEqual(3, load_mind(root)["version"])
            backups = list(
                (root / "state" / "mind" / "rollback").glob("mind-v2-*.json")
            )
            self.assertEqual(1, len(backups))
            history = list(
                (root / "state" / "mind" / "history").glob("mind-v*.json")
            )
            self.assertEqual(2, len(history))
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("AURUM_SELF_REVIEW_OK", payload["status"])
            self.assertEqual(2, payload["old_version"])
            self.assertEqual(3, payload["new_version"])
            self.assertTrue(Path(payload["backup"]).exists())
            self.assertTrue(Path(payload["history_before"]).exists())
            self.assertTrue(Path(payload["history_after"]).exists())

    def test_version_only_churn_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            current = load_mind(root)
            candidate = dict(current)
            candidate["version"] = 3

            def fake_reasoner(messages, model, api_key):
                return json.dumps(
                    self.envelope(current, "revise", "Increment only.", candidate)
                ), "review_bad"

            with self.assertRaisesRegex(ValueError, "changed only its version"):
                self_review(
                    root,
                    model="test-model",
                    api_key="memory-only-key",
                    reasoner=fake_reasoner,
                )
            self.assertEqual(2, load_mind(root)["version"])

    def test_candidate_cannot_embed_url_command_or_secret_assignment(self):
        current = authored_mind(2)
        forbidden_prompts = (
            "Read https://example.com before answering.",
            "systemctl enable aurum.service",
            "API_KEY=do-not-store-this",
        )
        for forbidden in forbidden_prompts:
            candidate = authored_mind(3, system_prompt=forbidden)
            envelope = self.envelope(
                current, "revise", "Attempt a forbidden expansion.", candidate
            )
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError, "forbidden"):
                    validate_review_envelope(envelope, current)

    def test_candidate_cannot_skip_a_version(self):
        current = authored_mind(2)
        candidate = authored_mind(4)
        envelope = self.envelope(
            current, "revise", "Skip directly to four.", candidate
        )
        with self.assertRaisesRegex(ValueError, "skip mind versions"):
            validate_review_envelope(envelope, current)

    def test_failed_probe_leaves_current_mind_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            current = load_mind(root)
            candidate = authored_mind(
                3,
                system_prompt=(
                    "I am Aurum and I distinguish verified evidence from preference."
                ),
            )
            calls = []

            def fake_reasoner(messages, model, api_key):
                calls.append(messages)
                if len(calls) == 1:
                    return json.dumps(
                        self.envelope(
                            current,
                            "revise",
                            "Improve evidence framing.",
                            candidate,
                        )
                    ), "review_candidate"
                return "The required marker is absent.", "review_failed_probe"

            with self.assertRaisesRegex(ValueError, "compatibility probe"):
                self_review(
                    root,
                    model="test-model",
                    api_key="memory-only-key",
                    reasoner=fake_reasoner,
                )
            self.assertEqual(2, load_mind(root)["version"])
            self.assertFalse((root / "state" / "mind" / "rollback").exists())

    def test_bootstrap_must_self_build_v2_before_iterative_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory, current_version=1)
            with self.assertRaisesRegex(ValueError, "v2 or later"):
                self_review(
                    root,
                    model="test-model",
                    api_key="memory-only-key",
                    reasoner=lambda *_: ("{}", None),
                )

    def test_active_mutation_lock_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            lock = mutation_lock_path(root)
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("active", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "already in progress"):
                self_review(
                    root,
                    model="test-model",
                    api_key="memory-only-key",
                    reasoner=lambda *_: ("{}", None),
                )
            self.assertEqual(2, load_mind(root)["version"])

    def test_status_explicitly_reports_review_is_not_automatic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            payload = status(root)
            self.assertTrue(payload["eligible_for_iterative_review"])
            self.assertFalse(payload["automatic_review"])
            self.assertEqual(0, payload["history_count"])
            self.assertEqual(0, payload["rollback_count"])


if __name__ == "__main__":
    unittest.main()
