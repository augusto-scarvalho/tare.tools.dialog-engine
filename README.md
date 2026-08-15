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

O código de saída é `0` quando não há diferenças, `1` quando há diferenças e
`2` quando algum arquivo é inválido ou não pode ser lido. Isso permite usá-lo
em pipelines de CI.

## Testes

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/run_mutation_tests.py
```

O segundo comando aplica mutações comportamentais temporárias ao
comparador. A suíte deve falhar para todas elas; caso alguma sobreviva, o
comando retorna erro.

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
`category` (`syntactic` ou `semantic`), `code`, `severity`, `node`, `field`,
`value` e `message`. Ele reúne a análise de condições e acrescenta validações
de configuração JSON, destino de jump, posição de `anything_else` e colisão
de sequência entre irmãos. Também identifica erros formais inequívocos em
condições SpEL: aspas não fechadas, parênteses desbalanceados e `AND`/`OR` ou
`&&`/`||` sem operando. O formato é determinístico e retorna código `1`
quando há achados.

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
