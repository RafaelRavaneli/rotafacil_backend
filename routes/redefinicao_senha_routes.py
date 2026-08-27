# routes/redefinicao_senha_routes.py

from flask import Blueprint, request, jsonify
from models.database import bd
from services.redefinicao_senha import RedefinicaoSenha

redefinicao_senha_bp = Blueprint('redefinicao_senha', __name__)

# --- Solicitar redefinição: público, sem RBAC (ninguém tem token ainda) ---
@redefinicao_senha_bp.route('/solicitar', methods=['POST'])
def solicitar_redefinicao():
    dados = request.get_json(silent=True) or {}
    resposta, status = RedefinicaoSenha.solicitar_redefinicao(bd, dados)
    return jsonify(resposta), status

# --- Efetivar a nova senha: público, o próprio token já é a "credencial" ---
@redefinicao_senha_bp.route('/redefinir', methods=['POST'])
def redefinir_senha():
    dados = request.get_json(silent=True) or {}
    resposta, status = RedefinicaoSenha.redefinir_senha(bd, dados)
    return jsonify(resposta), status