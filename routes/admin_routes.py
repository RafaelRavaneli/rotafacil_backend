from flask import Blueprint, request, jsonify
from models.database import bd
from services.administracao import Administracao
from services.community import CommunityError
from services.autenticacao import token_obrigatorio, requer_papel

admin_bp=Blueprint('admin',__name__)

@admin_bp.after_request
def nao_armazenar(response):
    response.headers['Cache-Control']='no-store, private'
    return response

def executar(funcao,*args):
    try:
        resposta,status=funcao(bd,*args)
    except CommunityError as error:
        resposta,status={'erro':str(error)},error.status
    except Exception:
        resposta,status={'erro':'Não foi possível confirmar a operação administrativa. Recarregue antes de tentar novamente.'},503
    return jsonify(resposta),status

@admin_bp.route('/contas',methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def contas(usuario_atual):
    return executar(Administracao.contas,usuario_atual,request.args.to_dict())

@admin_bp.route('/contas/<id>/acao',methods=['POST'])
@token_obrigatorio
@requer_papel('admin')
def conta(usuario_atual,id):
    return executar(Administracao.conta,usuario_atual,id,request.get_json(silent=True))

@admin_bp.route('/roteiros',methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def roteiros(usuario_atual):
    return executar(Administracao.roteiros,usuario_atual,request.args.to_dict())

@admin_bp.route('/roteiros/<id>/acao',methods=['POST'])
@token_obrigatorio
@requer_papel('admin')
def roteiro(usuario_atual,id):
    return executar(Administracao.roteiro,usuario_atual,id,request.get_json(silent=True))

@admin_bp.route('/historico',methods=['GET'])
@token_obrigatorio
@requer_papel('admin')
def historico(usuario_atual):
    return executar(Administracao.historico,usuario_atual,request.args.to_dict())
