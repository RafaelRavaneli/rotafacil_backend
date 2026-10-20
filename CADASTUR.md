# Cadastur no RotaFácil

Novas contas de guia e agência precisam informar `cadastur_numero`. O mesmo vale para mudanças de tipo de conta para esses perfis. Turistas não precisam informar Cadastur.

## Campos

- `cadastur_numero`: texto obrigatório no cadastro profissional. Aceita números e separadores usuais; o servidor armazena apenas os dígitos, preservando zeros iniciais.
- `cadastur_validade`: texto opcional no formato `AAAA-MM-DD`. Datas inexistentes são rejeitadas. Datas vencidas podem ser registradas para preservar a informação declarada; não representam regularidade.

Os campos são aceitos no cadastro, na edição por ID/e-mail e na mudança de tipo. A validade não pode ser informada sem número. Turistas não podem adicionar esses campos pela edição de perfil.

## Contas existentes

Contas anteriores continuam acessando o sistema e podem completar os dados no perfil. Edições sem os novos campos não exigem migração. O Firestore recebe os campos ao salvar, sem alteração estrutural ou atualização em massa.

## Conferência

Validar o preenchimento não verifica a existência ou situação do registro no Ministério do Turismo. Não há integração automática com a base oficial nem concessão automática de selo. O certificado Cadastur continua sendo enviado como documento profissional privado. A equipe vê número e validade informados ao analisar os documentos.

Ao publicar, disponibilize frontend e backend juntos: clientes antigos não enviam o número obrigatório para novas contas profissionais.
