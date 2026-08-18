# ADR-0001 — Adaptive external-memory foundation para Watson Dialog

**Status:** ACCEPTED  
**Data:** 2026-08-15  
**Escopo:** side project Watson Assistant Dialog tools.

## Contexto

O toolkit precisa comparar e analisar exports JSON que podem crescer além do que é confortável para um runtime efêmero. O incumbent DOM é rápido, mas seu footprint escala com a expansão dos dois documentos para objetos Python.

Foram consideradas alternativas como SQLite, pickle, Parquet/Arrow, LMDB e um record spool customizado. O problema concreto, porém, não exige um database canônico: o JSON já é a fonte e precisamos principalmente de structural metadata, random/local access e work partitioning.

## Decisão

Adotar como foundation:

```text
JSON autoritativo
  -> adaptive index backend
       -> transient: one-DOM-at-a-time + temporary JSON records
       -> mmap: source-backed single-pass + temporary local-record spool
  -> compact metadata/digests
  -> CompactGraph
  -> semantic work items/shards
  -> incumbent semantic reducer/oracle
```

DOM continua disponível como fast path e oracle.

## Por que não SQLite como default

SQLite é sólido, mas adiciona um boundary relacional que não corresponde ao workload dominante. Não precisamos de SQL, joins arbitrários nem transações persistentes para o scratch path. Ele continuaria sendo uma opção técnica válida se surgir um workload realmente relacional.

## Por que não pickle

Pickle não resolve indexação sozinho, cria forte coupling ao Python e sua desserialização não é apropriada para dados externos não confiáveis. O side project não precisa dessa superfície.

## Por que não Parquet como foundation

Parquet é excelente para analytics, column projection, compressão e datasets reutilizáveis. O diff operacional, entretanto, começa de um documento JSON hierárquico e frequentemente precisa materializar um record semântico específico. Converter obrigatoriamente cada execução para Parquet adicionaria custo e schema coupling antes de haver evidence de reutilização suficiente.

Parquet permanece candidato a cache/analytics opcional.

## Por que não Arrow IPC como requirement

Arrow IPC é atraente para mmap/zero-copy e hot caches, mas PyArrow é uma dependência pesada comparada à stdlib e não é necessária para correctness. Pode ser accelerator futuro sobre contratos já definidos.

## Por que JSON local spool

Um `TemporaryFile` com records JSON locais:

- é simples de auditar;
- não executa código ao desserializar;
- funciona em Windows/POSIX;
- permite offsets baratos;
- desaparece ao fechar;
- evita rescans de subtrees;
- não impõe schema persistente.

## Digest policy

Digests não são prova de mudança. São rejection filters.

- `nos`: raw-byte local digest para throughput;
- root UUID collections menores: canonical digest para seletividade;
- mismatch sempre passa pelo semantic diff quando necessário.

Essa assimetria permite otimização agressiva sem criar falso negativo.

## Graph partitioning

Não adotar hash UUID como sharding default nem SCC como shard obrigatório.

O planner usa unidades hierárquicas/semânticas, affinity e hard load tolerance. SCC/reachability permanecem análises globais sobre `CompactGraph`.

## Dependências

Foundation: Python stdlib.

Accelerators opcionais aceitos quando disponíveis/evidenciados:

- `orjson` para transient parsing/encoding;
- futuramente ijson/simdjson/Arrow, desde que adapters preservem contracts e fallback.

## Consequências positivas

- pequeno install surface;
- bounded-memory path real;
- Windows first-class;
- rollback simples para DOM;
- performance adaptativa;
- graph plane desacoplado do payload;
- evidence de paridade byte-exata em production-scale input.

## Consequências negativas

- mmap stdlib ainda é mais lento que DOM/transient em máquinas com RAM;
- local spool consome temp disk;
- existem dois backends que precisam de parity gates;
- V1 preserva a semântica order-sensitive histórica em vez de adotar automaticamente matching por `dialog_node`; essa dívida de UX é tratada explicitamente pelo ADR-0002.

## Rollback

Forçar `--engine dom` restaura comportamento incumbent sem reverter source. Também é possível forçar `transient` ou `mmap` para isolar regressões de backend.

## Critérios para revisar esta decisão

Reabrir o ADR se uma das condições ocorrer:

- um cache intermediário reutilizado muitas vezes provar benefício material;
- root collections/records excederem RAM de metadata Python;
- processamento distribuído real exigir durable partition files;
- benchmarks mostrarem dependency opcional com ganho grande e distribuição confiável Windows/Linux;
- um futuro modo V1 identity-aware exigir representação/contrato incompatível com o parity mode atual.
