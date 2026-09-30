"""Contratos de conversas, suporte, vínculos de guias e dispositivos FCM."""
import hashlib
import uuid
from datetime import datetime, timezone
from google.api_core.exceptions import AlreadyExists, FailedPrecondition
from google.cloud.firestore_v1 import LastUpdateOption
from firebase_admin import messaging


class CommunityError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text_value(data, field, maximum=2000):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise CommunityError(f"Informe {field} com até {maximum} caracteres.")
    return value.strip()


def guide_identifier(data):
    value = text_value(data, 'id_guia', 128)
    if '/' in value:
        raise CommunityError('Identificador de guia inválido.')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def row(doc):
    return {**doc.to_dict(), 'id': doc.id}


def required(ref):
    doc = ref.get()
    if not doc.exists:
        raise CommunityError('Registro não encontrado.', 404)
    return doc


def update_checked(ref, doc, values):
    try:
        ref.update(values, option=LastUpdateOption(doc.update_time))
    except FailedPrecondition:
        raise CommunityError('O registro mudou. Atualize a tela e tente novamente.', 409)


def guide_public(doc):
    data = doc.to_dict()
    return {'id': doc.id, 'nome': data.get('nome', 'Guia'),
            'cidade': data.get('cidade', ''), 'estado': data.get('estado', ''),
            'foto_url': data.get('foto_url'), 'verificado': data.get('verificado', False)}


class Community:
    @staticmethod
    def guides(db):
        return [guide_public(doc) for doc in db.collection('usuarios').where('tipo', '==', 'guia').stream()
                if doc.to_dict().get('ativo', True)]

    @staticmethod
    def start_chat(db, user, data):
        if user.get('tipo') != 'usuario':
            raise CommunityError('A conversa deve ser iniciada pelo turista.', 403)
        guide_id = guide_identifier(data)
        guide = required(db.collection('usuarios').document(guide_id))
        if guide.to_dict().get('tipo') != 'guia' or not guide.to_dict().get('ativo', True):
            raise CommunityError('Guia indisponível.', 404)
        chat_id = hashlib.sha256(f"{user['id']}:{guide_id}".encode()).hexdigest()
        ref = db.collection('conversas').document(chat_id)
        value = {'participantes': [user['id'], guide_id], 'id_usuario': user['id'],
                 'id_guia': guide_id, 'nomes': {user['id']: user.get('nome', 'Turista'),
                 guide_id: guide.to_dict().get('nome', 'Guia')}, 'criado_em': now()}
        try:
            ref.create(value)
        except AlreadyExists:
            pass
        return row(required(ref))

    @staticmethod
    def chats(db, user):
        return [row(doc) for doc in db.collection('conversas').where('participantes', 'array_contains', user['id']).stream()]

    @staticmethod
    def thread(db, user, collection, thread_id):
        ref = db.collection(collection).document(thread_id)
        doc = required(ref)
        data = doc.to_dict()
        allowed = user['id'] in data.get('participantes', []) if collection == 'conversas' else (
            data.get('id_usuario') == user['id'] or user.get('tipo') == 'admin')
        if not allowed:
            raise CommunityError('Você não tem acesso a esta conversa.', 403)
        return ref

    @staticmethod
    def messages(db, user, collection, thread_id):
        ref = Community.thread(db, user, collection, thread_id)
        # A consulta usa um único campo e retorna as 100 mensagens mais recentes.
        docs = ref.collection('mensagens').order_by('criado_em', direction='DESCENDING').limit(100).stream()
        return sorted([row(doc) for doc in docs], key=lambda item: item['criado_em'])

    @staticmethod
    def send(db, user, collection, thread_id, data):
        ref = Community.thread(db, user, collection, thread_id)
        if collection == 'suporte' and ref.get().to_dict().get('status') == 'fechado':
            raise CommunityError('Este atendimento está encerrado.', 409)
        message = {'id': str(uuid.uuid4()), 'texto': text_value(data, 'texto'),
                   'id_autor': user['id'], 'nome_autor': user.get('nome', 'Usuário'),
                   'atendente': collection == 'suporte' and user.get('tipo') == 'admin',
                   'criado_em': now()}
        ref.collection('mensagens').document(message['id']).create(message)
        return message

    @staticmethod
    def tickets(db, user):
        query = db.collection('suporte')
        if user.get('tipo') != 'admin':
            query = query.where('id_usuario', '==', user['id'])
        return [row(doc) for doc in query.stream()]

    @staticmethod
    def open_ticket(db, user, data):
        subject = text_value(data, 'assunto', 120)
        message = text_value(data, 'texto')
        ref = db.collection('suporte').document(str(uuid.uuid4()))
        ticket = {'id': ref.id, 'id_usuario': user['id'], 'assunto': subject,
                  'status': 'aberto', 'criado_em': now()}
        batch = db.batch()
        batch.create(ref, ticket)
        batch.create(ref.collection('mensagens').document(str(uuid.uuid4())),
                     {'texto': message, 'id_autor': user['id'], 'nome_autor': user.get('nome', 'Usuário'),
                      'atendente': user.get('tipo') == 'admin', 'criado_em': now()})
        batch.commit()
        return ticket

    @staticmethod
    def invite(db, user, data):
        if user.get('tipo') != 'agencia':
            raise CommunityError('Somente agências podem convidar guias.', 403)
        guide_id = guide_identifier(data)
        guide = required(db.collection('usuarios').document(guide_id))
        if guide.to_dict().get('tipo') != 'guia' or not guide.to_dict().get('ativo', True):
            raise CommunityError('Guia indisponível.', 404)
        invitation_id = hashlib.sha256(f"{user['id']}:{guide_id}".encode()).hexdigest()
        ref = db.collection('convites_guias').document(invitation_id)
        data = {'participantes': [user['id'], guide_id], 'id_agencia': user['id'],
                'id_guia': guide_id, 'nome_agencia': user.get('nome', 'Agência'),
                'nome_guia': guide.to_dict().get('nome', 'Guia'), 'status': 'pendente', 'criado_em': now()}
        try:
            ref.create(data)
        except AlreadyExists:
            raise CommunityError('Já existe um convite ou vínculo para este guia.', 409)
        return {'id': ref.id, **data}

    @staticmethod
    def invitations(db, user):
        return [row(doc) for doc in db.collection('convites_guias').where('participantes', 'array_contains', user['id']).stream()]

    @staticmethod
    def answer_invitation(db, user, invitation_id, data):
        ref = db.collection('convites_guias').document(invitation_id)
        doc = required(ref)
        invite = doc.to_dict()
        if user.get('tipo') != 'guia' or invite['id_guia'] != user['id']:
            raise CommunityError('Somente o guia convidado pode responder.', 403)
        status = data.get('status')
        if not isinstance(status, str) or status not in {'aceito', 'recusado'}:
            raise CommunityError('Use aceito ou recusado.')
        if invite['status'] != 'pendente':
            raise CommunityError('Este convite já foi respondido.', 409)
        update_checked(ref, doc, {'status': status, 'respondido_em': now()})
        return {'id': ref.id, **invite, 'status': status}

    @staticmethod
    def linked(db, agency_id):
        return [row(doc) for doc in db.collection('convites_guias').where('id_agencia', '==', agency_id).stream()
                if doc.to_dict().get('status') == 'aceito']

    @staticmethod
    def can_assign(db, user, guide_id):
        if not isinstance(guide_id, str) or '/' in guide_id:
            return False
        if guide_id in {user.get('id'), user.get('email')}:
            return True
        if user.get('tipo') == 'admin':
            return True
        if user.get('tipo') != 'agencia':
            return False
        guide = db.collection('usuarios').document(guide_id).get()
        return (guide.exists and guide.to_dict().get('tipo') == 'guia'
                and guide.to_dict().get('ativo', True)
                and any(item['id_guia'] == guide_id for item in Community.linked(db, user['id'])))


class PushDevices:
    @staticmethod
    def register(db, user, data):
        token = text_value(data, 'token', 4096)
        device = text_value(data, 'dispositivo_id', 128)
        # O token identifica uma inscrição FCM; não depende de um ID escolhido pelo usuário.
        key = hashlib.sha256(token.encode()).hexdigest()
        ref = db.collection('dispositivos_fcm').document(key)
        ref.set({'id_usuario': user['id'], 'dispositivo_id': device, 'token': token, 'atualizado_em': now()})
        # A rotação de token não deixa inscrições antigas da mesma instalação/conta.
        for doc in db.collection('dispositivos_fcm').where('id_usuario', '==', user['id']).stream():
            if doc.id != key and doc.to_dict().get('dispositivo_id') == device:
                try:
                    doc.reference.delete(option=LastUpdateOption(doc.update_time))
                except FailedPrecondition:
                    pass
        return {'mensagem': 'Dispositivo registrado.'}

    @staticmethod
    def remove(db, user, data):
        device = text_value(data, 'dispositivo_id', 128)
        for doc in db.collection('dispositivos_fcm').where('id_usuario', '==', user['id']).stream():
            if doc.to_dict().get('dispositivo_id') == device:
                try:
                    doc.reference.delete(option=LastUpdateOption(doc.update_time))
                except FailedPrecondition:
                    pass
        return {'mensagem': 'Dispositivo removido.'}

    @staticmethod
    def send(db, user_id, title, body):
        results = {'enviados': 0, 'falhas': 0}
        for doc in db.collection('dispositivos_fcm').where('id_usuario', '==', user_id).stream():
            try:
                messaging.send(messaging.Message(token=doc.to_dict()['token'],
                    notification=messaging.Notification(title=title, body=body)))
                results['enviados'] += 1
            except messaging.UnregisteredError:
                try:
                    doc.reference.delete(option=LastUpdateOption(doc.update_time))
                except FailedPrecondition:
                    pass
                results['falhas'] += 1
            except Exception:
                results['falhas'] += 1
        return results
