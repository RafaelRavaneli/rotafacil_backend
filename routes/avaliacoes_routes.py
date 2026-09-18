from flask import Blueprint, request, jsonify
from models.database import bd
from services.avaliacoes import Avaliacoes
from services.autenticacao import token_obrigatorio

avaliacoes_bp = Blueprint('avaliacoes', __name__)

# --- Avaliar uma trilha concluída ---
@avaliacoes_bp.route('/', methods=['POST'])
@token_obrigatorio
def adicionar_avaliacao(usuario_atual):
    dados = request.get_json(silent=True) or {}
    resposta, status = Avaliacoes.adicionar_avaliacao(
        bd,
        usuario_atual.get('id'),
        dados.get('id_trilha'),
        dados.get('nota'),
        dados.get('comentario'),
        usuario_atual.get('nome')
    )
    return jsonify(resposta), status

# --- Listar avaliações de uma trilha ---
@avaliacoes_bp.route('/trilha/<id_trilha>', methods=['GET'])
@token_obrigatorio
def listar_avaliacoes_trilha(usuario_atual, id_trilha):
    resposta, status = Avaliacoes.listar_avaliacoes_trilha(bd, id_trilha)
    return jsonify(resposta), status