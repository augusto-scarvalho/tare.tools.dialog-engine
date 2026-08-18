# IBM Rules — Legacy Watson Assistant Dialog

This catalog maintains the official sources and the rules they establish for the project. It contains no exports, customer data, or verbatim documentation dumps. Reviewed 2026-08-15.

## Scope

The scope covers public documentation for the legacy **Dialog** flow, API V1 node model, and related topics: evaluation tree and order, folders, conditions and SpEL, responses, next steps and jumps, slots and handlers, context, digressions, and structural API constraints.

## Official Sources Index

| Area | Source | Project Usage |
| --- | --- | --- |
| Authoring, conditions, responses & jumps | [Creating a dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-overview) | validation, graph and test runner |
| Processing order | [How your dialog is processed](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-build) | graph, reachability and test runner |
| Organization & folders | [Improving your conversation](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-tasks) | graph, topology and test runner |
| Start & end | [Starting and ending the dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-start) | special conditions and test runner |
| Slots | [Gathering information with slots](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-slots) | validation and test runner |
| Digressions | [Controlling the conversational flow](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime) | graph metadata and test runner |
| Objects & shorthand | [Expressions for accessing objects](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-expression-language) | SpEL parser/analyzer |
| SpEL Methods | [Expression language methods](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-methods) | SpEL parser/evaluator |
| Runtime context | [Personalizing the dialog with context](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime-context) | test scenarios and variables |
| Webhooks | [Making a programmatic call](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-webhooks) | test runner bounds and SpEL |
| API Structure | [Modifying dialog via API](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-api-dialog-modify) | API profile |
| API V1 Contract | [Watson Assistant V1 API](https://ondeck.console.cloud.ibm.com/apidocs/assistant-v1?code=unity) | node types and `dialog_stack` |

## Tree Model and Folders

- Normal evaluation traverses sibling nodes in authored order; if no child branch matches, flow returns to base level.
- A **folder is an explicit node type** (`type: folder` in API; `folder` in legacy export). Do not infer merely from having children.
- Folders can be empty and may have conditions. Without a condition, it defaults to `true`.
- Folder conditions must be met before evaluating internal nodes. Folders do not change root sibling order for runtime evaluation.

## Conditions, SpEL and Conversation Start

- Node conditions have a maximum length of 2,048 characters.
- `true` is an explicit sibling fallback. `anything_else` is the dialogue end fallback; it must occur after all evaluable root siblings.
- `conversation_start` is true in turn 1 regardless of input; `welcome` is true only in turn 1 without user input.
- Shorthand `@entity:(...)` inspects the first occurrence; values cannot contain closing parenthesis `)`.
- Hyphenated variables require `$(name-with-hyphen)` or `context['name-with-hyphen']`.
- The project evaluator is deliberately conservative: an `unknown` result does not imply rejection by Watson.

## Responses, Next Steps and Jumps

- Conditional responses evaluate in order within a node. Each can update context, emit rich responses, and set its own Jump to.
- Response-level jumps take precedence over node-level jumps.
- Jumps to **condition** evaluate the target and then siblings; jumps to **response** execute output directly without condition check; jumps to **user input** wait for next message.

## Slots, Handlers and Digressions

- A slot node gathers slots in sequence. Subsequent slots may depend on prior mandatory slots, but never on later slots or prior optional slots.
- Bare `@sys-number` does not recognize zero; use comparison `>= 0` when zero is valid.
- Slots block digression by default. Digression out is also blocked by `true`/`anything_else` forcing children, jumps, or skip user input.
