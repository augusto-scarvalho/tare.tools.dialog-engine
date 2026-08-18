"""Tests for decoupled SchemaBinding and State Machine Adapter."""

from __future__ import annotations

import unittest

from tare_dialog.schema_adapter import KeyMapping, SchemaBinding


class SchemaBindingTests(unittest.TestCase):
    """Verify that SchemaBinding adapts to arbitrary state machine JSON formats."""

    def test_auto_discovery_on_flat_watson(self) -> None:
        doc = {
            "dialog_nodes": [
                {"dialog_node": "node_1", "title": "Node 1", "conditions": "#greeting"}
            ]
        }
        binding = SchemaBinding.discover(doc)
        self.assertEqual(binding.schema_name, "watson_v1_flat")
        self.assertGreaterEqual(binding.confidence_score, 0.7)

        nodes = list(binding.iter_all_nodes(doc))
        self.assertEqual(len(nodes), 1)
        self.assertEqual(binding.get_id(nodes[0]), "node_1")
        self.assertEqual(binding.get_title(nodes[0]), "Node 1")
        self.assertEqual(binding.get_condition(nodes[0]), "#greeting")

    def test_auto_discovery_on_custom_hierarchical_json(self) -> None:
        doc = {
            "nos": [
                {
                    "uuid": "root_1",
                    "nome": "Menu Principal",
                    "condicao": "$auth == true",
                    "contexto": {"attempts": 0},
                    "filhos": [
                        {"uuid": "child_1", "nome": "Submenu", "condicao": "#opcao1"}
                    ],
                    "slots": [
                        {"uuid": "slot_1", "nome": "Slot CPF", "condicao": "@cpf"}
                    ]
                }
            ]
        }
        binding = SchemaBinding.discover(doc)
        self.assertEqual(binding.schema_name, "enterprise_hierarchical")
        self.assertGreaterEqual(binding.confidence_score, 0.9)

        all_nodes = list(binding.iter_all_nodes(doc))
        self.assertEqual(len(all_nodes), 3)  # root + slot + child

        node_ids = {binding.get_id(n) for n in all_nodes}
        self.assertEqual(node_ids, {"root_1", "child_1", "slot_1"})

    def test_custom_user_defined_binding_mapping(self) -> None:
        """User specifies custom property names for a non-Watson state machine (e.g. Rasa / Botpress)."""
        doc = {
            "states": [
                {
                    "state_id": "state_welcome",
                    "label": "Welcome Screen",
                    "guard": "user.is_logged_in == true",
                    "variables": {"retries": 1},
                    "steps": [
                        {"state_id": "state_step_1", "guard": "intent == 'buy'"}
                    ]
                }
            ]
        }
        custom_mapping = KeyMapping(
            id_keys=["state_id"],
            title_keys=["label"],
            condition_keys=["guard"],
            context_keys=["variables"],
            children_keys=["steps"],
        )
        binding = SchemaBinding(
            schema_name="custom_rasa_botpress",
            root_nodes_keys=["states"],
            mapping=custom_mapping,
        )

        nodes = list(binding.iter_all_nodes(doc))
        self.assertEqual(len(nodes), 2)
        self.assertEqual(binding.get_id(nodes[0]), "state_welcome")
        self.assertEqual(binding.get_title(nodes[0]), "Welcome Screen")
        self.assertEqual(binding.get_condition(nodes[0]), "user.is_logged_in == true")

        # Mutate condition using generic accessor
        binding.set_condition(nodes[0], "false")
        self.assertEqual(nodes[0]["guard"], "false")


if __name__ == "__main__":
    unittest.main()
