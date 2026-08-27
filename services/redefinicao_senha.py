# services/redefinicao_senha.py

import secrets
import hashlib
import datetime
from firebase_admin import firestore
from werkzeug.security import generate_password_hash
from services.notificacoes import Notificacoes


class RedefinicaoSenha:

    TEMPO_EXPIRACAO_MINUTOS = 30

    @staticmethod
    def _gerar_hash_token(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @staticmethod
    def solicitar_redefinicao(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            email = dados.get('email')
            if not email:
                return {"erro": "O campo 'email' é obrigatório"}, 400

            # Mensagem genérica: usada tanto pra sucesso real quanto quando
            # o e-mail não existe, para não revelar quais e-mails têm conta.
            mensagem_generica = {
                "mensagem": "Se o e-mail informado estiver cadastrado, um código de redefinição foi enviado."
            }

            usuarios_ref = db.collection('usuarios').where('email', '==', email).stream()
            docs = list(usuarios_ref)

            if not docs:
                return mensagem_generica, 200

            usuario_doc = docs[0]
            id_usuario = usuario_doc.id
            dados_usuario = usuario_doc.to_dict()

            agora = datetime.datetime.now(datetime.timezone.utc)

            # --- Rate limiting: já existe um token ativo (não expirado e não usado)? ---
            tokens_ativos_ref = db.collection('redefinicoes_senha') \
                .where('id_usuario', '==', id_usuario) \
                .where('usado', '==', False) \
                .stream()

            for doc in tokens_ativos_ref:
                token_existente = doc.to_dict()
                expira_em = token_existente.get('expira_em')
                if expira_em and expira_em > agora:
                    return mensagem_generica, 200  # já tem token válido, não gera outro

            # --- Gera o novo token opaco ---
            token_puro = secrets.token_urlsafe(32)
            token_hash = RedefinicaoSenha._gerar_hash_token(token_puro)
            expira_em = agora + datetime.timedelta(minutes=RedefinicaoSenha.TEMPO_EXPIRACAO_MINUTOS)

            db.collection('redefinicoes_senha').add({
                "id_usuario": id_usuario,
                "token_hash": token_hash,
                "criado_em": agora,
                "expira_em": expira_em,
                "usado": False
            })

            resposta_email, status_email = Notificacoes.enviar_email_redefinicao(
                dados_usuario.get('email'), token_puro
            )

            if status_email != 200:
                # Falha no envio não deve vazar detalhe técnico pro usuário final
                return {"erro": "Não foi possível enviar o e-mail de redefinição no momento. Tente novamente mais tarde."}, 500

            return mensagem_generica, 200

        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500
        
    @staticmethod
    def redefinir_senha(db, dados):
        try:
            if not dados:
                return {"erro": "Dados não enviados"}, 400

            token_recebido = dados.get('token')
            nova_senha = dados.get('nova_senha')

            if not token_recebido or not nova_senha:
                return {"erro": "Os campos 'token' e 'nova_senha' são obrigatórios"}, 400

            if len(nova_senha) < 6:
                return {"erro": "A nova senha deve ter no mínimo 6 caracteres"}, 400

            token_hash = RedefinicaoSenha._gerar_hash_token(token_recebido)

            registros_ref = db.collection('redefinicoes_senha') \
                .where('token_hash', '==', token_hash) \
                .stream()

            docs = list(registros_ref)

            if not docs:
                return {"erro": "Token inválido ou não encontrado"}, 400

            doc_redefinicao = docs[0]
            dados_redefinicao = doc_redefinicao.to_dict()

            if dados_redefinicao.get('usado'):
                return {"erro": "Este token já foi utilizado"}, 400

            agora = datetime.datetime.now(datetime.timezone.utc)
            expira_em = dados_redefinicao.get('expira_em')

            if not expira_em or expira_em < agora:
                return {"erro": "Token expirado. Solicite uma nova redefinição de senha."}, 400

            id_usuario = dados_redefinicao.get('id_usuario')

            usuario_ref = db.collection('usuarios').document(id_usuario)
            usuario_doc = usuario_ref.get()

            if not usuario_doc.exists:
                return {"erro": "Usuário associado a este token não foi encontrado"}, 404

            # Atualiza a senha do usuário
            usuario_ref.update({
                "senha": generate_password_hash(nova_senha)
            })

            # Marca o token como usado (nunca deletamos, vira rastro de auditoria)
            doc_redefinicao.reference.update({
                "usado": True,
                "usado_em": agora
            })

            return {"mensagem": "Senha redefinida com sucesso!"}, 200

        except Exception as e:
            return {"erro": f"Erro interno: {str(e)}"}, 500