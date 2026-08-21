import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import aurum_traits as traits  # noqa: E402


class AurumTraitRuntimeTests(unittest.TestCase):
    def test_manifest_and_all_bundles_are_complete(self):
        data = traits.load_manifest(ROOT / "traits.json")
        self.assertEqual(set(traits.REQUIRED), set(traits.trait_map(data)))
        with tempfile.TemporaryDirectory() as directory:
            paths = traits.build_all(
                Path(directory), manifest_path=ROOT / "traits.json"
            )
            self.assertEqual(len(traits.REQUIRED), len(paths))
            for path in paths:
                bundle = traits.verify_bundle(path)
                self.assertFalse(bundle["runtime"]["shell_execution"])
                self.assertEqual(
                    "compatibility-runtime", bundle["runtime"]["stage"]
                )

    def test_garden_materializes_all_human_plots(self):
        with tempfile.TemporaryDirectory() as directory:
            garden = traits.materialize_garden(Path(directory))
            for plot in traits.GARDEN_PLOTS:
                self.assertTrue((garden / plot).is_dir())
            metadata = json.loads(
                (garden / ".aurum-garden.json").read_text(encoding="utf-8")
            )
            self.assertEqual("aurum-garden-v1", metadata["schema"])

    def test_intent_maps_everyday_language_to_stable_traits(self):
        self.assertEqual(
            "TR8:WEB", traits.resolve_intent("Open the internet")["trait_id"]
        )
        self.assertEqual(
            "TR8:MEDIA", traits.resolve_intent("Show my pictures")["trait_id"]
        )
        self.assertEqual(
            "TR8:WRITE", traits.resolve_intent("Start a document")["trait_id"]
        )
        self.assertEqual(
            "TR8:FILES", traits.resolve_intent("Open my Garden")["trait_id"]
        )

    def test_external_provider_selection_and_dry_run_are_shell_free(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "firefox"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            plan = traits.launch_plan(
                "TR8:WEB",
                "https://example.org",
                garden_root=Path(directory),
                state_root=Path(directory),
                search_path=directory,
            )
            self.assertTrue(plan["ready"])
            self.assertEqual(str(fake), plan["argv"][0])
            self.assertEqual(0, traits.launch(plan, dry_run=True))

    def test_web_rejects_non_http_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "firefox"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaises(ValueError):
                traits.launch_plan(
                    "TR8:WEB",
                    "file:///etc/passwd",
                    garden_root=Path(directory),
                    state_root=Path(directory),
                    search_path=directory,
                )

    def test_write_prepares_a_real_document(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "libreoffice"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            plan = traits.launch_plan(
                "TR8:WRITE",
                None,
                garden_root=Path(directory),
                state_root=Path(directory),
                search_path=directory,
            )
            document = Path(plan["argv"][-1])
            self.assertTrue(document.is_file())
            self.assertIn("Garden", document.parts)

    def test_recovery_provider_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = traits.launch_plan(
                "TR8:RECOVER",
                None,
                garden_root=Path(directory),
                state_root=Path(directory),
            )
            self.assertTrue(plan["ready"])
            self.assertFalse(plan["internal"]["actuation_performed"])


if __name__ == "__main__":
    unittest.main()
