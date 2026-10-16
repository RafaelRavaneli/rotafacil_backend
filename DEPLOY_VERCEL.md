# Publicação do backend RotaFácil no Vercel

Preparação para testes do grupo. A publicação só está concluída quando o deploy estiver ativo e os fluxos forem verificados na URL pública.

## Importar o repositório

1. Na conta Vercel, escolha **Add New > Project** e importe `RafaelRavaneli/rotafacil_backend`.
2. Escolha o preset **Flask** e a raiz do repositório como Root Directory.
3. Para homologação, configure `develop` como Production Branch desse projeto de testes. A palavra Production no painel indica a URL estável deste projeto; não significa que o produto já foi homologado para clientes.
4. O repositório fixa Python 3.13 em `.python-version`. O Vercel instala `requirements.txt` e executa `python preparar_vercel.py`, conforme `vercel.json`.
5. Não configure `python app.py` nem Gunicorn como Start Command: Vercel importa a instância `app` de `app.py` como função Python.
6. Cadastre as variáveis abaixo antes de publicar. Configure os ambientes que serão utilizados; para evitar testes no banco de produção, use credenciais de homologação.

## Variáveis de ambiente

| Variável | Valor e finalidade |
|---|---|
| `KEY` | Segredo forte para assinar JWT; não é a chave pública do frontend Firebase |
| `FIREBASE_CREDENTIALS_JSON` | Conteúdo JSON completo da conta de serviço Firebase, cadastrado como variável sensível no painel |
| `CORS_ORIGINS` | Para os testes locais: `http://localhost:8080,http://127.0.0.1:8080`. Acrescente a origem exata do frontend publicado quando existir, sem barra final |
| `IMGBB_API_KEY` | Credencial do upload de imagens |
| `URL_IMGBB` | `https://api.imgbb.com/1/upload` |
| `FIREBASE_STORAGE_BUCKET` | Bucket privado usado para documentos profissionais |
| `EMAIL_REMETENTE` | Conta utilizada na recuperação de senha |
| `EMAIL_SENHA_APP` | Senha de aplicativo do e-mail; validar SMTP na hospedagem |
| `ENABLE_SCHEDULER` | `false` |
| `FLASK_DEBUG` | `false` |

No Vercel, não use o caminho do Render `/etc/secrets/firebase-key.json`. A nova configuração lê o JSON protegido diretamente do ambiente. Localmente, o arquivo `firebase-key.json` e `FIREBASE_CREDENTIALS_PATH` continuam funcionando. Se as duas variáveis estiverem preenchidas, o JSON tem precedência.

Não coloque `.env`, credencial Firebase, senha ou tokens no Git, em arquivos de configuração públicos ou em mensagens do grupo. `.vercelignore` e a exclusão do pacote da função impedem o envio dos arquivos locais conhecidos. Variáveis sensíveis devem ser cadastradas no ambiente Runtime, sem prefixos destinados ao frontend.

## Swagger e arquivos estáticos

O build copia `static/openapi.json` para `public/static/openapi.json`. O Vercel serve esse arquivo pela CDN, preservando a URL utilizada pela documentação `/docs`. O contrato original continua em `static/openapi.json`; o arquivo em `public` é gerado e não deve ser editado manualmente.

## Limites desta publicação

- O backend continua usando Firestore; os dados não dependem do disco temporário da função.
- Requisição e resposta têm limite de 4,5 MB no Vercel Functions. Teste uploads pequenos; esse limite inclui o corpo completo, inclusive codificação Base64 quando utilizada. Arquivos maiores podem ser rejeitados antes de alcançar o Flask.
- `maxDuration` está definido em 60 segundos. Chamadas ao Firestore, upload e e-mail precisam terminar dentro desse prazo.
- A API não inicia o agendador em segundo plano ao ser importada pelo Vercel. Lembretes diários não estão configurados nesta publicação. Um cron posterior exige endpoint protegido apropriado, controle de execução e teste de duplicidade; não exponha o disparo administrativo sem autenticação.
- SMTP, push e upload precisam de homologação na hospedagem. Não considerar sucesso de testes simulados como evidência de entrega real de e-mail ou notificações.
- O plano Hobby destina-se a uso pessoal não comercial. Esta proposta é para testes acadêmicos; antes de operação comercial para clientes, revisar elegibilidade e plano.
- Se Deployment Protection impedir chamadas do aplicativo, ajuste o acesso do projeto de homologação conforme o painel. A autenticação JWT da API deve continuar ativa.

## Validação após o deploy

1. Abrir a URL pública `/`: deve retornar JSON informando que a API está funcionando.
2. Abrir `/docs` e `/static/openapi.json`: conferir contrato disponível.
3. No frontend, executar, substituindo a URL pela URL real do deploy:

```cmd
flutter run -d chrome --web-port=8080 --dart-define=USE_BACKEND=true --dart-define=API_BASE_URL=https://URL-REAL-DO-BACKEND.vercel.app
```

4. Testar cadastro e login dos três perfis, consulta de trilhas, favoritos, criação/edição, reserva, cancelamento, convite e resposta.
5. Testar credenciais inválidas, acesso sem JWT, CORS e erros de autorização.
6. Validar recuperação de senha, upload de imagem e recebimento de push separadamente.
7. Registrar URL, commit, ambiente Firebase, resultados e limitações. Se ocorrer falha, consultar os logs sem registrar credenciais, senhas ou tokens.

## Verificação local

```cmd
venv\Scripts\python.exe -m unittest discover -s tests -v
venv\Scripts\python.exe preparar_vercel.py
```

O primeiro comando usa armazenamento e serviços simulados. O segundo prepara arquivos estáticos e não inicia a API nem acessa Firebase.

## Referências

Consultadas em 14/10/2026:

- [Flask no Vercel](https://vercel.com/docs/frameworks/backend/flask)
- [Runtime Python](https://vercel.com/docs/functions/runtimes/python)
- [Limites de Functions](https://vercel.com/docs/functions/limitations)
- [Exclusão de arquivos do deploy](https://vercel.com/docs/deployments/vercel-ignore)
- [Plano Hobby](https://vercel.com/docs/plans/hobby)
