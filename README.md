# PyReact

Um mini-framework "React" em Python: você escreve componentes com hooks
(`use_state`, `use_effect`, `use_memo`), o servidor renderiza tudo em HTML
(SSR) e depois mantém a página **interativa de verdade** via WebSocket —
sem você escrever uma linha de JavaScript.

## Como funciona (visão geral)

```
Componente Python (função)
        │  h(...)
        ▼
   VNode (Virtual DOM)
        │  reconciler.py — expande componentes, roda hooks
        ▼
  Árvore "host" (só tags/texto)
        │
        ├─ renderer.py → HTML (primeira carga / SSR)
        └─ diff.py      → patches (depois de cada evento)
                             │
                             ▼
                  client.js aplica no DOM real
```

1. **`vdom.py`** — `VNode` e a função `h()` (hyperscript), equivalente ao
   `React.createElement`.
2. **`hooks.py`** — `use_state`, `use_effect`, `use_memo`, implementados
   com uma lista de "slots" por instância de componente, na ordem de
   chamada (por isso hooks não podem ficar dentro de `if`/`for`).
3. **`component.py`** — `ComponentInstance`: guarda os hooks de uma
   instância viva, persistindo entre re-renders.
4. **`reconciler.py`** — percorre a árvore, chama as funções de
   componente, e produz uma árvore final só com elementos HTML. Cada nó
   recebe um `data-pyid` estável (baseado no caminho na árvore + `key`).
5. **`renderer.py`** — converte a árvore final em uma string HTML, e
   registra os handlers de evento (`onClick`, `onInput`, ...) num
   dicionário indexado por `data-pyid`.
6. **`diff.py`** — compara a árvore antiga com a nova e gera uma lista
   mínima de patches (`set_text`, `update_props`, `insert`, `remove_at`,
   `replace_at`).
7. **`session.py`** — o estado vivo de uma aba: instâncias de
   componentes, árvore atual e handlers.
8. **`app.py`** — servidor FastAPI: `GET /` faz o SSR inicial e cria uma
   sessão; `WS /ws/{session_id}` recebe eventos do navegador, roda o
   handler correspondente, re-renderiza, diffa e manda os patches.
9. **`static/client.js`** — runtime mínimo no navegador: delega eventos
   DOM pro servidor via WebSocket, e aplica os patches recebidos.

## Exemplo de uso

```python
from pyreact import h, use_state, use_effect, PyReactApp

def Counter(props):
    count, set_count = use_state(0)

    def on_click(_value):
        set_count(lambda c: c + 1)

    use_effect(lambda: print(f"mudou para {count}"), deps=[count])

    return h("div", None,
        h("p", None, count),
        h("button", {"onClick": on_click}, "+1"),
    )

app = PyReactApp(Counter, title="Meu app")

if __name__ == "__main__":
    app.run()  # abre em http://127.0.0.1:8000
```

Rodando os exemplos prontos:

```bash
pip install fastapi uvicorn websockets
python examples/counter.py    # contador simples
python examples/todo.py       # lista de tarefas (mostra reordenação por key)
python examples/live_clock.py # relógio e contador que atualizam sozinhos (server push)
# abra http://127.0.0.1:8000
```

## API dos componentes

- Um componente é **uma função que recebe `props` (dict) e retorna um único `VNode`** raiz (sem fragmentos/listas na raiz, por simplicidade).
- `h(tag_ou_componente, props, *children)` cria um elemento ou renderiza um subcomponente.
- Props especiais: `className`, `style` (dict em vez de string), `key` (para listas), e handlers `onClick`/`onInput`/`onChange`/`onSubmit`/`onKeyDown`/`onKeyUp`/`onFocus`/`onBlur`.
- `use_state(inicial)` → `(valor, set_valor)`. `set_valor` aceita valor direto ou função `(anterior) -> novo`.
- `use_effect(fn, deps=None)` → roda `fn()` depois do render, quando `deps` mudam (`None` = toda renderização). Se `fn` retornar uma função, ela é usada como cleanup antes do próximo efeito.
- `use_memo(fn, deps)` → memoiza o resultado de `fn()` enquanto `deps` não mudar.
- `use_interval(callback, seconds)` → chama `callback` a cada `seconds` segundos enquanto o componente estiver na tela (`seconds=None` pausa). Sempre usa a versão mais recente do `callback`.

## Rodando os testes

```bash
pip install -r requirements.txt
pytest
```

São 107 testes cobrindo cada módulo isoladamente (`vdom`, `hooks`,
`reconciler`, `renderer`, `diff`), o ciclo de vida dos componentes, e testes
de integração via `Session` e via WebSocket (`app.py`, com `TestClient`) (SSR inicial → clique → patch mínimo, `use_effect` disparando
no momento certo, estado persistindo entre eventos). Um dos testes do
`reconciler` documenta explicitamente a limitação de reordenação de listas
citada abaixo, pra ela não passar despercebida se alguém tentar consertar
no futuro.

## Reconciliação por `key` (listas)

Quando **todos os filhos de um elemento são elementos** (nenhum texto solto
misturado), o PyReact casa cada filho antigo com o novo pela sua `data-pyid`
(que segue a `key` que você passar, ou a posição quando não há `key`) e
calcula o conjunto mínimo de mudanças usando uma *longest increasing
subsequence* sobre as posições antigas — a mesma técnica usada por
Vue/Inferno. Na prática isso significa: reordenar uma lista gera patches
`move` (o elemento real do DOM é só reposicionado, preservando estado do
próprio elemento como foco e valor de inputs), não remove+insere tudo de
novo. Veja `examples/todo.py` (mover itens pra cima/baixo) pra um exemplo
funcional disso.

Continua valendo a regra de sempre passar `key` estável (o id do dado, não
o índice da lista) pra itens que podem ser reordenados, adicionados ou
removidos no meio — é isso que dá à identidade do elemento uma base que não
depende da posição.

## Server push (o servidor fala primeiro)

Até aqui, toda atualização de tela partia de um evento do navegador (clique,
digitação). Agora o servidor também pode iniciar uma atualização sozinho —
um relógio, um contador, um placar que atualiza porque *algo aconteceu no
servidor*, não porque o usuário mexeu em algo.

```python
from pyreact import h, use_state, use_interval

def Relogio(props):
    agora, set_agora = use_state(lambda: hora_atual())
    use_interval(lambda: set_agora(hora_atual()), 1.0)  # a cada 1s
    return h("p", None, agora)
```

Por baixo do capô: cada `Session` tem um `asyncio.Event` interno. Quando um
`set_state` acontece — seja dentro de um evento de clique, de um
`use_interval`, de um `use_effect` assíncrono (`async def`), ou até de uma
`threading.Thread` comum rodando em paralelo — a sessão "acorda" um laço
dedicado (`_push_loop`) que recalcula o diff e manda os patches pelo mesmo
WebSocket, sem o navegador ter pedido nada.

- **Efeitos assíncronos:** `use_effect` aceita uma função `async def`. Ela
  vira uma tarefa em segundo plano, cancelada automaticamente quando as
  `deps` mudam ou o componente sai da tela — sem vazar `Task`s penduradas.
- **Handlers assíncronos:** `onClick`/`onInput`/etc. também aceitam `async
  def`. Rodam como tarefa própria, então a aba continua respondendo a
  outros cliques enquanto um handler lento "carrega" algo.
- **Threads comuns:** chamar `set_state` de dentro de uma `threading.Thread`
  funciona — a comunicação entre a thread e o event loop usa
  `call_soon_threadsafe`, então não precisa se preocupar com isso.
- **Erros isolados:** uma exceção num efeito, callback de `use_interval` ou
  handler assíncrono vai para o log; não derruba a sessão nem os outros
  componentes.

Veja `examples/live_clock.py` — um relógio e um contador automático
funcionando sem nenhum clique, mais um handler assíncrono que não trava a
interface.

## Ciclo de vida e robustez

- **Cleanup de efeitos:** se um `use_effect` retorna uma função, ela roda antes do próximo disparo do efeito **e** quando o componente sai da tela (ou a sessão é encerrada) — então timers e conexões abertos num efeito não vazam.
- **Handlers de evento:** podem ser `lambda: ...` (sem argumento) ou `lambda valor: ...`; a assinatura é inspecionada, então um `TypeError` de dentro do handler nunca causa uma segunda execução. Se um handler levantar exceção, ela é registrada no log e a sessão continua funcionando.
- **Reconexão:** se o WebSocket cair, o `client.js` reconecta sozinho (espera de 1s, 2s, 4s... até 10s). O servidor mantém a sessão por `session_ttl` segundos (padrão 60) e, na reconexão, manda o HTML completo pra ressincronizar. Se o servidor reiniciou e a sessão não existe mais, a página recarrega sozinha.
- **Sessões órfãs:** sessões cujo WebSocket nunca conectou, ou caiu e não voltou dentro do `session_ttl`, são removidas (com cleanup dos efeitos). Configure com `PyReactApp(App, session_ttl=120)`.

## Limitações conhecidas (é um "mini" React de verdade)

- **Diff de listas** agora casa itens por identidade (`key` ou posição) e minimiza `move`s via LIS — veja a seção acima. A limitação que resta é: sem `key` explícita, a identidade de cada item ainda é baseada na posição, então inserir/remover no MEIO de uma lista sem key desalinha a identidade dos itens seguintes (o problema clássico de "usar o índice como key"). Sempre passe `key` estável quando a lista pode mudar de ordem ou tamanho no meio.
- Um componente deve retornar **um único elemento raiz** (sem suporte a Fragments).
- Sem suporte a Context API, portais, ou renderização assíncrona/streaming.
- Estado vive **na memória do processo do servidor**, por sessão (uma aba = uma sessão). Reiniciar o servidor perde o estado de todas as sessões — não há persistência.
- Sem otimizações tipo `React.memo`/virtualização de listas grandes.

## Estrutura do projeto

```
pyreact/
├── pyreact/
│   ├── __init__.py       # exports públicos (h, use_state, use_effect, PyReactApp, ...)
│   ├── vdom.py           # VNode + h()
│   ├── hooks.py          # use_state, use_effect, use_memo
│   ├── component.py      # ComponentInstance
│   ├── reconciler.py     # resolve componentes -> árvore host
│   ├── renderer.py       # árvore host -> HTML
│   ├── diff.py           # árvore antiga + nova -> patches
│   ├── session.py        # estado de uma sessão/aba
│   ├── app.py            # servidor FastAPI (SSR + WebSocket)
│   └── static/client.js  # runtime no navegador
└── examples/
    └── counter.py        # exemplo funcional
```
