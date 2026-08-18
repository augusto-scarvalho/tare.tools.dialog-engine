"""Matrix of Positive vs Negative Curation Tests (Zero False Positives Validation)."""

import unittest
from tare_dialog.validator import validate
from tare_dialog.spel import evaluate, parse


class CurationPositiveNegativeMatrixTests(unittest.TestCase):
    """Systematic pairwise testing: Every error rule MUST have an equivalent valid pattern that produces 0 false positives."""

    # ------------------------------------------------------------------
    # 1. Jumps: Unresolved Jump Target vs Valid Jump Target & Builtin "root"
    # ------------------------------------------------------------------
    def test_pair_jump_target(self) -> None:
        # Negative: target does not exist
        broken = {
            "nos": [
                {"uuid": "n1", "nome": "Origem", "condicao": "true", "uuidEnviarPara": "uuid_inexistente_404"}
            ]
        }
        rep_broken = validate(broken)
        self.assertTrue(any(iss["code"] == "unresolved_jump_target" for iss in rep_broken["issues"]))

        # Positive: target exists
        valid_target = {
            "nos": [
                {"uuid": "n1", "nome": "Origem", "condicao": "true", "uuidEnviarPara": "n2"},
                {"uuid": "n2", "nome": "Destino", "condicao": "true"}
            ]
        }
        rep_valid_target = validate(valid_target)
        self.assertFalse(any(iss["code"] == "unresolved_jump_target" for iss in rep_valid_target["issues"]))

        # Positive: builtin "root" target
        valid_root_target = {
            "nos": [
                {"uuid": "n1", "nome": "Restart", "condicao": "true", "uuidEnviarPara": "root"}
            ]
        }
        rep_root = validate(valid_root_target)
        self.assertFalse(any(iss["code"] == "unresolved_jump_target" for iss in rep_root["issues"]))

    # ------------------------------------------------------------------
    # 2. Disabled Nodes: condition "false" vs Active Conditions
    # ------------------------------------------------------------------
    def test_pair_disabled_condition(self) -> None:
        # Negative: literal false
        broken = {
            "nos": [
                {"uuid": "n1", "nome": "Desativado", "condicao": "false"}
            ]
        }
        rep_broken = validate(broken)
        self.assertTrue(any(iss["code"] == "disabled_condition_false" for iss in rep_broken["issues"]))

        # Positive: active conditions (intent, entity, variable, true)
        for cond in ["#fazer_pix", "@operacao:pix", "$pix_amount > 0", "true", "anything_else"]:
            valid = {
                "nos": [
                    {"uuid": "n1", "nome": "Ativo", "condicao": cond}
                ]
            }
            rep_valid = validate(valid)
            self.assertFalse(any(iss["code"] == "disabled_condition_false" for iss in rep_valid["issues"]))

    # ------------------------------------------------------------------
    # 3. SpEL Syntax: Unbalanced Parenthesis vs Complex Ternary Expressions
    # ------------------------------------------------------------------
    def test_pair_spel_syntax(self) -> None:
        # Negative: unclosed parenthesis
        broken_spel = "<? (input.text ?>"
        node_broken = {
            "dialog_nodes": [
                {
                    "dialog_node": "node_broken_spel",
                    "title": "SpEL Error",
                    "conditions": "true",
                    "context": {"decision": broken_spel}
                }
            ]
        }
        rep_broken = validate(node_broken)
        self.assertTrue(any("unclosed_parenthesis" in iss["code"] for iss in rep_broken["issues"]))

        # Positive: complex valid expressions
        valid_spels = [
            "<? (input.text != null) ? 'token' : 'ok' ?>",
            "<? $balance >= 100 && $account_type.equalsIgnoreCase('checking') ?>",
            "<? now().isAfter('2026-01-01') ?>",
            "<? input.text.matches('^[0-9]{11}$') ?>"
        ]
        for expr in valid_spels:
            node_valid = {
                "dialog_nodes": [
                    {
                        "dialog_node": "node_valid_spel",
                        "title": "SpEL Valid",
                        "conditions": "true",
                        "context": {"decision": expr}
                    }
                ]
            }
            rep_valid = validate(node_valid)
            self.assertFalse(any(iss["code"].startswith("context_spel_") for iss in rep_valid["issues"]))

    # ------------------------------------------------------------------
    # 4. Slot Enable Contradiction: $var && $var == false vs Real Conditions
    # ------------------------------------------------------------------
    def test_pair_slot_enable_conditions(self) -> None:
        # Negative: contradictory self-false condition
        broken_slot = {
            "nos": [
                {
                    "uuid": "frame1",
                    "nome": "Frame",
                    "condicao": "true",
                    "slots": [
                        {
                            "uuid": "s1",
                            "condicao": "@sys-number",
                            "condicaoSlots": "$pix_confirmed && $pix_confirmed == false"
                        }
                    ]
                }
            ]
        }
        rep_broken = validate(broken_slot)
        self.assertTrue(any(iss["code"] == "unsatisfiable_slot_enable_condition" for iss in rep_broken["issues"]))

        # Positive: legitimate conditions
        for cond in ["$pix_key != null", "$pix_amount > 100", "$status == 'pending'", "true"]:
            valid_slot = {
                "nos": [
                    {
                        "uuid": "frame1",
                        "nome": "Frame",
                        "condicao": "true",
                        "slots": [
                            {
                                "uuid": "s1",
                                "condicao": "@sys-number",
                                "condicaoSlots": cond
                            }
                        ]
                    }
                ]
            }
            rep_valid = validate(valid_slot)
            self.assertFalse(any(iss["code"] == "unsatisfiable_slot_enable_condition" for iss in rep_valid["issues"]))

    # ------------------------------------------------------------------
    # 5. Slot Dependency: Later Slot Dependency vs Prior Slot Reference
    # ------------------------------------------------------------------
    def test_pair_slot_dependencies(self) -> None:
        # Negative: slot 1 depends on $slot2_var
        broken_slots = {
            "variaveisContexto": [
                {"uuid": "v1", "variavelContexto": "$pix_key"},
                {"uuid": "v2", "variavelContexto": "$pix_amount"}
            ],
            "nos": [
                {
                    "uuid": "frame1",
                    "nome": "Frame",
                    "condicao": "true",
                    "slots": [
                        {
                            "uuid": "s1",
                            "uuidVariavelContexto": "v1",
                            "condicao": "@chave_pix && $pix_amount > 0"  # Depends on later slot!
                        },
                        {
                            "uuid": "s2",
                            "uuidVariavelContexto": "v2",
                            "condicao": "@sys-number"
                        }
                    ]
                }
            ]
        }
        rep_broken = validate(broken_slots)
        self.assertTrue(any(iss["code"] == "slot_depends_on_later_slot" for iss in rep_broken["issues"]))

        # Positive: slot 2 depends on $pix_key (prior slot)
        valid_slots = {
            "variaveisContexto": [
                {"uuid": "v1", "variavelContexto": "$pix_key"},
                {"uuid": "v2", "variavelContexto": "$pix_amount"}
            ],
            "nos": [
                {
                    "uuid": "frame1",
                    "nome": "Frame",
                    "condicao": "true",
                    "slots": [
                        {
                            "uuid": "s1",
                            "uuidVariavelContexto": "v1",
                            "condicao": "@chave_pix"
                        },
                        {
                            "uuid": "s2",
                            "uuidVariavelContexto": "v2",
                            "condicao": "@sys-number && $pix_key != null"  # Legitimate prior dependency!
                        }
                    ]
                }
            ]
        }
        rep_valid = validate(valid_slots)
        self.assertFalse(any(iss["code"] == "slot_depends_on_later_slot" for iss in rep_valid["issues"]))

    # ------------------------------------------------------------------
    # 6. Sibling Order: Ambiguous Tie vs Clean Sibling Order
    # ------------------------------------------------------------------
    def test_pair_sibling_chains(self) -> None:
        # Negative: two nodes claiming previous_sibling = "n1"
        broken_siblings = {
            "dialog_nodes": [
                {"dialog_node": "n1", "title": "First", "conditions": "true", "parent": None, "previous_sibling": None},
                {"dialog_node": "n2", "title": "Second A", "conditions": "true", "parent": None, "previous_sibling": "n1"},
                {"dialog_node": "n3", "title": "Second B", "conditions": "true", "parent": None, "previous_sibling": "n1"}
            ]
        }
        rep_broken = validate(broken_siblings)
        self.assertTrue(any(iss["code"] == "previous_sibling_has_multiple_successors" for iss in rep_broken["issues"]))

        # Positive: cleanly ordered linked list
        valid_siblings = {
            "dialog_nodes": [
                {"dialog_node": "n1", "title": "First", "conditions": "true", "parent": None, "previous_sibling": None},
                {"dialog_node": "n2", "title": "Second", "conditions": "true", "parent": None, "previous_sibling": "n1"},
                {"dialog_node": "n3", "title": "Third", "conditions": "true", "parent": None, "previous_sibling": "n2"}
            ]
        }
        rep_valid = validate(valid_siblings)
        self.assertFalse(any(iss["code"] == "previous_sibling_has_multiple_successors" for iss in rep_valid["issues"]))


if __name__ == "__main__":
    unittest.main()
