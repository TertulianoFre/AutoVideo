// Fila: menus suspensos (Editar vídeo / Regenerar), regenerar com confirmação e edição do texto das cenas (lápis).

const PALAVRAS_POR_SEGUNDO = 2.8; // ritmo médio dessa narração em português (medido nos vídeos gerados)

function estimarNarracao(texto) {
  const palavras = (texto || "").trim().split(/\s+/).filter(Boolean).length;
  const segundos = palavras / PALAVRAS_POR_SEGUNDO;
  return { palavras, segundos };
}

function formatarNarracao(texto) {
  const { palavras, segundos } = estimarNarracao(texto);
  if (!palavras) return "sem texto";
  const s = Math.round(segundos);
  return `${palavras} palavras · ≈ ${s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`} de narração`;
}

// ---------------- menus suspensos ----------------

document.addEventListener("click", (ev) => {
  const abrir = ev.target.closest(".btn-abrir-menu");
  const item = ev.target.closest(".menu-suspenso button");
  document.querySelectorAll(".menu-suspenso.aberto").forEach((m) => {
    if (!abrir || m !== abrir.nextElementSibling) m.classList.remove("aberto");
  });
  if (abrir) {
    abrir.nextElementSibling.classList.toggle("aberto");
    return;
  }
  if (item) executarAcaoMenu(item);
});

function executarAcaoMenu(item) {
  const slug = item.dataset.slug;
  const alvo = { dataset: { slug }, textContent: "" }; // as funções dos painéis só precisam do slug
  const acao = item.dataset.acao;
  if (["cenas", "legenda", "thumb"].includes(acao) && !fecharOutrosPaineis(acao, slug)) return;
  switch (acao) {
    case "cenas": alternarPainelCenas(alvo); break;
    case "legenda": alternarPainelLegenda(alvo); break;
    case "thumb": alternarPainelThumb(alvo); break;
    case "regen-mesmo": confirmarRegenerar(slug, item.dataset.titulo, true); break;
    case "regen-novo": confirmarRegenerar(slug, item.dataset.titulo, false); break;
  }
}

// abrir uma edição fecha a que estiver aberta (em qualquer vídeo) — senão vira informação demais na tela
function fecharOutrosPaineis(acao, slug) {
  const classe = { cenas: "cenas-painel", legenda: "legenda-painel", thumb: "thumb-painel" }[acao];
  for (const painel of document.querySelectorAll(".cenas-painel.aberto, .legenda-painel.aberto, .thumb-painel.aberto")) {
    if (painel.classList.contains(classe) && painel.dataset.slug === slug) continue; // esse mesmo: o clique vai fechá-lo
    if (painel.classList.contains("cenas-painel") && (contarEdicoesDeTexto(painel) || temposAlterados(painel)) && !confirm("Tem alterações nas cenas que ainda não foram salvas. Fechar mesmo assim (elas serão descartadas)?")) return false;
    if (painel.classList.contains("cenas-painel")) painel.dataset.carregado = ""; // reabre limpo
    painel.classList.remove("aberto");
  }
  return true;
}

// ---------------- regenerar (com confirmação) ----------------

function confirmarRegenerar(slug, titulo, manterRoteiro) {
  const o_que = manterRoteiro ? "mantendo o roteiro atual" : "escrevendo um roteiro NOVO";
  if (!confirm(`Regenerar "${titulo}" ${o_que}? Narração, imagens e vídeo são refeitos do zero (trocas que você fez nas cenas se perdem) e a publicação precisará ser confirmada de novo.`)) return;
  regenerarVideo(slug, manterRoteiro, false);
}

async function regenerarVideo(slug, manterRoteiro, reaproveitarImagens) {
  const dados = new FormData();
  dados.set("manter_roteiro", manterRoteiro ? "true" : "false");
  dados.set("reaproveitar_imagens", reaproveitarImagens ? "true" : "false");
  const resposta = await fetch(`/api/videos/${slug}/regenerar`, { method: "POST", body: dados });
  const { erro } = await resposta.json();
  if (erro) {
    alert(erro);
    return;
  }
  // o vídeo passa a aparecer como "processando" (com barra e tempo restante) até terminar
  await carregarFila(true);
  carregarPainel();
}

// ---------------- edição do texto das cenas (lápis) ----------------

function contarEdicoesDeTexto(painel) {
  return [...painel.querySelectorAll(".cena-edicao-texto")].filter((t) => t.value.trim() !== t.dataset.original.trim() && !t.closest(".cena-edicao").hidden).length;
}

function atualizarBotaoSalvarTextos(painel) {
  const n = contarEdicoesDeTexto(painel);
  const botao = painel.querySelector(".btn-salvar-textos");
  botao.hidden = n === 0;
  botao.textContent = n === 1 ? "Salvar 1 texto e refazer narração" : `Salvar ${n} textos e refazer narração`;
}

document.addEventListener("click", (ev) => {
  const lapis = ev.target.closest(".btn-lapis");
  if (!lapis) return;
  const card = lapis.closest(".cena-card");
  const area = card.querySelector(".cena-edicao");
  const abrindo = area.hidden;
  area.hidden = !abrindo;
  card.querySelector(".cena-card-texto").hidden = abrindo;
  lapis.classList.toggle("ativo", abrindo);
  const campo = area.querySelector("textarea");
  if (abrindo) {
    campo.focus();
    area.querySelector(".cena-edicao-info").textContent = formatarNarracao(campo.value);
  } else {
    campo.value = campo.dataset.original; // fechar o lápis descarta a edição dessa cena
  }
  atualizarBotaoSalvarTextos(card.closest(".cenas-painel"));
});

document.addEventListener("input", (ev) => {
  const campo = ev.target.closest(".cena-edicao-texto");
  if (!campo) return;
  const area = campo.closest(".cena-edicao");
  const original = estimarNarracao(campo.dataset.original).segundos;
  const novo = estimarNarracao(campo.value).segundos;
  const dif = Math.round(novo - original);
  area.querySelector(".cena-edicao-info").textContent = `${formatarNarracao(campo.value)}${dif ? ` (${dif > 0 ? "+" : ""}${dif} s em relação ao original)` : ""}`;
  atualizarBotaoSalvarTextos(campo.closest(".cenas-painel"));
});

async function salvarTextosDasCenas(painel, slug) {
  const edicoes = {};
  painel.querySelectorAll(".cena-card").forEach((card) => {
    const campo = card.querySelector(".cena-edicao-texto");
    if (!card.querySelector(".cena-edicao").hidden && campo.value.trim() !== campo.dataset.original.trim()) {
      edicoes[card.dataset.indice] = campo.value.trim();
    }
  });
  const n = Object.keys(edicoes).length;
  if (!n) return;
  if (!confirm(`Salvar ${n} texto(s) e refazer a narração? As imagens das cenas que não mudaram são mantidas. O vídeo é regravado e a publicação precisará ser confirmada de novo.`)) return;
  const status = painel.querySelector(".cenas-rodape-status");
  status.textContent = "Salvando o roteiro…";
  const corpo = new FormData();
  corpo.set("edicoes", JSON.stringify(edicoes));
  const resultado = await fetch(`/api/videos/${slug}/cenas/textos`, { method: "PUT", body: corpo }).then((r) => r.json());
  if (resultado.erro) {
    status.textContent = `Deu erro: ${resultado.erro}`;
    return;
  }
  painel.dataset.carregado = "";
  painel.classList.remove("aberto");
  await regenerarVideo(slug, true, true);
}

// lápis pequeno ao lado de "Gerar outra imagem": abre/fecha o campo de descrição da imagem
document.addEventListener("click", (ev) => {
  const lapis = ev.target.closest(".btn-lapis-desc");
  if (!lapis) return;
  const campo = lapis.closest(".cena-card").querySelector(".cena-descricao");
  campo.hidden = !campo.hidden;
  lapis.classList.toggle("aberto", !campo.hidden);
  if (!campo.hidden) campo.focus();
});


// ---------------- tempo de cada cena (só aumenta; as seguintes andam pra frente) ----------------

function temposAlterados(painel) {
  return [...painel.querySelectorAll(".cena-duracao")].some((i) => Math.abs((parseFloat(i.value) || 0) - parseFloat(i.dataset.original)) > 0.05);
}

function recalcularTemposDasCenas(painel) {
  let acumulado = 0;
  painel.querySelectorAll(".cena-card").forEach((card) => {
    const campo = card.querySelector(".cena-duracao");
    const dur = campo ? Math.max(parseFloat(campo.value) || 0, parseFloat(campo.dataset.minimo)) : parseFloat(card.dataset.duracao || 0);
    if (campo) {
      const natural = parseFloat(campo.dataset.natural);
      const info = card.querySelector(".cena-tempo-info");
      const excesso = Math.round((dur - natural) * 10) / 10;
      info.textContent = excesso > 0.05
        ? `Fala de ${natural} s + pausa de ${excesso} s no fim da cena.`
        : excesso < -0.05
          ? `Fala acelerada em ${(natural / dur).toFixed(2).replace(".", ",")}× para caber em ${dur} s.`
          : `A fala dessa cena dura ${natural} s (tempo original). Mais vira pausa; menos acelera a fala (mínimo ${campo.dataset.minimo} s).`;
    }
    const rotulo = card.querySelector(".cena-card-tempo");
    if (rotulo) rotulo.textContent = `${formatarTempo(acumulado)}–${formatarTempo(acumulado + dur)} · ${Math.round(dur * 10) / 10}s`;
    acumulado += dur;
  });
  const total = painel.querySelector(".cenas-total");
  if (total) total.textContent = formatarTempo(acumulado);
  const botao = painel.querySelector(".btn-aplicar-tempos");
  const mudou = temposAlterados(painel);
  botao.hidden = !mudou;
  if (mudou) botao.textContent = `Aplicar tempos (vídeo de ${formatarTempo(parseFloat(total.dataset.original))} → ${formatarTempo(acumulado)})`;
}

document.addEventListener("input", (ev) => {
  const campo = ev.target.closest(".cena-duracao");
  if (campo) recalcularTemposDasCenas(campo.closest(".cenas-painel"));
});

document.addEventListener("change", (ev) => {
  const campo = ev.target.closest(".cena-duracao");
  if (!campo) return;
  const minimo = parseFloat(campo.dataset.minimo);
  if (!(parseFloat(campo.value) >= minimo)) campo.value = minimo; // abaixo disso a fala ficaria rápida demais
  recalcularTemposDasCenas(campo.closest(".cenas-painel"));
});

async function aplicarTemposDasCenas(painel, slug) {
  const status = painel.querySelector(".cenas-rodape-status");
  const botao = painel.querySelector(".btn-aplicar-tempos");
  const duracoes = {};
  painel.querySelectorAll(".cena-card").forEach((card) => {
    const campo = card.querySelector(".cena-duracao");
    if (campo) duracoes[card.dataset.indice] = Math.max(parseFloat(campo.value) || 0, parseFloat(campo.dataset.minimo));
  });
  if (!confirm("Aplicar os novos tempos? Cenas que aumentaram ganham uma pausa depois da fala; as que diminuíram têm a fala acelerada. As outras cenas só andam no tempo (não mudam de duração), a legenda acompanha e o vídeo é remontado. A publicação precisará ser confirmada de novo.")) return;
  botao.disabled = true;
  const corpo = new FormData();
  corpo.set("duracoes", JSON.stringify(duracoes));
  const { job_id, erro } = await fetch(`/api/videos/${slug}/cenas/duracoes`, { method: "POST", body: corpo }).then((r) => r.json());
  if (erro) {
    status.textContent = `Deu erro: ${erro}`;
    botao.disabled = false;
    return;
  }
  const rodape = painel.querySelector(".cenas-rodape");
  const intervalo = setInterval(async () => {
    const job = await fetch(`/api/jobs/${job_id}`).then((r) => r.json()).catch(() => null);
    if (!job || typeof job.progresso !== "number") return;
    status.textContent = textoDeProgresso(job);
    atualizarMiniBarra(rodape.parentElement, job.progresso);
    if (job.status === "pronto" || job.status === "erro") {
      clearInterval(intervalo);
      removerMiniBarra(rodape.parentElement);
      botao.disabled = false;
      if (job.status === "erro") {
        status.textContent = `Deu erro: ${job.erro}`;
        return;
      }
      painel.dataset.carregado = ""; // recarrega as cenas com os tempos novos
      painel.classList.remove("aberto");
      alternarPainelCenas({ dataset: { slug }, textContent: "" });
      carregarFila(true).then(() => alternarPainelCenas({ dataset: { slug }, textContent: "" }));
    }
  }, 1200);
}
