from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_builder():
    path = ROOT / "training" / "build_corpus.py"
    spec = importlib.util.spec_from_file_location("aurum_training_build_corpus", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AurumTrainingTests(unittest.TestCase):
    def test_secret_patterns_are_rejected(self) -> None:
        module = load_builder()
        self.assertTrue(module.contains_secret("api_key=secret-value"))
        self.assertTrue(module.contains_secret("sk-abcdefghijklmnopqrstuvwxyz"))
        self.assertFalse(module.contains_secret("Aurum owns state and verification."))

    def test_build_records_provenance_without_openai_output(self) -> None:
        module = load_builder()
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            source = repo / "Projects" / "AurumLLM" / "README.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "# Aurum\n\nAurum treats the model as a proposer while deterministic verification remains external. "
                "The local language model is replaceable and must preserve evidence boundaries.\n",
                encoding="utf-8",
            )
            output = repo / "dist" / "corpus.jsonl"
            manifest_path = repo / "dist" / "manifest.json"
            manifest = module.build(repo, output, manifest_path, ["Projects/AurumLLM/README.md"])
            self.assertGreater(manifest["records"], 0)
            self.assertFalse(manifest["contains_openai_output"])
            self.assertFalse(manifest["contains_user_conversation"])
            self.assertFalse(manifest["promotion_authorized"])
            record = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["origin"], "aurum-project-owned")
            self.assertIn("source_sha256", record)


if __name__ == "__main__":
    unittest.main()
