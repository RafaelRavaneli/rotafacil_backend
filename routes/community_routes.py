from functools import wraps
from flask import Blueprint, request, jsonify
from models.database import bd
from services.autenticacao import token_obrigatorio
from services.community import Community, CommunityError, PushDevices

community_bp = Blueprint('community', __name__)


def endpoint(fn):
    @wraps(fn)
    @token_obrigatorio
    def wrapped(user, *args, **kwargs):
        try:
            result = fn(user, *args, **kwargs)
            return jsonify(result)
        except CommunityError as error:
            return jsonify({'erro': str(error)}), error.status
    return wrapped


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise CommunityError('Envie um objeto JSON válido.')
    return value


@community_bp.route('/guias', methods=['GET'])
@endpoint
def guides(user):
    return Community.guides(bd)


@community_bp.route('/conversas', methods=['GET', 'POST'])
@endpoint
def chats(user):
    return Community.chats(bd, user) if request.method == 'GET' else Community.start_chat(bd, user, body())


@community_bp.route('/conversas/<thread_id>/mensagens', methods=['GET', 'POST'])
@endpoint
def chat_messages(user, thread_id):
    return Community.messages(bd, user, 'conversas', thread_id) if request.method == 'GET' else Community.send(bd, user, 'conversas', thread_id, body())


@community_bp.route('/suporte', methods=['GET', 'POST'])
@endpoint
def tickets(user):
    return Community.tickets(bd, user) if request.method == 'GET' else Community.open_ticket(bd, user, body())


@community_bp.route('/suporte/<thread_id>/mensagens', methods=['GET', 'POST'])
@endpoint
def support_messages(user, thread_id):
    return Community.messages(bd, user, 'suporte', thread_id) if request.method == 'GET' else Community.send(bd, user, 'suporte', thread_id, body())


@community_bp.route('/convites-guias', methods=['GET', 'POST'])
@endpoint
def invitations(user):
    return Community.invitations(bd, user) if request.method == 'GET' else Community.invite(bd, user, body())


@community_bp.route('/convites-guias/<invitation_id>', methods=['PUT'])
@endpoint
def answer_invitation(user, invitation_id):
    return Community.answer_invitation(bd, user, invitation_id, body())


@community_bp.route('/usuarios/fcm-token', methods=['POST', 'DELETE'])
@endpoint
def devices(user):
    return PushDevices.register(bd, user, body()) if request.method == 'POST' else PushDevices.remove(bd, user, request.args.to_dict())


@community_bp.route('/usuarios/fcm-token/teste', methods=['POST'])
@endpoint
def test_push(user):
    # Somente a própria conta pode receber a mensagem de teste.
    return PushDevices.send(bd, user['id'], 'RotaFácil', 'Notificações ativadas neste dispositivo.')
