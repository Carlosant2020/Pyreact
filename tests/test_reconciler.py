import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyreact.vdom import h
from pyreact.hooks import use_state
from pyreact.reconciler import resolve_tree
from pyreact.session import Session


def test_resolve_tree_remove_componentes_deixando_so_host():
    def Filho(props):
        return h("span", None, "oi")

    def Raiz(props):
        return h("div", None, h(Filho, None))

    session = Session(Raiz)
    tree = resolve_tree(h(Raiz, {}), session)

    assert tree.type == "div"
    assert tree.children[0].type == "span"  # nenhum componente sobrou na árvore


def test_resolve_tree_atribui_data_pyid_estavel():
    def Raiz(props):
        return h("div", None, h("span", None, "a"), h("span", None, "b"))

    session = Session(Raiz)
    tree1 = resolve_tree(h(Raiz, {}), session)
    tree2 = resolve_tree(h(Raiz, {}), session)

    assert tree1.props["data-pyid"] == tree2.props["data-pyid"]
    assert tree1.children[0].props["data-pyid"] == tree2.children[0].props["data-pyid"]
    assert tree1.children[0].props["data-pyid"] != tree1.children[1].props["data-pyid"]


def test_estado_do_componente_persiste_entre_resolves():
    def Contador(props):
        count, set_count = use_state(0)
        return h("button", {"onClick": lambda v: set_count(count + 1)}, str(count))

    session = Session(Contador)
    tree1 = resolve_tree(h(Contador, {}), session)
    assert tree1.children[0].props["nodeValue"] == "0"

    # simula o clique chamando o handler registrado na própria árvore
    tree1.props["onClick"](None)

    tree2 = resolve_tree(h(Contador, {}), session)
    assert tree2.children[0].props["nodeValue"] == "1"


def test_componentes_removidos_da_arvore_perdem_instancia():
    def Filho(props):
        use_state(0)  # só pra ocupar um slot de hook
        return h("span", None, "filho")

    def Raiz(props):
        mostrar, set_mostrar = use_state(True)
        children = [h(Filho, None)] if mostrar else []
        return h("div", None, *children)

    session = Session(Raiz)
    resolve_tree(h(Raiz, {}), session)
    assert len(session.instances) == 2  # Raiz + Filho

    # acha a instância da Raiz e desliga o "mostrar"
    raiz_instance = next(i for i in session.instances.values() if i.fn is Raiz)
    raiz_instance.hooks[0]["value"] = False

    resolve_tree(h(Raiz, {}), session)
    assert len(session.instances) == 1  # só a Raiz sobrou


def test_listas_mantem_identidade_quando_a_ordem_nao_muda():
    def Item(props):
        return h("li", {"key": props.get("item_id")}, props["label"])

    def Lista(props):
        items = props.get("items", [])
        return h("ul", None, *[h(Item, {"key": i["id"], "item_id": i["id"], "label": i["label"]})
                                for i in items])

    session = Session(Lista)
    itens = {"items": [{"id": "x", "label": "primeiro"}, {"id": "y", "label": "segundo"}]}
    tree1 = resolve_tree(h(Lista, itens), session)
    ids1 = [c.props["data-pyid"] for c in tree1.children]

    # só muda o texto, mesma ordem/keys -> identidade de cada item se mantém
    itens2 = {"items": [{"id": "x", "label": "PRIMEIRO"}, {"id": "y", "label": "SEGUNDO"}]}
    tree2 = resolve_tree(h(Lista, itens2), session)
    ids2 = [c.props["data-pyid"] for c in tree2.children]

    assert ids1 == ids2


def test_reordenar_lista_atualmente_muda_identidade_por_posicao():
    """Documenta a limitação atual (ver README): o diff/identidade de filhos
    é por posição, não por key — reordenar uma lista faz os itens serem
    tratados como 'novos' na nova posição, em vez de movidos."""
    def Item(props):
        return h("li", {"key": props.get("item_id")}, props["label"])

    def Lista(props):
        items = props.get("items", [])
        return h("ul", None, *[h(Item, {"key": i["id"], "item_id": i["id"], "label": i["label"]})
                                for i in items])

    session = Session(Lista)
    a = h(Lista, {"items": [{"id": "x", "label": "primeiro"}, {"id": "y", "label": "segundo"}]})
    tree1 = resolve_tree(a, session)
    pyid_de_x_antes = tree1.children[0].props["data-pyid"]

    b = h(Lista, {"items": [{"id": "y", "label": "segundo"}, {"id": "x", "label": "primeiro"}]})
    tree2 = resolve_tree(b, session)
    pyid_de_x_depois = tree2.children[1].props["data-pyid"]  # x agora está na posição 1

    # limitação atual: o pyid do item 'x' muda ao mudar de posição
    assert pyid_de_x_antes != pyid_de_x_depois
