// Novo vídeo: estimativa de tempo de produção, sugestão de duração pelo agente e prévia da legenda.

const formNovo = document.getElementById("form-novo");
const rotuloEstimativa = document.getElementById("estimativa-novo");
let timerEstimativa = null;

function parametrosDaEstimativa() {
  const dados = new FormData();
  const semNarracao = formNovo.sem_narracao.checked;
  const roteiro = formNovo.roteiro.value.trim();
  let duracao = parseFloat(formNovo.duracao_alvo.value) || 1;
  // com roteiro escrito, a duração real vem do tamanho do texto, não do campo "duração alvo"
  if (roteiro && !semNarracao) duracao = Math.max(0.3, estimarNarracao(roteiro).segundos / 60);
  dados.set("duracao_alvo", duracao);
  if (formNovo.num_cenas.value) dados.set("num_cenas", formNovo.num_cenas.value);
  dados.set("imagem", formNovo.imagem.value);
  dados.set("formatos", formNovo.formatos.value);
  dados.set("sem_narracao", semNarracao ? "true" : "false");
  dados.set("tem_roteiro", roteiro ? "true" : "false");
  dados.set("narracao_propria", typeof narracaoGravadaBlob !== "undefined" && narracaoGravadaBlob ? "true" : "false");
  dados.set("som_fundo", formNovo.som_fundo_ativo.checked ? "true" : "false");
  dados.set("transicao", formNovo.transicao.value);
  dados.set("n_imagens_base", typeof selecionadasBase !== "undefined" ? selecionadasBase.length : 0);
  return dados;
}

async function atualizarEstimativa() {
  try {
    const { segundos } = await fetch("/api/estimativa", { method: "POST", body: parametrosDaEstimativa() }).then((r) => r.json());
    rotuloEstimativa.textContent = `Tempo estimado para produzir: ${formatarRestante(segundos).replace("~", "≈ ")} (aproximado — melhora conforme você gera vídeos)`;
  } catch {
    rotuloEstimativa.textContent = "";
  }
}

function agendarEstimativa() {
  clearTimeout(timerEstimativa);
  timerEstimativa = setTimeout(atualizarEstimativa, 350);
}

formNovo.addEventListener("input", agendarEstimativa);
formNovo.addEventListener("change", agendarEstimativa);
document.getElementById("novo-base-grade")?.addEventListener("click", agendarEstimativa);
document.querySelector('[data-tab="novo"]').addEventListener("click", agendarEstimativa);
agendarEstimativa();

// ---------------- sugerir duração (agente) ----------------

document.getElementById("btn-sugerir-duracao").addEventListener("click", async (ev) => {
  const botao = ev.currentTarget;
  const motivo = document.getElementById("duracao-motivo");
  const titulo = formNovo.titulo.value.trim();
  if (!titulo) {
    motivo.textContent = "Escreva o título primeiro para o agente saber que tipo de vídeo é.";
    return;
  }
  botao.disabled = true;
  motivo.textContent = "O agente está pensando na duração ideal para o seu canal…";
  const corpo = new FormData();
  corpo.set("titulo", titulo);
  if (formNovo.num_cenas.value) corpo.set("num_cenas", formNovo.num_cenas.value);
  corpo.set("descricao_video", formNovo.descricao_video.value);
  try {
    const r = await fetch("/api/agente/duracao", { method: "POST", body: corpo }).then((x) => x.json());
    formNovo.duracao_alvo.value = r.minutos;
    motivo.textContent = `Sugestão: ${r.minutos} min. ${r.motivo || ""}`;
    agendarEstimativa();
  } catch {
    motivo.textContent = "Não consegui falar com o agente agora.";
  } finally {
    botao.disabled = false;
  }
});

// ---------------- prévia da legenda no formulário ----------------

const mockNovo = document.getElementById("leg-mock-novo");

function lerLegendaDoFormulario() {
  return {
    modo: formNovo.legenda_modo.value,
    tamanho: formNovo.legenda_tamanho.value,
    posicao: formNovo.legenda_posicao.value,
    cor: formNovo.legenda_cor.value,
    fundo: formNovo.legenda_fundo.value,
  };
}

function redesenharLegendaNovo() {
  if (mockNovo.clientHeight) desenharPreviewLegenda(mockNovo, lerLegendaDoFormulario());
}

["legenda_modo", "legenda_tamanho", "legenda_posicao", "legenda_cor", "legenda_fundo"].forEach((nome) => {
  formNovo[nome].addEventListener("input", redesenharLegendaNovo);
});
document.getElementById("secao-legenda").addEventListener("toggle", () => requestAnimationFrame(redesenharLegendaNovo));
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(() => { delete campoNumCenas.dataset.auto; redesenharLegendaNovo(); agendarEstimativa(); window.aoMudarMidiasBase(); }, 50));


// ---------------- mídias da Base escolhidas para as cenas (imagens E vídeos) ----------------

const campoNumCenas = formNovo.num_cenas;
const campoBaseRestante = document.getElementById("campo-base-restante");

function midiasEscolhidas() {
  return typeof selecionadasBase !== "undefined" ? selecionadasBase : [];
}

// chamada por base.js sempre que a seleção muda (e ao mexer na quantidade de cenas)
window.aoMudarMidiasBase = () => {
  const k = midiasEscolhidas().length;
  campoBaseRestante.closest("label").hidden = k === 0;
  document.getElementById("btn-roteiro-das-midias").hidden = k === 0;
  if (k > 0 && (!campoNumCenas.value || campoNumCenas.dataset.auto === "1")) {
    campoNumCenas.value = k; // uma cena por mídia escolhida (você pode mudar)
    campoNumCenas.dataset.auto = "1";
  } else if (k === 0 && campoNumCenas.dataset.auto === "1") {
    campoNumCenas.value = "";
    delete campoNumCenas.dataset.auto;
  }
  const n = parseInt(campoNumCenas.value, 10) || 0;
  const info = document.getElementById("midias-base-info");
  if (!k) info.textContent = "";
  else if (n === k) info.textContent = `${k} mídia(s) = ${k} cena(s): nenhuma imagem será gerada por IA.`;
  else if (n > k) info.textContent = `${k} de ${n} cenas usam a Base; ${campoBaseRestante.value === "repetir" ? "as demais repetem as escolhidas em ciclo (nada gerado por IA)" : "as demais são geradas pelo estilo de imagem acima"}.`;
  else info.textContent = `Você escolheu ${k} mídias mas pediu ${n} cena(s): só as ${n} primeiras entram.`;
  if (typeof atualizarCenasDoRoteiro === "function") atualizarCenasDoRoteiro();
  agendarEstimativa();
};

campoNumCenas.addEventListener("input", () => {
  delete campoNumCenas.dataset.auto; // você mexeu: a quantidade deixa de acompanhar a seleção
  window.aoMudarMidiasBase();
});
campoBaseRestante.addEventListener("change", window.aoMudarMidiasBase);

document.getElementById("btn-roteiro-das-midias").addEventListener("click", () => {
  document.getElementById("btn-preview-roteiro").click(); // mesmo fluxo da prévia (barra de progresso); as mídias vão junto
});

let audioAmostra = null;

document.getElementById("btn-ouvir-voz").addEventListener("click", async (ev) => {
  const botao = ev.currentTarget;
  const ROTULO = "▶ Ouvir";
  if (audioAmostra) { // já tocando: o clique pausa
    audioAmostra.pause();
    audioAmostra = null;
    botao.textContent = ROTULO;
    return;
  }
  botao.textContent = "carregando…";
  const audio = new Audio(`/api/voz/amostra?voz=${encodeURIComponent(formNovo.voz.value)}&idioma=${encodeURIComponent(formNovo.idioma.value)}`);
  audioAmostra = audio;
  const terminou = () => { if (audioAmostra === audio) audioAmostra = null; botao.textContent = ROTULO; };
  audio.addEventListener("ended", terminou);
  audio.addEventListener("error", terminou);
  try {
    await audio.play();
    if (audioAmostra === audio) botao.textContent = "⏸ Pausar";
  } catch {
    terminou();
  }
});

// trocar a voz ou o idioma com a amostra tocando: para a amostra antiga
["voz", "idioma"].forEach((nome) => formNovo[nome].addEventListener("change", () => {
  if (audioAmostra) { audioAmostra.pause(); audioAmostra = null; document.getElementById("btn-ouvir-voz").textContent = "▶ Ouvir"; }
}));


// ---------------- som de fundo com vários áudios da Base (playlist) ----------------

const blocoSom = document.getElementById("som-playlist-bloco");
const listaExtrasSom = document.getElementById("som-extras");

function nomeDoAudio(a) {
  return `${a.descricao || a.nome} (${Math.floor((a.duracao_segundos || 0) / 60)}:${String(Math.round((a.duracao_segundos || 0) % 60)).padStart(2, "0")})`;
}

function duracaoDoVideoEstimada() {
  const roteiro = formNovo.roteiro.value.trim();
  if (roteiro && !formNovo.sem_narracao.checked) return estimarNarracao(roteiro).segundos;
  return (parseFloat(formNovo.duracao_alvo.value) || 1) * 60;
}

function minSeg(s) {
  const t = Math.round(s);
  return t >= 60 ? `${Math.floor(t / 60)} min ${t % 60} s` : `${t} s`;
}

function atualizarPlaylistSom() {
  const audios = window.audiosBase || [];
  const itens = [];
  const primeiro = formNovo.som_fundo_biblioteca.value;
  if (primeiro) itens.push({ nome: primeiro, segundos: parseFloat(document.getElementById("som-tempo-0").value) || null });
  listaExtrasSom.querySelectorAll(".som-extra").forEach((linha) => {
    const nome = linha.querySelector(".som-extra-audio").value;
    if (nome) itens.push({ nome, segundos: parseFloat(linha.querySelector(".som-extra-tempo").value) || null });
  });
  document.getElementById("campo-som-playlist").value = itens.length > 1 || itens[0]?.segundos ? JSON.stringify(itens) : "";
  const total = itens.reduce((soma, it, i) => {
    const dur = audios.find((a) => a.nome === it.nome)?.duracao_segundos || 0;
    return soma + Math.max(1, it.segundos ? Math.min(dur, it.segundos) : dur) - (i && formNovo.som_fundo_suave.checked ? 2 : 0);
  }, 0);
  const video = duracaoDoVideoEstimada();
  const resumo = document.getElementById("som-playlist-resumo");
  if (!itens.length) resumo.textContent = "";
  else if (total >= video) resumo.textContent = `Os áudios somam ${minSeg(total)} e o vídeo tem cerca de ${minSeg(video)}: o som corta no fim do vídeo.`;
  else resumo.textContent = `Os áudios somam ${minSeg(total)} e o vídeo tem cerca de ${minSeg(video)}: faltam ${minSeg(video - total)}, então ${formNovo.som_fundo_repetir.value === "repetir" ? "a sequência se repete" : "o final fica em silêncio"}. Junte mais um áudio para variar.`;
}

function adicionarLinhaAudioSom() {
  const audios = window.audiosBase || [];
  if (!audios.length) return;
  const linha = document.createElement("div");
  linha.className = "som-extra";
  linha.innerHTML = `
    <select class="som-extra-audio">${audios.map((a) => `<option value="${escaparAttr(a.nome)}">${escaparAttr(nomeDoAudio(a))}</option>`).join("")}</select>
    <label>por <input type="number" class="som-extra-tempo" min="1" step="1" placeholder="inteiro"> s</label>
    <button type="button" class="btn-regenerar btn-regenerar-sutil som-extra-remover" title="Tirar esse áudio">✕</button>`;
  listaExtrasSom.appendChild(linha);
  atualizarPlaylistSom();
}

window.aoCarregarAudiosBase = () => {
  // as opções das linhas extras acompanham a Base (sem perder o que já foi escolhido)
  listaExtrasSom.querySelectorAll(".som-extra-audio").forEach((sel) => {
    const atual = sel.value;
    sel.innerHTML = (window.audiosBase || []).map((a) => `<option value="${escaparAttr(a.nome)}">${escaparAttr(nomeDoAudio(a))}</option>`).join("");
    if ((window.audiosBase || []).some((a) => a.nome === atual)) sel.value = atual;
  });
  atualizarPlaylistSom();
};

document.getElementById("btn-add-audio").addEventListener("click", adicionarLinhaAudioSom);
listaExtrasSom.addEventListener("click", (ev) => {
  if (ev.target.closest(".som-extra-remover")) {
    ev.target.closest(".som-extra").remove();
    atualizarPlaylistSom();
  }
});
blocoSom.addEventListener("input", atualizarPlaylistSom);
blocoSom.addEventListener("change", atualizarPlaylistSom);
formNovo.som_fundo_biblioteca.addEventListener("change", atualizarPlaylistSom);
formNovo.duracao_alvo.addEventListener("input", atualizarPlaylistSom);
formNovo.roteiro.addEventListener("input", atualizarPlaylistSom);
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(() => { listaExtrasSom.innerHTML = ""; document.getElementById("som-tempo-0").value = ""; atualizarPlaylistSom(); }, 60));
