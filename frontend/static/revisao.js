// Fila: confirmar publicação, editar legenda/transição e revisão do vídeo pelo agente.
// Usa cliques delegados no documento (as linhas da Fila são redesenhadas o tempo todo).

const OPCOES_LEGENDA = {
  modo: [["karaoke", "Karaokê (palavra atual em destaque)"], ["simples", "Simples (texto fixo)"], ["nenhuma", "Sem legenda"]],
  tamanho: [["p", "Pequena"], ["m", "Média"], ["g", "Grande"]],
  posicao: [["baixo", "Embaixo"], ["meio", "No meio"], ["topo", "No topo"]],
};
const OPCOES_TRANSICAO = [["fade", "Fade (suave)"], ["dissolver", "Dissolver"], ["deslizar", "Deslizar"], ["zoom", "Zoom"], ["circulo", "Círculo"], ["aleatoria", "Aleatória"], ["nenhuma", "Sem transição"]];

function selectHtml(classe, opcoes, atual) {
  return `<select class="${classe}">${opcoes.map(([v, r]) => `<option value="${v}"${v === atual ? " selected" : ""}>${r}</option>`).join("")}</select>`;
}

document.addEventListener("click", (ev) => {
  const alvo = ev.target.closest(".btn-legenda, .btn-revisar, .btn-confirmar-publicacao, .btn-desfazer-confirmacao");
  if (!alvo) return;
  if (alvo.classList.contains("btn-legenda")) alternarPainelLegenda(alvo);
  else if (alvo.classList.contains("btn-revisar")) alternarPainelRevisao(alvo);
  else definirAprovacao(alvo, alvo.classList.contains("btn-confirmar-publicacao"));
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
  carregarFila();
}

// ---------------- legenda + transição ----------------

function alternarPainelLegenda(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.legenda-painel[data-slug="${slug}"]`);
  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder legenda" : "legenda";
  if (!abrindo || painel.dataset.montado === "true") return;
  painel.dataset.montado = "true";

  if (painel.dataset.temCues !== "true") {
    painel.innerHTML = '<div class="cenas-status">Esse vídeo foi gerado antes da legenda ser editável. Clique em "Regenerar" uma vez para habilitar.</div>';
    return;
  }
  const cfg = JSON.parse(decodeURIComponent(painel.dataset.legenda));
  painel.innerHTML = `
    <div class="cenas-status">Muda só a legenda e a transição: o vídeo é remontado com as mesmas imagens e narração (leva menos de um minuto).</div>
    <div class="legenda-grade">
      <label><span>Estilo</span>${selectHtml("leg-modo", OPCOES_LEGENDA.modo, cfg.modo)}</label>
      <label><span>Tamanho</span>${selectHtml("leg-tamanho", OPCOES_LEGENDA.tamanho, cfg.tamanho)}</label>
      <label><span>Posição</span>${selectHtml("leg-posicao", OPCOES_LEGENDA.posicao, cfg.posicao)}</label>
      <label><span>Cor de destaque</span><input type="color" class="leg-cor" value="#${cfg.cor}"></label>
      <label class="checkbox-row"><input type="checkbox" class="leg-caixa"${cfg.caixa ? " checked" : ""}><span>Fundo escuro atrás</span></label>
      <label><span>Transição entre cenas</span>${selectHtml("leg-transicao", OPCOES_TRANSICAO, painel.dataset.transicao || "fade")}</label>
    </div>
    <div class="cena-card-acoes">
      <button type="button" class="btn-secondary btn-aplicar-legenda">Aplicar</button>
      <span class="video-meta legenda-status"></span>
    </div>`;
  painel.querySelector(".btn-aplicar-legenda").addEventListener("click", () => aplicarLegenda(slug, painel));
}

async function aplicarLegenda(slug, painel) {
  const status = painel.querySelector(".legenda-status");
  const botao = painel.querySelector(".btn-aplicar-legenda");
  const corpo = new FormData();
  corpo.set("modo", painel.querySelector(".leg-modo").value);
  corpo.set("tamanho", painel.querySelector(".leg-tamanho").value);
  corpo.set("posicao", painel.querySelector(".leg-posicao").value);
  corpo.set("cor", painel.querySelector(".leg-cor").value);
  corpo.set("caixa", painel.querySelector(".leg-caixa").checked ? "true" : "false");
  corpo.set("transicao", painel.querySelector(".leg-transicao").value);
  botao.disabled = true;
  status.textContent = "Enviando…";
  const { job_id, erro } = await fetch(`/api/videos/${slug}/legenda`, { method: "POST", body: corpo }).then((r) => r.json());
  if (erro) {
    status.textContent = `Deu erro: ${erro}`;
    botao.disabled = false;
    return;
  }
  const intervalo = setInterval(async () => {
    const job = await fetch(`/api/jobs/${job_id}`).then((r) => r.json()).catch(() => null);
    if (!job || typeof job.progresso !== "number") return;
    status.textContent = `${Math.round(job.progresso)}% — ${job.etapa}`;
    if (job.status === "pronto") {
      clearInterval(intervalo);
      botao.disabled = false;
      status.textContent = "Pronto! Abra o vídeo pra conferir (a confirmação de publicação foi desfeita).";
      const linha = document.querySelector(`.video-row[data-slug="${slug}"]`);
      const l16 = linha?.querySelector('a[href*="video_16x9"]');
      const l9 = linha?.querySelector('a[href*="video_9x16"]');
      if (l16 && job.resultado.video_16_9) l16.href = job.resultado.video_16_9;
      if (l9 && job.resultado.video_9_16) l9.href = job.resultado.video_9_16;
    } else if (job.status === "erro") {
      clearInterval(intervalo);
      botao.disabled = false;
      status.textContent = `Deu erro: ${job.erro}`;
    }
  }, 1200);
}

// ---------------- revisão pelo agente ----------------

const CAMPOS_REVISAO = [
  ["titulo", "Título", "input"],
  ["descricao_youtube", "Descrição do YouTube", "textarea"],
  ["tags", "Tags", "input"],
  ["thumbnail_texto", "Texto da thumbnail", "input"],
];

function esc(texto) {
  return String(texto ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

async function alternarPainelRevisao(botao) {
  const slug = botao.dataset.slug;
  const painel = document.querySelector(`.revisao-painel[data-slug="${slug}"]`);
  const abrindo = !painel.classList.contains("aberto");
  painel.classList.toggle("aberto", abrindo);
  botao.textContent = abrindo ? "esconder revisão" : "revisar com agente";
  if (!abrindo || painel.dataset.carregado === "true") return;
  painel.dataset.carregado = "true";

  painel.innerHTML = '<div class="cenas-status">O agente está lendo o vídeo e pensando em melhorias… (pode levar um minuto)</div><div class="barra-indeterminada"><div></div></div>';
  let dados;
  try {
    dados = await fetch(`/api/videos/${slug}/revisar`, { method: "POST" }).then((r) => r.json());
  } catch {
    dados = { erro: "Deu erro de conexão." };
  }
  if (dados.erro) {
    painel.dataset.carregado = "";
    painel.innerHTML = `<div class="cenas-status">Deu erro: ${esc(dados.erro)}</div>`;
    return;
  }

  const sugestoes = CAMPOS_REVISAO.filter(([campo]) => dados[campo]);
  const linhas = sugestoes.map(([campo, rotulo, tipo]) => {
    const valor = campo === "tags" ? dados.tags.join(", ") : dados[campo];
    const campoHtml = tipo === "textarea"
      ? `<textarea class="rev-valor" data-campo="${campo}" rows="5">${esc(valor)}</textarea>`
      : `<input type="text" class="rev-valor" data-campo="${campo}" value="${esc(valor)}">`;
    return `<div class="rev-item">
      <label class="checkbox-row"><input type="checkbox" class="rev-marcar" checked><span><b>${rotulo}</b></span></label>
      <div class="video-meta">Hoje: ${esc(dados.atual[campo])}</div>
      ${campoHtml}
    </div>`;
  }).join("");
  const observacoes = (dados.observacoes || []).length
    ? `<div class="rev-obs"><b>Pontos que exigem regenerar o vídeo (não dá pra aplicar aqui):</b><ul>${dados.observacoes.map((o) => `<li>${esc(o)}</li>`).join("")}</ul></div>`
    : "";
  painel.innerHTML = `
    <div class="cenas-status">${esc(dados.resumo) || "Revisão pronta."}</div>
    ${linhas || '<div class="cenas-status">O agente não sugeriu mudanças de título, descrição, tags ou thumbnail.</div>'}
    ${observacoes}
    ${linhas ? `<div class="cena-card-acoes"><button type="button" class="btn-secondary btn-aplicar-revisao">Aplicar as marcadas</button><span class="video-meta rev-status"></span></div>` : ""}`;

  const aplicar = painel.querySelector(".btn-aplicar-revisao");
  if (aplicar) {
    aplicar.addEventListener("click", async () => {
      const status = painel.querySelector(".rev-status");
      const corpo = new FormData();
      painel.querySelectorAll(".rev-item").forEach((item) => {
        if (item.querySelector(".rev-marcar").checked) {
          const campo = item.querySelector(".rev-valor");
          corpo.set(campo.dataset.campo, campo.value);
        }
      });
      status.textContent = "Aplicando…";
      const resultado = await fetch(`/api/videos/${slug}/revisar/aplicar`, { method: "POST", body: corpo }).then((r) => r.json());
      status.textContent = resultado.resposta || resultado.erro || "";
      if (resultado.acao === "editar") setTimeout(carregarFila, 1200);
    });
  }
}
