from flask import Blueprint, request, jsonify
from models.database import bd
from services.autenticacao import Autenticacao
from services.autenticacao import token_obrigatorio

# Cria o Blueprint exclusivo para autenticação
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    # Recebe os dados da internet e manda para a "Inteligência"
    resposta, status = Autenticacao.login(bd, request.get_json())
    return jsonify(resposta), status

@auth_bp.route('/senha', methods=['PUT'])
@token_obrigatorio
def alterar_senha(usuario_atual):
    resposta, status = Autenticacao.alterar_senha(
        bd, usuario_atual, request.get_json(silent=True) or {})
    return jsonify(resposta), status


@auth_bp.route('/email/solicitar', methods=['POST'])
def solicitar_confirmacao_email():
    from services.verificacao_email import VerificacaoEmail
    resposta, status = VerificacaoEmail.solicitar(bd, request.get_json(silent=True) or {})
    return jsonify(resposta), status


@auth_bp.route('/email/confirmar', methods=['POST'])
def confirmar_email():
    from services.verificacao_email import VerificacaoEmail
    resposta, status = VerificacaoEmail.confirmar(bd, request.get_json(silent=True) or {})
    return jsonify(resposta), status
