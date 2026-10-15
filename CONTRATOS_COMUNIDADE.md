# Catalogo de guias, convites, dispositivos e dashboard

Revisao de escopo: 13/10/2026. Conversas internas e atendimento por mensagens foram removidos do backend. O modulo community permanece responsavel pelo catalogo, pelos vinculos entre agencias e guias e pelos dispositivos FCM.

Todas as rotas abaixo exigem `Authorization: Bearer <JWT>`. Identidade e papel sao obtidos pelo servidor. Erros de validacao retornam 400; acesso negado, 403; registro ausente, 404; convite duplicado ou ja respondido, 409.

| Metodo e caminho | Entrada e resultado |
|---|---|
| GET `/api/guias` | Catalogo de guias ativos: id, nome, cidade, estado, foto_url e verificado. Nao expoe documento, senha ou e-mail. |
| GET `/api/convites-guias` | Convites e vinculos da conta autenticada. |
| POST `/api/convites-guias` | Agencia envia `{ "id_guia": "ID" }`. Um convite por par agencia/guia. |
| PUT `/api/convites-guias/<id>` | Guia convidado envia `{ "status": "aceito" }` ou `recusado`. Resposta unica. |
| POST `/api/usuarios/fcm-token` | `{ "token": "FCM", "dispositivo_id": "instalacao" }`. Substitui token antigo da mesma instalacao e conta. |
| DELETE `/api/usuarios/fcm-token?dispositivo_id=...` | Remove apenas a instalacao da conta autenticada. |
| POST `/api/usuarios/fcm-token/teste` | Testa envio para a propria conta. Retorna `enviados` e `falhas`; aceitacao pelo FCM nao comprova recebimento. |
| GET `/api/agendamentos/dashboard/<id_guia>` | Proprio guia/agencia ou admin. Retorna `total_agendamentos`, `por_status` e `valor_declarado_ativo`. |

Convites aceitos permitem vincular guias ativos a trilhas da agencia. A agencia tambem pode assumir suas proprias trilhas. A agência pode revogar convite pendente e reenviar convite recusado, revogado ou desligado. Agência e guia podem encerrar vínculo aceito quando não há reservas ativas; as trilhas passam para responsabilidade da agência.

O dashboard considera referencias por ID e e-mail legado sem duplicacao. Soma valores declarados nao negativos e finitos de reservas pendentes, agendadas, confirmadas, em andamento e concluidas. Exclui cancelamentos e status desconhecidos. Nao representa conciliacao de pagamentos.

Colecoes utilizadas por este modulo: `convites_guias` e `dispositivos_fcm`. A autorizacao e aplicada pelo backend, que usa SDK administrativo do Firebase.

## Notificacoes e configuracao

POST/DELETE `/api/usuarios/fcm-token` possuem uma unica implementacao, no blueprint community, com contrato por instalacao. A fonte de tokens e `dispositivos_fcm`.

O teste de push e os eventos de reserva usam `PushDevices.send`. `Notificacoes.notificar_usuario` delega para esse envio e preserva dados do evento. Falhas de push nao interrompem cadastro de reserva, cancelamento ou verificacao de perfil. Tokens invalidos sao removidos com controle de concorrencia. Tokens antigos em `usuarios.fcm_tokens` nao sao mais consultados; dispositivos precisam ser registrados novamente. Nao foi executada migracao ou exclusao de dados reais.

Para push web, configure Firebase publico, VAPID, service worker e HTTPS ou localhost. Consulte `rotafacil_frontend/CONFIGURAR_FIREBASE_FCM.md`. Preferencias por evento e recebimento real precisam de homologacao.

## Validacao

Execute no backend `venv/Scripts/python.exe -m unittest discover -s tests -v`. Os testes usam banco e envio FCM simulados. Cobrem catalogo, validacao de identificadores, convite e aceite, vinculo de trilhas, dispositivos, dashboard e ausencia das rotas removidas.

Homologue com contas de teste: convite e aceite, criacao de trilha com guia vinculado, rotacao e remocao de tokens, recebimento real de push e dashboard com reservas canceladas e referencias legadas.

Esta alteracao remove implementacoes e contratos de mensagens. Nao executa exclusao de dados existentes no Firestore.


## Desativação de trilhas com reservas

DELETE /api/trilhas/<id> desativa a trilha e preserva documentos. Se houver reservas não encerradas, responde HTTP 409 e mantém a trilha ativa. A mesma regra vale para PUT com ativo=false. Apenas cancelamentos e conclusões liberam a desativação; registros históricos não são removidos. Falha na consulta impede a desativação e retorna erro.


## Dados exibidos nas trilhas

As respostas de listagem, busca e detalhe acrescentam nome_guia com o nome público do responsável referenciado por id_guia, incluindo identificadores antigos por e-mail. Apenas o nome é incorporado do documento de usuário; nenhum campo privado adicional é retornado. A ausência de responsável válido resulta em nome_guia nulo.

distancia_km, quando enviado em criação ou edição, deve ser numérico, positivo e finito. Vírgula decimal é normalizada para ponto antes da persistência. Valores inválidos retornam HTTP 400. Registros antigos sem distância estruturada não são corrigidos automaticamente a partir da descrição.

## Exclusão segura da conta

DELETE `/api/usuarios/<id>` e DELETE `/api/usuarios/email/<email>` aceitam apenas o próprio usuário ou administrador. A API responde HTTP 409 quando existe reserva pendente, agendada, confirmada ou em andamento ligada ao participante, ao guia responsável ou às atividades da agência.

Sem compromissos ativos, a API remove dados privados e temporários da conta: favoritos, dispositivos FCM, disponibilidades, tokens de redefinição e convites. Reservas encerradas permanecem no histórico. Atividades criadas pela conta são desativadas e atribuições do guia excluído são removidas.

## Alteração do tipo da conta

PUT `/api/usuarios/<id>/tipo` aceita o próprio usuário ou administrador. A operação responde HTTP 409 enquanto houver reservas ativas ligadas à conta. O perfil guia exige CPF válido; agência exige CNPJ válido. Ao sair de um perfil profissional, a API desativa atividades próprias, remove atribuições e elimina vínculos incompatíveis. O cliente encerra a sessão e exige novo login após a alteração.

## Documentos profissionais

GET e POST `/api/documentos-profissionais/` permitem ao guia ou à agência listar e enviar seus documentos. O envio usa multipart com `arquivo` e `tipo_documento`. São aceitas imagens JPG, PNG e WEBP de até 5 MB. O arquivo fica no Firebase Storage privado; a resposta não contém URL pública nem caminho interno.

GET `/api/documentos-profissionais/<id>/arquivo` entrega o conteúdo somente ao dono ou administrador. DELETE `/api/documentos-profissionais/<id>` permite ao dono remover documentos pendentes ou rejeitados; documentos aprovados exigem ação administrativa. PUT `/api/documentos-profissionais/<id>/analise` aceita `aprovado` ou `rejeitado` apenas para admin e atualiza a verificação do perfil. Rejeição exige uma observação.

Configure `FIREBASE_STORAGE_BUCKET` e conceda à conta de serviço acesso ao bucket. Sem essa variável, rotas que manipulam arquivos respondem HTTP 503.
