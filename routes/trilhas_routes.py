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

# --- Buscar uma trilha específica: qualquer usuário logado ---
@trilhas_bp.route('/<id_trilha>', methods=['GET'])
@token_obrigatorio
def buscar_trilha_por_id(usuario_atual, id_trilha):
    resposta, status = Trilhas.buscar_trilha_por_id(bd, id_trilha)
    return jsonify(resposta), status

# --- Buscar trilhas por período: qualquer usuário logado ---
@trilhas_bp.route('/periodo', methods=['GET'])
@token_obrigatorio
def listar_trilhas_por_data(usuario_atual):
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    if not data_inicio or not data_fim:
        return jsonify({"erro": "Informe data_inicio e data_fim como query params."}), 400
    resposta, status = Trilhas.listar_trilhas_por_data(bd, data_inicio, data_fim)
    return jsonify(resposta), status

# --- Atualizar trilha: só criador, guia responsável ou admin ---
@trilhas_bp.route('/<id_trilha>', methods=['PUT'])
@token_obrigatorio
def atualizar_trilha(usuario_atual, id_trilha):
    resposta, status = Trilhas.atualizar_trilha(bd, id_trilha, request.get_json(silent=True) or {}, usuario_atual)
    return jsonify(resposta), status

# --- Deletar trilha: só criador, guia responsável ou admin ---
@trilhas_bp.route('/<id_trilha>', methods=['DELETE'])
@token_obrigatorio
def deletar_trilha(usuario_atual, id_trilha):
    resposta, status = Trilhas.deletar_trilha(bd, id_trilha, usuario_atual)
    return jsonify(resposta), status

from services.clima import Clima

# --- Previsão do tempo para os dias da trilha ---
@trilhas_bp.route('/<id_trilha>/clima', methods=['GET'])
@token_obrigatorio
def previsao_tempo_trilha(usuario_atual, id_trilha):
    resposta, status = Clima.obter_previsao_trilha(bd, id_trilha)
    return jsonify(resposta), status