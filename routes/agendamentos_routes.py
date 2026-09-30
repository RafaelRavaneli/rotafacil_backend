from flask import Blueprint, request, jsonify
from models.database import bd
from services.agendamentos import Agendamentos
from services.autenticacao import token_obrigatorio, requer_papel, eh_dono_ou_tem_papel

# Inicializa o Blueprint
agendamentos_bp = Blueprint('agendamentos', __name__)

# --- Criar um Agendamento ---
# Apenas turistas (ou agências, se desejar) devem poder agendar
@agendamentos_bp.route('/', methods=['POST'])
@token_obrigatorio
@requer_papel('usuario', 'agencia', 'guia')
def agendar_trilha(usuario_atual):
    dados = request.get_json(silent=True) or {}

    # Preenche automaticamente o ID do usuário logado por segurança
    dados['id_usuario'] = usuario_atual.get('id')   # ← aqui

    resposta, status = Agendamentos.agendar_trilha(bd, dados)
    return jsonify(resposta), status

# --- Listar Agendamentos do Turista ---
@agendamentos_bp.route('/usuario/<id_usuario>', methods=['GET'])
@token_obrigatorio
def listar_agendamentos_usuario(usuario_atual, id_usuario):
    # Garante que o turista só veja os próprios agendamentos (ou admin veja de todos)
    if not eh_dono_ou_tem_papel(usuario_atual, id_usuario, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver seus próprios agendamentos."}), 403
        
    resposta, status = Agendamentos.listar_agendamentos_usuario(bd, id_usuario)
    return jsonify(resposta), status

# --- Listar Agendamentos do Guia ---
@agendamentos_bp.route('/guia/<id_guia>', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def listar_agendamentos_guia(usuario_atual, id_guia):
    # Garante que o guia só veja a própria agenda
    if not eh_dono_ou_tem_papel(usuario_atual, id_guia, 'admin', 'agencia'):
        return jsonify({"erro": "Acesso negado. Você só pode acessar sua própria agenda."}), 403
        
    resposta, status = Agendamentos.listar_agendamentos_guia(bd, id_guia)
    return jsonify(resposta), status

# --- Cancelar Agendamento ---
@agendamentos_bp.route('/<id_agendamento>/cancelar', methods=['PUT'])
@token_obrigatorio
def cancelar_agendamento(usuario_atual, id_agendamento):
    resposta, status = Agendamentos.cancelar_agendamento(bd, id_agendamento, usuario_atual)
    return jsonify(resposta), status

# --- Dashboard do guia/agência: dono ou admin ---
@agendamentos_bp.route('/dashboard/<id_guia>', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def dashboard_guia(usuario_atual, id_guia):
    if not eh_dono_ou_tem_papel(usuario_atual, id_guia, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver seu próprio dashboard."}), 403
    resposta, status = Agendamentos.dashboard_guia(bd, id_guia)
    return jsonify(resposta), status

# --- Check-in: confirma início da trilha ---
@agendamentos_bp.route('/<id_agendamento>/checkin', methods=['PUT'])
@token_obrigatorio
def checkin_agendamento(usuario_atual, id_agendamento):
    dados = request.get_json(silent=True) or {}
    resposta, status = Agendamentos.fazer_checkin(
        bd, id_agendamento, usuario_atual, dados.get('latitude'), dados.get('longitude')
    )
    return jsonify(resposta), status

# --- Check-out: confirma conclusão da trilha ---
@agendamentos_bp.route('/<id_agendamento>/checkout', methods=['PUT'])
@token_obrigatorio
def checkout_agendamento(usuario_atual, id_agendamento):
    resposta, status = Agendamentos.fazer_checkout(bd, id_agendamento, usuario_atual)
    return jsonify(resposta), status

# --- Rota extra para testar/disparar os lembretes diários na hora (sem esperar o horário agendado) ---
@agendamentos_bp.route('/testar-lembretes', methods=['POST'])
@token_obrigatorio
@requer_papel('admin')
def testar_lembretes(usuario_atual):
    from services.agendador import enviar_lembretes_diarios
    enviar_lembretes_diarios()
    return jsonify({"mensagem": "Rotina de lembretes executada manualmente."}), 200