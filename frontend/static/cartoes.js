// Cartões da aba Agente que dá para minimizar: clique no título. O estado fica guardado neste navegador.
(function () {
  const CHAVE = "cartoes-recolhidos";
  const PADRAO_RECOLHIDOS = ["Motores de IA (roteiros e descrição de imagens)"]; // configurado uma vez e pronto: começa fechado
  let salvo = null;
  try { salvo = JSON.parse(localStorage.getItem(CHAVE)); } catch { salvo = null; }
  const recolhidos = new Set(Array.isArray(salvo) ? salvo : PADRAO_RECOLHIDOS);
  const gravar = () => { try { localStorage.setItem(CHAVE, JSON.stringify([...recolhidos])); } catch { /* sem armazenamento: tudo bem */ } };

  document.querySelectorAll("#tab-agente .card").forEach((cartao) => {
    const cabeca = cartao.querySelector(":scope > .card-head");
    if (!cabeca) return;
    const nome = cabeca.textContent.trim();
    cartao.classList.add("cartao-minimizavel");
    cabeca.setAttribute("role", "button");
    cabeca.tabIndex = 0;
    cabeca.title = "Clique para minimizar ou abrir";
    const aplicar = () => {
      const fechado = recolhidos.has(nome);
      cartao.classList.toggle("recolhido", fechado);
      cabeca.setAttribute("aria-expanded", String(!fechado));
    };
    const alternar = () => {
      if (recolhidos.has(nome)) recolhidos.delete(nome); else recolhidos.add(nome);
      gravar();
      aplicar();
    };
    cabeca.addEventListener("click", alternar);
    cabeca.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alternar(); } });
    aplicar();
  });
})();
