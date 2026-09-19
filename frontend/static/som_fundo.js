// Som de fundo de um vídeo JÁ gerado (Fila → Editar vídeo → Som de fundo): trocar, colocar ou tirar, escolher o volume
// e ouvir um exemplo antes de aplicar. Com áudios da Base, avisa se faltam segundos (juntar outro áudio) ou se vai cortar.

const TIPOS_DE_SOM = [
  ["", "Nenhum (sem som de fundo)"], ["chuva", "Chuva"], ["musica", "Música suave"], ["oceano", "Ondas do mar"],
  ["fogueira", "Fogueira"], ["vento", "Vento"], ["outro", "Outro (descrever)"], ["biblioteca", "Áudios da minha Base"],
];

function fecharEditorDeSom() {
  const janela = document.getElementById("editor-som");
  if (!janela) return;
  janela.querySelectorAll("audio").forEach((a) => a.pause());
  janela.remove();
}

function minSegSom(s) {
  s = Math.max(0, Math.round(s));
  return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
}

async function abrirEditorDeSom(slug) {
  fecharEditorDeSom();
  const [dados, base] = await Promise.all([
    fetch(`/api/videos/${slug}/som-fundo`).then((r) => r.json()).catch(() => ({ erro: "Sem conexão." })),
    fetch(`/api/biblioteca?canal=${encodeURIComponent(document.querySelector(`.cenas-painel[data-slug="${slug}"]`)?.dataset.canal || "")}`).then((r) => r.json()).catch(() => ({ audios: [] })),
  ]);
  if (dados.erro) { alert(dados.erro); return; }
  if (dados.publicado) { alert("Esse vídeo já foi publicado: não dá mais para trocar o som de fundo."); return; }
  const audios = base.audios_info || [];
  const duracaoDe = (nome) => (audios.find((a) => a.nome === nome)?.duracao_segundos) || 0;
  let lista = (dados.playlist || []).map((i) => ({ nome: i.nome, segundos: i.segundos || "" }));
  const opcoes = { repetir: "repetir", suave: true, fade: true, ...(dados.opcoes || {}) };

  document.body.insertAdjacentHTML("beforeend", `
    <div id="editor-som" class="previa-cena">
      <div class="previa-caixa editor-textos-caixa">
        <div class="previa-topo"><strong>Som de fundo</strong><button type="button" class="previa-fechar es-fechar" aria-label="Fechar">✕</button></div>
        <div class="video-meta">Vale só para este vídeo (${minSegSom(dados.duracao_video)}). Refaz o áudio final e remonta o vídeo, sem mexer em roteiro, narração nem imagens. A publicação precisa ser confirmada de novo.</div>
        <label class="et-campo"><span>Som de fundo</span><select class="es-tipo">${TIPOS_DE_SOM.map(([v, r]) => `<option value="${v}"${dados.tipo === v ? " selected" : ""}>${r}</option>`).join("")}</select></label>
        <label class="et-campo es-linha-outro" hidden><span>Descreva o som que quer</span><input type="text" class="es-descricao" maxlength="200" value="${escaparAttr(dados.descricao || "")}" placeholder="Ex.: floresta com pássaros"></label>
        <div class="es-bloco-base" hidden>
          <div class="es-itens"></div>
          <button type="button" class="btn-secondary btn-compacto es-juntar">+ Juntar outro áudio</button>
          <div class="es-resumo video-meta"></div>
          <div class="et-linha">
            <label class="et-campo"><span>Se faltar áudio para o vídeo todo</span><select class="es-repetir"><option value="repetir">Repetir os áudios em ciclo</option><option value="silencio">Terminar em silêncio</option></select></label>
            <div>
              <label class="checkbox-row"><input type="checkbox" class="es-suave"><span>Transição suave entre os áudios (2 s)</span></label>
              <label class="checkbox-row"><input type="checkbox" class="es-fade"><span>Sumir aos poucos no fim do vídeo</span></label>
            </div>
          </div>
        </div>
        <div class="es-bloco-volume">
          <label class="et-campo"><span>Volume do som de fundo: <b class="es-volume-rotulo"></b> <em>(o padrão é 20%; a narração fica sempre no volume normal)</em></span>
            <input type="range" class="es-volume" min="0" max="100" step="1" value="${Math.round((dados.volume ?? 0.2) * 100)}"></label>
          <div class="cena-card-acoes"><button type="button" class="btn-secondary es-ouvir">▶ Ouvir exemplo (12 s)</button><span class="video-meta es-ouvir-status"></span></div>
          <audio class="es-audio" controls hidden></audio>
        </div>
        <div class="cena-card-acoes">
          <button type="button" class="btn-primary es-aplicar">Aplicar ao vídeo</button>
          <button type="button" class="btn-secondary es-fechar">Cancelar</button>
          <span class="video-meta es-status"></span>
        </div>
      </div>
    </div>`);

  const janela = document.getElementById("editor-som");
  const q = (s) => janela.querySelector(s);
  q(".es-repetir").value = opcoes.repetir === "silencio" ? "silencio" : "repetir";
  q(".es-suave").checked = !!opcoes.suave;
  q(".es-fade").checked = !!opcoes.fade;

  const desenharItens = () => {
    q(".es-itens").innerHTML = lista.map((it, i) => `
      <div class="som-tempo-linha" data-i="${i}">
        <select class="es-audio-escolha">${audios.map((a) => `<option value="${escaparAttr(a.nome)}"${a.nome === it.nome ? " selected" : ""}>${escaparAttr(a.descricao || a.nome)} (${minSegSom(a.duracao_segundos || 0)})</option>`).join("")}</select>
        <span>tocar</span> <input type="number" class="es-seg" min="1" step="1" value="${it.segundos || ""}" placeholder="tudo"> <span>s</span>
        ${lista.length > 1 ? '<button type="button" class="btn-regenerar btn-regenerar-sutil es-tirar">✕</button>' : ""}
      </div>`).join("");
    q(".es-itens").querySelectorAll(".som-tempo-linha").forEach((linha) => {
      const i = parseInt(linha.dataset.i, 10);
      linha.querySelector(".es-audio-escolha").addEventListener("change", (ev) => { lista[i].nome = ev.target.value; resumir(); });
      linha.querySelector(".es-seg").addEventListener("input", (ev) => { lista[i].segundos = ev.target.value ? parseInt(ev.target.value, 10) : ""; resumir(); });
      const tirar = linha.querySelector(".es-tirar");
      if (tirar) tirar.addEventListener("click", () => { lista.splice(i, 1); desenharItens(); resumir(); });
    });
  };

  const resumir = () => {
    const resumo = q(".es-resumo");
    resumo.classList.remove("es-aviso");
    if (!audios.length) { resumo.textContent = "Você ainda não importou áudios na aba Base."; return; }
    const video = dados.duracao_video || 0;
    const suave = q(".es-suave").checked;
    const total = lista.reduce((soma, it, i) => {
      const d = duracaoDe(it.nome);
      return soma + Math.max(1, it.segundos ? Math.min(d, it.segundos) : d) - (i && suave ? 2 : 0);
    }, 0);
    if (total < video - 1) {
      const cicla = q(".es-repetir").value === "repetir";
      resumo.textContent = `Os áudios somam ${minSegSom(total)} e o vídeo tem ${minSegSom(video)}: faltam ${minSegSom(video - total)}. ${cicla ? "Os áudios vão se repetir em ciclo" : "O final vai ficar em silêncio"} — ou junte outro áudio para cobrir.`;
    } else if (total > video + 1) {
      resumo.classList.add("es-aviso");
      resumo.textContent = `⚠ Os áudios somam ${minSegSom(total)} e o vídeo tem ${minSegSom(video)}: os últimos ${minSegSom(total - video)} vão ser cortados.`;
    } else {
      resumo.textContent = `Os áudios cobrem o vídeo (${minSegSom(total)}).`;
    }
  };

  const ajustarTipo = () => {
    const tipo = q(".es-tipo").value;
    q(".es-linha-outro").hidden = tipo !== "outro";
    q(".es-bloco-base").hidden = tipo !== "biblioteca";
    q(".es-bloco-volume").hidden = tipo === "";
    if (tipo === "biblioteca" && !lista.length && audios.length) lista = [{ nome: audios[0].nome, segundos: "" }];
    if (tipo === "biblioteca") { desenharItens(); resumir(); }
  };

  q(".es-tipo").addEventListener("change", ajustarTipo);
  q(".es-juntar").addEventListener("click", () => {
    if (!audios.length) { alert("Importe áudios na aba Base primeiro."); return; }
    const usados = new Set(lista.map((i) => i.nome));
    lista.push({ nome: (audios.find((a) => !usados.has(a.nome)) || audios[0]).nome, segundos: "" });
    desenharItens(); resumir();
  });
  [".es-repetir", ".es-suave", ".es-fade"].forEach((s) => q(s).addEventListener("change", resumir));
  const rotuloVolume = () => { q(".es-volume-rotulo").textContent = `${q(".es-volume").value}%`; };
  q(".es-volume").addEventListener("input", () => { rotuloVolume(); q(".es-ouvir-status").textContent = "Ouça o exemplo de novo para testar esse volume."; });
  rotuloVolume();
  ajustarTipo();

  const corpoDoPedido = () => {
    const corpo = new FormData();
    corpo.set("tipo", q(".es-tipo").value);
    corpo.set("descricao", q(".es-descricao").value);
    corpo.set("playlist", JSON.stringify(lista.map((i) => ({ nome: i.nome, segundos: i.segundos || null }))));
    corpo.set("volume", String(parseInt(q(".es-volume").value, 10) / 100));
    corpo.set("repetir", q(".es-repetir").value);
    corpo.set("suave", q(".es-suave").checked ? "true" : "false");
    corpo.set("fade", q(".es-fade").checked ? "true" : "false");
    return corpo;
  };

  janela.querySelectorAll(".es-fechar").forEach((b) => b.addEventListener("click", fecharEditorDeSom));
  janela.addEventListener("click", (ev) => { if (ev.target === janela) fecharEditorDeSom(); });

  q(".es-ouvir").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    const status = q(".es-ouvir-status");
    botao.disabled = true;
    status.textContent = "Preparando o exemplo…";
    const r = await fetch(`/api/videos/${slug}/som-fundo/previa`, { method: "POST", body: corpoDoPedido() }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
    botao.disabled = false;
    if (r.erro) { status.textContent = r.erro; return; }
    const player = q(".es-audio");
    player.src = r.url;
    player.hidden = false;
    status.textContent = "Começo da narração + o som no volume escolhido.";
    player.play().catch(() => {});
  });

  q(".es-aplicar").addEventListener("click", async (ev) => {
    const botao = ev.currentTarget;
    const status = q(".es-status");
    if (q(".es-tipo").value === "biblioteca" && !lista.length) { status.textContent = "Escolha pelo menos um áudio da Base."; return; }
    botao.disabled = true;
    status.textContent = "Enviando…";
    const r = await fetch(`/api/videos/${slug}/som-fundo`, { method: "POST", body: corpoDoPedido() }).then((x) => x.json()).catch(() => ({ erro: "Sem conexão." }));
    if (r.erro) { status.textContent = `Deu erro: ${r.erro}`; botao.disabled = false; return; }
    const intervalo = setInterval(async () => {
      const job = await fetch(`/api/jobs/${r.job_id}`).then((x) => x.json()).catch(() => null);
      if (!job || typeof job.progresso !== "number") return;
      status.textContent = textoDeProgresso(job);
      if (job.status === "pronto" || job.status === "erro") {
        clearInterval(intervalo);
        if (job.status === "erro") { status.textContent = `Deu erro: ${job.erro}`; botao.disabled = false; return; }
        fecharEditorDeSom();
        carregarFila(true);
      }
    }, 1200);
  });
}

document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharEditorDeSom(); });
