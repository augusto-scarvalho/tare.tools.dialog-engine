# V1 external diff parity

**Status:** CURRENT
**Data de ratificação:** 2026-08-15
**Escopo:** side project `Watson Assistant Dialog Diff`. Não é arquitetura do tare.tools.

## 1. Objetivo

Adicionar execução external-memory para exports Dialog API V1 sem alterar o contrato histórico de `watson_dialog_diff.py`.

O objetivo desta slice é **paridade**, não redesenho do diff. O engine DOM continua sendo o oracle executável.

## 2. Semântica histórica que precisa ser preservada

O diff histórico trata coleções com objetos `uuid` como mapas por identidade. `dialog_nodes`, porém, usa `dialog_node`, não `uuid`. Portanto o incumbent não o converte em mapa; ele executa `compare_list()` e `SequenceMatcher` sobre a lista em ordem.

Consequências:

- reorder pode produzir mudanças;
- insert/remove é posicional;
- um bloco `replace` compara elementos compartilhados por posição antes de emitir sobras como add/remove;
- matching do `SequenceMatcher` usa `stable_item(item)` com todas as fields, inclusive fields que podem ser ignoradas posteriormente pelo semantic diff;
- `ignored_fields` afeta `find_differences()`, mas não pode alterar o alinhamento histórico do matcher;
- coleções não-UUID possuem um comportamento histórico adicional: suas mudanças são inseridas em `changes[]` durante a comparação e novamente durante o flatten final. Isso é preservado nesta slice porque é parte do output byte-level do oracle.

Esse comportamento pode ser discutido e corrigido futuramente, mas somente como mudança explícita e versionada.

## 3. Pipeline external V1

```text
current/candidate V1 JSON
        |
        +--> root scan / transient flatten
        |
        +--> dialog_nodes ordered item refs
                |
                +--> ordinal
                +--> source/spool byte range
                +--> stable SHA-256 token
        |
        +--> exact collision classification
        |
        +--> SequenceMatcher(tokens)
        |
        +--> ordered work plan
                |
                +--> equal    -> skip
                +--> pair     -> bounded payload task
                +--> delete   -> materialize one item
                +--> insert   -> materialize one item
        |
        +--> ResourceBudget -> bounded process workers
        |
        +--> deterministic event replay/reducer
        |
        +--> incumbent-compatible report
```

## 4. OrderedItemRef

O external index expõe `OrderedItemRef` para arrays root em que ordem é semanticamente relevante para o incumbent.

Conceitualmente:

```text
OrderedItemRef
  ordinal
  start
  end
  stable_digest
```

No backend `mmap`, `start/end` apontam para o source JSON. No `transient`, apontam para o `TemporaryFile` de records.

Nenhum array completo precisa permanecer materializado para o matching.

## 5. Stable matching token

`SequenceMatcher` historicamente compara o resultado de:

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

O external calcula SHA-256 dessa representação item-a-item para manter um token compacto.

### 5.1 Digest não é autoridade de igualdade sem defesa

Usar apenas SHA-256 como elemento do matcher introduziria, ainda que remotamente, uma nova semântica: colisões poderiam transformar dois itens diferentes em `equal`.

Para evitar isso, `_ordered_sequence_tokens()` faz:

1. conta quantas vezes cada digest aparece nas duas sequências;
2. digest que aparece uma única vez globalmente recebe token único e não pode participar de igualdade;
3. digest repetido é verificado contra os **bytes canônicos completos**;
4. cada valor canônico distinto recebe uma equivalence-class própria;
5. `SequenceMatcher` recebe `(class, digest, variant)`.

Assim, uma colisão criptográfica vira condição detectada/classificada, não shortcut silencioso.

A memória necessária para bytes canônicos persistentes fica limitada aos grupos de digest repetidos. Objetos idênticos compartilham uma única key canônica.

## 6. Exact event-plan parity

O external reproduz os opcodes do `SequenceMatcher` e cria uma lista de eventos ordenada.

### equal

Nenhum payload é decodificado para diff.

### replace

O incumbent calcula:

```text
shared = min(current block size, candidate block size)
```

Os `shared` pares são comparados por posição com `find_differences()`. Sobras do bloco viram delete/insert.

O external cria tasks somente para esses pares.

### delete / insert

O item é materializado individualmente apenas quando precisa aparecer em `before` ou `after`.

Em `--summary-only`, payloads de add/remove não são retidos, mas a contagem atômica continua igual ao DOM.

## 7. Paralelismo

Pairs alterados usam o mesmo `_run_payload_tasks()` do legacy external diff.

Worker input:

```text
ordinal
collection key
current item JSON bytes
candidate item JSON bytes
path prefix
ignored fields
```

Isso preserva Windows `spawn`: workers não recebem mmap, file descriptors compartilhados ou índices Python complexos.

Os resultados são recolocados no event plan pela ordem original. Completion order nunca altera o report.

## 8. Backends

### 8.1 mmap

- source-backed;
- não requer `json.load()` do documento completo;
- cada item V1 é canonicalizado isoladamente para o matching digest;
- payload detalhado é lido por range somente quando necessário;
- adequado a hard memory constraints.

### 8.2 transient

- aceita um DOM por vez quando `ResourceBudget` detecta headroom;
- `dialog_nodes` é imediatamente transformado em ordered item records no `TemporaryFile`;
- o DOM é limpo antes de abrir o segundo export;
- tende a ter throughput muito maior que o scanner Python mmap em hosts com RAM suficiente.

### 8.3 auto

O `auto` continua selecionando backend por recursos; V1 não introduz regra especial que contorne o `ResourceBudget`.

## 9. Root fields além de dialog_nodes

A implementação foi generalizada para **ordered arrays of objects**, não hard-coded exclusivamente a `dialog_nodes`.

Quando uma root collection:

1. não pode ser tratada como UUID map pelo contrato existente; e
2. ambos os lados são arrays compostos apenas por objetos;

ela pode usar o mesmo ordered external sequence diff.

Valores escalares, arrays mistos ou outros shapes continuam no fallback semântico existente.

Isso preserva a arquitetura por contrato e evita um sistema paralelo específico de V1.

## 10. Comportamento histórico de collections não-UUID

O incumbent atualmente adiciona atomic changes de collections não-UUID em `result["changes"]` em duas fases. O resultado full pode, portanto, conter duplicação histórica.

O external reproduz esse comportamento deliberadamente para garantir:

```text
external JSON bytes == DOM JSON bytes
```

Não interpretar isso como recomendação de API futura. É compatibility debt documentada.

Uma futura correção deve:

- receber ADR própria;
- introduzir schema/version behavior explícito ou migration path;
- ter golden outputs antigos e novos;
- não ser embutida em otimização de memória/performance.

## 11. Correctness gates adicionados

A slice V1 adiciona gates para:

- field change;
- insert;
- remove;
- reorder;
- mixed replace blocks;
- `--summary-only` com multiple atomic changes;
- ignored timestamp afetando matcher mas não semantic diff;
- mmap/transient parity;
- `--jobs 2` determinism;
- CLI byte parity external↔DOM;
- forced digest collision com canonical-byte discrimination.

## 12. Benchmark sintético ratificado

Dataset Watson-like V1 sintético:

- 50.000 `dialog_nodes`;
- ~16,8 MB por export;
- alterações esparsas em conditions/payload;
- uma inserção;
- uma remoção;
- pequeno reorder;
- metadata root alterada.

Mesmo runtime de implementação:

| Engine/backend | Wall | Peak RSS | Output SHA-256 |
|---|---:|---:|---|
| DOM | ~3,23 s | ~347 MiB | `2d37c77b5fbd57705cd2c1501cd7897fd8ac0154076ebb1113ab7c345020ecba` |
| external transient | ~5,16 s | ~234 MiB | mesmo hash |
| external mmap | ~22,30 s | ~310 MiB | mesmo hash |

Output: 26.964 bytes nos três casos.

Interpretação:

- DOM continua sendo throughput oracle quando RAM é abundante;
- transient reduz o pico observado e preserva bom throughput;
- mmap oferece bounded/source-backed behavior com custo maior de CPU no scanner Python;
- os três produziram **o mesmo arquivo JSON byte por byte**.

Esses números são evidence deste runtime, não SLO universal.

## 13. CURRENT / OPEN

### CURRENT

- external V1 parity para root ordered object arrays;
- `dialog_nodes` order-sensitive parity;
- mmap e transient;
- deterministic parallel pair diff;
- exact digest-collision classification;
- summary-only atomic parity;
- DOM byte-level oracle tests.

### OPEN

- mudar V1 para identity-aware diff por `dialog_node` como **modo novo**, não parity mode;
- accelerator ijson/simdjson;
- benchmark V1 de centenas de MB;
- persistable Arrow/Parquet cache somente se reuse justificar;
- corrigir duplicação histórica de non-UUID `changes[]` sob versioned output contract.
