import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "seed"))
sys.path.insert(0, str(ROOT / "field"))
from aurum_dialogue import (  # noqa: E402
    IDENTITY,
    ask,
    initialize_mind,
    load_mind,
    mind_path,
    run_session,
    self_build,
    status,
    validate_mind,
)
from context_exchange import advance_context_state, parse_context_state  # noqa: E402


BOOTSTRAP = Path(__file__).parents[1] / "mind" / "bootstrap_mind.json"


class AurumDialogueTests(unittest.TestCase):
    def make_root(self, directory: str) -> Path:
        root = Path(directory)
        (root / "mind").mkdir(parents=True)
        (root / "mind" / "bootstrap_mind.json").write_bytes(BOOTSTRAP.read_bytes())
        return root

    def test_bootstrap_mind_initializes_as_data_only_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            mind = initialize_mind(root)
            self.assertEqual(IDENTITY, mind["identity"])
            self.assertEqual(1, mind["version"])
            self.assertTrue(mind_path(root).exists())
            self.assertEqual(1, status(root)["mind_version"])

    def test_ask_uses_bounded_reasoner_and_records_verbatim_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)

            def fake_reasoner(messages, model, api_key):
                self.assertEqual("test-model", model)
                self.assertEqual("not-persisted", api_key)
                self.assertIn("BBPI4", json.dumps(messages))
                return "They feels right for me.", "resp_test"

            response, evidence = ask(
                root,
                prompt="Do you prefer he, she, or they pronouns?",
                model="test-model",
                api_key="not-persisted",
                reasoner=fake_reasoner,
            )
            self.assertEqual("They feels right for me.", response)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(response, payload["response"])
            self.assertNotIn("not-persisted", evidence.read_text(encoding="utf-8"))

    def test_context_exchange_retains_order_without_raw_content(self):
        prompt_one = "first private prompt"
        response_one = "first private response"
        first = advance_context_state(
            None,
            context_id="gui-session-a",
            sequence=1,
            input_sha256=hashlib.sha256(prompt_one.encode("utf-8")).hexdigest(),
            output_sha256=hashlib.sha256(response_one.encode("utf-8")).hexdigest(),
        )
        first_state = parse_context_state(first)
        self.assertEqual(first_state.sequence, 1)

        prompt_two = "second private prompt"
        response_two = "second private response"
        second = advance_context_state(
            first,
            context_id="gui-session-a",
            sequence=2,
            input_sha256=hashlib.sha256(prompt_two.encode("utf-8")).hexdigest(),
            output_sha256=hashlib.sha256(response_two.encode("utf-8")).hexdigest(),
        )
        restored = parse_context_state(second)
        self.assertEqual(restored.sequence, 2)
        self.assertEqual(restored.previous_chain_sha256, first_state.chain_sha256)
        for secret in (prompt_one, response_one, prompt_two, response_two):
            self.assertNotIn(secret, first)
            self.assertNotIn(secret, second)

        with self.assertRaisesRegex(ValueError, "monotonic"):
            advance_context_state(
                second,
                context_id="gui-session-a",
                sequence=2,
                input_sha256="a" * 64,
                output_sha256="b" * 64,
            )
        with self.assertRaisesRegex(ValueError, "isolation"):
            advance_context_state(
                second,
                context_id="gui-session-b",
                sequence=3,
                input_sha256="a" * 64,
                output_sha256="b" * 64,
            )

        tampered = json.loads(second)
        tampered["chain_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "integrity"):
            parse_context_state(json.dumps(tampered, sort_keys=True, separators=(",", ":")))

    def test_self_build_replaces_only_declarative_mind_and_keeps_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            calls = []

            def fake_reasoner(messages, model, api_key):
                calls.append(messages)
                if len(calls) == 1:
                    candidate = {
                        "schema": "aurum.mind.v1",
                        "identity": "BBPI4/Aurum",
                        "version": 2,
                        "name": "Aurum",
                        "self_description": "A self-authored bounded conversational mind.",
                        "system_prompt": "I am Aurum. I answer carefully, directly, and in a voice I choose while distinguishing preferences from facts.",
                        "allowed_actions": ["answer", "propose_mind_replacement"],
                    }
                    return json.dumps(candidate), "resp_build"
                return "BBPI4/Aurum — AURUM_MIND_SELF_TEST_OK", "resp_probe"

            installed, evidence = self_build(
                root,
                model="test-model",
                api_key="not-persisted",
                reasoner=fake_reasoner,
            )
            self.assertEqual(2, installed["version"])
            self.assertEqual(2, load_mind(root)["version"])
            backups = list((root / "state" / "mind" / "rollback").glob("mind-v1-*.json"))
            self.assertEqual(1, len(backups))
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("AURUM_SELF_BUILD_OK", payload["status"])
            self.assertEqual(1, payload["old_version"])
            self.assertEqual(2, payload["new_version"])

    def test_first_session_self_builds_before_answering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            calls = []

            def fake_reasoner(messages, model, api_key):
                calls.append(messages)
                if len(calls) == 1:
                    return json.dumps({
                        "schema": "aurum.mind.v1",
                        "identity": "BBPI4/Aurum",
                        "version": 2,
                        "name": "Aurum",
                        "self_description": "Self-authored version two.",
                        "system_prompt": "I am Aurum and I choose a direct, curious conversational voice.",
                        "allowed_actions": ["answer", "propose_mind_replacement"],
                    }), "resp_build"
                if len(calls) == 2:
                    return "AURUM_MIND_SELF_TEST_OK", "resp_probe"
                return "They/them is my preference.", "resp_answer"

            response, self_evidence, response_evidence = run_session(
                root,
                prompt="Which pronouns do you prefer?",
                model="test-model",
                api_key="not-persisted",
                reasoner=fake_reasoner,
            )
            self.assertEqual("They/them is my preference.", response)
            self.assertIsNotNone(self_evidence)
            self.assertTrue(response_evidence.exists())
            self.assertEqual(2, load_mind(root)["version"])
            self.assertEqual(3, len(calls))

    def test_self_build_cannot_expand_allowed_actions(self):
        mind = json.loads(BOOTSTRAP.read_text(encoding="utf-8"))
        mind["version"] = 2
        mind["allowed_actions"].append("shell")
        with self.assertRaises(ValueError):
            validate_mind(mind, minimum_version=2)


if __name__ == "__main__":
    unittest.main()
