# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona (visão geral do produto)

1. **Agente** pesquisa tendências na web (agendado ou sob pedido) e sugere ideias de vídeo.
2. **Você** aprova uma sugestão ou digita seu próprio título/descrição.
3. **Geração**: roteiro, narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação) e legenda sincronizada.
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts).
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube.
6. **Painel**: acompanha inscritos, visualizações, tempo de exibição e receita estimada do canal.

Tudo roda localmente no Windows, sem custo de API paga.

## Motor de geração — como funciona por dentro

Diagrama completo (fluxo principal + cada serviço externo usado): https://claude.ai/artifact/EaS2eEAc3MtsY3nrjSjeyx

Resumo do fluxo (`engine/`, testável pelo `cli.py`):

1. **Narração** (`engine/tts.py`) — `edge-tts` (Microsoft, grátis) gera o áudio e o tempo exato de cada palavra falada.
2. **Cenas** (`engine/scenes.py`) — o roteiro é dividido em cenas por frase (~5s cada), cada uma vai ganhar sua própria imagem de fundo.
3. **Imagem de cada cena** (`engine/visuals.py`) — três estilos escolhíveis:
   - `procedural`: gradiente gerado com Pillow, 100% local, sem internet.
   - `foto`: foto real — tenta o Openverse.org primeiro (grátis, sem chave), depois o Pexels (grátis, precisa de `PEXELS_API_KEY`). Se a foto encontrada tiver um rosto grande/de perto (detector local do OpenCV), tenta a outra fonte antes de desistir.
   - `ia`: traduz a cena pro inglês (MyMemory Translator, grátis), troca verbos de expressão facial de risco (bocejar, gritar...) por uma descrição de cena mais genérica, e gera a imagem via Pollinations.ai em estilo desenho 2D (grátis, sem chave). Até 3 tentativas; se falhar, cai pro procedural.
4. **Legenda** (`engine/subtitles.py`) — arquivo `.ass` com destaque de cor por palavra (efeito "karaokê"), sincronizado com a narração. Duração real avisada no final; dá pra passar uma duração alvo (`--duracao-alvo`, em minutos) e o motor avisa se o roteiro está curto/longo demais pra bater a meta.
5. **Montagem** (`engine/render.py`) — FFmpeg junta as imagens (slideshow, uma por cena) + narração + legenda queimada, exporta 16:9 e 9:16.

### Limitações conhecidas

- O estilo `ia` ainda pode gerar imagens estranhas em assuntos muito específicos/incomuns (a lista de palavras de risco cobre os casos vistos até agora, mas não é exaustiva).
- Checagem automática de "imagem com qualidade ruim, refazer" foi tentada com detector de rosto (OpenCV) — funciona bem em foto real, mas **não funciona em desenho/ilustração** (o detector é treinado pra foto), então só está ligada no estilo `foto`.
- Duração do vídeo ainda depende 100% do tamanho do roteiro que você escreve — não existe ainda geração automática de roteiro maior/menor pra bater uma meta de duração (depende do "próximo passo" de geração de roteiro por IA).
- Vídeo "ambiente" (ex: 30 min só de som de chuva, sem narração/legenda) não é suportado — o motor é construído em cima de narração falada. Seria um modo separado, ainda não construído.

## Requisitos já levantados, ainda não implementados

- Botão de **regenerar vídeo** na tela "Novo vídeo", caso o resultado não fique bom.
- **Geração de thumbnail**, com prévia editável (poder pedir pra alterar).
- Poder **pedir alterações** num vídeo já gerado (não só regenerar do zero).
- **Barra de progresso real** na tela "Novo vídeo" (etapa atual: narração → imagens → montagem), não uma barra fake.
- Botão de **baixar o vídeo em .mp4** direto da tela.
- **Geração automática de roteiro** a partir de só um título (pra controlar duração de verdade, e pra não precisar escrever o roteiro à mão).
- **Modo vídeo ambiente** (som contínuo tipo chuva + imagem, sem narração, duração longa).

## Stack

- Python 3.12
- FFmpeg (montagem de vídeo/áudio/legenda, com libass)
- Pillow (imagens de fundo procedurais)
- edge-tts (narração, voz neural gratuita da Microsoft)
- requests + deep-translator (busca de fotos e tradução de prompt)
- opencv-python-headless (detector de rosto, usado no estilo `foto`)
- YouTube Data API v3 (publicação agendada) + YouTube Analytics API (painel) — ainda não integrado
- Git para versionar o projeto

## Status

Motor de geração de vídeo funcionando (narração, cenas, 3 estilos de imagem, legenda com destaque, aviso de duração, montagem em 16:9 e 9:16). Próximo: geração automática de roteiro (resolve duração de verdade), depois partir para a tela real do app (Painel, Novo Vídeo, Agente, Fila).

## Próximos passos

1. Geração automática de roteiro a partir de um título (permite controlar duração de verdade)
2. Estrutura do backend + tela real do app (ligando no motor já pronto)
3. Configurar projeto no Google Cloud Console + credenciais OAuth da YouTube Data API
4. Integração da publicação agendada
