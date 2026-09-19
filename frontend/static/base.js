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

    carregarCenasPadrao(dadosBase);
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

// ---- Novo vídeo: escolher imagens e vídeos da Base pras cenas (a ordem do clique é a ordem das cenas) ----
let selecionadasBase = []; // "imagem:nome" | "video:nome"

async function montarSeletorBaseNovoVideo() {
  const grade = document.getElementById("novo-base-grade");
  if (!grade) return;
  const dados = await fetch("/api/biblioteca").then((r) => r.json());
  const itens = [
    ...(dados.imagens || []).map((i) => ({ ...i, tipo: "imagem" })),
    ...(dados.videos || []).map((v) => ({ ...v, tipo: "video" })),
  ];
  selecionadasBase = selecionadasBase.filter((e) => itens.some((i) => `${i.tipo}:${i.nome}` === e));
  const campo = document.getElementById("campo-imagens-base");

  const desenhar = () => {
    campo.value = selecionadasBase.join("|");
    grade.innerHTML = itens.length
      ? itens.map((it) => {
          const chave = `${it.tipo}:${it.nome}`;
          const ordem = selecionadasBase.indexOf(chave);
          const dica = `${it.nome}${it.descricao ? " — " + it.descricao : ""}${it.usado_em.length ? " — já usado em: " + it.usado_em.join(", ") : ""}`;
          const midia = it.tipo === "video" ? `<video src="${it.url}#t=0.5" muted preload="metadata"></video>` : `<img src="${it.url}" alt="">`;
          return `<div class="base-opcao"><button type="button" class="thumb-img-opcao${ordem >= 0 ? " selecionada" : ""}" data-chave="${escaparAttr(chave)}" title="${escaparAttr(dica)}">${midia}${it.tipo === "video" ? '<span class="base-tipo">vídeo</span>' : ""}${ordem >= 0 ? `<span class="base-ordem">cena ${ordem + 1}</span>` : ""}</button><span class="base-legenda" title="${escaparAttr(it.descricao || it.nome)}">${escaparAttr(it.descricao || it.nome)}</span></div>`;
        }).join("")
      : '<span class="video-meta">Nada na Base ainda — importe imagens ou vídeos na aba Base.</span>';
    grade.querySelectorAll(".thumb-img-opcao").forEach((op) => {
      op.addEventListener("click", () => {
        const chave = op.dataset.chave;
        if (selecionadasBase.includes(chave)) {
          selecionadasBase = selecionadasBase.filter((e) => e !== chave);
        } else {
          const usos = itens.find((i) => `${i.tipo}:${i.nome}` === chave)?.usado_em || [];
          if (usos.length && !confirm(`Isso já foi usado em: ${usos.join(", ")}. Usar de novo?`)) return;
          selecionadasBase.push(chave);
        }
        desenhar();
        if (typeof window.aoMudarMidiasBase === "function") window.aoMudarMidiasBase();
      });
    });
  };
  desenhar();
  if (typeof window.aoMudarMidiasBase === "function") window.aoMudarMidiasBase();
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


// ---------------- cenas padrão (narração + mídia da Base, prontas pra encaixar num vídeo) ----------------

function opcoesMidiaBase(dados, tipoAtual, nomeAtual) {
  const imagens = (dados.imagens || []).map((i) => `<option value="imagem|${escaparAttr(i.nome)}"${tipoAtual === "imagem" && nomeAtual === i.nome ? " selected" : ""}>Imagem: ${escaparAttr(i.descricao || i.nome)}</option>`);
  const videos = (dados.videos || []).map((v) => `<option value="video|${escaparAttr(v.nome)}"${tipoAtual === "video" && nomeAtual === v.nome ? " selected" : ""}>Vídeo: ${escaparAttr(v.descricao || v.nome)}</option>`);
  return `<option value="|">Sem imagem (é feita a partir do texto)</option>${imagens.join("")}${videos.join("")}`;
}

async function salvarCenaPadrao(campos) {
  const corpo = new FormData();
  Object.entries(campos).forEach(([k, v]) => corpo.set(k, v));
  const r = await fetch("/api/cenas-padrao", { method: "POST", body: corpo }).then((x) => x.json());
  if (r.erro) alert(r.erro);
  return !r.erro;
}

async function carregarCenasPadrao(dados) {
  const lista = document.getElementById("base-cenas-padrao-lista");
  const cenas = (await fetch("/api/cenas-padrao").then((r) => r.json()).catch(() => ({ cenas: [] }))).cenas || [];
  document.getElementById("base-cenas-contagem").textContent = `(${cenas.length})`;
  lista.innerHTML = cenas.length ? cenas.map((c) => {
    const miniatura = c.midia_tipo === "imagem" ? `<img src="/biblioteca/imagens/${encodeURIComponent(c.midia_nome)}" alt="">` : c.midia_tipo === "video" ? "🎬" : "🎞";
    return `
      <details class="base-linha" data-cena-padrao="${c.id}">
        <summary>
          <span class="base-linha-mini">${miniatura}</span>
          <span class="base-linha-textos"><span class="base-linha-titulo">${escaparAttr(c.nome)}</span><span class="base-linha-arquivo">${escaparAttr(c.texto)}</span></span>
          <span class="base-selo">${c.midia_tipo === "video" ? "com vídeo" : c.midia_tipo === "imagem" ? "com imagem" : "sem mídia"}</span>
        </summary>
        <div class="base-linha-corpo">
          <label style="width:100%"><span class="video-meta">Nome</span><input type="text" class="base-descricao cp-nome" value="${escaparAttr(c.nome)}" maxlength="80"></label>
          <label style="width:100%"><span class="video-meta">Texto que a IA narra</span><textarea class="base-descricao cp-texto" rows="3" maxlength="600">${escaparAttr(c.texto)}</textarea></label>
          <label style="width:100%"><span class="video-meta">Imagem ou vídeo da Base</span><select class="base-canal cp-midia">${opcoesMidiaBase(dados, c.midia_tipo, c.midia_nome)}</select></label>
          <div class="cena-card-acoes">
            <button type="button" class="btn-secondary cp-salvar" data-id="${c.id}">Salvar</button>
            <button type="button" class="btn-regenerar btn-regenerar-sutil cp-remover" data-id="${c.id}" data-nome="${escaparAttr(c.nome)}">remover cena padrão</button>
          </div>
        </div>
      </details>`;
  }).join("") : '<div class="empty">Nenhuma cena padrão ainda.</div>';

  lista.querySelectorAll(".cp-salvar").forEach((b) => b.addEventListener("click", async () => {
    const linha = b.closest("[data-cena-padrao]");
    const [tipo, nome] = linha.querySelector(".cp-midia").value.split("|");
    if (await salvarCenaPadrao({ id: b.dataset.id, nome: linha.querySelector(".cp-nome").value, texto: linha.querySelector(".cp-texto").value, midia_tipo: tipo, midia_nome: nome })) carregarBase();
  }));
  lista.querySelectorAll(".cp-remover").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(`Remover a cena padrão "${b.dataset.nome}"? (Os vídeos que já usam ela não mudam.)`)) return;
    await fetch(`/api/cenas-padrao/${b.dataset.id}`, { method: "DELETE" });
    carregarBase();
  }));

  const form = document.getElementById("form-cena-padrao");
  document.getElementById("btn-nova-cena-padrao").onclick = () => {
    form.hidden = !form.hidden;
    if (form.hidden) return;
    form.innerHTML = `
      <label style="width:100%"><span class="video-meta">Nome (só pra você achar)</span><input type="text" class="base-descricao" id="ncp-nome" maxlength="80" placeholder="Ex.: Inscreva-se e curta"></label>
      <label style="width:100%"><span class="video-meta">Texto que a IA narra</span><textarea class="base-descricao" id="ncp-texto" rows="3" maxlength="600" placeholder="Ex.: Gostou do vídeo? Então se inscreva no canal e deixe o seu like!"></textarea></label>
      <label style="width:100%"><span class="video-meta">Imagem ou vídeo da Base (opcional)</span><select class="base-canal" id="ncp-midia">${opcoesMidiaBase(dados, "", "")}</select></label>
      <div class="cena-card-acoes"><button type="button" class="btn-primary" id="ncp-salvar">Criar cena padrão</button></div>`;
    document.getElementById("ncp-salvar").onclick = async () => {
      const [tipo, nome] = document.getElementById("ncp-midia").value.split("|");
      if (await salvarCenaPadrao({ nome: document.getElementById("ncp-nome").value, texto: document.getElementById("ncp-texto").value, midia_tipo: tipo, midia_nome: nome })) {
        form.hidden = true;
        carregarBase();
      }
    };
  };
}
