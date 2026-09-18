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
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(() => { redesenharLegendaNovo(); agendarEstimativa(); }, 50));


// ---------------- vídeo da Base como fundo do vídeo inteiro + roteiro do tamanho dele ----------------

let videosBase = [];
const campoVideoBase = document.getElementById("campo-video-base-geral");

function videoBaseEscolhido() {
  return videosBase.find((v) => v.nome === campoVideoBase.value) || null;
}

function preencherVideosBaseNovoVideo(videos) {
  videosBase = videos;
  const atual = campoVideoBase.value;
  campoVideoBase.innerHTML = '<option value="">Nenhum</option>' + videos.map((v) => `<option value="${escaparAttr(v.nome)}">${escaparAttr(v.descricao || v.nome)} (${Math.round(v.duracao_segundos)} s)</option>`).join("");
  campoVideoBase.value = videos.some((v) => v.nome === atual) ? atual : "";
}

function descricaoParaRoteiro() {
  const base = formNovo.descricao_video.value.trim();
  const v = videoBaseEscolhido();
  if (!v) return base;
  return `${base} O roteiro será narrado sobre um vídeo importado, "${v.descricao || v.nome}" (${Math.round(v.duracao_segundos)} segundos). Escreva a narração acompanhando o que esse vídeo provavelmente mostra, sem citar o nome do arquivo.`.trim();
}

campoVideoBase.addEventListener("change", () => {
  const v = videoBaseEscolhido();
  const info = document.getElementById("video-base-info");
  const botao = document.getElementById("btn-roteiro-do-video");
  if (v) {
    formNovo.duracao_alvo.value = Math.max(0.3, Math.round((v.duracao_segundos / 60) * 100) / 100); // o roteiro tem o tempo do vídeo
    formNovo.num_cenas.value = "";
    formNovo.num_cenas.disabled = true; // o vídeo inteiro é uma cena só
    const s = Math.round(v.duracao_segundos);
    info.textContent = `Vídeo de ${s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`}: a duração alvo foi ajustada para esse tempo. O vídeo vira uma cena só; se a narração for mais longa ele repete em loop.`;
    botao.hidden = false;
  } else {
    formNovo.num_cenas.disabled = false;
    info.textContent = "";
    botao.hidden = true;
  }
  agendarEstimativa();
});

document.getElementById("btn-roteiro-do-video").addEventListener("click", () => {
  document.getElementById("btn-preview-roteiro").click(); // usa o mesmo fluxo da prévia (com barra de progresso)
});

// ---------------- ouvir amostra da voz ----------------

document.getElementById("btn-ouvir-voz").addEventListener("click", async (ev) => {
  const botao = ev.currentTarget;
  const original = botao.textContent;
  botao.disabled = true;
  botao.textContent = "carregando…";
  try {
    const audio = new Audio(`/api/voz/amostra?voz=${encodeURIComponent(formNovo.voz.value)}&idioma=${encodeURIComponent(formNovo.idioma.value)}`);
    audio.addEventListener("ended", () => { botao.disabled = false; botao.textContent = original; });
    audio.addEventListener("error", () => { botao.disabled = false; botao.textContent = original; });
    await audio.play();
    botao.textContent = "tocando…";
  } catch {
    botao.disabled = false;
    botao.textContent = original;
  }
});
