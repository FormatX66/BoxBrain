import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "seed"))

from aurum_console import (  # noqa: E402
    CONSOLE_SCHEMA,
    CYAN,
    PLAIN_PROMPT,
    RESET,
    TEAL_256,
    TEAL_TRUECOLOR,
    YELLOW,
    _console_prompt,
    console_status,
    run_console,
)


BOOTSTRAP = ROOT / "mind" / "bootstrap_mind.json"
DEPLOYMENT_EVIDENCE = ROOT / "autobuild" / "external_evidence" / "bbpi4_aurum_console.json"


class AurumConsoleTests(unittest.TestCase):
    def make_root(self, directory: str) -> Path:
        root = Path(directory)
        (root / "mind").mkdir(parents=True)
        (root / "mind" / "bootstrap_mind.json").write_bytes(BOOTSTRAP.read_bytes())
        return root

    def test_status_and_help_need_no_api_key_or_reasoner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output = io.StringIO()
            errors = io.StringIO()

            result = run_console(
                root,
                input_stream=io.StringIO("/status\n/help\n/quit\n"),
                output_stream=output,
                error_stream=errors,
                environment={},
                key_provider=lambda _: self.fail("key prompt was unexpected"),
                reasoner=lambda *_: self.fail("reasoner was unexpected"),
            )

            self.assertEqual(0, result)
            self.assertEqual("", errors.getvalue())
            self.assertIn("AURUM CONSOLE", output.getvalue())
            self.assertIn('"host_actuation": false', output.getvalue())
            self.assertIn("Aurum console closed.", output.getvalue())
            self.assertEqual(CONSOLE_SCHEMA, console_status(root, "test-model")["schema"])

    def test_prompt_requires_terminal_color_and_unicode_capabilities(self):
        class TerminalBuffer(io.StringIO):
            def __init__(self, encoding="utf-8"):
                super().__init__()
                self._encoding = encoding

            def isatty(self):
                return True

            @property
            def encoding(self):
                return self._encoding

        self.assertEqual(PLAIN_PROMPT, _console_prompt(io.StringIO(), {}))
        self.assertEqual(PLAIN_PROMPT, _console_prompt(TerminalBuffer(), {"TERM": "dumb"}))
        self.assertEqual(
            PLAIN_PROMPT,
            _console_prompt(TerminalBuffer("ascii"), {"TERM": "xterm-256color"}),
        )
        self.assertEqual(
            PLAIN_PROMPT,
            _console_prompt(
                TerminalBuffer(),
                {"TERM": "xterm-256color", "NO_COLOR": "1"},
            ),
        )
        self.assertEqual(
            f"{YELLOW}Å{RESET}{TEAL_TRUECOLOR}u{RESET}rum> ",
            _console_prompt(
                TerminalBuffer(),
                {"TERM": "xterm-256color", "COLORTERM": "truecolor"},
            ),
        )
        self.assertEqual(
            f"{YELLOW}Å{RESET}{TEAL_256}u{RESET}rum> ",
            _console_prompt(TerminalBuffer(), {"TERM": "xterm-256color"}),
        )
        self.assertEqual(
            f"{YELLOW}Å{RESET}{CYAN}u{RESET}rum> ",
            _console_prompt(TerminalBuffer(), {"TERM": "xterm"}),
        )

    def test_dialogue_key_stays_in_memory_and_evidence_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output = io.StringIO()
            errors = io.StringIO()
            keys = []

            def fake_reasoner(messages, model, api_key):
                keys.append(api_key)
                self.assertEqual("test-model", model)
                self.assertIn("hello", json.dumps(messages).lower())
                return "Hello from Aurum.", "response-test"

            result = run_console(
                root,
                model="test-model",
                input_stream=io.StringIO("hello\n/quit\n"),
                output_stream=output,
                error_stream=errors,
                environment={},
                key_provider=lambda _: "memory-only-secret",
                reasoner=fake_reasoner,
            )

            self.assertEqual(0, result)
            self.assertEqual(["memory-only-secret"], keys)
            self.assertEqual("", errors.getvalue())
            self.assertIn("Aurum: Hello from Aurum.", output.getvalue())
            evidence = next((root / "verification" / "dialogue").glob("AURUM_ASK_*.json"))
            evidence_text = evidence.read_text(encoding="utf-8")
            self.assertNotIn("memory-only-secret", evidence_text)
            self.assertIn("Hello from Aurum.", evidence_text)

    def test_no_key_mode_fails_closed_without_ending_console(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            output = io.StringIO()
            errors = io.StringIO()

            result = run_console(
                root,
                input_stream=io.StringIO("hello\n/quit\n"),
                output_stream=output,
                error_stream=errors,
                environment={},
                allow_key_prompt=False,
                key_provider=lambda _: self.fail("key prompt was unexpected"),
                reasoner=lambda *_: self.fail("reasoner was unexpected"),
            )

            self.assertEqual(0, result)
            self.assertIn("live dialogue is disabled", errors.getvalue())
            self.assertIn("Aurum console closed.", output.getvalue())

    def test_bbpi4_deployment_evidence_preserves_safety_boundaries(self):
        evidence = json.loads(DEPLOYMENT_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual("aurum-bbpi4-console-evidence-v1", evidence["schema"])
        self.assertTrue(evidence["verified"])
        self.assertEqual("10.12.194.1", evidence["route"])
        self.assertTrue(evidence["console"]["dialogue_only"])
        self.assertFalse(evidence["console"]["host_actuation"])
        self.assertFalse(evidence["console"]["api_key_persisted"])
        self.assertEqual(0, evidence["verification"]["new_systemd_units"])
        self.assertFalse(evidence["authority_granted"])
        self.assertFalse(evidence["persistent_service_added"])
        serialized = json.dumps(evidence).casefold()
        self.assertNotIn('"api_key":', serialized)
        self.assertNotIn('"token":', serialized)


if __name__ == "__main__":
    unittest.main()
