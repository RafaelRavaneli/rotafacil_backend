# services/notificacoes.py

import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

class Notificacoes:
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