// Sequência de mídias da Base (imagens e vídeos): escolher, ordenar (↑ ↓), remover e descrever cada uma.
// Usada no Novo vídeo (mídias das cenas) e no cartão do Agente (roteiro a partir das imagens).
// A IA gratuita de texto não enxerga imagens: quem "conta" o que aparece em cada uma é a descrição escrita aqui
// (ela fica salva na Base), e o roteiro é escrito seguindo essas descrições, na ordem da sequência.

function chaveDe(it) {
  return `${it.tipo}:${it.nome}`;
}

async function montarSequencia(cfg) {
  const { grade, strip, campo, lista, aoMudar } = cfg;
  if (!grade) return;
  const dados = await fetch(`/api/biblioteca?canal=${encodeURIComponent(seletorCanal.value || "")}`).then((r) => r.json());
  const itens = [
    ...(dados.imagens || []).map((i) => ({ ...i, tipo: "imagem" })),
    ...(dados.videos || []).map((v) => ({ ...v, tipo: "video" })),
  ];
  for (let i = lista.length - 1; i >= 0; i--) if (!itens.some((it) => chaveDe(it) === lista[i])) lista.splice(i, 1); // sumiu da Base

  const miniatura = (it) => (it.tipo === "video" ? `<video src="${it.url}#t=0.5" muted preload="metadata"></video>` : `<img src="${it.url}" alt="">`);

  const desenhar = () => {
    if (campo) campo.value = lista.join("|");
    grade.innerHTML = itens.length
      ? itens.map((it) => {
          const ordem = lista.indexOf(chaveDe(it));
          const dica = `${it.nome}${it.descricao ? " — " + it.descricao : ""}${it.usado_em.length ? " — já usado em: " + it.usado_em.join(", ") : ""}`;
          return `<div class="base-opcao"><button type="button" class="thumb-img-opcao${ordem >= 0 ? " selecionada" : ""}" data-chave="${escaparAttr(chaveDe(it))}" title="${escaparAttr(dica)}">${miniatura(it)}${it.tipo === "video" ? '<span class="base-tipo">vídeo</span>' : ""}${ordem >= 0 ? `<span class="base-ordem">cena ${ordem + 1}</span>` : ""}</button><span class="base-legenda" title="${escaparAttr(it.descricao || it.nome)}">${escaparAttr(it.descricao || it.nome)}</span></div>`;
        }).join("")
      : '<span class="video-meta">Nada na Base ainda — importe imagens ou vídeos na aba Base.</span>';

    if (strip) {
      strip.innerHTML = lista.length
        ? `<div class="video-meta">Sequência (a ordem em que aparecem no vídeo). Descreva cada uma: é assim que a IA "enxerga" para escrever o roteiro.</div>` +
          lista.map((chave, i) => {
            const it = itens.find((x) => chaveDe(x) === chave);
            return `<div class="seq-item" data-i="${i}">
              <span class="seq-num">${i + 1}</span>
              <span class="seq-mini">${miniatura(it)}</span>
              <div class="seq-corpo">
                <span class="video-meta">${escaparAttr(it.nome)}</span>
                <input type="text" class="seq-desc" data-chave="${escaparAttr(chave)}" value="${escaparAttr(it.descricao || "")}" maxlength="300" placeholder="Descreva o que aparece (ex.: polvo abrindo um caramujo)">
              </div>
              <div class="seq-botoes">
                <button type="button" class="seq-up" title="Subir"${i === 0 ? " disabled" : ""}>↑</button>
                <button type="button" class="seq-down" title="Descer"${i === lista.length - 1 ? " disabled" : ""}>↓</button>
                <button type="button" class="seq-rem" title="Tirar da sequência">✕</button>
              </div>
            </div>`;
          }).join("")
        : "";
    }

    grade.querySelectorAll(".thumb-img-opcao").forEach((op) => op.addEventListener("click", () => {
      const chave = op.dataset.chave;
      const pos = lista.indexOf(chave);
      if (pos >= 0) lista.splice(pos, 1);
      else {
        const usos = itens.find((i) => chaveDe(i) === chave)?.usado_em || [];
        if (usos.length && !confirm(`Isso já foi usado em: ${usos.join(", ")}. Usar de novo?`)) return;
        lista.push(chave);
      }
      desenhar();
    }));

    if (strip) {
      strip.querySelectorAll(".seq-item").forEach((linha) => {
        const i = parseInt(linha.dataset.i, 10);
        linha.querySelector(".seq-up").addEventListener("click", () => { [lista[i - 1], lista[i]] = [lista[i], lista[i - 1]]; desenhar(); });
        linha.querySelector(".seq-down").addEventListener("click", () => { [lista[i + 1], lista[i]] = [lista[i], lista[i + 1]]; desenhar(); });
        linha.querySelector(".seq-rem").addEventListener("click", () => { lista.splice(i, 1); desenhar(); });
        linha.querySelector(".seq-desc").addEventListener("change", async (ev) => {
          const it = itens.find((x) => chaveDe(x) === ev.target.dataset.chave);
          it.descricao = ev.target.value.trim();
          const corpo = new FormData();
          corpo.set("descricao", it.descricao);
          corpo.set("canal_id", it.canal_id || "");
          await fetch(`/api/biblioteca/${it.tipo === "video" ? "videos" : "imagens"}/${encodeURIComponent(it.nome)}/info`, { method: "PUT", body: corpo });
          grade.querySelectorAll(".thumb-img-opcao").forEach((b) => { if (b.dataset.chave === chaveDe(it)) b.nextElementSibling.textContent = it.descricao || it.nome; });
        });
      });
    }
    if (typeof aoMudar === "function") aoMudar();
  };
  desenhar();
}

// ---------------- Agente: roteiro a partir das imagens escolhidas ----------------

const selecionadasAgente = [];

function montarSequenciaAgente() {
  return montarSequencia({
    grade: document.getElementById("ag-base-grade"),
    strip: document.getElementById("ag-base-sequencia"),
    lista: selecionadasAgente,
    aoMudar: () => {
      const n = selecionadasAgente.length;
      document.getElementById("btn-ag-roteiro").disabled = n === 0;
      const dur = parseFloat(document.getElementById("ag-duracao").value) || 0;
      document.getElementById("ag-resumo").textContent = n ? `${n} cena(s) de ~${Math.round((dur * 60) / n)} s cada (${dur} min no total).` : "Escolha as imagens para começar.";
    },
  });
}

document.getElementById("ag-duracao").addEventListener("input", () => {
  const n = selecionadasAgente.length;
  const dur = parseFloat(document.getElementById("ag-duracao").value) || 0;
  document.getElementById("ag-resumo").textContent = n ? `${n} cena(s) de ~${Math.round((dur * 60) / n)} s cada (${dur} min no total).` : "Escolha as imagens para começar.";
});

function mostrarRoteiroDoAgente() {
  const area = document.getElementById("ag-roteiro-texto");
  const paragrafos = area.value.split("\n").map((p) => p.trim()).filter(Boolean);
  document.getElementById("ag-roteiro-cenas").innerHTML =
    `<div class="roteiro-cenas-ok"><b>Narração total: ${formatarNarracao(paragrafos.join(" "))}</b></div>` +
    paragrafos.map((p, i) => `<div class="roteiro-cena"><b>Cena ${i + 1}</b> <span class="video-meta">${formatarNarracao(p)}</span></div>`).join("");
}

document.getElementById("ag-roteiro-texto").addEventListener("input", mostrarRoteiroDoAgente);

document.getElementById("btn-ag-roteiro").addEventListener("click", async (ev) => {
  const botao = ev.currentTarget;
  const status = document.getElementById("ag-roteiro-status");
  const titulo = document.getElementById("ag-titulo").value.trim();
  if (!titulo) {
    status.textContent = "Escreva o título do vídeo primeiro.";
    return;
  }
  botao.disabled = true;
  document.getElementById("ag-barra").hidden = false;
  const inicio = Date.now();
  const relogio = setInterval(() => (status.textContent = `O agente está escrevendo o roteiro… ${Math.round((Date.now() - inicio) / 1000)}s`), 500);
  const corpo = new FormData();
  corpo.set("titulo", titulo);
  corpo.set("duracao_alvo", document.getElementById("ag-duracao").value || "1");
  corpo.set("num_cenas", String(selecionadasAgente.length));
  corpo.set("descricao_video", document.getElementById("ag-instrucoes").value);
  corpo.set("midias", selecionadasAgente.join("|"));
  try {
    const r = await fetch("/api/roteiro/preview", { method: "POST", body: corpo }).then((x) => x.json());
    if (r.erro) {
      status.textContent = `Deu erro: ${r.erro}`;
    } else {
      document.getElementById("ag-roteiro-texto").value = r.roteiro;
      document.getElementById("ag-roteiro-resultado").hidden = false;
      mostrarRoteiroDoAgente();
      status.textContent = "Roteiro pronto. Ajuste o texto se quiser e envie para o Novo vídeo.";
    }
  } catch {
    status.textContent = "Deu erro de conexão, tenta de novo.";
  } finally {
    clearInterval(relogio);
    document.getElementById("ag-barra").hidden = true;
    botao.disabled = selecionadasAgente.length === 0;
  }
});

document.getElementById("btn-ag-usar").addEventListener("click", async () => {
  // leva título, roteiro, duração e a sequência de mídias para o formulário do Novo vídeo
  formNovo.titulo.value = document.getElementById("ag-titulo").value.trim();
  formNovo.roteiro.value = document.getElementById("ag-roteiro-texto").value.trim();
  formNovo.duracao_alvo.value = document.getElementById("ag-duracao").value || "1";
  selecionadasBase.splice(0, selecionadasBase.length, ...selecionadasAgente);
  campoNumCenas.value = selecionadasAgente.length;
  campoNumCenas.dataset.auto = "1";
  trocarAba("novo");
  await montarSeletorBaseNovoVideo();
  formNovo.roteiro.dispatchEvent(new Event("input", { bubbles: true }));
  formNovo.titulo.focus();
});
