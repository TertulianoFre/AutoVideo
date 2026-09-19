// Cartão "Motores de IA" da aba Agente: mostra quais provedores estão ativos e guarda as chaves grátis no .env.

const NOMES_MOTORES = { groq: "Groq", gemini: "Google Gemini", cerebras: "Cerebras", openrouter: "OpenRouter", ollama: "Ollama (local)", pollinations: "Pollinations" };
const MOTORES_COM_VISAO = new Set(["groq", "gemini", "openrouter"]);

async function desenharMotoresIA() {
  const area = document.getElementById("motores-ia");
  if (!area) return;
  const { provedores } = await fetch("/api/ia/status").then((r) => r.json());
  area.innerHTML = provedores.map((p) => {
    const editavel = !["ollama", "pollinations"].includes(p.id);
    const situacao = p.descansando ? `<span class="video-meta">no limite, volta em ${p.descansando}s</span>` : p.chave ? '<span class="motor-ok">● ativo</span>' : '<span class="video-meta">sem chave</span>';
    const visao = MOTORES_COM_VISAO.has(p.id) ? ' <span class="tag-pill">visão</span>' : "";
    const campo = editavel
      ? `<input type="password" placeholder="${p.chave ? "chave salva (cole outra para trocar)" : "cole a chave grátis aqui"}" autocomplete="off"><button type="button" class="btn-secondary btn-compacto motor-salvar">Salvar</button>${p.chave ? '<button type="button" class="btn-regenerar btn-regenerar-sutil motor-apagar">remover</button>' : ""}`
      : "";
    return `<div class="motor-linha" data-id="${p.id}"><span class="motor-nome">${NOMES_MOTORES[p.id] || p.id}${visao}</span>${situacao}${campo}<span class="video-meta">${p.site}</span></div>`;
  }).join("");
  area.querySelectorAll(".motor-linha").forEach((linha) => {
    const id = linha.dataset.id;
    const enviar = async (chave) => {
      const corpo = new FormData();
      corpo.set("provedor", id);
      corpo.set("chave", chave);
      await fetch("/api/ia/chave", { method: "POST", body: corpo });
      desenharMotoresIA();
    };
    const salvar = linha.querySelector(".motor-salvar");
    if (salvar) salvar.addEventListener("click", () => { const v = linha.querySelector("input").value.trim(); if (v) enviar(v); });
    const apagar = linha.querySelector(".motor-apagar");
    if (apagar) apagar.addEventListener("click", () => { if (confirm("Remover a chave deste motor?")) enviar(""); });
  });
}

document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.tab === "agente") desenharMotoresIA(); }));
desenharMotoresIA();
