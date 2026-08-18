import tempfile
import unittest
from pathlib import Path

from watson_spel import UNKNOWN, SpelError, evaluate_condition, evaluate_expression
import watson_dialog_conditions as conditions
import watson_dialog_external as external
import watson_dialog_test as runner
import watson_dialog_validate as validate


class AdversarialHardeningTests(unittest.TestCase):
    def test_spel_division_by_zero_safe(self) -> None:
        self.assertIs(evaluate_expression("10 / 0", {}), UNKNOWN)
        self.assertIs(evaluate_condition("10 / 0", {}), UNKNOWN)

    def test_spel_type_mismatch_safe(self) -> None:
        self.assertEqual(evaluate_expression("10 + 'abc'", {}), "10abc")
        self.assertIs(evaluate_expression("'abc' - 10", {}), UNKNOWN)
        self.assertIs(evaluate_expression("10 < 'abc'", {}), UNKNOWN)
        self.assertIs(evaluate_expression("- 'abc'", {}), UNKNOWN)
        self.assertIs(evaluate_expression("'abc' * 'def'", {}), UNKNOWN)

    def test_spel_dunder_property_blocked(self) -> None:
        self.assertIs(evaluate_expression("('hello').__class__", {}), UNKNOWN)
        self.assertIs(evaluate_expression("('hello').__class__.__name__", {}), UNKNOWN)
        self.assertIs(evaluate_expression("__builtins__", {}), UNKNOWN)

    def test_spel_recursion_depth_limit(self) -> None:
        deep_expression = "(" * 500 + "true" + ")" * 500
        with self.assertRaises(SpelError):
            evaluate_expression(deep_expression, {})

    def test_spel_memory_amplification_capped(self) -> None:
        # Huge string multiplication should be rejected to prevent memory exhaustion
        self.assertIs(evaluate_expression("'a' * 10000000", {}), UNKNOWN)

    def test_runner_condition_result_handles_all_exceptions(self) -> None:
        self.assertEqual(runner.condition_result("10 / 0", {}, False), "unknown")
        self.assertEqual(runner.condition_result("'a' - 5", {}, False), "unknown")

    def test_conditions_evaluator_handles_exceptions(self) -> None:
        doc = {"nos": [{"uuid": "node1", "condicao": "10 / 0"}]}
        res = conditions.evaluate_document_conditions(doc, {})
        self.assertEqual(res["summary"]["unknown"], 1)
        self.assertEqual(res["evaluations"][0]["result"], "unknown")

    def test_external_parser_malformed_json_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "empty_slot.json"
            tmp_path.write_text('{"nos": [,]}', encoding="utf-8")
            with self.assertRaises((external.JsonStructureError, ValueError)):
                with external.DialogSourceIndex.open(tmp_path):
                    pass

    def test_validate_missing_node_uuid(self) -> None:
        doc = {"nos": [{"nome": "Sem UUID", "condicao": "true"}]}
        report = validate.validate(doc)
        codes = report["summary"]["issues_by_code"]
        self.assertIn("missing_node_uuid", codes)

    def test_dormant_reference_downgraded_to_info(self) -> None:
        doc = {"nos": [
            {"uuid": "inactive", "status": "INATIVO", "condicao": "#missing_intent && @missing_entity", "filhos": []},
            {"uuid": "active", "status": "ATIVO", "condicao": "#active_missing_intent", "filhos": []},
        ]}
        report = conditions.analyze_conditions(doc)
        inactive_issues = [i for i in report["issues"] if i["node"] == "inactive"]
        active_issues = [i for i in report["issues"] if i["node"] == "active"]
        self.assertTrue(all(i["severity"] == "info" for i in inactive_issues))
        self.assertTrue(any(i["severity"] == "warning" for i in active_issues))

    def test_digression_constraint_info_severity(self) -> None:
        doc = {"nos": [
            {
                "uuid": "transition_node", "condicao": "#start", "inDigressionOut": True,
                "uuidEnviarPara": "other_node", "filhos": [],
            },
            {
                "uuid": "other_node", "condicao": "#other", "filhos": [],
            }
        ]}
        report = validate.validate(doc)
        transition_issues = [i for i in report["issues"] if i["code"] == "digression_blocked_by_transition"]
        self.assertEqual(len(transition_issues), 1)
        self.assertEqual(transition_issues[0]["severity"], "info")


if __name__ == "__main__":
    unittest.main()
