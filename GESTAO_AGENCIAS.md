# Gestão dos roteiros de agência

O campo `criado_por` continua identificando o proprietário do roteiro, por ID ou e-mail. O campo `id_guia` indica quem executa a atividade. A atribuição não transfere a gestão.

- A agência proprietária edita, desativa e arquiva seus roteiros e gerencia os inscritos: confirma, recusa, cancela e finaliza as saídas.
- O guia atribuído consulta as informações do roteiro e vê as datas na agenda. As reservas da agência não entram na lista nem nos indicadores financeiros do guia.
- Telefones de participantes e contatos de emergência ficam disponíveis à agência proprietária durante o vínculo autorizado. O guia continua gerenciando reservas de roteiros próprios.
- Reservas de roteiros de agência retornam `id_agencia`, `nome_agencia` e `telefone_agencia`. O telefone do guia não é retornado nesses casos. O contato do turista usa a agência, mesmo quando ela não informou telefone; não há fallback para o guia.
- Notificações de novas reservas e de cancelamentos feitos pelo turista são encaminhadas ao proprietário do roteiro.

A regra operacional reutiliza a autorização de propriedade de `Trilhas` por meio de `Agendamentos._usuario_pode_operar_agendamento`. Listagem, indicadores, ações e acesso a contatos usam essa mesma decisão. Não há migração de banco.

Registros legados sem criador continuam sob gestão do guia responsável. Reservas históricas sem roteiro mantêm o comportamento legado.
