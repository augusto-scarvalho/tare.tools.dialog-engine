# ADR-0003 — Resource-aware auto engine selection

**Status:** ACCEPTED
**Data:** 2026-08-15
**Escopo:** side project Watson Assistant Dialog tools.

## Contexto

O diff passou a ter três caminhos de execução válidos:

- DOM incumbent: maior throughput quando os dois documentos cabem confortavelmente;
- external transient: um DOM por vez + spool, reduzindo coexistência de memória;
- external mmap: source-backed/strict memory fallback.

O comportamento histórico de `--engine auto` era puramente baseado em tamanho: arquivos abaixo de 16 MiB iam para DOM e arquivos acima desse threshold iam para external.

Benchmarks posteriores mostraram que tamanho sozinho não é uma boa proxy de decisão em hardware heterogêneo. Em um benchmark V1 de ~16,8 MiB por export, o DOM foi ~3,23 s enquanto transient ficou ~5,16 s e mmap ~22,3 s; todos produziram bytes idênticos. Uma workstation com dezenas de GiB livres deve poder escolher o fast path sem ser penalizada pelo mesmo cutoff de um runtime efêmero pequeno.

## Decisão

`--engine auto` passa a combinar size floor + recursos disponíveis.

Regra default:

```text
largest file < 16 MiB
    -> DOM

largest file >= 16 MiB
    -> se memória disponível é desconhecida: external
    -> estimar DOM peak = 10 × (current bytes + candidate bytes)
    -> DOM somente se estimated peak <= 30% da RAM atualmente disponível
    -> caso contrário: external
```

Os valores 10× e 30% são safety policy conservadora, não semântica do diff.

Depois que `external` é escolhido, `--index-backend auto` continua decidindo `transient` versus `mmap` independentemente, usando seu próprio envelope de um-DOM-at-a-time.

## Compatibilidade de overrides

### `--engine dom|external`

Override explícito continua tendo precedência total.

### `WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES`

Esse environment knob já existia e funcionava como cutoff determinístico. Sua semântica é preservada:

- se explicitamente definido e o maior arquivo estiver abaixo do valor: DOM;
- se explicitamente definido e o maior arquivo atingir/exceder o valor: external.

Ou seja, resource-aware selection vale para o **default auto policy**, não reinterpreta uma configuração explícita existente.

## Consequências positivas

- hosts com RAM abundante podem preferir throughput do DOM;
- hosts pressionados caem automaticamente para external;
- memória desconhecida resolve conservadoramente;
- não existe branching por vendor/formato;
- overrides antigos continuam determinísticos;
- engine selection e backend selection permanecem camadas distintas.

## Consequências negativas

- `auto` depende de memória disponível no instante da decisão;
- estimativa 10× é conservadora e pode escolher external quando DOM caberia;
- performance pode variar entre runs conforme pressão de RAM do host.

Isso é aceitável porque `auto` é policy de performance/recursos, não contract de resultado. Os outputs de DOM/external possuem parity gates independentes.

## Gates

- small file continua DOM mesmo em host pequeno;
- large file + fat budget pode escolher DOM;
- large file + constrained budget escolhe external;
- memória desconhecida escolhe external;
- explicit `--engine external` vence heuristic;
- environment threshold explícito preserva cutoff histórico.

## Rollback

- forçar `--engine dom`;
- forçar `--engine external`;
- definir `WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES` para recuperar um cutoff de tamanho determinístico.
