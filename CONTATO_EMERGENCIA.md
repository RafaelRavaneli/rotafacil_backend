# Contato de emergência com acesso controlado

Tópico obrigatório: https://trello.com/c/4shFSEvN. Implementação local, sem publicação.

## Perfil e autorização

O turista informa nome (até 120 caracteres), telefone (10 a 15 dígitos, até 30 caracteres formatados), relação (até 80 caracteres) e consentimento booleano explícito. Dados antigos não recebem consentimento automático. O perfil permite editar, retirar autorização e remover o contato ao salvar. Não há exigência de cadastrar contato para reservar.

Campos: `contato_emergencia_nome`, `contato_emergencia_telefone`, `contato_emergencia_relacao`, `contato_emergencia_consentimento`. O backend controla `contato_emergencia_consentimento_em`; o cliente não pode fornecer esse horário. Autorizar exige os três dados preenchidos. Alteração do contato por cliente antigo sem o campo de consentimento retira a autorização, em vez de renová-la implicitamente. O formulário atual envia a escolha explicitamente.

Informações ficam no perfil protegido do próprio usuário. Listagem administrativa e consultas administrativas a perfis de outras pessoas removem todos os campos `contato_emergencia_*`. Admin não pode conceder autorização em nome do turista. Cadastro público não concede autorização nem recebe contato operacional: o contato é preenchido no perfil autenticado.

## Consulta operacional

`GET /api/usuarios/{id}/contato-emergencia?id_agendamento={reserva}` exige autenticação de guia/agência e todas as condições:

1. Reserva pertence ao turista solicitado e está confirmada, agendada ou em andamento. Pendente, recusada, cancelada ou concluída não autoriza consulta.
2. Solicitante é o responsável operacional atual pelo roteiro. Em roteiro da agência, somente a agência consulta o contato do participante. O guia atribuído mantém consulta às informações do roteiro e exibição na agenda, conforme a arquitetura existente.
3. Roteiro existe e a reserva tem início e fim válidos. Janela: desde 24 horas antes do início até o término. Horários legados sem offset usam UTC-3. Fora da janela, acesso negado mesmo que o status ainda não tenha sido atualizado.
4. Turista mantém consentimento verdadeiro e contato completo.
5. Registro de auditoria é gravado antes de devolver os dados. Se a gravação falha, a resposta é 503 e não contém contato.

A consulta retorna nome do participante, nome/telefone/relação do contato. Não retorna telefone adicional do participante. Admin não possui bypass. Cancelamento, conclusão, fim da janela, remoção do roteiro, troca de responsável e retirada do consentimento bloqueiam novas consultas.

As respostas do perfil e da consulta usam `Cache-Control: no-store, private`. O frontend consulta sob demanda e não adiciona o contato ao modelo/listagem de reservas nem a notificações.

## Auditoria

Coleção `consultas_emergencia`: somente IDs de usuário, solicitante, reserva e roteiro, papel do solicitante e horário do servidor. Nunca nome, relação ou telefone. Não há API pública para consultar essa coleção. Remover o contato não copia seus valores para um histórico; auditoria registra apenas referências. Exclusão da conta remove consultas vinculadas ao turista, respeitando a regra existente que impede excluir contas com compromissos ativos.

## Organizador

Roteiro oferece `emergencia_organizador_telefone` (telefone público do responsável operacional) e `emergencia_instrucoes` (até 1500 caracteres). Guia/agência cadastra e edita. Detalhes do roteiro e da reserva exibem esses dados e botão de ligação. Ausência é informada explicitamente. Em roteiro de agência, preencher telefone da própria agência. Esses campos não são o contato particular do turista.

## Continuidade

Sem migração obrigatória: campos opcionais; consentimento ausente equivale a não autorizado. A primeira consulta autorizada cria auditoria. Nenhum novo índice composto é necessário. Contrato documentado em `static/openapi.json` no backend.

Homologação manual, publicação e testes integrados em produção ficam para o encerramento da primeira versão. Os tópicos anteriores e a correção de UF/cidade permanecem locais e preservados.
