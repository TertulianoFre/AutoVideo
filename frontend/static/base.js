// Aba Base: áudios e imagens importados, com descrição, canal e "usado em quais vídeos".
let dadosBase = null;

function escaparAttr(texto) {
  return String(texto || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function opcoesCanais(canais, atual) {
  return `<option value="">Todos os canais</option>${(canais || []).map((c) => `<option value="${c.id}"${c.id === atual ? " selected" : ""}>${escaparAttr(c.nome)}</option>`).join("")}`;
}

function blocoInfoBase(tipo, item, canais) {
  const usos = item.usado_em?.length
    ? `<span class="base-usado">Usado em: ${item.usado_em.map(escaparAttr).join(", ")}</span>`
    : '<span class="base-nao-usado">Ainda não usado em nenhum vídeo</span>';
  return `
    <input type="text" class="base-descricao" data-tipo="${tipo}" data-nome="${escaparAttr(item.nome)}" value="${escaparAttr(item.descricao)}" maxlength="300" placeholder="Descrição (ex: chuva forte, bom pra vídeos de relaxar)">
    <select class="base-canal" data-tipo="${tipo}" data-nome="${escaparAttr(item.nome)}" title="Canal">${opcoesCanais(canais, item.canal_id)}</select>
    ${usos}`;
}

function linhaBase(tipo, item, canais, miniatura, preview) {
  const usos = item.usado_em?.length ? `<span class="base-selo base-selo-usado">em ${item.usado_em.length} vídeo${item.usado_em.length > 1 ? "s" : ""}</span>` : '<span class="base-selo">livre</span>';
  const titulo = item.descricao || item.nome;
  const rotuloBotao = { audios: "áudio", imagens: "imagem", videos: "vídeo" }[tipo];
  return `
    <details class="base-linha" data-item-base>
      <summary>
        <span class="base-linha-mini">${miniatura}</span>
        <span class="base-linha-textos">
          <span class="base-linha-titulo">${escaparAttr(titulo)}</span>
          ${item.descricao ? `<span class="base-linha-arquivo">${escaparAttr(item.nome)}</span>` : ""}
        </span>
        ${usos}
      </summary>
      <div class="base-linha-corpo">
        ${preview}
        <span class="video-meta">Arquivo: ${escaparAttr(item.nome)}</span>
        ${blocoInfoBase(tipo, item, canais)}
        <button type="button" class="btn-regenerar btn-regenerar-sutil btn-remover-${{ audios: "audio", imagens: "imagem", videos: "video" }[tipo]}-base" data-nome="${escaparAttr(item.nome)}">remover ${rotuloBotao}</button>
      </div>
    </details>`;
}

async function salvarInfoBase(elemento) {
  const bloco = elemento.closest("[data-item-base]");
  const dados = new FormData();
  dados.set("descricao", bloco.querySelector(".base-descricao").value);
  dados.set("canal_id", bloco.querySelector(".base-canal").value);
  await fetch(`/api/biblioteca/${elemento.dataset.tipo}/${encodeURIComponent(elemento.dataset.nome)}/info`, { method: "PUT", body: dados });
  const titulo = bloco.querySelector(".base-linha-titulo");
  if (titulo) titulo.textContent = bloco.querySelector(".base-descricao").value.trim() || elemento.dataset.nome; // o título da linha acompanha a descrição
}

async function carregarBase() {
  try {
    dadosBase = await fetch("/api/biblioteca").then((r) => r.json());
    const filtro = document.getElementById("base-filtro-canal");
    const filtroAtual = filtro.value;
    filtro.innerHTML = opcoesCanais(dadosBase.canais, filtroAtual).replace("Todos os canais", "Todos os canais (mostrar tudo)");
    filtro.value = filtroAtual;
    const passa = (item) => !filtro.value || !item.canal_id || item.canal_id === filtro.value;
    const canais = dadosBase.canais;

    const audios = (dadosBase.audios_info || []).filter(passa);
    document.getElementById("base-audios-contagem").textContent = `(${audios.length})`;
    document.getElementById("base-audios-lista").innerHTML = audios.length
      ? audios.map((a) => linhaBase("audios", a, canais, "🎵", `<audio controls preload="none" src="${a.url}" class="base-preview-audio"></audio>`)).join("")
      : '<div class="empty">Nenhum áudio importado ainda.</div>';

    const imagens = (dadosBase.imagens || []).filter(passa);
    document.getElementById("base-imagens-contagem").textContent = `(${imagens.length})`;
    document.getElementById("base-imagens-grade").innerHTML = imagens.length
      ? imagens.map((img) => linhaBase("imagens", img, canais, `<img src="${img.url}" alt="">`, `<img src="${img.url}" alt="" class="base-preview-imagem">`)).join("")
      : '<div class="empty">Nenhuma imagem importada ainda.</div>';

    const videos = (dadosBase.videos || []).filter(passa);
    document.getElementById("base-videos-contagem").textContent = `(${videos.length})`;
    document.getElementById("base-videos-lista").innerHTML = videos.length
      ? videos.map((vid) => linhaBase("videos", vid, canais, "🎬", `<video src="${vid.url}" controls preload="metadata" class="base-item-video"></video>`)).join("")
      : '<div class="empty">Nenhum vídeo importado ainda.</div>';

    document.querySelectorAll(".base-descricao").forEach((c) => c.addEventListener("change", () => salvarInfoBase(c)));
    document.querySelectorAll(".base-canal").forEach((c) => c.addEventListener("change", () => salvarInfoBase(c)));
    document.querySelectorAll(".btn-remover-audio-base, .btn-remover-imagem-base, .btn-remover-video-base").forEach((botao) => {
      botao.addEventListener("click", async () => {
        const tipo = botao.classList.contains("btn-remover-audio-base") ? "audios" : botao.classList.contains("btn-remover-video-base") ? "videos" : "imagens";
        const lista = tipo === "audios" ? dadosBase.audios_info : tipo === "videos" ? dadosBase.videos : dadosBase.imagens;
        const usos = (lista.find((i) => i.nome === botao.dataset.nome) || {}).usado_em || [];
        if (usos.length && !confirm(`Esse item está em uso em: ${usos.join(", ")}. Remover mesmo assim?`)) return;
        await fetch(`/api/biblioteca/${tipo}/${encodeURIComponent(botao.dataset.nome)}`, { method: "DELETE" });
        carregarBase();
      });
    });
  } catch {
    document.getElementById("base-audios-lista").innerHTML = '<div class="empty">Deu erro carregando a biblioteca.</div>';
  }
}

document.getElementById("base-filtro-canal").addEventListener("change", carregarBase);

// ---- Novo vídeo: escolher imagens da Base pras primeiras cenas (a ordem do clique é a ordem das cenas) ----
let selecionadasBase = [];

async function montarSeletorBaseNovoVideo() {
  const grade = document.getElementById("novo-base-grade");
  if (!grade) return;
  const dados = await fetch("/api/biblioteca").then((r) => r.json());
  const imagens = dados.imagens || [];
  selecionadasBase = selecionadasBase.filter((n) => imagens.some((i) => i.nome === n));
  const campo = document.getElementById("campo-imagens-base");

  const desenhar = () => {
    campo.value = selecionadasBase.join("|");
    grade.innerHTML = imagens.length
      ? imagens.map((img) => {
          const ordem = selecionadasBase.indexOf(img.nome);
          const dica = `${img.nome}${img.descricao ? " — " + img.descricao : ""}${img.usado_em.length ? " — já usada em: " + img.usado_em.join(", ") : ""}`;
          return `<div class="base-opcao"><button type="button" class="thumb-img-opcao${ordem >= 0 ? " selecionada" : ""}" data-nome="${escaparAttr(img.nome)}" title="${escaparAttr(dica)}"><img src="${img.url}" alt="">${ordem >= 0 ? `<span class="base-ordem">cena ${ordem + 1}</span>` : ""}</button><span class="base-legenda" title="${escaparAttr(img.descricao || img.nome)}">${escaparAttr(img.descricao || img.nome)}</span></div>`;
        }).join("")
      : '<span class="video-meta">Nenhuma imagem na Base ainda — importe na aba Base.</span>';
    grade.querySelectorAll(".thumb-img-opcao").forEach((op) => {
      op.addEventListener("click", () => {
        const nome = op.dataset.nome;
        if (selecionadasBase.includes(nome)) {
          selecionadasBase = selecionadasBase.filter((n) => n !== nome);
        } else {
          const usos = imagens.find((i) => i.nome === nome)?.usado_em || [];
          if (usos.length && !confirm(`Essa imagem já foi usada em: ${usos.join(", ")}. Usar de novo?`)) return;
          selecionadasBase.push(nome);
        }
        desenhar();
      });
    });
  };
  desenhar();
}


document.getElementById("input-upload-video-base").addEventListener("change", async (evento) => {
  const arquivo = evento.target.files[0];
  if (!arquivo) return;
  const status = document.getElementById("base-video-status");
  const barra = document.getElementById("base-video-barra");
  const inicio = Date.now();
  barra.hidden = false;
  const relogio = setInterval(() => {
    status.textContent = `Enviando e convertendo… ${Math.round((Date.now() - inicio) / 1000)}s (vídeos grandes levam alguns minutos)`;
  }, 500);
  const dados = new FormData();
  dados.set("arquivo", arquivo);
  try {
    const resultado = await fetch("/api/biblioteca/videos/upload", { method: "POST", body: dados }).then((r) => r.json());
    status.textContent = resultado.erro ? `Deu erro: ${resultado.erro}` : "Importado!";
    carregarBase();
  } catch {
    status.textContent = "Deu erro de conexão.";
  } finally {
    clearInterval(relogio);
    barra.hidden = true;
    evento.target.value = "";
  }
});
