# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona (visão geral do produto)

1. **Agente** combina o contexto do canal com o que está em alta no YouTube agora e sugere títulos — implementado (aba "Agente"); pesquisar tendências na web em geral (fora do YouTube) ainda não.
2. **Você** aprova uma sugestão (clica em "Usar esse título") ou digita seu próprio título/descrição.
3. **Geração**: um único fluxo pra tudo — roteiro (levando em conta o contexto do canal), narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação), legenda sincronizada, e opcionalmente um som de fundo (chuva, música suave...) baixinho por baixo da narração. Também dá pra marcar "sem narração" e usar só o som de fundo como áudio do vídeo (ex: 30 min de chuva pra relaxar) — tudo no mesmo formulário, sem telas separadas.
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts), com thumbnail automática.
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube (16:9 como vídeo normal, 9:16 como Short) — desde que o app fique rodando e sua conta esteja conectada.
6. **Painel**: acompanha inscritos, visualizações, tempo de exibição e receita estimada do canal (ainda não implementado — só a conexão com o YouTube e o contexto do canal por enquanto).

Tudo roda localmente no Windows, sem custo de API paga.

## App (backend + tela)

Já existe um app de verdade, não só o terminal — `backend/` (FastAPI) serve a tela em `frontend/`.

Rodar: dê dois cliques em `iniciar.bat` (ativa o venv, sobe o servidor na porta 8080 e abre o navegador sozinho). Se preferir manual:
```
.venv\Scripts\uvicorn backend.main:app --reload --port 8080
```
Abre em `http://localhost:8080`, com 4 telas: **Painel** (vídeos recentes, contexto do canal, estatísticas), **Agente** (sugestões de título), **Novo vídeo** (formulário único com progresso real) e **Fila** (todos os vídeos gerados, com **Regenerar**, **roteiro novo** e **nova thumbnail**). A conexão com o YouTube fica no perfil, no topo do menu lateral — clique nele pra conectar.

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

**Editar uma cena específica** (`engine.pipeline.regenerar_cena`, botão "cenas" na Fila): mostra cada cena do vídeo (texto + imagem) com um botão "Regenerar essa cena" — refaz só a imagem daquela cena (a IA sorteia de novo) e remonta o vídeo com ffmpeg, sem tocar no roteiro, na narração, na legenda nem nas outras cenas. Só funciona em vídeos gerados depois desse recurso existir (precisa do `metadata.json` ter a lista de cenas salva — clique em "Regenerar" uma vez em vídeos antigos pra habilitar).

### Publicação automática (`engine/youtube.py`, `engine/agendador.py`)

Precisa de um `client_secret.json` na raiz do projeto (credencial OAuth "App para computador", criada no Google Cloud Console — ver checklist abaixo) e de conectar sua conta uma vez no Painel (botão "Conectar YouTube": abre o navegador, você loga e autoriza).

Com isso feito, um agendador roda em segundo plano junto com o backend (`agendador.iniciar_agendador()`, confere a cada 10 min): qualquer vídeo com `data_postagem` já vencida e ainda não publicado é enviado automaticamente — o 16:9 como vídeo normal e o 9:16 como Short (dois uploads separados), com título, descrição (o roteiro) e as hashtags sugeridas. Fica como `private` por padrão até você confiar no fluxo (ajustável em `agendador.PRIVACIDADE_PADRAO`).

**Uma conta só, mesmo credencial pra sempre**: você configura o Google Cloud Console uma única vez. Conectar uma conta/canal novo depois é só clicar em "Conectar" de novo — sem precisar mexer no Cloud Console outra vez, a menos que seja uma conta de Google totalmente diferente (aí precisa adicionar o e-mail dela como "usuário de teste" na tela de consentimento OAuth do mesmo projeto).

**Limitação do Google, não do código**: como o app fica em modo "teste" (evita o processo de verificação do Google), a autorização expira a cada 7 dias — o Painel mostra "Não conectado" quando isso acontece, é só clicar em "Conectar" de novo.

**Estatísticas do canal** (inscritos, visualizações totais) aparecem no perfil/Painel quando conectado, e as mesmas informações alimentam o **Agente** (tendências do YouTube). Ambas usam o escopo `youtube.readonly`, que não existia nas primeiras versões — quem já tinha conectado antes precisa clicar em **"Reconectar"** (no perfil, no topo do menu) uma vez pra liberar as duas coisas de uma vez. O app avisa isso claramente, não precisa adivinhar.

### Agente (`engine/agente.py`)

Aba própria: clique em "Sugerir ideias" e ele combina o contexto do canal (`dados/canal.json`) com os títulos em alta no YouTube agora (`youtube.obter_tendencias`, região BR — só como inspiração, nunca copia) pra gerar títulos novos via Pollinations.ai. Cada sugestão tem um botão "Usar esse título" que já leva pra "Novo vídeo" com o título preenchido. Sem conexão com o YouTube, ainda sugere ideias — só fica sem o contexto de tendências.

### Limitações conhecidas

- O estilo `ia` (imagem) ainda pode gerar imagens estranhas em assuntos muito específicos/incomuns (a lista de palavras de risco cobre os casos vistos até agora, mas não é exaustiva).
- Checagem automática de "imagem com qualidade ruim, refazer" foi tentada com detector de rosto (OpenCV) — funciona bem em foto real, mas **não funciona em desenho/ilustração**, então só está ligada no estilo `foto`.
- O roteiro automático às vezes escreve uma frase meio estranha/gramaticalmente torta (é um modelo pequeno e gratuito) — use o "Pré-visualizar roteiro" pra revisar antes.
- Som de fundo (chuva/música) é sintetizado (ruído filtrado / acorde simples), não gravação real — soa genérico, ainda dá pra melhorar. Pedir "outro" som ainda não sintetiza algo customizado de verdade.
- Publicação automática depende do app ficar rodando (não é um serviço em nuvem) e da conta reconectada a cada 7 dias (limitação do modo "teste" do Google).

## Requisitos já levantados, ainda não implementados

- Prévia **editável** da thumbnail de verdade (hoje só troca a imagem-base por outra cena — "nova thumbnail" na Fila — não dá pra desenhar/ajustar).
- Sintetizar sons de fundo customizados de verdade (hoje só chuva e música suave são reais).
- **Receita estimada** no Painel — precisa do escopo `yt-analytics-monetary.readonly`, que o Google trata como escopo restrito (exige processo de verificação/CASA da Google, não é só ativar a API). Não vale a pena pra um app de uso pessoal — ficaria só inscritos/visualizações mesmo.
- Pesquisar tendências fora do YouTube (web em geral) pro Agente — hoje só usa o que está em alta no próprio YouTube.

## Stack

- Python 3.12
- FastAPI + Uvicorn (backend/app) — `backend/`, tela em `frontend/`
- FFmpeg (montagem de vídeo/áudio/legenda, com libass) — localizado automaticamente via `engine/ferramentas.py`, não depende do PATH do processo
- Pillow (imagens de fundo procedurais), NumPy (síntese de som de fundo)
- edge-tts (narração, voz neural gratuita da Microsoft)
- Pollinations.ai (texto do roteiro, hashtags e imagens por IA, grátis, sem chave)
- requests + deep-translator (busca de fotos e tradução de prompt)
- opencv-python-headless (detector de rosto, usado no estilo `foto`)
- google-api-python-client + google-auth-oauthlib (publicação no YouTube) — YouTube Analytics API (painel de estatísticas) ainda não integrada
- Git para versionar o projeto

## Status

App funcionando de ponta a ponta: Agente sugerindo ideias, contexto do canal, pré-visualização de roteiro, narração opcional, som de fundo opcional (mixado ou sozinho), 3 estilos de imagem, thumbnail automática (regenerável à parte), legenda com destaque, progresso real, download, regenerar (mantendo o roteiro), editar uma cena específica sem regenerar tudo, publicação automática no YouTube (upload + agendador local) e estatísticas reais do canal no perfil.

## Checklist do Google Cloud Console (feito uma vez, por você)

1. [console.cloud.google.com](https://console.cloud.google.com/) → criar projeto
2. "APIs e serviços" → "Biblioteca" → ativar **YouTube Data API v3**
3. "Tela de permissão OAuth" → tipo Externo → preencher nome/e-mails → em "Usuários de teste", adicionar seu e-mail → deixar em "Teste" (sem verificação)
4. "Credenciais" → "Criar credenciais" → "ID do cliente OAuth" → tipo **App para computador** → baixar o JSON
5. Salvar o arquivo como `client_secret.json` na raiz do projeto
6. No app, clicar no perfil (canto superior esquerdo) e autorizar

## Próximos passos

1. Sons de fundo customizados de verdade (hoje só chuva/música suave)
2. Suporte a mais de um canal/conta ao mesmo tempo (hoje é hardcoded pra uma conta "principal")
