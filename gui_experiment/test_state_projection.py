import unittest

from gui_experiment.state_projection import compile_view_request, project_machine_state, request_state_change


class GuiProjectionTests(unittest.TestCase):
    def test_windows_request_compiles_to_constraints(self) -> None:
        intent = compile_view_request("Make it look and work like Windows")
        self.assertEqual(intent.profile, "windows")
        self.assertIn("taskbar", intent.constraints)

    def test_projection_does_not_mutate_machine_state(self) -> None:
        state = {
            "capabilities": ["network.mode", "display.scale"],
            "status": {"network": "online"},
            "kernel_secret": {"do_not_expose": True},
            "view_epoch": 3,
        }
        before = repr(state)
        view = project_machine_state(state, compile_view_request("minimal"))
        self.assertEqual(repr(state), before)
        self.assertNotIn("kernel_secret", view)

    def test_gui_emits_desired_state_not_imperative_command(self) -> None:
        state = {"capabilities": ["display.scale"], "status": {}, "view_epoch": 4}
        view = project_machine_state(state, compile_view_request("minimal"))
        request = request_state_change(view, "display.scale", 1.25)
        self.assertEqual(request["kind"], "desired-state")
        self.assertEqual(request["view_epoch"], 4)

    def test_unexposed_capability_is_rejected(self) -> None:
        view = project_machine_state(
            {"capabilities": ["display.scale"], "status": {}},
            compile_view_request("minimal"),
        )
        with self.assertRaises(ValueError):
            request_state_change(view, "kernel.raw_write", True)


if __name__ == "__main__":
    unittest.main()
