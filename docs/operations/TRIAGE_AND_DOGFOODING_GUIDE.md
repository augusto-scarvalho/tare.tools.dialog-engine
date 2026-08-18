# Guia de Triagem, Dogfooding e Calibração — Watson Dialog Tools

**Status:** Fonte Oficial de Verdade (Source of Truth)  
**Versão:** 1.0  
**Escopo:** Critérios de classificação de ocorrências, ciclo de dogfooding e recalibração contínua das ferramentas de auditoria e validação do Watson Assistant Dialog.

---

## 1. O que é o Processo de Dogfooding & Triagem?

O objetivo da suíte de ferramentas não é apenas alertar sobre possíveis falhas no JSON do Watson Assistant, mas permitir que o revisor humano audite e classifique os achados (*detector hits*) para retroalimentar o validador.

A cadeia de decisão segue o princípio:
$$\text{Detector Hit} \longrightarrow \text{Causa-Raiz} \longrightarrow \text{Interpretação de Runtime/Design} \longrightarrow \text{Impacto no Produto} \longrightarrow \text{Decisão de Calibração}$$

---

## 2. Taxonomia de Decisão (Significado dos Status)

Ao inspecionar cada ocorrência na interface de triagem, você deve categorizá-la em uma das três opções fundamentais:

### 🐞 **1. Bug Confirmado (Defeito Real no Fluxo / Produto)**
* **Definição:** O validador identificou uma falha real que **quebra a jornada, bloqueia o usuário ou degrada o comportamento conversacional em produção**.
* **Responsabilidade:** Conteúdo / Autoria do Watson Dialog.
* **Ação Esperada:**
  1. Registrar na triagem como Bug Confirmado.
  2. Abrir item no backlog do bot para ajuste do fluxo conversacional no Watson Assistant.
* **Exemplos Comuns:**
  - **Zero não capturado:** O prompt pergunta *"Dê uma nota de 0 a 10"*, mas a condição de captura do slot usa `@sys-number` (que no Watson rejeita `0`), tornando impossível responder zero.
  - **Mismatch de tipo de captura:** O slot captura `@sys-number`, mas os nós filhos dependem de `$inputType:document` (PDF/documentos).
  - **Sintaxe SpEL comprovadamente inválida:** Expressões como `@entidade:(valor).literal` ou `@entidade(...)` que falham no runtime da IBM.
  - **Contradição lógica direta:** Condição de habilitação do slot impossível, ex: `$flag && $flag == false`.

---

### 🛡️ **2. Falso Positivo / Intencional (Calibração do Validador)**
* **Definição:** O validador emitiu um aviso, mas o fluxo do bot está **correto e operando conforme o design deliberado pelo time**. A falha está na **suposição ou sensibilidade do validador**.
* **Responsabilidade:** Ferramentas de Auditoria (`watson_dialog_*.py` / Antigravity).
* **Ação Esperada:**
  1. Registrar como Falso Positivo / Intencional.
  2. Adicionar uma nota de *Rationale* explicando o motivo do design.
  3. Exportar a triagem para que o modelo/desenvolvedor ajuste as regras de detecção.
* **Exemplos Comuns:**
  - Nós sentinela ou fallbacks com condição `true` acessados exclusivamente via `Jump` dinâmico proveniente de outro módulo.
  - Variáveis de contexto geradas dinamicamente por webhooks ou integrações de backend (ex: `$integrations`, `$user_claims`).
  - Digressões bloqueadas intencionalmente para assegurar que o usuário conclua o preenchimento de um frame obrigatório.

---

### 📦 **3. Débito Técnico / Backlog (Não Quebra Fluxo Crítico)**
* **Definição:** A ocorrência aponta uma imperfeição real no JSON, mas que **não gera impacto direto na experiência do cliente em produção**. Trata-se de código legado, rascunhos ou desvios de estilo.
* **Responsabilidade:** Débito técnico de arquitetura / Manutenção periódica.
* **Ação Esperada:**
  1. Manter classificado como Débito Técnico / Backlog.
  2. O validador categoriza como severidade `info` ou `provenance`, evitando poluir a fila de prioridades (P0/P1).
* **Exemplos Comuns:**
  - Referências a intents/entidades deletadas dentro de nós marcados como `INATIVO` ou `REVISAO`.
  - Ramos deliberadamente desligados com a condição `false` mantidos como histórico.
  - Irmãos legados com sequências numéricas idênticas onde a ordem relativa não afeta o resultado final.

---

## 3. Como Usar o Console de Triagem (`triage_viewer.html`)

1. **Seleção de Corpus:**
   - Alterne no cabeçalho entre **`CURRENT`** (versão em produção) e **`CANDIDATE`** (versão candidata a release).
2. **Inspeção de Nós (UUID):**
   - Clique no botão **`🔍 Inspecionar Nó`** em qualquer card para abrir a gaveta lateral com:
     - Linhagem (*Breadcrumbs*) e hierarquia completa.
     - Metadados de execução, jumps e digressões.
     - Condição SpEL completa.
     - Slots, variáveis associadas e *event handlers*.
     - Respostas configuradas e sub-nós filhos.
     - Raw JSON do nó com botão de cópia.
3. **Classificação e Anotação:**
   - Clique no botão correspondente (🐞 Bug, 🛡️ Falso Positivo ou 📦 Débito).
   - Insira notas no campo de texto explicativo (essencial para justificar falsos positivos).
   - O progresso é salvo instantaneamente no `localStorage` do navegador.
4. **Exportação das Decisões:**
   - **`📤 Exportar Triagem (JSON)`**: Gera o arquivo `watson_triage_decisions_<corpus>_<data>.json` para ser processado pelo assistente/CLI.
   - **`📄 Relatório (Markdown)`**: Gera um documento executivo formatado para compartilhamento com o time.
