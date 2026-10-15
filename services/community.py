"""Contratos de catalogo de guias, vinculos e dispositivos FCM."""
import hashlib
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
    def guide(db, guide_id):
        guide = required(db.collection('usuarios').document(guide_id))
        data = guide.to_dict() or {}
        if data.get('tipo') != 'guia' or not data.get('ativo', True):
            raise CommunityError('Guia indisponível.', 404)
        specialties = data.get('especialidades')
        if not isinstance(specialties, list):
            specialties = []
        public = guide_public(guide)
        public.update({
            'descricao_profissional': str(
                data.get('descricao_profissional') or '').strip(),
            'especialidades': [str(item).strip() for item in specialties
                               if str(item).strip()],
        })
        return public

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
    def manage_invitation(db, user, invitation_id, action):
        ref = db.collection('convites_guias').document(invitation_id)
        doc = required(ref)
        invite = doc.to_dict()
        action = (action or '').strip().lower()
        is_agency = (user.get('tipo') == 'agencia' and
                     invite.get('id_agencia') == user.get('id'))
        is_guide = (user.get('tipo') == 'guia' and
                    invite.get('id_guia') == user.get('id'))

        if action == 'reenviar':
            if not is_agency:
                raise CommunityError('Somente a agência pode reenviar o convite.', 403)
            if invite.get('status') not in {'recusado', 'revogado', 'desligado'}:
                raise CommunityError('Este convite não pode ser reenviado agora.', 409)
            guide = required(db.collection('usuarios').document(invite['id_guia']))
            if guide.to_dict().get('tipo') != 'guia' or not guide.to_dict().get('ativo', True):
                raise CommunityError('Guia indisponível.', 404)
            values = {
                'status': 'pendente',
                'reenviado_em': now(),
                'respondido_em': None,
                'encerrado_em': None,
            }
        elif action == 'revogar':
            if not is_agency:
                raise CommunityError('Somente a agência pode revogar o convite.', 403)
            if invite.get('status') != 'pendente':
                raise CommunityError('Somente convites pendentes podem ser revogados.', 409)
            values = {'status': 'revogado', 'encerrado_em': now()}
        elif action == 'desligar':
            if not (is_agency or is_guide):
                raise CommunityError('Somente os participantes podem encerrar o vínculo.', 403)
            if invite.get('status') != 'aceito':
                raise CommunityError('Somente vínculos aceitos podem ser encerrados.', 409)
            if Community._vinculo_tem_reservas_ativas(db, invite):
                raise CommunityError(
                    'Não é possível encerrar o vínculo enquanto houver reservas ativas.', 409)
            Community._remover_guia_das_trilhas(db, invite)
            values = {
                'status': 'desligado',
                'encerrado_em': now(),
                'encerrado_por': user.get('id'),
            }
        else:
            raise CommunityError('Ação de vínculo inválida.')

        update_checked(ref, doc, values)
        return {'id': ref.id, **invite, **values}

    @staticmethod
    def _aliases(db, user_id):
        aliases = {user_id}
        doc = db.collection('usuarios').document(user_id).get()
        if doc.exists and (doc.to_dict() or {}).get('email'):
            aliases.add(doc.to_dict()['email'])
        return aliases

    @staticmethod
    def _trilhas_do_vinculo(db, invite):
        agency_aliases = Community._aliases(db, invite['id_agencia'])
        guide_aliases = Community._aliases(db, invite['id_guia'])
        return [doc for doc in db.collection('trilhas').stream()
                if (doc.to_dict() or {}).get('criado_por') in agency_aliases
                and (doc.to_dict() or {}).get('id_guia') in guide_aliases]

    @staticmethod
    def _vinculo_tem_reservas_ativas(db, invite):
        trail_ids = {doc.id for doc in Community._trilhas_do_vinculo(db, invite)}
        for booking in db.collection('agendamentos').stream():
            data = booking.to_dict() or {}
            status = str(data.get('status') or '').strip().lower()
            if (data.get('id_trilha') in trail_ids and status in {
                    'agendado', 'pendente', 'confirmado', 'em_andamento'}):
                return True
        return False

    @staticmethod
    def _remover_guia_das_trilhas(db, invite):
        for trail in Community._trilhas_do_vinculo(db, invite):
            trail.reference.update({'id_guia': invite['id_agencia']})

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
    def send(db, user_id, title, body, dados=None):
        results = {'enviados': 0, 'falhas': 0}
        for doc in db.collection('dispositivos_fcm').where('id_usuario', '==', user_id).stream():
            try:
                messaging.send(messaging.Message(token=doc.to_dict()['token'],
                    notification=messaging.Notification(title=title, body=body),
                    data={key: str(value) for key, value in (dados or {}).items()}))
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
