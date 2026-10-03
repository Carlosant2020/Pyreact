// Runtime mínimo do PyReact: conecta no WebSocket, aplica patches recebidos
// do servidor e reencaminha eventos do DOM para o servidor decidir o que fazer.

(function () {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const sessionId = window.__PYREACT_SESSION__;
  const SESSION_NOT_FOUND = 4404; // o servidor não conhece mais essa sessão
  let socket = null;
  let attempt = 0;

  function connect() {
    socket = new WebSocket(`${proto}//${location.host}/ws/${sessionId}`);

    socket.addEventListener("open", () => {
      attempt = 0;
    });

    socket.addEventListener("message", (msg) => {
      const data = JSON.parse(msg.data);
      if (data.type === "patches") {
        data.patches.forEach(applyPatch);
      } else if (data.type === "full") {
        // ressincronização após reconectar: troca o conteúdo inteiro
        document.getElementById("pyreact-root").innerHTML = data.html;
      }
    });

    socket.addEventListener("close", (e) => {
      if (e.code === SESSION_NOT_FOUND) {
        // o servidor reiniciou (ou a sessão expirou): o estado se perdeu,
        // então recarrega pra começar uma sessão nova
        location.reload();
        return;
      }
      // queda de rede/servidor: tenta de novo com espera crescente (1s, 2s, 4s... até 10s)
      const delay = Math.min(1000 * 2 ** attempt, 10000);
      attempt += 1;
      setTimeout(connect, delay);
    });
  }

  function findByPyId(pyid) {
    return document.querySelector(`[data-pyid="${CSS.escape(pyid)}"]`);
  }

  function applyPatch(patch) {
    switch (patch.op) {
      case "update_props": {
        const el = findByPyId(patch.id);
        if (!el) return;
        for (const [key, value] of Object.entries(patch.props)) {
          if (value === null) {
            el.removeAttribute(key);
          } else if (key === "value" && "value" in el) {
            el.value = value; // inputs: precisa setar a propriedade, não só o atributo
          } else {
            el.setAttribute(key, value);
          }
        }
        break;
      }
      case "set_text": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        if (node) node.nodeValue = patch.value;
        break;
      }
      case "replace_at": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        if (node) parent.replaceChild(tmp.content.firstChild, node);
        break;
      }
      case "insert": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        const ref = parent.childNodes[patch.index] || null;
        parent.insertBefore(tmp.content.firstChild, ref);
        break;
      }
      case "remove_at": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const node = parent.childNodes[patch.index];
        if (node) parent.removeChild(node);
        break;
      }
      // --- patches endereçados por data-pyid (diff por key, listas) ---
      case "remove": {
        const el = findByPyId(patch.id);
        if (el) el.remove();
        break;
      }
      case "replace": {
        const el = findByPyId(patch.id);
        if (!el) return;
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        el.replaceWith(tmp.content.firstChild);
        break;
      }
      case "insert_before": {
        const parent = findByPyId(patch.parent_id) || document.body;
        const ref = patch.ref_id ? findByPyId(patch.ref_id) : null;
        const tmp = document.createElement("template");
        tmp.innerHTML = patch.html;
        parent.insertBefore(tmp.content.firstChild, ref);
        break;
      }
      case "move": {
        const el = findByPyId(patch.id);
        const parent = findByPyId(patch.parent_id) || document.body;
        if (!el) return;
        const ref = patch.ref_id ? findByPyId(patch.ref_id) : null;
        parent.insertBefore(el, ref); // mover um nó existente não perde seu estado no DOM (ex: foco, scroll)
        break;
      }
    }
  }

  function sendEvent(pyid, eventName, value) {
    // sem conexão aberta o evento é descartado (a UI volta a responder
    // assim que a reconexão acontecer)
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ pyid, event: eventName, value }));
  }

  // Delegação de eventos: um único listener por tipo de evento no document,
  // que sobe a árvore procurando o elemento mais próximo com data-events.
  ["click", "input", "change", "submit", "keydown", "keyup", "focus", "blur"].forEach((eventType) => {
    document.addEventListener(
      eventType,
      (e) => {
        let el = e.target;
        while (el && el !== document.body) {
          const events = el.getAttribute && el.getAttribute("data-events");
          if (events && events.split(",").includes(eventType)) {
            if (eventType === "submit") e.preventDefault();
            const value = "value" in el ? el.value : null;
            sendEvent(el.getAttribute("data-pyid"), eventType, value);
            break;
          }
          el = el.parentElement;
        }
      },
      true
    );
  });

  connect();
})();
