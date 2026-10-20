# E-mail de autenticação — configuração e checkpoint

> Atualização local de 20/10/2026, ainda sem publicação: as interfaces de confirmação e recuperação passam a usar links e iniciar sessão após validação. O contrato e as garantias atuais estão em [LINKS_AUTENTICACAO.md](LINKS_AUTENTICACAO.md). As referências a cópia de códigos abaixo descrevem a implementação anterior.

## Decisões de 20/10/2026

- Remetente: `nao.responda.rotafacil@gmail.com`.
- Confirmação obrigatória antes do primeiro login de novas contas após ativação.
- Contas anteriores à ativação não serão bloqueadas automaticamente. Podem confirmar o endereço em Privacidade e segurança.
- Confirmação do e-mail é independente da aprovação profissional e do Cadastur.
- Transporte existente: Gmail SMTP com SSL, `smtp.gmail.com:465`. Não exige alterar o DNS de rotafacil.eco.br, pois o remetente é Gmail.

## Configuração da Vercel

Projeto: `ads-team4/rotafacil-backend` (`prj_gk1HXhGGziCNHX9BEwARC3AN2Yi3`), ambiente Production.

1. `EMAIL_REMETENTE`: Config, já cadastrado com o endereço informado.
2. `EMAIL_SENHA_APP`: Secret, inserir diretamente na Vercel. Nunca usar a senha normal do Gmail nem registrar a credencial no repositório ou no chat.
3. `EMAIL_VERIFICATION_ENABLED`: Config, `true` na ativação. Deixar ausente/false até o backend e o frontend novos estarem publicados e o envio estar disponível.

Para criar a senha: entrar na conta remetente, ativar Verificação em duas etapas, abrir https://myaccount.google.com/apppasswords e criar uma senha para RotaFácil. Orientação oficial: https://support.google.com/mail/answer/185833?hl=pt-BR.

Variáveis novas só chegam a deployments novos. Publicar primeiro o código de backend e frontend com exigência desativada; validar o SMTP por recuperação de senha em uma conta de homologação; depois habilitar a exigência e publicar novamente o backend.

## Fluxos implementados

### Confirmação

- `POST /api/auth/email/solicitar`: e-mail normalizado, resposta genérica, intervalo mínimo de 60 segundos entre envios para a mesma conta.
- `POST /api/auth/email/confirmar`: e-mail e token de uso único, com validade de 30 minutos.
- Somente o hash do token fica em `verificacoes_email`. Reenvio substitui o código anterior. Troca de endereço invalida a confirmação e os códigos ligados ao endereço anterior.
- Consumo do código usa precondição de versão do Firestore. Atualização concorrente da conta exige novo código.
- Novos cadastros sob a regra ativa são salvos com `exigir_confirmacao_email=true` e `email_confirmado=false`. Falha no e-mail preserva a conta e oferece reenvio.
- Login responde 403 com `codigo=EMAIL_NAO_CONFIRMADO`; o aplicativo abre a tela de confirmação. Não é emitido JWT antes da confirmação.
- Campos de confirmação não são editáveis pela API comum de perfil.

### Recuperação de senha

- Mantidos os endpoints `/api/auth/senha/solicitar` e `/api/auth/senha/redefinir`.
- Código expira em 30 minutos, é de uso único e não fica armazenado em texto puro.
- Falha de envio remove a solicitação nova e permite tentar novamente.
- Reenvio após 60 segundos substitui solicitações anteriores, depois do envio bem-sucedido.
- Redefinição incrementa `versao_auth`; JWTs emitidos anteriormente deixam de acessar rotas protegidas.
- Respostas e e-mails não revelam senha, credenciais SMTP ou detalhes internos do servidor.

## Validação local

- Backend: 86 testes passaram.
- Frontend: 122 testes passaram, com 6 ignorados pelo modo de execução.
- Contratos em modo backend: 38 testes passaram, com 3 ignorados pelo modo de execução.
- Análise estática do frontend sem problemas.

Cobertura: conta antiga e nova, bloqueio antes da confirmação, código expirado/reutilizado/de outra conta, falha e reenvio, troca de endereço, preservação de dados no formulário e invalidação de JWT após recuperação.

## Estado operacional deste checkpoint

Remetente cadastrado na Vercel. Usuário está gerando a senha de aplicativo. Credencial não foi lida nem registrada pelo agente. Código novo ainda não publicado; envio e recebimento reais ainda não comprovados. Não marcar homologação de e-mail como aprovada antes dos dois testes reais.
