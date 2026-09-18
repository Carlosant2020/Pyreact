"""
Exemplo de uso do PyReact: um contador com incremento/decremento, um passo
configurável via input, e um useEffect que loga no console do servidor
toda vez que o contador muda.

Rode com:
    python examples/counter.py
E abra http://127.0.0.1:8000
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact import h, use_state, use_effect, PyReactApp


def Counter(props):
    count, set_count = use_state(0)
    step, set_step = use_state(1)

    def on_increment(_value):
        set_count(lambda c: c + step)

    def on_decrement(_value):
        set_count(lambda c: c - step)

    def on_step_change(value):
        try:
            set_step(int(value))
        except (TypeError, ValueError):
            pass

    def log_change():
        print(f"[servidor] contador mudou para {count}")

    use_effect(log_change, deps=[count])

    color = "crimson" if count < 0 else "seagreen"

    return h("div", {"style": {"fontFamily": "sans-serif", "padding": "2rem",
                                "maxWidth": "360px", "margin": "0 auto"}},
        h("h1", None, "Contador PyReact"),
        h("p", {"style": {"fontSize": "3rem", "color": color, "margin": "0"}}, count),
        h("div", {"style": {"display": "flex", "gap": "0.5rem", "marginTop": "1rem"}},
            h("button", {"onClick": on_decrement}, "− "),
            h("button", {"onClick": on_increment}, "+ "),
        ),
        h("label", {"style": {"display": "block", "marginTop": "1rem"}},
            "Passo: ",
            h("input", {"value": str(step), "onInput": on_step_change,
                        "style": {"width": "4rem"}}),
        ),
    )


app = PyReactApp(Counter, title="Contador PyReact")

if __name__ == "__main__":
    print("Rodando em http://127.0.0.1:8000")
    app.run()
