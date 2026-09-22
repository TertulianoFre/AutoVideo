# AutoVideo

Aplicativo local (Windows) que automatiza a produção de vídeos para o YouTube: do título ao vídeo publicado. Ele escreve o roteiro, narra, cria as imagens de cada cena, gera a legenda sincronizada, monta o vídeo em 16:9 e em 9:16 (Shorts), faz a thumbnail e publica no YouTube na data agendada.

Tudo roda na sua máquina e funciona sem nenhuma API paga. Chaves gratuitas de alguns serviços são opcionais e só aumentam a variedade e o limite de uso.

## Funcionalidades

- **Roteiro automático** a partir do título, com o contexto do canal (nicho, tom, público) e a duração desejada. Pode ser pré-visualizado, editado ou escrito à mão.
- **Narração** com vozes neurais gratuitas (feminina, masculina, infantil; vários idiomas), ou gravada/enviada por você. Também dá para gerar vídeos sem narração, só com som de fundo.
- **Som de fundo** sintetizado localmente (chuva, música suave, mar, fogueira, vento, com camadas combináveis) ou um áudio seu.
- **Imagens por cena** em três estilos: gradiente procedural (offline), fotos livres de direitos (Openverse, Wikimedia, NASA, Pexels, Pixabay) ou ilustração gerada por IA.
- **Legenda estilo karaokê** com destaque palavra por palavra e estilo configurável.
- **Exportação em 16:9 e 9:16** e **thumbnails editáveis** (texto arrastável, cor, tamanho, efeitos, imagem de fundo própria), inclusive para o Short.
- **Storyboard de cenas**: edite o texto, troque ou regenere a imagem de uma cena sem refazer o vídeo inteiro.
- **Vários canais** no mesmo app, cada um com seu contexto e sua conta do YouTube. Cada vídeo é sempre publicado na conta do canal que o criou.
- **Publicação agendada** no YouTube (vídeo normal + Short), com título, descrição e tags, somente após a sua confirmação.
- **Agente** em linguagem natural: sugere títulos com base no que está em alta, responde perguntas sobre o canal e edita, reagenda ou cancela vídeos ("muda o vídeo X para sexta às 18h").
- **Painel** com inscritos, visualizações e vídeos gerados por semana.
- **Biblioteca de mídia** ("Base") com áudios, imagens e vídeos seus, reutilizáveis em qualquer vídeo.

## Requisitos

- Windows 10/11
- [Python 3.12](https://www.python.org/downloads/)
- [FFmpeg](https://ffmpeg.org/) com libass. O jeito mais simples é `winget install Gyan.FFmpeg`. O app encontra o FFmpeg no `PATH` ou na instalação do winget.
- Conexão com a internet (para narração, imagens por IA/fotos e publicação)

## Instalação

```bash
git clone https://github.com/TertulianoFre/AutoVideo.git
cd AutoVideo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Como rodar

Dê dois cliques em `iniciar.bat`: ele ativa o ambiente virtual, sobe o servidor e abre o navegador em `http://127.0.0.1:8080`.

Ou, manualmente:

```bash
.venv\Scripts\uvicorn backend.main:app --port 8080
```

Também é possível gerar um vídeo direto pelo terminal, sem a interface:

```bash
.venv\Scripts\python cli.py --titulo "Curiosidades sobre polvos" --imagem ia --duracao-alvo 1
```

Rode `python cli.py --help` para ver todas as opções.

## Configuração (opcional)

### Chaves de API gratuitas

Crie um arquivo `.env` na raiz do projeto (ele é ignorado pelo git). Nenhuma chave é obrigatória.

| Variável | Para quê | Onde obter |
|---|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` | Geração de texto (roteiro, agente). Os provedores com chave são usados em rodízio; sem nenhuma, o app usa a Pollinations.ai, que é gratuita e não precisa de chave. | console.groq.com, aistudio.google.com/apikey, console.mistral.ai, cloud.cerebras.ai, openrouter.ai/keys |
| `OLLAMA_MODEL`, `OLLAMA_VISION_MODEL` | Usar um modelo local via [Ollama](https://ollama.com), sem limite de uso | — |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY` | Mais variedade de fotos no estilo `foto` | pexels.com/api, pixabay.com/api/docs |

As chaves de texto também podem ser cadastradas pela própria interface.

### Publicação no YouTube

A publicação usa a YouTube Data API v3 com uma credencial OAuth sua. A configuração é feita uma única vez e vale para todos os canais:

1. Em [console.cloud.google.com](https://console.cloud.google.com/), crie um projeto e ative a **YouTube Data API v3**.
2. Em **Tela de permissão OAuth**, escolha o tipo *Externo*, mantenha em modo *Teste* e adicione como usuário de teste o e-mail de cada conta Google que for conectar.
3. Em **Credenciais**, crie um *ID do cliente OAuth* do tipo **App para computador** e baixe o JSON.
4. Salve o arquivo como `client_secret.json` na raiz do projeto.
5. No app, selecione o canal no topo do menu lateral e clique no perfil para autorizar a conta.

Em modo *Teste*, o Google expira a autorização a cada 7 dias. Quando o perfil mostrar "Não conectado", basta conectar de novo.

O agendador roda junto com o servidor e verifica a cada 10 minutos se há vídeos confirmados com a data de postagem vencida. Para rodar sem publicar nada (por exemplo, em testes), defina `YT_SEM_AGENDADOR=1`.

## Como funciona

```
título ─► roteiro ─► narração ─► cenas ─► imagens ─► legenda ─► montagem (FFmpeg) ─► thumbnail ─► agendamento ─► YouTube
```

O ponto de entrada do motor é `engine/pipeline.py:gerar_video`, usado tanto pela interface quanto pelo `cli.py`. Os vídeos são gerados um de cada vez, em fila, e cada um fica em uma pasta própria em `output/` com um `metadata.json` (roteiro, cenas, canal, agendamento, configurações da thumbnail).

### Estrutura do projeto

```
backend/     API FastAPI (main.py) e fila de geração (jobs.py)
frontend/    Interface web (HTML/JS) servida pelo backend
engine/      Motor de geração
  pipeline.py    orquestra a geração de um vídeo
  roteiro.py     roteiro e hashtags
  ia_texto.py    provedores de texto por IA, com rodízio e fallback
  tts.py         narração (edge-tts)
  alinhamento.py sincronia entre áudio, palavras e cenas
  scenes.py      divisão do roteiro em cenas
  visuals.py     imagens das cenas (procedural, fotos, IA)
  ambiente.py    síntese de som de fundo
  subtitles.py   legenda .ass estilo karaokê
  render.py      montagem com FFmpeg
  thumbnail.py   thumbnails 16:9 e 9:16
  canal.py       canais e seus contextos
  agente.py      agente em linguagem natural
  youtube.py     OAuth, upload e estatísticas
  agendador.py   publicação automática
  biblioteca.py  biblioteca de mídia (Base)
cli.py       geração pelo terminal
dados/       dados locais de uso (canais, tokens, biblioteca) — não versionados
output/      vídeos gerados — não versionados
```

## Stack

Python 3.12 · FastAPI + Uvicorn · FFmpeg · Pillow · NumPy · OpenCV (detecção de rosto nas fotos) · edge-tts · Pollinations.ai e provedores compatíveis com a API da OpenAI · deep-translator · Google API Client (YouTube Data API v3)

## Limitações conhecidas

- A publicação depende de o app estar rodando: não é um serviço em nuvem.
- Modelos de texto e imagem gratuitos às vezes produzem frases ou imagens estranhas. Use a pré-visualização do roteiro e o editor de cenas para revisar antes de publicar.
- O som de fundo sintetizado soa genérico. Para algo específico, importe um áudio seu na Base.
- Com narração gravada por você, a sincronia da legenda é aproximada, porque não há marcação de tempo por palavra como na voz gerada.
- Receita estimada não aparece no painel: o escopo de monetização do YouTube Analytics exige verificação do Google.
