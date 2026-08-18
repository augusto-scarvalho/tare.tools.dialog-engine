"""Automated tests for Semantic Business Rule Mutation & Test Gap Auditor."""

import json
import unittest
from pathlib import Path

from tare_dialog.rule_mutator import (
    MutationOperator,
    RiskTier,
    SemanticRuleMutator,
    evaluate_rules_against_scenarios,
    generate_audit_manifest,
    synthesize_counterexample_scenario,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class RuleMutatorEngineTests(unittest.TestCase):
    """Tests for SemanticRuleMutator, evaluate_rules_against_scenarios, and manifest generation."""

    def setUp(self) -> None:
        self.doc = json.loads((FIXTURES_DIR / "demo_banking_current.json").read_text(encoding="utf-8"))
        self.scenarios = json.loads((FIXTURES_DIR / "demo_banking_scenarios.json").read_text(encoding="utf-8"))
        self.mutator = SemanticRuleMutator()

    def test_generates_classified_rule_mutants(self) -> None:
        mutants = self.mutator.generate_rule_mutants(self.doc)
        self.assertGreater(len(mutants), 0)

        risk_tiers = {m.risk_tier for m in mutants}
        self.assertTrue(RiskTier.BUSINESS_FINANCIAL in risk_tiers or RiskTier.ROUTING_ESCALATION in risk_tiers)

        operators = {m.operator for m in mutants}
        self.assertTrue(MutationOperator.INTENT_MUTATION in operators or MutationOperator.LIMIT_INVERSION in operators)

    def test_evaluates_scenarios_and_discovers_blindspots(self) -> None:
        report = evaluate_rules_against_scenarios(self.doc, self.scenarios, self.mutator)
        summary = report["summary"]

        self.assertGreater(summary["total_mutations"], 0)
        self.assertGreaterEqual(summary["killed_by_tests"], 1)  # Card invoice is covered
        self.assertGreater(summary["survived_blindspots"], 0)   # Human handoff is not covered

    def test_synthesizes_counterexample_gap_scenarios(self) -> None:
        mutants = self.mutator.generate_rule_mutants(self.doc)
        survived_mutant = next((m for m in mutants if "handoff" in m.node_id or "limit" in m.node_id), mutants[0])

        synth_scenario = synthesize_counterexample_scenario(survived_mutant)
        self.assertIn("turns", synth_scenario)
        self.assertEqual(synth_scenario["turns"][0]["expected"]["node"], survived_mutant.node_id)

    def test_generates_canonical_audit_manifest(self) -> None:
        report = evaluate_rules_against_scenarios(self.doc, self.scenarios, self.mutator)
        manifest = generate_audit_manifest(report, reviewer="curator@tare.tools")

        self.assertEqual(manifest["$schema"], "tare.tools/mutation-audit/v1")
        self.assertEqual(manifest["reviewer"], "curator@tare.tools")
        self.assertIn("summary", manifest)
        self.assertIn("recommended_actions", manifest)


if __name__ == "__main__":
    unittest.main()
