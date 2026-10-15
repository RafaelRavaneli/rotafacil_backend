from flask import Blueprint, jsonify, request

from models.database import bd
from services.autenticacao import token_obrigatorio
from services.notificacoes import Notificacoes


notificacoes_bp = Blueprint('notificacoes', __name__)


@notificacoes_bp.route('/', methods=['GET'])
@token_obrigatorio
def listar(usuario_atual):
    resposta, status = Notificacoes.listar(bd, usuario_atual)
    return jsonify(resposta), status


@notificacoes_bp.route('/<identificador>/lida', methods=['PUT'])
@token_obrigatorio
def marcar_lida(usuario_atual, identificador):
    resposta, status = Notificacoes.marcar_lida(
        bd, usuario_atual, identificador)
    return jsonify(resposta), status


@notificacoes_bp.route('/lidas', methods=['PUT'])
@token_obrigatorio
def marcar_todas_lidas(usuario_atual):
    resposta, status = Notificacoes.marcar_todas_lidas(bd, usuario_atual)
    return jsonify(resposta), status


@notificacoes_bp.route('/preferencias', methods=['GET', 'PUT'])
@token_obrigatorio
def preferencias(usuario_atual):
    if request.method == 'GET':
        resposta, status = Notificacoes.obter_preferencias(bd, usuario_atual)
    else:
        resposta, status = Notificacoes.atualizar_preferencias(
            bd, usuario_atual, request.get_json(silent=True) or {})
    return jsonify(resposta), status


@notificacoes_bp.route('/teste', methods=['POST'])
@token_obrigatorio
def testar(usuario_atual):
    resultado = Notificacoes.notificar_usuario(
        bd, usuario_atual.get('id'), 'Notificação de teste',
        'A central de notificações do RotaFácil está funcionando.',
        {'tipo': 'sistema'})
    return jsonify(resultado), 200
