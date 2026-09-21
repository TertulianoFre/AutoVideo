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
