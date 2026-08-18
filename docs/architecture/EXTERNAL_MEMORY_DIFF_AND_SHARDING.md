# External-memory diff, compact graph e semantic work sharding

**Status:** CURRENT para exports legacy onde indicado; OPEN/PROPOSED onde explicitamente marcado.  
**Escopo:** side project `Watson Assistant Dialog Diff`. Não é especificação do tare.tools.  
**Objetivo:** permitir análise semântica de exports Watson grandes com comportamento previsível em workstations, Windows/WSL, CI e runtimes efêmeros com memória/tempo restritos.

## 1. Problema

O formato legado do Watson Dialog é um JSON hierárquico. O documento contém coleções root e uma árvore `nos`, cujos itens podem conter `filhos`, `slots`, filhos de slots, saltos e payloads extensos. O caminho histórico usa `json.load()` e materializa o documento completo.

Esse caminho continua útil e rápido em arquivos pequenos, mas cria quatro problemas quando o export cresce:

1. dois exports comparados simultaneamente podem exigir múltiplas vezes o tamanho codificado em RAM;
2. `--summary-only` reduz saída, não a memória do parsing DOM;
3. scanners byte-a-byte ingênuos podem revarrer a mesma subárvore em cada ancestral;
4. paralelizar antes de reduzir o documento a work items bounded pode multiplicar memória em vez de reduzir latência.

A arquitetura implementada separa source storage, structural indexing, payload materialization, graph topology e work scheduling.

## 2. Invariantes

As seguintes propriedades são requisitos de correctness:

- o JSON original permanece a fonte autoritativa do payload;
- o engine external nunca precisa manter os dois DOMs completos simultaneamente;
- o backend `mmap` não chama `json.load()` para construir seu índice;
- digests são filtros de rejeição, nunca autoridade para declarar uma diferença semântica;
- qualquer digest mismatch pode produzir trabalho extra, mas não pode omitir mudança real;
- o diff detalhado continua passando pelo mesmo `find_differences()` do incumbent;
- o resultado external legacy deve ser semanticamente idêntico ao engine DOM;
- workers recebem apenas records locais bounded, nunca o export inteiro;
- a ordem final é determinada no reducer, não pela ordem de conclusão dos workers;
- graph sharding não altera o grafo nem concede semântica nova; só organiza work units;
- exports reais de produção permanecem fora do Git.

## 3. Visão arquitetural

```text
                  current.json / candidate.json
                            |
                    size + ResourceBudget
                            |
              +-------------+--------------+
              |                            |
          DOM engine                  external engine
        small fast path                    |
              |                 +----------+----------+
              |                 |                     |
              |             transient                mmap
              |          one DOM at a time      strict external-memory
              |                 |                     |
              |           local JSON spool      single-pass source scan
              |                 |              + local JSON spool
              |                 +----------+----------+
              |                            |
              |                    Dialog record index
              |                            |
              |                  digest/change discovery
              |                            |
              |                  changed records only
              |                            |
              |                   bounded worker pool
              |                            |
              +-------------------- deterministic reducer
                                           |
                                      canonical report
```

Um segundo plano compartilha o mesmo structural index:

```text
DialogSourceIndex
      |
      +--> CompactGraph
              |
              +--> structural/global analysis
              +--> semantic shard planner
                      |
                      +--> logical shards > physical workers
```

## 4. Backends de execução

### 4.1 DOM

**CURRENT.** O incumbent usa `json.load()` e mantém os objetos Python completos. É o fast path para arquivos pequenos e o oracle histórico de paridade.

Vantagens:

- implementação simples;
- excelente throughput em arquivos que cabem confortavelmente em RAM;
- comportamento histórico já coberto por testes.

Limitação: a expansão JSON→objetos Python pode consumir várias vezes o tamanho do arquivo e dois documentos podem coexistir durante o diff.

### 4.2 Transient

**CURRENT para legacy external diff.** `DialogTransientIndex` aceita o pico de um DOM por vez quando o `ResourceBudget` detecta headroom suficiente.

Fluxo:

1. parse de um export;
2. flatten dos nodes em records locais;
3. escrita desses records em `TemporaryFile`;
4. captura de metadata/digests compactos;
5. liberação do DOM;
6. repetição para o segundo export.

O transient nunca precisa manter os dois DOMs completos ao mesmo tempo. `WATSON_DIALOG_JSON_PARSER=auto|stdlib|orjson` controla o parser. `orjson` é accelerator opcional e não faz parte do correctness contract.

### 4.3 mmap source-backed

**CURRENT para legacy external diff, preflight, compact graph e sharding.** É o fallback estrito de memória.

O JSON é aberto read-only com `mmap`. O index guarda `RecordRef` e metadata estrutural. O payload completo só é materializado quando uma operação pede explicitamente aquele record.

A partir da otimização de agosto de 2026, o legacy scanner é single-pass para a árvore normal:

- a raiz JSON é percorrida incrementalmente;
- ao encontrar `nos`, o parser desce imediatamente para o array;
- ao encontrar um node, seus campos locais são consumidos uma vez;
- `filhos` e `slots` são processados pelo mesmo cursor e devolvem o offset final ao pai;
- uma subárvore não é primeiro “pulada” inteira e depois lida novamente por cada ancestral.

Se um JSON adverso coloca `filhos`/`slots` antes de `uuid`, o scanner usa um replay controlado daquele range após descobrir o identificador. JSON object ordering não é tratado como contrato semântico.

## 5. Local record spool no mmap

Quando `capture_details=True`, o source index cria um `TemporaryFile` apenas para records locais.

Isso é diferente de materializar um segundo documento ou de usar um banco:

```text
original node
  uuid
  nome
  condicao
  respostas
  ...local fields...
  filhos: [huge subtree]
  slots:  [huge subtree]

                first pass
                    |
                    v
TemporaryFile: {uuid,nome,condicao,respostas,...local fields...}
```

O spool resolve um problema importante: depois de descobrir que um root talvez mudou, extrair seus campos locais não pode revarrer todos os descendentes só para ignorar `filhos`/`slots`.

Propriedades:

- é criado somente quando detalhes/diff exigem acesso local repetido;
- é arquivo temporário anônimo, não store canônico;
- é eliminado no `close()`;
- nenhum pickle é usado;
- nenhum SQL/database é usado;
- o conteúdo é JSON comum;
- memória continua bounded pelo record em processamento + metadata;
- disk usage é observável via `local_spool_bytes` no summary do index.

## 6. Digest strategy: filtro assimétrico

Um digest no engine external serve para **evitar trabalho**, não para provar que há alteração.

### 6.1 Nodes (`nos`): raw-byte rejection digest

Para dezenas de milhares de records, decodificar e recanonicalizar cada campo era CPU dominante. O mmap usa um BLAKE2b sobre:

```text
sorted local field name + original JSON value bytes
```

Campos ignorados como timestamps são excluídos.

A propriedade essencial é:

> digest igual ⇒ os bytes locais relevantes são iguais ⇒ semantic diff pode ser pulado.

Já o inverso não é autoridade:

> digest diferente ⇒ talvez mudou ⇒ execute semantic diff.

Whitespace, `1` vs `1.0`, escape equivalente ou mudança de ordem interna de objeto podem gerar falso positivo. Isso é permitido porque o resultado final ainda passa por `find_differences()`.

### 6.2 Coleções root menores: canonical digest

Em coleções como `entidades`, o benchmark real mostrou que raw bytes criavam muitos falsos positivos apesar de semântica equivalente. Essas coleções têm cardinalidade muito menor que `nos`, portanto o index usa canonicalização JSON para o digest delas.

É uma otimização híbrida baseada em workload:

- grande volume: filtro barato, falsos positivos tolerados;
- coleção menor: filtro mais caro e seletivo.

## 7. Diff legacy external

### 7.1 Matching estrutural

Nodes são identificados por UUID. O index mantém:

- `record_id`/`source_id`;
- parent;
- kind (`dialog_node`, `slot`, `slot_child`);
- sequence;
- jump metadata;
- local size/weight;
- digest;
- byte range/source reference.

Moves são detectados por alteração de parent. Subtree add/remove/move cobre descendentes para evitar double reporting.

### 7.2 Paths

O external reconstrói paths do incumbent:

```text
filhos[uuid=<id>]
slots[uuid=<id>]
```

`legacy_root_and_path()` sobe pelo parent index e retorna root + path relativo.

### 7.3 Parallel changed-record diff

Somente records cujo digest/relação exige inspeção viram tasks.

Uma task contém:

```text
ordinal
root_id
current_local_json_bytes
candidate_local_json_bytes
relative_path
ignored_fields
```

O worker executa o mesmo `find_differences()` do engine DOM. Ele não recebe mmap, file descriptor compartilhado nem documento completo; isso preserva portabilidade para Windows `spawn`.

A fila mantém no máximo aproximadamente `2 × jobs` futures em voo. O reducer ordena por ordinal/path antes de montar o report.

## 8. CompactGraph

O graph plane não carrega responses/payloads. Vértices recebem IDs inteiros e edges usam arrays compactos.

Edge families atuais:

- `contains`;
- `contains_slot`;
- `slot_branch`;
- `folder_entry`;
- `next_evaluation`;
- `jump`.

Algoritmos globais como reachability/SCC devem operar nesse plano compacto. SCC é unidade de análise, não obrigação de shard físico.

## 9. Semantic work sharding

Hash puro por UUID equilibra contagem, mas destrói localidade estrutural. O planner atual cria unidades a partir de subárvores e slots, divide unidades grandes e faz packing com affinity.

Prioridades aproximadas:

```text
contains_slot / slot_branch > contains / folder_entry > next_evaluation > jump
```

Load balance é constraint; affinity é otimização.

Workers físicos e shards lógicos são conceitos distintos. O planner normalmente produz mais shards que workers para reduzir tail latency e permitir distribuição dinâmica.

## 10. ResourceBudget

`watson_dialog_resources.py` detecta CPUs utilizáveis, RAM disponível e espaço temporário quando possível.

Precedência:

```text
CLI explicit > env override > auto-detection > conservative fallback
```

`--jobs auto` não significa `os.cpu_count()`. O objetivo é preservar headroom para parser, OS e outros processos.

Backend auto:

- arquivo pequeno: DOM engine;
- external + RAM confortável: transient;
- external + RAM insuficiente/indeterminada: mmap.

Os thresholds são políticas operacionais, não parte da semântica do diff.

## 11. Evidência de performance

### 11.1 Synthetic deep-tree gate

Dataset sintético legacy:

- 21.845 nodes;
- ~7,82 MB;
- branching factor 4;
- profundidade 7;
- `capture_details=True`.

Mesmo ambiente:

| implementação mmap | wall index | peak RSS |
|---|---:|---:|
| commit anterior `e483319` | 14,83 s | ~138 MiB |
| single-pass | 2,06 s | ~136 MiB |

Speedup aproximado: **7,2×** sem aumento material de RAM.

### 11.2 Production-scale evidence

Dois exports privados, aproximadamente 83 MB cada, foram usados apenas como evidence runtime e permanecem fora do Git.

Após single-pass + hybrid digest + local spool:

- full legacy mmap external: ~34,4 s;
- peak RSS observado: ~342 MiB;
- output: byte-idêntico ao oracle DOM já ratificado;
- SHA-256 do report: `c4f8c19b20630b2031b6bbfc0da38549e96193965689399f2b1e1f75c5a00b68`.

O commit anterior não completava sequer um dos indexes de produção dentro de um teto de 45 s neste runtime; o novo full diff dos dois arquivos completa dentro desse envelope.

Esses números são evidence de uma máquina/runtime, não SLO universal.

## 12. Correctness gates

Antes de promover mudança no external engine:

1. `compileall`;
2. suite completa `unittest`;
3. fixtures legacy flat/nested/slot/move;
4. parity `CompactGraph` legacy/V1;
5. `json.load` forbidden no source index;
6. single-pass gate: `filhos` após `uuid` não pode chamar subtree `value_end`;
7. adversarial-order gate: `filhos` antes de `uuid` continua correto;
8. local-spool gate: changed-root access não pode chamar `object_fields` novamente;
9. external parallel JSON byte determinism;
10. mutation smoke;
11. quando exports privados estiverem disponíveis, parity hash external↔DOM sem persistir conteúdo no repo.

## 13. Segurança e privacidade

- `input/*.json` é ignorado pelo Git;
- `.relay/` contém evidence operacional e também é ignorado;
- benchmarks não devem imprimir labels, conditions, response text ou valores de contexto de produção;
- reports completos de produção ficam em `output/` ou temp e não são commitados;
- temporários do external index são fechados no lifecycle do context manager;
- nenhum deserializer executável como pickle é aceito para dados de cliente;
- o scanner não usa `eval`/`exec` nem faz network calls.

## 14. Windows/POSIX

O foundation usa `mmap`, `TemporaryFile`, `json`, `hashlib`, `array` e multiprocessing/process pool por contratos da stdlib.

Workers recebem bytes e valores simples para funcionar com `spawn` no Windows. Não existe dependência de `fork` para correctness.

## 15. Rollback

O DOM incumbent permanece disponível por:

```bash
--engine dom
```

O external pode ser forçado para:

```bash
--engine external --index-backend transient
--engine external --index-backend mmap
```

Isso permite comparar engines e fazer rollback operacional sem reverter código.

## 16. OPEN / próximos accelerators

### ADAPT: ijson

Um adapter incremental C-backed pode substituir parte do lexical scanning sem mudar `DialogRecordIndex`. No runtime de implementação atual `ijson` não está instalado e a sandbox não possui network egress para instalá-lo; portanto ele **não é CURRENT nem dependency**.

Antes de adoção:

- wheels Windows/Linux devem ser validados;
- parity deve usar os mesmos fixtures;
- backend ausente deve cair explicitamente para stdlib;
- nenhuma mudança de semântica pode depender dele.

### OPEN: simdjson On-Demand

Pode reduzir CPU de parse, mas precisa ser avaliado quanto a lifetime do buffer/input e footprint real. Não é foundation atual.

### ADAPT, não foundation: Arrow IPC / Parquet

Continuam candidatos para cache analítico/reutilizável. Não são necessários para o scratch path atual e não devem substituir o JSON autoritativo sem evidence de benefício.

### RETIRE como defaults

- SQLite como store relacional do scratch path;
- pickle como formato de dados externos;
- raw-byte graph hash sharding;
- `jobs = cpu_count` sem resource budget;
- paralelizar o JSON bruto antes de criar work items semânticos.

## 17. V1 external diff parity

**CURRENT.** A paridade external foi estendida a Dialog API V1 sem reinterpretar `dialog_nodes` como mapa por identidade.

O incumbent trata `dialog_nodes` como uma lista order-sensitive porque seus itens usam `dialog_node`, não `uuid`. O external preserva essa semântica com `OrderedItemRef`, canonical matching token, collision check exato, `SequenceMatcher` compatível e event-plan determinístico.

A implementação é generalizada para root ordered arrays of objects e funciona nos backends `mmap` e `transient`. Pairs alterados são enviados ao mesmo bounded worker pool usado pelo legacy; add/remove materializa somente o item necessário.

Um benchmark sintético com 50.000 nodes (~16,8 MB/export) produziu output byte-idêntico nos três engines/backends testados:

- DOM: ~3,23 s / ~347 MiB;
- transient: ~5,16 s / ~234 MiB;
- mmap: ~22,30 s / ~310 MiB;
- SHA-256 comum: `2d37c77b5fbd57705cd2c1501cd7897fd8ac0154076ebb1113ab7c345020ecba`.

A semântica, collision strategy, compatibility debt e gates estão detalhados em [`V1_EXTERNAL_DIFF_PARITY.md`](V1_EXTERNAL_DIFF_PARITY.md) e ADR-0002.

## 18. Resource-aware engine auto-selection

**CURRENT.** O engine selector não usa mais 16 MiB como decisão suficiente por si só. O threshold default é um floor para considerar external; acima dele a policy estima se os dois DOMs cabem com folga na RAM atualmente disponível.

Default:

```text
< 16 MiB largest -> DOM
>= 16 MiB:
  unknown RAM -> external
  estimated DOM peak = 10 × combined encoded bytes
  estimated peak <= 30% available RAM -> DOM
  otherwise -> external
```

Isso permite que uma workstation grande escolha DOM para throughput enquanto um runtime efêmero escolha external para preservar headroom.

O environment existente `WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES` mantém seu significado histórico de cutoff explícito e, quando definido, não é reinterpretado pela heurística de RAM.

A decisão de engine e a decisão de backend continuam separadas:

```text
engine auto -> DOM ou external
external backend auto -> transient ou mmap
```

Detalhes e rationale: [`../adr/0003-resource-aware-auto-engine-selection.md`](../adr/0003-resource-aware-auto-engine-selection.md).
