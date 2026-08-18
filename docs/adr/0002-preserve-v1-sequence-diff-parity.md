# ADR-0002 — Preservar a semântica posicional do diff V1 durante a migração external-memory

**Status:** ACCEPTED
**Data:** 2026-08-15
**Escopo:** side project Watson Assistant Dialog tools.

## Contexto

`dialog_nodes` em exports Dialog API V1 identifica nodes por `dialog_node`. Seria natural criar um novo diff que mapeasse a coleção por esse identificador, tornando reorder irrelevante.

Entretanto, o engine DOM histórico não faz isso. Sua função genérica só indexa arrays por `uuid`; como `dialog_nodes` não possui `uuid`, ele executa `SequenceMatcher` sobre a lista ordenada e compara blocos de replace por posição.

A migração para external-memory é uma mudança de execução/performance, não autorização para redesenhar a semântica do report.

## Decisão

O engine external V1 deve preservar exatamente a semântica order-sensitive do DOM incumbent.

Implementar:

- ordered item refs;
- stable canonical matching digest;
- collision verification por canonical bytes;
- `SequenceMatcher(..., autojunk=False)` compatível com o incumbent;
- pair/delete/insert event plan idêntico ao `compare_list()`;
- `find_differences()` incumbent como semantic reducer;
- reprodução do comportamento histórico de flatten de non-UUID collections para byte-level parity.

Não implementar implicitamente um map por `dialog_node` nesta slice.

## Consequências positivas

- parity pode ser provada por igualdade byte a byte;
- nenhuma alteração de comportamento fica escondida numa otimização;
- rollback para DOM permanece simples;
- V1 ganha external-memory sem criar segundo report schema;
- future identity-aware semantics podem ser comparadas contra um baseline estável.

## Consequências negativas

- reorder V1 continua podendo aparecer como mudança;
- reports não-UUID preservam duplicação histórica em `changes[]`;
- comportamento incumbent não é necessariamente a melhor UX futura.

Esses pontos são compatibility debt, não bugs desta implementação external.

## Alternativas rejeitadas nesta slice

### Reindexar `dialog_nodes` por `dialog_node`

**REJECT for parity / OPEN as future mode.** Melhor semântica potencial, mas quebra outputs existentes.

### Normalizar V1 para legacy antes do diff

**REJECT.** A normalização do runner preserva apenas fields que o simulador entende. Usá-la como diff source perderia fields V1 desconhecidas e deixaria de comparar o raw export autoritativo.

### Materializar `dialog_nodes` inteiro no external engine

**REJECT as foundation.** Preserva semântica, mas reintroduz crescimento de memória que motivou a migração.

### Usar somente digest como token do SequenceMatcher

**REJECT.** Colisão passaria a ter autoridade semântica. O design atual verifica canonical bytes quando um digest pode participar de igualdade.

## Rollback

`--engine dom` mantém o oracle anterior.

`--engine external --index-backend transient|mmap` permite selecionar a implementação external sem alterar o report contract.

## Evidência de ratificação

- suite completa: 92+ testes antes do collision gate final;
- mutation smoke: 8/8 KILLED;
- synthetic V1 50k nodes: DOM/transient/mmap com mesmo SHA-256 do output;
- CLI parity tests com insert/remove/reorder/change;
- forced digest-collision unit gate.
