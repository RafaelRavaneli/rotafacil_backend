# Documentos legais e registro de aceite

## Conteúdo e fontes

Os termos e a política estão em `legal/legal_documents.json`. Os textos em Markdown permitem revisão humana. A versão `2026-10-20` está arquivada em `legal/versions/2026-10-20.json`. A cópia do frontend deve ser idêntica ao JSON do backend.

Os documentos descrevem a operação atual, inclusive reservas sujeitas à confirmação do organizador, ausência de processamento de pagamentos, atendimento de direitos por e-mail, serviços externos e imagens públicas no ImgBB. A identificação do responsável e o contato foram fornecidos pelo responsável do projeto.

Referência normativa: [Lei Geral de Proteção de Dados Pessoais](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm). O texto não representa certificação de conformidade. O canal informado deve receber e tratar solicitações reais.

## Contrato

- `GET /api/usuarios/documentos-legais`: consulta pública dos textos, versões e hashes.
- `POST /api/usuarios/`: cadastro exige `aceite_termos: true`, `ciencia_privacidade: true`, `termos_versao` e `privacidade_versao` atuais. Indicadores em texto, versões antigas ou ausência de aceite são rejeitados.
- `POST /api/usuarios/aceite-legal`: conta autenticada registra seu próprio aceite. O ID vem exclusivamente do JWT. Contas antigas não recebem aceite retroativo automático e continuam acessando normalmente.

O servidor grava `aceite_legal` e `historico_aceites_legais` no usuário, contendo as versões, os hashes do conteúdo e o horário UTC calculado pelo servidor. Valores de prova fornecidos pelo cliente não substituem esses campos. Repetir o aceite idêntico não cria novo registro. A edição comum do perfil não permite alterar a prova ou o histórico.

O aceite dos termos e a ciência da política não equivalem a consentimento genérico. As permissões de localização e notificações permanecem independentes.

## Evolução e publicação

Não editar silenciosamente uma versão já publicada. Arquivar o documento anterior, criar nova versão e sincronizar o frontend. Alterações relevantes exigem comunicação e coleta adequada de novo aceite; não presumir consentimento pelo uso continuado.

Na primeira publicação desta funcionalidade, atualizar primeiro o frontend que envia o aceite e depois o backend que o exige. Uma aba antiga em cache pode precisar ser atualizada para cadastrar uma nova conta. Não há migração de contas existentes nem novas credenciais de ambiente.

## Validação

Testes cobrem cadastro sem aceite, versões inválidas, horário e hashes do servidor, histórico, repetição idempotente, autenticação, conta ausente, formato inválido e proteção contra edição do registro pelo perfil. A consulta dos documentos não depende de Firebase ou envio de e-mail.
