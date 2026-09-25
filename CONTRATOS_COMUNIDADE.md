# Comunidade, dispositivos e dashboard — primeira entrega

Todas as rotas exigem `Authorization: Bearer <JWT>`. A identidade e o papel vêm do usuário autenticado no banco; o cliente não escolhe autor, destinatários arbitrários ou condição de atendente. Erros de validação retornam JSON `erro` com 400; acesso negado 403; registro ausente 404; convite já respondido/duplicado 409.

| Método e caminho | Entrada / resultado |
|---|---|
| GET `/api/guias` | Catálogo autenticado: ID, nome, cidade, estado, foto_url, verificado; não expõe documento, senha ou e-mail |
| GET `/api/conversas` | Conversas das quais a conta participa |
| POST `/api/conversas` | `{ "id_guia": "ID" }`; turista inicia conversa com guia ativo. Repetir retorna a mesma conversa |
| GET `/api/conversas/<id>/mensagens` | Últimas 100 mensagens em ordem cronológica, somente participantes |
| POST `/api/conversas/<id>/mensagens` | `{ "texto": "Mensagem" }`, até 2000 caracteres; autor definido no servidor |
| GET `/api/suporte` | Atendimentos próprios; admin lista todos |
| POST `/api/suporte` | `{ "assunto": "Até 120 caracteres", "texto": "Mensagem" }`; cria atendimento e primeira mensagem no mesmo lote |
| GET/POST `/api/suporte/<id>/mensagens` | Mesmo formato de mensagens; proprietário ou admin; apenas admin recebe `atendente: true` |
| GET `/api/convites-guias` | Convites/vínculos da agência ou guia autenticado |
| POST `/api/convites-guias` | Agência envia `{ "id_guia": "ID" }`; um convite por par agência/guia |
| PUT `/api/convites-guias/<id>` | Guia convidado envia `{ "status": "aceito" }` ou `recusado`; decisão só ocorre uma vez |
| POST `/api/usuarios/fcm-token` | `{ "token": "FCM", "dispositivo_id": "instalação" }`; registra conta autenticada e substitui token antigo da instalação |
| DELETE `/api/usuarios/fcm-token?dispositivo_id=...` | Remove somente a instalação da conta autenticada |
| POST `/api/usuarios/fcm-token/teste` | Envio de teste aos dispositivos da própria conta; `{ "enviados": 0, "falhas": 0 }` conta aceitações pelo FCM, não comprova recebimento |
| GET `/api/agendamentos/dashboard/<id_guia>` | Próprio guia/agência ou admin. `total_agendamentos`, `por_status` e `valor_declarado_ativo` |

O dashboard inclui reservas referenciadas pelo ID e pelo e-mail atual legado, sem duplicar documentos. Soma valores não negativos e finitos de reservas agendadas, em andamento ou concluídas; exclui canceladas e status desconhecidos. São valores declarados, sem conciliação com meio de pagamento. Os painéis Flutter continuam calculando seus indicadores pelos dados já carregados.

Coleções novas: `conversas` e `suporte` (subcoleção `mensagens`), `convites_guias` e `dispositivos_fcm`. O servidor usa o SDK administrativo: a autorização é aplicada pelas rotas, não pelas regras do cliente Firestore. Não foi feita migração nem alteração nas regras existentes. Consultas usam filtro único e ordenação simples; eventual configuração de índices desativados deve ser verificada no ambiente real.

## Interface e limites desta entrega

- O modo conectado substitui os avisos de indisponibilidade por listas e envio de mensagens. Botão Atualizar busca mensagens novas; não há tempo real, anexos, paginação anterior às últimas 100 mensagens nem confirmação de leitura.
- Agência escolhe guia no catálogo. Guia responde em Perfil → Convites de agências. Somente vínculos aceitos aparecem no seletor de responsável das trilhas, usando IDs. O backend rejeita atribuição arbitrária. A própria agência continua podendo assumir a trilha.
- Atendimento administrativo é possível pela API autenticada com conta admin, provisionada fora do cadastro público. O aplicativo ainda não possui login/home administrativos. Não há encerramento de atendimento, reenvio/revogação de convite ou painel de atendentes nesta etapa.
- Push possui registro, rotação, remoção e teste da própria conta. Não foram adicionados gatilhos automáticos de envio para mensagens ou reservas. As preferências específicas de reserva/marketing ainda não comandam envios externos.
- Configuração pública Firebase, VAPID, service worker e HTTPS/localhost são necessários para push web. Seguir `rotafacil_frontend/CONFIGURAR_FIREBASE_FCM.md`. Credenciais privadas existentes não foram alteradas.

## Validação

Testes automatizados usam HTTP e Firestore simulados, inclusive envio FCM simulado. Cobrem isolamento entre contas, autoria, suporte, convite/aceite, bloqueio de responsável sem vínculo, dispositivos e dashboard. Executar no backend `venv/Scripts/python.exe -m unittest discover -s tests -v`; no frontend `flutter analyze`, `flutter test` e `flutter test --dart-define=USE_BACKEND=true`.

Roteiro pendente com contas reais em ambiente de teste:

1. Turista inicia conversa com guia, envia mensagem; guia abre e atualiza, responde; terceiro usuário não deve acessar o histórico.
2. Turista abre atendimento; admin responde pela API; turista atualiza e vê a identificação da equipe.
3. Agência convida guia; guia aceita; agência atualiza e cria trilha com o guia. Testar também recusa com outro par de contas.
4. Registrar duas instalações FCM, girar token, sair de uma instalação e conferir que a outra permanece inscrita. Usar teste de push da própria conta, conferir primeiro e segundo plano e remoção de token inválido.
5. Comparar dashboard com reservas reais, incluindo cancelamento e responsável legado por e-mail.

Nenhuma conta, mensagem, convite ou envio externo real foi criado durante os testes automatizados. A aprovação de uso real desses recursos depende dessa validação.
