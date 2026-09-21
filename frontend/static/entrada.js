// Pasta de entrada da Base: mostra o caminho, importa na hora e atualiza a lista quando algo entra sozinho.

async function atualizarEntrada() {
  const r = await fetch("/api/base/entrada").then((x) => x.json()).catch(() => null);
  if (!r) return;
  document.getElementById("entrada-caminho").textContent = r.pasta;
  document.getElementById("entrada-status").textContent = r.pendentes ? `${r.pendentes} arquivo(s) aguardando importação…` : "";
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
document.getElementById("btn-entrada-abrir").addEventListener("click", async () => {
  const r = await fetch("/api/base/abrir-entrada", { method: "POST" }).then((x) => x.json()).catch(() => ({}));
  if (r.erro) document.getElementById("entrada-status").textContent = `Não consegui abrir: ${r.erro}`;
});
document.getElementById("btn-entrada-copiar").addEventListener("click", async () => {
  const caminho = document.getElementById("entrada-caminho").textContent;
  try { await navigator.clipboard.writeText(caminho); document.getElementById("entrada-status").textContent = "Caminho copiado."; }
  catch { prompt("Copie o caminho:", caminho); }
});

document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.tab === "base") { atualizarEntrada(); importarEntradaAgora(true); } }));
setInterval(() => { if (document.getElementById("tab-base").classList.contains("active")) importarEntradaAgora(true); }, 15000);
atualizarEntrada();
