# ADR-0005 — Modularização de Pacote (`src/tare_dialog`) e Aceleração de Performance (`orjson`, `networkx`, `rich`, `pydantic`)

**Status:** ACCEPTED  
**Data:** 2026-08-18  
**Escopo:** `tare.tools.dialog-engine`

---

## 1. Contexto & Desafio

Com a implementação da estratégia de Distribuição Dupla ([ADR-0004](0004-dual-distribution-strategy-modular-and-ephemeral.md)), a restrição artificial de "zero dependências externas" na base de código de desenvolvimento principal tornou-se desnecessária.

Executar o parsing de JSONs com mais de 28.000 nós (83MB+) e dezenas de milhares de expressões SpEL em Python puro sem extensões em C/Rust apresentava oportunidades claras de aceleração e modernização de Developer Experience (DX).

---

## 2. Decisão Arquitetural

1. **Estruturação no Padrão `src-layout` (`src/tare_dialog`):**
   - Agrupamento dos módulos soltos da raiz em um pacote canônico com namespaces claros (`tare_dialog.explorer`, `tare_dialog.diff_engine`, `tare_dialog.validator`, `tare_dialog.spel`, `tare_dialog.graph`, `tare_dialog.triage`, `tare_dialog.cli`).
   - Manutenção de shims de retrocompatibilidade total na raiz (`watson_*.py`) para não quebrar scripts ou integrações legadas.

2. **Aceleração com Bibliotecas de Alta Performance:**
   - **`orjson` (Rust C-Extension):** Substituição transparente do `json` padrão no carregamento e cálculo de digests (`load_json()`, `stable_item()`), acelerando o parsing em 1.37x em arquivos de 166MB.
   - **`networkx`:** Modela o fluxo de diálogo como um `DiGraph`, fornecendo algoritmos eficientes de detecção de ciclos (`find_graph_cycles()`), componentes fortemente conexos e análise de alcançabilidade.
   - **`pydantic` v2:** Modelagem tipada e validação de esquemas de nós, respostas ricas e componentes universais.
   - **`rich`:** Interface de linha de comando com tabelas formatadas em cores, painéis e syntax highlighting (`--format rich`, `--rich`).

3. **Otimizações Internas de AST & SpEL:**
   - **LRU Cache (`@functools.lru_cache`):** Armazena em cache os tokens e diagnósticos de sintaxe SpEL repetidos em milhares de nós.
   - **Slotted Dataclasses (`slots=True`):** Redução drástica da pegada de memória de instâncias `Token` e nós.

---

## 3. Consequências & Ganhos

* **100% de Paridade Semântica:** A suíte de 132 testes automatizados continuou com 100% de aprovação (132/132 PASS).
* **Compatibilidade Completa:** O builder de distribuição efêmera (`scripts/build_standalone.py`) continua gerando o artefato autônomo `dialog_engine_standalone.py` e o executável `dialog_engine.pyz` para o ChatGPT Code Interpreter e Copilot.
