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

Rodando o exemplo pronto:

```bash
pip install fastapi uvicorn websockets
python examples/counter.py
# abra http://127.0.0.1:8000
```

## API dos componentes

- Um componente é **uma função que recebe `props` (dict) e retorna um único `VNode`** raiz (sem fragmentos/listas na raiz, por simplicidade).
- `h(tag_ou_componente, props, *children)` cria um elemento ou renderiza um subcomponente.
- Props especiais: `className`, `style` (dict em vez de string), `key` (para listas), e handlers `onClick`/`onInput`/`onChange`/`onSubmit`/`onKeyDown`/`onKeyUp`/`onFocus`/`onBlur`.
- `use_state(inicial)` → `(valor, set_valor)`. `set_valor` aceita valor direto ou função `(anterior) -> novo`.
- `use_effect(fn, deps=None)` → roda `fn()` depois do render, quando `deps` mudam (`None` = toda renderização). Se `fn` retornar uma função, ela é usada como cleanup antes do próximo efeito.
- `use_memo(fn, deps)` → memoiza o resultado de `fn()` enquanto `deps` não mudar.

## Rodando os testes

```bash
pip install -r requirements.txt
pytest
```

São 49 testes cobrindo cada módulo isoladamente (`vdom`, `hooks`,
`reconciler`, `renderer`, `diff`) e alguns testes de integração via
`Session` (SSR inicial → clique → patch mínimo, `use_effect` disparando
no momento certo, estado persistindo entre eventos). Um dos testes do
`reconciler` documenta explicitamente a limitação de reordenação de listas
citada abaixo, pra ela não passar despercebida se alguém tentar consertar
no futuro.

## Limitações conhecidas (é um "mini" React de verdade)

- **Diff de listas é por posição**, não por `key` para reordenação — itens que só mudam de lugar são recriados em vez de movidos. Bom o suficiente para listas que crescem/encolhem no fim ou têm itens editados no lugar.
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
