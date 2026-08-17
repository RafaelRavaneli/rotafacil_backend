from flask import Blueprint, request, jsonify
from models.database import bd
from services.autenticacao import Autenticacao

# Cria o Blueprint exclusivo para autenticação
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['POST'])
def login():
    # Recebe os dados da internet e manda para a "Inteligência"
    resposta, status = Autenticacao.login(bd, request.get_json())
    return jsonify(resposta), status