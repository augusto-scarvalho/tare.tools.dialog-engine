# Regras IBM — Watson Assistant Dialog

Esta pasta guarda as fontes que fundamentam as regras automáticas do projeto.
Não contém exports, dados de clientes ou exemplos extraídos dos diálogos.

## Formato legado (Dialog skill)

- [Adicionar Dialog / classic experience](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-skill-dialog-add)
  - upload em UTF-8 sem BOM;
  - limite de 15 MB para upload pela interface; para arquivos maiores, a IBM
    orienta usar a API.
- [Criar diálogo](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-overview)
  - condição com até 2.048 caracteres;
  - `anything_else` é o fallback final;
  - o destino de Jump to deve existir;
  - no máximo cinco tipos de resposta por resposta condicional;
  - no máximo uma resposta Connect to human agent, Search skill e Option por nó.
- [Iniciar e encerrar diálogo](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-start)
  - Welcome e Anything else são nós padrão; a IBM recomenda não remover o
    Anything else.

## Expressões SpEL

- [Linguagem de expressões](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-expression-language)
  - `$variavel` com hífen deve ser acessada como `$(variavel-com-hifen)` ou
    `context['variavel-com-hifen']`;
  - `@entity:(valor)` não pode ser usado se o valor contiver `)`;
  - shorthand de entity considera a primeira ocorrência da entity.
- [Métodos de expressão](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-methods)
  - expressões de regex usam sintaxe RE2.

## Slots e fluxo

- [Slots](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-slots)
  - slots são avaliados na ordem em que aparecem;
  - uma condição de slot pode depender de slot anterior obrigatório;
  - `@sys-number` sozinho não aceita zero; use `@sys-number >= 0` quando zero
    for válido;
  - handlers `true`/`anything_else` impedem o fluxo Not found;
  - não reutilize uma variável de contexto de slot;
  - variáveis de slot precisam ser limpas fora do nó de slots para reiniciar o
    fluxo.
- [Processamento do diálogo](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-build)
  - nós são avaliados em ordem dentro da árvore.
- [Fluxo e digressões](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime)
  - saltos e condições especiais podem bloquear digressões.

## Formato API

- [Modificar diálogo por API](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-api-dialog-modify)
  - `slot` deve ser filho de `frame`;
  - `frame` deve conter slot;
  - `response_condition` e `event_handler` não podem ter filhos;
  - handlers possuem pais e `event_name` permitidos.

As regras do formato API serão implementadas em um perfil próprio quando o
export recebido expuser `type`, `parent`, `previous_sibling` e `event_name`.
