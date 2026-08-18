#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tare.tools — Dialog Engine (Ephemeral Standalone Distribution)

A single-file, zero-dependency, pure Python stdlib bundle engineered for:
- ChatGPT Code Interpreter / Advanced Data Analysis (ADA) sandboxes
- Microsoft 365 Copilot Studio & Agent Sandboxes
- Serverless ephemeral runtimes and offline analysis

Capabilities:
- AST Semantic Diff Engine & Provenance Analysis
- Spring Expression Language (SpEL) AST Lexer & Safe Evaluator
- Static Validation & 12-Phase Quality Gates
- Topological Flow Graph & Reachability Analyzer
- Deterministic Scenario Runner & Regression Tracing
- Universal Dialog AST Explorer (Official Watson V1 & Enterprise Nested)

License: Apache-2.0
Copyright (c) 2026 Augusto Carvalho and tare.tools contributors.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterator, NamedTuple



# ------------------------------------------------------------------------------
# Module: resources.py
# ------------------------------------------------------------------------------

"""Portable resource discovery and conservative auto-sizing for Watson Dialog tools.

The helpers in this module never grant authority and do not change semantics.
They only choose bounded execution widths from resources visible to the current
process.  Optional psutil support improves telemetry but is not required.
"""


import sys
from pathlib import Path



import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MIB = 1024 * 1024
DEFAULT_MAX_INPUT_BYTES = 50 * _MIB


def resolve_max_input_bytes(value: int | None) -> int:
    if value is not None:
        if value < 0:
            raise ValueError("max_input_bytes não pode ser negativo")
        return value
    env_max = os.environ.get("WATSON_DIALOG_MAX_BYTES", "")
    if env_max.isdigit():
        return int(env_max)
    return DEFAULT_MAX_INPUT_BYTES



def _usable_cpu_count() -> int:
    process_count = getattr(os, "process_cpu_count", None)
    if callable(process_count):
        value = process_count()
        if value:
            return max(1, int(value))
    try:
        affinity = os.sched_getaffinity(0)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        affinity = None
    if affinity:
        return max(1, len(affinity))
    return max(1, int(os.cpu_count() or 1))


def _available_memory_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.virtual_memory().available)
    except Exception:
        pass

    if os.name == "posix":
        try:
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return pages * page_size
        except (AttributeError, OSError, ValueError):
            return None
    return None


def _temp_free_bytes(path: Path | None = None) -> int | None:
    target = path or Path(tempfile.gettempdir())
    try:
        return int(shutil.disk_usage(target).free)
    except OSError:
        return None


@dataclass(frozen=True)
class ResourceBudget:
    usable_cpus: int
    available_memory_bytes: int | None
    temp_free_bytes: int | None
    max_jobs_cap: int

    @classmethod
    def detect(cls, temp_dir: Path | None = None) -> ResourceBudget:
        usable_cpus = _usable_cpu_count()
        env_cap = os.environ.get("WATSON_DIALOG_MAX_JOBS", "")
        # Keep a conservative default ceiling for subprocess-heavy work, but
        # scale it with larger machines instead of pinning every host to 8.
        default_cap = max(1, min(16, usable_cpus))
        max_jobs_cap = int(env_cap) if env_cap.isdigit() and int(env_cap) > 0 else default_cap
        return cls(
            usable_cpus=usable_cpus,
            available_memory_bytes=_available_memory_bytes(),
            temp_free_bytes=_temp_free_bytes(temp_dir),
            max_jobs_cap=max_jobs_cap,
        )

    def auto_jobs(
        self,
        task_count: int,
        *,
        estimated_worker_memory_bytes: int = 512 * _MIB,
        cpu_fraction: float = 0.5,
    ) -> int:
        """Return a conservative worker count for independent subprocess work.

        The CPU rule intentionally keeps headroom because mutation/unit-test
        subprocesses are CPU-heavy and concurrent Python runtimes amplify RSS.
        Users can override the result explicitly with ``--jobs N``.
        """
        if task_count <= 0:
            return 1
        cpu_jobs = max(1, int(self.usable_cpus * cpu_fraction))
        if self.usable_cpus >= 2:
            cpu_jobs = max(1, cpu_jobs)
        memory_jobs = task_count
        if self.available_memory_bytes and estimated_worker_memory_bytes > 0:
            # Keep 25% of currently available memory uncommitted.
            usable_memory = int(self.available_memory_bytes * 0.75)
            memory_jobs = max(1, usable_memory // estimated_worker_memory_bytes)
        return max(1, min(task_count, cpu_jobs, memory_jobs, self.max_jobs_cap))

    def logical_shards(
        self,
        worker_count: int,
        task_count: int,
        oversubscription: int = 4,
        min_tasks_per_shard: int = 8,
    ) -> int:
        if task_count <= 0:
            return 1
        workers = max(1, min(worker_count, task_count))
        desired = workers * max(1, oversubscription)
        useful_cap = max(workers, (task_count + max(1, min_tasks_per_shard) - 1) // max(1, min_tasks_per_shard))
        return max(1, min(task_count, desired, useful_cap))

    def to_dict(self) -> dict[str, int | None]:
        return {
            "usable_cpus": self.usable_cpus,
            "available_memory_bytes": self.available_memory_bytes,
            "temp_free_bytes": self.temp_free_bytes,
            "max_jobs_cap": self.max_jobs_cap,
        }


def resolve_jobs(value: str | int, task_count: int, budget: ResourceBudget | None = None) -> int:
    if isinstance(value, int):
        if value < 1:
            raise ValueError("jobs deve ser pelo menos 1")
        return min(value, max(1, task_count))
    rendered = str(value).strip().lower()
    if rendered == "auto":
        return (budget or ResourceBudget.detect()).auto_jobs(task_count)
    if rendered.isdigit() and int(rendered) > 0:
        return min(int(rendered), max(1, task_count))
    raise ValueError("jobs deve ser 'auto' ou um inteiro positivo")

# ------------------------------------------------------------------------------
# Module: spel.py
# ------------------------------------------------------------------------------

"""Safe evaluator for the SpEL subset used by Watson Assistant Dialog conditions.

It intentionally supports expressions only: no assignments, type construction,
reflection, or arbitrary Python/Java method execution is permitted.
"""


import sys
from pathlib import Path



import functools
import re
from dataclasses import dataclass
from typing import Any


class SpelError(ValueError):
    pass


class _Unknown:
    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    value: str


TOKEN_RE = re.compile(
    r"\s*(?:(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")|(?P<number>\d+(?:\.\d+)?L?)|(?P<op>\?\.|&&|\|\||==|!=|>=|<=|[+*/<>!?:().,\[\]-])|(?P<name>[$@#]?(?:[A-Za-z_][\w-]*|\d[\w-]*)))"
)


@functools.lru_cache(maxsize=32768)
def _syntax_diagnostics_cached(expression: str) -> tuple[tuple[str, str, str], ...]:
    diagnostics = _syntax_diagnostics_impl(expression)
    return tuple((d["category"], d["code"], d["message"]) for d in diagnostics)


def syntax_diagnostics(expression: str) -> list[dict[str, str]]:
    cached = _syntax_diagnostics_cached(expression)
    return [{"category": c, "code": k, "message": m} for c, k, m in cached]


def _syntax_diagnostics_impl(expression: str) -> list[dict[str, str]]:
    """Return only SpEL errors that are unambiguous without full evaluation.

    The Dialog export can use valid SpEL features outside this project's parser
    subset.  These checks deliberately cover only universally invalid forms:
    unterminated quoted strings, unbalanced parentheses, and boolean operators
    missing one of their operands.
    """
    diagnostics: list[dict[str, str]] = []
    masked: list[str] = []
    quote: str | None = None
    depth = 0
    index = 0
    while index < len(expression):
        character = expression[index]
        if quote:
            masked.append(" ")
            if character == quote:
                # SpEL escapes a quote inside a same-quoted string by doubling
                # the quote character. Backslash is ordinary string content.
                if index + 1 < len(expression) and expression[index + 1] == quote:
                    masked.append(" ")
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            masked.append(" ")
        elif character == "(":
            depth += 1
            masked.append(character)
        elif character == ")":
            if depth == 0:
                diagnostics.append({"category": "syntactic", "code": "unmatched_closing_parenthesis", "message": "Há um parêntese de fechamento sem abertura correspondente."})
            else:
                depth -= 1
            masked.append(character)
        else:
            masked.append(character)
        index += 1
    if quote:
        diagnostics.append({"category": "lexical", "code": "unterminated_string", "message": "Há uma string com aspas não fechadas."})
    if depth:
        diagnostics.append({"category": "syntactic", "code": "unclosed_parenthesis", "message": "Há um parêntese aberto sem fechamento correspondente."})
    if diagnostics:
        return diagnostics

    code = "".join(masked)
    operator = r"(?:&&|\|\||\bAND\b|\bOR\b)"
    if re.search(rf"^\s*{operator}", code, flags=re.IGNORECASE):
        diagnostics.append({"category": "syntactic", "code": "missing_left_operand", "message": "O operador booleano não possui operando à esquerda."})
    if re.search(rf"{operator}\s*$", code, flags=re.IGNORECASE):
        diagnostics.append({"category": "syntactic", "code": "missing_right_operand", "message": "O operador booleano não possui operando à direita."})
    if re.search(rf"{operator}\s*{operator}", code, flags=re.IGNORECASE):
        diagnostics.append({"category": "syntactic", "code": "missing_boolean_operand", "message": "Há operadores booleanos consecutivos sem operando entre eles."})
    return diagnostics


def _template_close(text: str, start: int) -> int | None:
    """Find the next ``?>`` delimiter outside quoted SpEL string literals."""
    quote: str | None = None
    index = start
    while index + 1 < len(text):
        character = text[index]
        if quote:
            if character == quote:
                # SpEL string literals escape their delimiter by doubling it
                # ('' or ""). A backslash does not escape the following quote.
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            index += 1
            continue
        if text.startswith("?>", index):
            return index
        index += 1
    return None


def template_syntax_diagnostics(text: str) -> list[dict[str, Any]]:
    """Validate embedded ``<? expression ?>`` SpEL templates conservatively.

    Watson context values and response text may contain literal text around one
    or more expression templates.  The project's full SpEL evaluator is
    intentionally partial, so this function reports only malformed template
    boundaries and the same syntax errors that :func:`syntax_diagnostics` can
    establish without depending on unsupported SpEL features.

    Each diagnostic carries the extracted expression and character span so a
    caller can locate the exact failing template without executing it.
    """
    diagnostics: list[dict[str, Any]] = []
    cursor = 0
    ordinal = 0
    while True:
        opening = text.find("<?", cursor)
        if opening < 0:
            break
        ordinal += 1
        closing = _template_close(text, opening + 2)
        if closing is None:
            expression = text[opening + 2 :].strip()
            diagnostics.append({
                "category": "syntactic",
                "code": "unclosed_template",
                "message": "A expressão SpEL iniciada por <? não possui o delimitador de fechamento ?>.",
                "expression": expression,
                "start": opening,
                "end": len(text),
                "ordinal": ordinal,
            })
            break

        expression = text[opening + 2 : closing].strip()
        if not expression:
            diagnostics.append({
                "category": "syntactic",
                "code": "empty_expression",
                "message": "O template <? ?> não contém uma expressão SpEL.",
                "expression": expression,
                "start": opening,
                "end": closing + 2,
                "ordinal": ordinal,
            })
        else:
            for diagnostic in syntax_diagnostics(expression):
                diagnostics.append({
                    **diagnostic,
                    "expression": expression,
                    "start": opening,
                    "end": closing + 2,
                    "ordinal": ordinal,
                })
        cursor = closing + 2
    return diagnostics


@functools.lru_cache(maxsize=32768)
def tokenize(expression: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    index = 0
    while index < len(expression):
        match = TOKEN_RE.match(expression, index)
        if not match:
            raise SpelError(f"Token inválido próximo de: {expression[index:index + 20]!r}")
        index = match.end()
        kind = next(name for name, value in match.groupdict().items() if value is not None)
        value = match.group(kind)
        tokens.append(Token(kind, value))
    tokens.append(Token("eof", ""))
    return tuple(tokens)


MAX_EXPRESSION_DEPTH = 128


class Parser:
    PRECEDENCE = {"||": 1, "&&": 2, "==": 3, "!=": 3, "matches": 3, ">": 4, ">=": 4, "<": 4, "<=": 4, "+": 5, "-": 5, "*": 6, "/": 6}

    def __init__(self, expression: str):
        self.tokens = tokenize(expression)
        self.position = 0
        self.in_ternary_value = False
        self.depth = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.position]

    def take(self, value: str | None = None) -> Token:
        token = self.current
        if value is not None and token.value != value:
            raise SpelError(f"Esperado {value!r}; encontrado {token.value!r}")
        self.position += 1
        return token

    def parse(self) -> Any:
        result = self.expression()
        if self.current.kind != "eof":
            raise SpelError(f"Token inesperado: {self.current.value!r}")
        return result

    def expression(self, minimum: int = 0) -> Any:
        self.depth += 1
        if self.depth > MAX_EXPRESSION_DEPTH:
            raise SpelError("Profundidade máxima de expressão SpEL excedida")
        try:
            left = self.prefix()
            while (self.current.value == ":" and not self.in_ternary_value) or ((self.current.value in self.PRECEDENCE or self.current.value.lower() in {"and", "or", "matches"}) and self._precedence() >= minimum):
                if self.current.value == ":":
                    self.take(":")
                    left = ("shorthand", left, self.shorthand_value())
                    continue
                operator = self.take().value
                operator = {"and": "&&", "or": "||"}.get(operator.lower(), operator)
                precedence = self.PRECEDENCE[operator]
                right = self.expression(precedence + 1)
                left = ("binary", operator, left, right)
            if minimum == 0 and self.current.value == "?":
                self.take("?")
                self.in_ternary_value = True
                if_true = self.expression(1)
                self.in_ternary_value = False
                self.take(":")
                left = ("ternary", left, if_true, self.expression())
            return left
        finally:
            self.depth -= 1

    def _precedence(self) -> int:
        value = self.current.value.lower()
        return self.PRECEDENCE[{"and": "&&", "or": "||"}.get(value, value)]

    def shorthand_value(self) -> str:
        if self.current.value == "(":
            self.take("(")
            depth, values = 1, []
            while depth:
                token = self.take()
                if token.kind == "eof":
                    raise SpelError("Valor abreviado sem fechamento")
                if token.value == "(": depth += 1
                elif token.value == ")": depth -= 1
                if depth: values.append(token.value)
            return "".join(values)
        sign = self.take("-").value if self.current.value == "-" else ""
        token = self.take()
        return sign + (token.value[1:-1] if token.kind == "string" else token.value)

    def prefix(self) -> Any:
        if self.current.value in {"!", "-"}:
            return ("unary", self.take().value, self.prefix())
        if self.current.kind == "name" and self.current.value.lower() == "not":
            self.take()
            return ("unary", "!", self.prefix())
        if self.current.value == "(":
            self.take("(")
            result = self.expression()
            self.take(")")
        elif self.current.kind == "string":
            raw = self.take().value
            quote, content = raw[0], raw[1:-1]
            result = ("literal", content.replace("\\\\", "\\").replace("\\" + quote, quote))
        elif self.current.kind == "number":
            raw = self.take().value.rstrip("L")
            result = ("literal", float(raw) if "." in raw else int(raw))
        elif self.current.kind == "name" and self.current.value == "new":
            self.take()
            class_name = self.take().value
            result = ("construct", class_name, self.arguments())
        elif self.current.kind == "name":
            name = self.take().value
            lowered = name.lower()
            result = ("literal", {"true": True, "false": False, "null": None}[lowered]) if lowered in {"true", "false", "null"} else ("name", name)
        else:
            raise SpelError(f"Expressão esperada; encontrado {self.current.value!r}")
        if self.current.value == "(" and result[0] == "name":
            result = ("global_call", result[1], self.arguments())
        while True:
            safe = self.current.value == "?."
            if self.current.value in {".", "?."}:
                self.take()
                method = self.take().value
                if self.current.value == "(":
                    arguments = self.arguments()
                    result = ("call", result, method, arguments, safe)
                else:
                    result = ("property", result, method, safe)
            elif self.current.value == "[":
                self.take("[")
                key = self.expression()
                self.take("]")
                result = ("index", result, key, safe)
            else:
                break
        return result

    def arguments(self) -> list[Any]:
        self.take("(")
        arguments: list[Any] = []
        if self.current.value != ")":
            while True:
                arguments.append(self.expression())
                if self.current.value != ",":
                    break
                self.take(",")
        self.take(")")
        return arguments


def parse(expression: str) -> Any:
    return Parser(expression).parse()


def _truth(value: Any) -> Any:
    if value is UNKNOWN:
        return UNKNOWN
    return bool(value)


def _entity_value(name: str, environment: dict[str, Any]) -> Any:
    entities = environment.get("entities", {})
    if isinstance(entities, dict):
        return entities.get(name, UNKNOWN)
    values = [item.get("value") for item in entities if item.get("entity") == name]
    return values if values else UNKNOWN


def _name(name: str, environment: dict[str, Any]) -> Any:
    if name.startswith("_"):
        return UNKNOWN
    if name.startswith("$"):
        return environment.get("context", {}).get(name[1:], UNKNOWN)
    if name.startswith("@"):
        return _entity_value(name[1:], environment)
    if name.startswith("#"):
        intents = environment.get("intents", [])
        return any(item.get("intent", item.get("name")) == name[1:] for item in intents)
    if name in environment.get("locals", {}):
        return environment["locals"][name]
    return environment.get(name, UNKNOWN)


def _property(value: Any, key: str) -> Any:
    if value is UNKNOWN or value is None or key.startswith("_"):
        return UNKNOWN
    if isinstance(value, dict):
        return value.get(key, UNKNOWN)
    if isinstance(value, list) and key == "size":
        return len(value)
    return getattr(value, key, UNKNOWN)


def _call(value: Any, method: str, arguments: list[Any], environment: dict[str, Any]) -> Any:
    if value is UNKNOWN or value is None or method.startswith("_") or any(argument is UNKNOWN for argument in arguments):
        return UNKNOWN
    try:
        if method == "toLowerCase": return str(value).lower()
        if method == "toUpperCase": return str(value).upper()
        if method == "toString": return str(value)
        if method == "trim": return str(value).strip()
        if method == "size": return len(value)
        if method == "length": return len(value)
        if method == "contains": return arguments[0] in value
        if method == "startsWith": return str(value).startswith(str(arguments[0]))
        if method == "endsWith": return str(value).endswith(str(arguments[0]))
        if method == "equals": return value == arguments[0]
        if method == "equalsIgnoreCase": return str(value).lower() == str(arguments[0]).lower()
        if method == "isEmpty": return not value
        if method == "get": return value[int(arguments[0])]
        if method == "indexOf": return str(value).find(str(arguments[0]))
        if method == "substring": return str(value)[int(arguments[0]):] if len(arguments) == 1 else str(value)[int(arguments[0]):int(arguments[1])]
        if method == "replace": return str(value).replace(str(arguments[0]), str(arguments[1]))
        if method == "matches": return bool(re.fullmatch(str(arguments[0]), str(value)))
        if method == "find": return bool(re.search(str(arguments[0]), str(value)))
        if method == "join": return str(arguments[0]).join(map(str, value))
        if method == "filter":
            variable, expression = arguments
            if not isinstance(variable, str) or not isinstance(expression, str):
                return UNKNOWN
            tree = parse(expression)
            return [item for item in value if _truth(evaluate(tree, {**environment, "locals": {**environment.get("locals", {}), variable: item}})) is True]
    except (IndexError, KeyError, TypeError, ValueError, re.error):
        return UNKNOWN
    return UNKNOWN


def _global_call(name: str, arguments: list[Any], environment: dict[str, Any]) -> Any:
    if name.startswith("_"):
        return UNKNOWN
    functions = environment.get("functions", {})
    function = functions.get(name)
    if callable(function):
        try:
            return function(*arguments)
        except Exception:
            return UNKNOWN
    return UNKNOWN


def evaluate(tree: Any, environment: dict[str, Any]) -> Any:
    kind = tree[0]
    if kind == "literal": return tree[1]
    if kind == "name": return _name(tree[1], environment)
    if kind == "property": return _property(evaluate(tree[1], environment), tree[2])
    if kind == "index":
        value, key = evaluate(tree[1], environment), evaluate(tree[2], environment)
        try: return value[key] if value is not UNKNOWN and key is not UNKNOWN else UNKNOWN
        except (KeyError, IndexError, TypeError): return UNKNOWN
    if kind == "call": return _call(evaluate(tree[1], environment), tree[2], [evaluate(argument, environment) for argument in tree[3]], environment)
    if kind == "global_call": return _global_call(tree[1], [evaluate(argument, environment) for argument in tree[2]], environment)
    if kind == "shorthand":
        source = tree[1]
        if source[0] != "name": return UNKNOWN
        value = evaluate(source, environment)
        if value is UNKNOWN: return UNKNOWN
        return any(str(item) == tree[2] for item in value) if source[1].startswith("@") and isinstance(value, list) else str(value) == tree[2]
    if kind == "construct":
        return {"__spel_type__": tree[1]} if tree[1] == "Random" else UNKNOWN
    if kind == "ternary":
        condition = _truth(evaluate(tree[1], environment))
        return evaluate(tree[2] if condition is True else tree[3], environment) if condition is not UNKNOWN else UNKNOWN
    if kind == "unary":
        value = evaluate(tree[2], environment)
        if value is UNKNOWN:
            return UNKNOWN
        try:
            return not _truth(value) if tree[1] == "!" else -value
        except (TypeError, ValueError, OverflowError):
            return UNKNOWN
    if kind == "binary":
        operator, left_tree, right_tree = tree[1:]
        left = evaluate(left_tree, environment)
        if operator == "&&" and left is not UNKNOWN and not _truth(left): return False
        if operator == "||" and left is not UNKNOWN and _truth(left): return True
        right = evaluate(right_tree, environment)
        if left is UNKNOWN or right is UNKNOWN: return UNKNOWN
        try:
            if operator == "&&": return _truth(left) and _truth(right)
            if operator == "||": return _truth(left) or _truth(right)
            if operator == "==": return left == right
            if operator == "!=": return left != right
            if operator == "matches": return bool(re.fullmatch(str(right), str(left)))
            if operator == ">": return left > right
            if operator == ">=": return left >= right
            if operator == "<": return left < right
            if operator == "<=": return left <= right
            if operator == "+":
                if isinstance(left, str) or isinstance(right, str):
                    s_left, s_right = str(left), str(right)
                    if len(s_left) + len(s_right) > 100_000:
                        return UNKNOWN
                    return s_left + s_right
                return left + right
            if operator == "-": return left - right
            if operator == "*":
                if isinstance(left, (str, list)) or isinstance(right, (str, list)):
                    seq = left if isinstance(left, (str, list)) else right
                    count = right if isinstance(left, (str, list)) else left
                    if not isinstance(count, int) or count < 0 or len(seq) * count > 100_000:
                        return UNKNOWN
                return left * right
            if operator == "/":
                if right == 0:
                    return UNKNOWN
                return left / right
        except (TypeError, ValueError, ZeroDivisionError, OverflowError, re.error):
            return UNKNOWN
    raise SpelError(f"AST desconhecida: {kind}")


def evaluate_expression(expression: str, environment: dict[str, Any]) -> Any:
    return evaluate(parse(expression), environment)


def evaluate_condition(expression: str, environment: dict[str, Any]) -> bool | _Unknown:
    value = evaluate_expression(expression, environment)
    return _truth(value)

# ------------------------------------------------------------------------------
# Module: conditions.py
# ------------------------------------------------------------------------------

"""Statically analyze boolean conditions in a Watson Assistant Dialog export."""


import sys
from pathlib import Path



import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_TERMS = 256
INTENT_PATTERN = re.compile(r"(?<![\w#])#([\w.-]+)")
ENTITY_PATTERN = re.compile(r"(?<![\w@])@([\w-]+)")
VARIABLE_PATTERN = re.compile(r"\$([A-Za-z_][\w-]*)")
INVALID_ENTITY_SHORTHAND_MEMBER = re.compile(r"@[\w-]+:\([^)]*\)\s*\.\s*[A-Za-z_]\w*")
INVALID_ENTITY_CALL = re.compile(r"@[\w-]+\s*\(")
INVALID_ENTITY_CALL_NAME = re.compile(r"@([\w-]+)\s*\(")
COMPARISON_PATTERN = re.compile(r"^\s*([\$A-Za-z_][\w.\[\]'\"]*)\s*(==|!=)\s*(['\"][^'\"]*['\"]|-?\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class Formula:
    kind: str
    value: Any


def sorted_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (node.get("sequencia") is None, node.get("sequencia", 0), str(node.get("uuid") or "")))


def strip_outer_parentheses(expression: str) -> str:
    expression = expression.strip()
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        quote: str | None = None
        wraps_all = True
        for index, character in enumerate(expression):
            if quote:
                if character == quote and expression[index - 1] != "\\":
                    quote = None
            elif character in "'\"":
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    wraps_all = False
                    break
        if not wraps_all or depth != 0:
            break
        expression = expression[1:-1].strip()
    return expression


def split_top_level(expression: str, symbols: tuple[str, ...], words: tuple[str, ...]) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    upper = expression.upper()
    while index < len(expression):
        character = expression[index]
        if quote:
            if character == quote and (index == 0 or expression[index - 1] != "\\"):
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 0:
            symbol = next((item for item in symbols if expression.startswith(item, index)), None)
            if symbol:
                parts.append(expression[start:index].strip())
                start = index + len(symbol)
                index = start
                continue
            word = next((item for item in words if upper.startswith(item, index) and (index == 0 or not upper[index - 1].isalnum()) and (index + len(item) == len(upper) or not upper[index + len(item)].isalnum())), None)
            if word:
                parts.append(expression[start:index].strip())
                start = index + len(word)
                index = start
                continue
        index += 1
    if not parts:
        return [expression.strip()]
    parts.append(expression[start:].strip())
    return parts


def parse_formula(expression: str) -> Formula:
    expression = strip_outer_parentheses(expression)
    if expression.lower() == "true":
        return Formula("const", True)
    if expression.lower() == "false":
        return Formula("const", False)
    parts = split_top_level(expression, ("||",), ("OR",))
    if len(parts) > 1:
        return Formula("or", tuple(parse_formula(part) for part in parts))
    parts = split_top_level(expression, ("&&",), ("AND",))
    if len(parts) > 1:
        return Formula("and", tuple(parse_formula(part) for part in parts))
    if expression.startswith("!") and not expression.startswith("!="):
        return Formula("not", parse_formula(expression[1:].strip()))
    return Formula("atom", re.sub(r"\s+", " ", expression).strip())


def merge_terms(left: dict[str, bool], right: dict[str, bool]) -> dict[str, bool] | None:
    result = dict(left)
    equalities: dict[str, str] = {}
    inequalities: set[tuple[str, str]] = set()
    for key, value in [*left.items(), *right.items()]:
        if key in result and result[key] != value:
            return None
        result[key] = value
        match = COMPARISON_PATTERN.match(key)
        if not match:
            continue
        subject, operator, literal = match.groups()
        literal = literal.strip("'\"")
        if operator == "==" and value:
            if subject in equalities and equalities[subject] != literal:
                return None
            if (subject, literal) in inequalities:
                return None
            equalities[subject] = literal
        elif operator == "!=" and value:
            if equalities.get(subject) == literal:
                return None
            inequalities.add((subject, literal))
    return result


def terms(formula: Formula, negated: bool = False) -> list[dict[str, bool]]:
    if formula.kind == "const":
        return [{}] if formula.value != negated else []
    if formula.kind == "atom":
        return [{formula.value: not negated}]
    if formula.kind == "not":
        return terms(formula.value, not negated)
    if formula.kind == "or":
        children = formula.value if not negated else tuple(Formula("not", child) for child in formula.value)
        if negated:
            return terms(Formula("and", children))
        return [term for child in children for term in terms(child)] [:MAX_TERMS]
    if formula.kind == "and":
        children = formula.value if not negated else tuple(Formula("not", child) for child in formula.value)
        if negated:
            return terms(Formula("or", children))
        product: list[dict[str, bool]] = [{}]
        for child in children:
            next_product: list[dict[str, bool]] = []
            for left in product:
                for right in terms(child):
                    merged = merge_terms(left, right)
                    if merged is not None:
                        next_product.append(merged)
            product = next_product[:MAX_TERMS]
        return product
    raise ValueError(f"Tipo de fórmula desconhecido: {formula.kind}")


def formula_contains_constant(formula: Formula, value: bool) -> bool:
    """Return whether a parsed formula contains an explicit boolean constant."""
    if formula.kind == "const":
        return formula.value is value
    if formula.kind == "not":
        return formula_contains_constant(formula.value, value)
    if formula.kind in {"and", "or"}:
        return any(formula_contains_constant(child, value) for child in formula.value)
    return False


def analyze_formula(condition: str) -> dict[str, Any]:
    normalized = condition.strip()
    parsed = parse_formula(normalized)
    satisfiable_terms = terms(parsed)
    return {
        "normalized": normalized,
        "is_satisfiable": bool(satisfiable_terms),
        "is_always_true": normalized.lower() == "true",
        # Watson Dialog explicitly supports `false` as a deliberate way to
        # disable a branch or keep it only as an alternate jump target.
        # Preserve that intent separately from accidental contradictions.
        "has_explicit_false": formula_contains_constant(parsed, False),
    }


def known_artifacts(document: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    intents = {str(item["nome"]) for item in document.get("intencoes", []) if isinstance(item, dict) and item.get("nome")}
    entities = {str(item["nome"]) for item in document.get("entidades", []) if isinstance(item, dict) and item.get("nome")}
    variables = {str(item["variavelContexto"]).lstrip("$") for item in document.get("variaveisContexto", []) if isinstance(item, dict) and item.get("variavelContexto")}
    return intents, entities, variables


def condition_references(condition: str) -> dict[str, list[str]]:
    code = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", lambda match: " " * len(match.group(0)), condition)
    return {
        "intents": sorted(set(INTENT_PATTERN.findall(code))),
        "entities": sorted(set(ENTITY_PATTERN.findall(code))),
        "variables": sorted(set(VARIABLE_PATTERN.findall(code))),
    }


def iter_groups(nodes: list[dict[str, Any]], parent: str = "root") -> Any:
    yield parent, sorted_siblings(nodes)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("uuid") or "(sem_uuid)")
        children = node.get("filhos") or []
        if children:
            yield from iter_groups(children, node_id)
        for slot in node.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            yield slot_id, sorted_siblings(slot.get("filhos") or [])
            for child in slot.get("filhos") or []:
                if isinstance(child, dict):
                    nested = child.get("filhos") or []
                    if nested:
                        yield from iter_groups(nested, str(child.get("uuid") or "(sem_uuid)"))


def iter_conditions(document: dict[str, Any]) -> Any:
    def visit(nodes: list[dict[str, Any]]) -> Any:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node.get("condicao"):
                yield node_id, "dialog_node", str(node["condicao"])
            for response in node.get("respostas") or []:
                if isinstance(response, dict):
                    condition = response.get("condicao") or response.get("conditions")
                    if condition:
                        yield f"response:{node_id}:{response.get('uuid', '')}", "response_condition", str(condition)
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    if slot.get("condicao"):
                        yield f"slot:{slot.get('uuid') or '(sem_uuid)'}", "slot", str(slot["condicao"])
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])
    yield from visit(document.get("nos") or [])


def dormant_legacy_nodes(document: dict[str, Any], formula_by_node: dict[str, dict[str, Any]]) -> set[str]:
    """Return nodes dormant themselves or underneath dormant source evidence.

    A path is treated as dormant for *active-flow diagnostics* when the
    normalized source marks a node `INATIVO` or when that node's condition is
    statically unsatisfiable.  This does not erase the node: explicit-false
    branches can still be valid jump targets and remain present in graph/data
    outputs.
    """
    dormant: set[str] = set()

    def visit(nodes: list[dict[str, Any]], ancestor_dormant: bool = False) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            formula = formula_by_node.get(node_id)
            own_dormant = (
                str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}
                or (formula is not None and not formula["is_satisfiable"])
            )
            current_dormant = ancestor_dormant or own_dormant
            if current_dormant:
                dormant.add(node_id)
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    visit(slot.get("filhos") or [], current_dormant)
            visit(node.get("filhos") or [], current_dormant)

    yield_nodes = document.get("nos") or []
    if isinstance(yield_nodes, list):
        visit(yield_nodes)
    return dormant


def observed_jump_targets(document: dict[str, Any]) -> set[str]:
    """Collect legacy node IDs that have an explicit alternate jump entry."""
    targets: set[str] = set()

    def capture(value: Any) -> None:
        if value not in (None, "", "root"):
            targets.add(str(value))

    def visit(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            capture(node.get("uuidEnviarPara"))
            for response in node.get("respostas") or []:
                if isinstance(response, dict):
                    capture(response.get("uuidEnviarPara") or response.get("dialog_node"))
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    capture(slot.get("uuidEnviarPara"))
                    for response in slot.get("respostas") or []:
                        if isinstance(response, dict):
                            capture(response.get("uuidEnviarPara") or response.get("dialog_node"))
                    visit(slot.get("filhos") or [])
            visit(node.get("filhos") or [])

    yield_nodes = document.get("nos") or []
    if isinstance(yield_nodes, list):
        visit(yield_nodes)
    return targets


def sibling_order_is_proven(siblings: list[dict[str, Any]]) -> bool:
    """Whether legacy sibling order can be derived without a tie-break guess."""
    if len(siblings) <= 1:
        return True
    sequences = [node.get("sequencia") for node in siblings if isinstance(node, dict)]
    return all(sequence is not None for sequence in sequences) and len(set(sequences)) == len(sequences)


def analyze_conditions(document: dict[str, Any], check_variables: bool = False, summary_only: bool = False) -> dict[str, Any]:
    intents, entities, variables = known_artifacts(document)
    issues: list[dict[str, str]] = []

    def add(issue_type: str, severity: str, node: str, message: str, condition: str) -> None:
        issues.append({"type": issue_type, "severity": severity, "node": node, "message": message, "condition": condition})

    formula_by_node: dict[str, dict[str, Any]] = {}
    for node, _kind, condition in iter_conditions(document):
        formula = analyze_formula(condition)
        formula_by_node[node] = formula

    dormant_nodes = dormant_legacy_nodes(document, formula_by_node)
    jump_targets = observed_jump_targets(document)

    for node, _kind, condition in iter_conditions(document):
        formula = formula_by_node[node]
        if not formula["is_satisfiable"]:
            if formula["has_explicit_false"]:
                add("disabled_condition_false", "info", node, "A condição contém `false` explícito e mantém o ramo deliberadamente desabilitado no fluxo normal.", condition)
            else:
                add("unsatisfiable_condition", "warning", node, "A condição é logicamente impossível sem um `false` explícito de desabilitação.", condition)
        if INVALID_ENTITY_SHORTHAND_MEMBER.search(condition):
            add("invalid_spel_entity_shorthand_member", "error", node, "Um atalho @entidade:(valor) já retorna booleano e não pode acessar uma propriedade como .literal.", condition)
        invalid_called_entities = set(INVALID_ENTITY_CALL_NAME.findall(condition))
        if invalid_called_entities:
            add("invalid_spel_entity_call", "error", node, "Entidades não são funções; a sintaxe @entidade(...) é inválida.", condition)

        owner = node.split(":")[1] if node.startswith("response:") else (node.removeprefix("slot:") if node.startswith("slot:") else node)
        is_dormant = node in dormant_nodes or owner in dormant_nodes
        ref_severity = "info" if is_dormant else "warning"

        for intent in condition_references(condition)["intents"]:
            if intent not in intents:
                add("unknown_intent", ref_severity, node, f"Intent não definida: #{intent}.", condition)
        for entity in condition_references(condition)["entities"]:
            if entity in invalid_called_entities:
                continue
            if entity not in entities and not entity.startswith("sys-"):
                add("unknown_entity", ref_severity, node, f"Entidade não definida: @{entity}.", condition)
        if check_variables:
            for variable in condition_references(condition)["variables"]:
                if variable not in variables and variable not in {"integrations", "skills"}:
                    add("unknown_variable", "info", node, f"Variável de contexto não declarada: ${variable}.", condition)
    for _group, siblings in iter_groups(document.get("nos") or []):
        # Do not invent a UUID tie-break and then report reachability from it.
        # Duplicate/missing legacy sequence values make relative order an
        # unresolved provenance question; the unified validator reports that
        # separately as `legacy_order_ambiguous`.
        if not sibling_order_is_proven(siblings):
            continue
        always_true: tuple[str, int] | None = None
        seen: dict[str, tuple[str, int]] = {}
        for index, node in enumerate(siblings):
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node_id in dormant_nodes:
                continue
            condition = str(node.get("condicao") or "")
            if not condition:
                continue
            formula = formula_by_node.get(node_id, analyze_formula(condition))
            if always_true:
                always_true_id, always_true_index = always_true
                interval = {str(item.get("uuid") or "(sem_uuid)") for item in siblings[always_true_index + 1:index + 1] if isinstance(item, dict)}
                if not (interval & jump_targets):
                    add("shadowed_by_always_true", "warning", node_id, f"Um nó anterior ({always_true_id}) com condição true impede a avaliação deste irmão no fluxo normal, sem entrada Jump observada no intervalo.", condition)
            elif formula["normalized"] in seen and formula["is_satisfiable"]:
                prior_id, prior_index = seen[formula["normalized"]]
                interval = {str(item.get("uuid") or "(sem_uuid)") for item in siblings[prior_index + 1:index + 1] if isinstance(item, dict)}
                if not (interval & jump_targets):
                    add("duplicate_sibling_condition", "info", node_id, f"Condição idêntica à do irmão anterior {prior_id}, sem entrada Jump observada no intervalo.", condition)
            if formula["is_always_true"]:
                always_true = (node_id, index)
            seen.setdefault(formula["normalized"], (node_id, index))

    ordered_issues = sorted(issues, key=lambda issue: (issue["node"], issue["type"], issue["condition"]))
    by_type = {issue_type: sum(issue["type"] == issue_type for issue in ordered_issues) for issue_type in sorted({issue["type"] for issue in ordered_issues})}
    return {
        "schema_version": 1,
        "summary": {"conditions": len(formula_by_node), "issues": len(ordered_issues), "issues_by_type": by_type},
        "issues": [] if summary_only else ordered_issues,
    }


def evaluate_document_conditions(document: dict[str, Any], environment: dict[str, Any], summary_only: bool = False) -> dict[str, Any]:
    """Evaluate every node/slot condition against one supplied runtime state."""
    evaluations: list[dict[str, str]] = []
    for node, kind, condition in iter_conditions(document):
        try:
            result = evaluate_condition(condition, environment)
            value = "unknown" if result is UNKNOWN else str(result).lower()
        except Exception:
            value = "unknown"
        evaluations.append({"node": node, "kind": kind, "condition": condition, "result": value})
    evaluations.sort(key=lambda item: item["node"])
    return {
        "summary": {key: sum(item["result"] == key for item in evaluations) for key in ("true", "false", "unknown")},
        "evaluations": [] if summary_only else evaluations,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Analisa alcançabilidade e referências em condições do Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto; pode gerar avisos para integrações externas")
    parser.add_argument("--scenario", type=Path, help="JSON com input, context, intents e entities para avaliar as condições")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado de contagens")
    args = parser.parse_args()
    try:
        doc = load_json(args.input, max_bytes=args.max_input_bytes)
        report = analyze_conditions(doc, check_variables=args.check_variables, summary_only=args.summary_only)
        if args.scenario:
            scenario_data = load_json(args.scenario, max_bytes=args.max_input_bytes)
            report["evaluation"] = evaluate_document_conditions(doc, scenario_data, summary_only=args.summary_only)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["summary"]["issues"] or report.get("evaluation", {}).get("summary", {}).get("unknown") else 0



# ------------------------------------------------------------------------------
# Module: test_runner.py
# ------------------------------------------------------------------------------

"""Deterministic, traceable scenario runner for legacy Watson Dialog exports."""


import sys
from pathlib import Path



import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
ROOT_GROUP = "root"
MAX_IMMEDIATE_JUMPS = 5_000
MAX_NODE_EXECUTIONS_PER_TURN = 50


def scenario_name(scenario: dict[str, Any], path: Path | None = None) -> str:
    return str(scenario.get("name") or (path.stem if path else "scenario"))


def validate_scenario(scenario: dict[str, Any]) -> None:
    for key, expected in (("input", dict), ("context", dict), ("entities", (dict, list)), ("intents", list), ("turns", list), ("cursor", str), ("effects", dict)):
        if key in scenario and not isinstance(scenario[key], expected):
            raise ValueError(f"scenario.{key} deve ser {expected}.")
    if "dialog_stack" in scenario:
        stack = scenario["dialog_stack"]
        if isinstance(stack, str):
            return
        if not isinstance(stack, list) or any(not isinstance(item, dict) or not isinstance(item.get("dialog_node"), str) for item in stack):
            raise ValueError("scenario.dialog_stack deve ser uma string ou uma lista de objetos com dialog_node.")


def condition_result(condition: str, environment: dict[str, Any], fallback: bool) -> str:
    normalized = condition.strip().lower()
    if normalized == "anything_else": return "true" if fallback else "false"
    if normalized == "welcome": return "true" if environment.get("is_first_turn") and not environment.get("input", {}).get("text") else "false"
    if normalized == "conversation_start": return "true" if environment.get("conversation_start", environment.get("is_first_turn")) is True else "false"
    if normalized == "irrelevant": return "true" if environment.get("irrelevant") is True else "false"
    try: value = evaluate_condition(condition, environment)
    except Exception: return "unknown"
    return "unknown" if value is UNKNOWN else str(value).lower()


def normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Convert the flat Dialog API V1 shape into the legacy runner shape.

    The runner remains intentionally read-only. This adapter only preserves the
    execution fields it understands, and leaves the caller's document intact.
    """
    if "nos" in document:
        return document
    raw_nodes = document.get("dialog_nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("O diálogo precisa conter nos (legado) ou dialog_nodes (API V1).")
    by_id = {str(node["dialog_node"]): node for node in raw_nodes if isinstance(node, dict) and node.get("dialog_node") is not None}
    children: dict[str | None, list[str]] = {}
    for node_id, node in by_id.items():
        parent = node.get("parent")
        children.setdefault(str(parent) if parent not in (None, "") else None, []).append(node_id)

    def ordered(parent: str | None) -> list[str]:
        ids = children.get(parent, [])
        by_previous = {str(by_id[node_id].get("previous_sibling")): node_id for node_id in ids if by_id[node_id].get("previous_sibling") not in (None, "")}
        first = [node_id for node_id in ids if by_id[node_id].get("previous_sibling") in (None, "")]
        result: list[str] = []
        if len(first) == 1:
            current = first[0]
            seen: set[str] = set()
            while current not in seen:
                result.append(current); seen.add(current)
                if current not in by_previous: break
                current = by_previous[current]
        return result if len(result) == len(ids) else sorted(ids)

    def next_fields(node: dict[str, Any]) -> dict[str, Any]:
        next_step = node.get("next_step") or {}
        if not isinstance(next_step, dict): return {}
        behavior = str(next_step.get("behavior") or "")
        target = next_step.get("dialog_node") or next_step.get("target")
        if behavior in {"jump_to", "jump"} and target:
            selector = str(next_step.get("selector") or "condition")
            return {"uuidEnviarPara": str(target), "jumpSelector": {"response": "body", "client": "user_input"}.get(selector, selector)}
        if behavior in {"skip_user_input", "skip"}:
            return {"jumpSelector": "move_on"}
        return {"jumpSelector": "wait_user_input"}

    def handler(node_id: str, sequence: int) -> dict[str, Any]:
        node = by_id[node_id]
        return {
            "uuid": node_id, "uuidSlot": str(node.get("parent") or ""), "sequencia": sequence,
            "nome": node.get("title"), "condicao": node.get("conditions") or "true",
            "event_name": node.get("event_name"), "respostas": [], "filhos": [], **next_fields(node),
        }

    def convert(node_id: str, sequence: int) -> dict[str, Any]:
        node = by_id[node_id]
        node_type = str(node.get("type") or "standard")
        value: dict[str, Any] = {
            "uuid": node_id, "nome": node.get("title"), "sequencia": sequence,
            "condicao": node.get("conditions") or "true", "folder": node_type == "folder",
            "respostas": [], "filhos": [], "slots": [], **next_fields(node),
            "actions": node.get("actions") or [], "webhook": node.get("webhook"),
            "inDigressionIn": str(node.get("digress_in") or "returns") != "not_available",
            "inDigressionOut": str(node.get("digress_out") or "allow_all") != "not_available",
            "inRetornoDigression": str(node.get("digress_in") or "returns") == "returns",
            "inDigressionSlot": str(node.get("digress_out_slots") or "not_allowed") != "not_allowed",
        }
        for child_sequence, child_id in enumerate(ordered(node_id)):
            child = by_id[child_id]
            child_type = str(child.get("type") or "standard")
            if child_type == "response_condition":
                value["respostas"].append({"uuid": child_id, "sequenciaBloco": child_sequence, "sequenciaItem": 0, "condicao": child.get("conditions") or "true", **next_fields(child)})
            elif child_type == "slot":
                slot_handlers = [handler(handler_id, handler_sequence) for handler_sequence, handler_id in enumerate(ordered(child_id)) if str(by_id[handler_id].get("type") or "standard") == "event_handler"]
                metadata = child.get("metadata") or {}
                value["slots"].append({
                    "uuid": child_id, "identificador": child.get("variable") or child_id,
                    "uuidVariavelContexto": child.get("variable"), "indicadorObrigatorio": bool(child.get("required") or metadata.get("required")),
                    "condicao": child.get("conditions") or "true", "respostas": [], "filhos": slot_handlers,
                })
            elif child_type in {"standard", "frame", "folder"}:
                value["filhos"].append(convert(child_id, child_sequence))
        frame_handlers = [handler(handler_id, handler_sequence) for handler_sequence, handler_id in enumerate(ordered(node_id)) if str(by_id[handler_id].get("type") or "standard") == "event_handler"]
        if frame_handlers:
            value["frame_handlers"] = frame_handlers
        return value

    roots = [convert(node_id, sequence) for sequence, node_id in enumerate(ordered(None)) if str(by_id[node_id].get("type") or "standard") in {"standard", "frame", "folder"}]
    variables = [{"uuid": str(node.get("variable")), "variavelContexto": str(node.get("variable"))} for node in by_id.values() if str(node.get("type") or "standard") == "slot" and node.get("variable")]
    return {"nos": roots, "variaveisContexto": variables}


def index_dialog(document: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[str]] = {}
    group_of: dict[str, str] = {}
    children_of: dict[str, str] = {}
    slots: dict[str, dict[str, Any]] = {}
    frame_for_slot: dict[str, str] = {}

    def visit(values: list[dict[str, Any]], group: str) -> None:
        ordered = sorted_siblings(values)
        groups[group] = [str(node["uuid"]) for node in ordered]
        for node in ordered:
            node_id = str(node["uuid"])
            nodes[node_id], group_of[node_id] = node, group
            child_group = f"children:{node_id}"
            children_of[node_id] = child_group
            frame_handlers = sorted_siblings(node.get("frame_handlers") or [])
            groups[f"frame_handlers:{node_id}"] = [str(handler["uuid"]) for handler in frame_handlers]
            for handler in frame_handlers:
                handler_id = str(handler["uuid"])
                nodes[handler_id], group_of[handler_id] = handler, f"frame_handlers:{node_id}"
                children_of[handler_id] = f"children:{handler_id}"
            visit(node.get("filhos") or [], child_group)
            for slot in node.get("slots") or []:
                slot_id = str(slot["uuid"])
                slots[slot_id] = slot
                frame_for_slot[slot_id] = node_id
                visit(slot.get("filhos") or [], f"slot:{slot['uuid']}")

    visit(document.get("nos") or [], ROOT_GROUP)
    variable_by_uuid = {str(item["uuid"]): str(item["variavelContexto"]).lstrip("$") for item in document.get("variaveisContexto") or [] if item.get("uuid") and item.get("variavelContexto")}
    return {"nodes": nodes, "groups": groups, "group_of": group_of, "children_of": children_of, "slots": slots, "frame_for_slot": frame_for_slot, "variable_by_uuid": variable_by_uuid}


def set_cursor(state: dict[str, Any], index: dict[str, Any], cursor: str) -> None:
    if cursor == ROOT_GROUP:
        state["cursor"] = ROOT_GROUP
        return
    if cursor not in index["nodes"]:
        raise ValueError(f"Cursor aponta para UUID inexistente: {cursor}")
    state["cursor"] = cursor


def first_child(index: dict[str, Any], node_id: str) -> str | None:
    children = index["groups"].get(index["children_of"][node_id], [])
    return children[0] if children else None


def stack_node(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[-1].get("dialog_node", ROOT_GROUP))
    return str(value or ROOT_GROUP)


def cursor_for_stack(index: dict[str, Any], dialog_stack: str) -> str:
    if dialog_stack == ROOT_GROUP:
        return ROOT_GROUP
    # A stack points at the active node; the next request starts at its child.
    return first_child(index, dialog_stack) or dialog_stack


def select(index: dict[str, Any], cursor: str, environment: dict[str, Any], trace: list[dict[str, Any]]) -> str | None:
    """Evaluate root, or a node and its following logical siblings.

    A Watson folder is not itself a response-producing dialog step. If its
    condition matches, the runtime immediately evaluates its contents; when no
    contained node matches, evaluation continues after the folder.
    """
    if cursor == ROOT_GROUP:
        group, candidates = ROOT_GROUP, index["groups"].get(ROOT_GROUP, [])
    else:
        group = index["group_of"].get(cursor)
        if group is None:
            raise ValueError(f"Cursor aponta para UUID inexistente: {cursor}")
        siblings = index["groups"][group]
        candidates = siblings[siblings.index(cursor):]
    for node_id in candidates:
        node = index["nodes"][node_id]
        condition = str(node.get("condicao") or "")
        result = condition_result(condition, environment, fallback=True)
        event = "folder_condition" if node.get("folder") else "condition"
        trace.append({"event": event, "scope": group, "node": node_id, "name": node.get("nome"), "condition": condition, "result": result})
        if result != "true":
            continue
        if node.get("folder"):
            child = first_child(index, node_id)
            if child and (selected := select(index, child, environment, trace)) is not None:
                return selected
            continue
        return node_id
    return None


def entity_value(condition: str, environment: dict[str, Any]) -> Any:
    match = re.search(r"@([\w-]+)", condition)
    if not match: return environment.get("input", {}).get("text")
    entity, values = match.group(1), environment.get("entities", {})
    if isinstance(values, dict):
        value = values.get(entity, UNKNOWN)
        return value[0] if isinstance(value, list) and value else value
    for value in values:
        if value.get("entity") == entity: return value.get("value", UNKNOWN)
    return UNKNOWN


def run_slot_handlers(handler_ids: list[str], event_name: str, index: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]], slot_id: str) -> str | None:
    for handler_id in handler_ids:
        handler = index["nodes"][handler_id]
        if handler.get("event_name") != event_name:
            continue
        condition = str(handler.get("condicao") or "true")
        result = condition_result(condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=event_name in {"generic", "nomatch"})
        trace.append({"event": "slot_handler_condition", "scope": f"slot:{slot_id}", "node": handler_id, "name": handler.get("nome"), "handler_event": event_name, "condition": condition, "result": result})
        if result == "true":
            trace.append({"event": "slot_handler", "scope": f"slot:{slot_id}", "node": handler_id, "handler_event": event_name, "action": str(handler.get("jumpSelector") or "wait_user_input")})
            record_node_execution(state, handler_id, trace)
            return handler_id
    return None


def fill_slot(frame: dict[str, Any], index: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    for slot in frame.get("slots") or []:
        slot_id = str(slot["uuid"])
        variable = index["variable_by_uuid"].get(str(slot.get("uuidVariavelContexto")))
        if variable and state["context"].get(variable) not in (None, ""):
            continue
        condition = str(slot.get("condicao") or "")
        handler_ids = index["groups"].get(f"slot:{slot_id}", [])
        v1_handlers = any(index["nodes"][handler_id].get("event_name") for handler_id in handler_ids)
        if v1_handlers:
            all_handler_ids = [*handler_ids, *index["groups"].get(f"frame_handlers:{frame['uuid']}", [])]
            if slot_id not in state["focused_slots"]:
                state["focused_slots"].add(slot_id)
                if handler := run_slot_handlers(all_handler_ids, "focus", index, state, environment, trace, slot_id):
                    return {"filled": False, "handler": handler}
            input_handler = run_slot_handlers(all_handler_ids, "input", index, state, environment, trace, slot_id)
        else:
            all_handler_ids, input_handler = handler_ids, None
        result = condition_result(condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=False)
        trace.append({"event": "slot_condition", "scope": f"slot:{slot_id}", "node": f"slot:{slot_id}", "condition": condition, "result": result})
        if result == "true":
            value = entity_value(condition, environment)
            if variable and value is not UNKNOWN: state["context"][variable] = value
            state["filled_slots"].add(slot_id)
            trace.append({"event": "slot_filled", "scope": f"slot:{slot_id}", "node": f"slot:{slot_id}", "context_variable": variable, "value": None if value is UNKNOWN else value})
            if v1_handlers:
                handler = run_slot_handlers(all_handler_ids, "filled", index, state, environment, trace, slot_id)
                generic = run_slot_handlers(all_handler_ids, "generic", index, state, environment, trace, slot_id)
                return {"filled": True, "handler": generic or handler or input_handler}
            return {"filled": True, "handler": None}
        if v1_handlers:
            generic = run_slot_handlers(all_handler_ids, "generic", index, state, environment, trace, slot_id)
            nomatch = None if generic else run_slot_handlers(all_handler_ids, "nomatch", index, state, environment, trace, slot_id)
            return {"filled": False, "handler": generic or nomatch or input_handler}
        for handler_id in handler_ids:
            handler = index["nodes"][handler_id]
            handler_condition = str(handler.get("condicao") or "")
            handler_result = condition_result(handler_condition, {**environment, "context": state["context"], "slot_in_focus": True}, fallback=True)
            trace.append({"event": "slot_handler_condition", "scope": f"slot:{slot_id}", "node": handler_id, "name": handler.get("nome"), "condition": handler_condition, "result": handler_result})
            if handler_result == "true":
                trace.append({"event": "slot_handler", "scope": f"slot:{slot_id}", "node": handler_id, "action": str(handler.get("jumpSelector") or "wait_user_input")})
                record_node_execution(state, handler_id, trace)
                return {"filled": False, "handler": handler_id}
        return {"filled": False, "handler": None}
    return {"filled": False, "handler": None}


def required_slots_filled(frame: dict[str, Any], state: dict[str, Any]) -> bool:
    return all(str(slot["uuid"]) in state["filled_slots"] or not slot.get("indicadorObrigatorio") for slot in frame.get("slots") or [])


def restore_slot_state(frame_id: str, index: dict[str, Any], state: dict[str, Any]) -> None:
    """Rebuild filled-slot state when a request starts with a slot UUID."""
    frame = index["nodes"][frame_id]
    state["active_frame"] = frame_id
    stack_slot = state["dialog_stack"]
    if stack_slot in index["slots"]:
        state["focused_slots"].add(stack_slot)
    for slot in frame.get("slots") or []:
        variable = index["variable_by_uuid"].get(str(slot.get("uuidVariavelContexto")))
        if variable and state["context"].get(variable) not in (None, ""):
            state["filled_slots"].add(str(slot["uuid"]))


def stack_after(state: dict[str, Any], index: dict[str, Any]) -> list[dict[str, Any]]:
    item: dict[str, Any] = {"dialog_node": state["dialog_stack"]}
    if state["active_frame"] and state["dialog_stack"] in index["slots"]:
        item["state"] = "in_progress"
    return [item]


def selected_data(index: dict[str, Any], node_id: str, direct: bool = False) -> dict[str, Any]:
    node = index["nodes"][node_id]
    data = {"node": node_id, "name": node.get("nome"), "condition": node.get("condicao")}
    if direct: data["direct_response"] = True
    return data


def record_node_execution(state: dict[str, Any], node_id: str, trace: list[dict[str, Any]]) -> bool:
    """Record execution and stop the turn when one UUID reaches the loop limit."""
    count = 1 + sum(item.get("event") == "node_execution" and item.get("node") == node_id for item in trace)
    trace.append({"event": "node_execution", "node": node_id, "count": count})
    if count <= MAX_NODE_EXECUTIONS_PER_TURN:
        return True
    trace.append({"event": "error", "code": "node_execution_limit", "node": node_id, "executions": count, "limit": MAX_NODE_EXECUTIONS_PER_TURN})
    return False


def can_digress(index: dict[str, Any], state: dict[str, Any], target: str) -> tuple[bool, str]:
    """Return whether the current branch may enter a matching root target."""
    target_node = index["nodes"][target]
    if not target_node.get("inDigressionIn", True):
        return False, "target_disallows_digression"
    if state["active_frame"]:
        frame = index["nodes"][state["active_frame"]]
        if not frame.get("inDigressionSlot", False):
            return False, "slot_filling_disallows_digression"
    source = index["nodes"].get(state["dialog_stack"])
    if source:
        if not source.get("inDigressionOut", True):
            return False, "source_disallows_digression"
        if source.get("uuidEnviarPara") or str(source.get("jumpSelector") or "") == "move_on":
            return False, "source_forces_transition"
        if any(str(child.get("condicao") or "").strip().lower() in {"true", "anything_else"} for child in source.get("filhos") or []):
            return False, "source_has_forcing_child"
    return True, "allowed"


def begin_digression(index: dict[str, Any], state: dict[str, Any], target: str, trace: list[dict[str, Any]]) -> None:
    returns = bool(index["nodes"][target].get("inRetornoDigression"))
    if returns:
        state["digression_returns"].append({
            "cursor": state["cursor"], "dialog_stack": state["dialog_stack"], "active_frame": state["active_frame"],
            "filled_slots": set(state["filled_slots"]), "focused_slots": set(state["focused_slots"]),
        })
    else:
        # A destination configured not to return abandons every suspended
        # conversation, including an outer digression.
        state["digression_returns"].clear()
    trace.append({"event": "digression", "from": state["dialog_stack"], "target": target, "returns": returns})


def return_from_digression(state: dict[str, Any], trace: list[dict[str, Any]], node: str) -> bool:
    if not state["digression_returns"]:
        return False
    saved = state["digression_returns"].pop()
    state["cursor"] = saved["cursor"]
    state["dialog_stack"] = saved["dialog_stack"]
    state["active_frame"] = saved["active_frame"]
    state["filled_slots"] = saved["filled_slots"]
    state["focused_slots"] = saved["focused_slots"]
    trace.append({"event": "digression_return", "node": node, "to": state["dialog_stack"]})
    return True


def abandon_digression_returns(state: dict[str, Any], trace: list[dict[str, Any]], node: str, target: str) -> None:
    """A jump leaves the digressed branch instead of returning to its caller."""
    count = len(state["digression_returns"])
    if not count:
        return
    state["digression_returns"].clear()
    trace.append({"event": "digression_return_abandoned", "node": node, "target": target, "returns": count})


def response_jump(node: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Find the first matching conditional-response jump, if represented.

    The current legacy export stores response components in ``respostas`` and
    normally has no transition fields there. Some compatible exports include
    ``condicao``/``conditions``, ``uuidEnviarPara`` and ``jumpSelector`` on a
    conditional response; Watson gives such a jump precedence over the node's
    final-step jump.
    """
    responses = sorted(node.get("respostas") or [], key=lambda value: (value.get("sequenciaBloco") is None, value.get("sequenciaBloco", 0), value.get("sequenciaItem", 0), str(value.get("uuid", ""))))
    for response in responses:
        target = str(response.get("uuidEnviarPara") or response.get("dialog_node") or "")
        if not target:
            continue
        condition = str(response.get("condicao") or response.get("conditions") or "true")
        result = condition_result(condition, environment, fallback=True)
        trace.append({"event": "response_condition", "node": str(node["uuid"]), "response": str(response.get("uuid") or ""), "condition": condition, "result": result})
        if result == "true":
            return target, str(response.get("jumpSelector") or response.get("jump_selector") or "condition")
    return None


def apply_callout_effect(node: dict[str, Any], state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    """Apply a fixture-provided webhook/action result; never call external code."""
    configured = "action" if node.get("actions") or node.get("uuidAcao") else "webhook" if node.get("webhook") or node.get("urlWebhook") else None
    if not configured:
        return
    effects = environment.get("effects") or {}
    entries = effects.get(f"{configured}s", {}) if isinstance(effects, dict) else {}
    effect = entries.get(str(node["uuid"])) if isinstance(entries, dict) else None
    if not isinstance(effect, dict):
        trace.append({"event": "callout", "node": str(node["uuid"]), "kind": configured, "result": "not_provided"})
        return
    context = effect.get("context") or {}
    if not isinstance(context, dict):
        raise ValueError("effects.<tipo>.<node>.context deve ser um objeto.")
    state["context"].update(context)
    if configured == "action" and "result" in effect:
        variable = str(effect.get("result_variable") or "action_result_1").lstrip("$")
        state["context"][variable] = effect["result"]
    trace.append({"event": "callout", "node": str(node["uuid"]), "kind": configured, "result": "applied", "context_keys": sorted(context)})


def apply_transition(index: dict[str, Any], node_id: str, state: dict[str, Any], environment: dict[str, Any], trace: list[dict[str, Any]]) -> str:
    """Apply child and jump transitions; return the selected node for this turn."""
    selected = node_id
    for _ in range(MAX_IMMEDIATE_JUMPS):
        node = index["nodes"][selected]
        if not record_node_execution(state, selected, trace):
            return selected
        apply_callout_effect(node, state, environment, trace)
        conditional_jump = response_jump(node, environment, trace)
        target = conditional_jump[0] if conditional_jump else str(node.get("uuidEnviarPara") or "")
        if target == ROOT_GROUP or target in index["nodes"]:
            abandon_digression_returns(state, trace, selected, target)
        if target == ROOT_GROUP:
            mode = conditional_jump[1] if conditional_jump else str(node.get("jumpSelector") or "condition")
            trace.append({"event": "response_jump" if conditional_jump else "jump", "node": selected, "target": target, "mode": mode})
            # Root additionally restarts the tree. The digression return was
            # already abandoned above, just as it is for any other jump.
            state["active_frame"] = None
            state["filled_slots"] = set()
            state["focused_slots"] = set()
            set_cursor(state, index, ROOT_GROUP)
            state["dialog_stack"] = ROOT_GROUP
            trace.append({"event": "tree_restart", "node": selected, "mode": mode})
            if mode == "condition":
                next_node = select(index, ROOT_GROUP, environment, trace)
                if next_node is not None:
                    selected = next_node
                    continue
            return selected
        if not target or target not in index["nodes"]:
            action = str(node.get("jumpSelector") or "user_input")
            trace.append({"event": "next_action", "node": selected, "action": action})
            if action == "move_on":
                abandon_digression_returns(state, trace, selected, first_child(index, selected) or ROOT_GROUP)
            if node.get("slots"):
                state["active_frame"] = selected
                slot_result = fill_slot(node, index, state, environment, trace)
                if required_slots_filled(node, state):
                    state["active_frame"] = None
                    set_cursor(state, index, first_child(index, selected) or ROOT_GROUP)
                    state["dialog_stack"] = ROOT_GROUP
                    trace.append({"event": "slots_complete", "node": selected})
                else:
                    state["dialog_stack"] = str(next((slot["uuid"] for slot in node.get("slots") or [] if str(slot["uuid"]) not in state["filled_slots"]), selected))
                if slot_result["handler"]:
                    selected = slot_result["handler"]
            elif (child := first_child(index, selected)):
                set_cursor(state, index, child)
                state["dialog_stack"] = selected
                if action == "move_on":
                    next_node = select(index, child, environment, trace)
                    if next_node is not None:
                        selected = next_node
                        continue
            else:
                set_cursor(state, index, ROOT_GROUP)
                if not return_from_digression(state, trace, selected):
                    state["dialog_stack"] = ROOT_GROUP
            return selected
        mode = conditional_jump[1] if conditional_jump else str(node.get("jumpSelector") or "condition")
        trace.append({"event": "response_jump" if conditional_jump else "jump", "node": selected, "target": target, "mode": mode})
        if mode == "body":
            selected = target
            trace.append({"event": "direct_response", "node": target})
            continue
        if mode == "user_input":
            # Wait for the next user message, then evaluate the destination.
            set_cursor(state, index, target)
            state["dialog_stack"] = target
            return selected
        next_node = select(index, target, environment, trace)
        if next_node is None:
            set_cursor(state, index, ROOT_GROUP)
            state["dialog_stack"] = ROOT_GROUP
            return selected
        selected = next_node
    trace.append({"event": "error", "code": "immediate_jump_limit", "node": selected})
    return selected


def run_scenario(document: dict[str, Any], scenario: dict[str, Any], source: str | None = None) -> dict[str, Any]:
    validate_scenario(scenario)
    document = normalize_document(document)
    index = index_dialog(document)
    incoming_stack = stack_node(scenario.get("dialog_stack") or scenario.get("cursor"))
    state = {"context": dict(scenario.get("context") or {}), "cursor": ROOT_GROUP, "dialog_stack": incoming_stack, "active_frame": None, "filled_slots": set(), "focused_slots": set(), "digression_returns": []}
    if incoming_stack in index["frame_for_slot"]:
        restore_slot_state(index["frame_for_slot"][incoming_stack], index, state)
    else:
        set_cursor(state, index, cursor_for_stack(index, incoming_stack))
    turns = scenario.get("turns") or [{key: scenario[key] for key in ("input", "intents", "entities", "context", "conversation_start", "irrelevant", "effects") if key in scenario}]
    results = []
    for number, turn in enumerate(turns, 1):
        validate_scenario(turn)
        dialog_stack_before = stack_node(turn.get("dialog_stack") or turn.get("cursor") or state["dialog_stack"])
        if "dialog_stack" in turn or "cursor" in turn:
            state["dialog_stack"] = dialog_stack_before
            state["active_frame"] = None
            state["filled_slots"] = set()
            state["focused_slots"] = set()
            state["digression_returns"].clear()
            if dialog_stack_before in index["frame_for_slot"]:
                restore_slot_state(index["frame_for_slot"][dialog_stack_before], index, state)
            else:
                set_cursor(state, index, cursor_for_stack(index, dialog_stack_before))
        state["context"].update(turn.get("context") or {})
        environment = {
            "input": turn.get("input", {}), "intents": turn.get("intents", []), "entities": turn.get("entities", {}), "context": state["context"],
            "is_first_turn": number == 1 and dialog_stack_before == ROOT_GROUP, "effects": {**(scenario.get("effects") or {}), **(turn.get("effects") or {})},
        }
        if "conversation_start" in turn:
            environment["conversation_start"] = turn["conversation_start"]
        if "irrelevant" in turn:
            environment["irrelevant"] = turn["irrelevant"]
        trace: list[dict[str, Any]] = []
        if state["active_frame"]:
            frame_id = state["active_frame"]
            frame = index["nodes"][frame_id]
            slot_result = fill_slot(frame, index, state, environment, trace)
            selected = slot_result["handler"] or frame_id
            if required_slots_filled(frame, state):
                state["active_frame"] = None
                set_cursor(state, index, first_child(index, frame_id) or ROOT_GROUP)
                state["dialog_stack"] = ROOT_GROUP
                trace.append({"event": "slots_complete", "node": frame_id})
        else:
            selected = select(index, state["cursor"], environment, trace)
            if selected is None and state["cursor"] != ROOT_GROUP:
                root_target = select(index, ROOT_GROUP, environment, trace)
                if root_target and str(index["nodes"][root_target].get("condicao") or "").strip().lower() != "anything_else":
                    allowed, reason = can_digress(index, state, root_target)
                    if allowed:
                        begin_digression(index, state, root_target, trace)
                        selected = root_target
                    else:
                        trace.append({"event": "digression_blocked", "from": state["dialog_stack"], "target": root_target, "reason": reason})
                else:
                    selected = root_target
            if selected: selected = apply_transition(index, selected, state, environment, trace)
        results.append({"turn": number, "input": environment["input"], "dialog_stack_before": [{"dialog_node": dialog_stack_before}], "selected": selected_data(index, selected) if selected else None, "dialog_stack_after": stack_after(state, index), "branch_exited": state["dialog_stack"] == ROOT_GROUP, "trace": trace, "context": dict(sorted(state["context"].items()))})
    expected = scenario.get("expect") or {}
    actual_nodes = [item["selected"]["node"] if item["selected"] else None for item in results]
    expected_nodes = expected.get("selected_nodes") or ([expected["selected_node"]] if "selected_node" in expected else None)
    passed = expected_nodes is None or expected_nodes == actual_nodes
    return {"name": scenario_name(scenario, Path(source) if source else None), "source": source, "turns": results, "selected": results[-1]["selected"] if results else None, "passed": passed, **({"expect": expected} if expected else {})}


def run_scenarios(document: dict[str, Any], scenarios: list[tuple[dict[str, Any], str | None]]) -> dict[str, Any]:
    results = [run_scenario(document, scenario, source) for scenario, source in scenarios]
    results.sort(key=lambda item: (item["name"], item["source"] or ""))
    return {"schema_version": SCHEMA_VERSION, "summary": {"scenarios": len(results), "passed": sum(item["passed"] for item in results), "failed": sum(not item["passed"] for item in results)}, "results": results}


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Executa sessões determinísticas de teste de um Dialog Watson.")
    parser.add_argument("dialog", type=Path)
    parser.add_argument("scenarios", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado de execução")
    args = parser.parse_args()
    try:
        doc = load_json(args.dialog, max_bytes=args.max_input_bytes)
        scenarios_loaded = [(load_json(path, max_bytes=args.max_input_bytes), str(path)) for path in args.scenarios]
        report = run_scenarios(doc, scenarios_loaded)
        if args.summary_only:
            report = {
                "schema_version": report["schema_version"],
                "summary": report["summary"],
                "results": [{"name": r["name"], "source": r["source"], "passed": r["passed"]} for r in report["results"]],
            }
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0 if not report["summary"]["failed"] else 1



# ------------------------------------------------------------------------------
# Module: graph.py
# ------------------------------------------------------------------------------

"""Build a deterministic directed graph from a Watson Assistant Dialog export."""


import sys
from pathlib import Path



import argparse
import json
import sys
from pathlib import Path
from typing import Any


GRAPH_SCHEMA_VERSION = 1


def text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def response_metadata(item: dict[str, Any]) -> dict[str, Any]:
    responses = item.get("respostas") or []
    return {
        "response_count": len(responses),
        "response_types": sorted({str(response["tipoRespostaNomeJSON"]) for response in responses if response.get("tipoRespostaNomeJSON")}),
        "component_types": sorted({response["idTipoComponente"] for response in responses if response.get("idTipoComponente") is not None}),
        "has_json_configuration": bool(item.get("json")),
    }


def node_metadata(node: dict[str, Any], kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": str(node["uuid"]),
        "kind": kind,
        # `folder` is a first-class legacy Watson Dialog node type. It is not
        # inferred from the presence of children: standard nodes can also have
        # child nodes, while a folder can be empty.
        "folder": bool(node.get("folder")),
        "name": text(node.get("nome")),
        "condition": text(node.get("condicao")),
        "sequence": node.get("sequencia"),
        "status": text(node.get("status")),
        "jump_selector": text(node.get("jumpSelector")),
        "multiple_responses": bool(node.get("respostaMultipla")),
        "has_action": bool(node.get("actions") or node.get("uuidAcao")),
        "has_webhook": bool(node.get("webhook") or node.get("urlWebhook")),
        "tags": sorted(str(tag) for tag in (node.get("tags") or [])),
        "digression": {
            "in": bool(node.get("inDigressionIn")),
            "out": bool(node.get("inDigressionOut")),
            "return": bool(node.get("inRetornoDigression")),
            "slot": bool(node.get("inDigressionSlot")),
        },
        **response_metadata(node),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], {})}


def slot_metadata(slot: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "id": f"slot:{slot['uuid']}",
        "kind": "slot",
        "name": text(slot.get("identificador")),
        "condition": text(slot.get("condicao")),
        "required": bool(slot.get("indicadorObrigatorio")),
        "multiple_responses": bool(slot.get("indicadorRespostaMultipla")),
        "tags": sorted(str(tag) for tag in (slot.get("slotTags") or [])),
        "context_variable_id": text(slot.get("uuidVariavelContexto")),
        **response_metadata(slot),
    }
    return {key: value for key, value in metadata.items() if value not in (None, [], {})}


def sorted_siblings(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (node.get("sequencia") is None, node.get("sequencia", 0), str(node["uuid"])))


def reachability(document: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    """Prove unreachable vertices from conditions and structural graph edges.

    A `body` jump targets a response directly, bypassing the target condition;
    it therefore prevents this static analysis from classifying that target as
    unreachable. Other jump modes do not provide that proof.
    """
    condition_report = analyze_conditions(document)
    direct_reasons: dict[str, list[str]] = {}
    for issue in condition_report["issues"]:
        if issue["type"] in {"disabled_condition_false", "unsatisfiable_condition", "shadowed_by_always_true"}:
            direct_reasons.setdefault(issue["node"], []).append(issue["type"])

    vertices = {vertex["id"]: vertex for vertex in graph["vertices"]}
    direct_body_targets = {
        edge["target"]
        for edge in graph["edges"]
        if edge["type"] == "jump" and vertices.get(edge["node"], {}).get("jump_selector") == "body"
    }
    parents: dict[str, set[str]] = {vertex_id: set() for vertex_id in vertices}
    for edge in graph["edges"]:
        if edge["type"] in {"contains", "contains_slot", "slot_branch"} and edge["target"] in parents:
            parents[edge["target"]].add(edge["node"])

    unreachable: dict[str, list[str]] = {
        node: sorted(reasons)
        for node, reasons in direct_reasons.items()
        if node in vertices and node not in direct_body_targets
    }
    changed = True
    while changed:
        changed = False
        for node in sorted(vertices):
            if node in unreachable or node in direct_body_targets or not parents[node]:
                continue
            if parents[node].issubset(unreachable):
                unreachable[node] = [f"all_structural_parents_unreachable:{parent}" for parent in sorted(parents[node])]
                changed = True

    items = [
        {
            "node": node,
            "kind": vertices[node]["kind"],
            "name": vertices[node].get("name"),
            "condition": vertices[node].get("condition"),
            "reasons": unreachable[node],
        }
        for node in sorted(unreachable)
    ]
    return {
        "summary": {
            "proven_unreachable": len(items),
            "condition_blocks": len(direct_reasons),
            "body_jump_exceptions": len(set(direct_reasons) & direct_body_targets),
        },
        "unreachable": items,
    }


def build_graph(document: dict[str, Any], summary_only: bool = False) -> dict[str, Any]:
    """Create a detailed graph whose edges always have node, target, and type."""
    document = normalize_document(document)
    vertices: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    unresolved_jumps: list[dict[str, str]] = []

    def add_edge(node: str, target: str, edge_type: str) -> None:
        edges.append({"node": node, "target": target, "type": edge_type})

    def add_sibling_edges(siblings: list[dict[str, Any]]) -> None:
        ordered = sorted_siblings(siblings)
        for node, target in zip(ordered, ordered[1:]):
            add_edge(str(node["uuid"]), str(target["uuid"]), "next_evaluation")

    def add_node(node: dict[str, Any], parent: str | None, edge_type: str | None) -> None:
        node_id = str(node["uuid"])
        kind = "event_handler" if node.get("event_name") else "slot_child" if node.get("uuidSlot") else "dialog_node"
        if node_id in vertices:
            raise ValueError(f"UUID de nó duplicado: {node_id}")
        vertices[node_id] = node_metadata(node, kind)
        if parent and edge_type:
            add_edge(parent, node_id, edge_type)

        for slot in sorted(node.get("slots") or [], key=lambda value: str(value["uuid"])):
            slot_id = f"slot:{slot['uuid']}"
            if slot_id in vertices:
                raise ValueError(f"UUID de slot duplicado: {slot['uuid']}")
            vertices[slot_id] = slot_metadata(slot)
            add_edge(node_id, slot_id, "contains_slot")
            children = slot.get("filhos") or []
            add_sibling_edges(children)
            for child in sorted_siblings(children):
                add_node(child, slot_id, "slot_branch")

        children = node.get("filhos") or []
        add_sibling_edges(children)
        if node.get("folder") and children:
            add_edge(node_id, str(sorted_siblings(children)[0]["uuid"]), "folder_entry")
        for child in sorted_siblings(children):
            add_node(child, node_id, "contains")

    roots = document.get("nos") or []
    add_sibling_edges(roots)
    for root in sorted_siblings(roots):
        add_node(root, None, None)

    native_nodes: dict[str, dict[str, Any]] = {}

    def index_native(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            native_nodes[str(node["uuid"])] = node
            for slot in node.get("slots") or []:
                index_native(slot.get("filhos") or [])
            index_native(node.get("filhos") or [])

    index_native(roots)
    for node_id in sorted(native_nodes):
        target = text(native_nodes[node_id].get("uuidEnviarPara"))
        if target == "root":
            add_edge(node_id, target, "tree_restart")
        elif target in vertices:
            if target:
                add_edge(node_id, target, "jump")
        elif target:
            add_edge(node_id, target, "jump")
            unresolved_jumps.append({"node": node_id, "target": target, "type": "jump"})

    ordered_vertices = [vertices[vertex_id] for vertex_id in sorted(vertices)]
    ordered_edges = sorted(edges, key=lambda edge: (edge["node"], edge["target"], edge["type"]))
    digression_targets = [
        {"node": str(root["uuid"]), "name": text(root.get("nome")), "returns": bool(root.get("inRetornoDigression"))}
        for root in sorted_siblings(roots)
        if root.get("inDigressionIn")
    ]
    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "summary": {
            "vertices": len(ordered_vertices),
            "dialog_nodes": sum(vertex["kind"] != "slot" for vertex in ordered_vertices),
            "event_handlers": sum(vertex["kind"] == "event_handler" for vertex in ordered_vertices),
            "folders": sum(bool(vertex.get("folder")) for vertex in ordered_vertices),
            "slots": sum(vertex["kind"] == "slot" for vertex in ordered_vertices),
            "callouts": sum(bool(vertex.get("has_action") or vertex.get("has_webhook")) for vertex in ordered_vertices),
            "digression_targets": len(digression_targets),
            "edges": len(ordered_edges),
            "edges_by_type": {edge_type: sum(edge["type"] == edge_type for edge in ordered_edges) for edge_type in sorted({edge["type"] for edge in ordered_edges})},
            "unresolved_jumps": len(unresolved_jumps),
        },
        "vertices": ordered_vertices,
        "edges": ordered_edges,
        "unresolved_jumps": unresolved_jumps,
        "digression_targets": digression_targets,
    }
    graph["reachability"] = reachability(document, graph)
    if summary_only:
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "summary": {
                "vertex_count": len(graph["vertices"]),
                "edge_count": len(graph["edges"]),
                "unresolved_jumps_count": len(graph["unresolved_jumps"]),
                "digression_targets_count": len(graph["digression_targets"]),
                "unreachable_count": len(graph["reachability"].get("unreachable", [])),
            },
            "unresolved_jumps": graph["unresolved_jumps"],
            "reachability": graph["reachability"],
        }
    return graph


def dot(graph: dict[str, Any]) -> str:
    colors = {"dialog_node": "#DCEEFF", "slot_child": "#FFF1CC", "event_handler": "#FFE2B8", "slot": "#E5D8FF"}
    lines = ["digraph watson_dialog {", "  rankdir=LR;", "  node [shape=box, style=rounded, fontname=Arial];"]
    for vertex in graph.get("vertices", []):
        label = vertex.get("name") or vertex["id"]
        if vertex.get("folder"):
            label = "[folder] " + label
        if vertex.get("condition"):
            label += "\\n" + vertex["condition"]
        escaped = label.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        shape = "folder" if vertex.get("folder") else "box"
        color = "#D7F2DF" if vertex.get("folder") else colors[vertex["kind"]]
        lines.append(f'  "{vertex["id"]}" [label="{escaped}", shape="{shape}", fillcolor="{color}", style="rounded,filled"];')
    for edge in graph.get("edges", []):
        lines.append(f'  "{edge["node"]}" -> "{edge["target"]}" [label="{edge["type"]}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


render_dot = dot


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Gera um grafo direcionado de um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--format", choices=("json", "dot"), default="json")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas contagens consolidadas do grafo")
    args = parser.parse_args()
    try:
        graph = build_graph(load_json(args.input, max_bytes=args.max_input_bytes), summary_only=args.summary_only)
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else dot(graph)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    nx = None
    HAS_NETWORKX = False


def to_networkx(graph_dict: dict[str, Any]) -> Any:
    """Convert dialog graph dictionary to a NetworkX DiGraph for advanced graph algorithms."""
    if not HAS_NETWORKX:
        raise ImportError("networkx is required for to_networkx(). Run: pip install networkx")
    G = nx.DiGraph()
    for v in graph_dict.get("vertices", []):
        G.add_node(v["id"], **v)
    for e in graph_dict.get("edges", []):
        G.add_edge(e["node"], e["target"], edge_type=e.get("type"))
    return G


def find_graph_cycles(graph_dict: dict[str, Any]) -> list[list[str]]:
    """Detect circular jump loops using NetworkX cycle detection."""
    if not HAS_NETWORKX:
        return []
    G = to_networkx(graph_dict)
    return list(nx.simple_cycles(G))

# ------------------------------------------------------------------------------
# Module: validator.py
# ------------------------------------------------------------------------------

"""Validate a Watson Assistant Dialog export using one stable issue contract.

The validator intentionally reports only problems that can be established from
the export itself.  It does not treat SpEL expressions outside the supported
parser subset as invalid Watson syntax.
"""


import sys
from pathlib import Path



import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_CONDITION_LENGTH = 2048
V1_NODE_TYPES = {"standard", "event_handler", "frame", "slot", "response_condition", "folder"}
V1_SLOT_EVENTS = {"focus", "input", "filled", "nomatch"}
SYS_NUMBER_ZERO_HANDLER_PATTERN = re.compile(r"@sys-number\s*(?:\.numeric_value\s*)?(?:==\s*0\b|<=\s*0\b|<\s*1\b)", re.IGNORECASE)
SYS_NUMBER_ZERO_SHORTHAND_PATTERN = re.compile(r"@sys-number\s*:\s*0\b", re.IGNORECASE)
ZERO_IN_PROMPT_RANGE_PATTERN = re.compile(r"(?:^|\D)0\s*(?:a|até|ate|[-–—])\s*[1-9]\d*\b", re.IGNORECASE)
DOCUMENT_INPUT_PATTERN = re.compile(r"\$inputType\s*:\s*document\b", re.IGNORECASE)
SELF_FALSE_ENABLE_PATTERNS = (
    re.compile(r"\$([A-Za-z_][\w-]*)\s*&&\s*\$\1\s*==\s*false\b", re.IGNORECASE),
    re.compile(r"\$([A-Za-z_][\w-]*)\s*==\s*false\s*&&\s*\$\1\b", re.IGNORECASE),
)


def field_for_condition(node: str) -> str:
    if node.startswith("response:"):
        _prefix, parent, response = node.split(":", 2)
        return f"nos[uuid={parent}].respostas[uuid={response}].condicao"
    return "condicao" if not node.startswith("slot:") else "slots[uuid=%s].condicao" % node.removeprefix("slot:")


def iter_json_configurations(document: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, str, Any]]:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            if node.get("json") not in (None, ""):
                yield node_id, "json", node["json"]
            for slot in node.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
                if slot.get("json") not in (None, ""):
                    yield slot_id, "json", slot["json"]
                yield from visit(slot.get("filhos") or [])
            yield from visit(node.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def _context_child_path(parent: str, key: Any) -> str:
    """Return a deterministic, unambiguous path for nested context values."""
    return f"{parent}[{json.dumps(str(key), ensure_ascii=False)}]"


def iter_context_strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Yield every string nested inside a context value with its JSON-like path."""
    if isinstance(value, str):
        yield path, value
        return
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            yield from iter_context_strings(value[key], _context_child_path(path, key))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_context_strings(item, f"{path}[{index}]")


def iter_dialog_contexts(document: dict[str, Any]) -> Iterator[tuple[str, str, Any]]:
    """Yield context payloads from API V1 nodes and normalized legacy JSON.

    The side project's normalized legacy export stores the original Watson node
    JSON as a string in ``node.json`` / ``slot.json``.  Production data uses
    that field for the IBM ``context`` object, while native API V1 exports keep
    the context directly on ``dialog_nodes[]``.
    """
    raw_v1_nodes = document.get("dialog_nodes")
    if isinstance(raw_v1_nodes, list):
        for node_data in raw_v1_nodes:
            if not isinstance(node_data, dict) or node_data.get("dialog_node") in (None, ""):
                continue
            if "context" in node_data:
                yield str(node_data["dialog_node"]), "context", node_data["context"]

    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, str, Any]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            node_id = str(node_data.get("uuid") or "(sem_uuid)")
            raw_json = node_data.get("json")
            if isinstance(raw_json, str) and raw_json:
                try:
                    configuration = json.loads(raw_json)
                except json.JSONDecodeError:
                    configuration = None
                if isinstance(configuration, dict) and "context" in configuration:
                    yield node_id, "json.context", configuration["context"]
            for slot in node_data.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
                raw_slot_json = slot.get("json")
                if isinstance(raw_slot_json, str) and raw_slot_json:
                    try:
                        configuration = json.loads(raw_slot_json)
                    except json.JSONDecodeError:
                        configuration = None
                    if isinstance(configuration, dict) and "context" in configuration:
                        yield slot_id, "json.context", configuration["context"]
                yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def context_spel_issues(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return conservative syntax findings for SpEL embedded in node context."""
    findings: list[dict[str, Any]] = []
    for node, context_field, context_value in iter_dialog_contexts(document):
        if not isinstance(context_value, dict):
            findings.append(issue(
                "syntactic",
                "dialog_context_not_object",
                "error",
                node,
                context_field,
                context_value,
                "O context de um dialog node deve ser um objeto JSON.",
            ))
            continue
        for field, value in iter_context_strings(context_value, context_field):
            if "<?" not in value:
                continue
            for diagnostic in template_syntax_diagnostics(value):
                findings.append(issue(
                    diagnostic["category"],
                    f"context_spel_{diagnostic['code']}",
                    "error",
                    node,
                    field,
                    diagnostic["expression"],
                    diagnostic["message"],
                ))
    return findings


def iter_nodes(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            yield node_data
            for slot in node_data.get("slots") or []:
                if isinstance(slot, dict):
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def iter_legacy_groups_in_source_order(nodes: list[dict[str, Any]], parent: str = "root") -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Yield legacy sibling groups without inventing an order for sequence ties."""
    yield parent, nodes
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("uuid") or "(sem_uuid)")
        children = node.get("filhos") or []
        if children:
            yield from iter_legacy_groups_in_source_order(children, node_id)
        for slot in node.get("slots") or []:
            if not isinstance(slot, dict):
                continue
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            slot_children = slot.get("filhos") or []
            yield slot_id, slot_children
            for child in slot_children:
                if not isinstance(child, dict):
                    continue
                nested = child.get("filhos") or []
                if nested:
                    yield from iter_legacy_groups_in_source_order(nested, str(child.get("uuid") or "(sem_uuid)"))


def iter_nodes_with_activity(document: dict[str, Any], condition_dormant: set[str] | None = None) -> Iterator[tuple[dict[str, Any], bool]]:
    """Yield legacy nodes plus whether their source path is dormant.

    `condition_dormant` comes from the already-computed condition analysis so
    digression checks can honor explicit-false/unsatisfiable ancestors without
    parsing every condition a second time.
    """
    condition_dormant = condition_dormant or set()

    def visit(nodes: list[dict[str, Any]], ancestor_dormant: bool = False) -> Iterator[tuple[dict[str, Any], bool]]:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("uuid") or "(sem_uuid)")
            dormant = (
                ancestor_dormant
                or node_id in condition_dormant
                or str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}
            )
            yield node, dormant
            for slot in node.get("slots") or []:
                if isinstance(slot, dict):
                    yield from visit(slot.get("filhos") or [], dormant)
            yield from visit(node.get("filhos") or [], dormant)

    yield from visit(document.get("nos") or [])


def is_non_operational_status(node: dict[str, Any]) -> bool:
    """Project-local status evidence used only to qualify active-flow claims."""
    return str(node.get("status") or "").strip().upper() in {"INATIVO", "REVISAO"}


def iter_response_owners(document: dict[str, Any]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    def visit(nodes: list[dict[str, Any]]) -> Iterator[tuple[str, list[dict[str, Any]]]]:
        for node_data in nodes:
            if not isinstance(node_data, dict):
                continue
            yield str(node_data.get("uuid") or "(sem_uuid)"), node_data.get("respostas") or []
            for slot in node_data.get("slots") or []:
                if isinstance(slot, dict):
                    yield f"slot:{slot.get('uuid') or '(sem_uuid)'}", slot.get("respostas") or []
                    yield from visit(slot.get("filhos") or [])
            yield from visit(node_data.get("filhos") or [])

    yield from visit(document.get("nos") or [])


def validate_v1_structure(document: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    """Validate the documented graph constraints when an API V1 payload is used."""
    raw_nodes = document.get("dialog_nodes")
    if not isinstance(raw_nodes, list):
        return
    nodes = [item for item in raw_nodes if isinstance(item, dict) and item.get("dialog_node") is not None]
    by_id: dict[str, dict[str, Any]] = {}
    for node_data in nodes:
        node_id = str(node_data["dialog_node"])
        if node_id in by_id:
            issues.append(issue("semantic", "duplicate_dialog_node_id", "error", node_id, "dialog_node", node_id, f"O ID {node_id} é duplicado na API V1."))
        else:
            by_id[node_id] = node_data

    parents = {node_id: str(node_data["parent"]) for node_id, node_data in by_id.items() if node_data.get("parent") not in (None, "")}
    children: dict[str | None, list[str]] = defaultdict(list)
    for node_id, node_data in by_id.items():
        parent = node_data.get("parent")
        parent_id = str(parent) if parent not in (None, "") else None
        children[parent_id].append(node_id)
        if parent_id and parent_id not in by_id:
            issues.append(issue("semantic", "unresolved_parent", "error", node_id, "parent", parent, f"O parent {parent_id} não existe."))
        if parent_id == node_id:
            issues.append(issue("semantic", "self_parent", "error", node_id, "parent", parent, "Um nó não pode ser pai de si mesmo."))
        ancestor = parent_id
        seen: set[str] = set()
        while ancestor in parents and ancestor not in seen:
            if ancestor == node_id:
                issues.append(issue("semantic", "parent_is_descendant", "error", node_id, "parent", parent, "O parent não pode ser descendente do nó."))
                break
            seen.add(ancestor)
            ancestor = parents[ancestor]

    previous_owners: dict[str, list[str]] = defaultdict(list)
    for node_id, node_data in by_id.items():
        node_type = str(node_data.get("type") or "standard")
        if node_type not in V1_NODE_TYPES:
            issues.append(issue("syntactic", "unknown_dialog_node_type", "error", node_id, "type", node_type, f"Tipo de nó V1 não suportado: {node_type}."))
        previous = node_data.get("previous_sibling")
        if previous not in (None, ""):
            previous_id = str(previous)
            previous_owners[previous_id].append(node_id)
            if previous_id not in by_id:
                issues.append(issue("semantic", "unresolved_previous_sibling", "error", node_id, "previous_sibling", previous, f"O irmão anterior {previous_id} não existe."))
            elif previous_id == node_id:
                issues.append(issue("semantic", "self_previous_sibling", "error", node_id, "previous_sibling", previous, "Um nó não pode ser irmão anterior de si mesmo."))
            elif by_id[previous_id].get("parent") != node_data.get("parent"):
                issues.append(issue("semantic", "cross_parent_previous_sibling", "error", node_id, "previous_sibling", previous, "O irmão anterior precisa ter o mesmo parent."))
        if node_type == "slot" and str(node_data.get("parent") or "") in by_id and str(by_id[str(node_data["parent"])].get("type") or "standard") != "frame":
            issues.append(issue("semantic", "slot_parent_not_frame", "error", node_id, "parent", node_data.get("parent"), "Um slot precisa ser filho de um frame."))
        if node_type == "response_condition" and str(node_data.get("parent") or "") in by_id and str(by_id[str(node_data["parent"])].get("type") or "standard") not in {"standard", "frame"}:
            issues.append(issue("semantic", "response_condition_parent_invalid", "error", node_id, "parent", node_data.get("parent"), "Uma response_condition precisa ser filha de standard ou frame."))
        if node_type in {"event_handler", "response_condition"} and children.get(node_id):
            issues.append(issue("semantic", "leaf_node_has_children", "error", node_id, "parent", children[node_id], f"Um nó {node_type} não pode ter filhos."))
        if node_type == "event_handler":
            event = str(node_data.get("event_name") or "")
            parent_type = str(by_id.get(str(node_data.get("parent") or ""), {}).get("type") or "standard")
            if event not in V1_SLOT_EVENTS | {"generic"}:
                issues.append(issue("syntactic", "invalid_event_handler_name", "error", node_id, "event_name", node_data.get("event_name"), "event_name não é permitido para event_handler."))
            elif event == "generic" and parent_type not in {"slot", "frame"}:
                issues.append(issue("semantic", "generic_handler_parent_invalid", "error", node_id, "parent", node_data.get("parent"), "Handler generic precisa pertencer a slot ou frame."))
            elif event in V1_SLOT_EVENTS and parent_type != "slot":
                issues.append(issue("semantic", "slot_handler_parent_invalid", "error", node_id, "parent", node_data.get("parent"), f"Handler {event} precisa pertencer a slot."))

    for previous, owners in previous_owners.items():
        if len(owners) > 1:
            for node_id in sorted(owners):
                issues.append(issue("semantic", "previous_sibling_has_multiple_successors", "error", node_id, "previous_sibling", previous, f"Mais de um nó aponta para o irmão anterior {previous}."))
    for parent, sibling_ids in children.items():
        first = [node_id for node_id in sibling_ids if by_id[node_id].get("previous_sibling") in (None, "")]
        if len(first) > 1:
            for node_id in sorted(first):
                issues.append(issue("semantic", "multiple_first_siblings", "error", node_id, "previous_sibling", None, f"O grupo de irmãos de {parent or 'root'} tem mais de um primeiro nó."))
    for node_id, node_data in by_id.items():
        if str(node_data.get("type") or "standard") == "frame" and not any(str(by_id[child].get("type") or "standard") == "slot" for child in children.get(node_id, [])):
            issues.append(issue("semantic", "frame_without_slot", "error", node_id, "type", "frame", "Um frame precisa ter pelo menos um filho slot."))

        # V1 Jump targets
        next_step = node_data.get("next_step")
        if isinstance(next_step, dict) and next_step.get("behavior") == "jump_to":
            target = next_step.get("dialog_node")
            if target not in (None, "") and str(target) not in set(by_id.keys()) | {"root"}:
                issues.append(issue("semantic", "unresolved_jump_target", "error", node_id, "next_step.dialog_node", target, f"O jump aponta para o nó inexistente {target}."))

        # V1 Disabled conditions
        cond = node_data.get("conditions")
        if cond is not None and str(cond).strip().lower() == "false":
            issues.append(issue("info", "disabled_condition_false", "info", node_id, "conditions", cond, "A condição contém `false` explícito e mantém o ramo deliberadamente desabilitado no fluxo normal."))


def context_variables(document: dict[str, Any]) -> dict[str, str]:
    """Map context variable UUIDs to names, ignoring malformed definitions."""
    return {
        str(item["uuid"]): str(item["variavelContexto"]).lstrip("$")
        for item in document.get("variaveisContexto") or []
        if item.get("uuid") and item.get("variavelContexto")
    }


def descendant_conditions(nodes: list[dict[str, Any]]) -> Iterator[str]:
    """Yield descendant node conditions without assigning runtime semantics."""
    for node in nodes:
        condition = node.get("condicao")
        if condition not in (None, ""):
            yield str(condition)
        yield from descendant_conditions(node.get("filhos") or [])


def response_text(slot: dict[str, Any]) -> str:
    """Return response text only for local semantic diagnostics."""
    return " ".join(
        str(response.get("textoResposta") or "")
        for response in slot.get("respostas") or []
        if response.get("textoResposta") not in (None, "")
    )


def slot_enable_is_self_false_contradiction(condition: str) -> bool:
    """Detect the audited `$x && $x == false` contradiction conservatively."""
    normalized = re.sub(r"\s+", " ", condition.strip())
    return any(pattern.search(normalized) for pattern in SELF_FALSE_ENABLE_PATTERNS)


def slot_number_diagnostics(slot: dict[str, Any], slot_id: str) -> list[dict[str, Any]]:
    """Return high-confidence number-capture diagnostics for one active slot.

    This intentionally does *not* warn on every bare `@sys-number`.  Positive
    selectors and non-zero domains are common.  We report only contradictions
    established by the slot's own children/prompt.
    """
    condition = str(slot.get("condicao") or "")
    if "@sys-number" not in condition or "@sys-number >= 0" in condition:
        return []

    children = list(descendant_conditions(slot.get("filhos") or []))
    findings: list[dict[str, Any]] = []
    if any(SYS_NUMBER_ZERO_HANDLER_PATTERN.search(child) for child in children):
        findings.append(issue(
            "semantic",
            "sys_number_zero_handler_unreachable",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O slot não captura zero, mas possui handler descendente para == 0, <= 0 ou < 1; esse tratamento de zero não é alcançável pela captura atual.",
        ))

    prompt = response_text(slot)
    if (
        ZERO_IN_PROMPT_RANGE_PATTERN.search(prompt)
        and any(SYS_NUMBER_ZERO_SHORTHAND_PATTERN.search(child) for child in children)
    ):
        findings.append(issue(
            "semantic",
            "sys_number_zero_valid_but_not_captured",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O próprio prompt inclui zero no domínio e existe branch @sys-number:0, mas a condição de captura não aceita zero.",
        ))

    if any(DOCUMENT_INPUT_PATTERN.search(child) for child in children):
        findings.append(issue(
            "semantic",
            "slot_capture_type_mismatch_document",
            "warning",
            slot_id,
            "condicao",
            condition,
            "O slot captura @sys-number, mas sua lógica descendente espera $inputType:document; a condição de captura não corresponde ao tipo de entrada processado.",
        ))
    return findings


def issue(category: str, code: str, severity: str, node: str, field: str, value: Any, message: str) -> dict[str, Any]:
    return {
        "category": category,
        "code": code,
        "severity": severity,
        "node": node,
        "field": field,
        "value": value,
        "message": message,
    }


def validate(document: dict[str, Any], check_variables: bool = False, summary_only: bool = False, max_issues: int | None = None) -> dict[str, Any]:
    """Return deterministic validation issues for the complete dialog export."""
    issues: list[dict[str, Any]] = []

    condition_categories = {
        "invalid_spel_entity_shorthand_member": "syntactic",
        "invalid_spel_entity_call": "syntactic",
    }
    condition_report = analyze_conditions(document, check_variables=check_variables)
    condition_dormant = {
        finding["node"] for finding in condition_report["issues"]
        if finding["type"] in {"disabled_condition_false", "unsatisfiable_condition"}
        and not finding["node"].startswith(("slot:", "response:"))
    }
    for finding in condition_report["issues"]:
        issues.append(issue(
            condition_categories.get(finding["type"], "semantic"),
            finding["type"],
            finding["severity"],
            finding["node"],
            field_for_condition(finding["node"]),
            finding["condition"],
            finding["message"],
        ))

    for node, _kind, condition in iter_conditions(document):
        if len(condition) > MAX_CONDITION_LENGTH:
            issues.append(issue("syntactic", "condition_too_long", "error", node, field_for_condition(node), condition, f"A condição possui {len(condition)} caracteres; o limite do Watson é {MAX_CONDITION_LENGTH}."))
        for diagnostic in syntax_diagnostics(condition):
            issues.append(issue(
                diagnostic["category"],
                diagnostic["code"],
                "error",
                node,
                field_for_condition(node),
                condition,
                diagnostic["message"],
            ))

    variable_names = {
        name for name in context_variables(document).values()
        if re.fullmatch(r"[A-Za-z_][\w-]*", name)
    }
    for node, _kind, condition in iter_conditions(document):
        for variable in sorted(name for name in variable_names if "-" in name):
            if re.search(rf"\${re.escape(variable)}(?![\w-])", condition):
                issues.append(issue("semantic", "ambiguous_context_variable_name", "warning", node, field_for_condition(node), condition, f"A variável ${variable} contém hífen; use $({variable}) ou context['{variable}']."))

    for node, _kind, condition in iter_conditions(document):
        if re.search(r"@[\w-]+:\([^)]*\([^)]*\)", condition):
            issues.append(issue("syntactic", "entity_shorthand_value_contains_closing_parenthesis", "error", node, field_for_condition(node), condition, "O shorthand @entidade:(valor) não pode ser usado quando o valor contém )."))

    for node, field, value in iter_json_configurations(document):
        if not isinstance(value, str):
            issues.append(issue("syntactic", "json_configuration_not_string", "error", node, field, value, "A configuração JSON deve ser uma string JSON."))
            continue
        try:
            json.loads(value)
        except json.JSONDecodeError as error:
            issues.append(issue("syntactic", "invalid_json_configuration", "error", node, field, value, f"Configuração JSON inválida: {error.msg}."))

    issues.extend(context_spel_issues(document))

    for owner, responses in iter_response_owners(document):
        blocks: dict[tuple[Any, Any], set[Any]] = defaultdict(set)
        for response in responses:
            if response.get("idTipoComponente") is not None:
                blocks[(response.get("idTipoResposta"), response.get("sequenciaBloco"))].add(response["idTipoComponente"])
        for block, component_types in sorted(blocks.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))):
            if len(component_types) > 5:
                issues.append(issue("semantic", "too_many_response_types", "error", owner, "respostas", sorted(component_types, key=str), f"A resposta condicional {block!r} possui {len(component_types)} tipos; o limite do Watson é 5."))

    for parent, siblings in iter_legacy_groups_in_source_order(document.get("nos") or []):
        seen_sequences: dict[Any, list[str]] = defaultdict(list)
        for index, node_data in enumerate(siblings):
            if not isinstance(node_data, dict):
                continue
            if node_data.get("uuid") in (None, ""):
                issues.append(issue("syntactic", "missing_node_uuid", "error", "(sem_uuid)", "uuid", None, "O nó legado não possui o campo uuid obrigatório."))
            node_id = str(node_data.get("uuid") or "(sem_uuid)")
            sequence = node_data.get("sequencia")
            if sequence is not None:
                seen_sequences[sequence].append(node_id)
            # `anything_else` is an ordering rule.  For the normalized legacy
            # export the physical sibling array is the only source ordering we
            # can inspect without inventing a tie-break for duplicate/None
            # sequence values.
            if (
                not is_non_operational_status(node_data)
                and str(node_data.get("condicao") or "").strip().lower() == "anything_else"
                and index != len(siblings) - 1
            ):
                issues.append(issue("semantic", "anything_else_not_last_sibling", "warning", node_id, "condicao", node_data.get("condicao"), f"anything_else deve ser o último irmão do grupo {parent}."))
        for sequence, node_ids in seen_sequences.items():
            if len(node_ids) > 1:
                ordered_ids = sorted(node_ids)
                issues.append(issue(
                    "provenance",
                    "legacy_order_ambiguous",
                    "info",
                    parent,
                    "sequencia",
                    {"sequence": sequence, "nodes": ordered_ids},
                    f"A sequência legacy {sequence!r} é compartilhada por {len(ordered_ids)} irmãos; a ordem relativa não pode ser inferida com segurança.",
                ))

    roots = document.get("nos") or []
    if not any(isinstance(node_data, dict) and str(node_data.get("condicao") or "").strip().lower() == "anything_else" for node_data in roots):
        issues.append(issue("semantic", "missing_root_anything_else", "warning", "root", "nos", None, "Não há um nó raiz com a condição anything_else."))

    variable_by_uuid = context_variables(document)
    for frame, inactive_path in iter_nodes_with_activity(document, condition_dormant):
        slots = frame.get("slots") or []
        names = [variable_by_uuid.get(str(slot.get("uuidVariavelContexto"))) for slot in slots if isinstance(slot, dict)]
        for index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                continue
            if slot.get("uuid") in (None, ""):
                issues.append(issue("syntactic", "missing_slot_uuid", "error", "(sem_uuid)", "uuid", None, "O slot não possui o campo uuid obrigatório."))
            condition = str(slot.get("condicao") or "")
            slot_id = f"slot:{slot.get('uuid') or '(sem_uuid)'}"
            if not inactive_path:
                issues.extend(slot_number_diagnostics(slot, slot_id))
                enable_condition = str(slot.get("condicaoSlots") or "").strip()
                if enable_condition and slot_enable_is_self_false_contradiction(enable_condition):
                    issues.append(issue(
                        "semantic",
                        "unsatisfiable_slot_enable_condition",
                        "warning",
                        slot_id,
                        "condicaoSlots",
                        enable_condition,
                        "A condição exige que a mesma variável seja simultaneamente truthy e igual a false; esse slot não pode ser habilitado por essa expressão.",
                    ))
            current_name = names[index] if index < len(names) else None
            for later_name in sorted(name for name in names[index + 1:] if name and name != current_name and f"${name}" in condition):
                issues.append(issue("semantic", "slot_depends_on_later_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${later_name}, preenchida por um slot posterior."))
            for prior_index, prior_name in enumerate(names[:index]):
                if prior_name and f"${prior_name}" in condition and prior_index < len(slots) and isinstance(slots[prior_index], dict) and not slots[prior_index].get("indicadorObrigatorio"):
                    issues.append(issue("semantic", "slot_depends_on_optional_slot", "warning", slot_id, "condicao", condition, f"A condição depende de ${prior_name}, preenchida por um slot anterior opcional."))

    node_ids = {str(node_data.get("uuid")) for node_data in iter_nodes(document) if isinstance(node_data, dict) and node_data.get("uuid") not in (None, "")}
    for node_data, inactive_path in iter_nodes_with_activity(document, condition_dormant):
        if not isinstance(node_data, dict):
            continue
        node_id = str(node_data.get("uuid") or "(sem_uuid)")
        target = node_data.get("uuidEnviarPara")
        if target not in (None, "") and str(target) not in node_ids | {"root"}:
            issues.append(issue("semantic", "unresolved_jump_target", "error", node_id, "uuidEnviarPara", target, f"O jump aponta para o UUID inexistente {target}."))
        if inactive_path or not node_data.get("inDigressionOut"):
            continue
        if target not in (None, "") or str(node_data.get("jumpSelector") or "") == "move_on":
            issues.append(issue("semantic", "digression_blocked_by_transition", "info", node_id, "inDigressionOut", node_data.get("inDigressionOut"), "O Watson não permite digressão de saída quando o nó ativo força jump ou Skip user input."))
        active_forcing_children = [
            child for child in node_data.get("filhos") or []
            if isinstance(child, dict)
            and not is_non_operational_status(child)
            and str(child.get("condicao") or "").strip().lower() in {"true", "anything_else"}
        ]
        if active_forcing_children:
            blocker_ids = ", ".join(sorted(str(child.get("uuid") or "(sem_uuid)") for child in active_forcing_children))
            all_escapes = all(
                any(keyword in str(child.get("nome") or "").lower() or keyword in str(child.get("condicao") or "").lower() for keyword in ("escape", "sair", "voltar"))
                for child in active_forcing_children
            )
            severity = "info" if all_escapes else "warning"
            issues.append(issue("semantic", "digression_blocked_by_forcing_child", severity, node_id, "inDigressionOut", node_data.get("inDigressionOut"), f"O Watson não permite digressão de saída com filho ativo true/anything_else; blockers: {blocker_ids}."))
    for owner, responses in iter_response_owners(document):
        for response in responses:
            target = response.get("uuidEnviarPara") or response.get("dialog_node")
            if target not in (None, "") and str(target) not in node_ids | {"root"}:
                issues.append(issue("semantic", "unresolved_response_jump_target", "error", owner, "respostas.uuidEnviarPara", target, f"O jump de resposta aponta para o UUID inexistente {target}."))

    validate_v1_structure(document, issues)

    issues.sort(key=lambda item: (item["node"], item["field"], item["code"], json.dumps(item["value"], ensure_ascii=False, sort_keys=True)))
    by_category = {category: sum(item["category"] == category for item in issues) for category in sorted({item["category"] for item in issues})}
    by_code = {code: sum(item["code"] == code for item in issues) for code in sorted({item["code"] for item in issues})}
    by_severity = {severity: sum(item["severity"] == severity for item in issues) for severity in sorted({item["severity"] for item in issues})}

    total_issues = len(issues)
    reported_issues = [] if summary_only else (issues[:max_issues] if max_issues is not None and max_issues >= 0 else issues)

    return {
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "issues": total_issues,
            "issues_by_category": by_category,
            "issues_by_code": by_code,
            "issues_by_severity": by_severity,
        },
        "issues": reported_issues,
    }


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Valida estrutural e semanticamente um export Watson Assistant Dialog.")
    parser.add_argument("input", type=Path, help="export JSON do Watson Assistant")
    parser.add_argument("--output", type=Path, help="arquivo de saída; padrão: stdout")
    parser.add_argument("--check-variables", action="store_true", help="também valida variáveis fora de variaveisContexto")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado das contagens de issues")
    parser.add_argument("--max-issues", type=int, default=None, help="limite máximo de issues detalhadas no relatório")
    args = parser.parse_args()
    try:
        report = validate(
            load_json(args.input, max_bytes=args.max_input_bytes),
            check_variables=args.check_variables,
            summary_only=args.summary_only,
            max_issues=args.max_issues,
        )
    except (ValueError, KeyError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["summary"]["issues"] else 0



# ------------------------------------------------------------------------------
# Module: diff_engine.py
# ------------------------------------------------------------------------------

"""Compare two Watson Assistant Dialog exports semantically.

The exports store their main collections as arrays of objects with UUIDs.  This
tool matches those objects by UUID, so a changed ordering in the JSON does not
appear as a change in the report.
"""


import sys
from pathlib import Path



import argparse
import concurrent.futures
import json
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    orjson = None
    HAS_ORJSON = False


DEFAULT_IGNORED_FIELDS = {"dataCriacao", "dataModificacao"}
DEFAULT_EXTERNAL_THRESHOLD_BYTES = 16 * 1024 * 1024
DEFAULT_DOM_MEMORY_MULTIPLIER = 10.0
DEFAULT_DOM_MEMORY_FRACTION = 0.30

def configure_utf8_output() -> None:
    """Ensure standard output and error streams handle UTF-8 cleanly on all platforms."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_json(path: Path, max_bytes: int | None = None) -> dict[str, Any]:
    max_bytes = resolve_max_input_bytes(max_bytes)
    if max_bytes > 0 and path.exists():
        file_size = path.stat().st_size
        if file_size > max_bytes:
            raise ValueError(
                f"Arquivo {path} ({file_size} bytes) excede o limite configurado de {max_bytes} bytes. "
                f"Use --max-input-bytes para aumentar o limite se necessário."
            )
    try:
        if HAS_ORJSON:
            document = orjson.loads(path.read_bytes())
        else:
            with path.open(encoding="utf-8") as file:
                document = json.load(file)
    except (OSError, ValueError, json.JSONDecodeError if not HAS_ORJSON else Exception) as error:
        raise ValueError(f"Não foi possível ler {path}: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{path} deve conter um objeto JSON na raiz.")
    return document


def item_label(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    for field in ("nome", "textoTema", "textoAcao", "textoObjeto", "variavelContexto"):
        if item.get(field):
            return str(item[field])
    return item.get("uuid", "(sem nome)")


def keyed_by_uuid(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list) or not all(isinstance(item, dict) and "uuid" in item for item in value):
        return None
    return {str(item["uuid"]): item for item in value}


def path_join(base: str, part: str) -> str:
    return f"{base}.{part}" if base else part


def json_value(value: str) -> Any | None:
    """Decode JSON stored as text, used by dialog nodes' ``json`` field."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, (dict, list)) else None


def path_item(path: str, index: int) -> str:
    return f"{path}[{index}]"


def stable_item(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_list(current: list[Any], candidate: list[Any], path: str, ignored_fields: set[str]) -> list[dict[str, Any]]:
    """Compare an unkeyed list item-by-item, preserving order when it matters."""
    # Tags are labels, not an ordered dialog flow. Their order is irrelevant.
    if path.rsplit(".", 1)[-1] == "tags":
        current_values = sorted(stable_item(item) for item in current)
        candidate_values = sorted(stable_item(item) for item in candidate)
        matcher = SequenceMatcher(a=current_values, b=candidate_values, autojunk=False)
        decode = json.loads
        changes: list[dict[str, Any]] = []
        for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
            if operation in ("delete", "replace"):
                changes.extend({"path": path, "kind": "removed", "before": decode(item), "after": None} for item in current_values[a_start:a_end])
            if operation in ("insert", "replace"):
                changes.extend({"path": path, "kind": "added", "before": None, "after": decode(item)} for item in candidate_values[b_start:b_end])
        return changes

    current_values = [stable_item(item) for item in current]
    candidate_values = [stable_item(item) for item in candidate]
    matcher = SequenceMatcher(a=current_values, b=candidate_values, autojunk=False)
    changes = []
    for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        if operation == "replace":
            shared = min(a_end - a_start, b_end - b_start)
            for offset in range(shared):
                changes.extend(find_differences(current[a_start + offset], candidate[b_start + offset], path_item(path, a_start + offset), ignored_fields))
            a_start += shared
            b_start += shared
        if operation in ("delete", "replace"):
            changes.extend({"path": path_item(path, index), "kind": "removed", "before": current[index], "after": None} for index in range(a_start, a_end))
        if operation in ("insert", "replace"):
            changes.extend({"path": path_item(path, index), "kind": "added", "before": None, "after": candidate[index]} for index in range(b_start, b_end))
    return changes


def find_differences(current: Any, candidate: Any, path: str, ignored_fields: set[str]) -> list[dict[str, Any]]:
    """Return atomic additions, removals and substitutions below *path*."""
    if isinstance(current, dict) and isinstance(candidate, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(set(current) | set(candidate)):
            if key in ignored_fields:
                continue
            child_path = path_join(path, key)
            if key not in current:
                changes.append({"path": child_path, "kind": "added", "before": None, "after": candidate[key]})
            elif key not in candidate:
                changes.append({"path": child_path, "kind": "removed", "before": current[key], "after": None})
            else:
                changes.extend(find_differences(current[key], candidate[key], child_path, ignored_fields))
        return changes

    # Some node configuration, including media components, is itself JSON
    # serialized inside a string field named ``json``. Compare its structure.
    if path.rsplit(".", 1)[-1] == "json" and isinstance(current, str) and isinstance(candidate, str):
        current_json, candidate_json = json_value(current), json_value(candidate)
        if current_json is not None and candidate_json is not None:
            return find_differences(current_json, candidate_json, path, ignored_fields)

    current_by_uuid, candidate_by_uuid = keyed_by_uuid(current), keyed_by_uuid(candidate)
    if current_by_uuid is not None and candidate_by_uuid is not None:
        changes = []
        for uuid in sorted(set(current_by_uuid) | set(candidate_by_uuid)):
            child_path = f"{path}[uuid={uuid}]"
            if uuid not in current_by_uuid:
                changes.append({"path": child_path, "kind": "added", "before": None, "after": candidate_by_uuid[uuid]})
            elif uuid not in candidate_by_uuid:
                changes.append({"path": child_path, "kind": "removed", "before": current_by_uuid[uuid], "after": None})
            else:
                changes.extend(find_differences(current_by_uuid[uuid], candidate_by_uuid[uuid], child_path, ignored_fields))
        return changes

    if isinstance(current, list) and isinstance(candidate, list):
        return compare_list(current, candidate, path, ignored_fields)

    if current != candidate:
        return [{"path": path or "$", "kind": "changed", "before": current, "after": candidate}]
    return []


def summarize(current: dict[str, Any], candidate: dict[str, Any], ignored_fields: set[str], summary_only: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "ignored_fields": sorted(ignored_fields),
        "summary": {"added": 0, "removed": 0, "changed": 0},
        "collections": {},
        "changes": [],
    }
    for key in sorted(set(current) | set(candidate)):
        if key in ignored_fields:
            continue
        before, after = current.get(key), candidate.get(key)
        before_map, after_map = keyed_by_uuid(before), keyed_by_uuid(after)
        if before_map is None or after_map is None:
            changes = find_differences(before, after, key, ignored_fields)
            if changes:
                result["collections"][key] = {"added": [], "removed": [], "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}]}
                result["summary"]["changed"] += len(changes)
                if not summary_only:
                    result["changes"].extend({"collection": key, "uuid": None, "label": key, **c} for c in changes)
            continue

        collection = {"added": [], "removed": [], "changed": []}
        for uuid in sorted(set(before_map) | set(after_map)):
            if uuid not in before_map:
                collection["added"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "value": after_map[uuid] if not summary_only else None})
            elif uuid not in after_map:
                collection["removed"].append({"uuid": uuid, "label": item_label(before_map[uuid]), "value": before_map[uuid] if not summary_only else None})
            else:
                changes = find_differences(before_map[uuid], after_map[uuid], "", ignored_fields)
                if changes:
                    collection["changed"].append({"uuid": uuid, "label": item_label(after_map[uuid]), "changes": changes if not summary_only else []})
        if any(collection.values()):
            result["collections"][key] = collection
            result["summary"]["added"] += len(collection["added"])
            result["summary"]["removed"] += len(collection["removed"])
            result["summary"]["changed"] += len(collection["changed"])

    if not summary_only:
        for collection, data in result["collections"].items():
            for entry in data["added"]:
                result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "added", "before": None, "after": entry["value"]})
            for entry in data["removed"]:
                result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], "path": "$", "kind": "removed", "before": entry["value"], "after": None})
            for entry in data["changed"]:
                for change in entry["changes"]:
                    result["changes"].append({"collection": collection, "uuid": entry["uuid"], "label": entry["label"], **change})
        result["summary"] = {"added": 0, "removed": 0, "changed": 0}
        for change in result["changes"]:
            result["summary"][change["kind"] if change["kind"] in ("added", "removed") else "changed"] += 1
    return result


diff_dialogs = summarize


class ExternalDiffUnsupported(ValueError):
    """Raised when the source-backed engine cannot preserve incumbent semantics."""


def _empty_report(ignored_fields: set[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ignored_fields": sorted(ignored_fields),
        "summary": {"added": 0, "removed": 0, "changed": 0},
        "collections": {},
        "changes": [],
    }


def _prefix_changes(changes: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    if not prefix:
        return changes
    prefixed: list[dict[str, Any]] = []
    for change in changes:
        copied = dict(change)
        path = str(copied.get("path") or "$")
        copied["path"] = prefix if path == "$" else f"{prefix}.{path}"
        prefixed.append(copied)
    return prefixed


def _diff_payload_task(task: tuple[int, str, bytes, bytes, str, tuple[str, ...]]) -> tuple[int, str, list[dict[str, Any]]]:
    """Worker-safe record diff used by the external engine.

    Workers receive only bounded record-local JSON bytes, never an mmap or a
    full export.  This keeps process isolation portable to Windows spawn while
    preserving the parent process' external-memory contract.
    """
    ordinal, root_id, current_bytes, candidate_bytes, prefix, ignored = task
    current = json.loads(current_bytes)
    candidate = json.loads(candidate_bytes)
    changes = find_differences(current, candidate, "", set(ignored))
    return ordinal, root_id, _prefix_changes(changes, prefix)


def _run_payload_tasks(
    tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]],
    jobs: int,
) -> list[tuple[int, str, list[dict[str, Any]]]]:
    if not tasks:
        return []
    if jobs <= 1 or len(tasks) == 1:
        return [_diff_payload_task(task) for task in tasks]

    # Bound queued work to avoid turning sparse changed-node materialization
    # into a second memory spike on large exports.
    results: list[tuple[int, str, list[dict[str, Any]]]] = []
    iterator = iter(tasks)
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as executor:
        pending: dict[concurrent.futures.Future[tuple[int, str, list[dict[str, Any]]]], None] = {}
        for _ in range(min(len(tasks), jobs * 2)):
            try:
                pending[executor.submit(_diff_payload_task, next(iterator))] = None
            except StopIteration:
                break
        while pending:
            done, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                results.append(future.result())
                try:
                    pending[executor.submit(_diff_payload_task, next(iterator))] = None
                except StopIteration:
                    pass
    return sorted(results, key=lambda result: result[0])


def _has_covering_ancestor(index: Any, record_id: str, covered: set[str]) -> bool:
    return any(ancestor in covered for ancestor in index.ancestors(record_id))


def _decode_bytes(value: bytes) -> Any:
    return json.loads(value)


def _ordered_sequence_tokens(
    current_index: Any,
    current_refs: list[Any],
    candidate_index: Any,
    candidate_refs: list[Any],
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Build exact-equality tokens for incumbent ``SequenceMatcher`` parity.

    Each ordered-item ref carries a SHA-256 of the incumbent-compatible stable
    JSON serialization.  A digest that appears only once across both sequences
    cannot participate in equality, so no canonical bytes need to stay in
    memory.  Repeated digests are verified against the exact canonical bytes
    and assigned an equivalence-class integer.  This makes a cryptographic
    collision a detected condition rather than a silent semantic shortcut.
    """
    counts: dict[str, int] = {}
    for ref in [*current_refs, *candidate_refs]:
        counts[ref.stable_digest] = counts.get(ref.stable_digest, 0) + 1

    variants: dict[str, dict[bytes, int]] = {}

    def tokens(index: Any, refs: list[Any]) -> list[tuple[str, str, int]]:
        result: list[tuple[str, str, int]] = []
        for ref in refs:
            digest = ref.stable_digest
            if counts[digest] == 1:
                result.append(("unique", digest, 0))
                continue
            canonical = index.ordered_item_stable_bytes(ref)
            group = variants.setdefault(digest, {})
            variant = group.get(canonical)
            if variant is None:
                variant = len(group)
                group[canonical] = variant
            result.append(("exact", digest, variant))
        return result

    return tokens(current_index, current_refs), tokens(candidate_index, candidate_refs)


def _external_ordered_object_array(
    key: str,
    current_index: Any,
    candidate_index: Any,
    current_refs: list[Any],
    candidate_refs: list[Any],
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """External-memory equivalent of :func:`compare_list` for object arrays.

    This intentionally preserves the incumbent's *order-sensitive* semantics.
    In particular V1 ``dialog_nodes`` is not reinterpreted as an identity map
    by ``dialog_node`` in this parity mode.
    """
    current_tokens, candidate_tokens = _ordered_sequence_tokens(
        current_index, current_refs, candidate_index, candidate_refs
    )
    matcher = SequenceMatcher(a=current_tokens, b=candidate_tokens, autojunk=False)

    events: list[tuple[int, str, int, int | None]] = []
    pair_tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]] = []
    event_ordinal = 0
    pair_ordinal = 0
    for operation, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        if operation == "replace":
            shared = min(a_end - a_start, b_end - b_start)
            for offset in range(shared):
                ai, bi = a_start + offset, b_start + offset
                events.append((event_ordinal, "pair", pair_ordinal, None))
                pair_tasks.append(
                    (
                        pair_ordinal,
                        key,
                        current_index.ordered_item_bytes(current_refs[ai]),
                        candidate_index.ordered_item_bytes(candidate_refs[bi]),
                        path_item(key, ai),
                        tuple(sorted(ignored_fields)),
                    )
                )
                event_ordinal += 1
                pair_ordinal += 1
            a_start += shared
            b_start += shared
        if operation in ("delete", "replace"):
            for ai in range(a_start, a_end):
                events.append((event_ordinal, "delete", ai, None))
                event_ordinal += 1
        if operation in ("insert", "replace"):
            for bi in range(b_start, b_end):
                events.append((event_ordinal, "insert", bi, None))
                event_ordinal += 1

    budget = ResourceBudget.detect()
    worker_count = resolve_jobs(jobs, len(pair_tasks), budget) if pair_tasks else 1
    pair_results = {ordinal: changes for ordinal, _, changes in _run_payload_tasks(pair_tasks, worker_count)}

    changes: list[dict[str, Any]] = []
    for _, event_type, index_value, _ in events:
        if event_type == "pair":
            changes.extend(pair_results.get(index_value, []))
        elif event_type == "delete":
            before = None if summary_only else _decode_bytes(current_index.ordered_item_bytes(current_refs[index_value]))
            changes.append({"path": path_item(key, index_value), "kind": "removed", "before": before, "after": None})
        else:
            after = None if summary_only else _decode_bytes(candidate_index.ordered_item_bytes(candidate_refs[index_value]))
            changes.append({"path": path_item(key, index_value), "kind": "added", "before": None, "after": after})

    if not changes:
        return None
    return {
        "added": [],
        "removed": [],
        "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}],
        "_summary_atomic_changed": len(changes),
        "_preflatten_changes": [] if summary_only else list(changes),
    }


def _external_generic_collection(
    key: str,
    current_index: Any,
    candidate_index: Any,
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """Compare a root UUID collection without materializing the whole array."""
    before_map = current_index.uuid_collection(key) if key in current_index.root_fields else None
    after_map = candidate_index.uuid_collection(key) if key in candidate_index.root_fields else None
    if before_map is None or after_map is None:
        if key in current_index.root_fields and key in candidate_index.root_fields:
            before_ordered = current_index.ordered_object_array(key)
            after_ordered = candidate_index.ordered_object_array(key)
            if before_ordered is not None and after_ordered is not None:
                return _external_ordered_object_array(
                    key,
                    current_index,
                    candidate_index,
                    before_ordered,
                    after_ordered,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
        before = current_index.root_value(key) if key in current_index.root_fields else None
        after = candidate_index.root_value(key) if key in candidate_index.root_fields else None
        changes = find_differences(before, after, key, ignored_fields)
        if not changes:
            return None
        return {
            "added": [],
            "removed": [],
            "changed": [{"label": key, "uuid": None, "changes": changes if not summary_only else []}],
            "_summary_atomic_changed": len(changes),
            "_preflatten_changes": [] if summary_only else list(changes),
        }

    collection: dict[str, list[dict[str, Any]]] = {"added": [], "removed": [], "changed": []}
    for uuid in sorted(set(before_map) | set(after_map)):
        before_ref = before_map.get(uuid)
        after_ref = after_map.get(uuid)
        if before_ref is None and after_ref is not None:
            value = _decode_bytes(candidate_index.collection_item_bytes(after_ref))
            collection["added"].append({"uuid": uuid, "label": item_label(value), "value": value if not summary_only else None})
        elif after_ref is None and before_ref is not None:
            value = _decode_bytes(current_index.collection_item_bytes(before_ref))
            collection["removed"].append({"uuid": uuid, "label": item_label(value), "value": value if not summary_only else None})
        elif before_ref is not None and after_ref is not None and before_ref.semantic_digest != after_ref.semantic_digest:
            before = _decode_bytes(current_index.collection_item_bytes(before_ref))
            after = _decode_bytes(candidate_index.collection_item_bytes(after_ref))
            changes = find_differences(before, after, "", ignored_fields)
            if changes:
                collection["changed"].append({"uuid": uuid, "label": item_label(after), "changes": changes if not summary_only else []})
    return collection if any(collection.values()) else None


def _external_legacy_nodes(
    current_index: Any,
    candidate_index: Any,
    ignored_fields: set[str],
    summary_only: bool,
    jobs: str | int,
) -> dict[str, Any] | None:
    """Compare legacy ``nos`` by local records while reconstructing nested paths."""
    current_roots = set(current_index.roots)
    candidate_roots = set(candidate_index.roots)
    current_records = current_index.records
    candidate_records = candidate_index.records
    common_records = set(current_records) & set(candidate_records)

    collection: dict[str, list[dict[str, Any]]] = {"added": [], "removed": [], "changed": []}
    changed_by_root: dict[str, list[dict[str, Any]]] = {}

    # Top-level list semantics remain exactly those of the incumbent UUID map.
    for root_id in sorted(candidate_roots - current_roots):
        value = candidate_index.load_record(root_id)
        collection["added"].append({"uuid": root_id, "label": item_label(value), "value": value if not summary_only else None})
    for root_id in sorted(current_roots - candidate_roots):
        value = current_index.load_record(root_id)
        collection["removed"].append({"uuid": root_id, "label": item_label(value), "value": value if not summary_only else None})

    relation_changed = {
        record_id
        for record_id in common_records
        if current_records[record_id].parent_id != candidate_records[record_id].parent_id
    }
    removed_records = set(current_records) - set(candidate_records)
    added_records = set(candidate_records) - set(current_records)
    # A missing/moved ancestor already carries its subtree as the value of one
    # list addition/removal.  Descendants must not be reported twice.
    current_cover = set(removed_records) | relation_changed | (current_roots - candidate_roots)
    candidate_cover = set(added_records) | relation_changed | (candidate_roots - current_roots)

    def add_nested_change(root_id: str, change: dict[str, Any]) -> None:
        if root_id in current_roots & candidate_roots:
            changed_by_root.setdefault(root_id, []).append(change)

    # Pure removals below a surviving top-level root.
    for record_id in sorted(removed_records):
        root_id, path = current_index.legacy_root_and_path(record_id)
        if root_id not in current_roots & candidate_roots:
            continue
        if _has_covering_ancestor(current_index, record_id, current_cover - {record_id}):
            continue
        before = None if summary_only else current_index.load_record(record_id)
        add_nested_change(root_id, {"path": path, "kind": "removed", "before": before, "after": None})

    # Pure additions below a surviving top-level root.
    for record_id in sorted(added_records):
        root_id, path = candidate_index.legacy_root_and_path(record_id)
        if root_id not in current_roots & candidate_roots:
            continue
        if _has_covering_ancestor(candidate_index, record_id, candidate_cover - {record_id}):
            continue
        after = None if summary_only else candidate_index.load_record(record_id)
        add_nested_change(root_id, {"path": path, "kind": "added", "before": None, "after": after})

    # Moves are represented as list removal + list addition, matching the
    # incumbent's recursive keyed-list comparison.  Descendants of a moved
    # record are covered by the moved subtree itself.
    for record_id in sorted(relation_changed):
        if _has_covering_ancestor(current_index, record_id, relation_changed - {record_id}) or _has_covering_ancestor(
            candidate_index, record_id, relation_changed - {record_id}
        ):
            continue
        old_root, old_path = current_index.legacy_root_and_path(record_id)
        new_root, new_path = candidate_index.legacy_root_and_path(record_id)
        if old_root in current_roots & candidate_roots:
            before = None if summary_only else current_index.load_record(record_id)
            add_nested_change(old_root, {"path": old_path, "kind": "removed", "before": before, "after": None})
        if new_root in current_roots & candidate_roots:
            after = None if summary_only else candidate_index.load_record(record_id)
            add_nested_change(new_root, {"path": new_path, "kind": "added", "before": None, "after": after})

    tasks: list[tuple[int, str, bytes, bytes, str, tuple[str, ...]]] = []
    ordinal = 0
    for record_id in sorted(common_records - relation_changed):
        before_ref = current_records[record_id]
        after_ref = candidate_records[record_id]
        if before_ref.semantic_digest == after_ref.semantic_digest:
            continue
        if _has_covering_ancestor(current_index, record_id, relation_changed) or _has_covering_ancestor(
            candidate_index, record_id, relation_changed
        ):
            continue
        old_root, old_path = current_index.legacy_root_and_path(record_id)
        new_root, new_path = candidate_index.legacy_root_and_path(record_id)
        if old_root != new_root or old_path != new_path:
            # Defensive fallback; parent-id changes should already have put the
            # record in relation_changed.
            continue
        if old_root not in current_roots & candidate_roots:
            continue
        tasks.append(
            (
                ordinal,
                old_root,
                current_index.local_record_bytes(record_id),
                candidate_index.local_record_bytes(record_id),
                old_path,
                tuple(sorted(ignored_fields)),
            )
        )
        ordinal += 1

    budget = ResourceBudget.detect()
    worker_count = resolve_jobs(jobs, len(tasks), budget) if tasks else 1
    for _, root_id, changes in _run_payload_tasks(tasks, worker_count):
        if changes:
            changed_by_root.setdefault(root_id, []).extend(changes)

    for root_id in sorted(changed_by_root):
        changes = sorted(
            changed_by_root[root_id],
            key=lambda change: (
                str(change.get("path", "")),
                str(change.get("kind", "")),
                stable_item(change.get("before")),
                stable_item(change.get("after")),
            ),
        )
        label_source = candidate_index if root_id in candidate_records else current_index
        label = item_label(label_source.load_local_record(root_id))
        collection["changed"].append({"uuid": root_id, "label": label, "changes": changes if not summary_only else []})

    return collection if any(collection.values()) else None


def summarize_external_paths(
    current_path: Path,
    candidate_path: Path,
    ignored_fields: set[str],
    *,
    summary_only: bool = False,
    max_bytes: int | None = None,
    jobs: str | int = "auto",
    index_backend: str = "auto",
) -> dict[str, Any]:
    """Source-backed semantic diff for legacy exports.

    The full export is never materialized.  Only changed/added/removed records
    become Python objects; unchanged records are rejected by semantic digest.
    """

    with open_dialog_index(
        current_path,
        max_bytes=max_bytes,
        capture_details=True,
        ignored_fields=ignored_fields,
        backend=index_backend,
    ) as current_index, open_dialog_index(
        candidate_path,
        max_bytes=max_bytes,
        capture_details=True,
        ignored_fields=ignored_fields,
        backend=index_backend,
    ) as candidate_index:
        if current_index.format_type != candidate_index.format_type:
            raise ExternalDiffUnsupported(
                f"Formats incompatíveis: current={current_index.format_type}, candidate={candidate_index.format_type}"
            )
        if current_index.format_type not in {"legacy", "v1"}:
            raise ExternalDiffUnsupported(
                f"Formato external não suportado: {current_index.format_type}."
            )

        result = _empty_report(ignored_fields)
        for key in sorted(set(current_index.root_fields) | set(candidate_index.root_fields)):
            if key in ignored_fields:
                continue
            if key == "nos" and current_index.format_type == "legacy" and key in current_index.root_fields and key in candidate_index.root_fields:
                collection = _external_legacy_nodes(
                    current_index,
                    candidate_index,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
            else:
                collection = _external_generic_collection(
                    key,
                    current_index,
                    candidate_index,
                    ignored_fields,
                    summary_only,
                    jobs,
                )
            if collection is not None:
                summary_atomic_changed = int(collection.pop("_summary_atomic_changed", len(collection["changed"])))
                preflatten_changes = collection.pop("_preflatten_changes", [])
                result["collections"][key] = collection
                result["summary"]["added"] += len(collection["added"])
                result["summary"]["removed"] += len(collection["removed"])
                result["summary"]["changed"] += summary_atomic_changed if summary_only else len(collection["changed"])
                if not summary_only:
                    result["changes"].extend(
                        {"collection": key, "uuid": None, "label": key, **change}
                        for change in preflatten_changes
                    )

        if not summary_only:
            for collection_name, data in result["collections"].items():
                for entry in data["added"]:
                    result["changes"].append({
                        "collection": collection_name,
                        "uuid": entry["uuid"],
                        "label": entry["label"],
                        "path": "$",
                        "kind": "added",
                        "before": None,
                        "after": entry["value"],
                    })
                for entry in data["removed"]:
                    result["changes"].append({
                        "collection": collection_name,
                        "uuid": entry["uuid"],
                        "label": entry["label"],
                        "path": "$",
                        "kind": "removed",
                        "before": entry["value"],
                        "after": None,
                    })
                for entry in data["changed"]:
                    for change in entry["changes"]:
                        result["changes"].append({
                            "collection": collection_name,
                            "uuid": entry["uuid"],
                            "label": entry["label"],
                            **change,
                        })
            result["summary"] = {"added": 0, "removed": 0, "changed": 0}
            for change in result["changes"]:
                result["summary"][change["kind"] if change["kind"] in ("added", "removed") else "changed"] += 1
        return result


def choose_diff_engine(
    current_path: Path,
    candidate_path: Path,
    requested: str = "auto",
    *,
    budget: ResourceBudget | None = None,
) -> str:
    """Choose the fast DOM path only when it has a conservative RAM envelope.

    ``DEFAULT_EXTERNAL_THRESHOLD_BYTES`` remains a small-file fast-path floor:
    below it, the incumbent DOM is used directly.  Above it, ``auto`` no longer
    means "external unconditionally".  The combined encoded size is expanded
    by an empirical safety multiplier and must fit inside a bounded fraction of
    *currently available* memory.  Unknown memory resolves conservatively to
    external.

    Explicit ``--engine dom|external`` always wins and is the rollback/control
    surface for callers that know more about their workload than the heuristic.
    """
    if requested in {"dom", "external"}:
        return requested
    if requested != "auto":
        raise ValueError("engine deve ser auto, dom ou external")
    threshold_text = os.environ.get("WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES", "").strip()
    explicit_threshold = threshold_text.isdigit()
    threshold = int(threshold_text) if explicit_threshold else DEFAULT_EXTERNAL_THRESHOLD_BYTES
    largest = max(current_path.stat().st_size, candidate_path.stat().st_size)
    if largest < threshold:
        return "dom"
    if explicit_threshold:
        # Preserve the historical meaning of the existing environment knob:
        # callers that set it explicitly asked for a deterministic size cutoff.
        return "external"

    resolved_budget = budget or ResourceBudget.detect()
    available = resolved_budget.available_memory_bytes
    if not available:
        return "external"
    encoded_total = current_path.stat().st_size + candidate_path.stat().st_size
    estimated_dom_peak = int(encoded_total * DEFAULT_DOM_MEMORY_MULTIPLIER)
    dom_memory_budget = int(available * DEFAULT_DOM_MEMORY_FRACTION)
    return "dom" if estimated_dom_peak <= dom_memory_budget else "external"


def short_value(value: Any, limit: int = 180) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ": "))
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def markdown(report: dict[str, Any], max_changes: int) -> str:
    totals = report["summary"]
    lines = ["# Diff Watson Assistant", "", "`current → candidate`", "", "| Adicionados | Removidos | Alterados |", "| ---: | ---: | ---: |", f"| {totals['added']} | {totals['removed']} | {totals['changed']} |"]
    for collection, data in report["collections"].items():
        lines.extend(["", f"## {collection}"])
        for kind, title in (("added", "Adicionados"), ("removed", "Removidos")):
            if data[kind]:
                lines.extend(["", f"### {title}"])
                lines.extend(f"- `{entry['uuid']}` — {entry['label']}" for entry in data[kind])
        if data["changed"]:
            lines.extend(["", "### Alterados"])
            for entry in data["changed"]:
                lines.extend(["", f"#### {entry['label']} (`{entry['uuid']}`)"])
                shown = entry["changes"][:max_changes]
                for change in shown:
                    lines.append(f"- `{change['path']}`: {short_value(change['before'])} → {short_value(change['after'])}")
                hidden = len(entry["changes"]) - len(shown)
                if hidden:
                    lines.append(f"- _… e mais {hidden} alteração(ões); use `--max-changes` para exibir._")
    return "\n".join(lines) + "\n"


def main() -> int:
    configure_utf8_output()
    parser = argparse.ArgumentParser(description="Diff semântico de exports do Watson Assistant Dialog.")
    parser.add_argument("current", type=Path, help="arquivo da versão atual")
    parser.add_argument("candidate", type=Path, help="arquivo da versão candidata")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="grava o relatório neste arquivo; padrão: stdout")
    parser.add_argument("--include-timestamps", action="store_true", help="inclui dataCriacao e dataModificacao")
    parser.add_argument("--max-changes", type=int, default=20, help="máximo de campos mostrados por item no Markdown")
    parser.add_argument("--max-input-bytes", type=int, default=None, help="limite máximo em bytes; padrão: WATSON_DIALOG_MAX_BYTES ou 50 MiB")
    parser.add_argument("--summary-only", action="store_true", help="emite apenas sumário consolidado de contagens")
    parser.add_argument(
        "--engine",
        choices=("auto", "dom", "external"),
        default="auto",
        help="auto usa external para exports >= 16 MiB; dom força json.load; external força índice source-backed legacy/V1",
    )
    parser.add_argument(
        "--jobs",
        default="auto",
        help="workers do diff detalhado external: auto ou inteiro positivo",
    )
    parser.add_argument(
        "--index-backend",
        choices=("auto", "mmap", "transient"),
        default="auto",
        help="backend do índice external: auto escolhe transient quando um DOM por vez cabe com folga; mmap força bounded-memory estrito",
    )
    args = parser.parse_args()
    if args.max_changes < 1:
        parser.error("--max-changes deve ser pelo menos 1")

    ignored = set() if args.include_timestamps else DEFAULT_IGNORED_FIELDS
    try:
        engine = choose_diff_engine(args.current, args.candidate, args.engine)
        if engine == "external":
            report = summarize_external_paths(
                args.current,
                args.candidate,
                set(ignored),
                summary_only=args.summary_only,
                max_bytes=args.max_input_bytes,
                jobs=args.jobs,
                index_backend=args.index_backend,
            )
        else:
            report = summarize(
                load_json(args.current, max_bytes=args.max_input_bytes),
                load_json(args.candidate, max_bytes=args.max_input_bytes),
                ignored,
                summary_only=args.summary_only,
            )
    except (OSError, ValueError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 2
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n" if args.format == "json" else markdown(report, args.max_changes)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.summary_only:
        return 1 if any(report["summary"].values()) else 0
    return 1 if report["changes"] else 0



# ------------------------------------------------------------------------------
# Module: explorer.py
# ------------------------------------------------------------------------------

"""Universal Dialog AST Explorer & Polymorphic Schema Adapter for tare.tools.dialog-engine.

Provides automatic introspection, extraction, and bidirectional normalization for:
1. Official IBM Watson Assistant Skill JSON (V1 classic and V2 flat pointer topologies).
2. Hierarchical / Nested enterprise dialog trees (nos/filhos/respostas/slots).
3. Multi-channel output schemas (WhatsApp, Web Chat, Mobile App, Voice, Slack).
4. Multimodal & Rich media responses (text, images, carousels, cards, options, pauses).
5. Slots, slot event handlers, and context variable lifecycles.
6. Arbitrary rich metadata, tags, designer coordinates, and action payloads.
"""


import sys
from pathlib import Path



import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    print("  tare.tools — Dialog AST Explorer & Schema Discovery")
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



# ------------------------------------------------------------------------------
# Module: schema_adapter.py
# ------------------------------------------------------------------------------

"""Universal Schema Discovery, Semantic Binding, and State Machine Adapter for tare.tools.dialog-engine.

Decouples the engine from specific vendor or proprietary JSON key names, allowing
it to navigate, validate, mutate, and diff ANY conversational state machine or dialog
graph by mapping it to canonical Universal AST primitives.
"""


import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator


@dataclass
class KeyMapping:
    """Configurable semantic property mappings for a state machine node."""
    id_keys: list[str] = field(default_factory=lambda: ["dialog_node", "uuid", "id", "node_id", "name", "key"])
    title_keys: list[str] = field(default_factory=lambda: ["title", "nome", "name", "label", "description"])
    condition_keys: list[str] = field(default_factory=lambda: ["conditions", "condicao", "condition", "guard", "when", "expression"])
    context_keys: list[str] = field(default_factory=lambda: ["context", "contexto", "variables", "state", "variaveisContexto"])
    children_keys: list[str] = field(default_factory=lambda: ["children", "filhos", "subnodes", "branches", "steps"])
    slots_keys: list[str] = field(default_factory=lambda: ["slots", "parameters", "entities_capture", "quadros"])
    responses_keys: list[str] = field(default_factory=lambda: ["output", "respostas", "responses", "messages", "actions"])
    jumps_keys: list[str] = field(default_factory=lambda: ["next_step", "jump_to", "transitions", "target", "goto"])


@dataclass
class SchemaBinding:
    """Semantic adapter that binds arbitrary JSON structures to Universal AST primitives."""
    schema_name: str = "auto_discovered"
    root_nodes_keys: list[str] = field(default_factory=lambda: ["dialog_nodes", "nos", "nodes", "states", "arvoreDialogo", "blocks"])
    mapping: KeyMapping = field(default_factory=KeyMapping)
    confidence_score: float = 1.0
    discovered_alignment: dict[str, str] = field(default_factory=dict)

    # --------------------------------------------------------------------------
    # Field Extractors (Decoupled Accessors)
    # --------------------------------------------------------------------------
    def get_id(self, node: dict[str, Any]) -> str:
        for k in self.mapping.id_keys:
            if k in node and node[k]:
                return str(node[k])
        return ""

    def get_title(self, node: dict[str, Any]) -> str:
        for k in self.mapping.title_keys:
            if k in node and node[k]:
                return str(node[k])
        return self.get_id(node)

    def get_condition(self, node: dict[str, Any]) -> str:
        for k in self.mapping.condition_keys:
            if k in node and node[k] is not None:
                return str(node[k])
        return ""

    def set_condition(self, node: dict[str, Any], new_condition: str) -> None:
        for k in self.mapping.condition_keys:
            if k in node:
                node[k] = new_condition
                return
        # Default fallback to the primary key in the mapping
        node[self.mapping.condition_keys[0]] = new_condition

    def get_context(self, node: dict[str, Any]) -> dict[str, Any]:
        for k in self.mapping.context_keys:
            if k in node and isinstance(node[k], dict):
                return node[k]
        return {}

    def set_context_variable(self, node: dict[str, Any], var_name: str, var_value: Any) -> None:
        for k in self.mapping.context_keys:
            if k in node and isinstance(node[k], dict):
                node[k][var_name] = var_value
                return
        # Initialize context if missing
        primary_key = self.mapping.context_keys[0]
        node[primary_key] = {var_name: var_value}

    def get_children(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        for k in self.mapping.children_keys:
            if k in node and isinstance(node[k], list):
                return [n for n in node[k] if isinstance(n, dict)]
        return []

    def get_slots(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        for k in self.mapping.slots_keys:
            if k in node and isinstance(node[k], list):
                return [s for s in node[k] if isinstance(s, dict)]
        return []

    def get_root_nodes(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(document, dict):
            return []
        for k in self.root_nodes_keys:
            if k in document and isinstance(document[k], list):
                return [n for n in document[k] if isinstance(n, dict)]
        return []

    # --------------------------------------------------------------------------
    # Universal Traversal & Visitors
    # --------------------------------------------------------------------------
    def iter_all_nodes(self, document: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every node, slot, and sub-branch across arbitrary state machines."""
        def visit(nodes: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                yield node
                for slot in self.get_slots(node):
                    yield slot
                    yield from visit(self.get_children(slot))
                yield from visit(self.get_children(node))

        roots = self.get_root_nodes(document)
        # If flat list without children nesting (e.g. standard Watson V1 flat list)
        is_flat = any("dialog_node" in n and ("parent" in n or "previous_sibling" in n) for n in roots[:10])
        if is_flat and not any(self.get_children(n) for n in roots[:10]):
            yield from roots
        else:
            yield from visit(roots)

    # --------------------------------------------------------------------------
    # Schema Auto-Discovery Engine
    # --------------------------------------------------------------------------
    @classmethod
    def discover(cls, document: dict[str, Any]) -> SchemaBinding:
        """Inspect document keys and infer semantic binding with confidence scoring."""
        if not isinstance(document, dict):
            return cls(schema_name="invalid", confidence_score=0.0)

        alignment: dict[str, str] = {}
        sample_node: dict[str, Any] = {}

        # 1. Discover root collection
        root_key = "dialog_nodes"
        for k in ["dialog_nodes", "nos", "nodes", "states", "arvoreDialogo", "blocks"]:
            if k in document and isinstance(document[k], list):
                root_key = k
                alignment["root_collection"] = f"{k} -> canonical:roots"
                if document[k] and isinstance(document[k][0], dict):
                    sample_node = document[k][0]
                break

        # 2. Discover node properties from sample
        mapping = KeyMapping()
        score = 0.7 if root_key in ("dialog_nodes", "nos") else 0.5

        if sample_node:
            # Condition key
            for k in mapping.condition_keys:
                if k in sample_node:
                    alignment["condition"] = f"{k} -> canonical:condition"
                    score += 0.1
                    break

            # Context key
            for k in mapping.context_keys:
                if k in sample_node:
                    alignment["context"] = f"{k} -> canonical:context"
                    score += 0.1
                    break

            # Children key
            for k in mapping.children_keys:
                if k in sample_node:
                    alignment["children"] = f"{k} -> canonical:children"
                    score += 0.1
                    break

            # Slots key
            for k in mapping.slots_keys:
                if k in sample_node:
                    alignment["slots"] = f"{k} -> canonical:slots"
                    score += 0.1
                    break

        format_name = "watson_v1_flat" if root_key == "dialog_nodes" else ("enterprise_hierarchical" if root_key == "nos" else f"custom_{root_key}")

        return cls(
            schema_name=format_name,
            root_nodes_keys=[root_key, *[k for k in ["dialog_nodes", "nos", "nodes", "states"] if k != root_key]],
            mapping=mapping,
            confidence_score=min(1.0, score),
            discovered_alignment=alignment,
        )


# Global default binding instance
DEFAULT_BINDING = SchemaBinding()

# ------------------------------------------------------------------------------
# Module: mutator.py
# ------------------------------------------------------------------------------

"""Symbolic AST & Automata Mutation Engine for Conversational State Graphs.

Provides systematic graph perturbations, predicate inversions, dangling transition
injections, and metamorphic relation testing for dialog trees and AI agent states.
"""


import copy
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable




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

# ------------------------------------------------------------------------------
# Module: rule_mutator.py
# ------------------------------------------------------------------------------

"""Semantic Business Rule Mutation & Test Gap Auditor.

Evaluates conversational test suites against semantic mutations of business rules,
security guardrails, underwriting conditions, and routing intents to discover
testing blindspots, dead predicates, and unverified edge cases.
"""


import copy
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any




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
    mutated_doc: dict[str, Any]
    status: str = "PENDING"  # "KILLED" or "SURVIVED_BLINDSPOT"
    killing_scenario_id: str | None = None
    curation_decision: str = "PENDING_REVIEW"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_tier"] = self.risk_tier.value
        d["operator"] = self.operator.value
        d.pop("mutated_doc", None)  # Exclude raw doc from summary dict
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

        def make_mutated_doc(target_id: str, new_cond: str | None = None, new_ctx_key: str | None = None, new_ctx_val: Any = None) -> dict[str, Any]:
            m_doc = copy.deepcopy(document)
            for n in b.iter_all_nodes(m_doc):
                if b.get_id(n) == target_id:
                    if new_cond is not None:
                        b.set_condition(n, new_cond)
                    if new_ctx_key is not None:
                        b.set_context_variable(n, new_ctx_key, new_ctx_val)
                    break
            return m_doc

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
                m_doc = make_mutated_doc(node_id, new_cond=mutated)
                mutants.append(RuleMutant(
                    mutation_id=self._next_id("SEC"),
                    node_id=node_id,
                    node_title=node_title,
                    risk_tier=RiskTier.SECURITY_CRITICAL,
                    operator=MutationOperator.GUARD_BYPASS,
                    original_expression=orig or "user_authenticated check",
                    mutated_expression=mutated,
                    explanation="Bypassed user authentication guard to test if unauthorized users reach this node.",
                    mutated_doc=m_doc,
                ))

            # ----------------------------------------------------------
            # 2. BUSINESS FINANCIAL: Limits & Score Thresholds
            # ----------------------------------------------------------
            for field, val in (ctx.items() if isinstance(ctx, dict) else []):
                if isinstance(val, str) and (">" in val or "<" in val or "score" in val.lower() or "limit" in val.lower()):
                    orig_val = str(val)
                    mutated_val = orig_val.replace(">=", "<").replace(">", "<=").replace("approved", "denied")
                    if mutated_val == orig_val:
                        mutated_val = f"<? false /* mutated {orig_val} */ ?>"

                    m_doc = make_mutated_doc(node_id, new_ctx_key=field, new_ctx_val=mutated_val)
                    mutants.append(RuleMutant(
                        mutation_id=self._next_id("FIN"),
                        node_id=node_id,
                        node_title=node_title,
                        risk_tier=RiskTier.BUSINESS_FINANCIAL,
                        operator=MutationOperator.LIMIT_INVERSION,
                        original_expression=f"{field}: {orig_val}",
                        mutated_expression=f"{field}: {mutated_val}",
                        explanation=f"Inverted financial underwriting threshold in context variable '{field}'.",
                        mutated_doc=m_doc,
                    ))

            # ----------------------------------------------------------
            # 3. ROUTING & ESCALATION: Intent & Trigger Guards
            # ----------------------------------------------------------
            if cond and cond not in {"welcome", "true", "false", "anything_else"}:
                mutated_cond = "false"
                is_escalation = any(k in cond.lower() for k in ("atendente", "humano", "transbordo", "ajuda", "duvida"))
                risk = RiskTier.ROUTING_ESCALATION if is_escalation else RiskTier.BUSINESS_FINANCIAL
                m_doc = make_mutated_doc(node_id, new_cond=mutated_cond)
                mutants.append(RuleMutant(
                    mutation_id=self._next_id("ROU"),
                    node_id=node_id,
                    node_title=node_title,
                    risk_tier=risk,
                    operator=MutationOperator.INTENT_MUTATION,
                    original_expression=cond,
                    mutated_expression=mutated_cond,
                    explanation=f"Disabled route trigger '{cond}' to test if conversational test suite detects loss of {node_title}.",
                    mutated_doc=m_doc,
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
    mutants = mutator.generate_rule_mutants(document)

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

        for i, scen in enumerate(scenarios):
            scen_id = scen.get("id") or f"scenario_{i+1}"
            base_trace = baseline_traces[i]

            try:
                m_trace = run_scenario(m.mutated_doc, scen)
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


# ==============================================================================
# Unified CLI Dispatcher for Ephemeral Sandboxes
# ==============================================================================

def main_cli() -> None:
    configure_utf8_output()
    parser = argparse.ArgumentParser(
        prog="dialog_engine",
        description="tare.tools Dialog Engine — Standalone Ephemeral Runner for ChatGPT ADA and M365 Copilot."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available engine commands")

    # 1. Diff
    diff_parser = subparsers.add_parser("diff", help="Semantic AST diff between two dialog versions")
    diff_parser.add_argument("current", type=Path, help="Current/Baseline dialog JSON")
    diff_parser.add_argument("candidate", type=Path, help="Candidate/Modified dialog JSON")
    diff_parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Report format")
    diff_parser.add_argument("--output", "-o", type=Path, help="Output destination file")
    diff_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal summary counts only")
    diff_parser.add_argument("--max-changes", type=int, default=20, help="Maximum changes to print per item in Markdown")

    # 2. Validate
    val_parser = subparsers.add_parser("validate", help="Validate dialog with single issue contract")
    val_parser.add_argument("document", type=Path, help="Target dialog JSON to validate")
    val_parser.add_argument("--output", "-o", type=Path, help="Output JSON report file")
    val_parser.add_argument("--summary-only", action="store_true", help="Emit high-signal issue summary only")

    # 3. Explore
    exp_parser = subparsers.add_parser("explore", help="Explore dialog primitives, channels, media, and schema")
    exp_parser.add_argument("document", type=Path, help="Target dialog JSON export")
    exp_parser.add_argument("--introspect", action="store_true", default=True, help="Print summary of discovered primitives")
    exp_parser.add_argument("--channels", action="store_true", help="List communication channels")
    exp_parser.add_argument("--multimedia", action="store_true", help="List rich media components")
    exp_parser.add_argument("--ast", action="store_true", help="Output Universal AST JSON")
    exp_parser.add_argument("--convert-to", choices=["v1", "nested"], help="Convert format (v1 or nested)")
    exp_parser.add_argument("--output", "-o", type=Path, help="Output file")

    # 4. Graph
    graph_parser = subparsers.add_parser("graph", help="Generate topological graph and reachability report")
    graph_parser.add_argument("document", type=Path, help="Dialog JSON file")
    graph_parser.add_argument("--output-json", type=Path, help="JSON graph output file")
    graph_parser.add_argument("--output-dot", type=Path, help="DOT graph output file")

    # 5. Test
    test_parser = subparsers.add_parser("test", help="Run deterministic test scenario against dialog")
    test_parser.add_argument("document", type=Path, help="Dialog JSON file")
    test_parser.add_argument("scenario", type=Path, help="Scenario JSON test file")
    test_parser.add_argument("--output", "-o", type=Path, help="Output trace JSON file")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "diff":
            cur_doc = load_json(args.current)
            cand_doc = load_json(args.candidate)
            report = summarize(cur_doc, cand_doc, DEFAULT_IGNORED_FIELDS, summary_only=args.summary_only)
            if args.format == "json":
                out = json.dumps(report, indent=2, ensure_ascii=False)
            else:
                out = markdown(report, args.max_changes)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Diff written to {args.output}")
            else:
                print(out)

        elif args.command == "validate":
            doc = load_json(args.document)
            report = validate(doc)
            out = json.dumps(report, indent=2, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Validation written to {args.output}")
            else:
                print(out)

        elif args.command == "explore":
            raw_doc = load_json(args.document)
            if args.convert_to:
                doc = explore_document(raw_doc)
                converted = to_v1_format(doc) if args.convert_to == "v1" else to_nested_format(doc)
                out = json.dumps(converted, indent=2, ensure_ascii=False)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(out, encoding="utf-8")
                    print(f"Converted to {args.convert_to}: {args.output}")
                else:
                    print(out)
            elif args.channels:
                intro = introspect_primitives(raw_doc)
                print(f"=== Discovered Channels ({len(intro['discovered_channels'])}) ===")
                for ch in intro["discovered_channels"]:
                    print(f" - {ch}")
            elif args.multimedia:
                doc = explore_document(raw_doc)
                print("=== Discovered Multimedia & Rich Responses ===")
                for node in doc.iter_nodes():
                    for resp in node.responses:
                        if resp.response_type != "text" or resp.media_urls or resp.options:
                            print(f"[{node.id}] ({resp.channel}) {resp.response_type.upper()}: title='{resp.title}' media={resp.media_urls}")
            elif args.ast:
                doc = explore_document(raw_doc)
                out = json.dumps(doc.to_dict(), indent=2, ensure_ascii=False)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(out, encoding="utf-8")
                    print(f"AST written to {args.output}")
                else:
                    print(out)
            else:
                intro = introspect_primitives(raw_doc)
                print("=================================================================")
                print(f"  tare.tools — Dialog AST Explorer (Ephemeral Standalone)")
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

        elif args.command == "graph":
            doc = load_json(args.document)
            g = build_graph(doc)
            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"Graph JSON written to {args.output_json}")
            if args.output_dot:
                args.output_dot.parent.mkdir(parents=True, exist_ok=True)
                args.output_dot.write_text(render_dot(g), encoding="utf-8")
                print(f"Graph DOT written to {args.output_dot}")
            if not args.output_json and not args.output_dot:
                print(json.dumps(g["summary"], indent=2, ensure_ascii=False))

        elif args.command == "test":
            doc = load_json(args.document)
            scen = load_json(args.scenario)
            result = run_scenario(doc, scen)
            out = json.dumps(result, indent=2, ensure_ascii=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(out, encoding="utf-8")
                print(f"Test trace written to {args.output}")
            else:
                print(out)

    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main_cli()
