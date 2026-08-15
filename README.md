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
- `next_evaluation`: próximo irmão, na ordem em que condições podem ser avaliadas;
- `contains_slot` e `slot_branch`: estrutura de slots e de seus filhos;
- `jump`: rota configurada por `uuidEnviarPara`, com o `jumpSelector` original.

Os vértices preservam respostas múltiplas, contagem/tipos de resposta,
componentes, condição, tags, slots e a presença de configuração JSON. Saltos
para UUIDs ausentes ficam também listados em `unresolved_jumps`.
