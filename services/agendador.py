from apscheduler.schedulers.background import BackgroundScheduler
import datetime as dt


def enviar_lembretes_diarios():
    # Import tardio (dentro da função) para evitar import circular na inicialização do app
    from models.database import bd
    from services.notificacoes import Notificacoes

    amanha = (dt.datetime.now() + dt.timedelta(days=1)).date()

    try:
        agendamentos_ref = bd.collection('agendamentos').where('status', '==', 'agendado').stream()
        for doc in agendamentos_ref:
            dados = doc.to_dict()
            data_str = dados.get('data_agendada')
            if not data_str:
                continue
            try:
                data_agendamento = dt.datetime.fromisoformat(data_str).date()
            except (ValueError, TypeError):
                continue

            if data_agendamento == amanha:
                trilha_doc = bd.collection('trilhas').document(dados.get('id_trilha')).get()
                nome_trilha = trilha_doc.to_dict().get('nome') if trilha_doc.exists else 'sua trilha'
                Notificacoes.notificar_usuario(
                    bd, dados.get('id_usuario'),
                    "Sua trilha é amanhã!",
                    f"Não esqueça: '{nome_trilha}' está agendada para amanhã. Prepare sua mochila!",
                    dados={"tipo": "lembrete", "id_agendamento": doc.id}
                )
        print(f"[agendador] Lembretes diários verificados às {dt.datetime.now()}.")
    except Exception as e:
        print(f"[agendador] Erro ao enviar lembretes diários: {e}")


def iniciar_agendador():
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    # Roda todo dia às 18h — dá aviso com antecedência pra trilha do dia seguinte
    scheduler.add_job(enviar_lembretes_diarios, 'cron', hour=18, minute=0)
    scheduler.start()
    return scheduler
