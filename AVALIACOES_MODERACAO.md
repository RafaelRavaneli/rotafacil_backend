# Avaliações por reserva e moderação

Tópico obrigatório: https://trello.com/c/l6wBwk4k. Alterações locais, sem publicação.

## Regras

- Turista autenticado avalia somente a própria reserva concluída pelo responsável. Reserva pendente, confirmada, cancelada ou de outra pessoa não permite envio.
- Uma avaliação por reserva; reservas diferentes do mesmo roteiro permitem avaliações diferentes. Identificador de reserva é a chave do novo registro. Criação usa operação exclusiva para não sobrescrever uma avaliação concorrente.
- Notas inteiras de 0 a 5 para roteiro e, quando vinculados, guia/agência. Zero é válido. Comentário opcional, até 500 caracteres. Autor, data e vínculos são definidos no servidor; campos de média ou moderação enviados pelo cliente são rejeitados.
- Autor pode editar até 7 dias após a criação, somente enquanto a avaliação está publicada e a reserva continua concluída. Editar não renova o prazo. Avaliação ocultada não pode ser editada para contornar a moderação.
- Data e autor aparecem nas listas. Datas nativas do Firestore são convertidas em ISO para exibição consistente.

Clientes antigos que omitem a reserva só são atendidos se houver uma única reserva concluída correspondente. Mais de uma exige seleção explícita. Avaliações legadas sem vínculo/data continuam visíveis como conteúdo histórico; não recebem novo prazo de edição automaticamente. Não existe migração que invente datas de criação ou reservas para esses registros.

## Médias e exibição

Média e quantidade são calculadas no servidor, somente com notas válidas de avaliações publicadas. O cálculo inclui zero e exclui conteúdo ocultado. O catálogo de roteiros e o catálogo/perfil profissional consultam as avaliações reais, evitando que contadores demonstrativos ou caches antigos determinem a classificação. Os contadores persistidos também são recalculados nas alterações.

A home continua usando o carrossel Melhores avaliados existente, agora alimentado por esses dados. Criar/editar/moderar provoca atualização dos dados do aplicativo. Painel de avaliações oferece recarga, repete leitura ao retornar à janela e acompanha atualizações do AppStore. Perfil do organizador oferece recarga explícita dos dados e médias.

Guia possui avaliações em seu perfil existente. Agência/organizador possui perfil com campos públicos mínimos (nome, tipo, cidade/UF, apresentação, verificação, médias) e avaliações. Acesso pelo roteiro e, para agência, também pelos detalhes da reserva. URL `/profissional/{id}` é recuperável na inicialização autenticada. Nenhum documento, e-mail ou telefone privado é incluído nesse perfil.

## Denúncia e moderação

- Pessoa autenticada pode denunciar avaliação publicada de outra pessoa, com motivo entre conteúdo ofensivo, dados pessoais, spam e outro; descrição opcional de até 500 caracteres.
- Uma denúncia por pessoa/avaliação. Denúncia não oculta conteúdo automaticamente nem altera média.
- Admin acessa o painel pelo botão Moderar avaliações na área de verificação profissional. Filtros: denúncias pendentes, todas, publicadas e ocultas.
- Admin pode ocultar, restaurar ou manter conteúdo, sempre com motivo de 3 a 500 caracteres. Decisões registram ID administrativo, avaliação, ação, motivo, horário e resultado. A solicitação é registrada antes de alterar o conteúdo; falha de auditoria impede a alteração. Conflito concorrente não sobrescreve a versão alterada por outro usuário.
- Denúncias presentes na decisão ficam analisadas; novas denúncias posteriores permanecem para análise.
- Listas públicas não expõem denunciantes, IDs de participantes/reservas ou histórico administrativo. Dados administrativos ficam em rotas protegidas. Respostas usam `Cache-Control: no-store, private`.

Coleções novas: `denuncias_avaliacoes` e `historico_moderacao_avaliacoes`. Registros de avaliações ganham estado de moderação e horário de edição. Ausência de estado nas avaliações legadas significa publicada. Consultas usam igualdade simples; nenhum índice composto novo é necessário.

## API

- `POST /api/avaliacoes/`: criar.
- `GET /api/avaliacoes/trilha/{id}`: conteúdo publicado do roteiro.
- `GET /api/avaliacoes/profissional/{id}` e `/perfil`: avaliações e perfil público mínimo de guia/agência.
- `GET /api/avaliacoes/reserva/{id}`: avaliação própria e permissão de editar.
- `PATCH /api/avaliacoes/{id}`: edição autorizada.
- `POST /api/avaliacoes/{id}/denunciar`: denúncia.
- `GET /api/avaliacoes/moderacao`: fila, estados, denúncias e histórico; exclusivo admin.
- `POST /api/avaliacoes/{id}/moderar`: decisão com motivo; exclusivo admin.

Contrato em `static/openapi.json` no backend. Diálogos com campos aguardam a animação de saída antes de liberar controladores, evitando erro de navegação/fechamento.

Homologação manual e publicação ficam para o encerramento combinado. Administração geral de contas/roteiros continua outro tópico e não foi iniciada.
