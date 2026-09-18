# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona (visão geral do produto)

1. **Agente** combina o contexto do canal ativo com o que está em alta no YouTube agora e sugere títulos — implementado (aba "Agente"); pesquisar tendências na web em geral (fora do YouTube) ainda não.
2. **Você** aprova uma sugestão (clica em "Usar esse título") ou digita seu próprio título/descrição.
3. **Geração**: um único fluxo pra tudo — roteiro (levando em conta o contexto do canal ativo), narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação), legenda sincronizada, e opcionalmente um som de fundo (chuva, música suave...) baixinho por baixo da narração. Também dá pra marcar "sem narração" e usar só o som de fundo como áudio do vídeo (ex: 30 min de chuva pra relaxar) — tudo no mesmo formulário, sem telas separadas.
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts), com thumbnail automática.
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube (16:9 como vídeo normal, 9:16 como Short), na conta do canal a que o vídeo pertence — desde que o app fique rodando e essa conta esteja conectada.
6. **Painel**: acompanha inscritos e visualizações do canal ativo (tempo de exibição e receita estimada ainda não implementados).

Suporta **múltiplos canais** (nicho/contexto e conta do YouTube próprios de cada um) rodando no mesmo app — veja a seção "Canais" abaixo.

Tudo roda localmente no Windows, sem custo de API paga.

## App (backend + tela)

Já existe um app de verdade, não só o terminal — `backend/` (FastAPI) serve a tela em `frontend/`.

Rodar: dê dois cliques em `iniciar.bat` (ativa o venv, sobe o servidor na porta 8080 e abre o navegador sozinho). Se preferir manual:
```
.venv\Scripts\uvicorn backend.main:app --reload --port 8080
```
Abre em `http://localhost:8080`, com 5 telas: **Painel** (vídeos recentes, estatísticas do canal ativo), **Canais** (gerenciar canais — nome, contexto, qual está ativo), **Agente** (sugestões de título), **Novo vídeo** (formulário único com progresso real) e **Fila** (todos os vídeos de todos os canais, com **Regenerar**, **roteiro novo**, **nova thumbnail**, **editar thumbnail** e **cenas**). O seletor de canal ativo fica no topo do menu lateral; logo abaixo, o perfil mostra a conexão com o YouTube **do canal ativo** — clique nele pra conectar/reconectar.

Na tela "Novo vídeo", só **título** e **data de postagem** são obrigatórios. É um formulário só — nada de tela separada pra "vídeo ambiente". Tudo mais é opcional:
- **Descrição do vídeo**: texto livre que ajusta o estilo — ex: "2D simples", "mais detalhado/realista", "infantil e colorido". Influencia tanto o roteiro quanto a imagem gerada por IA.
- **Roteiro**: se deixar em branco, o motor escreve sozinho a partir do título (+ contexto do canal + descrição do vídeo). Tem um botão **"Pré-visualizar roteiro"** que gera só o texto primeiro (sem imagem/narração/vídeo) pra você ler, editar ou pedir de novo antes de gastar tempo gerando o vídeo inteiro.
- **Vídeo sem narração**: vira só som de fundo + imagem (ideal pra vídeos longos, 15-60 min).
- **Som de fundo**: chuva ou música suave, mixados bem baixo por baixo da narração — funciona tanto num vídeo narrado normal quanto sozinho (sem narração). "Outro" permite descrever o que você quer, mas hoje ainda usa a síntese mais parecida (chuva ou música) — não sintetiza qualquer som descrito ainda.

## Motor de geração — como funciona por dentro

Diagrama completo (fluxo principal + cada serviço externo usado): https://claude.ai/artifact/EaS2eEAc3MtsY3nrjSjeyx — o diagrama ainda não reflete a unificação do som de fundo (foi desenhado quando "ambiente" era um modo separado).

Resumo do fluxo (`engine/pipeline.py:gerar_video`, único ponto de entrada, testável também pelo `cli.py`):

1. **Contexto do canal** (`engine/canal.py`) — uma descrição livre (nicho, tom, público) por canal, salva em `dados/canais.json` e usada como base sempre que um roteiro é gerado pra esse canal (veja a seção "Canais" abaixo).
2. **Roteiro** (`engine/roteiro.py`) — opcional: se você não passar um roteiro pronto, o motor escreve um sozinho a partir do título (+ contexto do canal + descrição do vídeo), com estrutura pedida explicitamente (gancho, 2-3 detalhes concretos, frase de impacto — não genérico), do tamanho certo pra bater a duração alvo (via Pollinations.ai, chat compatível com a API da OpenAI, grátis, sem chave, `reasoning_effort: low` pra não gastar o orçamento de tokens só "pensando"), e depois passa por uma segunda chamada só de revisão (gramática/fluência, mantendo sentido e tamanho — se a revisão sair estranha, mantém o rascunho original). Também gera **hashtags/tags sugeridas** — hoje ficam disponíveis pra copiar; inserção automática no YouTube depende da integração com a YouTube Data API.
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

**Editar a thumbnail** (botão "editar thumbnail" na Fila): troca o texto exibido (independente do título do vídeo), a cor (5 opções), a posição (grade 3x3: topo/centro/baixo × esquerda/centro/direita) e o tamanho da fonte (pequena/média/grande) — sem mexer na imagem de base. Fica salvo no `metadata.json` (`thumbnail_texto`, `thumbnail_cor`, `thumbnail_posicao`, `thumbnail_tamanho`) — sobrevive a "nova thumbnail" (só troca a imagem) e a regenerar a cena 0. É posicionamento por grade fixa, não arrastar/redimensionar livre.

### Canais (`engine/canal.py`, aba "Canais")

Cada canal cadastrado tem: **id**, **nome**, **contexto** (nicho/tom/público) e **conta do YouTube própria** (mesmo id do canal — um token separado em `dados/tokens/token_<id>.json`). Tudo fica em `dados/canais.json` (não versionado no git — é dado pessoal de uso, evolui a cada canal que você adiciona; se o arquivo não existir ainda, o app cria sozinho um canal `principal` na primeira vez, migrando o contexto do antigo `dados/canal.json` se ele existir).

Um canal fica marcado como **ativo** por vez (seletor no topo do menu lateral) — é o que "Novo vídeo" usa pra escrever o roteiro (contexto certo) e gravar o vídeo com o `canal_id` certo, e o que o **Agente** usa pra puxar tendências/contexto. A **Fila** e o **Painel** mostram vídeos de todos os canais juntos (com uma etiqueta do nome do canal em cada linha, quando há mais de um canal); trocar o canal ativo nunca esconde vídeo nenhum.

Cada vídeo grava o `canal_id` de quem o criou no `metadata.json`, e **continua sendo desse canal pra sempre** — regenerar, editar cena ou trocar o canal ativo depois não muda isso. O agendador (`engine/agendador.py`) usa exatamente esse `canal_id` salvo pra escolher a conta do YouTube certa na hora de publicar — nunca publica um vídeo na conta errada mesmo com vários canais ativos ao mesmo tempo. Vídeos gerados antes desse recurso existir (sem `canal_id` salvo) caem no canal `principal`, mesmo comportamento de sempre.

Adicionar um canal novo é só preencher nome (+ contexto opcional) na aba "Canais". Pra conectar a conta do YouTube dele: defina ele como ativo e clique no perfil, no topo do menu — o fluxo de conexão é sempre o mesmo, só muda pra qual token ele salva.

### Publicação automática (`engine/youtube.py`, `engine/agendador.py`)

Precisa de um `client_secret.json` na raiz do projeto (credencial OAuth "App para computador", criada no Google Cloud Console — ver checklist abaixo) e de conectar a conta de cada canal pelo menos uma vez (perfil, no topo do menu, com esse canal ativo).

Com isso feito, um agendador roda em segundo plano junto com o backend (`agendador.iniciar_agendador()`, confere a cada 10 min): qualquer vídeo com `data_postagem` já vencida e ainda não publicado é enviado automaticamente — o 16:9 como vídeo normal e o 9:16 como Short (dois uploads separados), na conta do canal a que ele pertence, com título, descrição (o roteiro) e as hashtags sugeridas. Fica como `private` por padrão até você confiar no fluxo (ajustável em `agendador.PRIVACIDADE_PADRAO`).

**Mesma credencial do Google Cloud pra todos os canais**: você configura o Google Cloud Console uma única vez, não importa quantos canais/contas adicionar depois. Conectar uma conta nova é só clicar em "Conectar" de novo (com o canal certo ativo) — sem precisar mexer no Cloud Console outra vez, a menos que seja uma conta de Google totalmente diferente (aí precisa adicionar o e-mail dela como "usuário de teste" na tela de consentimento OAuth do mesmo projeto).

**Limitação do Google, não do código**: como o app fica em modo "teste" (evita o processo de verificação do Google), a autorização de cada conta expira a cada 7 dias — o perfil mostra "Não conectado" pro canal ativo quando isso acontece, é só clicar em "Conectar" de novo.

**Estatísticas do canal** (inscritos, visualizações totais) aparecem no perfil/Painel pro canal ativo quando conectado, e as mesmas informações alimentam o **Agente** (tendências do YouTube). Ambas usam o escopo `youtube.readonly`, que não existia nas primeiras versões — quem já tinha conectado antes precisa clicar em **"Reconectar"** (no perfil, no topo do menu) uma vez pra liberar as duas coisas de uma vez. O app avisa isso claramente, não precisa adivinhar.

### Agente (`engine/agente.py`)

Aba própria: clique em "Sugerir ideias" e ele combina o contexto do canal **ativo** com os títulos em alta na conta do YouTube desse canal agora (`youtube.obter_tendencias`, região BR — só como inspiração, nunca copia) pra gerar títulos novos via Pollinations.ai. Cada sugestão tem um botão "Usar esse título" que já leva pra "Novo vídeo" com o título preenchido. Sem conexão com o YouTube, ainda sugere ideias — só fica sem o contexto de tendências.

### Limitações conhecidas

- O estilo `ia` (imagem) ainda pode gerar imagens estranhas em assuntos muito específicos/incomuns (a lista de palavras de risco cobre os casos vistos até agora, mas não é exaustiva).
- Checagem automática de "imagem com qualidade ruim, refazer" foi tentada com detector de rosto (OpenCV) — funciona bem em foto real, mas **não funciona em desenho/ilustração**, então só está ligada no estilo `foto`.
- O roteiro automático passa por uma segunda chamada de revisão (corrige gramática/frases estranhas antes de devolver) mas ainda é um modelo pequeno e gratuito — de vez em quando sai uma frase esquisita mesmo assim. Use o "Pré-visualizar roteiro" pra revisar antes.
- Som de fundo (`engine/ambiente.py`: chuva, música, ondas do mar, fogueira, vento) é sintetizado (ruído filtrado, sem gravação real) — soa genérico, ainda dá pra melhorar. Pedir "outro" com descrição livre escolhe o mais parecido desses 5 como base e ainda soma camadas extra por cima se a descrição menciona pássaros, trovão ou multidão/cafeteria; fora essas combinações reconhecidas, ainda não sintetiza um som totalmente novo e arbitrário.
- Publicação automática depende do app ficar rodando (não é um serviço em nuvem) e da conta reconectada a cada 7 dias (limitação do modo "teste" do Google).

## Requisitos já levantados, ainda não implementados

- Editor visual de thumbnail com posição livre (arrastar o texto pra qualquer lugar, trocar fonte) — hoje a posição é uma grade fixa de 9 pontos + 3 tamanhos, não drag-and-drop.
- Sintetizar **qualquer** som de fundo descrito de verdade — hoje são 5 tipos-base fixos + 3 camadas combináveis (pássaros, trovão, multidão) reconhecidas por palavra-chave; uma descrição sem nenhuma dessas palavras ainda cai só no tipo-base mais parecido, sem gerar nada realmente novo.
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

App funcionando de ponta a ponta: **múltiplos canais** (contexto e conta do YouTube próprios de cada um, publicação sempre na conta certa), Agente sugerindo ideias, pré-visualização de roteiro (com revisão automática), narração opcional, som de fundo opcional (5 tipos, mixado ou sozinho), 3 estilos de imagem, thumbnail automática e editável (texto/cor/posição/tamanho), legenda com destaque, progresso real, download, regenerar (mantendo o roteiro e o canal original), editar uma cena específica sem regenerar tudo, publicação automática no YouTube (upload + agendador local) e estatísticas reais do canal ativo no perfil.

## Checklist do Google Cloud Console (feito uma vez, por você — vale pra todos os canais)

1. [console.cloud.google.com](https://console.cloud.google.com/) → criar projeto
2. "APIs e serviços" → "Biblioteca" → ativar **YouTube Data API v3**
3. "Tela de permissão OAuth" → tipo Externo → preencher nome/e-mails → em "Usuários de teste", adicionar o e-mail de cada conta do Google que for conectar (uma por canal) → deixar em "Teste" (sem verificação)
4. "Credenciais" → "Criar credenciais" → "ID do cliente OAuth" → tipo **App para computador** → baixar o JSON
5. Salvar o arquivo como `client_secret.json` na raiz do projeto
6. No app, com o canal certo ativo (seletor no topo do menu), clicar no perfil (canto superior esquerdo) e autorizar — repita esse último passo pra cada canal/conta que quiser conectar

## Próximos passos

1. Mais camadas de som combináveis (hoje só pássaros/trovão/multidão) e, mais pra frente, sintetizar algo verdadeiramente arbitrário a partir de qualquer descrição
2. Posição livre (arrastar) da thumbnail, em vez da grade fixa de 9 pontos de hoje
3. Editar/renomear a conta do YouTube de um canal já criado sem precisar recriar o canal
