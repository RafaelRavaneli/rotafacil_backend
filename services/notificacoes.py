# services/notificacoes.py

import smtplib
import os
import datetime
import uuid
from email.message import EmailMessage
from dotenv import load_dotenv
from services.community import PushDevices

load_dotenv()

class Notificacoes:
    PREFERENCIAS_PADRAO = {
        'push': True,
        'agendamentos': True,
        'marketing': False,
    }

    @staticmethod
    def _preferencias_usuario(db, id_usuario):
        doc = db.collection('usuarios').document(id_usuario).get()
        if not doc.exists:
            return dict(Notificacoes.PREFERENCIAS_PADRAO)
        salvas = (doc.to_dict() or {}).get('preferencias_notificacoes') or {}
        return {
            chave: bool(salvas.get(chave, padrao))
            for chave, padrao in Notificacoes.PREFERENCIAS_PADRAO.items()
        }

    @staticmethod
    def _categoria(dados):
        tipo = str((dados or {}).get('tipo') or '').strip().lower()
        if tipo in {'marketing', 'novidade', 'recomendacao'}:
            return 'marketing'
        if tipo in {
            'reserva', 'novo_agendamento', 'cancelamento', 'lembrete',
            'checkin', 'checkout'
        }:
            return 'agendamentos'
        return 'sistema'

    @staticmethod
    def listar(db, usuario):
        try:
            itens = []
            for doc in db.collection('notificacoes').where(
                    'id_usuario', '==', usuario.get('id')).stream():
                item = doc.to_dict() or {}
                item['id'] = doc.id
                itens.append(item)
            itens.sort(key=lambda item: item.get('criado_em') or '', reverse=True)
            return itens[:100], 200
        except Exception as error:
            return {'erro': f'Erro ao listar notificações: {error}'}, 500

    @staticmethod
    def marcar_lida(db, usuario, identificador):
        try:
            ref = db.collection('notificacoes').document(identificador)
            doc = ref.get()
            if not doc.exists:
                return {'erro': 'Notificação não encontrada.'}, 404
            if (doc.to_dict() or {}).get('id_usuario') != usuario.get('id'):
                return {'erro': 'Acesso negado.'}, 403
            ref.update({'lida': True})
            return {'mensagem': 'Notificação marcada como lida.'}, 200
        except Exception as error:
            return {'erro': f'Erro ao atualizar notificação: {error}'}, 500

    @staticmethod
    def marcar_todas_lidas(db, usuario):
        try:
            quantidade = 0
            for doc in db.collection('notificacoes').where(
                    'id_usuario', '==', usuario.get('id')).stream():
                if not (doc.to_dict() or {}).get('lida', False):
                    doc.reference.update({'lida': True})
                    quantidade += 1
            return {'mensagem': 'Notificações marcadas como lidas.',
                    'quantidade': quantidade}, 200
        except Exception as error:
            return {'erro': f'Erro ao atualizar notificações: {error}'}, 500

    @staticmethod
    def obter_preferencias(db, usuario):
        return Notificacoes._preferencias_usuario(db, usuario.get('id')), 200

    @staticmethod
    def atualizar_preferencias(db, usuario, dados):
        try:
            if not isinstance(dados, dict):
                return {'erro': 'Envie preferências válidas.'}, 400
            desconhecidas = set(dados) - set(Notificacoes.PREFERENCIAS_PADRAO)
            if desconhecidas:
                return {'erro': 'Preferências não reconhecidas.'}, 400
            atuais = Notificacoes._preferencias_usuario(db, usuario.get('id'))
            for chave, valor in dados.items():
                if not isinstance(valor, bool):
                    return {'erro': f'A preferência {chave} deve ser booleana.'}, 400
                atuais[chave] = valor
            db.collection('usuarios').document(usuario.get('id')).update(
                {'preferencias_notificacoes': atuais})
            return atuais, 200
        except Exception as error:
            return {'erro': f'Erro ao salvar preferências: {error}'}, 500

    # --- E-mail (redefinição de senha) ---
    @staticmethod
    def enviar_email_redefinicao(destinatario, token):
        try:
            remetente = os.getenv("EMAIL_REMETENTE")
            senha_app = os.getenv("EMAIL_SENHA_APP")

            if not remetente or not senha_app:
                return {"erro": "Credenciais de e-mail não configuradas no servidor (.env)"}, 500

            msg = EmailMessage()
            msg["Subject"] = "RotaFácil - Redefinição de senha"
            msg["From"] = remetente
            msg["To"] = destinatario
            msg.set_content(
                f"Você solicitou a redefinição de senha no RotaFácil.\n\n"
                f"Use o código abaixo para redefinir sua senha (válido por 30 minutos):\n\n"
                f"{token}\n\n"
                f"Se você não solicitou isso, ignore este e-mail."
            )

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
                servidor.login(remetente, senha_app)
                servidor.send_message(msg)

            return {"mensagem": "E-mail de redefinição enviado com sucesso!"}, 200

        except smtplib.SMTPAuthenticationError:
            return {"erro": "Falha na autenticação com o servidor de e-mail. Verifique a senha de app."}, 500
        except Exception as e:
            return {"erro": f"Erro ao enviar e-mail: {str(e)}"}, 500

    # --- Push (FCM) ---
    @staticmethod
    def notificar_usuario(db, id_usuario, titulo, corpo, dados=None):
        """Persiste a central e envia push sem interromper a ação principal."""
        if not id_usuario:
            return {'enviados': 0, 'falhas': 0}
        try:
            preferencias = Notificacoes._preferencias_usuario(db, id_usuario)
            categoria = Notificacoes._categoria(dados)
            if categoria in {'agendamentos', 'marketing'} and not preferencias[categoria]:
                return {'enviados': 0, 'falhas': 0}

            identificador = str(uuid.uuid4())
            db.collection('notificacoes').document(identificador).set({
                'id': identificador,
                'id_usuario': id_usuario,
                'titulo': titulo,
                'corpo': corpo,
                'dados': {key: str(value) for key, value in (dados or {}).items()},
                'categoria': categoria,
                'lida': False,
                'criado_em': datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
            if not preferencias['push']:
                return {'enviados': 0, 'falhas': 0}
            return PushDevices.send(db, id_usuario, titulo, corpo, dados)
        except Exception as error:
            print(f"[notificacoes] Falha ao consultar dispositivos: {error}")
            return {'enviados': 0, 'falhas': 1}
