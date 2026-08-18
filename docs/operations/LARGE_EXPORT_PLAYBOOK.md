# Playbook — exports Watson grandes

**Status:** CURRENT operational guidance.  
**Escopo:** uso seguro do side project em arquivos reais/privados.

## 1. Princípio operacional

Exports reais são input local, não source code.

```text
input/current.json
input/candidate.json
```

Esses arquivos são ignorados por `input/*.json`. Não use `git add -f` neles. Fixtures versionadas pertencem exclusivamente a `tests/fixtures/` e devem ser sintéticas/sanitizadas.

## 2. Preflight

Antes de diff completo:

```bash
python3 watson_dialog_shard.py input/current.json --summary-only --max-input-bytes 0
```

ou execute o diff em summary:

```bash
python3 watson_dialog_diff.py \
  input/current.json input/candidate.json \
  --engine external \
  --summary-only \
  --format json \
  --max-input-bytes 0 \
  --output output/summary.json
```

`0` em `--max-input-bytes` desabilita o guard de tamanho conscientemente. Não transforme isso em default global para inputs desconhecidos.

## 3. Escolha de engine

### Automático

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json --engine auto
```

Use como default normal.

### Oracle / arquivos pequenos

```bash
--engine dom
```

Útil para parity e quando RAM não é restrição.

### External com auto backend

```bash
--engine external --index-backend auto
```

O runtime escolhe transient ou mmap a partir de recursos observados.

### Bounded-memory estrito

```bash
--engine external --index-backend mmap
```

Use quando o host é pequeno, efêmero, compartilhado ou o DOM não cabe com folga.

### Throughput com RAM confortável

```bash
--engine external --index-backend transient
```

Aceita um DOM por vez e o descarta antes do próximo.

## 4. Workers

```bash
--jobs auto
```

é preferível a um número fixo. Para auditoria/parity determinística de performance:

```bash
--jobs 1
--jobs 2
```

O conteúdo final deve ser idêntico independentemente de jobs.

## 5. Parser transient

```text
WATSON_DIALOG_JSON_PARSER=auto
WATSON_DIALOG_JSON_PARSER=stdlib
WATSON_DIALOG_JSON_PARSER=orjson
```

`orjson` é opcional. Se for explicitamente solicitado e ausente, a execução deve falhar de modo explícito; não mascarar a configuração.

## 6. Benchmark reproduzível

Capture no mínimo:

- file sizes;
- node/record count;
- selected engine/backend/parser;
- jobs;
- wall time;
- peak RSS quando disponível;
- local spool bytes;
- output bytes/hash;
- Python/OS;
- commit SHA.

Linux/WSL:

```bash
/usr/bin/time -v python3 watson_dialog_diff.py \
  input/current.json input/candidate.json \
  --engine external --index-backend mmap --jobs 2 \
  --format json --max-input-bytes 0 \
  --output output/diff.json
sha256sum output/diff.json
```

PowerShell pode medir elapsed com `Measure-Command`; peak working set deve ser obtido por ferramenta separada/telemetria do processo quando necessário.

## 7. Parity gate com produção

Quando houver autorização para usar exports reais:

1. nunca copiar os JSONs para `tests/fixtures/`;
2. gerar external report em `output/` ou temp;
3. gerar DOM oracle apenas se RAM permitir;
4. comparar hash/bytes;
5. registrar somente metadata não sensível no evidence report;
6. apagar reports completos e cópias temporárias se não forem necessários operacionalmente.

Exemplo:

```bash
python3 watson_dialog_diff.py current.json candidate.json \
  --engine external --index-backend mmap --format json --output external.json
python3 watson_dialog_diff.py current.json candidate.json \
  --engine dom --format json --output dom.json
cmp external.json dom.json
```

## 8. Git hygiene

Antes de commit:

```bash
git status --short
git ls-files input output .relay
git check-ignore input/current.json input/candidate.json
```

O esperado é:

- nenhum export real rastreado;
- nenhum report runtime em `output/` rastreado, exceto `.gitkeep`;
- `.relay/` fora do source history;
- apenas código/docs/tests/fixtures sintéticos staged.

## 9. Falhas esperadas

### Exit 1

Diferenças foram encontradas. Não é erro operacional.

### Exit 2

Input inválido, limite excedido ou configuração/backend impossível.

### Memory pressure

Force:

```bash
--engine external --index-backend mmap --jobs 1
```

### Slow mmap

Confirme commit atual e verifique se single-pass + local spool estão ativos. O mmap é fallback de memória; transient pode ser mais rápido em hosts grandes.

### Temp disk baixo

O diff detalhado mmap usa spool local temporário. Libere espaço ou use outro temp directory pelo mecanismo padrão do sistema antes de executar. Não faça fallback silencioso para dois DOMs se o objetivo era bounded memory.

## 10. Dados sensíveis

Não inclua em issues/chat/evidence:

- texto de respostas;
- nomes/labels reais desnecessários;
- condições com dados de cliente;
- valores de contexto;
- payloads completos.

Use counts, tamanhos, timings, hashes e IDs sintéticos sempre que possível.

## 11. Exports Dialog API V1

O engine external suporta V1 com paridade ao DOM incumbent.

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json \
  --engine external --index-backend auto --jobs auto \
  --format json --output output/v1-diff.json
```

Para parity gate:

```bash
python3 watson_dialog_diff.py input/current.json input/candidate.json \
  --engine dom --format json --output output/v1-dom.json
python3 watson_dialog_diff.py input/current.json input/candidate.json \
  --engine external --index-backend mmap --jobs 2 \
  --format json --output output/v1-external.json
```

Compare os bytes/hashes.

Importante: parity mode preserva a semântica histórica order-sensitive de `dialog_nodes`. Ele **não** trata reorder como semanticamente irrelevante por `dialog_node`. Se a necessidade operacional for identity-aware diff, isso deve ser implementado como modo novo/versionado, não confundido com `--engine external`.

Em hosts com RAM confortável, `transient` tende a ser a escolha de throughput. Em hard memory constraints, force `mmap`. O `auto` decide com `ResourceBudget` e não usa formato V1 como justificativa para ignorar resource limits.

## 12. Como o `--engine auto` decide

Sem override, arquivos pequenos continuam no DOM. Acima do floor default de 16 MiB, o selector considera a RAM disponível no processo:

```text
estimated DOM peak = 10 × (current bytes + candidate bytes)
DOM budget          = 30% da RAM disponível
```

Se a estimativa couber no budget, `auto` pode manter DOM para throughput. Se não couber, ou se a RAM disponível não puder ser medida, escolhe external.

Isso significa que a mesma dupla de arquivos pode corretamente escolher:

- DOM em uma workstation de 64 GiB;
- external em CI/VM menor;
- external + mmap quando até um DOM por vez não cabe com folga.

Para execução reproduzível/auditoria, não dependa da heuristic:

```bash
--engine dom
--engine external --index-backend transient
--engine external --index-backend mmap
```

`WATSON_DIALOG_EXTERNAL_THRESHOLD_BYTES` permanece um cutoff explícito. Quando definido, ele preserva a policy histórica de tamanho e vence a escolha resource-aware default.
