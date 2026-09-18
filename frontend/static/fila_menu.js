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

// acompanha um job de edição de estrutura (cena adicionada/removida/texto trocado) no rodapé do painel
async function acompanharEdicaoDeCenas(painel, slug, job_id) {
  const status = painel.querySelector(".cenas-rodape-status");
  const rodape = painel.querySelector(".cenas-rodape");
  const trava = [...painel.querySelectorAll("button")];
  trava.forEach((b) => (b.disabled = true));
  const intervalo = setInterval(async () => {
    const job = await fetch(`/api/jobs/${job_id}`).then((r) => r.json()).catch(() => null);
    if (!job || typeof job.progresso !== "number") return;
    status.textContent = textoDeProgresso(job);
    atualizarMiniBarra(rodape.parentElement, job.progresso);
    if (job.status !== "pronto" && job.status !== "erro") return;
    clearInterval(intervalo);
    removerMiniBarra(rodape.parentElement);
    trava.forEach((b) => (b.disabled = false));
    if (job.status === "erro") {
      status.textContent = `Deu erro: ${job.erro}`;
      return;
    }
    painel.dataset.carregado = ""; // recarrega as cenas já na nova estrutura
    painel.classList.remove("aberto");
    await carregarFila(true);
    alternarPainelCenas({ dataset: { slug }, textContent: "" });
  }, 1200);
}

function haAlteracoesNaoSalvas(painel) {
  return contarEdicoesDeTexto(painel) || temposAlterados(painel);
}

async function enviarEstruturaDeCenas(painel, slug, campos) {
  const corpo = new FormData();
  Object.entries(campos).forEach(([k, v]) => corpo.set(k, v));
  const status = painel.querySelector(".cenas-rodape-status");
  status.textContent = "Enviando…";
  const { job_id, erro } = await fetch(`/api/videos/${slug}/cenas/estrutura`, { method: "POST", body: corpo }).then((r) => r.json());
  if (erro) {
    status.textContent = `Deu erro: ${erro}`;
    return;
  }
  acompanharEdicaoDeCenas(painel, slug, job_id);
}

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
  if (!confirm(`Salvar ${n} texto(s)? Só a fala dessas cenas é narrada de novo (as outras falas, imagens e vídeos ficam como estão). A publicação precisará ser confirmada de novo.`)) return;
  enviarEstruturaDeCenas(painel, slug, { operacao: "substituir", edicoes: JSON.stringify(edicoes) });
}

// ---------------- excluir cena (sempre com confirmação) ----------------

document.addEventListener("click", (ev) => {
  const botao = ev.target.closest(".btn-excluir-cena");
  if (!botao) return;
  const painel = botao.closest(".cenas-painel");
  const card = botao.closest(".cena-card");
  if (painel.querySelectorAll(".cena-card").length < 2) {
    alert("O vídeo precisa de pelo menos uma cena.");
    return;
  }
  if (haAlteracoesNaoSalvas(painel) && !confirm("Tem textos/tempos editados ainda não salvos; eles serão descartados. Continuar?")) return;
  const trecho = card.querySelector(".cena-card-texto").textContent.trim().slice(0, 70);
  if (!confirm(`Excluir a cena ${parseInt(card.dataset.indice, 10) + 1} ("${trecho}…")? A fala dela também sai do vídeo e as cenas seguintes andam pra frente.`)) return;
  enviarEstruturaDeCenas(painel, painel.dataset.slug, { operacao: "remover", indice: card.dataset.indice });
});

// ---------------- adicionar cena (nova ou padrão) ----------------

document.addEventListener("click", async (ev) => {
  const botao = ev.target.closest(".btn-nova-cena, .btn-cena-padrao");
  if (!botao) return;
  const painel = botao.closest(".cenas-painel");
  const slug = painel.dataset.slug;
  const padrao = botao.classList.contains("btn-cena-padrao");
  const form = painel.querySelector(".form-nova-cena");
  const n = painel.querySelectorAll(".cena-card").length;
  let presets = [];
  if (padrao) {
    presets = (await fetch("/api/cenas-padrao").then((r) => r.json()).catch(() => ({ cenas: [] }))).cenas || [];
    if (!presets.length) {
      form.hidden = false;
      form.innerHTML = '<div class="cenas-status">Nenhuma cena padrão ainda. Crie na aba Base → Cenas padrão.</div>';
      return;
    }
  }
  const posicoes = [`<option value="${n}">No fim do vídeo</option>`, '<option value="0">No começo</option>']
    .concat(Array.from({ length: n - 1 }, (_, k) => `<option value="${k + 1}">Depois da cena ${k + 1}</option>`)).join("");
  form.hidden = false;
  form.innerHTML = `
    <div class="form-nova-cena-corpo">
      <strong>${padrao ? "Adicionar cena padrão" : "Adicionar cena nova"}</strong>
      ${padrao ? `<label><span>Qual cena padrão</span><select class="nc-preset">${presets.map((p, i) => `<option value="${i}">${escaparAttr(p.nome)}</option>`).join("")}</select></label>` : ""}
      <label><span>Texto que a IA vai narrar nessa cena</span><textarea class="nc-texto" rows="3" placeholder="Ex.: Gostou? Então se inscreva no canal e deixe o seu like!"></textarea></label>
      <div class="video-meta nc-tempo">sem texto</div>
      ${padrao ? '<div class="video-meta nc-midia"></div>' : '<label><span>Imagem da cena (opcional): descreva o que quer ver</span><input type="text" class="nc-descricao" maxlength="300" placeholder="Se deixar vazio, a imagem é feita a partir do texto"></label>'}
      <label><span>Onde entra</span><select class="nc-posicao">${posicoes}</select></label>
      <div class="cena-card-acoes"><button type="button" class="btn-primary nc-adicionar">Adicionar cena</button><button type="button" class="btn-secondary nc-cancelar">Cancelar</button></div>
    </div>`;
  const texto = form.querySelector(".nc-texto");
  const atualizar = () => { form.querySelector(".nc-tempo").textContent = formatarNarracao(texto.value); };
  const escolherPreset = () => {
    const p = presets[parseInt(form.querySelector(".nc-preset").value, 10)];
    texto.value = p.texto;
    form.querySelector(".nc-midia").textContent = p.midia_nome ? `${p.midia_tipo === "video" ? "Vídeo" : "Imagem"} da Base: ${p.midia_nome}` : "Sem imagem definida: a imagem será feita a partir do texto.";
    atualizar();
  };
  texto.addEventListener("input", atualizar);
  if (padrao) {
    form.querySelector(".nc-preset").addEventListener("change", escolherPreset);
    escolherPreset();
  }
  form.querySelector(".nc-cancelar").addEventListener("click", () => { form.hidden = true; form.innerHTML = ""; });
  form.querySelector(".nc-adicionar").addEventListener("click", () => {
    if (texto.value.trim().length < 3) { texto.focus(); return; }
    if (haAlteracoesNaoSalvas(painel) && !confirm("Tem textos/tempos editados ainda não salvos; eles serão descartados. Continuar?")) return;
    const p = padrao ? presets[parseInt(form.querySelector(".nc-preset").value, 10)] : null;
    form.hidden = true;
    enviarEstruturaDeCenas(painel, slug, {
      operacao: "adicionar", posicao: form.querySelector(".nc-posicao").value, texto: texto.value.trim(),
      descricao_imagem: padrao ? "" : form.querySelector(".nc-descricao").value,
      midia_tipo: p?.midia_tipo || "", midia_nome: p?.midia_nome || "",
    });
  });
  texto.focus();
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


// ---------------- minimizar a edição (barra sob a linha do vídeo) ----------------

const TITULOS_PAINEIS = { "cenas-painel": "Editando cenas e roteiro", "legenda-painel": "Editando legenda e transição", "thumb-painel": "Editando thumbnails" };

function atualizarBarrasDePaineis() {
  document.querySelectorAll(".painel-barra").forEach((barra) => {
    const aberto = document.querySelector(`.cenas-painel.aberto[data-slug="${barra.dataset.slug}"], .legenda-painel.aberto[data-slug="${barra.dataset.slug}"], .thumb-painel.aberto[data-slug="${barra.dataset.slug}"]`);
    if (barra.hidden !== !aberto) barra.hidden = !aberto;
    const alvoTitulo = barra.querySelector(".painel-barra-titulo");
    const titulo = aberto ? TITULOS_PAINEIS[[...aberto.classList].find((c) => TITULOS_PAINEIS[c])] || "Editando" : "";
    if (alvoTitulo.textContent !== titulo) alvoTitulo.textContent = titulo; // só escreve se mudou (senão o observador se dispara sem parar)
  });
}

// a barra reage sozinha a qualquer painel que abra ou feche (menu, "Concluir e fechar", minimizar...)
new MutationObserver(atualizarBarrasDePaineis).observe(document.getElementById("fila-lista"), { subtree: true, attributes: true, attributeFilter: ["class"] });

document.addEventListener("click", (ev) => {
  const botao = ev.target.closest(".btn-minimizar-painel");
  if (!botao) return;
  const slug = botao.closest(".painel-barra").dataset.slug;
  for (const painel of document.querySelectorAll(`.cenas-painel.aberto[data-slug="${slug}"], .legenda-painel.aberto[data-slug="${slug}"], .thumb-painel.aberto[data-slug="${slug}"]`)) {
    if (painel.classList.contains("cenas-painel")) {
      if ((contarEdicoesDeTexto(painel) || temposAlterados(painel)) && !confirm("Tem alterações nas cenas que ainda não foram salvas. Minimizar mesmo assim (elas serão descartadas)?")) return;
      painel.dataset.carregado = "";
    }
    painel.classList.remove("aberto");
  }
  document.querySelector(`.video-row[data-slug="${slug}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
});

// ---------------- muitos vídeos: confirmar vários de uma vez ----------------

document.addEventListener("click", async (ev) => {
  const botao = ev.target.closest("#btn-confirmar-todos");
  if (!botao) return;
  const alvo = window.pendentesVisiveis || [];
  if (!alvo.length) return;
  if (!confirm(`Confirmar a publicação de ${alvo.length} vídeo(s) de uma vez (${alvo.slice(0, 5).map((v) => `"${v.titulo}"`).join(", ")}${alvo.length > 5 ? "…" : ""})? Só faça isso se já revisou todos: eles serão postados nas datas marcadas.`)) return;
  botao.disabled = true;
  for (const v of alvo) {
    const corpo = new FormData();
    corpo.set("aprovado", "true");
    await fetch(`/api/videos/${v.slug}/aprovacao`, { method: "POST", body: corpo });
  }
  botao.disabled = false;
  carregarFila(true);
});

document.addEventListener("click", (ev) => {
  if (ev.target.closest("#btn-mostrar-mais")) {
    limiteFila += 20;
    aplicarFiltrosFila();
  }
});
