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
      <div class="preview-row">
        <button type="button" class="btn-secondary btn-compacto entrada-abrir">Abrir a pasta</button>
        <button type="button" class="btn-secondary btn-compacto entrada-copiar">Copiar o caminho</button>
      </div>
    </div>`).join("");
  lista.querySelectorAll(".entrada-canal").forEach((el) => {
    const caminho = el.querySelector("code").textContent;
    el.querySelector(".entrada-abrir").addEventListener("click", async () => {
      const dados = new FormData();
      dados.append("canal_id", el.dataset.canal);
      const res = await fetch("/api/base/abrir-entrada", { method: "POST", body: dados }).then((x) => x.json()).catch(() => ({}));
      if (res.erro) document.getElementById("entrada-status").textContent = `Não consegui abrir: ${res.erro}`;
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
