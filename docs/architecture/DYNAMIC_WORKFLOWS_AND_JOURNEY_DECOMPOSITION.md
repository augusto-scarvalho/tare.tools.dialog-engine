# tare.tools.dialog-engine — Arquitetura de Decomposição de Jornadas, Workflows Dinâmicos e Transpilação de SpEL

**Documento:** `ARCH-DIALOG-ENGINE-002`  
**Classificação:** Especificação Arquitetural e Design Normativo  
**Status:** PROPOSTO / EM RATIFICAÇÃO  
**Autores:** Arquiteto de Sistemas Conversacionais & Antigravity Swarm  
**Data:** 2026-08-18  

---

## 1. Visão Geral e Desafio da Indústria

Árvores de diálogo corporativas (como IBM Watson Assistant Classic, watsonx Assistant Actions, Rasa, Botpress e autômatos aninhados proprietários) acumulam décadas de complexidade acidental:
1. **Monólitos com 28.000+ Nós:** Dificuldade extrema de manutenção, alta latência de diff e alto risco de regressão silenciosa.
2. **Acoplamento a Expressões de Script (SpEL):** Lógica de negócio crítica embutida diretamente em strings de templates (`<? ... ?>`) dentro do JSON de diálogo.
3. **Fusão Indevida de Intenção e Implementação:** A "Jornada de Negócio" (o objetivo do usuário) fica aprisionada na tecnologia do autômato de diálogo.

O **`tare.tools.dialog-engine`** introduz a arquitetura de **Decomposição Topológica de Jornadas, Workflows Dinâmicos Baseados em Tarefas e Transpilação Desacoplada de SpEL**, viabilizando a modernização segura e progressiva de monólitos conversacionais.

---

## 2. Diagrama Arquitetural Geral

```text
  ÁRVORE MONOLÍTICA LEGADA (28k+ nós com SpEL embutido)
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │ Watson V1 Classic / V2 Actions / Rasa / Autômatos Corporativos Aninhados               │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                       1. DECOMPOSIÇÃO TOPOLÓGICA DE JORNADA
                                             ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │  Sub-Jornadas Canônicas Desacopladas (Jornada de Negócio != Autômato)                   │
  │  • Contratos Declarativos SDD / BDD                                                    │
  │  • Isolamento de Subgrafos Acíclicos com Envelopes de Contexto                         │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                       2. PIPELINE DE EXTRAÇÃO E TRANSPILAÇÃO DE SPEL
                                             ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │  Decomposição em 4 Estágios:                                                           │
  │  • Tipo A (Guarda Pura)        ➔ Transpilação Nativa (Python / TS / Go)                │
  │  • Tipo B (Redutor de Estado)  ➔ Containers Efêmeros / WASM (FaaS)                     │
  │  • Tipo C (Integração/Side-Eff)➔ Conectores MCP / Webhooks OpenAPI 3.0                 │
  │  • Sincronização Atômica       ➔ CAS Context Delta Merge                               │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                       3. WORKFLOWS DINÂMICOS (BLUEPRINT-FIRST-MODEL-SECOND)
                                             ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │  Grafo de Tarefas Conversacionais (Task-Oriented Dialog Graph)                         │
  │  • Blueprint Determinístico: Regras de negócio, invariantes e conformidade             │
  │  • Slots Dinâmicos Tipados: Atuação generativa probabilística restrita por políticas    │
  │  • Decomposição On-Demand (ADaPT): Re-decomposição automática sob falha ou ambiguidade │
  └────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                       4. VERIFICAÇÃO CONTÍNUA & CHAOS TESTING
                                             ▼
  ┌────────────────────────────────────────────────────────────────────────────────────────┐
  │  Suite de Conformance & Falsificação (tare_dialog)                                     │
  │  • 127+ Testes Automatizados / 12 Clusters de Taxonomia de Validação                   │
  │  • Dual-Run Regression Testing (SpEL Legado vs Código Transpilado)                     │
  └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Os Quatro Pilares Técnicos

### 3.1 Separação Ontológica: "Jornada de Negócio" $\neq$ "Árvore de Diálogo"
- A árvore de diálogo é apenas uma representação física contingente.
- A **Jornada de Negócio** é o contrato formal (SDD/BDD) que declara:
  - **Objetivo:** Meta a ser atingida pelo usuário (ex: `segunda_via_boleto`, `reativacao_plano`);
  - **Pré-condições:** Estado inicial e autenticação requerida;
  - **Mutações de Contexto:** Variáveis esperadas na conclusão;
  - **Critérios de Sucesso:** Mensagens canônicas emitidas e status terminal.

### 3.2 Desconstrução e Transpilação de SpEL em 4 Estágios
1. **Extração de AST & Análise de Pureza:**
   - O módulo `tare_dialog.spel` faz o parsing da string SpEL para uma AST tipada.
   - Classifica em:
     - **Tipo A (Guarda Pura):** Predicado booleano sem I/O.
     - **Tipo B (Transformador de Estado):** Computação pura em memória (filtros, reduções, datas).
     - **Tipo C (Ação Impura / Efeito Colateral):** Chamada de webhook ou I/O externo.
2. **Task-Oriented Intermediate Representation (IR):**
   - Transforma a expressão em um manifesto declarativo com `read_envelope` e `write_delta`.
3. **Três Alvos de Execução:**
   - *Código Nativo:* Compilado diretamente para funções puras Python/TypeScript/Go.
   - *Containers Efêmeros / WASM:* Isolamento estrito de memória ($<32\text{MB}$) e timeout ($<200\text{ms}$).
   - *Webhooks OpenAPI / MCP:* Invocação declarativa com circuit breaker e idempotency keys.
4. **Mesclagem Atômica de Contexto (Context Delta Merge):**
   - Nenhuma função escreve diretamente na memória global. Todas retornam um `ContextDelta` validado e mesclado atomicamente.

### 3.3 Workflows Dinâmicos (Blueprint-First-Model-Second & ADaPT)
- **Blueprint Determinístico:** O orquestrador governa transições de estado, autenticação e regras de compliance.
- **Slots Dinâmicos:** A IA generativa atua exclusivamente no preenchimento de parâmetros, desambiguação de intenções e síntese de respostas.
- **Decomposição On-Demand (ADaPT):** Quando uma etapa do diálogo falha ou detecta ambiguidade, o orquestrador divide o nó em sub-tarefas de clarificação de forma autônoma.

### 3.4 Conformance, Validação Estática e Memória Externa
- **Taxonomia de 12 Clusters:** Validação profunda de referências de catálogo, SpEL, controle de fluxo, reuso de slots condicionais, digressões e deduplicação causal.
- **Sharding Adaptativo:** Processamento paralelo em streaming para grafos com mais de 28.000 nós sem estouro de RAM.
- **Dual-Run Testing:** Garantia matemática de que a versão transpilada produz o mesmo output da versão legada.
