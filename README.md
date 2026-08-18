<div align="center">

# tare.tools — Dialog Engine

**Árvore de Sintaxe Abstrata (AST) Conversacional Determinística, Motor de Diff Semântico, Avaliador SpEL Seguro, Analisador de Grafos Topológicos e Console Mission Control de Triagem para Diálogos e Árvores de Conversação Corporativas.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![High Performance](https://img.shields.io/badge/Accelerated-orjson%20%7C%20networkx%20%7C%20rich-purple.svg)](#performance-e-arquitetura)
[![Tests](https://img.shields.io/badge/Tests-132%20Passed%20(100%25)-success.svg)](#testes-automatizados)
[![Dual Distribution](https://img.shields.io/badge/Dual%20Dist-Modular%20%2B%20Ephemeral%20ADA-orange.svg)](#estratégia-de-distribuição-dupla)
[![Live Web Console](https://img.shields.io/badge/Web%20Console-SIGNAL%20Live-blueviolet.svg)](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/)

<p align="center">
  <a href="#por-que-o-dialog-engine">Por que o Dialog Engine?</a> •
  <a href="#pilares-arquiteturais">Pilares Arquiteturais</a> •
  <a href="#estratégia-de-distribuição-dupla">Distribuição Dupla</a> •
  <a href="#taxonomia-de-validação-em-12-fases">Taxonomia de Validação</a> •
  <a href="#instalação-e-quickstart">Instalação & Quickstart</a> •
  <a href="#referência-de-comandos-cli">Referência da CLI</a> •
  <a href="#api-da-biblioteca-python">API Python</a> •
  <a href="#console-mission-control-html">Console Mission Control</a> •
  <a href="#licença">Licença</a>
</p>

</div>

---

## Por que o Dialog Engine? (A Mudança de Paradigma)

Sistemas de IA Conversacional corporativos (IBM Watson Assistant, árvores de diálogo legadas e grafos de agentes) são máquinas de estado não lineares e profundamente aninhadas, contendo milhares de nós, condições dinâmicas em *Spring Expression Language* (SpEL), slots multi-turnos e digressões recursivas.

Ferramentas tradicionais de diff baseadas em texto (`git diff`) e comparadores de JSON ingênuos falham catastroficamente por três motivos estruturais:

1. **Ruído de Falsos Positivos:** A simples reordenação de chaves JSON ou movimentação de nós irmãos gera milhares de linhas de conflitos falsos.
2. **Cegueira para Expressões SpEL Dinâmicas:** Erros de sintaxe, branches inalcançáveis, contradições de tipo e condições sombreadas passam despercebidos até o momento da execução em produção.
3. **Escala e Colapso de Digressão:** Árvores corporativas massivas (mais de 28.000 nós, JSONs de 80 MB+) esgotam a memória RAM durante o parsing DOM ingênuo, enquanto digressões recursivas corrompem o estado da conversa.

```text
DIFF TRADICIONAL INGÊNUO (Ruído de Chaves & Falsos Positivos)
[Nó A (linha 40)] <--- Caos de Diffs ---> [Nó A (linha 1200)]  [!] Reordenação de chaves cria conflitos inexistentes.

MOTOR DE AST DETERMINÍSTICO DO DIALOG ENGINE (Preservação de Invariantes Semânticos)
   +---> [Intent: #transferencia] ---> [Slot: $valor (@sys-number)] ---> [Condição: $valor > 0]
   |                                                                                │
[Raiz da Árvore] ----------------- (Binding por UUID Determinístico) -------------> [Nó de Sucesso]
   |                                                                                ▲
   +---> [Digressão: #ajuda] --------> (Preservação de Pilha / Retorno) ------------+
```

### Matriz Comparativa

| Capacidade | Diff Ingênuo / Linha a Linha | tare.tools Dialog Engine |
|---|---|---|
| **Resolução de Identidade de Nós** | Linha / índice do array (frágil) | **UUID imutável e ordenação canônica de AST** |
| **Análise de Condições SpEL** | Nenhuma (trata como texto bruto) | **Lexer AST estático e avaliação segura fail-closed** |
| **Topologia & Detecção de Ciclos** | Inspeção manual | **Detecção de ciclos e loops infinitos via NetworkX** |
| **Ciclo de Vida de Slots e Variáveis** | Não rastreado | **Detecção de contradições de tipo e reutilização disjunta** |
| **Parsing & Serialização de Alta Escala** | Lento em JSON padrão | **Acelerado com `orjson` (Rust) — 166MB em 600ms** |
| **Descoberta de Esquemas & Omnichannel** | Apenas um formato rígido | **Introspecção universal (Watson V1 flat + Corporativo aninhado)** |
| **Execução em Runtimes Efêmeros** | Requer instalação complexa | **Distribuição Standalone de arquivo único para ChatGPT ADA / Copilot** |

---

## Pilares Arquiteturais

```text
                                ARQUITETURA DO TARE.TOOLS DIALOG ENGINE
                                
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │  Explorador Universal │ ──► │  Lexer AST SpEL Seguro │ ──► │ Grafo Topológico &    │
   │  de Esquemas e AST    │     │  com Cache LRU         │     │ Detecção de Ciclos    │
   │  (tare_dialog.explorer)│     │  (tare_dialog.spel)    │     │ (tare_dialog.graph)   │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
               │                             │                              │
               ▼                             ▼                              ▼
   ┌───────────────────────┐     ┌────────────────────────┐     ┌───────────────────────┐
   │ Motor de Diff AST     │     │ Validador em 12 Fases  │     │ Console Mission       │
   │ Semântico com orjson  │     │ com Contrato Único     │     │ Control SIGNAL (HTML) │
   │ (tare_dialog.diff)    │     │ (tare_dialog.validator)│     │ (tare_dialog.triage)  │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
```

### 1. Explorador Universal de AST & Descoberta de Esquema (`tare_dialog.explorer`)
Introspector polimórfico e conversor de esquemas bidirecional e sem perdas:
- **Watson V1 Clássico:** Estrutura flat baseada em ponteiros (`dialog_node`, `parent`, `previous_sibling`).
- **Árvores Corporativas Aninhadas:** Hierarquias profundas (`nos`, `filhos`, `respostas`, `slots`).
- **Suporte Multicanal:** Reconhecimento nativo de canais (WhatsApp, Web Chat, Mobile App, Voice, Slack).
- **Componentes Multimídia:** Imagens, carrosséis, botões/opções, pausas e transferência para atendente humano.

### 2. Motor de Diff Semântico AST (`tare_dialog.diff_engine`)
Compara árvores de diálogo por UUID, detectando com precisão adições, remoções e modificações em nós, respostas condicionais, variáveis de contexto, slots e event handlers sem falsos positivos gerados por reordenação de chaves.

### 3. Barreira de Segurança SpEL (`tare_dialog.spel`)
Lexer estático e avaliador seguro para o subconjunto de Spring Expression Language utilizado pelo Watson (`#intent`, `@entity`, `$context`, operadores ternários, métodos de string, expressões regulares):
- **Cache LRU:** Tokenização de alta velocidade para árvores com dezenas de milhares de nós.
- **Proteção Dunder:** Rejeição estrita de travessias `__dunder__` e reflexão.
- **Fail-Closed:** Propagação segura de `UNKNOWN` em anomalias de tempo de execução.

### 4. Grafo Topológico & Análise de Ciclos (`tare_dialog.graph`)
Modela o fluxo da conversa como um grafo direcionado (`networkx.DiGraph`), detectando:
- Ciclos e loops infinitos de jumps (`find_graph_cycles()`).
- Nós inalcançáveis (*dead branches*) por condições booleanas contraditórias.
- Exportação nos formatos JSON e Graphviz DOT.

---

## Estratégia de Distribuição Dupla

O projeto é disponibilizado em **duas distribuições distintas** ([ADR-0004](docs/adr/0004-dual-distribution-strategy-modular-and-ephemeral.md)):

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📦 DISTRIBUIÇÃO A — PACOTE MODULAR (Ambientes de Engenharia, Servidores, CI)│
│    - Pacote moderno src/tare_dialog com orjson, networkx, pydantic e rich.   │
│    - Sharding de memória com mmap para árvores massivas (>100.000 nós).     │
│    - Console interativo SIGNAL Mission Control (HTML).                      │
│    - Suíte de 132 testes automatizados (pytest).                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⚡ DISTRIBUIÇÃO B — STANDALONE EFÊMERO (ChatGPT ADA & M365 Copilot Sandbox) │
│    - Arquivo único zero-install: dist/dialog_engine_standalone.py (~220 KB) │
│    - Executável portátil ZipApp: dist/dialog_engine.pyz (~50 KB)             │
│    - Suba diretamente no Code Interpreter / Sandbox sem precisar de pip!    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Taxonomia de Validação em 12 Fases

O validador estático unificado (`tare_dialog.validator`) opera sob um **contrato único de issues** classificado em 12 fases progressivas:

| Fase | Código de Regra | Descrição do Invariante Semântico |
|---|---|---|
| **Fase 1** | `disabled_condition_false` | Detecta nós desativados inalcançáveis com condição literal `false`. |
| **Fase 2** | `invalid_spel_syntax` | Audita sintaxe estática SpEL (parênteses desbalanceados, aspas abertas). |
| **Fase 3** | `unresolved_jump_target` | Identifica jumps que apontam para UUIDs inexistentes. |
| **Fase 4** | `sys_number_zero_not_captured` | Previne falha onde prompt aceita 0 mas captura `@sys-number` não trata zero. |
| **Fase 5** | `unsatisfiable_slot_enable` | Alerta contradições lógicas em condições de habilitação de slots (`$var && $var == false`). |
| **Fase 6** | `slot_type_contradiction` | Identifica incompatibilidade entre entidade de captura e tipo de entrada. |
| **Fase 7** | `slot_depends_on_later_slot` | Detecta slot cuja condição depende de variável preenchida posteriormente. |
| **Fase 8** | `slot_depends_on_optional_slot`| Alerta dependência de variável capturada por slot anterior opcional. |
| **Fase 9** | `digression_blocked_by_transition` | Audita nós com digressão de saída bloqueados por transição forçada. |
| **Fase 10** | `multiple_first_siblings` | Identifica grupos de nós irmãos com múltiplos nós marcados como primeiro. |
| **Fase 11** | `missing_root_anything_else` | Alerta ausência de nó raiz de fallback com condição `anything_else`. |
| **Fase 12** | `too_many_response_types` | Valida o limite de componentes por bloco de resposta condicional. |

---

## Instalação e Quickstart

### Instalação como Pacote Python
```bash
# Clonar o repositório
git clone https://github.com/augusto-scarvalho/tare.tools.dialog-engine.git
cd tare.tools.dialog-engine

# Instalar dependências de alta performance
pip install -e .
```

### Executar a Suíte de Testes
```bash
python -m pytest
```

---

## Referência de Comandos CLI

A CLI `dialog-engine` (ou `tare-dialog`) oferece suporte nativo a terminal rico (`rich`):

### 1. Introspecção e Descoberta Universal de Esquemas (`explore`)
```bash
# Introspecção completa de primitivas, canais e mídias
dialog-engine explore input/skill.json

# Listar apenas os canais de comunicação identificados
dialog-engine explore input/skill.json --channels

# Listar componentes multimídia e rich responses
dialog-engine explore input/skill.json --multimedia

# Converter entre formatos (v1 flat <-> corporativo aninhado)
dialog-engine explore input/skill.json --convert-to v1 --output output/v1_skill.json
```

### 2. Diff Semântico AST (`diff`)
```bash
# Diff visual com terminal formatado em cores
dialog-engine diff input/current.json input/candidate.json --format rich

# Gerar relatório de diff em Markdown
dialog-engine diff input/current.json input/candidate.json --format markdown --output output/diff.md

# Gerar diff estruturado em JSON
dialog-engine diff input/current.json input/candidate.json --format json --output output/diff.json
```

### 3. Validação Estática com Contrato Único (`validate`)
```bash
# Validação rica no terminal com tabela de issues
dialog-engine validate input/skill.json --rich

# Exportar relatório completo de validação em JSON
dialog-engine validate input/skill.json --output output/validation_report.json
```

### 4. Grafo de Fluxo e Detecção de Ciclos (`graph`)
```bash
# Gerar grafo topológico e estatísticas de alcance
dialog-engine graph input/skill.json --output-json output/graph.json

# Exportar visualização Graphviz DOT
dialog-engine graph input/skill.json --output-dot output/graph.dot
```

### 5. Execução de Cenários de Teste (`test`)
```bash
# Executar cenário determinístico de teste contra o diálogo
dialog-engine test input/skill.json tests/fixtures/scenario.json --output output/trace.json
```

---

## API da Biblioteca Python

```python
import tare_dialog as td

# 1. Carregar documento com parsing ultra-rápido (orjson)
doc = td.load_json("input/skill.json")

# 2. Explorar e normalizar AST
ast_doc = td.explore_document(doc)
print(f"Formato: {ast_doc.source_format} | Nós: {len(ast_doc.nodes)}")

# 3. Executar validação estática em 12 fases
relatorio = td.validate(doc)
print(f"Total de issues encontradas: {relatorio['summary']['issues']}")

# 4. Calcular diff semântico entre duas versões
diff = td.summarize(doc_v1, doc_v2, td.DEFAULT_IGNORED_FIELDS)
print(f"Mudanças: +{diff['summary']['added']} ~{diff['summary']['changed']} -{diff['summary']['removed']}")

# 5. Avaliar expressão SpEL com sandbox seguro
resultado = td.evaluate_condition("$valor > 100 && #confirmar", context={"valor": 150}, intents=["confirmar"])
assert resultado is True
```

---

## Console Mission Control (HTML)

O projeto inclui o console visual interativo [`triage_viewer.html`](triage_viewer.html), construído com o **SIGNAL Design System**, oferecendo:
- **14 Temas Visuais de Engenharia** (NASA Deep Space, Tokyo Night, Monokai Pro, Synthwave, etc.).
- **Filtros Avançados:** Filtragem por severidade, fase de auditoria, UUID do nó e status de regressão.
- **Painel de Inspeção Profunda:** Visualização do JSON bruto do nó, árvore hierárquica e histórico de mudanças.

---

## Licença

Distribuído sob a licença **Apache-2.0**. Consulte o arquivo [LICENSE](LICENSE) e [NOTICE](NOTICE) para obter detalhes completos.
