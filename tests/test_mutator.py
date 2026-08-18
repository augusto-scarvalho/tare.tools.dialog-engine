"""Automated tests for the Symbolic AST & Automata Mutation Engine."""

import json
import unittest
from pathlib import Path

from tare_dialog.mutator import DialogTreeMutator, calculate_mutation_score
from tare_dialog.validator import validate

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class MutatorEngineTests(unittest.TestCase):
    """Tests for DialogTreeMutator and calculate_mutation_score."""

    def setUp(self) -> None:
        self.mutator = DialogTreeMutator(seed=123)
        self.base_tree = json.loads((FIXTURES_DIR / "demo_banking_current.json").read_text(encoding="utf-8"))

    def test_dangling_jump_mutator(self) -> None:
        mutant = self.mutator.mutate_dangling_jump(self.base_tree)
        self.assertIsNotNone(mutant)
        self.assertEqual(mutant.expected_issue_code, "unresolved_jump_target")
        rep = validate(mutant.mutated_tree)
        self.assertTrue(any(iss["code"] == "unresolved_jump_target" for iss in rep["issues"]))

    def test_sibling_fork_mutator(self) -> None:
        mutant = self.mutator.mutate_duplicate_sibling_successor(self.base_tree)
        self.assertIsNotNone(mutant)
        self.assertEqual(mutant.expected_issue_code, "previous_sibling_has_multiple_successors")
        rep = validate(mutant.mutated_tree)
        self.assertTrue(any(iss["code"] == "previous_sibling_has_multiple_successors" for iss in rep["issues"]))

    def test_unclosed_spel_parenthesis_mutator(self) -> None:
        mutant = self.mutator.mutate_unclosed_spel_parenthesis(self.base_tree)
        self.assertIsNotNone(mutant)
        self.assertEqual(mutant.expected_issue_code, "context_spel_unclosed_parenthesis")
        rep = validate(mutant.mutated_tree)
        self.assertTrue(any("unclosed_parenthesis" in iss["code"] for iss in rep["issues"]))

    def test_disabled_condition_mutator(self) -> None:
        mutant = self.mutator.mutate_disabled_condition_false(self.base_tree)
        self.assertIsNotNone(mutant)
        self.assertEqual(mutant.expected_issue_code, "disabled_condition_false")
        rep = validate(mutant.mutated_tree)
        self.assertTrue(any(iss["code"] == "disabled_condition_false" for iss in rep["issues"]))

    def test_metamorphic_neutral_mutator_does_not_introduce_false_positives(self) -> None:
        mutant = self.mutator.mutate_metamorphic_neutral(self.base_tree)
        self.assertIsNone(mutant.expected_issue_code)

        base_rep = validate(self.base_tree)
        mutant_rep = validate(mutant.mutated_tree)

        base_codes = {iss["code"] for iss in base_rep["issues"]}
        mutant_codes = {iss["code"] for iss in mutant_rep["issues"]}
        self.assertEqual(base_codes, mutant_codes)

    def test_calculate_mutation_score_achieves_100_percent(self) -> None:
        score_rep = calculate_mutation_score(self.base_tree, validate)
        self.assertEqual(score_rep["mutation_score_pct"], 100.0)
        self.assertEqual(score_rep["survived_mutants"], 0)
        self.assertEqual(score_rep["metamorphic_neutral_passed"], 1)
        self.assertEqual(score_rep["metamorphic_neutral_failed"], 0)


if __name__ == "__main__":
    unittest.main()
