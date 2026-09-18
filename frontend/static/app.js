const TITULOS = { painel: "Painel", agente: "Agente", novo: "Novo vídeo", fila: "Fila" };

function trocarAba(nome) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${nome}`));
  document.getElementById("page-title").textContent = TITULOS[nome];
  if (nome === "painel") carregarPainel();
  if (nome === "fila") carregarFila();
}

document.querySelectorAll(".nav-item").forEach((botao) => {
  botao.addEventListener("click", () => trocarAba(botao.dataset.tab));
});

function formatarDuracao(segundos) {
  const s = Math.round(segundos || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const seg = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(seg).padStart(2, "0")}` : `${m}:${String(seg).padStart(2, "0")}`;
}

function formatarDataPostagem(iso) {
  if (!iso) return "sem data definida";
  const [ano, mes, dia] = iso.split("-");
  return `postar em ${dia}/${mes}/${ano}`;
}

const ICONE_VIDEO = '<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2.5" y="5.5" width="10" height="9" rx="1.5"></rect><path d="M12.5 9l5-3v8l-5-3z"></path></svg>';

function statusPublicacao(v) {
  if (v.publicado) {
    const link = v.youtube_video_id ? `<a href="https://youtu.be/${v.youtube_video_id}" target="_blank">assistir</a>` : "";
    return `<span class="dot dot-positive"></span> publicado ${link}`;
  }
  if (v.publicacao_erro) {
    return `<span class="dot dot-negative"></span> erro ao publicar: ${v.publicacao_erro}`;
  }
  return "";
}

function linhaDeVideo(v, comRegenerar) {
  const rotulos = [];
  if (v.sem_narracao) rotulos.push("sem narração");
  if (v.som_fundo_tipo) rotulos.push(`som: ${v.som_fundo_tipo}`);
  const modoLabel = rotulos.length ? `· ${rotulos.join(", ")}` : "";
  const thumb = v.thumbnail
    ? `<img src="${v.thumbnail}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:6px">`
    : ICONE_VIDEO;
  const botaoRegenerar = comRegenerar
    ? `<button type="button" class="btn-regenerar" data-slug="${v.slug}" data-manter-roteiro="true">Regenerar</button>
       ${!v.sem_narracao ? `<button type="button" class="btn-regenerar btn-regenerar-sutil" data-slug="${v.slug}" data-manter-roteiro="false" title="Escreve um roteiro novo também">roteiro novo</button>` : ""}
       <button type="button" class="btn-regenerar btn-regenerar-sutil btn-nova-thumb" data-slug="${v.slug}" title="Sorteia outra imagem de cena pra thumbnail">nova thumbnail</button>
       <button type="button" class="btn-regenerar btn-regenerar-sutil btn-editar-thumb" data-slug="${v.slug}" title="Mudar o texto e a cor da thumbnail">editar thumbnail</button>
       ${v.tem_cenas ? `<button type="button" class="btn-regenerar btn-regenerar-sutil btn-ver-cenas" data-slug="${v.slug}" title="Editar cenas específicas sem refazer o vídeo inteiro">cenas</button>` : ""}`
    : "";
  const publicacao = statusPublicacao(v);
  return `
    <div class="video-item">
      <div class="video-row" data-slug="${v.slug}">
        <div class="video-thumb">${thumb}</div>
        <div class="video-info">
          <div class="video-title">${v.titulo}</div>
          <div class="video-meta video-meta-status">${formatarDataPostagem(v.data_postagem)} ${modoLabel}</div>
          ${publicacao ? `<div class="video-meta">${publicacao}</div>` : ""}
        </div>
        <div class="video-links">
          <a href="${v.video_16_9}" target="_blank">16:9</a>
          <a href="${v.video_9_16}" target="_blank">Shorts</a>
          ${botaoRegenerar}
        </div>
      </div>
      ${comRegenerar ? `<div class="thumb-painel" data-slug="${v.slug}" data-titulo="${v.titulo.replace(/"/g, "&quot;")}"></div>` : ""}
      ${comRegenerar && v.tem_cenas ? `<div class="cenas-painel" data-slug="${v.slug}"></div>` : ""}
    </div>`;
}

async function buscarVideos() {
  const resposta = await fetch("/api/videos");
  return resposta.ok ? resposta.json() : [];
}

async function carregarPainel() {
  const videos = await buscarVideos();
  document.getElementById("stat-total").textContent = videos.length;
  const lista = document.getElementById("painel-lista");
  lista.innerHTML = videos.length
    ? videos.slice(0, 6).map(linhaDeVideo).join("")
    : '<div class="empty">Nenhum vídeo ainda — vá em "Novo vídeo" pra gerar o primeiro.</div>';
}

async function carregarFila() {
  const videos = await buscarVideos();
  const lista = document.getElementById("fila-lista");
  lista.innerHTML = videos.length
    ? videos.map((v) => linhaDeVideo(v, true)).join("")
    : '<div class="empty">Nenhum vídeo gerado ainda.</div>';

  lista.querySelectorAll(".btn-regenerar:not(.btn-nova-thumb):not(.btn-ver-cenas):not(.btn-editar-thumb)").forEach((botao) => {
    botao.addEventListener("click", () => regenerarVideo(botao));
  });
  lista.querySelectorAll(".btn-nova-thumb").forEach((botao) => {
    botao.addEventListener("click", () => regenerarThumbnail(botao));
  });
  lista.querySelectorAll(".btn-ver-cenas").forEach((botao) => {
    botao.addEventListener("click", () => alternarPainelCenas(botao));
  });
  lista.querySelectorAll(".btn-editar-thumb").forEach((botao) => {
    botao.addEventListener("click", () => alternarPainelThumb(botao));
  });
}

// ---------------- Fila: editar texto/cor da thumbnail ----------------

const CORES_THUMB = [
  { nome: "Padrão", hex: "" },
  { nome: "Amarelo", hex: "FFD23F" },
  { nome: "Vermelho", hex: "FF4C4C" },
  { nome: "Verde", hex: "3DDC84" },
  { nome: "Azul", hex: "4DA6FF" },
];

function alternarPainelThumb(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.thumb-painel[data-slug="${slug}"]`);
  if (!painel) return;

  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder thumbnail" : "editar thumbnail";
  if (!abrindo || painel.dataset.montado === "true") return;

  painel.dataset.montado = "true";
  const tituloPadrao = painel.dataset.titulo || "";
  const swatches = CORES_THUMB.map(
    (c, i) => `<button type="button" class="cor-swatch${i === 0 ? " selecionada" : ""}" data-hex="${c.hex}" title="${c.nome}" style="background:${c.hex ? "#" + c.hex : "#F6F2E9"}"></button>`
  ).join("");

  painel.innerHTML = `
    <div class="thumb-form">
      <input type="text" class="thumb-texto" value="${tituloPadrao}" maxlength="80" placeholder="Texto que aparece na thumbnail">
      <div class="cor-swatches">${swatches}</div>
      <button type="button" class="btn-secondary btn-salvar-thumb">Salvar</button>
      <span class="video-meta thumb-status"></span>
    </div>`;

  painel.querySelectorAll(".cor-swatch").forEach((sw) => {
    sw.addEventListener("click", () => {
      painel.querySelectorAll(".cor-swatch").forEach((s) => s.classList.remove("selecionada"));
      sw.classList.add("selecionada");
    });
  });

  painel.querySelector(".btn-salvar-thumb").addEventListener("click", () => salvarThumb(slug, painel));
}

async function salvarThumb(slug, painel) {
  const texto = painel.querySelector(".thumb-texto").value.trim();
  const corSelecionada = painel.querySelector(".cor-swatch.selecionada");
  const status = painel.querySelector(".thumb-status");
  const botaoSalvar = painel.querySelector(".btn-salvar-thumb");

  if (!texto) {
    status.textContent = "Escreve algum texto primeiro.";
    return;
  }

  botaoSalvar.disabled = true;
  status.textContent = "Salvando…";

  const dados = new FormData();
  dados.set("texto", texto);
  dados.set("cor", corSelecionada ? corSelecionada.dataset.hex : "");

  try {
    const resposta = await fetch(`/api/videos/${slug}/thumbnail/editar`, { method: "POST", body: dados });
    const resultado = await resposta.json();
    botaoSalvar.disabled = false;
    if (resultado.erro) {
      status.textContent = `Deu erro: ${resultado.erro}`;
      return;
    }
    status.textContent = "Salvo!";
    setTimeout(() => (status.textContent = ""), 3000);
    const thumbImg = document.querySelector(`.video-row[data-slug="${slug}"] .video-thumb img`);
    if (thumbImg) thumbImg.src = resultado.thumbnail;
  } catch {
    botaoSalvar.disabled = false;
    status.textContent = "Deu erro de conexão, tenta de novo.";
  }
}

// ---------------- Fila: editar uma cena específica ----------------

function cardDeCena(slug, cena) {
  const imagem = cena.imagem
    ? `<img class="cena-card-img" src="${cena.imagem}" alt="">`
    : `<div class="cena-card-img" style="display:flex;align-items:center;justify-content:center;color:var(--text-dim)">${ICONE_VIDEO}</div>`;
  return `
    <div class="cena-card" data-indice="${cena.indice}">
      ${imagem}
      <div class="cena-card-body">
        <div class="cena-card-indice">Cena ${cena.indice + 1}</div>
        <p class="cena-card-texto">${cena.texto || ""}</p>
        <button type="button" class="btn-regenerar btn-regenerar-cena" data-slug="${slug}" data-indice="${cena.indice}">Regenerar essa cena</button>
      </div>
    </div>`;
}

async function alternarPainelCenas(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.cenas-painel[data-slug="${slug}"]`);
  if (!painel) return;

  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder cenas" : "cenas";
  if (!abrindo || painel.dataset.carregado === "true") return;

  painel.innerHTML = '<div class="cenas-status">Carregando cenas…</div>';
  const resposta = await fetch(`/api/videos/${slug}/cenas`);
  const dados = await resposta.json();

  if (dados.erro) {
    painel.innerHTML = `<div class="cenas-status">${dados.erro}</div>`;
    return;
  }

  painel.dataset.carregado = "true";
  painel.innerHTML = `
    <div class="cenas-status">Regenerar uma cena só refaz a imagem dela (a IA sorteia de novo) e remonta o vídeo — roteiro, narração e as outras cenas continuam intactos.</div>
    <div class="cenas-grid">${dados.cenas.map((c) => cardDeCena(slug, c)).join("")}</div>`;

  painel.querySelectorAll(".btn-regenerar-cena").forEach((b) => {
    b.addEventListener("click", () => regenerarCena(b));
  });
}

async function regenerarCena(botao) {
  const slug = botao.dataset.slug;
  const indice = botao.dataset.indice;
  const card = botao.closest(".cena-card");
  const imagem = card.querySelector(".cena-card-img");
  const rotulo = botao.textContent;
  botao.disabled = true;
  botao.textContent = "Gerando…";

  const resposta = await fetch(`/api/videos/${slug}/cenas/${indice}/regenerar`, { method: "POST" });
  const { job_id, erro } = await resposta.json();
  if (erro) {
    botao.disabled = false;
    botao.textContent = rotulo;
    alert(erro);
    return;
  }

  const intervalo = setInterval(async () => {
    const r = await fetch(`/api/jobs/${job_id}`);
    const job = await r.json();
    botao.textContent = `${Math.round(job.progresso)}% — ${job.etapa}`;
    if (job.status === "pronto") {
      clearInterval(intervalo);
      botao.disabled = false;
      botao.textContent = "Regenerar essa cena";
      if (imagem && imagem.tagName === "IMG") imagem.src = job.resultado.cena_imagem;
      // atualiza só a miniatura da linha (se essa era a cena 0) sem recarregar
      // a fila inteira — assim o painel de cenas continua aberto pra você
      // poder corrigir mais de uma em sequência.
      if (job.resultado.thumbnail) {
        const thumbImg = document.querySelector(`.video-row[data-slug="${slug}"] .video-thumb img`);
        if (thumbImg) thumbImg.src = job.resultado.thumbnail;
      }
    } else if (job.status === "erro") {
      clearInterval(intervalo);
      botao.disabled = false;
      botao.textContent = rotulo;
      alert(`Deu erro: ${job.erro}`);
    }
  }, 1200);
}

async function regenerarThumbnail(botao) {
  const slug = botao.dataset.slug;
  const linha = botao.closest(".video-row");
  const imagem = linha.querySelector(".video-thumb img");
  botao.disabled = true;

  const resposta = await fetch(`/api/videos/${slug}/thumbnail/regenerar`, { method: "POST" });
  const dados = await resposta.json();
  botao.disabled = false;
  if (dados.erro) {
    alert(dados.erro);
    return;
  }
  if (imagem) imagem.src = dados.thumbnail;
}

async function regenerarVideo(botao) {
  const slug = botao.dataset.slug;
  const manterRoteiro = botao.dataset.manterRoteiro !== "false";
  const linha = botao.closest(".video-row");
  const status = linha.querySelector(".video-meta-status");
  const botoesDaLinha = linha.querySelectorAll(".btn-regenerar");
  botoesDaLinha.forEach((b) => (b.disabled = true));
  status.textContent = manterRoteiro ? "Gerando de novo (mesmo roteiro)…" : "Gerando de novo (roteiro novo)…";

  const dados = new FormData();
  dados.set("manter_roteiro", manterRoteiro);
  const resposta = await fetch(`/api/videos/${slug}/regenerar`, { method: "POST", body: dados });
  const { job_id, erro } = await resposta.json();
  if (erro) {
    status.textContent = erro;
    botoesDaLinha.forEach((b) => (b.disabled = false));
    return;
  }

  const intervalo = setInterval(async () => {
    const r = await fetch(`/api/jobs/${job_id}`);
    const job = await r.json();
    status.textContent = `Gerando de novo… ${Math.round(job.progresso)}% — ${job.etapa}`;
    if (job.status === "pronto") {
      clearInterval(intervalo);
      carregarFila();
      carregarPainel();
    } else if (job.status === "erro") {
      clearInterval(intervalo);
      status.textContent = `Deu erro: ${job.erro}`;
      botoesDaLinha.forEach((b) => (b.disabled = false));
    }
  }, 1200);
}

// ---------------- Contexto do canal ----------------

const formCanal = document.getElementById("form-canal");
const canalStatus = document.getElementById("canal-status");

fetch("/api/canal")
  .then((r) => r.json())
  .then((dados) => { formCanal.querySelector("[name=contexto]").value = dados.contexto || ""; });

formCanal.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await fetch("/api/canal", { method: "POST", body: new FormData(formCanal) });
  canalStatus.textContent = "Salvo — os próximos roteiros já usam esse contexto.";
  setTimeout(() => (canalStatus.textContent = ""), 4000);
});

// ---------------- Novo vídeo: sem narração + som de fundo ----------------

const camposNarrado = document.getElementById("campos-narrado");
const campoDuracao = document.getElementById("campo-duracao");
const campoSemNarracao = document.getElementById("campo-sem-narracao");
const campoSomFundoAtivo = document.getElementById("campo-som-fundo-ativo");
const camposSomFundo = document.getElementById("campos-som-fundo");
const campoSomFundoTipo = document.getElementById("campo-som-fundo-tipo");
const campoSomFundoDescricao = document.querySelector("[name=som_fundo_descricao]");
const linhaSomFundoDescricao = document.getElementById("linha-som-fundo-descricao");

function aplicarEstadoSomFundo() {
  const ativo = campoSomFundoAtivo.checked;
  camposSomFundo.hidden = !ativo;
  // desabilitado = não entra no formulário — assim, quando o som de fundo
  // está desligado, nenhum som_fundo_tipo é enviado por engano.
  campoSomFundoTipo.disabled = !ativo;
  campoSomFundoDescricao.disabled = !ativo || campoSomFundoTipo.value !== "outro";
}

campoSemNarracao.addEventListener("change", () => {
  const semNarracao = campoSemNarracao.checked;
  camposNarrado.hidden = semNarracao;
  campoDuracao.value = semNarracao ? 15 : 1;

  // sem narração, o som de fundo é o áudio inteiro do vídeo — obrigatório
  if (semNarracao) campoSomFundoAtivo.checked = true;
  campoSomFundoAtivo.disabled = semNarracao;
  aplicarEstadoSomFundo();
});

campoSomFundoAtivo.addEventListener("change", aplicarEstadoSomFundo);

campoSomFundoTipo.addEventListener("change", () => {
  linhaSomFundoDescricao.hidden = campoSomFundoTipo.value !== "outro";
  aplicarEstadoSomFundo();
});

aplicarEstadoSomFundo();

// ---------------- Novo vídeo: pré-visualizar roteiro ----------------

const btnPreviewRoteiro = document.getElementById("btn-preview-roteiro");
const previewRoteiroStatus = document.getElementById("preview-roteiro-status");
const campoRoteiro = document.getElementById("campo-roteiro");
const campoTitulo = document.querySelector("[name=titulo]");
const campoDescricaoVideo = document.querySelector("[name=descricao_video]");

btnPreviewRoteiro.addEventListener("click", async () => {
  const titulo = campoTitulo.value.trim();
  if (!titulo) {
    previewRoteiroStatus.textContent = "Escreve o título primeiro.";
    campoTitulo.focus();
    return;
  }

  btnPreviewRoteiro.disabled = true;
  previewRoteiroStatus.textContent = "Escrevendo o roteiro…";

  const dados = new FormData();
  dados.set("titulo", titulo);
  dados.set("duracao_alvo", campoDuracao.value || "1");
  dados.set("descricao_video", campoDescricaoVideo.value || "");

  try {
    const resposta = await fetch("/api/roteiro/preview", { method: "POST", body: dados });
    const dadosResposta = await resposta.json();
    if (dadosResposta.erro) {
      previewRoteiroStatus.textContent = `Deu erro: ${dadosResposta.erro}`;
    } else {
      campoRoteiro.value = dadosResposta.roteiro;
      previewRoteiroStatus.textContent = "Pronto — revise e edite à vontade antes de gerar o vídeo.";
    }
  } catch {
    previewRoteiroStatus.textContent = "Deu erro de conexão, tenta de novo.";
  } finally {
    btnPreviewRoteiro.disabled = false;
  }
});

// ---------------- Novo vídeo: envio + progresso ----------------

const form = document.getElementById("form-novo");
const progressoCard = document.getElementById("progresso-card");
const resultadoCard = document.getElementById("resultado-card");
const erroCard = document.getElementById("erro-card");
const progressFill = document.getElementById("progress-fill");
const progressoEtapa = document.getElementById("progresso-etapa");
const progressoPct = document.getElementById("progresso-pct");

let poller = null;

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  resultadoCard.hidden = true;
  erroCard.hidden = true;
  progressoCard.hidden = false;
  progressFill.style.width = "0%";
  progressoPct.textContent = "0%";
  progressoEtapa.textContent = "Iniciando…";
  form.querySelector(".btn-primary").disabled = true;

  const dados = new FormData(form);
  const resposta = await fetch("/api/videos", { method: "POST", body: dados });
  const { job_id } = await resposta.json();

  if (poller) clearInterval(poller);
  poller = setInterval(() => acompanharJob(job_id), 1200);
});

async function acompanharJob(jobId) {
  const resposta = await fetch(`/api/jobs/${jobId}`);
  const job = await resposta.json();

  progressFill.style.width = `${job.progresso}%`;
  progressoPct.textContent = `${Math.round(job.progresso)}%`;
  progressoEtapa.textContent = job.etapa;

  if (job.status === "pronto") {
    clearInterval(poller);
    form.querySelector(".btn-primary").disabled = false;
    mostrarResultado(job.resultado);
  } else if (job.status === "erro") {
    clearInterval(poller);
    form.querySelector(".btn-primary").disabled = false;
    progressoCard.hidden = true;
    erroCard.hidden = false;
    document.getElementById("erro-conteudo").textContent = job.erro;
  }
}

function mostrarResultado(resultado) {
  progressoCard.hidden = true;
  resultadoCard.hidden = false;

  const tags = (resultado.tags || [])
    .map((t) => `<span class="tag-pill">#${t}</span>`)
    .join("");

  const thumbHtml = resultado.thumbnail
    ? `<div class="resultado-formato"><h3>Thumbnail</h3><img src="${resultado.thumbnail}" style="width:100%;max-width:420px;border-radius:10px;border:1px solid var(--border);display:block">
       <div class="resultado-actions"><a href="${resultado.thumbnail}" download>Baixar thumbnail</a></div></div>`
    : "";

  document.getElementById("resultado-conteudo").innerHTML = `
    ${thumbHtml}
    <div class="resultado-formato">
      <h3>16:9 — vídeo normal (${formatarDuracao(resultado.duracao_segundos)})</h3>
      <video controls src="${resultado.video_16_9}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_16_9}" download>Baixar .mp4</a>
      </div>
    </div>
    <div class="resultado-formato">
      <h3>9:16 — Shorts</h3>
      <video controls src="${resultado.video_9_16}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_9_16}" download>Baixar .mp4</a>
      </div>
    </div>
    ${tags ? `<div class="resultado-formato"><h3>Hashtags sugeridas</h3><div class="tags-list">${tags}</div></div>` : ""}`;
}

// ---------------- Conexão com o YouTube (perfil no menu lateral) ----------------

const youtubeDot = document.getElementById("youtube-dot");
const youtubeStatusTexto = document.getElementById("youtube-status-texto");
const brandLink = document.getElementById("brand-link");
const brandAvatar = document.getElementById("brand-avatar");
const brandName = document.getElementById("brand-name");
const brandSub = document.getElementById("brand-sub");

let youtubeConectando = false;

async function atualizarStatusYoutube() {
  const resposta = await fetch("/api/youtube/status");
  const dados = await resposta.json();

  if (!dados.client_secret_presente) {
    youtubeDot.className = "dot dot-dim";
    youtubeStatusTexto.textContent = "client_secret.json não encontrado na raiz do projeto.";
    brandSub.textContent = "YouTube não configurado";
    return null;
  }

  if (dados.conectando) {
    youtubeConectando = true;
    youtubeDot.className = "dot dot-pending";
    youtubeStatusTexto.textContent = "Esperando você autorizar no navegador…";
    brandSub.textContent = "Conectando…";
  } else if (dados.conectado) {
    youtubeConectando = false;
    youtubeDot.className = "dot dot-positive";
    youtubeStatusTexto.textContent = "Conectado";
    carregarEstatisticasCanal();
  } else {
    youtubeConectando = false;
    youtubeDot.className = "dot dot-negative";
    youtubeStatusTexto.textContent = dados.erro ? `Não conectado (${dados.erro})` : "Não conectado";
    brandName.textContent = "Meu Canal";
    brandSub.textContent = "Clique pra conectar o YouTube";
    brandAvatar.innerHTML = "MC";
  }
  return dados;
}

async function carregarEstatisticasCanal() {
  const linha = document.getElementById("stats-row-youtube");
  const resposta = await fetch("/api/youtube/estatisticas");
  const dados = await resposta.json();

  if (dados.erro) {
    // provavelmente conectou antes do escopo de leitura existir.
    linha.hidden = true;
    youtubeStatusTexto.textContent = "Conectado (reconecte pra liberar inscritos/visualizações)";
    brandSub.textContent = "Reconecte pra ver o perfil";
    return;
  }

  document.getElementById("stat-canal-nome").textContent = dados.nome_canal ? `Inscritos — ${dados.nome_canal}` : "Inscritos";
  document.getElementById("stat-inscritos").textContent = dados.inscritos.toLocaleString("pt-BR");
  document.getElementById("stat-visualizacoes").textContent = dados.visualizacoes.toLocaleString("pt-BR");
  linha.hidden = false;

  brandName.textContent = dados.nome_canal || "Meu Canal";
  brandSub.textContent = `${dados.inscritos.toLocaleString("pt-BR")} inscritos — ver canal ↗`;
  if (dados.avatar_url) brandAvatar.innerHTML = `<img src="${dados.avatar_url}" alt="">`;
  brandLink.href = dados.canal_url || "#";
  brandLink.target = "_blank";
  brandLink.rel = "noopener";
  brandLink.title = "Abrir seu canal no YouTube";
}

brandLink.addEventListener("click", async (ev) => {
  // conectado: deixa o link abrir o canal normalmente. Não conectado: em vez
  // de navegar pro "#", dispara o login.
  if (brandLink.getAttribute("target") === "_blank") return;
  ev.preventDefault();
  if (youtubeConectando) return;

  const poller = setInterval(async () => {
    const dados = await atualizarStatusYoutube();
    if (dados && !dados.conectando) clearInterval(poller);
  }, 1500);
  await fetch("/api/youtube/conectar", { method: "POST" });
});

// ---------------- Agente: sugestões de ideias ----------------

const btnAgenteSugerir = document.getElementById("btn-agente-sugerir");
const agenteResultadoCard = document.getElementById("agente-resultado-card");
const agenteLista = document.getElementById("agente-lista");
const agenteAviso = document.getElementById("agente-aviso");

btnAgenteSugerir.addEventListener("click", async () => {
  btnAgenteSugerir.disabled = true;
  agenteAviso.textContent = "Pensando em ideias…";
  agenteResultadoCard.hidden = true;

  try {
    const resposta = await fetch("/api/agente/sugestoes", { method: "POST" });
    const dados = await resposta.json();

    if (dados.erro) {
      agenteAviso.textContent = `Deu erro: ${dados.erro}`;
      return;
    }

    agenteAviso.textContent = dados.aviso || "";
    agenteLista.innerHTML = dados.ideias
      .map(
        (ideia) => `
        <div class="video-row">
          <div class="video-info"><div class="video-title" style="text-transform:none">${ideia}</div></div>
          <div class="video-links">
            <button type="button" class="btn-secondary btn-usar-ideia" data-titulo="${ideia.replace(/"/g, "&quot;")}">Usar esse título</button>
          </div>
        </div>`
      )
      .join("");
    agenteResultadoCard.hidden = false;

    agenteLista.querySelectorAll(".btn-usar-ideia").forEach((botao) => {
      botao.addEventListener("click", () => {
        campoTitulo.value = botao.dataset.titulo;
        trocarAba("novo");
        campoTitulo.focus();
      });
    });
  } catch {
    agenteAviso.textContent = "Deu erro de conexão, tenta de novo.";
  } finally {
    btnAgenteSugerir.disabled = false;
  }
});

atualizarStatusYoutube();
carregarPainel();
