from flask import Blueprint, jsonify, request
from models.database import bd
from services.autenticacao import token_obrigatorio
from services.disponibilidades import Disponibilidades


disponibilidades_bp = Blueprint('disponibilidades', __name__)


@disponibilidades_bp.route('/', methods=['GET', 'POST'])
@token_obrigatorio
def disponibilidades(usuario_atual):
    if request.method == 'GET':
        resposta, status = Disponibilidades.listar(
            bd, usuario_atual, request.args.get('guia_id'))
    else:
        resposta, status = Disponibilidades.criar(
            bd, usuario_atual, request.get_json(silent=True) or {})
    return jsonify(resposta), status


@disponibilidades_bp.route('/<identificador>', methods=['DELETE'])
@token_obrigatorio
def excluir_disponibilidade(usuario_atual, identificador):
    resposta, status = Disponibilidades.excluir(bd, usuario_atual, identificador)
    return jsonify(resposta), status
