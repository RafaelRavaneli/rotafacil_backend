# Checklist do roteiro e preparação pessoal

## Escopo

Primeiro tópico da conclusão da primeira versão. Alterações locais, sem publicação. A homologação integrada com usuários será realizada ao final do planejamento, conforme decisão do usuário.

## Dados do roteiro

`itens_obrigatorios` e `itens_recomendados` são listas opcionais de textos. Cada lista aceita até 50 itens com 1 a 120 caracteres. O serviço normaliza espaços e elimina duplicatas dentro de cada lista. Na apresentação conjunta, itens obrigatórios têm prioridade sobre recomendados com o mesmo nome normalizado.

Roteiros anteriores, sem `itens_obrigatorios`, continuam funcionando. As permissões existentes de gestão permanecem: agência administra seus roteiros; o guia vinculado mantém acesso de consulta.

## Preparação pessoal

- `GET /api/agendamentos/{id_agendamento}/checklist`: consulta itens atuais e marcações particulares.
- `PATCH /api/agendamentos/{id_agendamento}/checklist`: recebe exclusivamente `id_item` e `marcado` booleano.
- Apenas o turista dono da reserva acessa essas rotas. Outros turistas, guias, agências e administradores recebem 403.
- Reservas pendentes, agendadas, confirmadas ou em andamento permitem preparação. Reservas canceladas, recusadas e concluídas são somente leitura.
- O checklist é separado por reserva; duas datas do mesmo roteiro não compartilham preparação.
- A identificação do item é SHA-256 do nome em letras minúsculas e com espaços normalizados. Mudança de capitalização ou de classificação obrigatório/recomendado preserva a marcação. Um item com novo nome começa desmarcado; itens removidos não são exibidos nem podem receber novas marcações.

## Persistência e privacidade

Coleção `checklists_pessoais`, com ID igual ao da reserva e campos `id_usuario`, `id_agendamento`, `id_trilha`, `marcados` e `atualizado_em`. O serviço escreve apenas a chave do item alterado usando merge, preservando outras marcações. Os dados não são incorporados às respostas de reservas ou inscritos enviadas aos organizadores.

A exclusão da conta elimina os documentos associados a `id_usuario`. A coleção é criada sob demanda, sem migração em massa de reservas ou necessidade de índice composto novo.

## Falhas

Falhas de leitura ou gravação retornam 503 com mensagem genérica. A interface não confirma uma marcação até receber a resposta de sucesso. O usuário pode atualizar ou tentar novamente; uma falha do checklist não impede consultar os demais dados da reserva.

## Verificação

Testes isolados e de rota autenticada cobrem validação, persistência, separação entre reservas e usuários, permissões, estado encerrado, alteração dos itens, compatibilidade com listas antigas e indisponibilidade do armazenamento. Não utilizam Firebase real nem publicam alterações.
