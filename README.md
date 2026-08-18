<div align="center">

# tare.tools — Dialog Engine

**Árvore de Sintaxe Abstrata (AST) Conversacional Determinística, Motor de Diff Semântico, Avaliador SpEL Seguro, Analisador de Grafos Topológicos, Fuzzer Simbólico por Mutação e Console Mission Control de Triagem para Diálogos e Árvores de Conversação Corporativas.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![High Performance](https://img.shields.io/badge/Accelerated-orjson%20%7C%20networkx%20%7C%20rich-purple.svg)](#performance-e-arquitetura)
[![Tests](https://img.shields.io/badge/Tests-148%20Passed%20(100%25)-success.svg)](#testes-automatizados)
[![Dual Distribution](https://img.shields.io/badge/Dual%20Dist-Modular%20%2B%20Ephemeral%20ADA-orange.svg)](#estratégia-de-distribuição-dupla)
[![Live Web Console](https://img.shields.io/badge/Web%20Console-SIGNAL%20Live-blueviolet.svg)](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/)

<p align="center">
  <a href="#por-que-o-dialog-engine">Por que o Dialog Engine?</a> •
  <a href="#catálogo-de-funcionalidades--benefícios-reais">Funcionalidades & Benefícios</a> •
  <a href="#pilares-arquiteturais">Pilares Arquiteturais</a> •
  <a href="#estratégia-de-distribuição-dupla">Distribuição Dupla</a> •
  <a href="#taxonomia-de-validação-em-12-fases">Taxonomia de Validação</a> •
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
| **Auditoria por Mutação Simbólica** | Inexistente | **Injeção formal de falhas com cálculo de Mutation Score** |
| **Auditoria de Regras de Negócio** | Falso 100% ("test-the-tests ausente") | **Descoberta de pontos cegos e síntese automática de cenários** |
| **Parsing & Serialização de Alta Escala** | Lento em JSON padrão | **Acelerado com `orjson` (Rust) — 166MB em 600ms** |
| **Descoberta de Esquemas & Omnichannel** | Apenas um formato rígido | **Introspecção universal (Watson V1 flat + Corporativo aninhado)** |
| **Execução em Runtimes Efêmeros** | Requer instalação complexa | **Distribuição Standalone de arquivo único para ChatGPT ADA / Copilot** |

---

## Catálogo de Funcionalidades & Benefícios Reais

Cada componente do `tare.tools.dialog-engine` foi projetado para resolver dores críticas de engenharia em ambientes corporativos de missão crítica:

### 1. Auditoria de Regras de Negócio & Descoberta de Pontos Cegos (`audit-rules`)
* **O Problema:** Times de QA frequentemente comemoram "100% dos testes passando", sem saber que seus 10 ou 20 cenários cobrem apenas o caminho feliz, deixando brechas de segurança e regras financeiras totalmente desprotegidas.
* **A Solução do Engine:** O mutador inverte operadores de limite de crédito (`$score >= 750` $\to$ `< 750`), desativa travas de autenticação (`$user_authenticated` $\to$ `true`) e muta intenções de transbordo (`#falar_atendente`). Se todos os testes do cliente continuarem passando, o engine alerta o **Ponto Cego (Blindspot)**.
* **Síntese Automática:** O engine **escreve sozinho o arquivo de teste JSON que faltava** (`--synthesize-gaps`), fechando a brecha sem esforço manual.
* **Exemplo Concreto:**
  ```bash
  dialog-engine audit-rules bot_banco.json --scenarios cenarios.json --synthesize-gaps --gaps-out-dir ./novos_testes/
  ```

### 2. Motor de Mutação Simbólica de AST & Autômatos (`mutate`)
* **O Problema:** Como garantir matematicamente que o validador estático realmente detecta todos os erros e que não gera falsos positivos?
* **A Solução do Engine:** Implementa 7 operadores formais de mutação de grafo ($M_{jump}, M_{topo}, M_{pred}, M_{dormant}, M_{contra}, M_{slot}, M_{meta}$) e calcula o *Mutation Score* (Taxa de Morte).
* **Testes Metamórficos:** O operador neutro $M_{meta}$ aplica variações cosméticas no JSON para provar rigorosamente que o motor mantém **Zero Falsos Positivos**.
* **Exemplo Concreto:**
  ```bash
  dialog-engine mutate tests/fixtures/demo_banking_current.json
  # Resultado: Mutation Score: 100.0% (4/4 KILLED, 1 METAMORPHIC PASS)
  ```

### 3. Motor de Diff Semântico AST sem Ruído (`diff`)
* **O Problema:** Um `git diff` de 5.000 linhas em JSON após um curador renomear um nó ou reordenar propriedades na interface gráfica torna revisões de PR inviáveis.
* **A Solução do Engine:** Indexa todos os nós por UUID imutável e compara propriedades de forma canônica. Aponta com precisão cirúrgica apenas as adições, remoções e modificações semânticas reais.
* **Exemplo Concreto:**
  ```bash
  dialog-engine diff producao.json candidata.json --format rich
  ```

### 4. Sandbox e Avaliador Seguro SpEL (`spel`)
* **O Problema:** Expressões em Spring Expression Language (`<? $user_score >= 750 ? 'aprovado' : 'analise' ?>`) frequentemente contêm erros de digitação, parênteses desbalanceados ou injeções que travam o runtime do assistente em produção.
* **A Solução do Engine:** Lexer estático com cache LRU que audita sintaxe sem executar código arbitrário, bloqueia acesso a métodos perigosos e trata acessos nulos com semântica *fail-closed*.

### 5. Grafo Topológico & Detecção de Ciclos Infinitos (`graph`)
* **O Problema:** Saltos circulares indiretos (Nó A $\to$ Nó B $\to$ Nó C $\to$ Nó A) criam loops infinitos que travam a sessão do usuário e geram custos astronômicos de infraestrutura.
* **A Solução do Engine:** Modela o diálogo como um dígrafo topológico (`networkx.DiGraph`), encontra ciclos no grafo e exporta representações em JSON e Graphviz DOT.
* **Exemplo Concreto:**
  ```bash
  dialog-engine graph bot.json --output-dot grafo.dot
  ```

### 6. Introspecção e Descoberta Universal de Esquemas (`explore`)
* **O Problema:** Ter ferramentas separadas para o formato flat nativo do Watson Assistant (V1) e para formatos corporativos aninhados.
* **A Solução do Engine:** Converte e navega bidirecionalmente e sem perdas entre esquemas flat (`dialog_nodes`) e aninhados (`nos/filhos/slots`), detectando canais (WhatsApp, Web, Voz) e mídias (carrosséis, botões).

### 7. Console Mission Control SIGNAL (`triage_viewer.html`)
* **O Problema:** Dificuldade de curadores e auditores não-técnicos navegarem em relatórios gigantescos de terminal ou JSON.
* **A Solução do Engine:** Console visual executável em navegador (GitHub Pages) com 14 temas de engenharia, busca instantânea, drawer de inspeção profunda de nós e painel de triagem de mutantes.

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
   │ Motor de Diff AST     │     │ Validador em 12 Fases  │     │ Mutação Simbólica &   │
   │ Semântico com orjson  │     │ com Contrato Único     │     │ Auditoria de Regras   │
   │ (tare_dialog.diff)    │     │ (tare_dialog.validator)│     │ (tare_dialog.mutator) │
   └───────────────────────┘     └────────────────────────┘     └───────────────────────┘
```

---

## Estratégia de Distribuição Dupla

O projeto é disponibilizado em **duas distribuições distintas** ([ADR-0004](docs/adr/0004-dual-distribution-strategy-modular-and-ephemeral.md)):

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📦 DISTRIBUIÇÃO A — PACOTE MODULAR (Ambientes de Engenharia, Servidores, CI)│
│    - Pacote moderno src/tare_dialog com orjson, networkx, pydantic e rich.   │
│    - Suporte a mutate e audit-rules com renderização rica em terminal.      │
│    - Console interativo SIGNAL Mission Control (HTML).                      │
│    - Suíte de 148 testes automatizados (pytest).                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ ⚡ DISTRIBUIÇÃO B — STANDALONE EFÊMERO (ChatGPT ADA & M365 Copilot Sandbox) │
│    - Arquivo único zero-install: dist/dialog_engine_standalone.py (~250 KB) │
│    - Executável portátil ZipApp: dist/dialog_engine.pyz (~57 KB)             │
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

### Executar a Suíte de Testes (148 Testes)
```bash
python -m pytest
```

---

## Referência de Comandos CLI

A CLI `dialog-engine` (ou `tare-dialog`) oferece suporte nativo a terminal rico (`rich`):

### 1. Auditoria de Regras de Negócio & Pontos Cegos (`audit-rules`)
```bash
# Auditar cobertura de regras contra suíte de cenários de teste
dialog-engine audit-rules input/skill.json --scenarios tests/scenarios.json

# Gerar manifesto auditável e sintetizar automaticamente os testes que faltavam
dialog-engine audit-rules input/skill.json \
  --scenarios tests/scenarios.json \
  --audit-out dist/audit_manifest.json \
  --synthesize-gaps \
  --gaps-out-dir dist/novos_testes/
```

### 2. Análise de Mutação Simbólica de AST (`mutate`)
```bash
# Executar mutação formal de AST e calcular Mutation Score
dialog-engine mutate input/skill.json

# Exportar variantes mutantes JSON para testes externos
dialog-engine mutate input/skill.json --output-dir dist/mutants/
```

### 3. Diff Semântico AST (`diff`)
```bash
# Diff visual com terminal formatado em cores
dialog-engine diff input/current.json input/candidate.json --format rich

# Gerar relatório de diff em Markdown
dialog-engine diff input/current.json input/candidate.json --format markdown --output output/diff.md

# Gerar diff estruturado em JSON
dialog-engine diff input/current.json input/candidate.json --format json --output output/diff.json
```

### 4. Validação Estática com Contrato Único (`validate`)
```bash
# Validação rica no terminal com tabela de issues
dialog-engine validate input/skill.json --rich

# Exportar relatório completo de validação em JSON
dialog-engine validate input/skill.json --output output/validation_report.json
```

### 5. Grafo de Fluxo e Detecção de Ciclos (`graph`)
```bash
# Gerar grafo topológico e estatísticas de alcance
dialog-engine graph input/skill.json --output-json output/graph.json

# Exportar visualização Graphviz DOT
dialog-engine graph input/skill.json --output-dot output/graph.dot
```

### 6. Introspecção e Descoberta Universal de Esquemas (`explore`)
```bash
# Introspecção completa de primitivas, canais e mídias
dialog-engine explore input/skill.json

# Converter entre formatos (v1 flat <-> corporativo aninhado)
dialog-engine explore input/skill.json --convert-to v1 --output output/v1_skill.json
```

---

## API da Biblioteca Python

```python
import tare_dialog as td

# 1. Carregar documento com parsing ultra-rápido (orjson)
doc = td.load_json("input/skill.json")

# 2. Executar auditoria de regras contra cenários de teste
scenarios = td.load_json("tests/scenarios.json")
report = td.evaluate_rules_against_scenarios(doc, scenarios)
print(f"Taxa de Proteção por Testes: {report['summary']['test_mutation_score_pct']}%")

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

O projeto inclui o console visual interativo [`triage_viewer.html`](triage_viewer.html), hospedado ao vivo em [GitHub Pages](https://augusto-scarvalho.github.io/tare.tools.dialog-engine/), oferecendo:
- **14 Temas Visuais de Engenharia** (NASA Deep Space, Tokyo Night, Monokai Pro, Synthwave, etc.).
- **Filtros Avançados:** Filtragem por severidade, fase de auditoria, UUID do nó e status de regressão.
- **Painel de Inspeção Profunda:** Visualização do JSON bruto do nó, árvore hierárquica e histórico de mudanças.

---

## Licença

Distribuído sob a licença **Apache-2.0**. Consulte o arquivo [LICENSE](LICENSE) e [NOTICE](NOTICE) para obter detalhes completos.
