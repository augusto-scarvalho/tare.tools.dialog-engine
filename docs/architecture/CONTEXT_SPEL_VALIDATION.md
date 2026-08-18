# Context SpEL Validation

**Status:** CURRENT  
**Scope:** Watson Assistant Dialog side project only  
**Primary implementation:** `watson_spel.py`, `watson_dialog_validate.py`

## 1. Problem

Watson Assistant Dialog allows a dialog node to write values into `context`. A context value may be any JSON value, and string values may embed Spring Expression Language (SpEL) by using the IBM evaluation template syntax:

```text
<? expression ?>
```

A malformed expression in a node condition is comparatively visible because the condition itself is already analyzed by this project. A malformed expression inside `context`, however, can remain hidden inside a node JSON payload and fail only when the dialog runtime evaluates that node.

The side project's normalized legacy export adds one more layer: the original IBM dialog-node JSON is stored as a JSON **string** in each normalized node or slot's `json` field. Therefore the same IBM context can appear through two physical representations:

```text
API V1 export
  dialog_nodes[].context

normalized legacy export
  nos[].json -> parsed JSON -> context
  nos[].slots[].json -> parsed JSON -> context
```

The validator must cover both without creating separate semantic implementations.

## 2. IBM semantic basis

IBM documents that:

- dialog-node context is an object;
- context variable values can be strings, numbers, arrays, objects, and other supported JSON values;
- SpEL can be embedded in values by using `<? expression ?>`;
- unlike node conditions, context/output expressions require the evaluation delimiters when expression evaluation is intended.

Primary references:

- `https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-methods`
- `https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-expression-language`
- `https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime-context`
- Watson Assistant v1 API reference (`DialogNode.context`).

The conformance catalog records this as `CONF-SPEL-003`.

## 3. Correctness policy

The validator is deliberately **conservative**.

It does **not** reject an expression merely because the project's safe SpEL evaluator cannot parse or execute every IBM-supported feature. That would turn an incomplete local parser into false authority over the Watson runtime.

The context validator reports only defects that can be established without full IBM evaluation:

1. `<?` with no matching `?>`;
2. an empty `<? ?>` template;
3. unterminated quoted strings inside the extracted expression;
4. unbalanced parentheses;
5. boolean operators with a provably missing operand.

Existing safe syntax diagnostics are reused for the expression body.

Unsupported methods, globals, date helpers, array helpers, and other legal SpEL features are **not** classified as errors solely because they are outside the evaluator subset.

## 4. Template scanner

`watson_spel.template_syntax_diagnostics(text)` scans a context string for embedded expression templates.

The close-delimiter scanner is quote-aware and follows SpEL string-literal rules rather than Python/C-style escaping:

- single- and double-quoted strings are supported;
- the matching quote is escaped by doubling it (`''` or `""`);
- backslash is ordinary string content and does **not** escape the following quote.

For example, neither of these may be mis-scanned:

```text
<? '?>'.contains('>') ?>
<? @pattern.literal.replace('\', '') ?>
```

The first contains `?>` inside a quoted string. The second contains a one-character backslash string; the quote after the backslash closes the literal normally. Treating `\` as a C/Python escape would incorrectly hide the real template terminator.

For each malformed template the scanner returns:

- category;
- code;
- message;
- extracted expression;
- start/end character span;
- template ordinal inside the containing string.

The validator prefixes context-specific codes with `context_spel_` so summary counts distinguish condition defects from context defects.

Examples:

```text
context_spel_unclosed_template
context_spel_empty_expression
context_spel_unterminated_string
context_spel_unclosed_parenthesis
context_spel_missing_right_operand
```

## 5. Context discovery

`watson_dialog_validate.iter_dialog_contexts()` discovers contexts from both supported source shapes.

### 5.1 API V1

For each object in `dialog_nodes`:

```json
{
  "dialog_node": "node-id",
  "context": {
    "name": "<? input.text ?>"
  }
}
```

The issue owner is the `dialog_node` ID and the root field is `context`.

### 5.2 Normalized legacy

For every normalized node and slot, the `json` field is parsed only if it is valid JSON. If the parsed object contains `context`, that context is analyzed.

Example physical shape:

```json
{
  "uuid": "normalized-node-id",
  "json": "{\"context\":{\"name\":\"<? input.text ?>\"}}"
}
```

The issue owner is the normalized node UUID (or `slot:<uuid>`), and the root field is `json.context`.

Invalid `json` payloads continue to be reported by the existing `invalid_json_configuration` validation. They are not reparsed as context, preventing duplicate/noisy diagnostics.

## 6. Nested paths

Context values can contain nested objects and arrays. Validation recursively visits only strings and records an exact deterministic path.

Examples:

```text
context["profile"]["name"]
context["items"][2]["label"]
json.context["request"]["payload"][0]
```

This makes a finding actionable without flattening or mutating the source document.

## 7. Stable issue contract

Context SpEL findings use the same validation contract as every other validator finding:

```json
{
  "category": "syntactic",
  "code": "context_spel_unclosed_template",
  "severity": "error",
  "node": "...",
  "field": "json.context[\"...\"]",
  "value": "...expression only...",
  "message": "..."
}
```

The `value` field contains only the extracted expression rather than the entire context string. This reduces report noise and limits unrelated context data exposure.

## 8. Production-scale evidence and false-positive correction (2026-08-15)

The two private production exports were used only as local validation inputs and remain excluded from Git.

An earlier version of this validator reported seven `context_spel_unclosed_template` findings in six nodes in both exports. Manual inspection showed that all seven expressions **did contain** a closing `?>`. Their common shape included a SpEL string literal containing a single backslash, for example:

```text
<? @pattern.literal.replace('\', '') ?>
```

The original scanner incorrectly treated backslash as a C/Python-style escape for the following quote. That kept the scanner artificially inside the string literal and caused the real `?>` to be ignored. This was a validator defect, not a Watson-dialog defect.

After changing the scanner to SpEL quote semantics and adding regression tests, the aggregated context-SpEL findings are:

```text
current.json
  file size       83,086,063 bytes
  context issues  0
  affected nodes  0

candidate.json
  file size       83,119,234 bytes
  context issues  0
  affected nodes  0
```

The empty `(node, field, code)` signature set is identical between current and candidate. This evidence applies only to the conservative syntax family implemented here; it does not prove semantic correctness of every context assignment.

The correction is retained as negative evidence: production-scale validation exposed a false-positive class, the lexical assumption was corrected against SpEL string-literal semantics, and a targeted regression/mutation gate now prevents reintroducing it.

## 9. Gates

Required gates include:

- valid V1 context expression produces no finding;
- malformed V1 nested context expression produces exact field path;
- normalized legacy node `json.context` is covered;
- normalized legacy slot `json.context` is covered;
- multiple templates in one string are scanned independently;
- `?>` inside quoted SpEL string does not close the template;
- a literal backslash such as `replace('\', '')` does not escape the closing quote;
- doubled quotes (`''` / `""`) remain inside the same SpEL literal;
- mutation that reintroduces backslash-as-escape behavior must be killed;
- invalid outer `json` does not generate duplicate context findings;
- mutation removing `context_spel_issues()` from unified validation must be killed;
- existing validation report remains deterministic.

## 10. Non-goals / open extensions

Not implemented as authority in this slice:

- full IBM Spring SpEL grammar validation;
- type checking against live runtime context;
- checking whether referenced entities/intents/context variables exist at the exact node execution point;
- evaluating context assignments in dependency order (IBM does not guarantee declaration order for context variable updates in the same node);
- automatic remediation of malformed expressions.

Those require stronger runtime or grammar evidence and should be added separately rather than widening this conservative syntax gate.
