"""Index nodes efficiently for actionable items to keep HTML file snappy and lightweight."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import watson_dialog_diff as diff
import watson_dialog_validate as validate

print("Loading documents...")
current_doc = diff.load_json(ROOT / "input" / "current.json", max_bytes=104857600)
candidate_doc = diff.load_json(ROOT / "input" / "candidate.json", max_bytes=104857600)

current_rep = validate.validate(current_doc)
candidate_rep = validate.validate(candidate_doc)

def build_node_indexer(document):
    index = {}
    variable_by_uuid = {
        str(item.get("uuid")): str(item.get("variavelContexto", "")).lstrip("$")
        for item in document.get("variaveisContexto") or []
        if isinstance(item, dict) and item.get("uuid") and item.get("variavelContexto")
    }

    def visit(nodes, parent_id=None, path=None):
        path = path or []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "")
            if not node_id:
                continue
            current_path = [*path, {"uuid": node_id, "name": node.get("nome"), "kind": "dialog_node"}]
            index[node_id] = {
                "uuid": node_id,
                "kind": "dialog_node",
                "parent_id": parent_id,
                "name": node.get("nome"),
                "status": node.get("status"),
                "condition": node.get("condicao"),
                "sequence": node.get("sequencia"),
                "jump_target": node.get("uuidEnviarPara"),
                "jump_selector": node.get("jumpSelector"),
                "in_digression_in": node.get("inDigressionIn"),
                "in_digression_out": node.get("inDigressionOut"),
                "path": current_path,
                "responses": [
                    {
                        "uuid": str(r.get("uuid")),
                        "condition": r.get("condicao"),
                        "text": r.get("textoResposta"),
                        "component_type": r.get("idTipoComponente"),
                        "channel": r.get("tipoRespostaNomeJSON"),
                    }
                    for r in node.get("respostas") or []
                    if isinstance(r, dict)
                ],
                "slots": [
                    {
                        "uuid": str(s.get("uuid")),
                        "identifier": s.get("identificador"),
                        "variable_uuid": s.get("uuidVariavelContexto"),
                        "variable_name": variable_by_uuid.get(str(s.get("uuidVariavelContexto"))),
                        "required": s.get("indicadorObrigatorio"),
                        "condition": s.get("condicao"),
                        "enable_condition": s.get("condicaoSlots"),
                        "handlers": [
                            {
                                "uuid": str(h.get("uuid")),
                                "name": h.get("nome"),
                                "condition": h.get("condicao"),
                                "event_name": h.get("event_name"),
                            }
                            for h in s.get("filhos") or []
                            if isinstance(h, dict)
                        ]
                    }
                    for s in node.get("slots") or []
                    if isinstance(s, dict)
                ],
                "children": [
                    {
                        "uuid": str(c.get("uuid")),
                        "name": c.get("nome"),
                        "condition": c.get("condicao"),
                        "status": c.get("status"),
                    }
                    for c in node.get("filhos") or []
                    if isinstance(c, dict)
                ],
                "raw_json": {k: v for k, v in node.items() if k not in ("filhos", "slots")},
            }

            for slot in node.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = str(slot.get("uuid") or "")
                if not slot_id:
                    continue
                slot_path = [*current_path, {"uuid": f"slot:{slot_id}", "name": slot.get("identificador"), "kind": "slot"}]
                index[f"slot:{slot_id}"] = {
                    "uuid": f"slot:{slot_id}",
                    "raw_uuid": slot_id,
                    "kind": "slot",
                    "parent_node_id": node_id,
                    "parent_name": node.get("nome"),
                    "name": slot.get("identificador"),
                    "condition": slot.get("condicao"),
                    "enable_condition": slot.get("condicaoSlots"),
                    "required": slot.get("indicadorObrigatorio"),
                    "variable_uuid": slot.get("uuidVariavelContexto"),
                    "variable_name": variable_by_uuid.get(str(slot.get("uuidVariavelContexto"))),
                    "path": slot_path,
                    "handlers": [
                        {
                            "uuid": str(h.get("uuid")),
                            "name": h.get("nome"),
                            "condition": h.get("condicao"),
                            "event_name": h.get("event_name"),
                            "status": h.get("status"),
                        }
                        for h in slot.get("filhos") or []
                        if isinstance(h, dict)
                    ],
                    "raw_json": {k: v for k, v in slot.items() if k != "filhos"},
                }

            visit(node.get("filhos") or [], node_id, current_path)

    visit(document.get("nos") or [])
    return index

current_index = build_node_indexer(current_doc)
candidate_index = build_node_indexer(candidate_doc)

def get_node_details(corpus_index, node_key):
    if node_key in corpus_index:
        return corpus_index[node_key]
    if node_key.startswith("slot:") and node_key in corpus_index:
        return corpus_index[node_key]
    if node_key.startswith("response:"):
        parts = node_key.split(":")
        if len(parts) >= 2 and parts[1] in corpus_index:
            return corpus_index[parts[1]]
    raw_key = node_key.removeprefix("slot:")
    if raw_key in corpus_index:
        return corpus_index[raw_key]
    return None

# Only index actionable nodes + sample infos to keep file size ultra-optimized (< 300 KB)
current_actionable = [i for i in current_rep["issues"] if i["severity"] in ("error", "warning")]
current_info = [i for i in current_rep["issues"] if i["severity"] == "info"]

current_nodes_map = {}
for item in current_actionable + current_info[:30]:
    node_key = item["node"]
    details = get_node_details(current_index, node_key)
    if details:
        current_nodes_map[node_key] = details
        # Also index path ancestor nodes
        for p in details.get("path") or []:
            p_uuid = p.get("uuid")
            if p_uuid and p_uuid not in current_nodes_map and p_uuid in current_index:
                current_nodes_map[p_uuid] = current_index[p_uuid]

candidate_actionable = [i for i in candidate_rep["issues"] if i["severity"] in ("error", "warning")]
candidate_info = [i for i in candidate_rep["issues"] if i["severity"] == "info"]

candidate_nodes_map = {}
for item in candidate_actionable + candidate_info[:30]:
    node_key = item["node"]
    details = get_node_details(candidate_index, node_key)
    if details:
        candidate_nodes_map[node_key] = details
        for p in details.get("path") or []:
            p_uuid = p.get("uuid")
            if p_uuid and p_uuid not in candidate_nodes_map and p_uuid in candidate_index:
                candidate_nodes_map[p_uuid] = candidate_index[p_uuid]

payload = {
    "generated_at": "2026-08-16T10:15:00-03:00",
    "current": {
        "summary": current_rep["summary"],
        "actionable_issues": current_actionable,
        "sample_info_issues": current_info[:30],
        "total_info_count": len(current_info),
        "nodes": current_nodes_map,
    },
    "candidate": {
        "summary": candidate_rep["summary"],
        "actionable_issues": candidate_actionable,
        "sample_info_issues": candidate_info[:30],
        "total_info_count": len(candidate_info),
        "nodes": candidate_nodes_map,
    }
}

out_data = ROOT / "output" / "validation_triage_data.json"
out_data.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Generated optimized dataset: {len(current_nodes_map)} nodes indexed.")
