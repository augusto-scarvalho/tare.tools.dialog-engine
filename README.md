# Watson Assistant Dialog Diff

Comparador semântico para exports JSON do Watson Assistant Dialog. As coleções
identificadas por `uuid` são comparadas pelo identificador, portanto uma troca
de ordem no arquivo não gera um falso positivo.

## Estrutura

```text
input/
├── current.json       # versão atualmente publicada
└── candidate.json     # versão a avaliar
output/                # relatórios gerados
watson_dialog_diff.py
docs/
├── architecture/EXTERNAL_MEMORY_DIFF_AND_SHARDING.md
├── architecture/V1_EXTERNAL_DIFF_PARITY.md
├── operations/LARGE_EXPORT_PLAYBOOK.md
├── adr/0001-adaptive-external-memory-foundation.md
├── adr/0002-preserve-v1-sequence-diff-parity.md
└── adr/0003-resource-aware-auto-engine-selection.md
```

Os arquivos em `input/` são ignorados pelo Git: exports reais não são
versionados. A suíte usa apenas JSONs sintéticos em `tests/fixtures/`.

## Uso

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json --output output/diff.md
```

O resultado padrão é Markdown e vai para a saída padrão. Para gravar um
relatório de revisão:

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json --output output/diff.md
```

Para obter o diff completo, determinístico e apropriado para automação, gere o
JSON. Ele contém uma lista plana em `changes`, com cada campo, tag, resposta,
mídia/configuração serializada em `json`, inclusão e remoção encontrados.

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json --format json --output output/diff.json
```

Opções úteis:

- `--format json`: gera o diff completo e estruturado para automações.
- `--include-timestamps`: também compara `dataCriacao` e `dataModificacao`.
- `--max-changes 50`: aumenta o número de campos exibidos para cada item
  alterado no relatório Markdown.
- `--summary-only`: reduz o **payload de saída**. Nos utilitários DOM existentes ele não
  transforma o parsing em bounded-memory; para inspeção/particionamento de exports grandes use
  `watson_dialog_shard.py`.
- `--max-input-bytes N`: define limite de tamanho de leitura em bytes. Sem a flag, a policy é
  resolvida por `WATSON_DIALOG_MAX_BYTES` e depois pelo padrão de 50 MiB.
- `--engine auto|dom|external`: `auto` mantém o DOM em arquivos pequenos e, acima de 16 MiB,
  decide DOM×external a partir de uma estimativa conservadora sobre a RAM atualmente disponível.
  `dom` e `external` continuam sendo overrides explícitos.
- `--index-backend auto|transient|mmap`: no engine external, `transient` materializa **um documento
  por vez**, o achata em um spool JSON efêmero e libera o DOM antes de abrir o segundo export;
  `mmap` usa o scanner estritamente bounded-memory. `auto` escolhe a partir de RAM e disco livres.
- `--jobs auto|N`: paraleliza apenas os records efetivamente alterados no diff external. Os workers
  recebem JSON local bounded, nunca o export inteiro.

O código de saída é `0` quando não há diferenças, `1` quando há diferenças e
`2` quando algum arquivo é inválido ou não pode ser lido. Isso permite usá-lo
em pipelines de CI.

## Segurança para Grandes Documentos (Large-Document Safety)

O projeto separa explicitamente **size guard**, **bounded output** e **bounded-memory execution**:

1. **Guardrail de tamanho**: `--max-input-bytes` é aplicado antes do parsing. Sem valor explícito,
   os CLIs respeitam `WATSON_DIALOG_MAX_BYTES` e depois o padrão de 50 MiB.
2. **`--summary-only` nos CLIs DOM**: reduz o resultado emitido, mas não promete sozinho reduzir a
   memória dominante do `json.load()`. Essa distinção evita falso senso de segurança.
3. **Preflight source-backed**: `preflight_check()` usa `DialogSourceIndex` e `mmap`, contando
   estrutura sem `json.load()` do documento inteiro.
4. **External diff adaptativo**: o engine external compara digests primeiro e materializa somente
   records adicionados/removidos/alterados. Em legacy nested ele recompõe paths de `filhos[...]` e
   `slots[...]`, preservando a semântica do diff DOM.
5. **Dois backends de índice**:
   - `mmap`: bounded-memory estrito, stdlib-only. O legacy scanner é single-pass para a árvore
     normal e, quando `capture_details=True`, grava records **locais** em `TemporaryFile` para que
     changed roots não revarram seus descendentes;
   - `transient`: aceita o pico de um DOM por vez quando há headroom, grava records locais em
     `TemporaryFile`, descarta o DOM e só então abre o segundo export. Não usa SQLite/pickle.
   `WATSON_DIALOG_INDEX_BACKEND` pode forçar `mmap` ou `transient`.
6. **Parser adaptativo do transient**: `WATSON_DIALOG_JSON_PARSER=auto|stdlib|orjson`. `orjson` é
   apenas accelerator opcional; em hosts com menos memória o `auto` prefere stdlib para RSS menor.
7. **Digest híbrido**: `nos` usa um rejection digest barato sobre bytes locais; mismatch nunca é
   tratado como prova de mudança e sempre pode cair no diff semântico. Coleções root menores usam
   digest canônico para evitar falsos positivos de serialização.
8. **CompactGraph**: a topologia usa IDs inteiros e arrays compactos para análise/sharding, sem
   carregar respostas e payloads JSON no graph plane.
9. **Compatibilidade**: o caminho DOM atual permanece o fast path e oracle de paridade. O external
   possui paridade completa ratificada para exports **legacy e Dialog API V1**. Em V1,
   `dialog_nodes` preserva deliberadamente a semântica order-sensitive do DOM histórico; um futuro
   diff identity-aware por `dialog_node` deverá ser um modo novo/versionado. `mmap` e a implementação base usam apenas stdlib e funcionam em Windows/POSIX.

## Documentação de arquitetura e operação

A implementação external-memory é documentada como parte do source repo, separada dos reports
operacionais de `.relay/`:

- [`docs/architecture/EXTERNAL_MEMORY_DIFF_AND_SHARDING.md`](docs/architecture/EXTERNAL_MEMORY_DIFF_AND_SHARDING.md): contracts, backends, single-pass scanner, local spool, digest policy, CompactGraph, sharding, correctness gates, benchmarks e próximos accelerators.
- [`docs/architecture/V1_EXTERNAL_DIFF_PARITY.md`](docs/architecture/V1_EXTERNAL_DIFF_PARITY.md): semântica V1 order-sensitive, ordered refs, exact collision handling, event-plan, benchmarks e compatibility debt.
- [`docs/architecture/CONTEXT_SPEL_VALIDATION.md`](docs/architecture/CONTEXT_SPEL_VALIDATION.md): descoberta de `context` em API V1 e no `json` legado normalizado, scanner `<? expression ?>`, política conservadora contra falsos positivos, paths aninhados e gates.
- [`docs/operations/LARGE_EXPORT_PLAYBOOK.md`](docs/operations/LARGE_EXPORT_PLAYBOOK.md): execução segura em exports privados, engine/backend selection, benchmark, parity, Git hygiene e troubleshooting.
- [`docs/adr/0001-adaptive-external-memory-foundation.md`](docs/adr/0001-adaptive-external-memory-foundation.md): foundation external-memory e tradeoffs contra SQLite, pickle, Parquet/Arrow.
- [`docs/adr/0002-preserve-v1-sequence-diff-parity.md`](docs/adr/0002-preserve-v1-sequence-diff-parity.md): decisão de preservar o contrato posicional V1 antes de qualquer identity-aware redesign.
- [`docs/adr/0003-resource-aware-auto-engine-selection.md`](docs/adr/0003-resource-aware-auto-engine-selection.md): policy de escolha DOM×external baseada em tamanho, RAM disponível e overrides explícitos.

Audits, implementation reports e planos de trabalho continuam em `.relay/` e fora do Git; esses
documentos versionados descrevem apenas arquitetura/contratos que devem acompanhar o código.

## Testes e Mutation Suite

```bash
# Executa toda a suíte unitária, large-document e conformance (109+ testes)
python3 -m unittest discover -s tests -p 'test_*.py'

# Execução adaptativa: auto dimensiona subprocessos a partir de CPU/RAM visíveis
python3 tests/run_mutation_tests.py --jobs auto

# Modo rápido (smoke set representativo)
python3 tests/run_mutation_tests.py --smoke --jobs auto

# Evidence incremental + retomada após timeout/interrupção
python3 tests/run_mutation_tests.py --jobs auto --checkpoint-jsonl output/mutation.jsonl --budget-seconds 90
python3 tests/run_mutation_tests.py --jobs auto --checkpoint-jsonl output/mutation.jsonl --resume

# Execução direcionada a um mutante ou com saída JSON
python3 tests/run_mutation_tests.py --mutant timestamps_are_not_ignored
python3 tests/run_mutation_tests.py --json
```

O mutation runner possui 46 mutantes semânticos cobrindo diff, grafo, SpEL, runner, digressões, validação e geração de cenários. `--jobs auto` usa um `ResourceBudget` conservador baseado em CPUs realmente utilizáveis pelo processo, memória disponível e um cap de segurança; `WATSON_DIALOG_MAX_JOBS` ou `--jobs N` permitem override explícito. A fila é dinâmica, cada mutante mantém timeout próprio e `--checkpoint-jsonl` grava evidence append-only assim que o mutante termina. `--resume` só reaproveita registros cujo fingerprint ainda corresponde ao código e à definição da mutação atuais.

Estados continuam explícitos: `KILLED`, `SURVIVED`, `TIMEOUT`, `INVALID_MUTANT` e `HARNESS_ERROR`. Quando `--budget-seconds` impede iniciar todo o conjunto, o runner preserva os concluídos, lista os deferred e retorna código `3` em vez de produzir falso PASS.

## Conformance Corpus e Proveniência Semântica

O projeto inclui um catálogo explícito de proveniência semântica em [`conformance/conformance_catalog.json`](conformance/conformance_catalog.json), mapeando:
- Regras oficiais da documentação IBM Watson Dialog;
- Status de conformidade (`SUPPORTED`, `PARTIAL`, `UNKNOWN`, `OUT_OF_SCOPE`);
- Tipo de oráculo (`ibm_doc_rule`, `observed_runtime`, `simulator_hypothesis`);
- Casos de teste que evidenciam cada comportamento do simulador.


## Grafo compacto e sharding semântico

Para exports grandes ou para planejar execução paralela sem materializar o DOM completo:

```bash
python3 watson_dialog_shard.py input/current.json --summary-only
python3 watson_dialog_shard.py input/current.json --jobs auto --logical-shards auto --output output/shards.json
```

`watson_dialog_shard.py` faz um scan source-backed do JSON com `mmap`, constrói um `CompactGraph`
e separa **workers físicos** de **shards lógicos**. Por padrão existem mais shards que workers para
permitir distribuição dinâmica e reduzir tail latency.

O particionamento é hierárquico e semântico: tenta manter subárvores/slots juntas, divide subárvores
que excedem o peso alvo e usa afinidade ponderada (`contains`/slot > sibling order > jump) como
critério de localidade, mantendo load balance como restrição. Jumps e sibling edges informam a
partição, mas SCCs não são forçadas a virar shards atômicos.

O relatório contém `max_load_ratio`, `edge_cut_ratio`, pesos e resource snapshot. O plano não altera
a semântica do grafo; ele apenas descreve work units. O `build_graph()` detalhado continua sendo o
oracle de paridade. Fixtures legacy e API V1 possuem testes de paridade estrutural exata entre o
`CompactGraph` source-backed e o grafo incumbent.

## Grafo direcionado do diálogo

```bash
python3 watson_dialog_graph.py input/current.json --output output/dialog_graph.json
python3 watson_dialog_graph.py input/current.json --format dot --output output/dialog_graph.dot
```

O JSON do grafo é o formato canônico e determinístico. Ele contém um sumário,
os vértices detalhados e as arestas. Cada aresta contém somente `node`,
`target` e `type`. Os tipos são:

- `contains`: nó filho na árvore do diálogo;
- `folder_entry`: entrada para o primeiro nó de um folder cuja condição foi aceita;
- `next_evaluation`: próximo irmão, na ordem em que condições podem ser avaliadas;
- `contains_slot` e `slot_branch`: estrutura de slots e de seus filhos;
- `jump`: rota configurada por `uuidEnviarPara`, com o `jumpSelector` original.

Os vértices preservam respostas múltiplas, contagem/tipos de resposta,
componentes, condição, tags, slots e a presença de configuração JSON. Saltos
para UUIDs ausentes ficam também listados em `unresolved_jumps`.

Folders reais do Watson são marcados com `folder: true` (e contabilizados em
`summary.folders`). Não são inferidos por terem filhos: `folder` é um tipo
explícito do export; pode ser vazio, ter condição própria e apenas agrupar nós.
No formato DOT eles usam o formato visual `folder` e o prefixo `[folder]`.
Quando um folder possui filhos, a aresta `folder_entry` aponta para o primeiro
nó interno, separando a entrada lógica do folder da relação estrutural
`contains`.

O grafo também expõe `digression_targets`: raízes que aceitam digressão. Elas
não viram arestas entre todos os nós e todas as raízes, pois isso seria uma
relação dinâmica e potencialmente quadrática; os metadados de digressão em
cada vértice permitem decidir a elegibilidade no runner.

O campo `reachability` une o grafo à análise de condições e lista somente nós
comprovadamente inalcançáveis. Um salto `body` é tratado como exceção, pois
executa a resposta do destino sem avaliar a condição dele.

## Análise de condições

```bash
python3 watson_dialog_conditions.py input/current.json --output output/condition_analysis.json
```

O relatório determinístico valida referências a intents, entities e variáveis
de contexto; identifica condições booleanamente impossíveis; e aponta irmãos
que ficam potencialmente inalcançáveis após uma condição `true`. Expressões
dinâmicas que não podem ser provadas são mantidas fora do diagnóstico de erro.
Use `--check-variables` para também comparar referências a variáveis com
`variaveisContexto`; essa opção pode produzir avisos para valores definidos por
integrações externas ou webhooks.

Para executar as expressões SpEL das condições contra um estado de runtime,
forneça `--scenario`. O JSON pode conter `input`, `context`, `intents` e
`entities`; métodos sem implementação segura retornam `unknown`, sem executar
código externo.

```bash
python3 watson_dialog_conditions.py input/current.json --scenario scenario.json --output output/condition_analysis.json
```

## Validação unificada

```bash
python3 watson_dialog_validate.py input/current.json --output output/validation.json
```

Este é o relatório canônico de validação do export inteiro. Cada achado possui
`category`, `code`, `severity`, `node`, `field`, `value` e `message`. Além de
`syntactic` e `semantic`, o relatório usa `provenance` para incerteza estrutural
que deve ser preservada sem ser promovida a erro de produto. O formato é
determinístico e retorna código `1` quando há achados.

A validação é calibrada por confiança. `false` explícito é informação de ramo
desabilitado, não warning de contradição; empates de `sequencia` viram
`legacy_order_ambiguous` por tie-set; shadows/condições duplicadas exigem ordem
inequívoca, path operacional e ausência de entrada Jump observada; e digression
não atribui blocking power a paths/children `INATIVO` ou `REVISAO`. O antigo
warning genérico de `@sys-number` foi substituído por diagnósticos causais para
handler de zero inalcançável, zero explicitamente válido no prompt e mismatch de
tipo document/number. A rationale e os limites estão em
[`docs/architecture/VALIDATION_AUDIT_CALIBRATION.md`](docs/architecture/VALIDATION_AUDIT_CALIBRATION.md).

O validator também identifica erros formais inequívocos em condições SpEL:
aspas não fechadas, parênteses desbalanceados e `AND`/`OR` ou `&&`/`||` sem
operando.

O mesmo gate agora cobre SpEL embutido no `context` dos dialog nodes. Em API V1,
o validator lê `dialog_nodes[].context`; no export legado normalizado, ele abre
o fragmento IBM armazenado em `node.json`/`slot.json` e percorre o `context`
recursivamente. Strings com `<? expression ?>` são verificadas sem executar
SpEL e sem transformar features fora do parser local em falso erro. O scanner de
strings segue a semântica lexical de SpEL: aspas internas são duplicadas (`''` /
`""`) e barra invertida não escapa a aspa seguinte. Isso evita falsos positivos em
expressões como `<? @pattern.literal.replace('\', '') ?>`. Os findings usam
códigos `context_spel_*` e paths precisos como
`json.context["request"]["value"]`.

Em exports legados, valida também no máximo cinco tipos de componente por
resposta condicional e jumps definidos dentro de respostas compatíveis. Em um
payload API V1 que contenha `dialog_nodes`, habilita as regras estruturais de
`parent`, `previous_sibling`, `frame`, `slot`, `response_condition` e
`event_handler`.

As fontes e o inventário de regras da IBM ficam em
[`rules/ibm_watson_dialog.md`](rules/ibm_watson_dialog.md). Elas distinguem o
formato legado de Dialog skill do formato de nós da API.

## Cenários de teste

```bash
python3 watson_dialog_test.py input/current.json tests/fixtures/scenario_cancel.json --output output/test_report.json
```

Um cenário descreve um turno com `input`, `intents`, `entities` e `context`.
Opcionalmente, `expect.selected_node` transforma o cenário em asserção. O
runner avalia os nós raiz em ordem e devolve o nó selecionado e o trace de cada
condição avaliada.

Para uma sessão, use `turns` e `expect.selected_nodes`:

```json
{
  "turns": [
    {"input": {"text": "começar"}, "intents": [{"name": "start"}]},
    {"input": {"text": "sim"}, "intents": [{"name": "yes"}]}
  ],
  "expect": {"selected_nodes": ["start", "confirm"]}
}
```

O estado preserva `context`, ramo filho pendente e slots preenchidos. Folders
são transparentes para a seleção: depois de sua condição, o runner avalia os
nós internos. O runner executa jumps `condition`, `body` e `user_input`, bem
como jumps de respostas condicionais quando o export os representa. Handlers
legados sob slots são avaliados em ordem e aparecem no trace. Para payloads
V1, o runner normaliza `frame`, `slot`, `event_handler` e
`response_condition`; os eventos de slot seguem `focus`, `input`, `filled`,
`generic` e `nomatch`.

Cada request aceita `dialog_stack` no formato da API V1, por exemplo
`[{"dialog_node":"root"}]`, ou uma string como alias de compatibilidade. Ele
identifica o último nó válido da jornada; na próxima request, a avaliação
começa no primeiro filho dele. O runner devolve `dialog_stack_after` com o nó
ainda ativo, ou `root` e `branch_exited: true` quando a branch encerra. Apenas
em slots o stack recebe `state: "in_progress"`; o UUID cru do slot permite
retomar o preenchimento em uma nova request.

Quando uma condição de filho não atende a mensagem, o runner pode iniciar uma
digressão para uma raiz elegível. Os retornos são uma pilha interna e separada
do `dialog_stack`; portanto uma digressão pode iniciar outra e cada término
retoma o ramo imediatamente interrompido. Um destino de digressão pode executar
seu próprio jump; qualquer jump abandona todos os retornos pendentes e segue o
novo fluxo. Quando o destino é o especial `root`, o runner também reinicia a
árvore e devolve `root` no stack.

Callouts não são executados. Cenários podem injetar resultados determinísticos
por nó, evitando rede e código externo:

```json
{
  "effects": {
    "actions": {
      "node-uuid": {
        "context": {"currency": "BRL"},
        "result_variable": "quote_result",
        "result": {"amount": 42}
      }
    }
  }
}
```

O mesmo formato aceita `webhooks` no lugar de `actions`; nesse caso apenas o
objeto `context` é aplicado.

Como guarda contra ciclos, cada turno registra `node_execution` no trace e
interrompe a execução com `node_execution_limit` quando o mesmo UUID ultrapassa
50 execuções. O contador é reiniciado a cada request.

## Gerar cenário até um nó

```bash
python3 watson_dialog_generate_test.py input/current.json UUID_DO_NO --output output/generated_scenario.json
```

O gerador encontra o caminho estrutural até o nó, cria turns com os artefatos
simples das condições e inclui o UUID-alvo em `expect.selected_nodes`. Em
seguida, executa o runner e registra se a asserção gerada passou. Trechos SpEL
que não podem ser sintetizados ficam em `generated.issues`.

## Gerar testes para uma topologia

```bash
python3 watson_dialog_generate_test.py input/current.json --topology output/topology.json --output output/topology_scenarios.json
```

Use o JSON produzido por `watson_dialog_topology.py` como escopo. O gerador cria
um cenário por item, em ordem `leaves_to_root`: filhos, handlers e slots antes
de seus pais e ancestrais. Para testar um slot posterior, inclui os slots
anteriores como pré-requisitos. A saída preserva o resultado individual do
runner para condições ou fluxos que não puderam ser sintetizados.

## Gerar testes a partir do diff

```bash
python3 watson_dialog_generate_diff_tests.py input/current.json input/candidate.json --output output/diff_scenarios.json
```

O comando calcula o diff e usa a versão candidata para criar um cenário para
cada nó afetado. Em mudanças aninhadas, escolhe o nó candidato mais específico
(filho, slot ou handler); mudanças em respostas, tags e mídia exercitam o nó
dono. Remoções e mudanças fora de `nos` que não possuem cenário executável são
mantidas em `uncovered_changes` para auditoria.

## Quem faz jump para um nó

```bash
python3 watson_dialog_jumps.py input/current.json UUID_DE_DESTINO --output output/incoming_jumps.json
```

O resultado lista os UUIDs e nomes dos nós que possuem `uuidEnviarPara` apontando
para o destino, incluindo a condição e o modo (`jump_selector`) de cada jump.

## Topologia de um nó

```bash
python3 watson_dialog_topology.py input/current.json UUID_DO_NO --output output/topology.json
```

Gera o caminho de ancestrais e a subárvore de descendentes apenas pelas relações
de pai, filho, slot, handler de slot e blocos de resposta. Jumps são excluídos.
