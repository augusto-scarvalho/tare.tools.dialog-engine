# 📚 ÍNDICE DE DOCUMENTAÇÃO — TARE.TOOLS.DIALOG-ENGINE

> **Documentação técnica, arquitetura formal e especificações do motor topológico de interação e statecharts de diálogo.**

---

## 🏛️ 1. Decisões Arquiteturais & North Star
* **[`ontology/domain_ontology.yaml`](../ontology/domain_ontology.yaml):** Conceitos e invariantes normativos para descoberta federada. A presença de um conceito não comprova implementação, execução ou cobertura de testes; consulte as fases e evidências dos ADRs proprietários.
* **[`docs/adr/0007-dialog-engine-north-star.md`](adr/0007-dialog-engine-north-star.md):** Especificação da North Star do Dialog Engine (`ADR-047`), AST de conversação, bounded loops e modelo agnóstico de grafos.

---

## 📐 2. Arquitetura & Decomposição
* **[`docs/architecture/DYNAMIC_WORKFLOWS_AND_JOURNEY_DECOMPOSITION.md`](architecture/DYNAMIC_WORKFLOWS_AND_JOURNEY_DECOMPOSITION.md):** Decomposição de fluxos dinâmicos e jornadas de interação conversacional baseada em AST.
* **[`SPEC-DIALOG-001.md`](SPEC-DIALOG-001.md):** Critérios verificáveis para ingestão agnóstica, transições de statechart e quórum multi-seat.
