# ADR-0006: Adaptador Universal de Esquemas, Desacoplamento Semântico e Mutação sob Demanda

## Status
**Aceito (Accepted)** — Implementado em `src/tare_dialog/schema_adapter.py` e integrado a todos os módulos do Dialog Engine.

---

## Contexto e Problema

Sistemas de IA Conversacional corporativos utilizam uma grande variedade de esquemas JSON e formatos de exportação:
1. **IBM Watson Assistant V1 Classic:** Lista linear flat de `dialog_nodes` com ponteiros relacionais (`parent`, `previous_sibling`) e condições SpEL (`conditions`).
2. **IBM Watson Assistant V2 Actions:** Estruturas baseadas em `actions`, `steps` e `handlers`.
3. **Árvores Corporativas Aninhadas e Customizadas:** Estruturas hierárquicas profundas com nomes em português (`nos`, `filhos`, `condicao`, `contexto`, `variaveisContexto`, `slots`).
4. **Outros Frameworks de Estado (Rasa, Botpress, Dialogflow, Autômatos Genéricos):** Esquemas com `states`, `guards`, `transitions`, `memory`, `branches`.

### O Risco de Acoplamento
Se ferramentas de análise (diff semântico, mutadores, validadores, analisadores de grafos) utilizarem nomes de campos literais fixos (`node.get("condicao")` ou `node.get("filhos")`), o motor torna-se acoplado a um dialeto específico, perdendo sua universalidade e quebrando diante de variações de esquema.

Além disso, em árvores corporativas de escala massiva (mais de 28.000 nós e 80 MB de JSON), operações ingênuas de clonagem antecipada (`deepcopy`) para dezenas de milhares de mutantes resultam em gigabytes de alocação desnecessária de memória RAM.

---

## Decisão de Arquitetura

Implementamos uma **camada de adaptação e desacoplamento semântico** baseada em três pilares fundamentais:

### 1. `SchemaBinding` & `KeyMapping` Agnósticos
Criamos uma abstração declarativa que traduz qualquer esquema de entrada para as primitivas da **Árvore de Sintaxe Abstrata (AST) Universal**:
- **Identificador:** `get_id(node)` ➔ mapeia `dialog_node`, `uuid`, `id`, `state_id`, etc.
- **Título / Nome:** `get_title(node)` ➔ mapeia `title`, `nome`, `name`, `label`.
- **Condição / Guarda:** `get_condition(node)` & `set_condition(node, val)` ➔ mapeia `conditions`, `condicao`, `guard`, `when`.
- **Contexto / Memória:** `get_context(node)` & `set_context_variable(node, k, v)` ➔ mapeia `context`, `contexto`, `variables`, `state`.
- **Hierarquia e Filhos:** `get_children(node)` ➔ mapeia `children`, `filhos`, `branches`, `steps`.
- **Captura e Slots:** `get_slots(node)` ➔ mapeia `slots`, `quadros`, `parameters`.

### 2. Auto-Descoberta de Esquema com Pontuação de Confiança (`SchemaBinding.discover`)
O motor examina as chaves do documento e infere dinamicamente o alinhamento com a AST Canônica, calculando uma pontuação de confiança e permitindo sobreposição explícita do usuário via configuração.

### 3. Materialização de Mutantes sob Demanda (*Lazy On-Demand Mutation*)
Em vez de clonar o documento inteiro na fase de descoberta, cada `RuleMutant` armazena apenas a mutação delta (`node_id`, `new_cond`, `new_ctx_key`, `new_ctx_val`). O documento mutado completo só é materializado sob demanda no momento em que um cenário de teste é executado contra ele, reduzindo o tempo de geração de 29.000 mutantes para menos de **0.6 segundos**.

---

## Diagrama da Arquitetura

```text
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ FORMATO DE ENTRADA DESCONHECIDO (Watson V1, V2, Rasa, Árvores Aninhadas)   │
  └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 🧭 MOTOR DE AUTO-DESCOBERTA & BINDING (SchemaBinding.discover)              │
  │    • Inspeciona chaves estruturais e calcula matriz de alinhamento          │
  │    • Suporta configuração declarativa (KeyMapping) ou inferência automática │
  └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ 💎 AST CANÔNICA UNIVERSAL (UniversalDialogAST & Invariantes Formais)        │
  │    • Todos os módulos operam EXCLUSIVAMENTE sobre accessors universais:     │
  │      [Diff] • [Validador 12-Fases] • [Mutator AST] • [Rule Mutator]         │
  └─────────────────────────────────────────────────────────────────────────────┘
```

---

## Consequências e Benefícios

### Positivas
- **100% Desacoplado:** O motor opera sobre qualquer JSON de diálogo corporativo sem alteração no código fonte.
- **Suporte a Novas Plataformas:** Integração trivial com novos assistentes (Rasa, Botpress, LangGraph) apenas declarando um `KeyMapping`.
- **Desempenho Extremo:** 36.135 nós navegados em 0.10s e 29.202 mutantes gerados em 0.56s em árvores de 83 MB.
- **Auditabilidade e Curadoria:** O manifesto de auditoria (`audit_manifest.json`) rastreia o alinhamento e as decisões de curadores de forma independente do formato do fornecedor.

### Neutras / Compensações
- Documentos completamente atípicos sem nenhuma correspondência com termos comuns de autômatos podem exigir a definição manual de um `KeyMapping`.
