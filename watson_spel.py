"""Safe evaluator for the SpEL subset used by Watson Assistant Dialog conditions.

It intentionally supports expressions only: no assignments, type construction,
reflection, or arbitrary Python/Java method execution is permitted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class SpelError(ValueError):
    pass


class _Unknown:
    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


TOKEN_RE = re.compile(
    r"\s*(?:(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")|(?P<number>\d+(?:\.\d+)?L?)|(?P<op>\?\.|&&|\|\||==|!=|>=|<=|[+*/<>!?:().,\[\]-])|(?P<name>[$@#]?(?:[A-Za-z_][\w-]*|\d[\w-]*)))"
)


def syntax_diagnostics(expression: str) -> list[dict[str, str]]:
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
    escaped = False
    for character in expression:
        if quote:
            masked.append(" ")
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
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


def tokenize(expression: str) -> list[Token]:
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
    return tokens


class Parser:
    PRECEDENCE = {"||": 1, "&&": 2, "==": 3, "!=": 3, "matches": 3, ">": 4, ">=": 4, "<": 4, "<=": 4, "+": 5, "-": 5, "*": 6, "/": 6}

    def __init__(self, expression: str):
        self.tokens = tokenize(expression)
        self.position = 0
        self.in_ternary_value = False

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
    if value is UNKNOWN or value is None:
        return UNKNOWN
    if isinstance(value, dict):
        return value.get(key, UNKNOWN)
    if isinstance(value, list) and key == "size":
        return len(value)
    return getattr(value, key, UNKNOWN)


def _call(value: Any, method: str, arguments: list[Any], environment: dict[str, Any]) -> Any:
    if value is UNKNOWN or value is None or any(argument is UNKNOWN for argument in arguments):
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
        return UNKNOWN if value is UNKNOWN else (not _truth(value) if tree[1] == "!" else -value)
    if kind == "binary":
        operator, left_tree, right_tree = tree[1:]
        left = evaluate(left_tree, environment)
        if operator == "&&" and left is not UNKNOWN and not _truth(left): return False
        if operator == "||" and left is not UNKNOWN and _truth(left): return True
        right = evaluate(right_tree, environment)
        if left is UNKNOWN or right is UNKNOWN: return UNKNOWN
        if operator == "&&": return _truth(left) and _truth(right)
        if operator == "||": return _truth(left) or _truth(right)
        if operator == "==": return left == right
        if operator == "!=": return left != right
        if operator == "matches": return bool(re.fullmatch(str(right), str(left)))
        if operator == ">": return left > right
        if operator == ">=": return left >= right
        if operator == "<": return left < right
        if operator == "<=": return left <= right
        if operator == "+": return left + right
        if operator == "-": return left - right
        if operator == "*": return left * right
        if operator == "/": return left / right
    raise SpelError(f"AST desconhecida: {kind}")


def evaluate_expression(expression: str, environment: dict[str, Any]) -> Any:
    return evaluate(parse(expression), environment)


def evaluate_condition(expression: str, environment: dict[str, Any]) -> bool | _Unknown:
    value = evaluate_expression(expression, environment)
    return _truth(value)
