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
  switch (item.dataset.acao) {
    case "cenas": alternarPainelCenas(alvo); break;
    case "legenda": alternarPainelLegenda(alvo); break;
    case "thumb": alternarPainelThumb(alvo); break;
    case "regen-mesmo": confirmarRegenerar(slug, item.dataset.titulo, true); break;
    case "regen-novo": confirmarRegenerar(slug, item.dataset.titulo, false); break;
  }
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
