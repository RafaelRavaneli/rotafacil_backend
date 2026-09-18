from flask import Blueprint, request, jsonify
from models.database import bd
from services.favoritos import Favoritos
from services.autenticacao import token_obrigatorio

favoritos_bp = Blueprint('favoritos', __name__)

# --- Adicionar aos favoritos ---
@favoritos_bp.route('/', methods=['POST'])
@token_obrigatorio
def adicionar_favorito(usuario_atual):
    dados = request.get_json(silent=True) or {}
    resposta, status = Favoritos.adicionar_favorito(bd, usuario_atual.get('id'), dados.get('id_trilha'))
    return jsonify(resposta), status

# --- Remover dos favoritos ---
@favoritos_bp.route('/<id_trilha>', methods=['DELETE'])
@token_obrigatorio
def remover_favorito(usuario_atual, id_trilha):
    resposta, status = Favoritos.remover_favorito(bd, usuario_atual.get('id'), id_trilha)
    return jsonify(resposta), status

# --- Listar meus favoritos ---
@favoritos_bp.route('/', methods=['GET'])
@token_obrigatorio
def listar_favoritos(usuario_atual):
    resposta, status = Favoritos.listar_favoritos(bd, usuario_atual.get('id'))
    return jsonify(resposta), status