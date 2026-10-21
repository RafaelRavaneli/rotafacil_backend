# Administração: contas, bloqueios, verificação e roteiros

Tópico obrigatório: https://trello.com/c/D6MdjNTW. Implementação local, sem publicação.

## Acesso e painel

Papel admin já existente é validado no banco a cada chamada autenticada; não basta um papel gravado no navegador ou enviado no token. Cadastro público não cria admins. Não há promoção pública para esse papel.

Console separado oferece contas, roteiros e histórico. Pesquisa e filtros por tipo/situação são aplicados no servidor. Links abrem verificação de documentos e moderação de avaliações. URLs autenticadas: `/admin/contas`, `/admin/roteiros`, `/admin/historico`, `/admin/documentos`, `/admin/avaliacoes`.

Contas mostram somente dados operacionais necessários: identificador, nome, e-mail, tipo, cidade/UF, Cadastur e estados ativo/verificado. Nunca senha, documento pessoal ou contato de emergência. Histórico de avaliações continua integrado ao módulo anterior; consultas administrativas não possuem bypass de acesso ao contato de emergência.

## Bloqueio e sessões

Bloquear define `ativo=false` e incrementa `versao_auth`. Middleware consulta o estado atual e recusa todas as chamadas da conta bloqueada, inclusive com token emitido anteriormente. Login já recusava contas inativas. Frontend encerra a sessão ao receber `CONTA_BLOQUEADA` e orienta procurar atendimento.

Desbloquear também incrementa a versão de autenticação: tokens antigos continuam inválidos e é necessário entrar novamente. Bloqueio não exclui usuário, reservas, avaliações, vínculos ou roteiros. Roteiros de responsável ou guia atribuído bloqueado deixam de aceitar novas reservas e não aparecem como ativos na descoberta.

Não é permitido bloquear ou alterar contas administrativas por essas ações, nem usar exclusão/mudança de tipo de perfil para remover ou rebaixar admin. Não há edição administrativa genérica de outros perfis: o painel oferece ações explícitas auditadas. Admin não assume operações de confirmação, cancelamento ou conclusão de reservas do guia/agência.

## Verificação

Verificar e remover selo exigem guia/agência e motivo. Conta bloqueada não pode receber selo até ser desbloqueada. Alteração aparece nos perfis públicos. Remoção manual define `verificacao_suspensa_admin=true`; uma análise posterior de documento não restaura o selo automaticamente. Nova decisão explícita de verificar remove essa suspensão.

Análise de documentos existente também registra ação administrativa. Aprovação e rejeição mantêm as validações anteriores, com observação de até 500 caracteres. O endpoint legado `/api/usuarios/{id}/verificar` exige booleano e motivo e delega ao mesmo serviço auditado. O caminho antigo sem motivo deixa de ser aceito.

## Moderação de roteiros

Suspender define `bloqueado_moderacao=true`; liberar remove essa restrição. O campo `ativo` escolhido pelo organizador permanece preservado. Assim, liberar suspensão não reativa um roteiro que já estava inativo, nem libera um responsável bloqueado.

Busca e cálculo de disponibilidade consideram a restrição antes de permitir novas reservas. Reservas existentes não são canceladas automaticamente. Usuário comum não altera os campos administrativos por edição do roteiro. Admin modera por operações específicas com histórico, sem editar/excluir conteúdo pelas rotas genéricas do organizador.

No painel, filtros distinguem ativos, inativos, suspensos e responsável bloqueado. Suspensão específica e indisponibilidade por conta bloqueada são estados diferentes.

## Auditoria

Coleção `historico_admin`: tipo/identificador do alvo, ID de admin, ação, motivo, horário UTC, estados operacionais anterior/novo e resultado. Não copia perfil completo, senha, documentos ou contato de emergência. Motivos devem evitar dados pessoais desnecessários.

Solicitação é registrada antes da alteração. Falha ao gravar auditoria impede aplicar a ação. Atualização usa controle de versão; conflito não sobrescreve alteração concorrente. Histórico diferencia solicitação, conflito e ação aplicada. Se a confirmação final falhar, a API orienta recarregar antes de repetir; estado real deve ser conferido.

Histórico agrega decisões de avaliações, permite filtro por tipo e identificador do alvo e mostra os 500 registros mais recentes do resultado. Histórico antigo não é inventado retroativamente. Respostas administrativas usam `Cache-Control: no-store, private`.

## API e dados

- `GET /api/admin/contas`: filtros `tipo`, `estado`, `q`.
- `POST /api/admin/contas/{id}/acao`: bloquear, desbloquear, verificar, remover_verificacao.
- `GET /api/admin/roteiros`: filtros `estado`, `q`.
- `POST /api/admin/roteiros/{id}/acao`: suspender, liberar.
- `GET /api/admin/historico`: filtros `tipo`, `id_alvo`.

Ações recebem apenas `acao` e `motivo` (3 a 500 caracteres). Servidor define o autor e o horário. Contrato OpenAPI atualizado. Campos novos são opcionais em dados antigos: ausência de bloqueio/moderação não bloqueia conta ou roteiro. Sem migração obrigatória nem índice composto novo. Administradores devem ser provisionados por procedimento privado existente, nunca pelo cadastro público.

Homologação manual integrada e publicação ficam para o encerramento combinado. Nenhum teste manual do Trello é considerado concluído somente por testes automatizados.
