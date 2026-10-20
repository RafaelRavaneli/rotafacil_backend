import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from google.cloud.firestore_v1 import LastUpdateOption
from services.notificacoes import Notificacoes


class VerificacaoEmail:
    @staticmethod
    def habilitada():
        return os.getenv('EMAIL_VERIFICATION_ENABLED', 'false').lower() == 'true'

    @staticmethod
    def solicitar(db, dados):
        if not isinstance(dados, dict):
            return {'erro': 'Envie um objeto válido.'}, 400
        email = str((dados or {}).get('email') or '').strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
            return {'erro': 'Informe um e-mail válido.'}, 400
        resposta = {'mensagem': 'Se o endereço precisar de confirmação, enviaremos um link. Aguarde um minuto antes de solicitar outro.'}
        usuario = next(iter(db.collection('usuarios').where('email', '==', email).stream()), None)
        if usuario is None or not usuario.exists:
            return resposta, 200
        atual = usuario.to_dict() or {}
        if atual.get('email_confirmado') or not atual.get('ativo', True):
            return resposta, 200
        ref = db.collection('verificacoes_email').document(usuario.id)
        snapshot = ref.get()
        anterior = snapshot.to_dict() or {}
        agora = datetime.now(timezone.utc)
        if (anterior.get('email') == email and anterior.get('criado_em') and
                agora - anterior['criado_em'] < timedelta(seconds=60)):
            return resposta, 200
        token = secrets.token_urlsafe(32)
        registro = {'id_usuario': usuario.id, 'email': email,
                    'versao_auth': atual.get('versao_auth', 0),
                    'token_hash': hashlib.sha256(token.encode()).hexdigest(),
                    'criado_em': agora, 'expira_em': agora + timedelta(minutes=30),
                    'usado': False}
        try:
            if snapshot.exists:
                ref.update(registro, option=LastUpdateOption(snapshot.update_time))
            else:
                ref.create(registro)
        except (AlreadyExists, FailedPrecondition):
            return resposta, 200
        salvo = ref.get()
        _, status = Notificacoes.enviar_email_confirmacao(email, token)
        if status != 200:
            try:
                ref.delete(option=LastUpdateOption(salvo.update_time))
            except FailedPrecondition:
                pass
            return {'erro': 'Não foi possível enviar o link de confirmação. Tente novamente mais tarde.'}, 503
        return resposta, 200

    @staticmethod
    def confirmar(db, dados):
        if not isinstance(dados, dict):
            return {'erro': 'Envie um objeto válido.'}, 400
        email = str((dados or {}).get('email') or '').strip().lower()
        token = (dados or {}).get('token')
        if not email or not isinstance(token, str) or not 20 <= len(token.strip()) <= 128:
            return {'erro': 'Link de confirmação inválido. Solicite um novo link.'}, 400
        usuario = next(iter(db.collection('usuarios').where('email', '==', email).stream()), None)
        erro = {'erro': 'Link inválido, expirado ou já utilizado. Solicite um novo link.'}
        if usuario is None or not usuario.exists:
            return erro, 400
        atual = usuario.to_dict() or {}
        if not atual.get('ativo', True):
            return erro, 400
        ref = db.collection('verificacoes_email').document(usuario.id)
        snapshot = ref.get()
        registro = snapshot.to_dict() or {}
        agora = datetime.now(timezone.utc)
        if (not snapshot.exists or registro.get('email') != email or
                ('versao_auth' in registro and registro['versao_auth'] != atual.get('versao_auth', 0)) or
                registro.get('usado') or not registro.get('expira_em') or
                registro['expira_em'] <= agora or not hmac.compare_digest(
                    str(registro.get('token_hash') or ''),
                    hashlib.sha256(token.strip().encode()).hexdigest())):
            return erro, 400
        sessao = {}
        if dados.get('iniciar_sessao') is True:
            from services.autenticacao import Autenticacao
            sessao = {'email': email, 'nome': atual.get('nome', 'Usuário'),
                      'id': usuario.id, 'tipo': atual.get('tipo', 'usuario'),
                      'token': Autenticacao.make_token(email, usuario.id,
                          atual.get('tipo', 'usuario'), atual.get('versao_auth', 0))}
        try:
            ref.update({'usado': True, 'usado_em': agora},
                       option=LastUpdateOption(snapshot.update_time))
        except FailedPrecondition:
            return erro, 400
        try:
            usuario.reference.update({'email_confirmado': True, 'email_confirmado_em': agora},
                                     option=LastUpdateOption(usuario.update_time))
        except FailedPrecondition:
            return {'erro': 'A conta mudou. Solicite outro link de confirmação.'}, 409
        return {'mensagem': 'E-mail confirmado.', **sessao}, 200
