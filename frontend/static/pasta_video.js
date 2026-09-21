// Novo vídeo: escolher uma "pasta de vídeo" do canal (dados/entrada/<canal>/Vídeo 1...). Os arquivos cena 1, cena 2...
// dela entram na Base e ocupam as cenas, na ordem — o parágrafo N do roteiro é narrado sobre o arquivo N.

const campoPastaVideo = document.getElementById("campo-pasta-video");
const infoPastaVideo = document.getElementById("pasta-video-info");
const btnAbrirPastaVideo = document.getElementById("btn-pasta-video-abrir");
const btnDescreverPastaVideo = document.getElementById("btn-pasta-video-descrever");
let pastaVideoAplicada = ""; // pasta cujos arquivos estão na sequência agora ("" = a sequência é escolha manual)

async function atualizarPastasDeVideoNovo() {
  const canalId = seletorCanal.value || "";
  const r = await fetch(`/api/entrada/pastas-video?canal_id=${encodeURIComponent(canalId)}`).then((x) => x.json()).catch(() => null);
  if (!r) return;
  const atual = campoPastaVideo.value;
  campoPastaVideo.innerHTML =
    '<option value="">Nenhuma (escolher da Base ou gerar por IA)</option>' +
    r.pastas.map((p) => `<option value="${escaparAttr(p.nome)}">${escaparAttr(p.nome)} — ${p.arquivos} arquivo(s)</option>`).join("");
  campoPastaVideo.value = r.pastas.some((p) => p.nome === atual) ? atual : "";
  btnAbrirPastaVideo.hidden = !campoPastaVideo.value;
}

async function aplicarPastaDeVideo() {
  const nome = campoPastaVideo.value;
  btnAbrirPastaVideo.hidden = !nome;
  btnDescreverPastaVideo.hidden = !nome;
  if (!nome) {
    if (pastaVideoAplicada) { selecionadasBase.splice(0, selecionadasBase.length); await montarSeletorBaseNovoVideo(); window.aoMudarMidiasBase(); }
    pastaVideoAplicada = "";
    infoPastaVideo.textContent = "";
    return;
  }
  infoPastaVideo.textContent = "Preparando os arquivos da pasta (vídeos grandes levam um pouco)…";
  const dados = new FormData();
  dados.append("canal_id", seletorCanal.value || "");
  dados.append("nome", nome);
  const r = await fetch("/api/entrada/pastas-video/preparar", { method: "POST", body: dados }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
  if (r.erro) {
    infoPastaVideo.textContent = `Não deu: ${r.erro}`;
    return;
  }
  if (!r.itens.length) {
    infoPastaVideo.textContent = "A pasta está vazia. Salve nela os arquivos cena 1, cena 2, cena 3… (imagens ou vídeos) e escolha de novo.";
    return;
  }
  pastaVideoAplicada = nome;
  selecionadasBase.splice(0, selecionadasBase.length, ...r.itens.map((i) => i.chave));
  delete campoNumCenas.dataset.auto; // a quantidade de cenas passa a ser a da pasta
  campoNumCenas.value = "";
  await montarSeletorBaseNovoVideo();
  window.aoMudarMidiasBase();
  const lista = r.itens.map((i, k) => `cena ${k + 1} = ${i.arquivo}`).join(" · ");
  infoPastaVideo.textContent = `${r.itens.length} cena(s) na ordem dos nomes: ${lista}. Escreva o roteiro com ${r.itens.length} parágrafos (um por linha): o parágrafo 1 é narrado sobre a cena 1, e assim por diante. Ou use "Gerar roteiro com base nessas mídias".`;
}

campoPastaVideo.addEventListener("change", aplicarPastaDeVideo);
btnAbrirPastaVideo.addEventListener("click", async () => {
  const dados = new FormData();
  dados.append("canal_id", seletorCanal.value || "");
  dados.append("pasta_video", campoPastaVideo.value);
  await fetch("/api/base/abrir-entrada", { method: "POST", body: dados }).catch(() => {});
});

// a IA escreve a descrição dos arquivos que ainda não têm (é com ela que o roteiro gerado segue cada imagem)
btnDescreverPastaVideo.addEventListener("click", async () => {
  const sem = [];
  const base = await fetch(`/api/biblioteca?canal=${encodeURIComponent(seletorCanal.value || "")}`).then((x) => x.json()).catch(() => null);
  if (!base) return;
  const todos = [...(base.imagens || []).map((i) => ({ ...i, tipo: "imagem" })), ...(base.videos || []).map((v) => ({ ...v, tipo: "video" }))];
  selecionadasBase.forEach((chave) => {
    const item = todos.find((it) => `${it.tipo}:${it.nome}` === chave);
    if (item && !(item.descricao || "").trim()) sem.push(item);
  });
  if (!sem.length) { infoPastaVideo.textContent = "Todos os arquivos já têm descrição."; return; }
  btnDescreverPastaVideo.disabled = true;
  let feitos = 0;
  for (const item of sem) {
    infoPastaVideo.textContent = `A IA está olhando o arquivo ${feitos + 1} de ${sem.length}…`;
    const r = await fetch(`/api/biblioteca/${item.tipo === "video" ? "videos" : "imagens"}/${encodeURIComponent(item.nome)}/descrever`, { method: "POST" }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
    if (r.erro) { infoPastaVideo.textContent = `Parei no arquivo ${feitos + 1}: ${r.erro}`; break; }
    feitos++;
  }
  btnDescreverPastaVideo.disabled = false;
  if (feitos === sem.length) infoPastaVideo.textContent = `Pronto: ${feitos} descrição(ões) escritas. Confira e corrija na sequência abaixo, se quiser.`;
  await montarSeletorBaseNovoVideo();
});

document.querySelector('[data-tab="novo"]').addEventListener("click", atualizarPastasDeVideoNovo);
seletorCanal.addEventListener("change", () => { campoPastaVideo.value = ""; pastaVideoAplicada = ""; infoPastaVideo.textContent = ""; atualizarPastasDeVideoNovo(); });
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(() => { campoPastaVideo.value = ""; pastaVideoAplicada = ""; infoPastaVideo.textContent = ""; btnAbrirPastaVideo.hidden = true; btnDescreverPastaVideo.hidden = true; }, 80));
atualizarPastasDeVideoNovo();


// ---------------- thumbnail do vídeo: escolher entre as imagens da pasta Thumbnails do canal ----------------
const gradeThumbNovo = document.getElementById("thumb-novo-grade");
const campoThumbBase = document.getElementById("campo-thumbnail-base");

async function atualizarThumbsDoNovo() {
  const dados = await fetch(`/api/biblioteca?canal=${encodeURIComponent(seletorCanal.value || "")}`).then((x) => x.json()).catch(() => null);
  if (!dados) return;
  const thumbs = (dados.imagens || []).filter((i) => i.thumbnail && (i.canal_id === "" || i.canal_id === seletorCanal.value));
  if (!thumbs.some((t) => t.nome === campoThumbBase.value)) campoThumbBase.value = "";
  gradeThumbNovo.innerHTML = thumbs.length
    ? thumbs.map((t) => `<div class="base-opcao"><button type="button" class="thumb-img-opcao${t.nome === campoThumbBase.value ? " selecionada" : ""}" data-nome="${escaparAttr(t.nome)}" title="${escaparAttr(t.original || t.nome)}"><img src="${t.url}" alt=""></button><span class="base-legenda" title="${escaparAttr(t.original || t.nome)}">${escaparAttr(t.original || t.nome)}</span></div>`).join("")
    : '<span class="video-meta">Nenhuma thumbnail ainda. Salve imagens na pasta Thumbnails do canal (aba Base → Pasta de entrada).</span>';
}

gradeThumbNovo.addEventListener("click", (ev) => {
  const botao = ev.target.closest(".thumb-img-opcao");
  if (!botao) return;
  campoThumbBase.value = campoThumbBase.value === botao.dataset.nome ? "" : botao.dataset.nome;
  gradeThumbNovo.querySelectorAll(".thumb-img-opcao").forEach((b) => b.classList.toggle("selecionada", b.dataset.nome === campoThumbBase.value));
});
document.querySelector('[data-tab="novo"]').addEventListener("click", atualizarThumbsDoNovo);
seletorCanal.addEventListener("change", () => { campoThumbBase.value = ""; atualizarThumbsDoNovo(); });
document.getElementById("btn-limpar-novo").addEventListener("click", () => setTimeout(() => { campoThumbBase.value = ""; atualizarThumbsDoNovo(); }, 80));
atualizarThumbsDoNovo();


// ---------------- resumo das cenas: por parágrafo, a descrição da imagem e o tempo (para pedir as imagens na IA de imagem) ----------------
const blocoResumo = document.getElementById("resumo-cenas");
const btnResumo = document.getElementById("btn-resumo-cenas");

function segundosDaCena(texto) {
  return Math.max(1, Math.round(estimarNarracao(texto).segundos));
}

function tempoEmTexto(s) {
  return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
}

btnResumo.addEventListener("click", async () => {
  const paragrafos = campoRoteiro.value.split("\n").map((p) => p.trim()).filter(Boolean);
  if (!paragrafos.length) {
    blocoResumo.hidden = false;
    blocoResumo.innerHTML = '<span class="video-meta">Escreva (ou cole) o roteiro primeiro: cada parágrafo vira uma cena.</span>';
    return;
  }
  btnResumo.disabled = true;
  blocoResumo.hidden = false;
  blocoResumo.innerHTML = '<span class="video-meta">A IA está descrevendo a imagem de cada cena…</span>';
  const dados = new FormData();
  dados.set("roteiro", campoRoteiro.value);
  dados.set("titulo", formNovo.titulo.value);
  dados.set("descricao_video", formNovo.descricao_video.value);
  const r = await fetch("/api/roteiro/resumo-cenas", { method: "POST", body: dados }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
  btnResumo.disabled = false;
  if (r.erro) { blocoResumo.innerHTML = `<span class="roteiro-cenas-aviso">Não deu: ${escaparAttr(r.erro)}</span>`; return; }
  const tempos = paragrafos.map(segundosDaCena);
  const total = tempos.reduce((a, b) => a + b, 0);
  const texto = r.cenas.map((c, i) => `Cena ${i + 1} (${tempoEmTexto(tempos[i])}): ${c.descricao}\n${c.prompt}`).join("\n\n");
  blocoResumo.dataset.copia = texto;
  blocoResumo.innerHTML =
    `<div class="resumo-topo"><b>Resumo: ${r.cenas.length} cena(s) · ≈ ${tempoEmTexto(total)} de narração</b>` +
    `<button type="button" class="btn-secondary btn-compacto" id="btn-resumo-copiar" title="Copia todas as cenas (descrição + pedido em inglês) para colar na IA de imagem">Copiar tudo</button></div>` +
    (r.ia ? "" : '<div class="roteiro-cenas-aviso">A IA de texto não respondeu agora: a descrição é o começo do próprio parágrafo. Tente de novo em instantes.</div>') +
    r.cenas.map((c, i) => `<div class="resumo-cena">
        <div class="resumo-cena-topo"><b>Cena ${i + 1}</b><span class="video-meta">≈ ${tempoEmTexto(tempos[i])}</span></div>
        <div>${escaparAttr(c.descricao)}</div>
        <div class="video-meta resumo-prompt">${escaparAttr(c.prompt)}</div>
      </div>`).join("") +
    '<span class="video-meta">A descrição é em português; a linha em cinza é o pedido em inglês (costuma dar melhor resultado na IA de imagem). O tempo é uma estimativa da narração.</span>';
  document.getElementById("btn-resumo-copiar").addEventListener("click", async (ev) => {
    try { await navigator.clipboard.writeText(blocoResumo.dataset.copia); ev.target.textContent = "Copiado!"; }
    catch { prompt("Copie o resumo:", blocoResumo.dataset.copia); }
    setTimeout(() => { ev.target.textContent = "Copiar tudo"; }, 1800);
  });
});
campoRoteiro.addEventListener("input", () => { blocoResumo.hidden = true; }); // roteiro mudou: o resumo antigo não vale mais
