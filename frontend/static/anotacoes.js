// Bloco de notas simples: salva sozinho (depois de 700 ms sem digitar) em dados/anotacoes.txt.
let anotacoesTimer = null;
let anotacoesCarregadas = false;

async function carregarAnotacoes() {
  const campo = document.getElementById("anotacoes-texto");
  const status = document.getElementById("anotacoes-status");
  if (!anotacoesCarregadas) {
    try {
      campo.value = (await (await fetch("/api/anotacoes")).json()).texto || "";
      anotacoesCarregadas = true;
    } catch {
      status.textContent = "não consegui carregar";
      return;
    }
    campo.addEventListener("input", () => {
      status.textContent = "salvando…";
      clearTimeout(anotacoesTimer);
      anotacoesTimer = setTimeout(async () => {
        const dados = new FormData();
        dados.set("texto", campo.value);
        try {
          await fetch("/api/anotacoes", { method: "PUT", body: dados });
          status.textContent = "salvo";
        } catch {
          status.textContent = "erro ao salvar";
        }
      }, 700);
    });
  }
}
