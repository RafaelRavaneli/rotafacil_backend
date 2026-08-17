from flask import Blueprint, request, jsonify
from models.database import bd
from services.trilhas import Trilhas
from services.autenticacao import token_obrigatorio, requer_papel

# Inicializa o Blueprint
trilhas_bp = Blueprint('trilhas', __name__)

# Apenas Guias e Agências podem criar trilhas
@trilhas_bp.route('/', methods=['POST'])
@token_obrigatorio
@requer_papel('guia', 'agencia')
def criar_trilha(usuario_atual):
    # Passamos o usuario_atual para o serviço saber quem está criando
    resposta, status = Trilhas.cadastrar_trilha(bd, request.get_json(), usuario_atual)
    return jsonify(resposta), status

# Público (Qualquer um com token pode ver)
@trilhas_bp.route('/', methods=['GET'])
@token_obrigatorio
def listar_trilhas(usuario_atual):
    resposta, status = Trilhas.listar_trilhas(bd)
    return jsonify(resposta), status

# Busca avançada (Qualquer um com token pode buscar)
@trilhas_bp.route('/busca', methods=['GET'])
@token_obrigatorio
def buscar_trilhas_avancada(usuario_atual):
    # Pega os parâmetros da URL (Query Params) e transforma num dicionário
    filtros = request.args.to_dict()
    resposta, status = Trilhas.buscar_trilhas_avancado(bd, filtros)
    return jsonify(resposta), status