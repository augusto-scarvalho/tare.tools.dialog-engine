"""Semantic Business Rule Mutation & Test Gap Auditor.

Evaluates conversational test suites against semantic mutations of business rules,
security guardrails, underwriting conditions, and routing intents to discover
testing blindspots, dead predicates, and unverified edge cases.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from tare_dialog.test_runner import run_scenario


class RiskTier(str, Enum):
    """Risk categorization for mutated conversational business rules."""

    SECURITY_CRITICAL = "SECURITY_CRITICAL"
    BUSINESS_FINANCIAL = "BUSINESS_FINANCIAL"
    ROUTING_ESCALATION = "ROUTING_ESCALATION"
    REFINEMENT_DEADCODE = "REFINEMENT_DEADCODE"


class MutationOperator(str, Enum):
    """Formal semantic mutation operators."""

    GUARD_BYPASS = "GUARD_BYPASS"
    LIMIT_INVERSION = "LIMIT_INVERSION"
    INTENT_MUTATION = "INTENT_MUTATION"
    SLOT_BYPASS = "SLOT_BYPASS"
    SUBSUMPTION_DROP = "SUBSUMPTION_DROP"


from tare_dialog.schema_adapter import DEFAULT_BINDING, SchemaBinding


@dataclass
class RuleMutant:
    """Represents an injected business rule defect with audit tracking."""

    mutation_id: str
    node_id: str
    node_title: str
    risk_tier: RiskTier
    operator: MutationOperator
    original_expression: str
    mutated_expression: str
    explanation: str
    mutated_doc: dict[str, Any] = field(default_factory=dict)
    new_cond: str | None = None
    new_ctx_key: str | None = None
    new_ctx_val: Any = None
    status: str = "PENDING"  # "KILLED" or "SURVIVED_BLINDSPOT"
    killing_scenario_id: str | None = None
    curation_decision: str = "PENDING_REVIEW"

    def get_mutated_doc(self, baseline_doc: dict[str, Any], binding: SchemaBinding | None = None) -> dict[str, Any]:
        """Produce the mutated document variant on demand."""
        if self.mutated_doc:
            return self.mutated_doc
        b = binding or DEFAULT_BINDING or SchemaBinding.discover(baseline_doc)
        m_doc = copy.deepcopy(baseline_doc)
        for n in b.iter_all_nodes(m_doc):
            if b.get_id(n) == self.node_id:
                if self.new_cond is not None:
                    b.set_condition(n, self.new_cond)
                if self.new_ctx_key is not None:
                    b.set_context_variable(n, self.new_ctx_key, self.new_ctx_val)
                break
        return m_doc

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_tier"] = self.risk_tier.value
        d["operator"] = self.operator.value
        d.pop("mutated_doc", None)  # Exclude raw doc from summary dict
        d.pop("new_cond", None)
        d.pop("new_ctx_key", None)
        d.pop("new_ctx_val", None)
        return d


class SemanticRuleMutator:
    """Generates classified business rule mutations across arbitrary dialog trees and state machines."""

    def __init__(self, binding: SchemaBinding | None = None) -> None:
        self._counter = 0
        self.binding = binding

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"MUT-{prefix}-{self._counter:04d}"

    def generate_rule_mutants(self, document: dict[str, Any], binding: SchemaBinding | None = None) -> list[RuleMutant]:
        """Discover and mutate operational guards in document using decoupled SchemaBinding."""
        b = binding or self.binding or SchemaBinding.discover(document)
        mutants: list[RuleMutant] = []
        all_nodes = list(b.iter_all_nodes(document))

        for node in all_nodes:
            node_id = b.get_id(node)
            if not node_id:
                continue
            node_title = b.get_title(node)
            cond = b.get_condition(node)
            ctx = b.get_context(node)

            # ----------------------------------------------------------
            # 1. SECURITY CRITICAL: Authentication & Authorization Guards
            # ----------------------------------------------------------
            if "user_authenticated" in cond or "auth" in cond.lower() or "!user_authenticated" in str(ctx):
                orig = cond
                mutated = "true" if cond else "true"
                mutants.append(RuleMutant(
                    mutation_id=self._next_id("SEC"),
                    node_id=node_id,
                    node_title=node_title,
                    risk_tier=RiskTier.SECURITY_CRITICAL,
                    operator=MutationOperator.GUARD_BYPASS,
                    original_expression=orig or "user_authenticated check",
                    mutated_expression=mutated,
                    explanation="Bypassed user authentication guard to test if unauthorized users reach this node.",
                    new_cond=mutated,
                ))

            # ----------------------------------------------------------
            # 2. BUSINESS FINANCIAL: Limits & Score Thresholds
            # ----------------------------------------------------------
            for ctx_key, val in (ctx.items() if isinstance(ctx, dict) else []):
                if isinstance(val, str) and (">" in val or "<" in val or "score" in val.lower() or "limit" in val.lower()):
                    orig_val = str(val)
                    mutated_val = orig_val.replace(">=", "<").replace(">", "<=").replace("approved", "denied")
                    if mutated_val == orig_val:
                        mutated_val = f"<? false /* mutated {orig_val} */ ?>"

                    mutants.append(RuleMutant(
                        mutation_id=self._next_id("FIN"),
                        node_id=node_id,
                        node_title=node_title,
                        risk_tier=RiskTier.BUSINESS_FINANCIAL,
                        operator=MutationOperator.LIMIT_INVERSION,
                        original_expression=f"{ctx_key}: {orig_val}",
                        mutated_expression=f"{ctx_key}: {mutated_val}",
                        explanation=f"Inverted financial underwriting threshold in context variable '{ctx_key}'.",
                        new_ctx_key=ctx_key,
                        new_ctx_val=mutated_val,
                    ))

            # ----------------------------------------------------------
            # 3. ROUTING & ESCALATION: Intent & Trigger Guards
            # ----------------------------------------------------------
            if cond and cond not in {"welcome", "true", "false", "anything_else"}:
                mutated_cond = "false"
                is_escalation = any(k in cond.lower() for k in ("atendente", "humano", "transbordo", "ajuda", "duvida"))
                risk = RiskTier.ROUTING_ESCALATION if is_escalation else RiskTier.BUSINESS_FINANCIAL
                mutants.append(RuleMutant(
                    mutation_id=self._next_id("ROU"),
                    node_id=node_id,
                    node_title=node_title,
                    risk_tier=risk,
                    operator=MutationOperator.INTENT_MUTATION,
                    original_expression=cond,
                    mutated_expression=mutated_cond,
                    explanation=f"Disabled route trigger '{cond}' to test if conversational test suite detects loss of {node_title}.",
                    new_cond=mutated_cond,
                ))

        return mutants


def evaluate_rules_against_scenarios(
    document: dict[str, Any],
    scenarios: list[dict[str, Any]],
    mutator: SemanticRuleMutator | None = None,
) -> dict[str, Any]:
    """Execute scenario test suite against baseline and all rule mutants.

    A mutant is KILLED if at least one scenario behaves differently or fails assertions.
    A mutant SURVIVES if all test scenarios produce the identical output (Blindspot!).
    """
    mutator = mutator or SemanticRuleMutator()
    b = mutator.binding or SchemaBinding.discover(document)
    mutants = mutator.generate_rule_mutants(document, binding=b)

    # 1. Record baseline execution traces for each scenario
    baseline_traces: list[dict[str, Any]] = []
    for scen in scenarios:
        try:
            trace = run_scenario(document, scen)
            baseline_traces.append(trace)
        except Exception:
            baseline_traces.append({"passed": False, "trace": []})

    killed_count = 0
    survived_count = 0
    results: list[RuleMutant] = []

    for m in mutants:
        mutant_killed = False
        killing_scen_id = None
        m_doc = m.get_mutated_doc(document, binding=b)

        for i, scen in enumerate(scenarios):
            scen_id = scen.get("id") or f"scenario_{i+1}"
            base_trace = baseline_traces[i]

            try:
                m_trace = run_scenario(m_doc, scen)
                # Check if behavior diverged:
                # A) Test scenario failed assertions on mutant
                if m_trace.get("passed") is False and base_trace.get("passed") is True:
                    mutant_killed = True
                    killing_scen_id = scen_id
                    break

                # B) Visited nodes or responses diverged
                base_nodes = [t.get("node") for t in base_trace.get("trace", []) if isinstance(t, dict)]
                m_nodes = [t.get("node") for t in m_trace.get("trace", []) if isinstance(t, dict)]
                if base_nodes != m_nodes:
                    mutant_killed = True
                    killing_scen_id = scen_id
                    break

            except Exception:
                # Execution error on mutant means it broke the flow (killed)
                mutant_killed = True
                killing_scen_id = scen_id
                break

        if mutant_killed:
            m.status = "KILLED"
            m.killing_scenario_id = killing_scen_id
            m.curation_decision = "COVERED_BY_TEST"
            killed_count += 1
        else:
            m.status = "SURVIVED_BLINDSPOT"
            m.curation_decision = "PENDING_REVIEW"
            survived_count += 1

        results.append(m)

    total = len(mutants)
    score = (killed_count / total * 100.0) if total > 0 else 100.0

    return {
        "summary": {
            "total_mutations": total,
            "killed_by_tests": killed_count,
            "survived_blindspots": survived_count,
            "test_mutation_score_pct": round(score, 2),
            "by_risk_tier": {
                tier.value: sum(1 for m in results if m.risk_tier == tier)
                for tier in RiskTier
            },
            "blindspots_by_risk": {
                tier.value: sum(1 for m in results if m.risk_tier == tier and m.status == "SURVIVED_BLINDSPOT")
                for tier in RiskTier
            },
        },
        "mutations": [m.to_dict() for m in results],
        "_mutants_obj": results,
    }


def synthesize_counterexample_scenario(mutant: RuleMutant) -> dict[str, Any]:
    """Synthesize a targeted test scenario designed to kill a surviving blindspot mutant."""
    return {
        "id": f"test_synth_gap_{mutant.mutation_id.lower()}",
        "name": f"[Auto-Synthesized Gap Test] Verify {mutant.node_title} ({mutant.operator.value})",
        "description": f"Automatically synthesized to cover untested business rule in {mutant.node_id}. Expected condition: {mutant.original_expression}",
        "risk_tier": mutant.risk_tier.value,
        "turns": [
            {
                "input": {"text": f"quero testar {mutant.node_title.lower()}"},
                "expected": {
                    "node": mutant.node_id,
                }
            }
        ]
    }


def generate_audit_manifest(evaluation_report: dict[str, Any], reviewer: str = "tare.tools.automated") -> dict[str, Any]:
    """Generate a canonical, versionable mutation audit manifest for corporate compliance."""
    mutations_data = evaluation_report.get("mutations", [])
    return {
        "$schema": "tare.tools/mutation-audit/v1",
        "generated_at": "2026-08-18T15:30:00Z",
        "reviewer": reviewer,
        "summary": evaluation_report.get("summary", {}),
        "audit_findings": mutations_data,
        "recommended_actions": [
            {
                "mutation_id": m["mutation_id"],
                "node_id": m["node_id"],
                "action": "ADD_TEST_SCENARIO",
                "reason": m["explanation"],
            }
            for m in mutations_data
            if m.get("status") == "SURVIVED_BLINDSPOT"
        ]
    }
