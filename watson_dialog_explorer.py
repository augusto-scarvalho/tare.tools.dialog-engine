"""Universal Dialog AST Explorer & Polymorphic Schema Adapter for tare.tools.dialog-engine.

Provides automatic introspection, extraction, and bidirectional normalization for:
1. Official IBM Watson Assistant Skill JSON (V1 classic and V2 flat pointer topologies).
2. Hierarchical / Nested enterprise dialog trees (nos/filhos/respostas/slots).
3. Multi-channel output schemas (WhatsApp, Web Chat, Mobile App, Voice, Slack).
4. Multimodal & Rich media responses (text, images, carousels, cards, options, pauses).
5. Slots, slot event handlers, and context variable lifecycles.
6. Arbitrary rich metadata, tags, designer coordinates, and action payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class DialogJump:
    target_id: str
    selector: str = "condition"  # 'condition', 'body', 'user_input', 'move_on'
    behavior: str = "jump_to"    # 'jump_to', 'skip_user_input', 'wait_user_input'

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "selector": self.selector,
            "behavior": self.behavior,
        }


@dataclass
class DialogResponse:
    id: str
    response_type: str = "text"  # 'text', 'image', 'option', 'pause', 'connect_to_agent', 'card', 'carousel', 'video', 'audio', 'user_defined'
    channel: str = "default"     # 'default', 'whatsapp', 'web_chat', 'mobile_app', 'voice', etc.
    condition: str | None = None
    text_values: list[str] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    title: str | None = None
    description: str | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    pause_ms: int | None = None
    typing_indicator: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "response_type": self.response_type,
            "channel": self.channel,
            "condition": self.condition,
            "text_values": self.text_values,
            "media_urls": self.media_urls,
            "title": self.title,
            "description": self.description,
            "options": self.options,
            "pause_ms": self.pause_ms,
            "typing_indicator": self.typing_indicator,
            "raw_payload": self.raw_payload,
        }


@dataclass
class DialogSlotHandler:
    id: str
    event_name: str  # 'input', 'nomatch', 'focus', 'filled', 'custom'
    condition: str | None = None
    responses: list[DialogResponse] = field(default_factory=list)
    jump: DialogJump | None = None
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_name": self.event_name,
            "condition": self.condition,
            "responses": [r.to_dict() for r in self.responses],
            "jump": self.jump.to_dict() if self.jump else None,
            "raw_json": self.raw_json,
        }


@dataclass
class DialogSlot:
    id: str
    variable_name: str
    condition: str | None = None
    enable_condition: str | None = None
    required: bool = False
    handlers: list[DialogSlotHandler] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "variable_name": self.variable_name,
            "condition": self.condition,
            "enable_condition": self.enable_condition,
            "required": self.required,
            "handlers": [h.to_dict() for h in self.handlers],
            "raw_json": self.raw_json,
        }


@dataclass
class DialogNode:
    id: str
    title: str | None = None
    node_type: str = "standard"  # 'standard', 'folder', 'frame', 'slot', 'event_handler', 'response_condition'
    condition: str | None = None
    parent_id: str | None = None
    previous_sibling_id: str | None = None
    sequence: int = 0
    context: dict[str, Any] = field(default_factory=dict)
    responses: list[DialogResponse] = field(default_factory=list)
    slots: list[DialogSlot] = field(default_factory=list)
    children: list[DialogNode] = field(default_factory=list)
    jump: DialogJump | None = None
    digress_in: str = "returns"       # 'returns', 'does_not_return', 'not_available'
    digress_out: str = "allow_all"    # 'allow_all', 'allow_returning', 'not_available'
    digress_out_slots: str = "allow_returning"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "node_type": self.node_type,
            "condition": self.condition,
            "parent_id": self.parent_id,
            "previous_sibling_id": self.previous_sibling_id,
            "sequence": self.sequence,
            "context": self.context,
            "responses": [r.to_dict() for r in self.responses],
            "slots": [s.to_dict() for s in self.slots],
            "children": [c.to_dict() for c in self.children],
            "jump": self.jump.to_dict() if self.jump else None,
            "digress_in": self.digress_in,
            "digress_out": self.digress_out,
            "digress_out_slots": self.digress_out_slots,
            "tags": self.tags,
            "metadata": self.metadata,
            "actions": self.actions,
            "raw_json": self.raw_json,
        }


@dataclass
class UniversalDialogDocument:
    name: str = "Dialog"
    description: str = ""
    language: str = "pt-br"
    format_detected: str = "unknown"  # 'watson_v1_flat', 'enterprise_nested', 'hybrid'
    intents: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    context_variables: dict[str, Any] = field(default_factory=dict)
    nodes: dict[str, DialogNode] = field(default_factory=dict)
    roots: list[DialogNode] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def get_node(self, node_id: str) -> DialogNode | None:
        return self.nodes.get(str(node_id))

    def iter_nodes(self) -> Iterator[DialogNode]:
        yield from self.nodes.values()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "language": self.language,
            "format_detected": self.format_detected,
            "intents_count": len(self.intents),
            "entities_count": len(self.entities),
            "total_nodes": len(self.nodes),
            "root_nodes": len(self.roots),
            "roots": [r.to_dict() for r in self.roots],
            "metadata": self.metadata,
            "tags": self.tags,
        }


# ==============================================================================
# Polymorphic Extractors and Format Normalizers
# ==============================================================================

def detect_dialog_format(raw_document: dict[str, Any]) -> str:
    """Detect whether the JSON document is Watson V1 flat, enterprise nested, or hybrid."""
    if not isinstance(raw_document, dict):
        return "invalid"
    if "dialog_nodes" in raw_document and isinstance(raw_document["dialog_nodes"], list):
        return "watson_v1_flat"
    if any(k in raw_document for k in ("nos", "arvoreDialogo", "dialog_tree", "nodes")):
        return "enterprise_nested"
    if any(k in raw_document for k in ("intents", "entities", "metadata", "workspace_id")):
        return "watson_v1_flat"
    return "hybrid"


def _extract_rich_responses_v1(output_dict: dict[str, Any]) -> list[DialogResponse]:
    """Extract responses from official Watson Assistant output.generic & integrations."""
    if not isinstance(output_dict, dict):
        return []
    responses: list[DialogResponse] = []
    generic_list = output_dict.get("generic") or []
    
    # 1. Process output.generic
    if isinstance(generic_list, list):
        for idx, item in enumerate(generic_list):
            if not isinstance(item, dict):
                continue
            resp_type = str(item.get("response_type") or "text")
            channel = "default"
            if isinstance(item.get("channel"), dict) and item["channel"].get("name"):
                channel = str(item["channel"]["name"])
            elif isinstance(item.get("channel"), str):
                channel = item["channel"]

            text_values = []
            if "values" in item and isinstance(item["values"], list):
                for val in item["values"]:
                    if isinstance(val, dict) and "text" in val:
                        text_values.append(str(val["text"]))
                    elif isinstance(val, str):
                        text_values.append(val)
            elif "text" in item and isinstance(item["text"], str):
                text_values.append(item["text"])

            media_urls = []
            if item.get("source"):
                media_urls.append(str(item["source"]))
            if item.get("media_url"):
                media_urls.append(str(item["media_url"]))

            options = []
            if "options" in item and isinstance(item["options"], list):
                for opt in item["options"]:
                    if isinstance(opt, dict):
                        options.append(opt)

            pause_ms = item.get("time") if resp_type == "pause" else None
            typing_indicator = bool(item.get("typing", False))

            responses.append(
                DialogResponse(
                    id=f"resp_{idx}",
                    response_type=resp_type,
                    channel=channel,
                    text_values=text_values,
                    media_urls=media_urls,
                    title=item.get("title"),
                    description=item.get("description"),
                    options=options,
                    pause_ms=pause_ms,
                    typing_indicator=typing_indicator,
                    raw_payload=item,
                )
            )

    # 2. Legacy text fallback
    if not responses and "text" in output_dict:
        text_val = output_dict["text"]
        vals = [text_val] if isinstance(text_val, str) else [str(v) for v in text_val if isinstance(v, (str, dict))]
        responses.append(DialogResponse(id="resp_0", response_type="text", channel="default", text_values=vals))

    # 3. Process output.integrations (channel specific overrides like WhatsApp, Slack)
    integrations = output_dict.get("integrations") or {}
    if isinstance(integrations, dict):
        for chan_name, chan_data in integrations.items():
            if isinstance(chan_data, dict):
                responses.append(
                    DialogResponse(
                        id=f"chan_{chan_name}",
                        response_type="channel_integration",
                        channel=chan_name,
                        raw_payload=chan_data,
                    )
                )

    return responses


def _extract_rich_responses_nested(respostas_list: list[dict[str, Any]]) -> list[DialogResponse]:
    """Extract rich multimodal responses from nested enterprise format."""
    if not isinstance(respostas_list, list):
        return []
    responses: list[DialogResponse] = []
    for idx, r in enumerate(respostas_list):
        if not isinstance(r, dict):
            continue
        resp_id = str(r.get("uuid") or f"resp_{idx}")
        text = str(r.get("textoResposta") or r.get("text") or "")
        component_type = str(r.get("idTipoComponente") or r.get("component_type") or r.get("response_type") or "text")
        channel = str(r.get("tipoRespostaNomeJSON") or r.get("channel") or r.get("canal") or "default")
        condition = r.get("condicao") or r.get("condition")

        media_urls = []
        for m_key in ("midias", "media", "attachments", "url"):
            if m_key in r:
                val = r[m_key]
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str): media_urls.append(item)
                        elif isinstance(item, dict) and "url" in item: media_urls.append(item["url"])
                elif isinstance(val, str):
                    media_urls.append(val)

        options = []
        for o_key in ("opcoes", "options", "botoes", "buttons"):
            if o_key in r and isinstance(r[o_key], list):
                for opt in r[o_key]:
                    if isinstance(opt, dict): options.append(opt)

        responses.append(
            DialogResponse(
                id=resp_id,
                response_type=component_type,
                channel=channel,
                condition=str(condition) if condition else None,
                text_values=[text] if text else [],
                media_urls=media_urls,
                options=options,
                raw_payload=r,
            )
        )
    return responses


def explore_document(raw_document: dict[str, Any]) -> UniversalDialogDocument:
    """Explore and parse any Watson dialog export into UniversalDialogDocument AST."""
    if not isinstance(raw_document, dict):
        raise ValueError("O documento de diálogo precisa ser um objeto JSON.")

    fmt = detect_dialog_format(raw_document)
    name = str(raw_document.get("name") or raw_document.get("nome") or "Dialog")
    desc = str(raw_document.get("description") or raw_document.get("descricao") or "")
    lang = str(raw_document.get("language") or raw_document.get("idioma") or "pt-br")

    intents = raw_document.get("intents") or raw_document.get("intencoes") or []
    entities = raw_document.get("entities") or raw_document.get("entidades") or []
    tags = raw_document.get("tags") or []
    metadata = raw_document.get("metadata") or raw_document.get("metadados") or {}

    doc = UniversalDialogDocument(
        name=name,
        description=desc,
        language=lang,
        format_detected=fmt,
        intents=intents if isinstance(intents, list) else [],
        entities=entities if isinstance(entities, list) else [],
        metadata=metadata if isinstance(metadata, dict) else {},
        tags=tags if isinstance(tags, list) else [],
    )

    if fmt == "watson_v1_flat":
        _parse_watson_v1_flat(raw_document, doc)
    else:
        _parse_enterprise_nested(raw_document, doc)

    return doc


def _parse_watson_v1_flat(raw_document: dict[str, Any], doc: UniversalDialogDocument) -> None:
    """Parse official flat Watson Assistant V1/V2 skill JSON."""
    raw_nodes = raw_document.get("dialog_nodes") or []
    if not isinstance(raw_nodes, list):
        return

    # 1. Index all raw nodes by ID
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw_nodes:
        if isinstance(item, dict) and item.get("dialog_node") is not None:
            by_id[str(item["dialog_node"])] = item

    # 2. Build parent -> children mappings
    children_map: dict[str | None, list[str]] = {}
    for node_id, item in by_id.items():
        parent = item.get("parent")
        parent_key = str(parent) if parent not in (None, "") else None
        children_map.setdefault(parent_key, []).append(node_id)

    # 3. Order siblings using previous_sibling pointers
    def order_siblings(parent_key: str | None) -> list[str]:
        ids = children_map.get(parent_key, [])
        by_prev = {str(by_id[nid].get("previous_sibling")): nid for nid in ids if by_id[nid].get("previous_sibling") not in (None, "")}
        first = [nid for nid in ids if by_id[nid].get("previous_sibling") in (None, "")]
        result: list[str] = []
        if len(first) == 1:
            curr = first[0]
            seen = set()
            while curr not in seen:
                result.append(curr)
                seen.add(curr)
                if curr not in by_prev:
                    break
                curr = by_prev[curr]
        return result if len(result) == len(ids) else sorted(ids)

    # 4. Recursively build AST nodes
    def build_node(node_id: str, seq: int) -> DialogNode:
        item = by_id[node_id]
        node_type = str(item.get("type") or "standard")
        title = item.get("title") or item.get("user_label")
        cond = item.get("conditions")
        context = item.get("context") if isinstance(item.get("context"), dict) else {}
        actions = item.get("actions") if isinstance(item.get("actions"), list) else []

        # Extract jumps from next_step
        jump = None
        next_step = item.get("next_step")
        if isinstance(next_step, dict):
            behavior = str(next_step.get("behavior") or "jump_to")
            target = next_step.get("dialog_node") or next_step.get("target")
            selector = str(next_step.get("selector") or "condition")
            if target:
                jump = DialogJump(target_id=str(target), selector=selector, behavior=behavior)

        responses = _extract_rich_responses_v1(item.get("output") or {})
        
        node = DialogNode(
            id=node_id,
            title=str(title) if title else None,
            node_type=node_type,
            condition=str(cond) if cond is not None else None,
            parent_id=str(item.get("parent")) if item.get("parent") not in (None, "") else None,
            previous_sibling_id=str(item.get("previous_sibling")) if item.get("previous_sibling") not in (None, "") else None,
            sequence=seq,
            context=context,
            responses=responses,
            jump=jump,
            digress_in=str(item.get("digress_in") or "returns"),
            digress_out=str(item.get("digress_out") or "allow_all"),
            digress_out_slots=str(item.get("digress_out_slots") or "allow_returning"),
            tags=item.get("tags") if isinstance(item.get("tags"), list) else [],
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            actions=actions,
            raw_json=item,
        )
        doc.nodes[node_id] = node

        # Process children
        for c_seq, c_id in enumerate(order_siblings(node_id)):
            child_item = by_id[c_id]
            child_type = str(child_item.get("type") or "standard")
            if child_type == "slot":
                # Embedded slot
                slot_handlers: list[DialogSlotHandler] = []
                for h_id in order_siblings(c_id):
                    h_item = by_id[h_id]
                    h_jump = None
                    h_next_step = h_item.get("next_step")
                    if isinstance(h_next_step, dict):
                        h_behavior = str(h_next_step.get("behavior") or "jump_to")
                        h_target = h_next_step.get("dialog_node") or h_next_step.get("target")
                        h_selector = str(h_next_step.get("selector") or "condition")
                        if h_target:
                            h_jump = DialogJump(target_id=str(h_target), selector=h_selector, behavior=h_behavior)
                    slot_handlers.append(
                        DialogSlotHandler(
                            id=h_id,
                            event_name=str(h_item.get("event_name") or "input"),
                            condition=str(h_item.get("conditions")) if h_item.get("conditions") else None,
                            responses=_extract_rich_responses_v1(h_item.get("output") or {}),
                            jump=h_jump,
                            raw_json=h_item,
                        )
                    )
                node.slots.append(
                    DialogSlot(
                        id=c_id,
                        variable_name=str(child_item.get("variable") or ""),
                        condition=str(child_item.get("conditions")) if child_item.get("conditions") else None,
                        required=bool(child_item.get("required", False)),
                        handlers=slot_handlers,
                        raw_json=child_item,
                    )
                )
            elif child_type == "response_condition":
                node.responses.append(
                    DialogResponse(
                        id=c_id,
                        response_type="response_condition",
                        condition=str(child_item.get("conditions") or "true"),
                        text_values=[],
                        raw_payload=child_item,
                    )
                )
            else:
                child_node = build_node(c_id, c_seq)
                node.children.append(child_node)

        return node

    for r_seq, root_id in enumerate(order_siblings(None)):
        doc.roots.append(build_node(root_id, r_seq))


def _parse_enterprise_nested(raw_document: dict[str, Any], doc: UniversalDialogDocument) -> None:
    """Parse hierarchical / nested enterprise dialog trees."""
    nodes_root = raw_document.get("nos") or raw_document.get("arvoreDialogo") or raw_document.get("nodes") or []
    if not isinstance(nodes_root, list):
        return

    # Extract context variable declarations
    var_list = raw_document.get("variaveisContexto") or raw_document.get("context_variables") or []
    if isinstance(var_list, list):
        for v in var_list:
            if isinstance(v, dict) and "uuid" in v:
                v_name = v.get("variavelContexto") or v.get("name")
                if v_name:
                    doc.context_variables[str(v["uuid"])] = str(v_name)

    def parse_node(item: dict[str, Any], parent_id: str | None, seq: int) -> DialogNode:
        node_id = str(item.get("uuid") or item.get("id") or f"node_{seq}")
        title = item.get("nome") or item.get("title") or item.get("name")
        cond = item.get("condicao") or item.get("conditions")
        folder = bool(item.get("folder", False))
        
        # Extract jump
        jump = None
        target = item.get("uuidEnviarPara") or item.get("jump_to") or item.get("target")
        if target:
            selector = str(item.get("jumpSelector") or "condition")
            jump = DialogJump(target_id=str(target), selector=selector, behavior="jump_to")

        responses = _extract_rich_responses_nested(item.get("respostas") or item.get("responses") or [])
        
        # Slots
        slots: list[DialogSlot] = []
        for s in item.get("slots") or []:
            if not isinstance(s, dict):
                continue
            s_id = str(s.get("uuid") or s.get("id") or "slot")
            var_uuid = str(s.get("uuidVariavelContexto") or "")
            var_name = doc.context_variables.get(var_uuid) or str(s.get("identificador") or s.get("name") or "")

            handlers: list[DialogSlotHandler] = []
            for h in s.get("filhos") or s.get("handlers") or []:
                if isinstance(h, dict):
                    h_id = str(h.get("uuid") or h.get("id") or "handler")
                    handlers.append(
                        DialogSlotHandler(
                            id=h_id,
                            event_name=str(h.get("event_name") or "input"),
                            condition=str(h.get("condicao") or h.get("conditions") or "true"),
                            raw_json=h,
                        )
                    )

            slots.append(
                DialogSlot(
                    id=s_id,
                    variable_name=var_name,
                    condition=s.get("condicao") or s.get("conditions"),
                    enable_condition=s.get("condicaoSlots") or s.get("enable_condition"),
                    required=bool(s.get("indicadorObrigatorio", False)),
                    handlers=handlers,
                    raw_json=s,
                )
            )

        node = DialogNode(
            id=node_id,
            title=str(title) if title else None,
            node_type="folder" if folder else "standard",
            condition=str(cond) if cond is not None else None,
            parent_id=parent_id,
            sequence=seq,
            responses=responses,
            slots=slots,
            jump=jump,
            tags=item.get("tags") if isinstance(item.get("tags"), list) else [],
            metadata=item.get("metadados") or item.get("metadata") or {},
            actions=item.get("actions") or [],
            raw_json=item,
        )
        doc.nodes[node_id] = node

        # Process nested children
        for c_seq, child_dict in enumerate(item.get("filhos") or item.get("children") or []):
            if isinstance(child_dict, dict):
                child_node = parse_node(child_dict, node_id, c_seq)
                node.children.append(child_node)

        return node

    for r_seq, root_dict in enumerate(nodes_root):
        if isinstance(root_dict, dict):
            doc.roots.append(parse_node(root_dict, None, r_seq))


def introspect_primitives(raw_document: dict[str, Any]) -> dict[str, Any]:
    """Deeply inspect and discover all Watson primitives and features inside a JSON."""
    doc = explore_document(raw_document)
    
    channels = set()
    response_types = set()
    has_media = False
    has_slots = False
    has_jumps = False
    has_digressions = False
    tags_found = set(doc.tags)
    spel_conditions = []

    for node in doc.iter_nodes():
        if node.condition:
            spel_conditions.append(node.condition)
        if node.jump:
            has_jumps = True
        if node.slots:
            has_slots = True
            for s in node.slots:
                for h in s.handlers:
                    if h.jump:
                        has_jumps = True
                    for h_resp in h.responses:
                        channels.add(h_resp.channel)
                        response_types.add(h_resp.response_type)
                        if h_resp.media_urls:
                            has_media = True
                        if h_resp.condition:
                            spel_conditions.append(h_resp.condition)
        for tag in node.tags:
            tags_found.add(str(tag))
        for resp in node.responses:
            channels.add(resp.channel)
            response_types.add(resp.response_type)
            if resp.media_urls:
                has_media = True
            if resp.condition:
                spel_conditions.append(resp.condition)

    return {
        "format_detected": doc.format_detected,
        "total_nodes": len(doc.nodes),
        "root_nodes": len(doc.roots),
        "intents_count": len(doc.intents),
        "entities_count": len(doc.entities),
        "discovered_channels": sorted(channels),
        "discovered_response_types": sorted(response_types),
        "has_multimedia": has_media,
        "has_slots": has_slots,
        "has_jumps": has_jumps,
        "tags_count": len(tags_found),
        "tags": sorted(tags_found),
        "conditions_count": len(spel_conditions),
    }


def to_v1_format(doc: UniversalDialogDocument) -> dict[str, Any]:
    """Convert UniversalDialogDocument AST into standard IBM Watson Assistant V1 Skill JSON."""
    dialog_nodes: list[dict[str, Any]] = []

    def serialize_node(node: DialogNode, parent_id: str | None, prev_id: str | None) -> str:
        output_generic: list[dict[str, Any]] = []
        for r in node.responses:
            if r.response_type == "response_condition":
                continue
            item: dict[str, Any] = {"response_type": r.response_type}
            if r.text_values:
                item["values"] = [{"text": t} for t in r.text_values]
            if r.media_urls:
                item["source"] = r.media_urls[0]
            if r.title:
                item["title"] = r.title
            if r.description:
                item["description"] = r.description
            if r.options:
                item["options"] = r.options
            if r.pause_ms is not None:
                item["time"] = r.pause_ms
            if r.typing_indicator:
                item["typing"] = True
            if r.channel != "default":
                item["channel"] = {"name": r.channel}
            output_generic.append(item)

        node_dict: dict[str, Any] = {
            "dialog_node": node.id,
            "type": node.node_type,
            "conditions": node.condition or "true",
        }
        if node.title:
            node_dict["title"] = node.title
        if parent_id:
            node_dict["parent"] = parent_id
        if prev_id:
            node_dict["previous_sibling"] = prev_id
        if node.context:
            node_dict["context"] = node.context
        if output_generic:
            node_dict["output"] = {"generic": output_generic}
        if node.jump:
            node_dict["next_step"] = {
                "behavior": node.jump.behavior,
                "selector": node.jump.selector,
                "dialog_node": node.jump.target_id,
            }
        if node.tags:
            node_dict["tags"] = node.tags
        if node.metadata:
            node_dict["metadata"] = node.metadata
        if node.actions:
            node_dict["actions"] = node.actions

        dialog_nodes.append(node_dict)

        # 1. Serialize Slots as child nodes of type 'slot'
        last_slot_id: str | None = None
        for s in node.slots:
            slot_dict: dict[str, Any] = {
                "dialog_node": s.id,
                "type": "slot",
                "parent": node.id,
                "variable": s.variable_name,
                "required": s.required,
            }
            if s.condition:
                slot_dict["conditions"] = s.condition
            if last_slot_id:
                slot_dict["previous_sibling"] = last_slot_id
            dialog_nodes.append(slot_dict)
            last_slot_id = s.id

            # Slot Handlers as children of slot node
            last_handler_id: str | None = None
            for h in s.handlers:
                h_dict: dict[str, Any] = {
                    "dialog_node": h.id,
                    "type": "event_handler",
                    "parent": s.id,
                    "event_name": h.event_name,
                    "conditions": h.condition or "true",
                }
                if last_handler_id:
                    h_dict["previous_sibling"] = last_handler_id
                if h.jump:
                    h_dict["next_step"] = {
                        "behavior": h.jump.behavior,
                        "selector": h.jump.selector,
                        "dialog_node": h.jump.target_id,
                    }
                dialog_nodes.append(h_dict)
                last_handler_id = h.id

        # 2. Serialize standard children
        last_child_id = last_slot_id
        for child in node.children:
            last_child_id = serialize_node(child, node.id, last_child_id)

        return node.id

    last_root_id: str | None = None
    for r in doc.roots:
        last_root_id = serialize_node(r, None, last_root_id)

    return {
        "name": doc.name,
        "description": doc.description,
        "language": doc.language,
        "intents": doc.intents,
        "entities": doc.entities,
        "dialog_nodes": dialog_nodes,
        "metadata": doc.metadata,
        "tags": doc.tags,
    }


def to_nested_format(doc: UniversalDialogDocument) -> dict[str, Any]:
    """Convert UniversalDialogDocument AST into hierarchical / nested enterprise dialog JSON."""
    def serialize_nested_node(node: DialogNode) -> dict[str, Any]:
        respostas: list[dict[str, Any]] = []
        for r in node.responses:
            respostas.append({
                "uuid": r.id,
                "textoResposta": r.text_values[0] if r.text_values else "",
                "idTipoComponente": r.response_type,
                "tipoRespostaNomeJSON": r.channel,
                "condicao": r.condition,
                "midias": r.media_urls,
                "opcoes": r.options,
            })

        slots: list[dict[str, Any]] = []
        for s in node.slots:
            handlers: list[dict[str, Any]] = []
            for h in s.handlers:
                handlers.append({
                    "uuid": h.id,
                    "event_name": h.event_name,
                    "condicao": h.condition,
                })
            slots.append({
                "uuid": s.id,
                "identificador": s.variable_name,
                "indicadorObrigatorio": s.required,
                "condicao": s.condition,
                "condicaoSlots": s.enable_condition,
                "filhos": handlers,
            })

        node_dict: dict[str, Any] = {
            "uuid": node.id,
            "nome": node.title,
            "condicao": node.condition or "true",
            "sequencia": node.sequence,
            "folder": node.node_type == "folder",
            "respostas": respostas,
            "slots": slots,
            "filhos": [serialize_nested_node(c) for c in node.children],
            "tags": node.tags,
            "metadados": node.metadata,
            "actions": node.actions,
        }
        if node.jump:
            node_dict["uuidEnviarPara"] = node.jump.target_id
            node_dict["jumpSelector"] = node.jump.selector
        return node_dict

    return {
        "nome": doc.name,
        "descricao": doc.description,
        "idioma": doc.language,
        "intencoes": doc.intents,
        "entidades": doc.entities,
        "nos": [serialize_nested_node(r) for r in doc.roots],
        "tags": doc.tags,
        "metadados": doc.metadata,
    }


def main() -> None:
    import argparse
    import sys
    from watson_dialog_diff import configure_utf8_output, load_json

    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Universal Dialog AST Explorer for Watson Assistant and Enterprise Dialogs.")
    parser.add_argument("input", type=Path, help="Path to Watson Assistant JSON export.")
    parser.add_argument("--introspect", action="store_true", help="Print summary of discovered primitives, channels, media, and topology.")
    parser.add_argument("--channels", action="store_true", help="List all discovered communication channels.")
    parser.add_argument("--multimedia", action="store_true", help="List all rich media components (images, options, pauses, etc.).")
    parser.add_argument("--ast", action="store_true", help="Output normalized Universal Dialog AST as JSON.")
    parser.add_argument("--convert-to", choices=["v1", "nested"], help="Convert the export into official Watson V1 or nested enterprise format.")
    parser.add_argument("--output", "-o", type=Path, help="Target output file.")

    args = parser.parse_args()
    try:
        raw_doc = load_json(args.input)
    except Exception as e:
        sys.stderr.write(f"Error reading {args.input}: {e}\n")
        sys.exit(1)

    if args.convert_to:
        doc = explore_document(raw_doc)
        converted = to_v1_format(doc) if args.convert_to == "v1" else to_nested_format(doc)
        rendered = json.dumps(converted, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Successfully converted to {args.convert_to} format: {args.output}")
        else:
            print(rendered)
        return

    if args.channels:
        intro = introspect_primitives(raw_doc)
        print(f"=== Discovered Channels ({len(intro['discovered_channels'])}) ===")
        for ch in intro["discovered_channels"]:
            print(f" - {ch}")
        return

    if args.multimedia:
        doc = explore_document(raw_doc)
        print("=== Discovered Multimedia & Rich Responses ===")
        for node in doc.iter_nodes():
            for resp in node.responses:
                if resp.response_type != "text" or resp.media_urls or resp.options:
                    print(f"[{node.id}] ({resp.channel}) {resp.response_type.upper()}: title='{resp.title}' media={resp.media_urls} options={len(resp.options)}")
        return

    if args.ast:
        doc = explore_document(raw_doc)
        rendered = json.dumps(doc.to_dict(), indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print(f"AST written to {args.output}")
        else:
            print(rendered)
        return

    # Default / --introspect
    intro = introspect_primitives(raw_doc)
    print("=================================================================")
    print(f"  tare.tools — Dialog AST Explorer & Schema Discovery")
    print("=================================================================")
    print(f"  Format Detected:      {intro['format_detected']}")
    print(f"  Total Dialog Nodes:   {intro['total_nodes']} (Root: {intro['root_nodes']})")
    print(f"  Intents Catalog:      {intro['intents_count']}")
    print(f"  Entities Catalog:     {intro['entities_count']}")
    print(f"  SpEL Conditions:      {intro['conditions_count']}")
    print(f"  Slots Configured:     {intro['has_slots']}")
    print(f"  Jumps Configured:     {intro['has_jumps']}")
    print(f"  Multimedia Assets:    {intro['has_multimedia']}")
    print(f"  Discovered Channels:  {', '.join(intro['discovered_channels'])}")
    print(f"  Response Components:  {', '.join(intro['discovered_response_types'])}")
    print(f"  Custom Tags Found:    {intro['tags_count']} {intro['tags']}")
    print("=================================================================")


if __name__ == "__main__":
    main()
