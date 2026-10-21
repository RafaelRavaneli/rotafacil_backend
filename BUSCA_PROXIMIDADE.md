# Busca por proximidade

Implementação local do tópico 6. Não publicada nem executada contra o banco de produção.

## Consulta

`GET /api/trilhas/busca` recebe `latitude`, `longitude` e `raio_km` juntos. Aceita coordenadas finitas nos intervalos geográficos e raio de 0 a 100 km. Zero representa somente o ponto, com tolerância numérica de um micrômetro; não desativa o filtro. Coordenadas ausentes/parciais, NaN, infinito ou raio inválido retornam 400.

A consulta cobre a caixa esférica que contém a circunferência usando até 64 prefixos geohash. Inclui células vizinhas, polos e antimeridiano. Consulta o índice ascendente simples de geohash e deduplica candidatos; refina pelo cálculo Haversine no servidor. Filtros de cidade, UF, dificuldade, atividade, período (qualquer saída) e todos os recursos de acessibilidade selecionados são aplicados antes de paginar. Roteiros inativos, suspensos ou de responsáveis bloqueados não entram. A distância é em linha reta, não a distância por estrada.

A resposta geográfica inclui `distancia_usuario_km` sem arredondamento antes da ordenação. A ordem é distância e ID como desempate. O frontend apenas formata esse valor para exibição em uma casa decimal. Mapa e lista usam os mesmos resultados carregados.

## Paginação

Enviar `pagina` (a partir de 1) e `tamanho` (1–100; padrão 30) retorna `{itens, total, pagina, proxima_pagina}`. Página vazia retorna 200 com lista vazia. O refinamento e a ordenação ocorrem antes do corte: candidatos falsos positivos de uma célula não consomem vagas da página. Clientes antigos sem `pagina` continuam recebendo a lista legada e 404 se vazia.

Busca e carrossel têm Carregar mais. Alterar filtros, atualizar dados ou retornar à janela reinicia a busca. Respostas antigas não substituem uma busca mais recente. Página não é uma fotografia permanente do banco: se o catálogo mudar entre páginas, reinicie na página 1. A deduplicação no cliente evita repetição de cards durante essa transição.

## Localização e interface

Carrossel consulta raio fixo de 100 km no servidor; pesquisa usa o raio escolhido. Falha de permissão/GPS mostra orientação e mantém busca por cidade/UF. Coordenadas antigas persistidas não são usadas silenciosamente após negar permissão. O serviço compartilhado confere a permissão atual antes de reutilizar posição recente de até um minuto.

Não há fallback para filtrar o catálogo local em modo backend quando a API falha. O modo demonstrativo continua funcionando sem servidor. O catálogo geral usado pelas outras seções da home permanece independente; este tópico não altera sua estratégia de carga.

## Índice e dados legados — etapa de publicação futura

`firestore.indexes.json` declara explicitamente o índice simples ascendente de `trilhas.geohash`. Índices compostos anteriores são preservados; a nova consulta geográfica não depende deles. Novos roteiros e alterações parciais de coordenadas gravam geohash de precisão 9.

Antes de disponibilizar esta versão, verificar o projeto Firebase de destino e executar a inspeção:

```text
python scripts/atualizar_indice_proximidade.py
```

Por padrão, apenas conta índices corretos/pendentes e registros sem coordenadas válidas, sem expor dados. Depois de revisar a inspeção, aplicar na etapa de publicação autorizada:

```text
python scripts/atualizar_indice_proximidade.py --aplicar
```

A atualização é idempotente e usa controle de versão para não sobrescrever uma edição simultânea. Executar nova inspeção após conflitos. Roteiros sem coordenadas válidas continuam fora da proximidade e precisam de correção pelo organizador. Registros com coordenadas válidas mas sem geohash só entram após atualizar o índice: não há varredura completa silenciosa como fallback.

## Limites e validação

Não há corte arbitrário de candidatos: todas as células cobertas são lidas e refinadas. Cada página recalcula o conjunto e as estatísticas públicas; monitorar leituras/latência com o crescimento do catálogo. Para escala maior, avaliar mecanismo espacial especializado e paginação por fotografia, preservando a correção nas fronteiras.

Testes locais cobrem coordenadas zero/ausentes/inválidas, raio 0 e 100 km, dentro/fora, células vizinhas, polos, antimeridiano, 65 resultados em três páginas, empate, filtro combinado, segunda saída e atualização idempotente do índice. Frontend usa API simulada para validar parâmetros, distância, erro/repetição e permissão negada. Homologação manual em Android/iOS/desktop e banco real fica para a etapa final autorizada.
