const TITULOS = { painel: "Painel", canais: "Canais", agente: "Agente", novo: "Novo vídeo", fila: "Fila", base: "Base", afiliados: "Afiliados", anotacoes: "Anotações" };

function trocarAba(nome) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${nome}`));
  document.getElementById("page-title").textContent = TITULOS[nome];
  if (nome === "painel") carregarPainel();
  if (nome === "fila") carregarFila();
  if (nome === "canais") carregarCanais();
  if (nome === "base") carregarBase();
  if (nome === "novo") montarSeletorBaseNovoVideo();
  if (nome === "afiliados") carregarAfiliados();
  if (nome === "anotacoes") carregarAnotacoes();
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
  revisar: { rotulo: "aguardando sua confirmação", classe: "status-revisar" },
  pronto: { rotulo: "pronto para enviar", classe: "status-pronto" },
  aguardando: { rotulo: "aguardando data de publicação", classe: "status-aguardando" },
  erro: { rotulo: "erro ao publicar", classe: "status-erro" },
  processando: { rotulo: "processando", classe: "status-processando" },
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
  if (v.status === "processando") {
    const pct = Math.round(v.job_progresso || 0);
    const restante = formatarRestante(v.job_restante_segundos);
    const naFila = (v.job_etapa || "").startsWith("Na fila");
    const miniatura = v.thumbnail ? `<img src="${v.thumbnail}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:6px">` : ICONE_VIDEO;
    return `
      <div class="video-item" data-processando="${v.slug}">
        <div class="video-row">
          <div class="video-thumb">${miniatura}</div>
          <div class="video-info">
            <div class="video-title">${v.titulo}</div>
            <div class="video-meta video-meta-status">
              <span class="status-badge status-processando">${naFila ? "na fila" : "processando"}</span>
              <span class="proc-texto">${v.job_etapa || ""}${naFila ? "" : ` — ${pct}%`}${restante ? ` · faltam ${restante}` : ""}</span>
            </div>
            <div class="mini-barra"><div style="width:${Math.max(2, pct)}%"></div></div>
          </div>
        </div>
      </div>`;
  }

  const rotulos = [];
  if (v.sem_narracao) rotulos.push("sem narração");
  if (v.som_fundo_tipo) rotulos.push(`som: ${v.som_fundo_tipo}`);
  if (v.duracao_segundos) rotulos.push(formatarDuracao(v.duracao_segundos));
  const modoLabel = rotulos.length ? `· ${rotulos.join(", ")}` : "";
  const badgeCanal = v.canal_nome ? `<span class="canal-badge">${v.canal_nome}</span>` : "";
  const thumb = v.thumbnail
    ? `<img src="${v.thumbnail}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:6px">`
    : ICONE_VIDEO;
  const publicado = v.status === "publicado";
  const tituloAttr = (v.titulo || "").replace(/"/g, "&quot;");
  const acoesEdicao = comRegenerar && !publicado
    ? `<div class="menu-wrap">
         <button type="button" class="btn-editar-video btn-abrir-menu" title="Cenas, roteiro, legenda, transição e thumbnail">Editar vídeo ▾</button>
         <div class="menu-suspenso">
           ${v.tem_cenas ? `<button type="button" data-acao="cenas" data-slug="${v.slug}">Cenas e roteiro</button>` : ""}
           ${!v.sem_narracao ? `<button type="button" data-acao="legenda" data-slug="${v.slug}">Legenda e transição</button>` : ""}
           <button type="button" data-acao="thumb" data-slug="${v.slug}">Thumbnail</button>
           ${v.aprovado ? `<button type="button" class="btn-desfazer-confirmacao" data-slug="${v.slug}" data-titulo="${tituloAttr}">Desfazer confirmação de publicação</button>` : ""}
         </div>
       </div>`
    : "";
  const menuRegenerar = comRegenerar
    ? `<div class="menu-wrap">
         <button type="button" class="btn-regenerar btn-abrir-menu" title="Refaz narração, imagens e vídeo (pede confirmação)">Regenerar ▾</button>
         <div class="menu-suspenso menu-direita">
           <button type="button" data-acao="regen-mesmo" data-slug="${v.slug}" data-titulo="${tituloAttr}">Refazer com o mesmo roteiro</button>
           ${!v.sem_narracao ? `<button type="button" data-acao="regen-novo" data-slug="${v.slug}" data-titulo="${tituloAttr}">Escrever roteiro novo e refazer</button>` : ""}
         </div>
       </div>`
    : "";
  const publicacao = statusPublicacao(v);
  const badgeStatus = v.status === "pronto" || v.status === "aguardando" || v.status === "revisar" ? statusBadge(v) : "";
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
          ${v.video_16_9 ? `<a href="${v.video_16_9}" target="_blank">16:9</a>` : ""}
          ${v.video_9_16 ? `<a href="${v.video_9_16}" target="_blank">Shorts</a>` : ""}
          ${acoesEdicao}
          ${comRegenerar && !publicado && !v.aprovado ? `<button type="button" class="btn-confirmar-publicacao" data-slug="${v.slug}" data-titulo="${tituloAttr}" title="Sem confirmar, o vídeo NÃO é publicado">Confirmar publicação</button>` : ""}
          ${menuRegenerar}
          <button type="button" class="btn-excluir-video" data-slug="${v.slug}" data-titulo="${tituloAttr}" title="Cancelar e apagar esse vídeo da fila (não será publicado)">✕</button>
        </div>
      </div>
      ${comRegenerar ? `<div class="thumb-painel" data-slug="${v.slug}" data-texto="${(v.thumbnail_texto || v.titulo).replace(/"/g, "&quot;")}" data-cor="${v.thumbnail_cor || ""}" data-posicao="${v.thumbnail_posicao || "baixo-centro"}" data-tamanho-px="${v.thumbnail_tamanho_px || 80}" data-pos-x="${v.thumbnail_pos_x ?? ""}" data-pos-y="${v.thumbnail_pos_y ?? ""}" data-base="${v.thumbnail_base || ""}" data-efeito="${v.thumbnail_efeito || "nenhum"}" data-short="${v.thumbnail_short ? encodeURIComponent(JSON.stringify(v.thumbnail_short)) : ""}"></div>` : ""}
      ${comRegenerar && v.tem_cenas && !publicado ? `<div class="cenas-painel" data-slug="${v.slug}"></div>` : ""}
      ${comRegenerar && !publicado && !v.sem_narracao ? `<div class="legenda-painel" data-slug="${v.slug}" data-tem-cues="${v.tem_cues}" data-legenda="${encodeURIComponent(JSON.stringify(v.legenda || {}))}" data-transicao="${v.transicao || "fade"}"></div>` : ""}
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
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(largura * dpr);
  canvas.height = Math.round(120 * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
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

  const filtrados = videosFilaCache.filter((v) => {
    if (canal && v.canal_id !== canal) return false;
    if (status && v.status !== status) return false;
    return true;
  });

  const lista = document.getElementById("fila-lista");
  lista.innerHTML = filtrados.length
    ? filtrados.map((v) => linhaDeVideo(v, true)).join("")
    : '<div class="empty">Nenhum vídeo bate com esses filtros.</div>';


}

let filaAutoRefreshTimer = null;

function atualizarProcessandoNoLugar(videos) {
  videos.filter((v) => v.status === "processando").forEach((v) => {
    const item = document.querySelector(`[data-processando="${v.slug}"]`);
    if (!item) return;
    const pct = Math.round(v.job_progresso || 0);
    const restante = formatarRestante(v.job_restante_segundos);
    const naFila = (v.job_etapa || "").startsWith("Na fila");
    item.querySelector(".proc-texto").textContent = `${v.job_etapa || ""}${naFila ? "" : ` — ${pct}%`}${restante ? ` · faltam ${restante}` : ""}`;
    const barra = item.querySelector(".mini-barra > div");
    if (barra) barra.style.width = `${Math.max(2, pct)}%`;
  });
}

async function carregarFila(forcar = false) {
  videosFilaCache = await buscarVideos();

  const seletorCanalFiltro = document.getElementById("filtro-canal");
  const canaisUnicos = [...new Map(videosFilaCache.map((v) => [v.canal_id, v.canal_nome])).entries()];
  const valorAtual = seletorCanalFiltro.value;
  seletorCanalFiltro.innerHTML =
    '<option value="">Todos</option>' + canaisUnicos.map(([id, nome]) => `<option value="${id}">${nome}</option>`).join("");
  seletorCanalFiltro.value = valorAtual;

  // enquanto você edita (painel ou menu aberto) a lista não é redesenhada — só o progresso é atualizado no lugar
  const editando = document.querySelector(".thumb-painel.aberto, .cenas-painel.aberto, .legenda-painel.aberto, .menu-suspenso.aberto");
  if (editando && !forcar && document.querySelector("#fila-lista .video-item")) {
    atualizarProcessandoNoLugar(videosFilaCache);
  } else {
    aplicarFiltrosFila();
  }

  // se tem algo em "processando", atualiza sozinho até terminar — sem isso o
  // progresso só mudaria trocando de aba e voltando
  clearTimeout(filaAutoRefreshTimer);
  if (videosFilaCache.some((v) => v.status === "processando")) {
    filaAutoRefreshTimer = setTimeout(() => {
      if (document.getElementById("tab-fila").classList.contains("active")) carregarFila();
    }, 2500);
  }
}

document.addEventListener("click", async (evento) => {
  const botao = evento.target.closest(".btn-excluir-video");
  if (!botao) return;
  if (!confirm(`Cancelar e apagar "${botao.dataset.titulo}"? O vídeo não será publicado e os arquivos serão excluídos.`)) return;
  const resposta = await fetch(`/api/videos/${encodeURIComponent(botao.dataset.slug)}`, { method: "DELETE" });
  if (!resposta.ok) {
    alert("Não consegui excluir esse vídeo.");
    return;
  }
  carregarFila();
  carregarPainel();
});

["filtro-canal", "filtro-status"].forEach((id) => {
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

function escalaPreview(areaPreview, larguraCanvas = LARGURA_CANVAS_THUMB) {
  const largura = areaPreview.getBoundingClientRect().width;
  return largura ? largura / larguraCanvas : 460 / larguraCanvas;
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
      ${seletorEfeito(painel.dataset.efeito || "nenhum")}
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

  aplicarEfeitoPreview(rotuloArrastavel, painel.dataset.efeito || "nenhum");
  painel.querySelector(".thumb-efeito").addEventListener("change", (ev) => aplicarEfeitoPreview(rotuloArrastavel, ev.target.value));

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
  if (painel.dataset.short) montarEditorShorts(slug, painel);

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
  dados.set("efeito", painel.querySelector(".thumb-efeito").value);
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
    painel.dataset.efeito = painel.querySelector(".thumb-efeito").value;
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

function formatarTempo(segundos) {
  const s = Math.round(segundos || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function cardDeCena(slug, cena) {
  const semImagem = `<div class="cena-img-vazia">${ICONE_VIDEO}</div>`;
  const img16 = cena.imagem ? `<img class="cena-img cena-img-16" src="${cena.imagem}" alt="">` : semImagem;
  const img9 = cena.imagem_vertical ? `<img class="cena-img cena-img-9" src="${cena.imagem_vertical}" alt="">` : "";
  const fim = (cena.inicio_segundos || 0) + (cena.duracao_segundos || 0);
  const origem = cena.video_base
    ? `<div class="video-meta cena-da-base">▶ Vídeo da Base: ${escaparAttr(cena.video_base)}</div>`
    : cena.imagem_base ? `<div class="video-meta cena-da-base">Imagem da Base: ${escaparAttr(cena.imagem_base)}</div>` : "";
  const texto = escaparAttr(cena.texto || "");
  return `
    <div class="cena-card" data-indice="${cena.indice}">
      <div class="cena-card-imagens">${img16}${img9}</div>
      <div class="cena-card-body">
        <div class="cena-card-indice">Cena ${cena.indice + 1}
          <span class="cena-card-tempo">${formatarTempo(cena.inicio_segundos)}–${formatarTempo(fim)} · ${Math.round(cena.duracao_segundos || 0)}s</span>
        </div>
        <p class="cena-card-texto">${texto}</p>
        <div class="cena-edicao" hidden>
          <textarea class="cena-edicao-texto" rows="4" data-original="${texto}">${texto}</textarea>
          <div class="video-meta cena-edicao-info"></div>
        </div>
        <div class="cena-card-acoes">
          <button type="button" class="btn-regenerar btn-regenerar-cena" data-slug="${slug}" data-indice="${cena.indice}">Gerar outra imagem</button>
          <button type="button" class="btn-lapis-desc${cena.descricao_imagem ? " ativo" : ""}" title="${cena.descricao_imagem ? "Descrição da imagem em uso (clique para ver/editar)" : "Descrever a imagem que você quer (opcional)"}">✎</button>
          <label class="btn-regenerar btn-regenerar-sutil btn-enviar-cena" title="Usar uma imagem do seu computador (vale pros dois formatos)">
            Enviar imagem
            <input type="file" class="cena-upload-input" accept="image/*" hidden data-slug="${slug}" data-indice="${cena.indice}">
          </label>
          <button type="button" class="btn-regenerar btn-regenerar-sutil btn-base-cena" data-slug="${slug}" data-indice="${cena.indice}" title="Escolher uma imagem ou vídeo que você importou na aba Base">Usar da Base</button>
        </div>
        <input type="text" class="cena-descricao" hidden maxlength="300" value="${escaparAttr(cena.descricao_imagem || "")}" placeholder="Descreva a imagem (ex.: polvo abrindo um caramujo, close-up) e clique em Gerar outra imagem">
        ${origem}
        <div class="cena-base-grade" hidden></div>
      </div>
      <button type="button" class="btn-lapis" title="Editar o texto desta cena (a narração é refeita ao salvar)">✎</button>
    </div>`;
}

async function alternarPainelCenas(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.cenas-painel[data-slug="${slug}"]`);
  if (!painel) return;

  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder cenas" : "cenas";
  if (abrindo) painel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (!abrindo || painel.dataset.carregado === "true") return;

  painel.innerHTML = '<div class="cenas-status">Carregando cenas…</div>';
  const resposta = await fetch(`/api/videos/${slug}/cenas`);
  const dados = await resposta.json();

  if (dados.erro) {
    painel.innerHTML = `<div class="cenas-status">${dados.erro}</div>`;
    return;
  }

  painel.dataset.carregado = "true";
  const total = dados.cenas.reduce((soma, c) => soma + (c.duracao_segundos || 0), 0);
  painel.innerHTML = `
    <div class="cenas-status">${dados.cenas.length} cenas na ordem em que aparecem no vídeo (${formatarTempo(total)} no total), cada uma com o trecho do roteiro que ela cobre. As trocas de imagem/vídeo valem na hora e várias podem rodar ao mesmo tempo. O lápis (✎) edita o texto: você pode mexer em várias cenas e salvar tudo de uma vez.</div>
    <div class="cenas-grid">${dados.cenas.map((c) => cardDeCena(slug, c)).join("")}</div>
    <div class="cenas-rodape">
      <button type="button" class="btn-primary btn-salvar-textos" hidden>Salvar textos e refazer narração</button>
      <button type="button" class="btn-secondary btn-concluir-cenas">Concluir e fechar</button>
      <span class="video-meta cenas-rodape-status"></span>
    </div>`;

  painel.querySelector(".btn-concluir-cenas").addEventListener("click", () => {
    const status = painel.querySelector(".cenas-rodape-status");
    if (painel.querySelector(".cena-card button:disabled")) {
      status.textContent = "Ainda tem cena sendo gerada — espere terminar.";
      return;
    }
    if (contarEdicoesDeTexto(painel) && !confirm("Tem texto editado que ainda não foi salvo. Fechar mesmo assim (as edições serão descartadas)?")) return;
    // nada a "salvar" nas imagens: cada troca já foi aplicada ao vídeo. Aqui só fecha e atualiza a linha.
    painel.dataset.carregado = "";
    painel.classList.remove("aberto");
    botao.textContent = "cenas";
    carregarFila();
  });
  painel.querySelector(".btn-salvar-textos").addEventListener("click", () => salvarTextosDasCenas(painel, slug));

  painel.querySelectorAll(".btn-regenerar-cena").forEach((b) => {
    b.addEventListener("click", () => regenerarCena(b));
  });
  painel.querySelectorAll(".btn-base-cena").forEach((b) => {
    b.addEventListener("click", () => alternarEscolhaBaseCena(b));
  });
  painel.querySelectorAll(".cena-upload-input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.files[0]) enviarImagemCena(input);
    });
  });
}

function acompanharJobCena(jobId, card, botao, rotuloBotao) {
  const slug = botao.dataset.slug;
  const botoes = card.querySelectorAll("button");
  const corpo = card.querySelector(".cena-card-body");
  const intervalo = setInterval(async () => {
    const r = await fetch(`/api/jobs/${jobId}`);
    const job = await r.json();
    if (typeof job.progresso !== "number") return;
    botao.textContent = textoDeProgresso(job);
    atualizarMiniBarra(corpo, job.progresso);
    if (job.status === "pronto") {
      clearInterval(intervalo);
      botoes.forEach((b) => (b.disabled = false));
      removerMiniBarra(corpo);
      botao.textContent = rotuloBotao;
      const i16 = card.querySelector(".cena-img-16");
      const i9 = card.querySelector(".cena-img-9");
      if (i16) i16.src = job.resultado.cena_imagem;
      if (i9) i9.src = job.resultado.cena_imagem_9x16;
      // atualiza só a miniatura da linha (se essa era a cena 0), sem recarregar
      // a fila — o painel de cenas continua aberto pra corrigir mais de uma
      if (job.resultado.thumbnail) {
        const thumbImg = document.querySelector(`.video-row[data-slug="${slug}"] .video-thumb img`);
        if (thumbImg) thumbImg.src = job.resultado.thumbnail;
      }
    } else if (job.status === "erro") {
      clearInterval(intervalo);
      botoes.forEach((b) => (b.disabled = false));
      removerMiniBarra(corpo);
      botao.textContent = rotuloBotao;
      alert(`Deu erro: ${job.erro}`);
    }
  }, 1200);
}

async function regenerarCena(botao) {
  const card = botao.closest(".cena-card");
  const rotulo = botao.textContent;
  card.querySelectorAll("button").forEach((b) => (b.disabled = true));
  botao.textContent = "Gerando…";

  const corpoCena = new FormData();
  const campoDesc = card.querySelector(".cena-descricao");
  if (campoDesc && !campoDesc.hidden) corpoCena.set("descricao", campoDesc.value); // fechado = usa o que já valia
  const resposta = await fetch(`/api/videos/${botao.dataset.slug}/cenas/${botao.dataset.indice}/regenerar`, { method: "POST", body: corpoCena });
  const { job_id, erro } = await resposta.json();
  if (erro) {
    card.querySelectorAll("button").forEach((b) => (b.disabled = false));
    botao.textContent = rotulo;
    alert(erro);
    return;
  }
  acompanharJobCena(job_id, card, botao, rotulo);
}

async function alternarEscolhaBaseCena(botao) {
  const card = botao.closest(".cena-card");
  const grade = card.querySelector(".cena-base-grade");
  grade.hidden = !grade.hidden;
  if (grade.hidden || grade.dataset.carregado) return;
  grade.dataset.carregado = "true";
  const dados = await fetch("/api/biblioteca").then((r) => r.json());
  const itens = [
    ...(dados.imagens || []).map((i) => ({ ...i, tipo: "imagem" })),
    ...(dados.videos || []).map((v) => ({ ...v, tipo: "video" })),
  ];
  if (!itens.length) {
    grade.innerHTML = '<span class="video-meta">Nada na Base ainda — importe imagens ou vídeos na aba Base.</span>';
    return;
  }
  grade.innerHTML = itens
    .map((it) => {
      const dica = `${it.nome}${it.usado_em.length ? " — já usado em: " + it.usado_em.join(", ") : ""}`;
      const midia = it.tipo === "video" ? `<video src="${it.url}#t=0.5" muted preload="metadata"></video><span class="base-ordem">vídeo</span>` : `<img src="${it.url}" alt="">`;
      return `<button type="button" class="thumb-img-opcao" data-nome="${escaparAttr(it.nome)}" data-tipo="${it.tipo}" title="${escaparAttr(dica)}">${midia}</button>`;
    })
    .join("");
  grade.querySelectorAll(".thumb-img-opcao").forEach((op) => {
    op.addEventListener("click", async () => {
      const item = itens.find((i) => i.nome === op.dataset.nome && i.tipo === op.dataset.tipo);
      if (item.usado_em.length && !confirm(`Isso já foi usado em: ${item.usado_em.join(", ")}. Usar de novo?`)) return;
      const rotulo = card.querySelector(".btn-regenerar-cena").textContent;
      card.querySelectorAll("button").forEach((b) => (b.disabled = true));
      const corpo = new FormData();
      corpo.set("nome", item.nome);
      const rota = item.tipo === "video" ? "video-base" : "imagem-base";
      const resposta = await fetch(`/api/videos/${botao.dataset.slug}/cenas/${botao.dataset.indice}/${rota}`, { method: "POST", body: corpo });
      const { job_id, erro } = await resposta.json();
      if (erro) {
        card.querySelectorAll("button").forEach((b) => (b.disabled = false));
        alert(erro);
        return;
      }
      grade.hidden = true;
      acompanharJobCena(job_id, card, card.querySelector(".btn-regenerar-cena"), rotulo);
    });
  });
}

async function enviarImagemCena(input) {
  const card = input.closest(".cena-card");
  const botao = card.querySelector(".btn-regenerar-cena");
  const rotulo = botao.textContent;
  card.querySelectorAll("button").forEach((b) => (b.disabled = true));
  botao.textContent = "Enviando…";

  const dados = new FormData();
  dados.set("arquivo", input.files[0]);
  input.value = "";
  const resposta = await fetch(`/api/videos/${input.dataset.slug}/cenas/${input.dataset.indice}/imagem`, { method: "POST", body: dados });
  const { job_id, erro } = await resposta.json();
  if (erro) {
    card.querySelectorAll("button").forEach((b) => (b.disabled = false));
    botao.textContent = rotulo;
    alert(erro);
    return;
  }
  acompanharJobCena(job_id, card, botao, rotulo);
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
  if (semNarracao) document.getElementById("secao-som").open = true;
  aplicarEstadoSomFundo();
});

campoSomFundoAtivo.addEventListener("change", aplicarEstadoSomFundo);

campoSomFundoBiblioteca.addEventListener("change", async () => {
  try {
    const dados = await fetch("/api/biblioteca").then((r) => r.json());
    const item = (dados.audios_info || []).find((a) => a.nome === campoSomFundoBiblioteca.value);
    if (item?.usado_em?.length && !confirm(`Esse áudio já foi usado em: ${item.usado_em.join(", ")}. Usar de novo neste vídeo?`)) {
      const outro = (dados.audios_info || []).find((a) => !a.usado_em.length);
      campoSomFundoBiblioteca.value = outro ? outro.nome : "";
    }
  } catch {
    // sem aviso se não deu pra checar
  }
});

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
  const inicioRoteiro = Date.now();
  const barra = document.getElementById("preview-roteiro-barra");
  barra.hidden = false;
  const relogio = setInterval(() => {
    previewRoteiroStatus.textContent = `Escrevendo o roteiro… ${Math.round((Date.now() - inicioRoteiro) / 1000)}s (roteiros longos demoram)`;
  }, 500);
  previewRoteiroStatus.textContent = "Escrevendo o roteiro…";

  const dados = new FormData();
  dados.set("titulo", titulo);
  dados.set("duracao_alvo", campoDuracao.value || "1");
  dados.set("descricao_video", campoDescricaoVideo.value || "");
  const nCenas = document.querySelector("[name=num_cenas]").value;
  if (nCenas) dados.set("num_cenas", nCenas);

  try {
    const resposta = await fetch("/api/roteiro/preview", { method: "POST", body: dados });
    const dadosResposta = await resposta.json();
    if (dadosResposta.erro) {
      previewRoteiroStatus.textContent = `Deu erro: ${dadosResposta.erro}`;
    } else {
      campoRoteiro.value = dadosResposta.roteiro;
      const nPalavras = dadosResposta.roteiro.trim().split(/\s+/).length;
      previewRoteiroStatus.textContent = `Pronto — ${nPalavras} palavras (~${(nPalavras / 150).toFixed(1)} min). Revise e edite antes de gerar o vídeo.`;
      btnPreviewRoteiro.textContent = "Atualizar roteiro";
    }
  } catch {
    previewRoteiroStatus.textContent = "Deu erro de conexão, tenta de novo.";
  } finally {
    clearInterval(relogio);
    barra.hidden = true;
    btnPreviewRoteiro.disabled = false;
  }
});

// ---------------- Novo vídeo: como o roteiro vira cenas (ajuste antes de gerar) ----------------

const PALAVRAS_POR_MINUTO_FRONT = 150;

function atualizarCenasDoRoteiro() {
  const caixa = document.getElementById("roteiro-cenas");
  const nCenas = parseInt(document.querySelector("[name=num_cenas]").value, 10);
  const paragrafos = campoRoteiro.value.split("\n").map((p) => p.trim()).filter(Boolean);
  if (!paragrafos.length) {
    caixa.hidden = true;
    return;
  }
  caixa.hidden = false;
  const meta = parseFloat(campoDuracao.value) || 0;
  const total = `<div class="roteiro-cenas-ok"><b>Narração total: ${formatarNarracao(paragrafos.join(" "))}</b>${meta && !campoSemNarracao.checked ? ` (meta do campo Duração: ${meta} min)` : ""}</div>`;
  let aviso = "";
  if (nCenas >= 2) {
    aviso = paragrafos.length === nCenas
      ? `<div class="roteiro-cenas-ok">Cada parágrafo vira uma cena. Edite o texto acima à vontade: os tempos abaixo se atualizam.</div>`
      : `<div class="roteiro-cenas-aviso">O roteiro tem ${paragrafos.length} parágrafo(s) e você pediu ${nCenas} cenas — pra cada parágrafo virar uma cena, separe o texto em exatamente ${nCenas} parágrafos (uma linha em branco entre eles). Do jeito que está, as cenas serão divididas por tempo.</div>`;
  }
  const rotulo = nCenas >= 2 ? "Cena" : "Parágrafo";
  caixa.innerHTML = total + aviso + paragrafos.map((p, i) => `<div class="roteiro-cena"><b>${rotulo} ${i + 1}</b> <span class="video-meta">${formatarNarracao(p)}</span><div>${p.replace(/</g, "&lt;")}</div></div>`).join("");
}

campoRoteiro.addEventListener("input", atualizarCenasDoRoteiro);
document.querySelector("[name=num_cenas]").addEventListener("input", atualizarCenasDoRoteiro);
btnPreviewRoteiro.addEventListener("click", () => setTimeout(function esperar() {
  if (btnPreviewRoteiro.disabled) return setTimeout(esperar, 500);
  atualizarCenasDoRoteiro();
}, 500));

// ---------------- Novo vídeo: narração gravada por você ----------------

let narracaoGravadaBlob = null;
let mediaRecorderAtual = null;
let mediaRecorderChunks = [];
let gravacaoInicioEm = null;
let gravacaoTimer = null;

const btnGravarNarracao = document.getElementById("btn-gravar-narracao");
const inputUploadNarracao = document.getElementById("input-upload-narracao");
const narracaoGravadaStatus = document.getElementById("narracao-gravada-status");
const narracaoGravadaResultado = document.getElementById("narracao-gravada-resultado");
const narracaoGravadaPlayer = document.getElementById("narracao-gravada-player");
const narracaoGravadaDuracao = document.getElementById("narracao-gravada-duracao");
const btnRemoverNarracaoGravada = document.getElementById("btn-remover-narracao-gravada");

function formatarMmSs(segundos) {
  const s = Math.round(segundos || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function definirNarracaoGravada(blob, duracaoSegundosConhecida) {
  narracaoGravadaBlob = blob;
  document.getElementById("linha-voz-idioma").hidden = true;  // com áudio próprio, voz/idioma da IA não servem
  narracaoGravadaPlayer.src = URL.createObjectURL(blob);
  narracaoGravadaResultado.hidden = false;

  if (duracaoSegundosConhecida) {
    narracaoGravadaDuracao.textContent = `Duração: ${formatarMmSs(duracaoSegundosConhecida)}`;
  } else {
    // arquivo enviado — lê a duração real do próprio arquivo (o navegador
    // decodifica os metadados; se não conseguir, só não mostra o tempo)
    narracaoGravadaDuracao.textContent = "";
    const sondaAudio = new Audio();
    sondaAudio.addEventListener("loadedmetadata", () => {
      if (isFinite(sondaAudio.duration)) {
        narracaoGravadaDuracao.textContent = `Duração: ${formatarMmSs(sondaAudio.duration)}`;
      }
    });
    sondaAudio.src = narracaoGravadaPlayer.src;
  }
}

btnRemoverNarracaoGravada.addEventListener("click", () => {
  narracaoGravadaBlob = null;
  document.getElementById("linha-voz-idioma").hidden = false;
  narracaoGravadaResultado.hidden = true;
  narracaoGravadaPlayer.removeAttribute("src");
  narracaoGravadaDuracao.textContent = "";
  narracaoGravadaStatus.textContent = "";
  inputUploadNarracao.value = "";
});

inputUploadNarracao.addEventListener("change", () => {
  const arquivo = inputUploadNarracao.files[0];
  if (!arquivo) return;
  definirNarracaoGravada(arquivo);
  narracaoGravadaStatus.textContent = arquivo.name;
});

btnGravarNarracao.addEventListener("click", async () => {
  if (mediaRecorderAtual && mediaRecorderAtual.state === "recording") {
    mediaRecorderAtual.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    narracaoGravadaStatus.textContent = "Esse navegador não suporta gravação — envie um arquivo de áudio.";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorderChunks = [];
    mediaRecorderAtual = new MediaRecorder(stream);
    mediaRecorderAtual.addEventListener("dataavailable", (evento) => {
      if (evento.data.size > 0) mediaRecorderChunks.push(evento.data);
    });
    mediaRecorderAtual.addEventListener("stop", () => {
      clearInterval(gravacaoTimer);
      const duracaoSegundos = (Date.now() - gravacaoInicioEm) / 1000;
      definirNarracaoGravada(new Blob(mediaRecorderChunks, { type: "audio/webm" }), duracaoSegundos);
      narracaoGravadaStatus.textContent = "Gravação pronta.";
      btnGravarNarracao.textContent = "🎤 Gravar";
      stream.getTracks().forEach((faixa) => faixa.stop());
    });
    mediaRecorderAtual.start();
    gravacaoInicioEm = Date.now();
    btnGravarNarracao.textContent = "⏹ Parar gravação";
    narracaoGravadaStatus.textContent = "Gravando… 0:00";
    gravacaoTimer = setInterval(() => {
      narracaoGravadaStatus.textContent = `Gravando… ${formatarMmSs((Date.now() - gravacaoInicioEm) / 1000)}`;
    }, 1000);
  } catch {
    narracaoGravadaStatus.textContent = "Não consegui acessar o microfone — confira a permissão do navegador.";
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

document.getElementById("btn-limpar-novo").addEventListener("click", () => {
  form.reset();
  if (narracaoGravadaBlob) btnRemoverNarracaoGravada.click();
  selecionadasBase = [];
  document.getElementById("campo-imagens-base").value = "";
  montarSeletorBaseNovoVideo();
  // form.reset() volta os valores, mas não desfaz o que o JS esconde/desabilita
  [campoSemNarracao, campoSomFundoAtivo, campoSomFundoTipo].forEach((campo) => campo.dispatchEvent(new Event("change")));
  campoDuracao.value = 1;
  previewRoteiroStatus.textContent = "";
  btnPreviewRoteiro.textContent = "Pré-visualizar roteiro";
  atualizarCenasDoRoteiro();
  resultadoCard.hidden = true;
  erroCard.hidden = true;
  window.scrollTo(0, 0);
});

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
  if (narracaoGravadaBlob) {
    dados.set("narracao_audio", narracaoGravadaBlob, narracaoGravadaBlob.name || "narracao.webm");
  }
  let resposta = await fetch("/api/videos", { method: "POST", body: dados });
  let resultado = await resposta.json();
  if (resultado.duplicado && confirm(resultado.erro)) {
    dados.set("confirmar_duplicado", "true");
    resposta = await fetch("/api/videos", { method: "POST", body: dados });
    resultado = await resposta.json();
  }

  if (resultado.erro) {
    progressoCard.hidden = true;
    erroCard.hidden = false;
    document.getElementById("erro-conteudo").textContent = resultado.erro;
    form.querySelector(".btn-primary").disabled = false;
    return;
  }

  if (poller) clearInterval(poller);
  poller = setInterval(() => acompanharJob(resultado.job_id), 1200);

  // o pedido já está com o servidor: libera o formulário pra montar o próximo vídeo enquanto este é gerado
  form.querySelector(".btn-primary").disabled = false;
  if (narracaoGravadaBlob) btnRemoverNarracaoGravada.click();  // a gravação já foi enviada com este pedido
  document.getElementById("aviso-fila-novo").hidden = false;
});

let falhasJob = 0;

function abandonarJob(mensagem) {
  clearInterval(poller);
  form.querySelector(".btn-primary").disabled = false;
  progressoCard.hidden = true;
  erroCard.hidden = false;
  document.getElementById("erro-conteudo").textContent = mensagem;
}

async function acompanharJob(jobId) {
  let job;
  try {
    const resposta = await fetch(`/api/jobs/${jobId}`);
    if (resposta.status === 404) {
      // o servidor foi reiniciado (os jobs vivem na memória dele): a geração parou junto
      abandonarJob("O servidor foi reiniciado durante a geração e o vídeo parou no meio. Gere de novo (se ele aparecer na Fila, use Regenerar).");
      return;
    }
    job = await resposta.json();
    falhasJob = 0;
  } catch {
    // falha de rede passageira: tenta de novo, só desiste depois de várias seguidas
    if (++falhasJob >= 8) abandonarJob("Perdi a conexão com o servidor. Confira se o app está rodando e olhe a Fila.");
    return;
  }
  if (typeof job.progresso !== "number") return;

  progressFill.style.width = `${job.progresso}%`;
  progressoPct.textContent = `${Math.round(job.progresso)}%`;
  progressoEtapa.textContent = job.etapa;
  const restanteNovo = formatarRestante(job.restante_segundos);
  document.getElementById("progresso-restante").textContent = restanteNovo ? `Faltam ${restanteNovo} (estimativa)` : "";

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
    ${resultado.video_16_9 ? `<div class="resultado-formato">
      <h3>16:9 — vídeo normal (${formatarDuracao(resultado.duracao_segundos)})</h3>
      <video controls src="${resultado.video_16_9}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_16_9}" download>Baixar .mp4</a>
      </div>
    </div>` : ""}
    ${resultado.video_9_16 ? `<div class="resultado-formato">
      <h3>9:16 — Shorts (${formatarDuracao(resultado.duracao_segundos)})</h3>
      <video controls src="${resultado.video_9_16}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_9_16}" download>Baixar .mp4</a>
      </div>
    </div>` : ""}
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

function desenharLinha(canvasId, dias, valores, formato) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const L = canvas.clientWidth || 300;
  const A = 110;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(L * dpr);
  canvas.height = Math.round(A * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, L, A);

  const estilo = getComputedStyle(document.documentElement);
  const cor = estilo.getPropertyValue("--accent").trim() || "#E2793D";
  const dim = estilo.getPropertyValue("--text-dim").trim() || "#A79E8E";
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const faixa = max - min || 1;
  const mx = 42, topo = 12, base = A - 24;
  const x = (i) => mx + (i / (valores.length - 1)) * (L - mx - 8);
  const y = (v) => base - ((v - min) / faixa) * (base - topo);

  ctx.font = "10px sans-serif";
  ctx.fillStyle = dim;
  ctx.textAlign = "right";
  ctx.fillText(formato(max), mx - 6, topo + 4);
  ctx.fillText(formato(min), mx - 6, base + 3);
  [0, Math.floor(valores.length / 2), valores.length - 1].forEach((i) => {
    const [, m, d] = dias[i].split("-");
    ctx.textAlign = i === 0 ? "left" : i === valores.length - 1 ? "right" : "center";
    ctx.fillText(`${d}/${m}`, x(i), A - 8);
  });

  ctx.strokeStyle = cor;
  ctx.lineWidth = 2;
  ctx.beginPath();
  valores.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.stroke();
  ctx.lineTo(x(valores.length - 1), base);
  ctx.lineTo(x(0), base);
  ctx.closePath();
  ctx.globalAlpha = 0.12;
  ctx.fillStyle = cor;
  ctx.fill();
  ctx.globalAlpha = 1;
}

async function carregarGraficosYoutube() {
  const card = document.getElementById("card-graficos-youtube");
  const aviso = document.getElementById("graficos-youtube-aviso");
  let dados;
  try {
    dados = await fetch("/api/youtube/serie?dias=28").then((r) => r.json());
  } catch {
    return;
  }
  card.hidden = false;

  if (dados.erro) {
    aviso.textContent =
      "Não consegui carregar os gráficos: ative a \"YouTube Analytics API\" no Google Cloud Console (mesmo projeto) e clique em Reconectar no perfil, pra liberar a permissão nova.";
    return;
  }
  aviso.textContent = "";
  const dias = dados.serie.map((s) => s.dia);
  desenharLinha("grafico-views", dias, dados.serie.map((s) => s.views), (v) => v.toLocaleString("pt-BR"));

  // total de inscritos ao longo do tempo: parte do número atual e volta somando os líquidos de trás pra frente
  let total = dados.inscritos_atual;
  const acumulado = new Array(dados.serie.length);
  for (let i = dados.serie.length - 1; i >= 0; i--) {
    acumulado[i] = total;
    total -= dados.serie[i].inscritos_liquidos;
  }
  desenharLinha("grafico-inscritos", dias, acumulado, (v) => Math.round(v).toLocaleString("pt-BR"));
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
  carregarGraficosYoutube();

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
    if (resultado.acao === "reagendar" || resultado.acao === "cancelar" || resultado.acao === "editar") {
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

// ---------------- Afiliados (lista manual, ideia guardada) ----------------

const ROTULO_PLATAFORMA = { tiktok_shop: "TikTok Shop", shopee: "Shopee", outro: "Outra" };

async function carregarAfiliados() {
  const lista = document.getElementById("afiliados-lista");
  try {
    const itens = await fetch("/api/afiliados").then((r) => r.json());
    lista.innerHTML = itens.length
      ? itens
          .map(
            (item) => `
        <div class="video-item">
          <div class="video-row">
            <div class="video-info">
              <div class="video-title" style="text-transform:none">${item.nome} <span class="canal-badge">${ROTULO_PLATAFORMA[item.plataforma] || item.plataforma}</span></div>
              <div class="video-meta">${item.link ? `<a href="${item.link}" target="_blank" rel="noopener">${item.link}</a>` : "sem link ainda"}${item.nota ? ` · ${item.nota}` : ""}</div>
            </div>
            <div class="video-links">
              <button type="button" class="btn-regenerar btn-regenerar-sutil btn-remover-afiliado" data-id="${item.id}">remover</button>
            </div>
          </div>
        </div>`
          )
          .join("")
      : '<div class="empty">Nenhum produto anotado ainda.</div>';

    lista.querySelectorAll(".btn-remover-afiliado").forEach((botao) => {
      botao.addEventListener("click", async () => {
        await fetch(`/api/afiliados/${botao.dataset.id}`, { method: "DELETE" });
        carregarAfiliados();
      });
    });
  } catch {
    lista.innerHTML = '<div class="empty">Deu erro carregando a lista.</div>';
  }
}

document.getElementById("form-novo-afiliado").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const form = evento.target;
  const dados = new FormData(form);
  await fetch("/api/afiliados", { method: "POST", body: dados });
  form.reset();
  carregarAfiliados();
});

atualizarStatusYoutube();
carregarPainel();
