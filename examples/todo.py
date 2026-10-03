"""
Exemplo do PyReact: uma lista de tarefas com adicionar, remover e mover
itens pra cima/baixo. Cada item tem uma `key` estável (o próprio id da
tarefa) — é isso que permite ao PyReact mover o <li> de lugar no DOM real
em vez de destruir e recriar a lista inteira a cada mudança.

Rode com:
    python examples/todo.py
E abra http://127.0.0.1:8000
"""
import sys
import itertools
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact import h, use_state, PyReactApp

_next_id = itertools.count(1)


def novo_item(texto):
    return {"id": next(_next_id), "texto": texto, "feito": False}


def TodoItem(props):
    item = props["item"]
    on_toggle = props["on_toggle"]
    on_remover = props["on_remover"]
    on_mover = props["on_mover"]

    estilo_texto = {"textDecoration": "line-through", "opacity": "0.5"} if item["feito"] else {}

    return h("li", {"key": item["id"],
                     "style": {"display": "flex", "alignItems": "center", "gap": "0.5rem",
                               "padding": "0.4rem 0", "borderBottom": "1px solid #eee"}},
        h("input", {"type": "checkbox", "onChange": lambda _v: on_toggle(item["id"]),
                     "checked": item["feito"]}),
        h("span", {"style": {**estilo_texto, "flex": "1"}}, item["texto"]),
        h("button", {"onClick": lambda _v: on_mover(item["id"], -1)}, "▲"),
        h("button", {"onClick": lambda _v: on_mover(item["id"], 1)}, "▼"),
        h("button", {"onClick": lambda _v: on_remover(item["id"])}, "✕"),
    )


def TodoApp(props):
    itens, set_itens = use_state(lambda: [novo_item("Aprender PyReact"),
                                           novo_item("Fazer uma lista de tarefas"),
                                           novo_item("???")])
    texto_novo, set_texto_novo = use_state("")

    def adicionar(_value):
        if texto_novo.strip():
            set_itens(lambda atuais: atuais + [novo_item(texto_novo.strip())])
            set_texto_novo("")

    def alternar(item_id):
        set_itens(lambda atuais: [
            {**it, "feito": not it["feito"]} if it["id"] == item_id else it
            for it in atuais
        ])

    def remover(item_id):
        set_itens(lambda atuais: [it for it in atuais if it["id"] != item_id])

    def mover(item_id, direcao):
        def atualizar(atuais):
            i = next((idx for idx, it in enumerate(atuais) if it["id"] == item_id), None)
            j = i + direcao
            if i is None or j < 0 or j >= len(atuais):
                return atuais
            nova_lista = list(atuais)
            nova_lista[i], nova_lista[j] = nova_lista[j], nova_lista[i]
            return nova_lista
        set_itens(atualizar)

    return h("div", {"style": {"fontFamily": "sans-serif", "maxWidth": "420px",
                                "margin": "2rem auto", "padding": "0 1rem"}},
        h("h1", None, "Lista de tarefas"),
        h("div", {"style": {"display": "flex", "gap": "0.5rem", "marginBottom": "1rem"}},
            h("input", {"value": texto_novo, "onInput": lambda v: set_texto_novo(v),
                        "placeholder": "Nova tarefa...", "style": {"flex": "1"}}),
            h("button", {"onClick": adicionar}, "Adicionar"),
        ),
        h("ul", {"style": {"listStyle": "none", "padding": "0"}}, [
            h(TodoItem, {"key": item["id"], "item": item, "on_toggle": alternar,
                        "on_remover": remover, "on_mover": mover})
            for item in itens
        ]),
    )


app = PyReactApp(TodoApp, title="Lista de tarefas — PyReact")

if __name__ == "__main__":
    print("Rodando em http://127.0.0.1:8000")
    app.run()
