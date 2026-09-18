const TITULOS = { painel: "Painel", canais: "Canais", agente: "Agente", novo: "Novo vídeo", fila: "Fila", base: "Base" };

function trocarAba(nome) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${nome}`));
  document.getElementById("page-title").textContent = TITULOS[nome];
  if (nome === "painel") carregarPainel();
  if (nome === "fila") carregarFila();
  if (nome === "canais") carregarCanais();
  if (nome === "base") carregarBase();
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

function formatarDataPostagem(iso, hora) {
  if (!iso) return "sem data definida";
  const [ano, mes, dia] = iso.split("-");
  return hora ? `postar em ${dia}/${mes}/${ano} às ${hora}` : `postar em ${dia}/${mes}/${ano}`;
}

const STATUS_FILA = {
  publicado: { rotulo: "publicado", classe: "status-publicado" },
  pronto: { rotulo: "pronto para enviar", classe: "status-pronto" },
  aguardando: { rotulo: "aguardando data de publicação", classe: "status-aguardando" },
  erro: { rotulo: "erro ao publicar", classe: "status-erro" },
};

function statusBadge(v) {
  const info = STATUS_FILA[v.status];
  if (!info) return "";
  return `<span class="status-badge ${info.classe}">${info.rotulo}</span>`;
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

let mostrarBadgeCanal = false; // só quando existe mais de 1 canal, evita ruído pra quem usa só 1

function linhaDeVideo(v, comRegenerar) {
  const rotulos = [];
  if (v.sem_narracao) rotulos.push("sem narração");
  if (v.som_fundo_tipo) rotulos.push(`som: ${v.som_fundo_tipo}`);
  if (v.duracao_segundos) rotulos.push(formatarDuracao(v.duracao_segundos));
  const modoLabel = rotulos.length ? `· ${rotulos.join(", ")}` : "";
  const badgeCanal = mostrarBadgeCanal && v.canal_nome ? `<span class="canal-badge">${v.canal_nome}</span>` : "";
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
  const badgeStatus = v.status === "pronto" || v.status === "aguardando" ? statusBadge(v) : "";
  return `
    <div class="video-item">
      <div class="video-row" data-slug="${v.slug}">
        <div class="video-thumb">${thumb}</div>
        <div class="video-info">
          <div class="video-title">${v.titulo} ${badgeCanal}</div>
          <div class="video-meta video-meta-status">${formatarDataPostagem(v.data_postagem, v.hora_postagem)} ${modoLabel}</div>
          ${publicacao ? `<div class="video-meta">${publicacao}</div>` : ""}
          ${badgeStatus ? `<div class="video-meta">${badgeStatus}</div>` : ""}
        </div>
        <div class="video-links">
          <a href="${v.video_16_9}" target="_blank">16:9</a>
          <a href="${v.video_9_16}" target="_blank">Shorts</a>
          ${botaoRegenerar}
        </div>
      </div>
      ${comRegenerar ? `<div class="thumb-painel" data-slug="${v.slug}" data-texto="${(v.thumbnail_texto || v.titulo).replace(/"/g, "&quot;")}" data-cor="${v.thumbnail_cor || ""}" data-posicao="${v.thumbnail_posicao || "baixo-centro"}" data-tamanho-px="${v.thumbnail_tamanho_px || 80}" data-pos-x="${v.thumbnail_pos_x ?? ""}" data-pos-y="${v.thumbnail_pos_y ?? ""}" data-base="${v.thumbnail_base || ""}"></div>` : ""}
      ${comRegenerar && v.tem_cenas ? `<div class="cenas-painel" data-slug="${v.slug}"></div>` : ""}
    </div>`;
}

async function buscarVideos() {
  const resposta = await fetch("/api/videos");
  return resposta.ok ? resposta.json() : [];
}

function desenharGraficoVideos(videos) {
  const canvas = document.getElementById("grafico-videos");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const largura = canvas.clientWidth || 600;
  canvas.width = largura;
  canvas.height = 120;
  ctx.clearRect(0, 0, largura, 120);

  const SEMANAS = 8;
  const umaSemanaMs = 7 * 24 * 60 * 60 * 1000;
  const agora = Date.now();
  const contagens = new Array(SEMANAS).fill(0);
  videos.forEach((v) => {
    if (!v.modificado_em) return;
    const semanasAtras = Math.floor((agora - v.modificado_em * 1000) / umaSemanaMs);
    const indice = SEMANAS - 1 - semanasAtras;
    if (indice >= 0 && indice < SEMANAS) contagens[indice]++;
  });

  const max = Math.max(1, ...contagens);
  const larguraBarra = largura / SEMANAS;
  const corBarra = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#7c9eff";
  ctx.fillStyle = corBarra || "#7c9eff";
  contagens.forEach((valor, i) => {
    const altura = valor ? Math.max(4, (valor / max) * 90) : 0;
    ctx.fillRect(i * larguraBarra + 4, 110 - altura, larguraBarra - 8, altura);
    if (valor) {
      ctx.fillStyle = "#8892a6";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(valor), i * larguraBarra + larguraBarra / 2, 108 - altura - 4);
      ctx.fillStyle = corBarra || "#7c9eff";
    }
  });
}

async function carregarPainel() {
  const videos = await buscarVideos();
  document.getElementById("stat-total").textContent = videos.length;
  const totalSegundos = videos.reduce((soma, v) => soma + (v.duracao_segundos || 0), 0);
  document.getElementById("stat-duracao").textContent = `${Math.round(totalSegundos / 60)} min`;
  const lista = document.getElementById("painel-lista");
  lista.innerHTML = videos.length
    ? videos.slice(0, 6).map((v) => linhaDeVideo(v)).join("")
    : '<div class="empty">Nenhum vídeo ainda — vá em "Novo vídeo" pra gerar o primeiro.</div>';
  desenharGraficoVideos(videos);
}

let videosFilaCache = [];

function aplicarFiltrosFila() {
  const canal = document.getElementById("filtro-canal").value;
  const status = document.getElementById("filtro-status").value;
  const minMin = parseFloat(document.getElementById("filtro-duracao-min").value);
  const maxMin = parseFloat(document.getElementById("filtro-duracao-max").value);

  const filtrados = videosFilaCache.filter((v) => {
    if (canal && v.canal_id !== canal) return false;
    if (status && v.status !== status) return false;
    const minutos = (v.duracao_segundos || 0) / 60;
    if (!isNaN(minMin) && minutos < minMin) return false;
    if (!isNaN(maxMin) && minutos > maxMin) return false;
    return true;
  });

  const lista = document.getElementById("fila-lista");
  lista.innerHTML = filtrados.length
    ? filtrados.map((v) => linhaDeVideo(v, true)).join("")
    : '<div class="empty">Nenhum vídeo bate com esses filtros.</div>';

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

async function carregarFila() {
  videosFilaCache = await buscarVideos();

  const seletorCanalFiltro = document.getElementById("filtro-canal");
  const canaisUnicos = [...new Map(videosFilaCache.map((v) => [v.canal_id, v.canal_nome])).entries()];
  const valorAtual = seletorCanalFiltro.value;
  seletorCanalFiltro.innerHTML =
    '<option value="">Todos</option>' + canaisUnicos.map(([id, nome]) => `<option value="${id}">${nome}</option>`).join("");
  seletorCanalFiltro.value = valorAtual;

  aplicarFiltrosFila();
}

["filtro-canal", "filtro-status", "filtro-duracao-min", "filtro-duracao-max"].forEach((id) => {
  document.getElementById(id).addEventListener("input", aplicarFiltrosFila);
});

// ---------------- Fila: editar texto/cor da thumbnail ----------------

const CORES_THUMB = [
  { nome: "Padrão", hex: "" },
  { nome: "Amarelo", hex: "FFD23F" },
  { nome: "Vermelho", hex: "FF4C4C" },
  { nome: "Verde", hex: "3DDC84" },
  { nome: "Azul", hex: "4DA6FF" },
];

const POSICOES_THUMB = [
  "topo-esquerda", "topo-centro", "topo-direita",
  "centro-esquerda", "centro", "centro-direita",
  "baixo-esquerda", "baixo-centro", "baixo-direita",
];

// aproximação visual das mesmas frações usadas em engine/thumbnail.py, só
// pra posicionar o rótulo arrastável quando você clica numa célula da grade
const FRACAO_GRADE = {
  "topo-esquerda": [0.12, 0.18], "topo-centro": [0.5, 0.18], "topo-direita": [0.88, 0.18],
  "centro-esquerda": [0.12, 0.5], "centro": [0.5, 0.5], "centro-direita": [0.88, 0.5],
  "baixo-esquerda": [0.12, 0.82], "baixo-centro": [0.5, 0.82], "baixo-direita": [0.88, 0.82],
};

const TAMANHO_FONTE_MIN = 24;
const TAMANHO_FONTE_MAX = 190;
const LARGURA_CANVAS_THUMB = 1280; // mesmo LARGURA de engine/thumbnail.py — pra escalar o preview

function escalaPreview(areaPreview) {
  const largura = areaPreview.getBoundingClientRect().width;
  return largura ? largura / LARGURA_CANVAS_THUMB : 460 / LARGURA_CANVAS_THUMB;
}

function alternarPainelThumb(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.thumb-painel[data-slug="${slug}"]`);
  if (!painel) return;

  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder thumbnail" : "editar thumbnail";
  if (!abrindo || painel.dataset.montado === "true") return;

  painel.dataset.montado = "true";
  const textoAtual = painel.dataset.texto || "";
  const corAtual = painel.dataset.cor || "";
  const posicaoAtual = painel.dataset.posicao || "baixo-centro";
  const tamanhoPxAtual = parseInt(painel.dataset.tamanhoPx, 10) || 80;
  const posXSalvo = parseFloat(painel.dataset.posX);
  const posYSalvo = parseFloat(painel.dataset.posY);
  const temPosLivre = !Number.isNaN(posXSalvo) && !Number.isNaN(posYSalvo);
  const baseUrl = painel.dataset.base || "";

  const swatches = CORES_THUMB.map(
    (c) => `<button type="button" class="cor-swatch${c.hex === corAtual ? " selecionada" : ""}" data-hex="${c.hex}" title="${c.nome}" style="background:${c.hex ? "#" + c.hex : "#F6F2E9"}"></button>`
  ).join("");
  const grade = POSICOES_THUMB.map(
    (p) => `<button type="button" class="pos-cel${!temPosLivre && p === posicaoAtual ? " selecionada" : ""}" data-posicao="${p}" title="${p.replace("-", " ")}"></button>`
  ).join("");

  const [fx0, fy0] = temPosLivre ? [posXSalvo, posYSalvo] : FRACAO_GRADE[posicaoAtual] || FRACAO_GRADE["baixo-centro"];

  painel.innerHTML = `
    <p class="hint" style="margin:0 0 10px">Arraste o texto pra qualquer lugar da imagem, ou clique num ponto da grade pra um posicionamento rápido.</p>
    ${baseUrl ? `
      <div class="thumb-preview">
        <img class="thumb-preview-img" src="${baseUrl}" alt="">
        <div class="thumb-preview-texto" style="left:${fx0 * 100}%; top:${fy0 * 100}%; color:${corAtual ? "#" + corAtual : "#F6F2E9"}">${textoAtual}</div>
      </div>` : ""}
    <div class="thumb-form">
      <input type="text" class="thumb-texto" value="${textoAtual}" maxlength="80" placeholder="Texto que aparece na thumbnail">
      <div class="cor-swatches">${swatches}</div>
      <button type="button" class="btn-secondary btn-salvar-thumb">Salvar</button>
      <span class="video-meta thumb-status"></span>
    </div>
    <div class="thumb-tamanho-linha">
      <span class="video-meta">Tamanho da fonte</span>
      <input type="range" class="thumb-tamanho" min="${TAMANHO_FONTE_MIN}" max="${TAMANHO_FONTE_MAX}" step="2" value="${tamanhoPxAtual}">
      <span class="video-meta thumb-tamanho-valor">${tamanhoPxAtual}px</span>
    </div>
    <div class="pos-grade" title="Posição do texto na thumbnail">${grade}</div>
    <div class="thumb-imagens">
      <div class="thumb-imagens-head">
        <span class="video-meta">Imagem de fundo</span>
        <label class="btn-secondary btn-upload-thumb">
          Enviar imagem própria
          <input type="file" class="thumb-upload-input" accept="image/*" hidden>
        </label>
      </div>
      <div class="thumb-imagens-grade"><span class="video-meta">Carregando imagens…</span></div>
    </div>`;

  painel.dataset.modo = temPosLivre ? "livre" : "grade";
  painel.dataset.posX = temPosLivre ? String(posXSalvo) : "";
  painel.dataset.posY = temPosLivre ? String(posYSalvo) : "";

  const rotuloArrastavel = painel.querySelector(".thumb-preview-texto");
  const areaPreview = painel.querySelector(".thumb-preview");

  const aplicarTamanhoPreview = (px) => {
    if (rotuloArrastavel && areaPreview) rotuloArrastavel.style.fontSize = `${px * escalaPreview(areaPreview)}px`;
  };
  aplicarTamanhoPreview(tamanhoPxAtual);

  if (rotuloArrastavel && areaPreview) {
    const moverPara = (clientX, clientY) => {
      const rect = areaPreview.getBoundingClientRect();
      const fx = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
      const fy = Math.min(Math.max((clientY - rect.top) / rect.height, 0), 1);
      rotuloArrastavel.style.left = `${fx * 100}%`;
      rotuloArrastavel.style.top = `${fy * 100}%`;
      painel.dataset.modo = "livre";
      painel.dataset.posX = fx.toFixed(4);
      painel.dataset.posY = fy.toFixed(4);
      painel.querySelectorAll(".pos-cel").forEach((c) => c.classList.remove("selecionada"));
    };

    rotuloArrastavel.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      rotuloArrastavel.setPointerCapture(ev.pointerId);
      moverPara(ev.clientX, ev.clientY);
      const onMove = (e) => moverPara(e.clientX, e.clientY);
      const onUp = () => {
        rotuloArrastavel.removeEventListener("pointermove", onMove);
        rotuloArrastavel.removeEventListener("pointerup", onUp);
      };
      rotuloArrastavel.addEventListener("pointermove", onMove);
      rotuloArrastavel.addEventListener("pointerup", onUp);
    });
  }

  painel.querySelectorAll(".cor-swatch").forEach((sw) => {
    sw.addEventListener("click", () => {
      painel.querySelectorAll(".cor-swatch").forEach((s) => s.classList.remove("selecionada"));
      sw.classList.add("selecionada");
      if (rotuloArrastavel) rotuloArrastavel.style.color = sw.dataset.hex ? `#${sw.dataset.hex}` : "#F6F2E9";
    });
  });

  painel.querySelectorAll(".pos-cel").forEach((cel) => {
    cel.addEventListener("click", () => {
      painel.querySelectorAll(".pos-cel").forEach((c) => c.classList.remove("selecionada"));
      cel.classList.add("selecionada");
      painel.dataset.modo = "grade";
      painel.dataset.posX = "";
      painel.dataset.posY = "";
      if (rotuloArrastavel) {
        const [fx, fy] = FRACAO_GRADE[cel.dataset.posicao];
        rotuloArrastavel.style.left = `${fx * 100}%`;
        rotuloArrastavel.style.top = `${fy * 100}%`;
      }
    });
  });

  const campoTexto = painel.querySelector(".thumb-texto");
  campoTexto.addEventListener("input", () => {
    if (rotuloArrastavel) rotuloArrastavel.textContent = campoTexto.value;
  });

  const campoTamanho = painel.querySelector(".thumb-tamanho");
  const valorTamanho = painel.querySelector(".thumb-tamanho-valor");
  campoTamanho.addEventListener("input", () => {
    valorTamanho.textContent = `${campoTamanho.value}px`;
    aplicarTamanhoPreview(parseInt(campoTamanho.value, 10));
  });

  carregarImagensThumb(slug, painel);

  painel.querySelector(".thumb-upload-input").addEventListener("change", (ev) => {
    const arquivo = ev.target.files[0];
    if (arquivo) uploadImagemThumb(slug, painel, arquivo);
  });

  painel.querySelector(".btn-salvar-thumb").addEventListener("click", () => salvarThumb(slug, painel));
}

async function carregarImagensThumb(slug, painel) {
  const grade = painel.querySelector(".thumb-imagens-grade");
  if (!grade) return;
  try {
    const resposta = await fetch(`/api/videos/${slug}/thumbnail/imagens`);
    const dados = await resposta.json();
    if (dados.erro || !dados.imagens?.length) {
      grade.innerHTML = '<span class="video-meta">Nenhuma imagem de cena disponível ainda.</span>';
      return;
    }
    grade.innerHTML = dados.imagens
      .map((img) => `<button type="button" class="thumb-img-opcao${img.atual ? " selecionada" : ""}" data-nome="${img.nome}" title="${img.nome}"><img src="${img.url}" alt=""></button>`)
      .join("");
    grade.querySelectorAll(".thumb-img-opcao").forEach((op) => {
      op.addEventListener("click", () => escolherImagemThumb(slug, painel, op));
    });
  } catch {
    grade.innerHTML = '<span class="video-meta">Deu erro carregando as imagens.</span>';
  }
}

async function _atualizarBaseThumb(slug, painel, resultado) {
  const thumbImg = document.querySelector(`.video-row[data-slug="${slug}"] .video-thumb img`);
  if (thumbImg && resultado.thumbnail) thumbImg.src = resultado.thumbnail;
  if (resultado.thumbnail_base) {
    painel.dataset.base = resultado.thumbnail_base;
    const img = painel.querySelector(".thumb-preview-img");
    if (img) img.src = resultado.thumbnail_base;
  }
}

async function escolherImagemThumb(slug, painel, botaoOpcao) {
  painel.querySelectorAll(".thumb-img-opcao").forEach((op) => op.classList.remove("selecionada"));
  botaoOpcao.classList.add("selecionada");

  const dados = new FormData();
  dados.set("imagem", botaoOpcao.dataset.nome);
  const resposta = await fetch(`/api/videos/${slug}/thumbnail/escolher-imagem`, { method: "POST", body: dados });
  const resultado = await resposta.json();
  if (resultado.erro) {
    alert(resultado.erro);
    return;
  }
  await _atualizarBaseThumb(slug, painel, resultado);
}

async function uploadImagemThumb(slug, painel, arquivo) {
  const head = painel.querySelector(".thumb-imagens-head .video-meta");
  const rotuloOriginal = head.textContent;
  head.textContent = "Enviando…";

  const dados = new FormData();
  dados.set("arquivo", arquivo);
  try {
    const resposta = await fetch(`/api/videos/${slug}/thumbnail/upload`, { method: "POST", body: dados });
    const resultado = await resposta.json();
    head.textContent = rotuloOriginal;
    if (resultado.erro) {
      alert(resultado.erro);
      return;
    }
    await _atualizarBaseThumb(slug, painel, resultado);
    carregarImagensThumb(slug, painel);
  } catch {
    head.textContent = rotuloOriginal;
    alert("Deu erro de conexão, tenta de novo.");
  }
}

async function salvarThumb(slug, painel) {
  const texto = painel.querySelector(".thumb-texto").value.trim();
  const corSelecionada = painel.querySelector(".cor-swatch.selecionada");
  const posSelecionada = painel.querySelector(".pos-cel.selecionada");
  const tamanhoPx = painel.querySelector(".thumb-tamanho").value;
  const status = painel.querySelector(".thumb-status");
  const botaoSalvar = painel.querySelector(".btn-salvar-thumb");

  if (!texto) {
    status.textContent = "Escreve algum texto primeiro.";
    return;
  }

  botaoSalvar.disabled = true;
  status.textContent = "Salvando…";

  const cor = corSelecionada ? corSelecionada.dataset.hex : "";
  const posicao = posSelecionada ? posSelecionada.dataset.posicao : "baixo-centro";
  const modoLivre = painel.dataset.modo === "livre" && painel.dataset.posX && painel.dataset.posY;
  const dados = new FormData();
  dados.set("texto", texto);
  dados.set("cor", cor);
  dados.set("posicao", posicao);
  dados.set("tamanho_px", tamanhoPx);
  if (modoLivre) {
    dados.set("pos_x", painel.dataset.posX);
    dados.set("pos_y", painel.dataset.posY);
  }

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
    painel.dataset.texto = texto;
    painel.dataset.cor = cor;
    painel.dataset.posicao = posicao;
    painel.dataset.tamanhoPx = tamanhoPx;
    if (!modoLivre) {
      painel.dataset.posX = "";
      painel.dataset.posY = "";
    }
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

// ---------------- Canais (seletor no menu + aba de gerenciar) ----------------

const seletorCanal = document.getElementById("seletor-canal");
const novoVideoCanalAtivo = document.getElementById("novo-video-canal-ativo");

async function buscarCanais() {
  const resposta = await fetch("/api/canais");
  return resposta.ok ? resposta.json() : { canais: [], ativo: null };
}

async function popularSeletorCanal() {
  const { canais, ativo } = await buscarCanais();
  mostrarBadgeCanal = canais.length > 1;
  seletorCanal.innerHTML = canais
    .map((c) => `<option value="${c.id}"${c.id === ativo ? " selected" : ""}>${c.nome}</option>`)
    .join("");
  const canalAtivo = canais.find((c) => c.id === ativo);
  if (novoVideoCanalAtivo) {
    novoVideoCanalAtivo.textContent = canalAtivo ? `Canal: ${canalAtivo.nome}` : "";
  }
  return { canais, ativo };
}

seletorCanal.addEventListener("change", async () => {
  await fetch(`/api/canais/${seletorCanal.value}/ativar`, { method: "POST" });
  await popularSeletorCanal();
  // perfil (YouTube) e estatísticas do Painel são sempre do canal ativo
  atualizarStatusYoutube();
  if (document.getElementById("tab-painel").classList.contains("active")) carregarPainel();
  if (document.getElementById("tab-canais").classList.contains("active")) carregarCanais();
});

function linhaDeCanal(c, ativo) {
  return `
    <div class="canal-card" data-id="${c.id}">
      <div class="canal-card-head">
        <input type="text" class="canal-nome-input" value="${c.nome.replace(/"/g, "&quot;")}" maxlength="60">
        ${c.id === ativo ? '<span class="tag-pill">ativo</span>' : `<button type="button" class="btn-secondary btn-ativar-canal" data-id="${c.id}">Definir como ativo</button>`}
      </div>
      <label>
        <span>Contexto (nicho, tom, público)</span>
        <textarea class="canal-contexto-input" rows="3">${c.contexto || ""}</textarea>
      </label>
      <label class="canal-conta-label">
        <span>Conta do YouTube (avançado — normalmente não precisa mexer; só se quiser apontar esse canal pra uma conta já conectada com outro nome)</span>
        <input type="text" class="canal-conta-input" value="${(c.conta_youtube || "").replace(/"/g, "&quot;")}" maxlength="60">
      </label>
      <div class="canal-card-actions">
        <button type="button" class="btn-secondary btn-salvar-canal" data-id="${c.id}">Salvar</button>
        <span class="video-meta canal-yt-status" data-id="${c.id}">Verificando YouTube…</span>
      </div>
    </div>`;
}

async function carregarCanais() {
  const lista = document.getElementById("canais-lista");
  const { canais, ativo } = await buscarCanais();
  lista.innerHTML = canais.map((c) => linhaDeCanal(c, ativo)).join("");

  lista.querySelectorAll(".btn-ativar-canal").forEach((botao) => {
    botao.addEventListener("click", async () => {
      await fetch(`/api/canais/${botao.dataset.id}/ativar`, { method: "POST" });
      await popularSeletorCanal();
      atualizarStatusYoutube();
      carregarCanais();
    });
  });

  lista.querySelectorAll(".btn-salvar-canal").forEach((botao) => {
    botao.addEventListener("click", async () => {
      const card = botao.closest(".canal-card");
      const nome = card.querySelector(".canal-nome-input").value.trim();
      const contexto = card.querySelector(".canal-contexto-input").value;
      const contaYoutube = card.querySelector(".canal-conta-input").value.trim();
      const dados = new FormData();
      dados.set("nome", nome);
      dados.set("contexto", contexto);
      dados.set("conta_youtube", contaYoutube);
      botao.disabled = true;
      botao.textContent = "Salvando…";
      await fetch(`/api/canais/${botao.dataset.id}/editar`, { method: "POST", body: dados });
      botao.disabled = false;
      botao.textContent = "Salvo!";
      setTimeout(() => (botao.textContent = "Salvar"), 2000);
      popularSeletorCanal();
      atualizarStatusYoutube(); // se era o canal ativo, o perfil pode ter mudado de conta
      carregarCanais(); // status "YouTube: conectado/não conectado" do card pode ter mudado
    });
  });

  // status do YouTube de cada canal, só leitura (conectar é sempre pelo
  // perfil, no canal ativo — evita duplicar o fluxo de conexão em cada card)
  canais.forEach(async (c) => {
    const spanStatus = lista.querySelector(`.canal-yt-status[data-id="${c.id}"]`);
    if (!spanStatus) return;
    try {
      const resposta = await fetch(`/api/youtube/status?canal_id=${c.id}`);
      const dados = await resposta.json();
      spanStatus.textContent = dados.conectado ? "YouTube: conectado" : "YouTube: não conectado";
    } catch {
      spanStatus.textContent = "";
    }
  });
}

const formNovoCanal = document.getElementById("form-novo-canal");
const novoCanalStatus = document.getElementById("novo-canal-status");

formNovoCanal.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  novoCanalStatus.textContent = "Criando…";
  const resposta = await fetch("/api/canais", { method: "POST", body: new FormData(formNovoCanal) });
  const dados = await resposta.json();
  if (dados.erro) {
    novoCanalStatus.textContent = `Deu erro: ${dados.erro}`;
    return;
  }
  formNovoCanal.reset();
  novoCanalStatus.textContent = "Canal criado!";
  setTimeout(() => (novoCanalStatus.textContent = ""), 3000);
  popularSeletorCanal();
  carregarCanais();
});

popularSeletorCanal();

// ---------------- Novo vídeo: sem narração + som de fundo ----------------

const camposNarrado = document.getElementById("campos-narrado");
const campoDuracao = document.getElementById("campo-duracao");
const campoSemNarracao = document.getElementById("campo-sem-narracao");
const campoSomFundoAtivo = document.getElementById("campo-som-fundo-ativo");
const camposSomFundo = document.getElementById("campos-som-fundo");
const campoSomFundoTipo = document.getElementById("campo-som-fundo-tipo");
const campoSomFundoDescricao = document.querySelector("[name=som_fundo_descricao]");
const linhaSomFundoDescricao = document.getElementById("linha-som-fundo-descricao");
const campoSomFundoBiblioteca = document.getElementById("campo-som-fundo-biblioteca");
const linhaSomFundoBiblioteca = document.getElementById("linha-som-fundo-biblioteca");

function aplicarEstadoSomFundo() {
  const ativo = campoSomFundoAtivo.checked;
  camposSomFundo.hidden = !ativo;
  // desabilitado = não entra no formulário — assim, quando o som de fundo
  // está desligado, nenhum som_fundo_tipo é enviado por engano.
  campoSomFundoTipo.disabled = !ativo;
  campoSomFundoDescricao.disabled = !ativo || campoSomFundoTipo.value !== "outro";
  campoSomFundoBiblioteca.disabled = !ativo || campoSomFundoTipo.value !== "biblioteca";
}

async function popularSelectAudiosBiblioteca() {
  try {
    const dados = await fetch("/api/biblioteca").then((r) => r.json());
    const nomes = dados.audios_nomes || [];
    const valorAtual = campoSomFundoBiblioteca.value;
    campoSomFundoBiblioteca.innerHTML = nomes.length
      ? nomes.map((nome) => `<option value="${nome}">${nome}</option>`).join("")
      : '<option value="">Nenhum importado ainda — vá na aba Base</option>';
    if (nomes.includes(valorAtual)) campoSomFundoBiblioteca.value = valorAtual;
  } catch {
    // silencioso — se falhar, o select só fica com a opção padrão
  }
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
  linhaSomFundoBiblioteca.hidden = campoSomFundoTipo.value !== "biblioteca";
  if (campoSomFundoTipo.value === "biblioteca") popularSelectAudiosBiblioteca();
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

// ---------------- Agente: campo livre (perguntas, ideias, comandos) ----------------

const formAgenteLivre = document.getElementById("form-agente-livre");
const btnAgenteEnviar = document.getElementById("btn-agente-enviar");
const agenteLivreResposta = document.getElementById("agente-livre-resposta");

formAgenteLivre.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const campoMensagem = document.getElementById("campo-agente-mensagem");
  const mensagem = campoMensagem.value.trim();
  if (!mensagem) return;

  btnAgenteEnviar.disabled = true;
  agenteLivreResposta.textContent = "Pensando…";

  try {
    const dados = new FormData();
    dados.set("mensagem", mensagem);
    const resposta = await fetch("/api/agente/perguntar", { method: "POST", body: dados });
    const resultado = await resposta.json();

    if (resultado.erro) {
      agenteLivreResposta.textContent = `Deu erro: ${resultado.erro}`;
      return;
    }

    agenteLivreResposta.textContent = resultado.resposta || "";
    if (resultado.acao === "reagendar") {
      campoMensagem.value = "";
      carregarFila();
      carregarPainel();
    }
  } catch {
    agenteLivreResposta.textContent = "Deu erro de conexão, tenta de novo.";
  } finally {
    btnAgenteEnviar.disabled = false;
  }
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

// ---------------- Base: biblioteca de áudios e imagens importados ----------------

async function carregarBase() {
  try {
    const dados = await fetch("/api/biblioteca").then((r) => r.json());

    const listaAudios = document.getElementById("base-audios-lista");
    listaAudios.innerHTML = dados.audios_nomes?.length
      ? dados.audios_nomes
          .map(
            (nome, i) => `
        <div class="base-audio-item">
          <audio controls src="${dados.audios[i]}" style="height:32px"></audio>
          <span class="video-meta" style="flex:1">${nome}</span>
          <button type="button" class="btn-regenerar btn-regenerar-sutil btn-remover-audio-base" data-nome="${nome}">remover</button>
        </div>`
          )
          .join("")
      : '<div class="empty">Nenhum áudio importado ainda.</div>';

    listaAudios.querySelectorAll(".btn-remover-audio-base").forEach((botao) => {
      botao.addEventListener("click", async () => {
        await fetch(`/api/biblioteca/audios/${encodeURIComponent(botao.dataset.nome)}`, { method: "DELETE" });
        carregarBase();
      });
    });

    const gradeImagens = document.getElementById("base-imagens-grade");
    gradeImagens.innerHTML = dados.imagens?.length
      ? dados.imagens
          .map(
            (img) => `
        <div class="thumb-img-opcao" title="${img.nome}" style="position:relative">
          <img src="${img.url}" alt="">
          <button type="button" class="btn-remover-imagem-base" data-nome="${img.nome}" title="Remover" style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,0.6);color:#fff;border:none;border-radius:5px;width:20px;height:20px;cursor:pointer;line-height:1">×</button>
        </div>`
          )
          .join("")
      : '<div class="empty">Nenhuma imagem importada ainda.</div>';

    gradeImagens.querySelectorAll(".btn-remover-imagem-base").forEach((botao) => {
      botao.addEventListener("click", async (evento) => {
        evento.stopPropagation();
        await fetch(`/api/biblioteca/imagens/${encodeURIComponent(botao.dataset.nome)}`, { method: "DELETE" });
        carregarBase();
      });
    });
  } catch {
    document.getElementById("base-audios-lista").innerHTML = '<div class="empty">Deu erro carregando a biblioteca.</div>';
  }
}

document.getElementById("input-upload-audio-base").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (!arquivo) return;
  const status = document.getElementById("base-audio-status");
  status.textContent = "Enviando…";
  const dados = new FormData();
  dados.set("arquivo", arquivo);
  try {
    const resultado = await fetch("/api/biblioteca/audios/upload", { method: "POST", body: dados }).then((r) => r.json());
    status.textContent = resultado.erro ? `Deu erro: ${resultado.erro}` : "Importado!";
    carregarBase();
  } catch {
    status.textContent = "Deu erro de conexão.";
  } finally {
    evento.target.value = "";
  }
});

document.getElementById("input-upload-imagem-base").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (!arquivo) return;
  const status = document.getElementById("base-imagem-status");
  status.textContent = "Enviando…";
  const dados = new FormData();
  dados.set("arquivo", arquivo);
  try {
    const resultado = await fetch("/api/biblioteca/imagens/upload", { method: "POST", body: dados }).then((r) => r.json());
    status.textContent = resultado.erro ? `Deu erro: ${resultado.erro}` : "Importada!";
    carregarBase();
  } catch {
    status.textContent = "Deu erro de conexão.";
  } finally {
    evento.target.value = "";
  }
});

atualizarStatusYoutube();
carregarPainel();
