# Publicacao do backend no Render

Esta configuracao prepara API Flask e Swagger para hospedagem. Nenhum servico remoto e criado por estes arquivos.

## Preparar

1. Execute `venv/Scripts/python.exe -m unittest discover -s tests -v`.
2. Envie codigo, `static/openapi.json`, `templates/swagger.html` e `enviar_lembretes.py` ao repositorio.
3. Preserve `.env` e `firebase-key.json` fora do Git. Configure credenciais no painel da hospedagem.

`requirements.txt` inclui Gunicorn apenas em plataformas diferentes de Windows. Desenvolvimento local continua usando `python app.py`. Debug e agendador embutido ficam desativados por padrao; habilite `FLASK_DEBUG=true` ou `ENABLE_SCHEDULER=true` explicitamente quando necessario em desenvolvimento.

## Web Service

No Render, selecione New > Web Service e conecte repositorio e branch desejados.

| Campo | Valor |
|---|---|
| Language | Python 3 |
| Root Directory | Vazio se app.py estiver na raiz; caso contrario, pasta do backend no repositorio |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT` |
| Health Check Path | `/` |

Em Environment, configure:

| Variavel | Finalidade |
|---|---|
| KEY | Segredo aleatorio para assinar JWT |
| FIREBASE_CREDENTIALS_PATH | `/etc/secrets/firebase-key.json` |
| CORS_ORIGINS | Origens autorizadas do frontend, separadas por virgula, sem barra final |
| IMGBB_API_KEY | Chave privada para upload |
| URL_IMGBB | `https://api.imgbb.com/1/upload` |
| EMAIL_REMETENTE | Conta Gmail para recuperacao de senha |
| EMAIL_SENHA_APP | Senha de aplicativo da conta Gmail |
| ENABLE_SCHEDULER | `false` |
| FLASK_DEBUG | `false` |

Adicione Secret File chamado `firebase-key.json` com credencial administrativa do Firebase. O arquivo fica disponivel em `/etc/secrets/firebase-key.json`. Localmente, sem variavel configurada, o backend busca arquivo na raiz do repositorio.

O e-mail atual usa Gmail SMTP na porta 465. Instancias gratuitas do Render bloqueiam saida nas portas 25, 465 e 587: use instancia paga para manter esse fluxo ou implemente envio por API HTTPS antes de escolher plano gratuito. O plano gratuito tambem suspende servico apos inatividade.

## Lembretes diarios

Crie Cron Job separado com mesmo repositorio. Esse servico possui cobranca propria; confira plano e preco no painel antes de criar.

| Campo | Valor |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Command | `python enviar_lembretes.py` |
| Schedule | `0 21 * * *` |

Configure tambem Secret File `firebase-key.json` e `FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-key.json` nesse job. O horario e 21h UTC, equivalente a 18h de Sao Paulo. O calculo do dia seguinte usa explicitamente `America/Sao_Paulo`, independentemente do fuso do servidor.

Cada execucao faz uma rodada e encerra. Falhas de consulta propagam erro para o cron; falhas de entrega FCM sao contabilizadas pelo servico de envio. O comando ainda nao possui deduplicacao persistente de lembretes: repetir a rodada pode reenviar notificacoes. Configure apenas um cron para a mesma rotina.

## Conferir publicacao

Abra URL publica e `/docs`. Teste login, consulta, reserva, cancelamento, upload e recuperacao de senha com contas de homologacao. Registre dispositivo FCM e confira recebimento real, rotacao e logout.

Todos os eventos usam `dispositivos_fcm`. Tokens antigos em `usuarios.fcm_tokens` deixam de ser consultados; registre novamente dispositivos. Nao foi executada migracao ou exclusao de dados reais.

Os testes locais usam armazenamento e envio simulados. A inicializacao com Gunicorn deve ser verificada na hospedagem Linux; Gunicorn nao e executado no ambiente Windows.

## Referencias

- [Flask no Render](https://render.com/docs/deploy-flask)
- [Variaveis e arquivos secretos](https://render.com/docs/configure-environment-variables)
- [Cron Jobs](https://render.com/docs/cronjobs)
- [Limitacoes do plano gratuito](https://render.com/docs/free)
