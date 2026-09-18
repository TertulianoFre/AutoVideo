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

async function salvarInfoBase(elemento) {
  const bloco = elemento.closest("[data-item-base]");
  const dados = new FormData();
  dados.set("descricao", bloco.querySelector(".base-descricao").value);
  dados.set("canal_id", bloco.querySelector(".base-canal").value);
  await fetch(`/api/biblioteca/${elemento.dataset.tipo}/${encodeURIComponent(elemento.dataset.nome)}/info`, { method: "PUT", body: dados });
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
    const listaAudios = document.getElementById("base-audios-lista");
    listaAudios.innerHTML = audios.length
      ? audios.map((a) => `
        <div class="base-item" data-item-base>
          <div class="base-item-topo">
            <audio controls src="${a.url}" style="height:32px"></audio>
            <span class="video-meta" style="flex:1">${escaparAttr(a.nome)}</span>
            <button type="button" class="btn-regenerar btn-regenerar-sutil btn-remover-audio-base" data-nome="${escaparAttr(a.nome)}">remover</button>
          </div>
          ${blocoInfoBase("audios", a, canais)}
        </div>`).join("")
      : '<div class="empty">Nenhum áudio importado ainda.</div>';

    const imagens = (dadosBase.imagens || []).filter(passa);
    document.getElementById("base-imagens-contagem").textContent = `(${imagens.length})`;
    const listaImagens = document.getElementById("base-imagens-grade");
    listaImagens.innerHTML = imagens.length
      ? imagens.map((img) => `
        <div class="base-item base-item-imagem" data-item-base>
          <img src="${img.url}" alt="" class="base-item-img">
          <div class="base-item-corpo">
            <div class="base-item-topo"><span class="video-meta" style="flex:1">${escaparAttr(img.nome)}</span>
              <button type="button" class="btn-regenerar btn-regenerar-sutil btn-remover-imagem-base" data-nome="${escaparAttr(img.nome)}">remover</button></div>
            ${blocoInfoBase("imagens", img, canais)}
          </div>
        </div>`).join("")
      : '<div class="empty">Nenhuma imagem importada ainda.</div>';

    document.querySelectorAll(".base-descricao").forEach((c) => c.addEventListener("change", () => salvarInfoBase(c)));
    document.querySelectorAll(".base-canal").forEach((c) => c.addEventListener("change", () => salvarInfoBase(c)));
    document.querySelectorAll(".btn-remover-audio-base, .btn-remover-imagem-base").forEach((botao) => {
      botao.addEventListener("click", async () => {
        const tipo = botao.classList.contains("btn-remover-audio-base") ? "audios" : "imagens";
        const lista = tipo === "audios" ? dadosBase.audios_info : dadosBase.imagens;
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
