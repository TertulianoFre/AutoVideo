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
    case "textos": abrirEditorDeTextos(slug); break;
    case "som": abrirEditorDeSom(slug); break;
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

// ---------------- excluir cenas: marca várias e remonta uma vez só ----------------

function cenasMarcadas(painel) {
  return [...painel.querySelectorAll(".cena-card.cena-marcada")];
}

function atualizarMarcadas(painel) {
  const marcadas = cenasMarcadas(painel);
  const botao = painel.querySelector(".btn-excluir-marcadas");
  if (botao) {
    botao.hidden = marcadas.length === 0;
    botao.textContent = marcadas.length === 1 ? "Excluir 1 cena marcada e remontar" : `Excluir ${marcadas.length} cenas marcadas e remontar`;
  }
  recalcularTemposDasCenas(painel); // tempos e total já sem as cenas marcadas
}

document.addEventListener("click", (ev) => {
  const botao = ev.target.closest(".btn-excluir-cena");
  if (!botao) return;
  const painel = botao.closest(".cenas-painel");
  const card = botao.closest(".cena-card");
  const marcando = !card.classList.contains("cena-marcada");
  if (marcando && cenasMarcadas(painel).length + 1 >= painel.querySelectorAll(".cena-card").length) {
    alert("O vídeo precisa ficar com pelo menos uma cena.");
    return;
  }
  card.classList.toggle("cena-marcada", marcando);
  botao.textContent = marcando ? "↺" : "✕";
  botao.title = marcando ? "Desfazer: manter esta cena" : "Marcar esta cena para excluir (nada é apagado até você confirmar)";
  atualizarMarcadas(painel);
});

document.addEventListener("click", (ev) => {
  const botao = ev.target.closest(".btn-excluir-marcadas");
  if (!botao) return;
  const painel = botao.closest(".cenas-painel");
  const marcadas = cenasMarcadas(painel);
  if (!marcadas.length) return;
  if (haAlteracoesNaoSalvas(painel) && !confirm("Tem textos/tempos editados ainda não salvos; eles serão descartados. Continuar?")) return;
  const segundos = marcadas.reduce((soma, c) => soma + parseFloat(c.dataset.duracao || 0), 0);
  const lista = marcadas.map((c) => `Cena ${parseInt(c.dataset.indice, 10) + 1}`).join(", ");
  if (!confirm(`Excluir ${marcadas.length === 1 ? "a" : "as"} ${lista}? Saem ${formatarTempo(segundos)} do vídeo (a fala delas também) e as outras cenas andam pra frente. O vídeo é remontado uma vez só.`)) return;
  enviarEstruturaDeCenas(painel, painel.dataset.slug, { operacao: "remover", indices: marcadas.map((c) => c.dataset.indice).join(",") });
});

// ---------------- adicionar cena (nova ou padrão) ----------------

document.addEventListener("click", (ev) => {
  const inserir = ev.target.closest(".cena-inserir");
  if (inserir) {
    const painel = inserir.closest(".cenas-painel");
    const form = painel.querySelector(".form-nova-cena");
    const posicao = inserir.dataset.posicao;
    inserir.after(form); // o formulário abre logo abaixo do "+" clicado
    form.hidden = false;
    form.innerHTML = `<div class="form-nova-cena-corpo"><strong>Adicionar uma cena aqui</strong><div class="cena-card-acoes">
      <button type="button" class="btn-secondary nc-tipo-nova">Cena nova</button>
      <button type="button" class="btn-secondary nc-tipo-padrao">Cena padrão</button>
      <button type="button" class="btn-secondary nc-cancelar">Cancelar</button></div></div>`;
    form.querySelector(".nc-tipo-nova").addEventListener("click", () => abrirFormularioDeCena(painel, false, posicao));
    form.querySelector(".nc-tipo-padrao").addEventListener("click", () => abrirFormularioDeCena(painel, true, posicao));
    form.querySelector(".nc-cancelar").addEventListener("click", () => { form.hidden = true; form.innerHTML = ""; });
    return;
  }
  const botao = ev.target.closest(".btn-nova-cena, .btn-cena-padrao");
  if (!botao) return;
  const painel = botao.closest(".cenas-painel");
  painel.querySelector(".cenas-adicionar").after(painel.querySelector(".form-nova-cena"));
  abrirFormularioDeCena(painel, botao.classList.contains("btn-cena-padrao"), null);
});

async function abrirFormularioDeCena(painel, padrao, posicaoInicial) {
  const slug = painel.dataset.slug;
  const form = painel.querySelector(".form-nova-cena");
  const n = painel.querySelectorAll(".cena-card").length;
  let presets = [];
  if (padrao) {
    presets = (await fetch(`/api/cenas-padrao?canal=${encodeURIComponent(painel.dataset.canal || "")}`).then((r) => r.json()).catch(() => ({ cenas: [] }))).cenas || [];
    if (!presets.length) {
      form.hidden = false;
      form.innerHTML = '<div class="cenas-status">Nenhuma cena padrão ainda. Crie na aba Base → Cenas padrão.</div>';
      return;
    }
  }
  const dadosBase = padrao ? null : await fetch(`/api/biblioteca?canal=${encodeURIComponent(painel.dataset.canal || "")}`).then((r) => r.json()).catch(() => ({ imagens: [], videos: [] }));
  const opcoesBase = dadosBase
    ? `<option value="|">Nenhuma — a imagem é feita a partir do texto</option>` +
      (dadosBase.imagens || []).map((i) => `<option value="imagem|${escaparAttr(i.nome)}">Imagem: ${escaparAttr(i.descricao || i.nome)}</option>`).join("") +
      (dadosBase.videos || []).map((v) => `<option value="video|${escaparAttr(v.nome)}">Vídeo (${Math.round(v.duracao_segundos || 0)} s): ${escaparAttr(v.descricao || v.nome)}</option>`).join("")
    : "";
  const posicoes = [`<option value="${n}">No fim do vídeo</option>`, '<option value="0">No começo</option>']
    .concat(Array.from({ length: n - 1 }, (_, k) => `<option value="${k + 1}">Depois da cena ${k + 1}</option>`)).join("");
  form.hidden = false;
  form.innerHTML = `
    <div class="form-nova-cena-corpo">
      <strong>${padrao ? "Adicionar cena padrão" : "Adicionar cena nova"}</strong>
      ${padrao ? `<label><span>Qual cena padrão</span><select class="nc-preset">${presets.map((p, i) => `<option value="${i}">${escaparAttr(p.nome)}</option>`).join("")}</select></label>` : ""}
      <label class="nc-linha-texto"><span>Texto que a IA vai narrar nessa cena</span><textarea class="nc-texto" rows="3" placeholder="Ex.: Gostou? Então se inscreva no canal e deixe o seu like!"></textarea></label>
      <div class="video-meta nc-tempo">sem texto</div>
      ${padrao ? '<div class="video-meta nc-midia"></div>' : `
        <label><span>Imagem ou vídeo da cena (opcional)</span><select class="nc-base">${opcoesBase}</select></label>
        <div class="nc-envio"><label class="btn-secondary btn-compacto" style="cursor:pointer">Ou enviar do computador<input type="file" class="nc-arquivo" accept="image/*,video/*" hidden></label><span class="video-meta nc-arquivo-nome"></span></div>
        <label class="nc-linha-descricao"><span>Sem imagem escolhida? Descreva o que quer ver</span><input type="text" class="nc-descricao" maxlength="300" placeholder="Se deixar vazio, a imagem é feita a partir do texto"></label>`}
      <label class="nc-ajuste" hidden><span>O vídeo é maior que a fala. O que fazer?</span><select class="nc-ajustar"><option value="1">Esticar a cena até o fim do vídeo (a fala termina e o vídeo continua)</option><option value="">Cortar o vídeo quando a fala terminar</option></select></label>
      <label><span>Onde entra</span><select class="nc-posicao">${posicoes}</select></label>
      <div class="cena-card-acoes"><button type="button" class="btn-primary nc-adicionar">Adicionar cena</button><button type="button" class="btn-secondary nc-cancelar">Cancelar</button></div>
    </div>`;
  const texto = form.querySelector(".nc-texto");
  let midia = { tipo: "", nome: "", dur: 0, arquivo: null };
  let comAudioDoVideoAtual = false;
  const atualizar = () => {
    const tempo = form.querySelector(".nc-tempo");
    const ajuste = form.querySelector(".nc-ajuste");
    if (comAudioDoVideoAtual) { ajuste.hidden = true; return; }
    const fala = estimarNarracao(texto.value).segundos;
    let msg = formatarNarracao(texto.value);
    let mostrarAjuste = false;
    if (midia.tipo === "video" && midia.dur > 0 && fala > 0) {
      const dv = Math.round(midia.dur * 10) / 10;
      if (midia.dur > fala + 0.3) {
        mostrarAjuste = true;
        const esticar = form.querySelector(".nc-ajustar").value === "1";
        msg += ` · vídeo de ${dv} s, maior que a fala → a cena vai durar ${esticar ? dv : Math.round(fala * 10) / 10} s${esticar ? "" : " (o resto do vídeo é cortado)"}`;
      } else if (midia.dur < fala - 0.3) {
        msg += ` · vídeo de ${dv} s, menor que a fala → ele se repete até a fala acabar (a cena dura ≈ ${Math.round(fala * 10) / 10} s)`;
      } else {
        msg += ` · vídeo de ${dv} s, do tamanho da fala`;
      }
    } else if (midia.tipo === "video" && midia.dur > 0) {
      msg += ` · vídeo de ${Math.round(midia.dur * 10) / 10} s (escreva o texto para calcular a cena)`;
    }
    tempo.textContent = msg;
    ajuste.hidden = !mostrarAjuste;
  };
  if (!padrao) {
    const seletorBase = form.querySelector(".nc-base");
    const linhaDescricao = form.querySelector(".nc-linha-descricao");
    seletorBase.addEventListener("change", () => {
      const [tipo, nome] = seletorBase.value.split("|");
      const v = tipo === "video" ? (dadosBase.videos || []).find((x) => x.nome === nome) : null;
      midia = { tipo, nome, dur: v ? v.duracao_segundos || 0 : 0, arquivo: null };
      form.querySelector(".nc-arquivo").value = "";
      form.querySelector(".nc-arquivo-nome").textContent = "";
      linhaDescricao.hidden = !!tipo;
      atualizar();
    });
    form.querySelector(".nc-arquivo").addEventListener("change", (ev) => {
      const arquivo = ev.target.files[0];
      if (!arquivo) return;
      const ehVideo = arquivo.type.startsWith("video");
      midia = { tipo: ehVideo ? "video" : "imagem", nome: "", dur: 0, arquivo };
      seletorBase.value = "|";
      linhaDescricao.hidden = true;
      form.querySelector(".nc-arquivo-nome").textContent = `${arquivo.name} (vai para a Base)`;
      if (ehVideo) {
        const v = document.createElement("video");
        v.preload = "metadata";
        v.onloadedmetadata = () => { midia.dur = v.duration || 0; URL.revokeObjectURL(v.src); atualizar(); };
        v.src = URL.createObjectURL(arquivo);
      }
      atualizar();
    });
    form.querySelector(".nc-ajustar").addEventListener("change", atualizar);
  }
  const escolherPreset = () => {
    const p = presets[parseInt(form.querySelector(".nc-preset").value, 10)];
    texto.value = p.texto;
    if (posicaoInicial === null) form.querySelector(".nc-posicao").value = p.posicao_padrao === "inicio" ? "0" : String(n); // introdução vai pro começo, o resto pro fim
    form.querySelector(".nc-midia").textContent = p.midia_nome ? `${p.midia_tipo === "video" ? "Vídeo" : "Imagem"} da Base: ${p.midia_nome}` : "Sem imagem definida: a imagem será feita a partir do texto.";
    form.querySelector(".nc-linha-texto").hidden = !!p.usar_audio_video;
    comAudioDoVideoAtual = !!p.usar_audio_video;
    midia = { tipo: p.midia_tipo || "", nome: p.midia_nome || "", dur: p.duracao_segundos || 0, arquivo: null };
    form.querySelector(".nc-ajustar").addEventListener("change", atualizar);
    if (p.usar_audio_video) form.querySelector(".nc-tempo").textContent = `Usa o áudio do próprio vídeo · a cena dura ${Math.round((p.duracao_segundos || 0) * 10) / 10} s (o tempo do vídeo)`;
    else atualizar();
  };
  texto.addEventListener("input", atualizar);
  if (posicaoInicial !== null) form.querySelector(".nc-posicao").value = String(posicaoInicial);
  if (padrao) {
    form.querySelector(".nc-preset").addEventListener("change", escolherPreset);
    escolherPreset();
  }
  form.querySelector(".nc-cancelar").addEventListener("click", () => { form.hidden = true; form.innerHTML = ""; });
  form.querySelector(".nc-adicionar").addEventListener("click", async () => {
    const p = padrao ? presets[parseInt(form.querySelector(".nc-preset").value, 10)] : null;
    const comAudioDoVideo = !!(p && p.usar_audio_video);
    if (!comAudioDoVideo && texto.value.trim().length < 3) { texto.focus(); return; }
    if (haAlteracoesNaoSalvas(painel) && !confirm("Tem textos/tempos editados ainda não salvos; eles serão descartados. Continuar?")) return;
    let tipo = p?.midia_tipo || midia.tipo || "";
    let nome = p?.midia_nome || midia.nome || "";
    if (!padrao && midia.arquivo) {
      const botao = form.querySelector(".nc-adicionar");
      botao.disabled = true;
      botao.textContent = "Enviando o arquivo…";
      const corpo = new FormData();
      corpo.set("arquivo", midia.arquivo);
      const r = await fetch(`/api/biblioteca/${midia.tipo === "video" ? "videos" : "imagens"}/upload`, { method: "POST", body: corpo }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
      botao.disabled = false;
      botao.textContent = "Adicionar cena";
      if (r.erro) { alert(r.erro); return; }
      nome = r.nome;
    }
    const ajusteVisivel = !form.querySelector(".nc-ajuste").hidden;
    form.hidden = true;
    enviarEstruturaDeCenas(painel, slug, {
      operacao: "adicionar", posicao: form.querySelector(".nc-posicao").value, texto: comAudioDoVideo ? "" : texto.value.trim(), audio_do_video: comAudioDoVideo ? "1" : "",
      descricao_imagem: padrao || tipo ? "" : form.querySelector(".nc-descricao").value,
      midia_tipo: tipo, midia_nome: nome,
      ajustar_ao_video: tipo === "video" && !comAudioDoVideo && ajusteVisivel ? form.querySelector(".nc-ajustar").value : "",
    });
  });
  texto.focus();
}

// ---------------- tempo de cada cena (só aumenta; as seguintes andam pra frente) ----------------

function temposAlterados(painel) {
  return [...painel.querySelectorAll(".cena-duracao")].some((i) => Math.abs((parseFloat(i.value) || 0) - parseFloat(i.dataset.original)) > 0.05);
}

function recalcularTemposDasCenas(painel) {
  let acumulado = 0;
  painel.querySelectorAll(".cena-card").forEach((card) => {
    const campo = card.querySelector(".cena-duracao");
    const dur = campo ? Math.max(parseFloat(campo.value) || 0, parseFloat(campo.dataset.minimo)) : parseFloat(card.dataset.duracao || 0);
    if (card.classList.contains("cena-marcada")) {  // vai ser excluída: não conta no tempo
      const rot = card.querySelector(".cena-card-tempo");
      if (rot) rot.textContent = "será excluída";
      return;
    }
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
  atualizarLinhaDoTempo(painel);
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
  document.querySelector(`#fila-lista .video-row[data-slug="${slug}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
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

// lápis pequeno ao lado de "Gerar outra imagem": abre/fecha o campo de descrição da imagem
document.addEventListener("click", (ev) => {
  const lapis = ev.target.closest(".btn-lapis-desc");
  if (!lapis) return;
  const campo = lapis.closest(".cena-card").querySelector(".cena-descricao");
  campo.hidden = !campo.hidden;
  lapis.classList.toggle("aberto", !campo.hidden);
  if (!campo.hidden) campo.focus();
});


// ---------------- pré-visualizar a cena (clique na imagem) ----------------

function fecharPreviaDaCena() {
  const janela = document.getElementById("previa-cena");
  if (!janela) return;
  janela.querySelectorAll("video").forEach((v) => v.pause());
  janela.remove();
}

document.addEventListener("click", (ev) => {
  if (ev.target.closest("#previa-cena .previa-fechar") || ev.target.id === "previa-cena") {
    fecharPreviaDaCena();
    return;
  }
  const imagem = ev.target.closest(".cena-card .cena-img, .cena-card .cena-img-vazia");
  if (!imagem) return;
  const card = imagem.closest(".cena-card");
  const video = card.dataset.videoBase;
  const titulo = `Cena ${parseInt(card.dataset.indice, 10) + 1}`;
  const corpo = video
    ? `<video controls autoplay src="/biblioteca/videos/${encodeURIComponent(video)}"></video><div class="video-meta">Vídeo original da Base (com o som dele). No vídeo final ele é cortado para caber no formato.</div>`
    : `<div class="previa-imagens">${card.dataset.img16 ? `<img src="${card.dataset.img16}" alt="">` : ""}${card.dataset.img9 ? `<img class="previa-vertical" src="${card.dataset.img9}" alt="">` : ""}</div>`;
  fecharPreviaDaCena();
  document.body.insertAdjacentHTML("beforeend", `<div id="previa-cena" class="previa-cena"><div class="previa-caixa"><div class="previa-topo"><strong>${titulo}</strong><button type="button" class="previa-fechar" aria-label="Fechar">✕</button></div>${corpo}</div></div>`);
});

document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharPreviaDaCena(); });


// ---------------- linha do tempo das cenas ----------------

function atualizarLinhaDoTempo(painel) {
  const faixa = painel.querySelector(".linha-tempo");
  if (!faixa) return;
  const cartoes = [...painel.querySelectorAll(".cena-card")];
  let acumulado = 0;
  faixa.innerHTML = cartoes.map((card, i) => {
    const campo = card.querySelector(".cena-duracao");
    const dur = campo ? Math.max(parseFloat(campo.value) || 0, parseFloat(campo.dataset.minimo) || 0) : parseFloat(card.dataset.duracao || 0);
    const inicio = acumulado;
    const marcada = card.classList.contains("cena-marcada");
    if (!marcada) acumulado += dur;
    const texto = (card.querySelector(".cena-card-texto")?.textContent || "").trim();
    const comVideo = card.classList.contains("cena-audio-video");
    const vazia = !texto && !comVideo;
    const capa = card.dataset.img16 ? `background-image:url('${card.dataset.img16}')` : "";
    const classe = `lt-bloco${comVideo ? " lt-video" : ""}${vazia ? " lt-vazia" : ""}${marcada ? " lt-marcada" : ""}`;
    const dica = comVideo ? "Vídeo com o áudio dele" : vazia ? "Cena vazia (sem texto)" : texto.slice(0, 90);
    return `<div class="lt-item" style="flex:${Math.max(dur, 0.5)} 1 0px" data-indice="${card.dataset.indice}">
      <div class="${classe}" style="${capa}" title="${escaparAttr(`Cena ${i + 1} · ${dica}`)}"><span class="lt-rotulo">${comVideo ? "🎬 " : ""}${i + 1} · ${Math.round(dur * 10) / 10}s</span></div>
      <span class="lt-tempo">${marcada ? "excluir" : formatarTempo(inicio)}</span></div>`;
  }).join("");
  const cabeca = painel.querySelector(".lt-cabeca");
  if (cabeca) cabeca.textContent = `Linha do tempo · ${cartoes.length} cena(s) · total ${formatarTempo(acumulado)} (clique numa cena para ir até ela)`;
}

document.addEventListener("click", (ev) => {
  const item = ev.target.closest(".lt-item");
  if (!item) return;
  const painel = item.closest(".cenas-painel");
  const card = painel.querySelector(`.cena-card[data-indice="${item.dataset.indice}"]`);
  if (!card) return;
  card.scrollIntoView({ block: "center", behavior: "smooth" });
  card.classList.add("cena-destaque");
  setTimeout(() => card.classList.remove("cena-destaque"), 1600);
});


// ---------------- título e descrição do vídeo (só antes de publicar) ----------------

function fecharEditorDeTextos() {
  document.getElementById("editor-textos")?.remove();
}

async function abrirEditorDeTextos(slug) {
  fecharEditorDeTextos();
  const dados = await fetch(`/api/videos/${slug}/textos`).then((r) => r.json()).catch(() => ({ erro: "Sem conexão." }));
  if (dados.erro) {
    alert(dados.erro);
    return;
  }
  const bloqueado = !!dados.publicado;
  document.body.insertAdjacentHTML("beforeend", `
    <div id="editor-textos" class="previa-cena">
      <div class="previa-caixa editor-textos-caixa">
        <div class="previa-topo"><strong>Título, descrição e agendamento</strong><button type="button" class="previa-fechar et-fechar" aria-label="Fechar">✕</button></div>
        ${bloqueado ? '<div class="video-meta">Esse vídeo já foi publicado: não dá mais para trocar o título aqui.</div>' : '<div class="video-meta">O texto fica exatamente como você escrever (letras maiúsculas e minúsculas incluídas). Mudar título, descrição ou visibilidade exige confirmar a publicação de novo; só reagendar não.</div>'}
        <div class="et-linha">
          <label class="et-campo"><span>Data de postagem</span><input type="date" class="et-data" value="${escaparAttr(dados.data_postagem || "")}"${bloqueado ? " disabled" : ""}></label>
          <label class="et-campo"><span>Hora (vazio = assim que possível)</span><input type="time" class="et-hora" value="${escaparAttr(dados.hora_postagem || "")}"${bloqueado ? " disabled" : ""}></label>
          <label class="et-campo"><span>Visibilidade no YouTube</span><select class="et-privacidade"${bloqueado ? " disabled" : ""}>
            <option value="public"${dados.privacidade === "public" ? " selected" : ""}>Público</option>
            <option value="unlisted"${dados.privacidade === "unlisted" ? " selected" : ""}>Não listado (só com o link)</option>
            <option value="private"${dados.privacidade === "private" ? " selected" : ""}>Privado (só você vê)</option>
          </select></label>
        </div>
        ${bloqueado ? "" : '<div class="et-atalhos"><button type="button" class="btn-secondary btn-compacto et-hoje">Hoje</button><button type="button" class="btn-secondary btn-compacto et-amanha">Amanhã</button><span class="video-meta et-aviso-data"></span></div>'}
        <label class="et-campo"><span>Título (aparece no YouTube)</span><input type="text" class="et-titulo" maxlength="100" value="${escaparAttr(dados.titulo)}"${bloqueado ? " readonly" : ""}></label>
        <label class="et-campo"><span>Descrição do YouTube <em class="et-contagem"></em></span><textarea class="et-descricao" rows="10" maxlength="5000" placeholder="Ainda não tem descrição. Escreva ou peça para a IA escrever."${bloqueado ? " readonly" : ""}>${escaparAttr(dados.descricao_youtube)}</textarea></label>
        ${!bloqueado && dados.hashtags_automaticas ? `<div class="video-meta">As hashtags entram sozinhas na hora de publicar (você não precisa escrever). Vão no fim da descrição: <b>${escaparAttr(dados.hashtags_automaticas)}</b></div>` : ""}
        <div class="cena-card-acoes">
          ${bloqueado ? "" : '<button type="button" class="btn-primary et-salvar">Salvar</button><button type="button" class="btn-secondary et-ia">Escrever descrição com a IA</button>'}
          <button type="button" class="btn-secondary et-fechar">${bloqueado ? "Fechar" : "Cancelar"}</button>
          <span class="video-meta et-status"></span>
        </div>
      </div>
    </div>`);
  const janela = document.getElementById("editor-textos");
  const descricao = janela.querySelector(".et-descricao");
  const dataLocal = (deslocamento) => {
    const d = new Date();
    d.setDate(d.getDate() + deslocamento);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const avisarData = () => {
    const aviso = janela.querySelector(".et-aviso-data");
    if (!aviso) return;
    const dia = janela.querySelector(".et-data").value;
    aviso.textContent = dia && dia < dataLocal(0) ? "Essa data já passou: escolha uma data de hoje em diante para reagendar." : "";
  };
  const contar = () => { janela.querySelector(".et-contagem").textContent = `(${descricao.value.length}/5000)`; };
  contar();
  descricao.addEventListener("input", contar);
  janela.querySelectorAll(".et-fechar").forEach((b) => b.addEventListener("click", fecharEditorDeTextos));
  janela.addEventListener("click", (ev) => { if (ev.target === janela) fecharEditorDeTextos(); });
  if (bloqueado) return;
  janela.querySelector(".et-data").addEventListener("input", avisarData);
  janela.querySelector(".et-hoje").addEventListener("click", () => { janela.querySelector(".et-data").value = dataLocal(0); avisarData(); });
  janela.querySelector(".et-amanha").addEventListener("click", () => { janela.querySelector(".et-data").value = dataLocal(1); avisarData(); });
  avisarData();
  const status = janela.querySelector(".et-status");
  janela.querySelector(".et-ia").addEventListener("click", async (ev) => {
    if (descricao.value.trim() && !confirm("Substituir a descrição atual pela que a IA escrever? (Só aparece aqui: você ainda decide se salva.)")) return;
    const botao = ev.currentTarget;
    botao.disabled = true;
    status.textContent = "A IA está escrevendo…";
    const corpo = new FormData();
    corpo.set("titulo", janela.querySelector(".et-titulo").value);
    const r = await fetch(`/api/videos/${slug}/textos/descricao-ia`, { method: "POST", body: corpo }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
    botao.disabled = false;
    if (r.erro) { status.textContent = r.erro; return; }
    descricao.value = r.descricao;
    contar();
    status.textContent = "Pronto. Revise e clique em Salvar.";
  });
  janela.querySelector(".et-salvar").addEventListener("click", async (ev) => {
    const titulo = janela.querySelector(".et-titulo").value;
    if (!titulo.trim()) { status.textContent = "O título não pode ficar vazio."; return; }
    ev.currentTarget.disabled = true;
    const corpo = new FormData();
    corpo.set("titulo", titulo);
    corpo.set("descricao_youtube", descricao.value);
    if (!janela.querySelector(".et-data").value) { status.textContent = "Escolha a data de postagem."; ev.currentTarget.disabled = false; return; }
    corpo.set("data_postagem", janela.querySelector(".et-data").value);
    corpo.set("hora_postagem", janela.querySelector(".et-hora").value);
    corpo.set("privacidade", janela.querySelector(".et-privacidade").value);
    const r = await fetch(`/api/videos/${slug}/textos`, { method: "POST", body: corpo }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
    if (r.erro) { status.textContent = r.erro; ev.currentTarget.disabled = false; return; }
    fecharEditorDeTextos();
    carregarFila(true);
  });
}

document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharEditorDeTextos(); });
