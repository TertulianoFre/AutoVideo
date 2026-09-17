# Projeto YT

Canal de YouTube com vídeos gerados por automação (texto → narração → imagem → legenda), testando viabilidade de monetização.

## Como funciona

1. **Agente** pesquisa tendências na web (agendado ou sob pedido) e sugere ideias de vídeo.
2. **Você** aprova uma sugestão ou digita seu próprio título/descrição.
3. **Geração**: roteiro, narração (voz de IA — mulher, homem ou criança, em vários idiomas — ou sua própria gravação) e legenda sincronizada.
4. **Montagem** via FFmpeg: exporta em 16:9 (vídeo normal) e 9:16 (Shorts).
5. **Publicação**: você agenda a data e o app publica sozinho no YouTube.
6. **Painel**: acompanha inscritos, visualizações, tempo de exibição e receita estimada do canal.

Tudo roda localmente no Windows, sem custo de API paga.

## Stack

- Python
- FFmpeg (montagem de vídeo/áudio/legenda)
- Pillow (imagens de fundo)
- Motor de voz neural gratuito (a definir — favorito: edge-tts)
- YouTube Data API v3 (publicação agendada) + YouTube Analytics API (painel)
- Git para versionar o projeto

## Status

Em fase de design — ver os sketches do painel e o esquema de arquitetura antes de começar a implementação.

## Próximos passos

1. Configurar projeto no Google Cloud Console + credenciais OAuth da YouTube Data API
2. Estrutura de pastas e primeiro script do pipeline de geração de vídeo
3. Integração da publicação agendada
