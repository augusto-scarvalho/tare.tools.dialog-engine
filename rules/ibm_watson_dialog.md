# Regras IBM — Watson Assistant Dialog legado

Este catálogo guarda as fontes oficiais e as regras que elas fundamentam para
o projeto. Ele não contém exports, dados de clientes nem cópias extensas da
documentação. Revisado em 2026-08-15.

## Escopo da coleta

A coleta cobre a documentação pública do fluxo **Dialog** (experiência
legada), o modelo de nós da API V1 e os tópicos aos quais essas páginas levam:
árvore e ordem de avaliação, folders, condições e SpEL, respostas, próximos
passos e jumps, slots e handlers, contexto, digressões e restrições estruturais
da API. Documentação de Actions foi excluída, exceto quando uma página de
Dialog a referencia diretamente, pois é outro modelo de execução.

## Índice de fontes oficiais

| Área | Fonte | Uso no projeto |
| --- | --- | --- |
| Criação, condições, respostas e jump | [Creating a dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-overview) | validação, grafo e runner |
| Ordem de processamento | [How your dialog is processed](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-build) | grafo, alcançabilidade e runner |
| Organização e folders | [Improving your conversation](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-tasks) | grafo, topologia e runner |
| Início e fim | [Starting and ending the dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-start) | condições especiais e runner |
| Slots | [Gathering information with slots](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-slots) | validação e runner |
| Digressões | [Controlling the conversational flow](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime) | metadados do grafo e runner |
| Objetos e shorthand | [Expressions for accessing objects in dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-expression-language) | parser/analisador SpEL |
| Métodos SpEL | [Expression language methods for dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-methods) | parser/avaliador SpEL |
| Contexto de runtime | [Personalizing the dialog with context](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-runtime-context) | cenários e variáveis |
| Webhooks | [Making a programmatic call from dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-webhooks) | limites do runner e SpEL |
| Actions chamadas do Dialog | [Calling actions from a dialog](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-dialog-call-action) | respostas condicionais e limites do runner |
| Estrutura/API | [Modifying a dialog by using the API](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-api-dialog-modify) | perfil futuro da API |
| Contrato API V1 | [Watson Assistant V1 API](https://ondeck.console.cloud.ibm.com/apidocs/assistant-v1?code=unity) | tipos de nó e `dialog_stack` |
| Importação da skill | [Adicionar Dialog / classic experience](https://cloud.ibm.com/docs/watson-assistant?topic=watson-assistant-skill-dialog-add) | leitura de export |

## Modelo da árvore e folders

- A avaliação normal percorre os nós de um grupo na ordem definida; se um
  ramo filho não encontra condição verdadeira, o fluxo retorna ao nível base.
- Um **folder é um tipo explícito de nó** (`type: folder` na API; `folder`
  no export legado deste projeto). Não deve ser deduzido por ter filhos.
- Folder pode ser vazio e pode ter condição. Sem condição, equivale a `true`.
  Sua condição precisa ser satisfeita antes de processar o primeiro nó interno.
- Folder somente organiza nós e aplica customizações herdáveis; não muda a
  ordem de avaliação. Nós raiz em folder raiz continuam sendo raiz para o
  runtime, e não filhos do folder.
- `folder: true` é preservado pelo diff, exposto pelo grafo e contado em
  `summary.folders`.

## Condições, SpEL e início de conversa

- Condições de nó têm no máximo 2.048 caracteres.
- `true` é fallback explícito em um grupo. `anything_else` é o fallback de
  fim de diálogo; deve ocorrer depois dos demais nós raiz avaliáveis.
- `conversation_start` é verdadeiro no primeiro turno, independentemente de
  haver mensagem; `welcome` só é verdadeiro no primeiro turno sem entrada de
  usuário. `irrelevant` depende da classificação do serviço.
- Condição que depende apenas de contexto normalmente precisa ser combinada
  com artefato da entrada para que o nó seja acionado.
- Não teste numa condição de nó uma variável que o próprio nó acabou de
  definir; em respostas condicionais, contexto é definido apenas pela resposta
  efetivamente escolhida.
- O Dialog aceita shorthand de intent, entity e contexto e SpEL. O shorthand
  de entity examina a primeira ocorrência; para todas as ocorrências, use a
  expressão completa. Valores `@entity:(...)` não podem conter `)`.
- Variáveis com hífen precisam de `$(nome-com-hifen)` ou
  `context['nome-com-hifen']`. Expressões de regex usam RE2.
- O avaliador deste projeto é propositalmente seguro e parcial: resultado
  `unknown` não significa que o Watson rejeitaria a expressão.

## Respostas, próximos passos e jumps

- Respostas condicionais são avaliadas em ordem dentro do nó. Cada uma pode
  atualizar contexto, usar rich responses e configurar seu próprio Jump to.
- Um jump da resposta condicional tem precedência sobre o jump definido no nó.
- Próximos passos: esperar entrada; pular entrada para o primeiro filho (só
  quando há filho); ou Jump to para outro nó existente.
- Jump para **condition** avalia o alvo e depois seus irmãos; Jump para
  **response** executa a resposta do alvo sem testar a condição; Jump para
  **user input** espera a próxima mensagem e inicia o processamento a partir
  do alvo. Jump para condition voltando para um nó anterior pode criar loop.
- Uma resposta condicional pode ter até cinco tipos de resposta. Por nó, há no
  máximo um Connect to human agent, um Search skill e um Option.

## Slots, handlers e digressões

- Um nó com slots coleta slots em ordem. Slot posterior pode depender de slot
  obrigatório anterior, mas não de slot posterior ou de slot opcional anterior
  que talvez não tenha valor.
- `@sys-number` sozinho não reconhece zero; use comparação `>= 0` quando zero
  for válido. Não reutilize a mesma variável de contexto em slots; limpe as
  variáveis fora do frame para reiniciar o fluxo.
- Handler `true` ou `anything_else` impede o fluxo Not found. Na API, handlers
  de slot são `event_handler`; para o mesmo slot a ordem é `focus`, `input`,
  `filled`, `generic`, `nomatch`.
- Slots bloqueiam digressão por padrão. Digressões também não são permitidas
  quando há filho `true`/`anything_else`, jump, ou Skip user input que force a
  sequência. Apenas nós raiz podem ser alvos de digressão.
- O simulador mantém os retornos de digressão em uma pilha privada: uma
  digressão retornável pode abrir outra, e os términos retornam em ordem LIFO.
  Um alvo pode executar o próprio jump; qualquer jump descarta essa pilha de
  retornos. O destino especial `root` também reinicia a árvore.

## Regras estruturais da API V1

- IDs devem ser únicos; `parent` e `previous_sibling` formam uma árvore e uma
  lista ligada de irmãos válidas. Um nó não pode ser pai ou irmão de si mesmo,
  nem ter pai descendente.
- Tipos admitidos: `standard`, `event_handler`, `frame`, `slot`,
  `response_condition` e `folder`; `standard` é o padrão.
- `frame` deve ter ao menos um filho `slot`; `slot` deve ser filho de `frame`.
  `response_condition` deve ser filho de `standard` ou `frame`.
- `event_handler` e `response_condition` não podem ter filhos. Handlers
  `focus`, `input`, `filled` e `nomatch` pertencem a slot; `generic` pode
  pertencer a slot ou frame.
- O contrato V1 usa `context.system.dialog_stack` como uma lista de objetos
  para o estado do diálogo. O runner deve aceitar esse formato de entrada.

## Cobertura atual deliberada

- O diff é estrutural e genérico: preserva e compara qualquer campo do export,
  incluindo `folder`, tags, respostas e configuração serializada.
- O grafo expõe estrutura, ordem local, slots, jumps, metadados e `folder`.
- A validação cobre um subconjunto seguro das regras de condições, slots,
  JSON, sequências e destinos de jump.
- O runner é um simulador determinístico para exports legados; não é uma
  implementação integral do runtime Watson. Ele trata folders, retoma stack de
  slots, avalia handlers legados sob slots e respeita jump em resposta quando o
  export traz os campos de condição/destino. Para payload V1, normaliza frame,
  slot, response_condition e event_handler, inclusive a ordem dos eventos de
  slot. Digressões usam uma pilha de retorno privada, separada do dialog_stack;
  qualquer jump descarta seus retornos, e jump para `root` reinicia a árvore.
- Webhooks e actions não são invocados pelo runner. Seus resultados precisam
  ser injetados pela fixture do cenário, o que preserva determinismo e impede
  qualquer efeito externo durante teste.
- O runner aplica uma guarda por request: o mesmo UUID pode ser executado até
  50 vezes; a 51ª produz `node_execution_limit` no trace.
