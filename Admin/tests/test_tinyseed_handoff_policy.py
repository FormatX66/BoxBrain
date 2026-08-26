from __future__ import annotations

import copy
import unittest

from Admin.tinyseed_handoff_policy import same_release_identity, workflow_run_is_canonical


class TinySeedHandoffPolicyTests(unittest.TestCase):
    @staticmethod
    def release() -> dict:
        return {
            "state": "READY_TO_FLASH",
            "source_commit": "a" * 40,
            "assembled_at_unix": 1,
            "artifacts": {
                "x86": {"name": "seed.iso", "sha256": "b" * 64, "workflow_run": 10},
                "pi": {"name": "seed.img.xz", "sha256": "c" * 64, "workflow_run": 11},
            },
        }

    def test_non_main_workflow_run_cannot_advance_canonical_handoff(self) -> None:
        self.assertFalse(workflow_run_is_canonical("workflow_run", "future-branch/test"))
        self.assertTrue(workflow_run_is_canonical("workflow_run", "main"))
        self.assertTrue(workflow_run_is_canonical("workflow_dispatch", ""))

    def test_timestamp_and_runner_refresh_is_not_a_new_release(self) -> None:
        current = self.release()
        candidate = copy.deepcopy(current)
        candidate["assembled_at_unix"] = 999
        candidate["artifacts"]["x86"]["workflow_run"] = 1000
        candidate["artifacts"]["pi"]["workflow_run"] = 1001
        self.assertTrue(same_release_identity(current, candidate))

    def test_source_or_artifact_change_is_a_new_release(self) -> None:
        current = self.release()
        changed = copy.deepcopy(current)
        changed["artifacts"]["x86"]["sha256"] = "d" * 64
        self.assertFalse(same_release_identity(current, changed))

        changed = copy.deepcopy(current)
        changed["source_commit"] = "e" * 40
        self.assertFalse(same_release_identity(current, changed))

    def test_incomplete_manifest_never_matches(self) -> None:
        self.assertFalse(same_release_identity(self.release(), {}))
        self.assertFalse(same_release_identity({}, self.release()))


if __name__ == "__main__":
    unittest.main()
