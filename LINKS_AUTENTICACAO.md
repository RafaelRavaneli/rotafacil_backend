# Confirmação e recuperação por link

## Configuração

`APP_PUBLIC_URL` é opcional e usa `https://www.rotafacil.eco.br` como padrão. Para desenvolvimento local, pode apontar para `http://localhost:PORTA`; HTTP em outros hosts é rejeitado. A URL não pode conter credenciais, query ou fragmento. O endereço não vem da requisição do usuário.

Os e-mails preservam o transporte Gmail SMTP existente, mas passam a conter links pessoais. Os segredos ficam no fragmento da URL, fora da query HTTP. Não registrar links completos em logs ou documentos de teste.

## Contrato

- `POST /api/auth/email/solicitar`: envia link de confirmação, mantendo resposta genérica e limite de reenvio.
- `POST /api/auth/email/confirmar`: recebe `email`, `token` e, opcionalmente, `iniciar_sessao: true`. Após validar e consumir o segredo, confirma o e-mail e retorna os campos de sessão quando solicitados.
- `POST /api/auth/senha/solicitar`: envia link de recuperação.
- `POST /api/auth/senha/redefinir`: recebe `token`, `nova_senha` e, opcionalmente, `iniciar_sessao: true`. Troca a senha, confirma o e-mail e incrementa `versao_auth`, invalidando sessões anteriores. A sessão retornada utiliza a nova versão.

A sessão inclui `token` JWT, `id`, `email`, `nome` e `tipo`. Os endpoints antigos continuam aceitando os mesmos segredos por POST para compatibilidade durante a atualização; a interface deixa de pedir que o usuário copie códigos.

## Segurança

Segredos aleatórios, armazenados por hash, validade de 30 minutos e consumo único com precondições de versão. Contas inativas são rejeitadas. Novas solicitações são vinculadas ao e-mail e à versão de autenticação; mudanças posteriores tornam o link inválido. A confirmação de e-mail continua independente da aprovação profissional do guia ou agência.

O frontend exige confirmação explícita antes de chamar o POST; um simples GET do link não consome o segredo. Não há sessão emitida para link inválido, expirado, usado ou associado a conta alterada.

## Publicação futura

Não houve publicação nesta etapa. A atualização deve ser coordenada com o frontend e com o envio obrigatório de aceite dos documentos legais. Validar os dois projetos antes de homologar e-mails reais. Mensagens antigas que continham código podem ser substituídas solicitando um novo link.

## Testes

A suíte isolada verifica emissão da sessão, uso único, expiração, conta inativa, e-mail alterado, troca de senha, invalidação das sessões e links anteriores, segredo fora da query HTTP e rejeição de origem inválida. Nenhum teste envia e-mail real.
