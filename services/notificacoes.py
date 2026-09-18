# services/notificacoes.py

import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv
from firebase_admin import messaging, firestore

load_dotenv()

class Notificacoes:
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
    def _enviar_para_token(token, titulo, corpo, dados=None):
        try:
            mensagem = messaging.Message(
                notification=messaging.Notification(title=titulo, body=corpo),
                data={k: str(v) for k, v in (dados or {}).items()},
                token=token,
            )
            messaging.send(mensagem)
            return True
        except Exception as e:
            print(f"[notificacoes] Falha ao enviar push: {e}")
            return False

    @staticmethod
    def notificar_usuario(db, id_usuario, titulo, corpo, dados=None):
        """Busca os tokens de dispositivo do usuário e envia a notificação para todos.
        Nunca lança exceção — falha de push não pode derrubar a ação principal."""
        if not id_usuario:
            return
        usuario_doc = db.collection('usuarios').document(id_usuario).get()
        if not usuario_doc.exists:
            return
        tokens = usuario_doc.to_dict().get('fcm_tokens') or []
        for token in tokens:
            Notificacoes._enviar_para_token(token, titulo, corpo, dados)

    @staticmethod
    def registrar_token(db, id_usuario, token):
        try:
            if not token:
                return {"erro": "token é obrigatório"}, 400
            db.collection('usuarios').document(id_usuario).update({
                "fcm_tokens": firestore.ArrayUnion([token])
            })
            return {"mensagem": "Token de notificação registrado com sucesso"}, 200
        except Exception as e:
            return {"erro": f"Erro ao registrar token: {str(e)}"}, 500

    @staticmethod
    def remover_token(db, id_usuario, token):
        try:
            if not token:
                return {"erro": "token é obrigatório"}, 400
            db.collection('usuarios').document(id_usuario).update({
                "fcm_tokens": firestore.ArrayRemove([token])
            })
            return {"mensagem": "Token de notificação removido com sucesso"}, 200
        except Exception as e:
            return {"erro": f"Erro ao remover token: {str(e)}"}, 500
