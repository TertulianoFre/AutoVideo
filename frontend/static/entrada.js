// Pasta de entrada da Base: mostra o caminho, importa na hora e atualiza a lista quando algo entra sozinho.

async function atualizarEntrada() {
  const r = await fetch("/api/base/entrada").then((x) => x.json()).catch(() => null);
  if (!r) return;
  const lista = document.getElementById("entrada-canais");
  lista.innerHTML = r.canais.map((c) => `
    <div class="entrada-canal${c.id === r.ativo ? " ativo" : ""}" data-canal="${escaparAttr(c.id)}">
      <div class="entrada-canal-topo"><b>${escaparAttr(c.nome)}</b>${c.id === r.ativo ? ' <span class="video-meta">(canal ativo)</span>' : ""}
        <span class="video-meta">${c.pendentes ? `${c.pendentes} aguardando…` : ""}</span></div>
      <code class="entrada-caminho">${escaparAttr(c.pasta)}</code>
      <div class="entrada-pastas">
        ${c.pastas.map((p) => `<div class="entrada-pasta" data-pasta="${escaparAttr(p.nome)}">
            <span class="entrada-pasta-nome">📁 ${escaparAttr(p.nome)}</span>
            <span class="video-meta">${p.arquivos} arquivo(s)</span>
            <button type="button" class="btn-secondary btn-compacto entrada-pasta-abrir">Abrir</button>
          </div>`).join("") || '<span class="video-meta">Nenhuma pasta de vídeo ainda. Clique em "+ Nova pasta de vídeo".</span>'}
      </div>
      <div class="entrada-pasta entrada-pasta-thumb">
        <span class="entrada-pasta-nome">🖼 ${escaparAttr("Thumbnails")}</span>
        <span class="video-meta">${c.thumbnails.arquivos} imagem(ns) aguardando · as que já entraram ficam na Base como "thumbnail"</span>
        <button type="button" class="btn-secondary btn-compacto entrada-thumb-abrir">Abrir</button>
      </div>
      <div class="preview-row">
        <button type="button" class="btn-secondary btn-compacto entrada-nova">+ Nova pasta de vídeo</button>
        <button type="button" class="btn-secondary btn-compacto entrada-abrir">Abrir a pasta do canal</button>
        <button type="button" class="btn-secondary btn-compacto entrada-copiar">Copiar o caminho</button>
      </div>
    </div>`).join("");
  lista.querySelectorAll(".entrada-canal").forEach((el) => {
    const caminho = el.querySelector("code").textContent;
    const abrir = async (pastaVideo) => {
      const dados = new FormData();
      dados.append("canal_id", el.dataset.canal);
      if (pastaVideo) dados.append("pasta_video", pastaVideo);
      const res = await fetch("/api/base/abrir-entrada", { method: "POST", body: dados }).then((x) => x.json()).catch(() => ({}));
      if (res.erro) document.getElementById("entrada-status").textContent = `Não consegui abrir: ${res.erro}`;
    };
    el.querySelector(".entrada-abrir").addEventListener("click", () => abrir(""));
    el.querySelectorAll(".entrada-pastas .entrada-pasta").forEach((p) => p.querySelector(".entrada-pasta-abrir").addEventListener("click", () => abrir(p.dataset.pasta)));
    el.querySelector(".entrada-thumb-abrir").addEventListener("click", async () => {
      const dados = new FormData();
      dados.append("canal_id", el.dataset.canal);
      dados.append("thumbnails", "true");
      await fetch("/api/base/abrir-entrada", { method: "POST", body: dados }).catch(() => {});
    });
    el.querySelector(".entrada-nova").addEventListener("click", async () => {
      const dados = new FormData();
      dados.append("canal_id", el.dataset.canal);
      const res = await fetch("/api/entrada/pastas-video", { method: "POST", body: dados }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
      document.getElementById("entrada-status").textContent = res.erro ? `Não consegui criar: ${res.erro}` : `Pasta "${res.nome}" criada. Salve nela os arquivos cena 1, cena 2, cena 3…`;
      await atualizarEntrada();
      if (typeof atualizarPastasDeVideoNovo === "function") atualizarPastasDeVideoNovo();
    });
    el.querySelector(".entrada-copiar").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(caminho); document.getElementById("entrada-status").textContent = "Caminho copiado."; }
      catch { prompt("Copie o caminho:", caminho); }
    });
  });
}

async function importarEntradaAgora(silencioso) {
  const status = document.getElementById("entrada-status");
  if (!silencioso) status.textContent = "Importando…";
  const r = await fetch("/api/base/importar-entrada", { method: "POST" }).then((x) => x.json()).catch(() => null);
  if (!r) { if (!silencioso) status.textContent = "Sem conexão."; return; }
  if (r.importados.length || r.erros.length) {
    status.textContent = `${r.importados.length} importado(s)${r.erros.length ? `, ${r.erros.length} com erro (${r.erros[0].erro})` : ""}.`;
    if (typeof carregarBase === "function") carregarBase();
  } else if (!silencioso) {
    status.textContent = "Nada novo na pasta.";
  }
}

document.getElementById("btn-entrada-importar").addEventListener("click", () => importarEntradaAgora(false));
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.tab === "base") { atualizarEntrada(); importarEntradaAgora(true); } }));
setInterval(() => { if (document.getElementById("tab-base").classList.contains("active")) importarEntradaAgora(true); }, 15000);
atualizarEntrada();
