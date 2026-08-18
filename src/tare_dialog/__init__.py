"""tare.tools — Dialog Engine.

Deterministic Conversational AST, Semantic Diff Engine, SpEL Expression Evaluator,
Scenario Generator, and Mission Control Triage Console for Enterprise Dialog Systems.
"""

from __future__ import annotations

from tare_dialog.diff_engine import (
    DEFAULT_IGNORED_FIELDS,
    DEFAULT_MAX_INPUT_BYTES,
    configure_utf8_output,
    diff_dialogs,
    load_json,
    markdown,
    summarize,
    summarize_external_paths,
)
from tare_dialog.document import DialogIndex, PreflightMetadata, preflight_check
from tare_dialog.explorer import (
    DialogJump,
    DialogNode,
    DialogResponse,
    DialogSlot,
    DialogSlotHandler,
    UniversalDialogDocument,
    detect_dialog_format,
    explore_document,
    introspect_primitives,
    to_nested_format,
    to_v1_format,
)
from tare_dialog.graph import build_graph, dot, render_dot
from tare_dialog.spel import UNKNOWN, SpelError, evaluate_condition, syntax_diagnostics
from tare_dialog.test_runner import normalize_document, run_scenario
from tare_dialog.validator import validate

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_IGNORED_FIELDS",
    "DEFAULT_MAX_INPUT_BYTES",
    "UNKNOWN",
    "DialogIndex",
    "DialogJump",
    "DialogNode",
    "DialogResponse",
    "DialogSlot",
    "DialogSlotHandler",
    "PreflightMetadata",
    "SpelError",
    "UniversalDialogDocument",
    "build_graph",
    "configure_utf8_output",
    "detect_dialog_format",
    "diff_dialogs",
    "dot",
    "evaluate_condition",
    "explore_document",
    "introspect_primitives",
    "load_json",
    "markdown",
    "normalize_document",
    "preflight_check",
    "render_dot",
    "run_scenario",
    "summarize",
    "summarize_external_paths",
    "syntax_diagnostics",
    "to_nested_format",
    "to_v1_format",
    "validate",
]
