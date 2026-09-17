const TITULOS = { painel: "Painel", novo: "Novo vídeo", fila: "Fila" };

function trocarAba(nome) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.tab === nome));
  document.querySelectorAll(".tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${nome}`));
  document.getElementById("page-title").textContent = TITULOS[nome];
  if (nome === "painel") carregarPainel();
  if (nome === "fila") carregarFila();
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

function formatarDataPostagem(iso) {
  if (!iso) return "sem data definida";
  const [ano, mes, dia] = iso.split("-");
  return `postar em ${dia}/${mes}/${ano}`;
}

function linhaDeVideo(v) {
  const modoLabel = v.modo === "ambiente" ? "· ambiente" : "";
  return `
    <div class="video-row">
      <div class="video-thumb">
        <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2.5" y="5.5" width="10" height="9" rx="1.5"></rect><path d="M12.5 9l5-3v8l-5-3z"></path></svg>
      </div>
      <div class="video-info">
        <div class="video-title">${v.titulo}</div>
        <div class="video-meta">${formatarDataPostagem(v.data_postagem)} ${modoLabel}</div>
      </div>
      <div class="video-links">
        <a href="${v.video_16_9}" target="_blank">16:9</a>
        <a href="${v.video_9_16}" target="_blank">Shorts</a>
      </div>
    </div>`;
}

async function buscarVideos() {
  const resposta = await fetch("/api/videos");
  return resposta.ok ? resposta.json() : [];
}

async function carregarPainel() {
  const videos = await buscarVideos();
  document.getElementById("stat-total").textContent = videos.length;
  const lista = document.getElementById("painel-lista");
  lista.innerHTML = videos.length
    ? videos.slice(0, 6).map(linhaDeVideo).join("")
    : '<div class="empty">Nenhum vídeo ainda — vá em "Novo vídeo" pra gerar o primeiro.</div>';
}

async function carregarFila() {
  const videos = await buscarVideos();
  const lista = document.getElementById("fila-lista");
  lista.innerHTML = videos.length
    ? videos.map(linhaDeVideo).join("")
    : '<div class="empty">Nenhum vídeo gerado ainda.</div>';
}

// ---------------- Contexto do canal ----------------

const formCanal = document.getElementById("form-canal");
const canalStatus = document.getElementById("canal-status");

fetch("/api/canal")
  .then((r) => r.json())
  .then((dados) => { formCanal.querySelector("[name=contexto]").value = dados.contexto || ""; });

formCanal.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  await fetch("/api/canal", { method: "POST", body: new FormData(formCanal) });
  canalStatus.textContent = "Salvo — os próximos roteiros já usam esse contexto.";
  setTimeout(() => (canalStatus.textContent = ""), 4000);
});

// ---------------- Novo vídeo: alternância de modo ----------------

const camposNarrado = document.getElementById("campos-narrado");
const camposAmbiente = document.getElementById("campos-ambiente");
const campoModo = document.getElementById("campo-modo");
const campoDuracao = document.getElementById("campo-duracao");

document.querySelectorAll(".modo-btn").forEach((botao) => {
  botao.addEventListener("click", () => {
    document.querySelectorAll(".modo-btn").forEach((b) => b.classList.toggle("active", b === botao));
    const modo = botao.dataset.modo;
    campoModo.value = modo;
    camposNarrado.hidden = modo === "ambiente";
    camposAmbiente.hidden = modo === "narrado";
    campoDuracao.value = modo === "ambiente" ? 15 : 1;
  });
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
  const resposta = await fetch("/api/videos", { method: "POST", body: dados });
  const { job_id } = await resposta.json();

  if (poller) clearInterval(poller);
  poller = setInterval(() => acompanharJob(job_id), 1200);
});

async function acompanharJob(jobId) {
  const resposta = await fetch(`/api/jobs/${jobId}`);
  const job = await resposta.json();

  progressFill.style.width = `${job.progresso}%`;
  progressoPct.textContent = `${Math.round(job.progresso)}%`;
  progressoEtapa.textContent = job.etapa;

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

  document.getElementById("resultado-conteudo").innerHTML = `
    <div class="resultado-formato">
      <h3>16:9 — vídeo normal (${formatarDuracao(resultado.duracao_segundos)})</h3>
      <video controls src="${resultado.video_16_9}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_16_9}" download>Baixar .mp4</a>
      </div>
    </div>
    <div class="resultado-formato">
      <h3>9:16 — Shorts</h3>
      <video controls src="${resultado.video_9_16}"></video>
      <div class="resultado-actions">
        <a href="${resultado.video_9_16}" download>Baixar .mp4</a>
      </div>
    </div>
    ${tags ? `<div class="resultado-formato"><h3>Hashtags sugeridas</h3><div class="tags-list">${tags}</div></div>` : ""}`;
}

carregarPainel();
