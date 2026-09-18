// Utilidades de progresso/tempo, confirmação de publicação e editor de legenda (com prévia ao vivo).
// Cliques delegados no documento: as linhas da Fila são redesenhadas o tempo todo.

// ---------------- progresso e estimativa (usados em vários lugares) ----------------

function formatarRestante(segundos) {
  const s = Math.round(segundos || 0);
  if (s <= 0) return "";
  const r = Math.max(5, Math.round(s / 5) * 5); // arredonda de 5 em 5 segundos
  const m = Math.floor(r / 60);
  const x = r % 60;
  if (!m) return `~${x} s`;
  return x ? `~${m} min ${x} s` : `~${m} min`;
}

function atualizarMiniBarra(container, pct) {
  let barra = container.querySelector(":scope > .mini-barra");
  if (!barra) {
    barra = document.createElement("div");
    barra.className = "mini-barra";
    barra.innerHTML = "<div></div>";
    container.appendChild(barra);
  }
  barra.firstElementChild.style.width = `${Math.max(2, Math.min(100, pct))}%`;
}

function removerMiniBarra(container) {
  container.querySelector(":scope > .mini-barra")?.remove();
}

function textoDeProgresso(job) {
  const restante = formatarRestante(job.restante_segundos);
  return `${Math.round(job.progresso)}% — ${job.etapa}${restante ? ` (faltam ${restante})` : ""}`;
}

// ---------------- prévia da legenda ----------------

const COR_TEXTO_LEGENDA = "#F6F2E9";

function desenharPreviewLegenda(mock, cfg) {
  const altura = mock.clientHeight || 160;
  const escala = { p: 0.8, m: 1, g: 1.25 }[cfg.tamanho] || 1;
  const px = altura * (82 / 1080) * escala; // mesma proporção usada no vídeo 16:9
  const cor = cfg.cor?.startsWith("#") ? cfg.cor : `#${cfg.cor || "E2793D"}`;
  const contorno = Math.max(1, px * 0.05);
  const sombra = [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, 1], [-1, 1], [1, -1]].map(([x, y]) => `${x * contorno}px ${y * contorno}px 0 #000`).join(",");
  mock.innerHTML = '<div class="leg-mock-fundo"></div>';
  if (cfg.modo === "nenhuma") {
    mock.insertAdjacentHTML("beforeend", '<div class="leg-mock-nenhuma">Sem legenda</div>');
    return;
  }
  const palavras = cfg.modo === "karaoke"
    ? `Assim vai ficar a <span style="color:${cor}">legenda</span> no vídeo`
    : "Assim vai ficar a legenda no vídeo";
  const posicao = { baixo: "bottom:5%", meio: "top:50%;transform:translateY(-50%)", topo: "top:6%" }[cfg.posicao] || "bottom:5%";
  const estiloCaixa = cfg.caixa ? `background:rgba(20,19,15,.75);padding:${px * 0.1}px ${px * 0.35}px;border-radius:${px * 0.1}px` : `text-shadow:${sombra}`;
  mock.insertAdjacentHTML("beforeend", `<div class="leg-mock-linha" style="${posicao}"><span class="leg-mock-texto" style="font-size:${px}px;color:${COR_TEXTO_LEGENDA};${estiloCaixa}">${palavras}</span></div>`);
}

// ---------------- confirmar publicação ----------------

document.addEventListener("click", (ev) => {
  const alvo = ev.target.closest(".btn-confirmar-publicacao, .btn-desfazer-confirmacao");
  if (alvo) definirAprovacao(alvo, alvo.classList.contains("btn-confirmar-publicacao"));
});

async function definirAprovacao(botao, aprovado) {
  const slug = botao.dataset.slug;
  if (aprovado && !confirm(`Confirmar a publicação de "${botao.dataset.titulo}"? Quando chegar a data marcada, ele será postado no YouTube. Se editar o vídeo depois, a confirmação é desfeita.`)) return;
  botao.disabled = true;
  const corpo = new FormData();
  corpo.set("aprovado", aprovado ? "true" : "false");
  const resultado = await fetch(`/api/videos/${slug}/aprovacao`, { method: "POST", body: corpo }).then((r) => r.json());
  if (resultado.erro) {
    alert(resultado.erro);
    botao.disabled = false;
    return;
  }
  carregarFila(true);
}

// ---------------- legenda + transição (Fila) ----------------

const OPCOES_LEGENDA = {
  modo: [["karaoke", "Karaokê (palavra atual em destaque)"], ["simples", "Simples (texto fixo)"], ["nenhuma", "Sem legenda"]],
  tamanho: [["p", "Pequena"], ["m", "Média"], ["g", "Grande"]],
  posicao: [["baixo", "Embaixo"], ["meio", "No meio"], ["topo", "No topo"]],
};
const OPCOES_TRANSICAO = [["fade", "Fade (suave)"], ["dissolver", "Dissolver"], ["deslizar", "Deslizar suave"], ["aleatoria", "Variada (só as suaves)"], ["nenhuma", "Sem transição (corte seco)"]];

function selectHtml(classe, opcoes, atual) {
  return `<select class="${classe}">${opcoes.map(([v, r]) => `<option value="${v}"${v === atual ? " selected" : ""}>${r}</option>`).join("")}</select>`;
}

function alternarPainelLegenda(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.legenda-painel[data-slug="${slug}"]`);
  if (!painel) return;
  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  if (abrindo) painel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (!abrindo || painel.dataset.montado === "true") return;
  painel.dataset.montado = "true";

  if (painel.dataset.temCues !== "true") {
    painel.innerHTML = '<div class="cenas-status">Esse vídeo foi gerado antes da legenda ser editável. Use "Regenerar" uma vez para habilitar.</div>';
    return;
  }
  const cfg = JSON.parse(decodeURIComponent(painel.dataset.legenda));
  painel.innerHTML = `
    <div class="cenas-status">Muda só a legenda e a transição: o vídeo é remontado com as mesmas imagens e narração.</div>
    <div class="legenda-editor">
      <div class="legenda-grade">
        <label><span>Estilo</span>${selectHtml("leg-modo", OPCOES_LEGENDA.modo, cfg.modo)}</label>
        <label><span>Tamanho</span>${selectHtml("leg-tamanho", OPCOES_LEGENDA.tamanho, cfg.tamanho)}</label>
        <label><span>Posição</span>${selectHtml("leg-posicao", OPCOES_LEGENDA.posicao, cfg.posicao)}</label>
        <label><span>Cor de destaque</span><input type="color" class="leg-cor" value="#${cfg.cor}"></label>
        <label><span>Transição entre cenas</span>${selectHtml("leg-transicao", OPCOES_TRANSICAO, painel.dataset.transicao || "fade")}</label>
        <label class="leg-check"><input type="checkbox" class="leg-caixa"${cfg.caixa ? " checked" : ""}><span>Fundo escuro atrás</span></label>
      </div>
      <div class="leg-preview-bloco">
        <span class="video-meta">Exemplo (aproximado)</span>
        <div class="leg-mock"></div>
      </div>
    </div>
    <div class="cena-card-acoes">
      <button type="button" class="btn-secondary btn-aplicar-legenda">Aplicar</button>
      <span class="video-meta legenda-status"></span>
    </div>`;
  const ler = () => ({
    modo: painel.querySelector(".leg-modo").value,
    tamanho: painel.querySelector(".leg-tamanho").value,
    posicao: painel.querySelector(".leg-posicao").value,
    cor: painel.querySelector(".leg-cor").value,
    caixa: painel.querySelector(".leg-caixa").checked,
  });
  const mock = painel.querySelector(".leg-mock");
  const redesenhar = () => desenharPreviewLegenda(mock, ler());
  painel.querySelectorAll("select, input").forEach((c) => c.addEventListener("input", redesenhar));
  requestAnimationFrame(redesenhar);
  painel.querySelector(".btn-aplicar-legenda").addEventListener("click", () => aplicarLegenda(slug, painel, ler));
}

async function aplicarLegenda(slug, painel, ler) {
  const status = painel.querySelector(".legenda-status");
  const botao = painel.querySelector(".btn-aplicar-legenda");
  const cfg = ler();
  const corpo = new FormData();
  corpo.set("modo", cfg.modo);
  corpo.set("tamanho", cfg.tamanho);
  corpo.set("posicao", cfg.posicao);
  corpo.set("cor", cfg.cor);
  corpo.set("caixa", cfg.caixa ? "true" : "false");
  corpo.set("transicao", painel.querySelector(".leg-transicao").value);
  botao.disabled = true;
  status.textContent = "Enviando…";
  const { job_id, erro } = await fetch(`/api/videos/${slug}/legenda`, { method: "POST", body: corpo }).then((r) => r.json());
  if (erro) {
    status.textContent = `Deu erro: ${erro}`;
    botao.disabled = false;
    return;
  }
  const acoes = painel.querySelector(".cena-card-acoes");
  const intervalo = setInterval(async () => {
    const job = await fetch(`/api/jobs/${job_id}`).then((r) => r.json()).catch(() => null);
    if (!job || typeof job.progresso !== "number") return;
    status.textContent = textoDeProgresso(job);
    atualizarMiniBarra(acoes, job.progresso);
    if (job.status === "pronto") {
      clearInterval(intervalo);
      botao.disabled = false;
      removerMiniBarra(acoes);
      status.textContent = "Pronto! Abra o vídeo para conferir (a confirmação de publicação foi desfeita).";
      setTimeout(carregarFila, 1500);
    } else if (job.status === "erro") {
      clearInterval(intervalo);
      botao.disabled = false;
      removerMiniBarra(acoes);
      status.textContent = `Deu erro: ${job.erro}`;
    }
  }, 1200);
}
