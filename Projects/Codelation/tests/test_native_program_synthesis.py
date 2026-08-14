from __future__ import annotations

import sys
import unittest
from dataclasses import asdict
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from field_native_vm import NativeExample, compile_native, execute_native
from native_failure_diagnosis import diagnose_native_synthesis_failure
from native_program_synthesis import synthesize_native_expression
from native_self_debug import audit_native_self_build


class NativeProgramSynthesisTests(unittest.TestCase):
    def test_synthesizes_learning_delta_from_examples(self):
        examples = (
            NativeExample({"before": "field slush", "after": "field aurum slush"}, 1),
            NativeExample({"before": "a b", "after": "a c"}, 2),
            NativeExample({"before": "x y", "after": "x y"}, 0),
        )
        result = synthesize_native_expression(("before", "after"), examples, max_cost=8)
        self.assertTrue(result.found)
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "one two", "after": "one three"}), 2)

    def test_synthesizes_overlap_from_examples(self):
        examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2),
            NativeExample({"before": "field slush", "after": "field aurum"}, 1),
            NativeExample({"before": "x", "after": "y"}, 0),
        )
        result = synthesize_native_expression(("before", "after"), examples, max_cost=8)
        self.assertTrue(result.found)
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "a c", "after": "a c d"}), 2)

    def test_retention_reuses_previously_verified_capabilities(self):
        overlap_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2),
            NativeExample({"before": "field slush", "after": "field aurum"}, 1),
            NativeExample({"before": "x", "after": "y"}, 0),
        )
        union_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 3),
            NativeExample({"before": "field slush", "after": "field aurum"}, 3),
            NativeExample({"before": "x", "after": "x"}, 1),
        )
        overlap = synthesize_native_expression(("before", "after"), overlap_examples, max_cost=8)
        union = synthesize_native_expression(("before", "after"), union_examples, max_cost=8)
        self.assertTrue(overlap.found)
        self.assertTrue(union.found)

        retention_examples = (
            NativeExample({"before": "a b", "after": "a b c"}, 2 / 3),
            NativeExample({"before": "field slush", "after": "field"}, 1 / 2),
            NativeExample({"before": "", "after": ""}, 0),
        )
        result = synthesize_native_expression(
            ("before", "after"),
            retention_examples,
            max_cost=4,
            seed_expressions={
                "learning_overlap_score": overlap.expression,
                "learning_union_size": union.expression,
            },
        )
        self.assertTrue(result.found)
        self.assertEqual(
            set(result.seed_expressions_considered),
            {"learning_overlap_score", "learning_union_size"},
        )
        program = compile_native(("before", "after"), result.expression)
        self.assertEqual(execute_native(program, {"before": "x y", "after": "x y z"}), 2 / 3)

    def test_numeric_identity_matches_runtime_int_float_equality(self):
        examples = (
            NativeExample({"left": 1, "right": 2}, 0.5),
            NativeExample({"left": 0, "right": 0}, 0.0),
            NativeExample({"left": 2, "right": 2}, 1.0),
        )
        result = synthesize_native_expression(("left", "right"), examples, max_cost=3)
        self.assertTrue(result.found)
        program = compile_native(("left", "right"), result.expression)
        self.assertEqual(execute_native(program, {"left": 0, "right": 0}), 0.0)
        self.assertEqual(execute_native(program, {"left": 3, "right": 4}), 0.75)

    def test_self_debug_accepts_current_numeric_equivalence_contract(self):
        examples = (
            NativeExample({"left": 1, "right": 2}, 0.5),
            NativeExample({"left": 0, "right": 0}, 0.0),
            NativeExample({"left": 2, "right": 2}, 1.0),
        )
        report = audit_native_self_build(("left", "right"), examples, stage="preflight")
        self.assertEqual(report.status, "clean")
        self.assertFalse(report.issues)
        self.assertFalse(report.model_escalation_advised)

    def test_self_debug_catches_verifier_identity_disconnect_with_counterexample(self):
        examples = (
            NativeExample({"left": 0, "right": 0}, 0.0),
            NativeExample({"left": 2, "right": 2}, 1.0),
        )

        def broken_identity(value):
            return (type(value).__name__, repr(value))

        report = audit_native_self_build(
            ("left", "right"),
            examples,
            stage="preflight",
            identity_projector=broken_identity,
        )
        self.assertEqual(report.status, "blocked")
        self.assertIn("builder-equivalence", report.probable_failure_domains)
        self.assertEqual(report.recommended_action, "repair-builder-equivalence")
        self.assertTrue(report.counterexamples)
        self.assertFalse(report.model_escalation_advised)

    def test_self_debug_rejects_conflicting_semantic_examples_before_search(self):
        examples = (
            NativeExample({"text": "same"}, 1),
            NativeExample({"text": "same"}, 2),
        )
        report = audit_native_self_build(("text",), examples, stage="preflight")
        self.assertEqual(report.status, "blocked")
        self.assertIn("semantic-spec", report.probable_failure_domains)
        self.assertEqual(report.recommended_action, "repair-semantic-spec")

    def test_text_selection_failure_identifies_builder_learning(self):
        examples = (
            NativeExample(
                {"required": "human-readable", "available": "text-dialogue display-output", "permissions": ""},
                "text-dialogue",
            ),
            NativeExample(
                {"required": "visual-output", "available": "display-output text-dialogue", "permissions": "visible-output"},
                "display-output",
            ),
            NativeExample(
                {"required": "visual-output", "available": "display-output text-dialogue", "permissions": ""},
                "",
            ),
        )
        diagnosis = diagnose_native_synthesis_failure(
            ("required", "available", "permissions"),
            examples,
        )
        self.assertIn("conditional-empty-or-choice", diagnosis.categories)
        self.assertIn("cross-vocabulary-fact-binding", diagnosis.categories)
        self.assertIn("local-capability-candidate-covers-builder-learning", diagnosis.categories)
        self.assertIn("deterministic-conditional-selection", diagnosis.builder_learning)
        self.assertIn("declarative-fact-binding", diagnosis.builder_learning)
        self.assertTrue(diagnosis.local_capability_candidates)
        candidate = diagnosis.local_capability_candidates[0]
        self.assertEqual(candidate["name"], "io-plan")
        self.assertEqual(candidate["coverage"], 1.0)
        self.assertEqual(candidate["authority"], "none")
        self.assertFalse(candidate["routed"])
        self.assertFalse(candidate["executed"])

        post = audit_native_self_build(
            ("required", "available", "permissions"),
            examples,
            stage="post-failure",
            synthesis={"candidates_evaluated": 841, "signatures_retained": 73},
            diagnosis=asdict(diagnosis),
        )
        self.assertEqual(post.status, "actionable")
        self.assertEqual(post.recommended_action, "verify-existing-local-capability")
        self.assertEqual(post.internal_next_action, "verify-existing-local-capability")
        self.assertFalse(post.model_escalation_advised)

    def test_not_found_is_bounded_and_explicit(self):
        examples = (
            NativeExample({"text": "a"}, 99),
            NativeExample({"text": "a b"}, 101),
        )
        result = synthesize_native_expression(("text",), examples, max_cost=3, max_signatures=100)
        self.assertFalse(result.found)
        self.assertIsNone(result.expression)
        self.assertGreater(result.candidates_evaluated, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
