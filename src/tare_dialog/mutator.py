"""Symbolic AST & Automata Mutation Engine for Conversational State Graphs.

Provides systematic graph perturbations, predicate inversions, dangling transition
injections, and metamorphic relation testing for dialog trees and AI agent states.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from tare_dialog.validator import validate


@dataclass(frozen=True)
class Mutant:
    """Represents a mutated dialog tree variant with expected validation outcome."""

    mutator_name: str
    description: str
    expected_issue_code: str | None  # None for neutral/metamorphic mutants
    mutated_tree: dict[str, Any]
    target_node_id: str | None = None


class DialogTreeMutator:
    """Systematic AST and automata mutation generator for dialog trees."""

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------
    # 1. GRAPH TOPOLOGY & JUMP MUTATORS
    # ------------------------------------------------------------------
    def mutate_dangling_jump(self, tree: dict[str, Any]) -> Mutant | None:
        """Mutate a valid jump target into a non-existent UUID."""
        mutant_tree = copy.deepcopy(tree)
        nodes = mutant_tree.get("dialog_nodes") or mutant_tree.get("nos") or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            # Watson V1 next_step
            if "next_step" in node and isinstance(node["next_step"], dict) and node["next_step"].get("behavior") == "jump_to":
                target = node["next_step"].get("dialog_node")
                if target and target != "root":
                    node["next_step"]["dialog_node"] = f"mutant_ghost_{self.rng.randint(1000, 9999)}"
                    return Mutant(
                        mutator_name="dangling_jump_injection",
                        description=f"Altered jump target in node '{node.get('dialog_node') or node.get('uuid')}' to a ghost UUID.",
                        expected_issue_code="unresolved_jump_target",
                        mutated_tree=mutant_tree,
                        target_node_id=str(node.get("dialog_node") or node.get("uuid")),
                    )
            # Enterprise format uuidEnviarPara
            if node.get("uuidEnviarPara") and node.get("uuidEnviarPara") != "root":
                node["uuidEnviarPara"] = f"mutant_ghost_{self.rng.randint(1000, 9999)}"
                return Mutant(
                    mutator_name="dangling_jump_injection",
                    description=f"Altered uuidEnviarPara in node '{node.get('uuid')}' to a ghost UUID.",
                    expected_issue_code="unresolved_jump_target",
                    mutated_tree=mutant_tree,
                    target_node_id=str(node.get("uuid")),
                )
        return None

    def mutate_duplicate_sibling_successor(self, tree: dict[str, Any]) -> Mutant | None:
        """Mutate sibling chain by forcing two nodes to have the exact same previous_sibling."""
        mutant_tree = copy.deepcopy(tree)
        nodes = mutant_tree.get("dialog_nodes") or []
        if len(nodes) >= 3:
            first_id = nodes[0].get("dialog_node")
            if first_id:
                nodes[1]["previous_sibling"] = first_id
                nodes[2]["previous_sibling"] = first_id
                return Mutant(
                    mutator_name="sibling_fork_mutation",
                    description=f"Pointed both node '{nodes[1].get('dialog_node')}' and '{nodes[2].get('dialog_node')}' to previous_sibling '{first_id}'.",
                    expected_issue_code="previous_sibling_has_multiple_successors",
                    mutated_tree=mutant_tree,
                    target_node_id=str(nodes[2].get("dialog_node")),
                )
        return None

    # ------------------------------------------------------------------
    # 2. PREDICATE & SPEL MUTATORS
    # ------------------------------------------------------------------
    def mutate_unclosed_spel_parenthesis(self, tree: dict[str, Any]) -> Mutant | None:
        """Inject unclosed parenthesis into a SpEL context expression or condition."""
        mutant_tree = copy.deepcopy(tree)
        nodes = mutant_tree.get("dialog_nodes") or mutant_tree.get("nos") or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            ctx = node.get("context") or node.get("contexto")
            if isinstance(ctx, dict):
                for k, v in ctx.items():
                    if isinstance(v, str) and ("<?" in v or "$" in v):
                        ctx[k] = "<? (input.text != null ?>"
                        return Mutant(
                            mutator_name="unclosed_spel_parenthesis",
                            description=f"Injected unclosed parenthesis into context variable '{k}' in node '{node.get('dialog_node') or node.get('uuid')}'.",
                            expected_issue_code="context_spel_unclosed_parenthesis",
                            mutated_tree=mutant_tree,
                            target_node_id=str(node.get("dialog_node") or node.get("uuid")),
                        )
        # If no context found, inject one
        if nodes and isinstance(nodes[0], dict):
            nodes[0]["context"] = {"decision": "<? (input.text ?>"}
            return Mutant(
                mutator_name="unclosed_spel_parenthesis",
                description=f"Injected unclosed parenthesis context in node '{nodes[0].get('dialog_node') or nodes[0].get('uuid')}'.",
                expected_issue_code="context_spel_unclosed_parenthesis",
                mutated_tree=mutant_tree,
                target_node_id=str(nodes[0].get("dialog_node") or nodes[0].get("uuid")),
            )
        return None

    def mutate_disabled_condition_false(self, tree: dict[str, Any]) -> Mutant | None:
        """Mutate an active node condition to explicit 'false'."""
        mutant_tree = copy.deepcopy(tree)
        nodes = mutant_tree.get("dialog_nodes") or mutant_tree.get("nos") or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            cond = node.get("conditions") or node.get("condicao")
            if cond and str(cond).strip().lower() not in {"false", "welcome", "anything_else"}:
                if "conditions" in node:
                    node["conditions"] = "false"
                else:
                    node["condicao"] = "false"
                return Mutant(
                    mutator_name="disabled_condition_injection",
                    description=f"Injected explicit condition 'false' into operational node '{node.get('dialog_node') or node.get('uuid')}'.",
                    expected_issue_code="disabled_condition_false",
                    mutated_tree=mutant_tree,
                    target_node_id=str(node.get("dialog_node") or node.get("uuid")),
                )
        return None

    # ------------------------------------------------------------------
    # 3. SLOT & FRAME MUTATORS
    # ------------------------------------------------------------------
    def mutate_unsatisfiable_slot_enable(self, tree: dict[str, Any]) -> Mutant | None:
        """Inject self-contradictory guard ($var && $var == false) into a slot."""
        mutant_tree = copy.deepcopy(tree)
        nodes = mutant_tree.get("nos") or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            slots = node.get("slots") or []
            if slots and isinstance(slots[0], dict):
                slots[0]["condicaoSlots"] = "$pix_confirmed && $pix_confirmed == false"
                return Mutant(
                    mutator_name="unsatisfiable_slot_enable",
                    description=f"Injected contradictory enable condition in slot '{slots[0].get('uuid')}'.",
                    expected_issue_code="unsatisfiable_slot_enable_condition",
                    mutated_tree=mutant_tree,
                    target_node_id=str(slots[0].get("uuid")),
                )
        return None

    def mutate_slot_dependency_inversion(self, tree: dict[str, Any]) -> Mutant | None:
        """Inject dependency on a later slot variable inside an earlier slot."""
        mutant_tree = copy.deepcopy(tree)
        vars_ctx = mutant_tree.get("variaveisContexto") or []
        nodes = mutant_tree.get("nos") or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            slots = node.get("slots") or []
            if len(slots) >= 2 and len(vars_ctx) >= 2:
                later_var = str(vars_ctx[1].get("variavelContexto") or "$later_var")
                slots[0]["condicao"] = f"@some_entity && {later_var} > 0"
                return Mutant(
                    mutator_name="slot_dependency_inversion",
                    description=f"Injected forward dependency on '{later_var}' in prior slot '{slots[0].get('uuid')}'.",
                    expected_issue_code="slot_depends_on_later_slot",
                    mutated_tree=mutant_tree,
                    target_node_id=str(slots[0].get("uuid")),
                )
        return None

    # ------------------------------------------------------------------
    # 4. METAMORPHIC (NEUTRAL) MUTATORS (Zero False Positive Tests)
    # ------------------------------------------------------------------
    def mutate_metamorphic_neutral(self, tree: dict[str, Any]) -> Mutant:
        """Apply non-operational changes (whitespace, key ordering, metadata tags).
        
        A sound validator MUST NOT report any new validation issues on this mutant.
        """
        mutant_tree = copy.deepcopy(tree)
        # Add non-operational benign metadata
        mutant_tree["_metamorphic_run_id"] = f"meta_{self.rng.randint(10000, 99999)}"
        nodes = mutant_tree.get("dialog_nodes") or mutant_tree.get("nos") or []
        for node in nodes:
            if isinstance(node, dict):
                node["_audit_timestamp"] = "2026-08-18T12:00:00Z"
                # Reorder internal keys without changing semantic content
                keys = list(node.keys())
                self.rng.shuffle(keys)
                reordered = {k: node[k] for k in keys}
                node.clear()
                node.update(reordered)
        return Mutant(
            mutator_name="metamorphic_neutral_perturbation",
            description="Reordered dictionary keys and added inert audit metadata without altering semantics.",
            expected_issue_code=None,  # MUST NOT fail validation!
            mutated_tree=mutant_tree,
        )

    # ------------------------------------------------------------------
    # SUITE GENERATOR & SCORE EVALUATOR
    # ------------------------------------------------------------------
    def generate_all_mutants(self, tree: dict[str, Any]) -> list[Mutant]:
        """Generate a complete battery of mutants from a baseline dialog tree."""
        mutators: list[Callable[[dict[str, Any]], Mutant | None]] = [
            self.mutate_dangling_jump,
            self.mutate_duplicate_sibling_successor,
            self.mutate_unclosed_spel_parenthesis,
            self.mutate_disabled_condition_false,
            self.mutate_unsatisfiable_slot_enable,
            self.mutate_slot_dependency_inversion,
            self.mutate_metamorphic_neutral,
        ]
        results: list[Mutant] = []
        for mutator in mutators:
            mutant = mutator(tree)
            if mutant is not None:
                results.append(mutant)
        return results


def calculate_mutation_score(
    tree: dict[str, Any],
    validator_func: Callable[[dict[str, Any]], dict[str, Any]] = validate,
) -> dict[str, Any]:
    """Execute mutation analysis against a dialog tree and compute the formal Mutation Score."""
    mutator = DialogTreeMutator()
    mutants = mutator.generate_all_mutants(tree)

    total_adversarial = 0
    killed = 0
    survived: list[dict[str, Any]] = []
    neutral_passed = 0
    neutral_failed = 0

    for m in mutants:
        rep = validator_func(m.mutated_tree)
        detected_codes = {iss.get("code") for iss in rep.get("issues", [])}

        if m.expected_issue_code is None:
            # Metamorphic neutral mutant: must not introduce spurious errors
            base_rep = validator_func(tree)
            base_codes = {iss.get("code") for iss in base_rep.get("issues", [])}
            diff_codes = detected_codes - base_codes
            if not diff_codes:
                neutral_passed += 1
            else:
                neutral_failed += 1
                survived.append({
                    "mutator": m.mutator_name,
                    "type": "FALSE_POSITIVE",
                    "description": m.description,
                    "spurious_codes": sorted(diff_codes),
                })
        else:
            total_adversarial += 1
            # Check if expected issue code was killed (detected)
            # Or if variant of code matched (e.g. unclosed_parenthesis)
            is_killed = any(
                m.expected_issue_code == code or m.expected_issue_code in str(code)
                for code in detected_codes
            )
            if is_killed:
                killed += 1
            else:
                survived.append({
                    "mutator": m.mutator_name,
                    "type": "SURVIVED_MUTANT",
                    "description": m.description,
                    "expected_code": m.expected_issue_code,
                    "detected_codes": sorted(detected_codes),
                })

    score = (killed / total_adversarial * 100.0) if total_adversarial > 0 else 100.0

    return {
        "total_mutants": len(mutants),
        "adversarial_mutants": total_adversarial,
        "killed_mutants": killed,
        "survived_mutants": len(survived),
        "mutation_score_pct": round(score, 2),
        "metamorphic_neutral_passed": neutral_passed,
        "metamorphic_neutral_failed": neutral_failed,
        "survived_details": survived,
    }
