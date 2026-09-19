// Padrões do Novo vídeo por canal: o que você salva aqui já vem preenchido em todo formulário novo daquele canal.
// Não guarda o que muda a cada vídeo (título, data, hora, roteiro, mídias escolhidas, playlist de som).

const PADROES_IGNORADOS = new Set(["titulo", "data_postagem", "hora_postagem", "roteiro", "imagens_base", "base_restante", "num_cenas", "som_fundo_playlist", "som_fundo_biblioteca", "em_branco"]);
const statusPadroes = document.getElementById("padroes-status");

function valoresDoFormulario() {
  const saida = {};
  Array.from(formNovo.elements).forEach((el) => {
    if (!el.name || PADROES_IGNORADOS.has(el.name) || el.type === "file" || el.type === "button" || el.type === "submit") return;
    saida[el.name] = el.type === "checkbox" ? el.checked : el.value;
  });
  return saida;
}

function aplicarPadroes(padroes) {
  const nomes = Object.keys(padroes || {});
  nomes.forEach((nome) => {
    const el = formNovo.elements[nome];
    if (!el || el instanceof RadioNodeList) return;
    if (el.type === "checkbox") el.checked = !!padroes[nome];
    else el.value = padroes[nome];
  });
  // o JS esconde/mostra blocos conforme estes campos
  ["sem_narracao", "som_fundo_ativo", "som_fundo_tipo", "imagem", "formatos", "legenda_modo", "voz", "legenda_fundo", "legenda_cor"].forEach((nome) => {
    const el = formNovo.elements[nome];
    if (el && nomes.includes(nome)) {
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  // "sem narração" recalcula a duração sozinho: o valor salvo vale por último
  if (nomes.includes("duracao_alvo")) {
    formNovo.elements.duracao_alvo.value = padroes.duracao_alvo;
    formNovo.elements.duracao_alvo.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

async function carregarPadroesDoCanal() {
  if (!seletorCanal.value) return;
  try {
    const r = await fetch(`/api/canais/${encodeURIComponent(seletorCanal.value)}/padroes`).then((x) => x.json());
    const tem = Object.keys(r.padroes || {}).length > 0;
    aplicarPadroes(r.padroes);
    statusPadroes.textContent = tem ? "Este canal tem um padrão salvo: o formulário já vem preenchido com ele." : "Nenhum padrão salvo neste canal ainda.";
    document.getElementById("btn-apagar-padroes").hidden = !tem;
  } catch {
    statusPadroes.textContent = "";
  }
}

document.getElementById("btn-salvar-padroes").addEventListener("click", async () => {
  const r = await fetch(`/api/canais/${encodeURIComponent(seletorCanal.value)}/padroes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(valoresDoFormulario()),
  }).then((x) => x.json());
  statusPadroes.textContent = r.ok ? "Padrão do canal salvo. Todo vídeo novo deste canal já vem assim." : `Erro: ${r.erro || "não salvou"}`;
  document.getElementById("btn-apagar-padroes").hidden = !r.ok;
});

document.getElementById("btn-apagar-padroes").addEventListener("click", async () => {
  if (!confirm("Apagar o padrão salvo deste canal?")) return;
  await fetch(`/api/canais/${encodeURIComponent(seletorCanal.value)}/padroes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  document.getElementById("btn-apagar-padroes").hidden = true;
  statusPadroes.textContent = "Padrão apagado.";
});

// formulário novo: ao abrir a página, ao trocar de canal e ao limpar
seletorCanal.addEventListener("change", () => setTimeout(carregarPadroesDoCanal, 300));
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(carregarPadroesDoCanal, 150));
(async function iniciar() {
  for (let i = 0; i < 20 && !seletorCanal.value; i++) await new Promise((ok) => setTimeout(ok, 150)); // espera os canais carregarem
  carregarPadroesDoCanal();
})();
