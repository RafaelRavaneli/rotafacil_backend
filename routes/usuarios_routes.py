from flask import Blueprint, request, jsonify
from models.database import bd
from services.usuarios import Usuarios
from services.autenticacao import token_obrigatorio, requer_papel, eh_dono_ou_tem_papel
from services.notificacoes import Notificacoes

usuarios_bp = Blueprint('usuarios', __name__)

# --- Cadastro: público, sem RBAC (ninguém tem token ainda) ---
@usuarios_bp.route('/', methods=['POST'])
def cadastrar_usuario():
    resposta, status = Usuarios.cadastrar_usuario(bd, request.get_json())
    return jsonify(resposta), status

# --- Listar TODOS os usuários: só admin ---
@usuarios_bp.route('/', methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def listar_usuarios(usuario_atual):
    resposta, status = Usuarios.listar_usuarios(bd)
    return jsonify(resposta), status

# --- Buscar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['GET'])
@token_obrigatorio
def listar_usuario_por_email(usuario_atual, email):
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver o próprio perfil."}), 403
    resposta, status = Usuarios.listar_usuario_por_email(bd, email)
    return jsonify(resposta), status

# --- Buscar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['GET'])
@token_obrigatorio
def listar_usuario_por_id(usuario_atual, id):
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode ver o próprio perfil."}), 403
    resposta, status = Usuarios.listar_usuario_por_id(bd, id)
    return jsonify(resposta), status

# --- Atualizar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['PUT'])
@token_obrigatorio
def atualizar_usuario_por_email(usuario_atual, email):
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode editar o próprio perfil."}), 403
    resposta, status = Usuarios.atualizar_usuario_por_email(bd, email, request.get_json())
    return jsonify(resposta), status

# --- Atualizar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['PUT'])
@token_obrigatorio
def atualizar_usuario_por_id(usuario_atual, id):
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode editar o próprio perfil."}), 403
    resposta, status = Usuarios.atualizar_usuario_por_id(bd, id, request.get_json())
    return jsonify(resposta), status

# --- Deletar por e-mail: dono ou admin ---
@usuarios_bp.route('/email/<email>', methods=['DELETE'])
@token_obrigatorio
def deletar_usuario_por_email(usuario_atual, email):
    if not eh_dono_ou_tem_papel(usuario_atual, email, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode deletar o próprio perfil."}), 403
    resposta, status = Usuarios.deletar_usuario_por_email(bd, email)
    return jsonify(resposta), status

# --- Deletar por ID: dono ou admin ---
@usuarios_bp.route('/<id>', methods=['DELETE'])
@token_obrigatorio
def deletar_usuario_por_id(usuario_atual, id):
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode deletar o próprio perfil."}), 403
    resposta, status = Usuarios.deletar_usuario_por_id(bd, id)
    return jsonify(resposta), status

# --- Verificar/desverificar guia ou agência: exclusivo admin ---
@usuarios_bp.route('/<id>/verificar', methods=['PUT'])
@token_obrigatorio
@requer_papel('admin')
def verificar_usuario(usuario_atual, id):
    dados = request.get_json(silent=True) or {}
    verificado = dados.get('verificado', True)
    resposta, status = Usuarios.verificar_usuario(bd, id, verificado)
    return jsonify(resposta), status

# --- Mudar tipo de usuário (com validação de documento se virar guia/agencia): dono ou admin ---
@usuarios_bp.route('/<id>/tipo', methods=['PUT'])
@token_obrigatorio
def mudar_tipo_usuario(usuario_atual, id):
    if not eh_dono_ou_tem_papel(usuario_atual, id, 'admin'):
        return jsonify({"erro": "Acesso negado. Você só pode alterar o próprio tipo."}), 403
    dados = request.get_json(silent=True) or {}
    resposta, status = Usuarios.mudar_tipo_usuario(bd, id, dados.get('tipo'), dados.get('documento'))
    return jsonify(resposta), status

# --- Contato de emergência: guia com agendamento ativo, ou admin ---
@usuarios_bp.route('/<id>/contato-emergencia', methods=['GET'])
@token_obrigatorio
@requer_papel('guia', 'agencia', 'admin')
def obter_contato_emergencia(usuario_atual, id):
    resposta, status = Usuarios.obter_contato_emergencia(bd, id, usuario_atual)
    return jsonify(resposta), status

# --- Registrar token de notificação (FCM) do dispositivo atual ---
@usuarios_bp.route('/fcm-token', methods=['POST'])
@token_obrigatorio
def registrar_fcm_token(usuario_atual):
    dados = request.get_json(silent=True) or {}
    resposta, status = Notificacoes.registrar_token(bd, usuario_atual.get('id'), dados.get('token'))
    return jsonify(resposta), status

# --- Remover token de notificação (ex: no logout do app) ---
@usuarios_bp.route('/fcm-token', methods=['DELETE'])
@token_obrigatorio
def remover_fcm_token(usuario_atual):
    dados = request.get_json(silent=True) or {}
    resposta, status = Notificacoes.remover_token(bd, usuario_atual.get('id'), dados.get('token'))
    return jsonify(resposta), status