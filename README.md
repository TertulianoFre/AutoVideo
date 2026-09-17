# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona (visão geral do produto)

1. **Agente** pesquisa tendências na web (agendado ou sob pedido) e sugere ideias de vídeo.
2. **Você** aprova uma sugestão ou digita seu próprio título/descrição.
3. **Geração**: roteiro (levando em conta o contexto do canal), narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação) e legenda sincronizada. Também dá pra gerar um vídeo **ambiente** (som contínuo tipo chuva + imagem, sem narração).
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts).
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube.
6. **Painel**: acompanha inscritos, visualizações, tempo de exibição e receita estimada do canal.

Tudo roda localmente no Windows, sem custo de API paga.

## App (backend + tela)

Já existe um app de verdade, não só o terminal — `backend/` (FastAPI) serve a tela em `frontend/`.

Rodar:
```
.venv\Scripts\uvicorn backend.main:app --reload
```
Abre em `http://localhost:8000`, com 3 telas: **Painel** (vídeos recentes + contexto do canal), **Novo vídeo** (formulário com progresso real) e **Fila** (todos os vídeos gerados).

Na tela "Novo vídeo", só **título** e **data de postagem** são obrigatórios. Tudo mais é opcional:
- **Modo**: Narrado (roteiro + narração, padrão) ou Ambiente (som contínuo + imagem, sem narração — ex: "chuva pra relaxar", 15+ minutos).
- **Descrição do vídeo**: texto livre que ajusta o estilo — ex: "2D simples", "mais detalhado/realista", "infantil e colorido". Influencia tanto o roteiro quanto a imagem gerada por IA.
- **Roteiro**: se deixar em branco, o motor escreve sozinho a partir do título (+ contexto do canal + descrição do vídeo).

## Motor de geração — como funciona por dentro

Diagrama completo (fluxo principal + cada serviço externo usado): https://claude.ai/artifact/EaS2eEAc3MtsY3nrjSjeyx — cobre o modo narrado; o modo ambiente (`engine/ambiente.py`) ainda não está no diagrama.

Resumo do fluxo (`engine/`, testável também pelo `cli.py`):

1. **Contexto do canal** (`engine/canal.py`) — uma descrição livre (nicho, tom, público) salva uma vez em `dados/canal.json` e usada como base sempre que um roteiro é gerado, pra manter os vídeos alinhados com a linha do canal.
2. **Roteiro** (`engine/roteiro.py`) — opcional: se você não passar um roteiro pronto, o motor escreve um sozinho a partir do título (+ contexto do canal + descrição do vídeo), já do tamanho certo pra bater a duração alvo pedida (via Pollinations.ai, chat compatível com a API da OpenAI, grátis, sem chave). Também gera **hashtags/tags sugeridas** pra ajudar o vídeo a viralizar — hoje ficam disponíveis pra copiar; a inserção automática no YouTube (campos `tags`/`description` do upload) só é possível quando a integração com a YouTube Data API existir.
3. **Narração** (`engine/tts.py`) — `edge-tts` (Microsoft, grátis) gera o áudio e o tempo exato de cada palavra falada.
4. **Cenas** (`engine/scenes.py`) — o roteiro é dividido em cenas por frase (~5s cada), cada uma vai ganhar sua própria imagem de fundo.
5. **Imagem de cada cena** (`engine/visuals.py`) — três estilos escolhíveis:
   - `procedural`: gradiente gerado com Pillow, 100% local, sem internet.
   - `foto`: foto real — tenta o Openverse.org primeiro (grátis, sem chave), depois o Pexels (grátis, precisa de `PEXELS_API_KEY`). Se a foto encontrada tiver um rosto grande/de perto (detector local do OpenCV), tenta a outra fonte antes de desistir.
   - `ia`: traduz a cena pro inglês (MyMemory Translator, grátis), troca verbos de expressão facial de risco (bocejar, gritar...) por uma descrição de cena mais genérica, e gera a imagem via Pollinations.ai (grátis, sem chave). Estilo padrão é desenho 2D; a "descrição do vídeo" pode pedir algo diferente (mais detalhado, infantil, etc). Até 3 tentativas; se falhar, cai pro procedural.
6. **Legenda** (`engine/subtitles.py`) — arquivo `.ass` com destaque de cor por palavra (efeito "karaokê"), sincronizado com a narração. Não existe no modo ambiente.
7. **Montagem** (`engine/render.py`) — FFmpeg junta as imagens (slideshow) + áudio (+ legenda, se houver), exporta 16:9 e 9:16.

### Modo ambiente (`engine/ambiente.py`, `pipeline.gerar_video_ambiente`)

Sem narração nem legenda: um som contínuo em loop (hoje só "chuva", sintetizada localmente — ruído filtrado, não é gravação real, mas é grátis e automática) + imagens que trocam bem devagar (uma a cada ~4 min). Pensado pra vídeos longos (15-60 min) de relaxar/dormir/estudar.

### Limitações conhecidas

- O estilo `ia` (imagem) ainda pode gerar imagens estranhas em assuntos muito específicos/incomuns (a lista de palavras de risco cobre os casos vistos até agora, mas não é exaustiva).
- Checagem automática de "imagem com qualidade ruim, refazer" foi tentada com detector de rosto (OpenCV) — funciona bem em foto real, mas **não funciona em desenho/ilustração** (o detector é treinado pra foto), então só está ligada no estilo `foto`.
- O roteiro automático às vezes escreve uma frase meio estranha/gramaticalmente torta (é um modelo pequeno e gratuito) — vale sempre dar uma revisada antes de publicar.
- O som de chuva do modo ambiente é sintetizado (ruído filtrado), não uma gravação real — soa bem genérico, ainda dá pra melhorar.
- Hashtags/tags são só sugestão, ainda não entram sozinhas no YouTube (depende da integração com a YouTube Data API).

## Requisitos já levantados, ainda não implementados

- Botão de **regenerar vídeo** na tela "Novo vídeo", caso o resultado não fique bom.
- **Geração de thumbnail**, com prévia editável (poder pedir pra alterar).
- Poder **pedir alterações** num vídeo já gerado (não só regenerar do zero).
- **Publicação automática na data escolhida** — hoje "data de postagem" é só guardada como metadado; publicar de verdade nessa data depende da integração com a YouTube Data API + agendamento.
- Outros tipos de som ambiente além de chuva (hoje só `chuva` está implementado em `engine/ambiente.py`).

## Stack

- Python 3.12
- FastAPI + Uvicorn (backend/app) — `backend/`, tela em `frontend/`
- FFmpeg (montagem de vídeo/áudio/legenda, com libass) — localizado automaticamente via `engine/ferramentas.py`, não depende do PATH do processo
- Pillow (imagens de fundo procedurais), NumPy (síntese do som de chuva)
- edge-tts (narração, voz neural gratuita da Microsoft)
- Pollinations.ai (texto do roteiro, hashtags e imagens por IA, grátis, sem chave)
- requests + deep-translator (busca de fotos e tradução de prompt)
- opencv-python-headless (detector de rosto, usado no estilo `foto`)
- YouTube Data API v3 (publicação agendada) + YouTube Analytics API (painel) — ainda não integrado
- Git para versionar o projeto

## Status

App funcionando de ponta a ponta: tela real (Painel/Novo vídeo/Fila), motor completo (contexto do canal, roteiro automático com hashtags, narração, modo ambiente, 3 estilos de imagem, legenda com destaque, progresso real, download). Próximo: publicação de verdade no YouTube.

## Próximos passos

1. Configurar projeto no Google Cloud Console + credenciais OAuth da YouTube Data API
2. Integração da publicação agendada (usa a "data de postagem" já guardada) + inserção automática de tags/descrição
3. Tela do "Agente" (chat pra pedir vídeos, pesquisar tendências)
