// Calendário do mês (ícone no topo de todas as páginas): mostra, em cada dia, os vídeos agendados/publicados
// com hora, título e situação. Clicar num vídeo abre ele na Fila.

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

const botaoCalendario = document.getElementById("btn-calendario");
const popCalendario = document.getElementById("calendario-pop");
let mesCalendario = new Date();
mesCalendario.setDate(1);
let videosCalendario = [];
let diaSelecionado = null;

function isoLocal(data) {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
}

function rotuloStatus(v) {
  return (typeof STATUS_FILA !== "undefined" && STATUS_FILA[v.status]) || { rotulo: v.status, classe: "" };
}

function itemDoDia(v, completo) {
  const info = rotuloStatus(v);
  const hora = v.hora_postagem || "sem hora";
  const titulo = (v.titulo || "").replace(/</g, "&lt;");
  const canal = typeof mostrarBadgeCanal !== "undefined" && mostrarBadgeCanal && v.canal_nome ? ` · ${v.canal_nome}` : "";
  return `<button type="button" class="cal-item cal-${v.status}" data-slug="${v.slug}" title="${titulo} — ${hora} — ${info.rotulo}">
      <span class="cal-item-hora">${hora}</span>
      <span class="cal-item-titulo">${completo ? titulo : titulo.slice(0, 26) + (titulo.length > 26 ? "…" : "")}</span>
      ${completo ? `<span class="status-badge ${info.classe}">${info.rotulo}</span><span class="video-meta">${canal}</span>` : ""}
    </button>`;
}

function desenharCalendario() {
  const ano = mesCalendario.getFullYear();
  const mes = mesCalendario.getMonth();
  const hoje = isoLocal(new Date());
  const porDia = {};
  videosCalendario.filter((v) => v.data_postagem).forEach((v) => (porDia[v.data_postagem] ||= []).push(v));
  Object.values(porDia).forEach((lista) => lista.sort((a, b) => (a.hora_postagem || "99:99").localeCompare(b.hora_postagem || "99:99")));

  const primeiroDiaSemana = new Date(ano, mes, 1).getDay();
  const diasNoMes = new Date(ano, mes + 1, 0).getDate();
  let celulas = DIAS_SEMANA.map((d) => `<div class="cal-semana">${d}</div>`).join("");
  for (let i = 0; i < primeiroDiaSemana; i++) celulas += '<div class="cal-dia cal-vazio"></div>';
  for (let dia = 1; dia <= diasNoMes; dia++) {
    const iso = `${ano}-${String(mes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
    const lista = porDia[iso] || [];
    const visiveis = lista.slice(0, 2).map((v) => itemDoDia(v, false)).join("");
    celulas += `<div class="cal-dia${iso === hoje ? " cal-hoje" : ""}${iso === diaSelecionado ? " cal-selecionado" : ""}${lista.length ? " cal-com-video" : ""}" data-iso="${iso}">
        <span class="cal-numero">${dia}</span>${visiveis}${lista.length > 2 ? `<span class="cal-mais">+${lista.length - 2} mais</span>` : ""}
      </div>`;
  }
  const detalhe = diaSelecionado && porDia[diaSelecionado]
    ? `<div class="cal-detalhe"><strong>${diaSelecionado.split("-").reverse().join("/")}</strong>${porDia[diaSelecionado].map((v) => itemDoDia(v, true)).join("")}</div>`
    : diaSelecionado ? `<div class="cal-detalhe video-meta">Nenhum vídeo nesse dia.</div>` : "";

  popCalendario.innerHTML = `
    <div class="cal-topo">
      <button type="button" class="cal-nav" data-passo="-1" title="Mês anterior">‹</button>
      <strong class="cal-titulo">${MESES[mes][0].toUpperCase() + MESES[mes].slice(1)} de ${ano}</strong>
      <button type="button" class="cal-nav" data-passo="1" title="Próximo mês">›</button>
      <button type="button" class="btn-secondary btn-compacto cal-hoje-btn">Hoje</button>
    </div>
    <div class="cal-grade">${celulas}</div>
    ${detalhe}`;
}

async function abrirCalendario() {
  popCalendario.hidden = false;
  botaoCalendario.classList.add("aberto");
  desenharCalendario();
  try {
    videosCalendario = await (await fetch("/api/videos")).json();
  } catch {
    videosCalendario = [];
  }
  desenharCalendario();
}

function fecharCalendario() {
  popCalendario.hidden = true;
  botaoCalendario.classList.remove("aberto");
}

botaoCalendario.addEventListener("click", (ev) => {
  ev.stopPropagation();
  if (popCalendario.hidden) abrirCalendario();
  else fecharCalendario();
});

popCalendario.addEventListener("click", (ev) => {
  ev.stopPropagation();
  const nav = ev.target.closest(".cal-nav");
  if (nav) {
    mesCalendario.setMonth(mesCalendario.getMonth() + parseInt(nav.dataset.passo, 10));
    diaSelecionado = null;
    desenharCalendario();
    return;
  }
  if (ev.target.closest(".cal-hoje-btn")) {
    mesCalendario = new Date();
    mesCalendario.setDate(1);
    diaSelecionado = isoLocal(new Date());
    desenharCalendario();
    return;
  }
  const item = ev.target.closest(".cal-item");
  if (item) {
    fecharCalendario();
    trocarAba("fila");
    const slug = item.dataset.slug;
    const tentar = (n) => {
      const linha = document.querySelector(`.video-row[data-slug="${slug}"]`) || document.querySelector(`[data-processando="${slug}"]`);
      if (linha) {
        linha.scrollIntoView({ block: "center", behavior: "smooth" });
        linha.classList.add("piscar");
        setTimeout(() => linha.classList.remove("piscar"), 2200);
      } else if (n > 0) setTimeout(() => tentar(n - 1), 300);
    };
    tentar(10);
    return;
  }
  const dia = ev.target.closest(".cal-dia[data-iso]");
  if (dia) {
    diaSelecionado = dia.dataset.iso;
    desenharCalendario();
  }
});

document.addEventListener("click", () => { if (!popCalendario.hidden) fecharCalendario(); });
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !popCalendario.hidden) fecharCalendario(); });
