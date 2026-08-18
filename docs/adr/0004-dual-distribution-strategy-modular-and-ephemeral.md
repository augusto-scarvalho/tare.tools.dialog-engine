# ADR-0004 — Estratégia de Distribuição Dupla: Modular e Efêmera (ChatGPT ADA / M365 Copilot)

**Status:** ACCEPTED  
**Data:** 2026-08-18  
**Escopo:** `tare.tools.dialog-engine`

---

## 1. Contexto & Desafio

O ecossistema `tare.tools.dialog-engine` opera em dois contextos de execução fundamentalmente distintos:

1. **Ambiente de Engenharia / Servidor / CI/CD (Local & Cloud):**
   - Máquinas de desenvolvimento, pipelines de integração contínua (GitHub Actions), orquestradores de teste e agentes autônomos locais (`tare.tools.os`).
   - Requer alta modularidade, sharding adaptativo com mmap para árvores gigantescas (100MB+ JSON), concorrência multi-processo (`--jobs 4`), UI interativa com *SIGNAL Design System* (`triage_viewer.html`) e suíte de testes pytest completa.

2. **Runtimes Efêmeros e Sandboxes de IA (ChatGPT Code Interpreter / ADA & M365 Copilot Studio):**
   - Ambientes descartáveis com restrições severas de isolamento:
     - **Zero Dependências Externas:** Proibição ou impossibilidade de `pip install` em tempo de execução.
     - **Container Efêmero:** Ciclo de vida curto (cold start < 100ms, timeout rígido por célula de código).
     - **Distribuição em Arquivo Único:** Facilidade de upload e importação direta em prompts sem necessidade de descompactar múltiplos módulos (`import dialog_engine_standalone as de`).

---

## 2. Decisão Arquitetural

Adotamos formalmente a **Estratégia de Distribuição Dupla (Dual Distribution Strategy)** gerenciada por um pipeline automatizado de empacotamento (`scripts/build_standalone.py`):

```text
                                 SRC (Modular Codebase - Pure Stdlib)
                ┌─────────────────────────────────────────────────────────────┐
                │ watson_spel.py, watson_dialog_diff.py, watson_dialog_*.py   │
                └──────────────────────────────┬──────────────────────────────┘
                                               │
                      ┌────────────────────────┴────────────────────────┐
                      ▼                                                 ▼
        [DISTRIBUIÇÃO MODULAR (Parruda)]             [DISTRIBUIÇÃO EFÊMERA (Standalone)]
        - pyproject.toml / pytest                    - dist/dialog_engine_standalone.py (monolítico)
        - Memory-mapped sharding                     - dist/dialog_engine.pyz (zipapp executável)
        - Multi-core multiprocessing                 - Single-file zero-install para ChatGPT ADA
        - Interactive HTML triage viewer             - Importável em 1 linha no M365 Copilot
```

---

## 3. Especificação das Distribuições

### 📦 Distribuição A — Modular / Enterprise (Parruda)
* **Público:** Desenvolvedores, Engenheiros de QA, CI/CD e Sistemas Operacionais de Agentes.
* **Componentes:**
  - Pacote Python modular padrão (`pyproject.toml`).
  - Suporte a sharding de memória externa (`watson_dialog_shard.py`, `watson_dialog_external.py`) para árvores com mais de 100.000 nós.
  - Console visual interativo (`triage_viewer.html`) com 14 temas de engenharia.
  - Suíte completa de testes unitários e E2E via pytest.

### ⚡ Distribuição B — Standalone Efêmera (ChatGPT ADA / Copilot)
* **Público:** ChatGPT Code Interpreter, Microsoft 365 Copilot Studio, AWS Lambda, Serverless Edge.
* **Artefatos Gerados:**
  1. `dist/dialog_engine_standalone.py` (~220 KB): Monólito Python puro com todos os motores inlined, sem imports relativos entre módulos locais.
  2. `dist/dialog_engine.pyz` (~50 KB): Executável `zipapp` padrão que roda com `python dialog_engine.pyz <comando>`.
* **Características:**
  - 100% Python Standard Library (`json`, `re`, `argparse`, `dataclasses`, `pathlib`, `collections`, `difflib`, `typing`).
  - CLI unificada com subcomandos: `diff`, `validate`, `explore`, `graph`, `test`.
  - Importação direta no ChatGPT: `from dialog_engine_standalone import explore_document, summarize, validate`.

---

## 4. Consequências & Garantias

* **Paridade Semântica Estrita:** Qualquer evolução no código modular é automaticamente testada e compilada para o monólito com 100% de paridade de comportamento.
* **Portabilidade Extrema:** Qualquer pessoa pode baixar apenas `dialog_engine_standalone.py` e ter todo o motor de diff, SpEL, grafo e validação rodando em segundos em qualquer versão do Python 3.10+ sem instalar nada via pip.
