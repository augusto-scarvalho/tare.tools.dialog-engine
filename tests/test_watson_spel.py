"""Tests for the safe SpEL evaluator used in dialog conditions."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(os.environ.get("WATSON_SPEL_PATH", ROOT / "src/tare_dialog/spel.py"))
SPEC = importlib.util.spec_from_file_location("watson_spel_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
spel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = spel
SPEC.loader.exec_module(spel)
UNKNOWN = spel.UNKNOWN
evaluate_condition = spel.evaluate_condition
evaluate_expression = spel.evaluate_expression
template_syntax_diagnostics = spel.template_syntax_diagnostics


class WatsonSpelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = {
            "input": {"text": "Olá MUNDO"},
            "context": {"my_other_var": "bb", "products": ["bb", "other"], "profile": {"active": True}},
            "intents": [{"intent": "cancelar", "confidence": 0.99}],
            "entities": {"produto": ["bb", "cartao"]},
        }

    def test_string_chaining_and_boolean_operators(self) -> None:
        expression = "input.text.toLowerCase().contains('mundo') && #cancelar"
        self.assertIs(evaluate_condition(expression, self.environment), True)

    def test_filter_uses_the_local_variable_and_context(self) -> None:
        expression = "$products.filter('e', 'e == $my_other_var').size() == 1"
        self.assertIs(evaluate_condition(expression, self.environment), True)

    def test_properties_indexes_entities_and_unknown_values(self) -> None:
        self.assertIs(evaluate_condition("$profile.active && @produto.contains('bb') && intents[0].confidence >= 0.9", self.environment), True)
        self.assertIs(evaluate_condition("$missing.toLowerCase() == 'x'", self.environment), UNKNOWN)

    def test_unsupported_methods_are_unknown_not_executed(self) -> None:
        self.assertIs(evaluate_expression("input.text.arbitraryCode()", self.environment), UNKNOWN)

    def test_watson_shorthand_regex_and_ternary_syntax(self) -> None:
        self.environment["context"]["channel"] = "hs-APF"
        self.assertIs(evaluate_condition("$channel:(hs-APF) && input.text matches 'Olá.*'", self.environment), True)
        self.assertEqual(evaluate_expression("$profile.active ? 'yes' : 'no'", self.environment), "yes")

    def test_dialog_valid_entity_names_negative_values_and_random_construction(self) -> None:
        self.environment["entities"]["5w1h"] = ["porque"]
        self.environment["entities"]["sys-number"] = [-1]
        self.assertIs(evaluate_condition("@5w1h && @sys-number:-1", self.environment), True)
        self.assertIs(evaluate_expression("new Random().nextInt(2)", self.environment), UNKNOWN)

    def test_context_template_syntax_diagnostics_are_conservative_and_quote_aware(self) -> None:
        self.assertEqual(template_syntax_diagnostics("prefix <? input.text.toLowerCase() ?> suffix"), [])
        self.assertEqual(template_syntax_diagnostics("<? '?>'.contains('>') ?>"), [])
        self.assertEqual(template_syntax_diagnostics("<? @pattern.literal.replace('\\', '') ?>"), [])
        self.assertEqual(template_syntax_diagnostics("<? 'Tony''s ?> marker'.contains('x') ?>"), [])
        self.assertEqual(spel.syntax_diagnostics("@pattern.literal.replace('\\', '')"), [])
        self.assertEqual(spel.syntax_diagnostics("'Tony''s' == 'Tony''s'"), [])

        codes = [item["code"] for item in template_syntax_diagnostics("<? $ready && ?> / <? ?> / <? input.text")]
        self.assertEqual(codes, ["missing_right_operand", "empty_expression", "unclosed_template"])

        diagnostics = template_syntax_diagnostics("a <? ($ready ?> b <? input.text ?>")
        self.assertEqual([item["code"] for item in diagnostics], ["unclosed_parenthesis"])
        self.assertEqual(diagnostics[0]["ordinal"], 1)
        self.assertEqual(diagnostics[0]["expression"], "($ready")


if __name__ == "__main__":
    unittest.main()
