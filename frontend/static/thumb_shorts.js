// Efeitos de texto da thumbnail + editor da thumbnail vertical (Shorts).
// Carregado antes de app.js; usa CORES_THUMB e TAMANHO_FONTE_* de lá só em tempo de execução.

const EFEITOS_THUMB = [
  { id: "nenhum", nome: "Sem efeito" },
  { id: "sombra", nome: "Sombra" },
  { id: "neon", nome: "Neon" },
  { id: "explosao", nome: "Explosão" },
  { id: "youtuber", nome: "Estilo YouTuber" },
];

function seletorEfeito(atual) {
  return `<select class="thumb-efeito" title="Efeito atrás do texto">${EFEITOS_THUMB.map((e) => `<option value="${e.id}"${e.id === atual ? " selected" : ""}>${e.nome}</option>`).join("")}</select>`;
}

function aplicarEfeitoPreview(el, efeito) {
  if (!el) return;
  EFEITOS_THUMB.forEach((e) => el.classList.remove(`efx-${e.id}`));
  el.classList.add(`efx-${efeito}`);
}

async function montarEditorShorts(slug, painel) {
  const cfg = JSON.parse(decodeURIComponent(painel.dataset.short));
  const secao = document.createElement("div");
  secao.className = "thumb-shorts";
  const swatches = CORES_THUMB.map(
    (c) => `<button type="button" class="cor-swatch${c.hex === cfg.cor ? " selecionada" : ""}" data-hex="${c.hex}" title="${c.nome}" style="background:${c.hex ? "#" + c.hex : "#F6F2E9"}"></button>`
  ).join("");
  secao.innerHTML = `
    <h4 class="thumb-shorts-titulo">Thumbnail do Short (vertical 9:16)</h4>
    <p class="hint" style="margin:0 0 10px">Fundo gerado automaticamente (sem imagem de IA esticada) e o título em destaque. Arraste o texto pra posicionar. A prévia é aproximada; o resultado final sai ao salvar.</p>
    <div class="thumb-shorts-corpo">
      <div class="thumb-preview thumb-preview-vertical">
        <img class="thumb-preview-img" alt="">
        <div class="thumb-preview-texto"></div>
      </div>
      <div class="thumb-shorts-controles">
        <input type="text" class="short-texto" value="${(cfg.texto || "").replace(/"/g, "&quot;")}" maxlength="80" placeholder="Texto da thumbnail do Short (vazio = sem texto)">
        <div class="cor-swatches">${swatches}</div>
        ${seletorEfeito(cfg.efeito)}
        <select class="short-fundo" title="Fundo">
          <option value="procedural"${cfg.fundo === "procedural" ? " selected" : ""}>Fundo gerado</option>
          <option value="cena"${cfg.fundo === "cena" ? " selected" : ""}>Primeira cena vertical</option>
        </select>
        <div class="thumb-tamanho-linha">
          <span class="video-meta">Tamanho</span>
          <input type="range" class="short-tamanho" min="${TAMANHO_FONTE_MIN}" max="${TAMANHO_FONTE_MAX}" step="2" value="${cfg.tamanho_px}">
          <span class="video-meta short-tamanho-valor">${cfg.tamanho_px}px</span>
        </div>
        <div class="thumb-shorts-botoes">
          <button type="button" class="btn-secondary btn-salvar-short">Salvar</button>
          <button type="button" class="btn-secondary btn-novo-fundo-short">Outro fundo</button>
          <span class="video-meta short-status"></span>
        </div>
      </div>
    </div>`;
  painel.appendChild(secao);

  const area = secao.querySelector(".thumb-preview");
  const img = secao.querySelector(".thumb-preview-img");
  const rotulo = secao.querySelector(".thumb-preview-texto");
  const estado = { ...cfg, fundos: {} };
  const LARG = 1080;

  const corCss = () => (estado.cor ? `#${estado.cor}` : "#F6F2E9");
  const redesenhar = () => {
    rotulo.textContent = secao.querySelector(".short-texto").value;
    rotulo.style.left = `${estado.pos_x * 100}%`;
    rotulo.style.top = `${estado.pos_y * 100}%`;
    rotulo.style.color = corCss();
    rotulo.style.fontSize = `${estado.tamanho_px * escalaPreview(area, LARG)}px`;
    rotulo.style.setProperty("--cor-titulo", estado.cor ? corCss() : "#ffc21a");
    aplicarEfeitoPreview(rotulo, estado.efeito);
    img.src = estado.fundos[estado.fundo] || estado.fundos.procedural || "";
  };
  const carregarFundos = async () => {
    const r = await fetch(`/api/videos/${slug}/thumbnail-shorts/fundo`);
    const f = await r.json();
    if (!f.erro) estado.fundos = f;
    if (!estado.fundos.cena && estado.fundo === "cena") estado.fundo = "procedural";
    redesenhar();
  };

  secao.querySelector(".short-texto").addEventListener("input", redesenhar);
  secao.querySelector(".thumb-efeito").addEventListener("change", (ev) => { estado.efeito = ev.target.value; redesenhar(); });
  secao.querySelector(".short-fundo").addEventListener("change", (ev) => { estado.fundo = ev.target.value; redesenhar(); });
  secao.querySelector(".short-tamanho").addEventListener("input", (ev) => {
    estado.tamanho_px = parseInt(ev.target.value, 10);
    secao.querySelector(".short-tamanho-valor").textContent = `${estado.tamanho_px}px`;
    redesenhar();
  });
  secao.querySelectorAll(".cor-swatch").forEach((sw) => sw.addEventListener("click", () => {
    secao.querySelectorAll(".cor-swatch").forEach((x) => x.classList.remove("selecionada"));
    sw.classList.add("selecionada");
    estado.cor = sw.dataset.hex;
    redesenhar();
  }));

  const mover = (cx, cy) => {
    const rect = area.getBoundingClientRect();
    estado.pos_x = Math.min(Math.max((cx - rect.left) / rect.width, 0), 1);
    estado.pos_y = Math.min(Math.max((cy - rect.top) / rect.height, 0), 1);
    redesenhar();
  };
  rotulo.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    rotulo.setPointerCapture(ev.pointerId);
    const onMove = (e) => mover(e.clientX, e.clientY);
    const onUp = () => { rotulo.removeEventListener("pointermove", onMove); rotulo.removeEventListener("pointerup", onUp); };
    rotulo.addEventListener("pointermove", onMove);
    rotulo.addEventListener("pointerup", onUp);
  });

  const salvar = async (novoFundo) => {
    const status = secao.querySelector(".short-status");
    const texto = secao.querySelector(".short-texto").value.trim();
    if (!texto && !confirm("O texto está vazio: a thumbnail do Short vai ficar SEM texto. Continuar?")) return;
    status.textContent = "Salvando…";
    const dados = new FormData();
    dados.set("texto", texto);
    dados.set("cor", estado.cor || "");
    dados.set("tamanho_px", estado.tamanho_px);
    dados.set("pos_x", estado.pos_x.toFixed(4));
    dados.set("pos_y", estado.pos_y.toFixed(4));
    dados.set("efeito", estado.efeito);
    dados.set("fundo", estado.fundo);
    dados.set("novo_fundo", novoFundo ? "true" : "false");
    try {
      const r = await fetch(`/api/videos/${slug}/thumbnail-shorts/editar`, { method: "POST", body: dados });
      const res = await r.json();
      if (res.erro) { status.textContent = `Deu erro: ${res.erro}`; return; }
      if (novoFundo) await carregarFundos();
      status.textContent = "Salvo!";
      setTimeout(() => (status.textContent = ""), 3000);
    } catch {
      status.textContent = "Deu erro de conexão, tenta de novo.";
    }
  };
  secao.querySelector(".btn-salvar-short").addEventListener("click", () => salvar(false));
  secao.querySelector(".btn-novo-fundo-short").addEventListener("click", () => {
    estado.fundo = "procedural";
    secao.querySelector(".short-fundo").value = "procedural";
    salvar(true);
  });

  redesenhar();
  carregarFundos();
}
