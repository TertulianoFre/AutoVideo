# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona (visão geral do produto)

1. **Agente** pesquisa tendências na web (agendado ou sob pedido) e sugere ideias de vídeo.
2. **Você** aprova uma sugestão ou digita seu próprio título/descrição.
3. **Geração**: um único fluxo pra tudo — roteiro (levando em conta o contexto do canal), narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação), legenda sincronizada, e opcionalmente um som de fundo (chuva, música suave...) baixinho por baixo da narração. Também dá pra marcar "sem narração" e usar só o som de fundo como áudio do vídeo (ex: 30 min de chuva pra relaxar) — tudo no mesmo formulário, sem telas separadas.
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts), com thumbnail automática.
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube.
6. **Painel**: acompanha inscritos, visualizações, tempo de exibição e receita estimada do canal.

Tudo roda localmente no Windows, sem custo de API paga.

## App (backend + tela)

Já existe um app de verdade, não só o terminal — `backend/` (FastAPI) serve a tela em `frontend/`.

Rodar:
```
.venv\Scripts\uvicorn backend.main:app --reload
```
Abre em `http://localhost:8000`, com 3 telas: **Painel** (vídeos recentes + contexto do canal), **Novo vídeo** (formulário único com progresso real) e **Fila** (todos os vídeos gerados, com botão de **Regenerar**).

Na tela "Novo vídeo", só **título** e **data de postagem** são obrigatórios. É um formulário só — nada de tela separada pra "vídeo ambiente". Tudo mais é opcional:
- **Descrição do vídeo**: texto livre que ajusta o estilo — ex: "2D simples", "mais detalhado/realista", "infantil e colorido". Influencia tanto o roteiro quanto a imagem gerada por IA.
- **Roteiro**: se deixar em branco, o motor escreve sozinho a partir do título (+ contexto do canal + descrição do vídeo). Tem um botão **"Pré-visualizar roteiro"** que gera só o texto primeiro (sem imagem/narração/vídeo) pra você ler, editar ou pedir de novo antes de gastar tempo gerando o vídeo inteiro.
- **Vídeo sem narração**: vira só som de fundo + imagem (ideal pra vídeos longos, 15-60 min).
- **Som de fundo**: chuva ou música suave, mixados bem baixo por baixo da narração — funciona tanto num vídeo narrado normal quanto sozinho (sem narração). "Outro" permite descrever o que você quer, mas hoje ainda usa a síntese mais parecida (chuva ou música) — não sintetiza qualquer som descrito ainda.

## Motor de geração — como funciona por dentro

Diagrama completo (fluxo principal + cada serviço externo usado): https://claude.ai/artifact/EaS2eEAc3MtsY3nrjSjeyx — o diagrama ainda não reflete a unificação do som de fundo (foi desenhado quando "ambiente" era um modo separado).

Resumo do fluxo (`engine/pipeline.py:gerar_video`, único ponto de entrada, testável também pelo `cli.py`):

1. **Contexto do canal** (`engine/canal.py`) — uma descrição livre (nicho, tom, público) salva uma vez em `dados/canal.json` e usada como base sempre que um roteiro é gerado.
2. **Roteiro** (`engine/roteiro.py`) — opcional: se você não passar um roteiro pronto, o motor escreve um sozinho a partir do título (+ contexto do canal + descrição do vídeo), com estrutura pedida explicitamente (gancho, 2-3 detalhes concretos, frase de impacto — não genérico), do tamanho certo pra bater a duração alvo (via Pollinations.ai, chat compatível com a API da OpenAI, grátis, sem chave, `reasoning_effort: low` pra não gastar o orçamento de tokens só "pensando"). Também gera **hashtags/tags sugeridas** — hoje ficam disponíveis pra copiar; inserção automática no YouTube depende da integração com a YouTube Data API.
3. **Narração** (`engine/tts.py`) — `edge-tts` (Microsoft, grátis), ou nenhuma se "sem narração" estiver marcado.
4. **Som de fundo** (`engine/ambiente.py`, opcional) — chuva ou música suave sintetizadas localmente (numpy, sem internet). Sem narração, é o áudio inteiro do vídeo; com narração, é mixado bem baixo por baixo dela via `render.mixar_audio_com_fundo` (ffmpeg `amix`).
5. **Cenas** (`engine/scenes.py`) — com narração, o roteiro vira cenas por frase (~5s cada); sem narração, imagens em intervalo fixo (~4 min).
6. **Imagem de cada cena** (`engine/visuals.py`) — três estilos escolhíveis:
   - `procedural`: gradiente gerado com Pillow, 100% local, sem internet.
   - `foto`: foto real — tenta o Openverse.org primeiro (grátis, sem chave), depois o Pexels (grátis, precisa de `PEXELS_API_KEY`). Se a foto encontrada tiver um rosto grande/de perto (detector local do OpenCV), tenta a outra fonte antes de desistir.
   - `ia`: traduz a cena pro inglês (MyMemory Translator, grátis), troca verbos de expressão facial de risco (bocejar, gritar...) por uma descrição de cena mais genérica, e gera a imagem via Pollinations.ai (grátis, sem chave). Estilo padrão é desenho 2D; a "descrição do vídeo" pode pedir algo diferente. Até 3 tentativas; se falhar, cai pro procedural.
7. **Legenda** (`engine/subtitles.py`) — arquivo `.ass` com destaque de cor por palavra (efeito "karaokê"). Só existe com narração.
8. **Montagem** (`engine/render.py`) — FFmpeg junta as imagens (slideshow) + áudio (+ legenda, se houver), exporta 16:9 e 9:16.
9. **Thumbnail** (`engine/thumbnail.py`) — 1280x720, título em destaque por cima da primeira cena, estilo YouTube.

### Limitações conhecidas

- O estilo `ia` (imagem) ainda pode gerar imagens estranhas em assuntos muito específicos/incomuns (a lista de palavras de risco cobre os casos vistos até agora, mas não é exaustiva).
- Checagem automática de "imagem com qualidade ruim, refazer" foi tentada com detector de rosto (OpenCV) — funciona bem em foto real, mas **não funciona em desenho/ilustração**, então só está ligada no estilo `foto`.
- O roteiro automático às vezes escreve uma frase meio estranha/gramaticalmente torta (é um modelo pequeno e gratuito) — use o "Pré-visualizar roteiro" pra revisar antes.
- Som de fundo (chuva/música) é sintetizado (ruído filtrado / acorde simples), não gravação real — soa genérico, ainda dá pra melhorar. Pedir "outro" som ainda não sintetiza algo customizado de verdade.
- Hashtags/tags são só sugestão, ainda não entram sozinhas no YouTube.

## Requisitos já levantados, ainda não implementados

- Prévia **editável** da thumbnail.
- Poder **pedir alterações pontuais** num vídeo já gerado (o botão "Regenerar" da Fila refaz tudo do zero).
- **Publicação automática na data escolhida** — hoje "data de postagem" é só guardada como metadado; publicar de verdade (e deixar o programa rodando local publicando sozinho conforme os dias passam) depende da integração com a YouTube Data API + um agendador rodando junto do backend.
- Sintetizar sons de fundo customizados de verdade (hoje só chuva e música suave são reais).

## Stack

- Python 3.12
- FastAPI + Uvicorn (backend/app) — `backend/`, tela em `frontend/`
- FFmpeg (montagem de vídeo/áudio/legenda, com libass) — localizado automaticamente via `engine/ferramentas.py`, não depende do PATH do processo
- Pillow (imagens de fundo procedurais), NumPy (síntese de som de fundo)
- edge-tts (narração, voz neural gratuita da Microsoft)
- Pollinations.ai (texto do roteiro, hashtags e imagens por IA, grátis, sem chave)
- requests + deep-translator (busca de fotos e tradução de prompt)
- opencv-python-headless (detector de rosto, usado no estilo `foto`)
- YouTube Data API v3 (publicação agendada) + YouTube Analytics API (painel) — ainda não integrado
- Git para versionar o projeto

## Status

App funcionando de ponta a ponta com um fluxo único (sem telas separadas pra "narrado" vs "ambiente"): contexto do canal, pré-visualização de roteiro, narração opcional, som de fundo opcional (mixado ou sozinho), 3 estilos de imagem, thumbnail automática, legenda com destaque, progresso real, download, regenerar. Próximo: publicação de verdade no YouTube.

## Próximos passos

1. Configurar projeto no Google Cloud Console + credenciais OAuth da YouTube Data API
2. Integração da publicação agendada (usa a "data de postagem" já guardada) + um agendador local que publica sozinho conforme os dias passam + inserção automática de tags/descrição
3. Tela do "Agente" (chat pra pedir vídeos, pesquisar tendências)
