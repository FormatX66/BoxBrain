import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).with_name("local_lane_result_status.py")
spec = importlib.util.spec_from_file_location("local_lane_result_status", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class ResultStatusTests(unittest.TestCase):
    def test_matching_verified(self):
        value = module.classify_result({"request_id": "new"}, {"request_id": "new", "verified": True, "status": "VERIFIED"})
        self.assertEqual(value["status"], "verified")
        self.assertTrue(value["accept_result"])

    def test_matching_unverified(self):
        value = module.classify_result({"request_id": "new"}, {"request_id": "new", "verified": False, "status": "FAILED"})
        self.assertEqual(value["status"], "completed-unverified")
        self.assertTrue(value["accept_result"])

    def test_stale_result_is_pending(self):
        value = module.classify_result({"request_id": "new"}, {"request_id": "old", "verified": True, "status": "VERIFIED"})
        self.assertEqual(value["status"], "pending")
        self.assertFalse(value["accept_result"])

    def test_missing_result_is_pending(self):
        value = module.classify_result({"request_id": "new"}, None)
        self.assertEqual(value["status"], "pending")
        self.assertFalse(value["accept_result"])

    def test_missing_task_id_is_invalid(self):
        value = module.classify_result({}, {"request_id": "old"})
        self.assertEqual(value["status"], "invalid-task")
        self.assertFalse(value["accept_result"])


if __name__ == "__main__":
    unittest.main()
